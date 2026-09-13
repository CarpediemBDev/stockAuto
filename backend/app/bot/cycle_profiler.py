"""매매 사이클 구간별 소요 시간 계측.

`[Cycle] Duration`은 사이클 총합만 남긴다. 2026-09 들어 NY 정규장 사이클 간격 중앙값이
8월 129~155초에서 426초까지 늘었는데(발생 창 8/25~8/31), 총합만으로는 어느 구간에서
시간이 새는지 알 수 없어 원인을 확정하지 못했다. Redis 장애·가동 유저 증가·지표 CPU 비용
가설은 측정으로 기각됐고, 남은 후보는 구간을 쪼개야만 보인다.

## 두 가지를 함께 잰다

1. **구간별 누적 시간** - 사용자 흐름의 각 단계, 보유 종목 시세 조회, DB 세션 준비.
   97명의 흐름이 동시에 돌기 때문에 누적 합은 사이클 벽시계보다 클 수 있다. 절대값보다
   구간 간 상대 비중과 호출 횟수가 판단 근거다.

   구간은 중첩된다. `user.exit_signals` 안에 `exit.analyze_single_ticker`와
   `db.micro_session.*`이 들어 있으므로 요약의 값을 서로 더하면 안 된다. 바깥 구간이 크면
   그 안의 하위 구간 중 무엇이 차지하는지를 본다. `cycle.user_flows_wall`은 사용자 흐름
   전체의 벽시계 시간이라, `user.*` 합이 이 값을 크게 넘으면 실제로 병렬로 돈 것이고
   비슷하면 병렬이 무너진 것이다.

2. **이벤트 루프 막힘 시간** - 사용자 흐름은 `asyncio.gather`로 한 루프에서 돈다. 각 단계
   안에 동기 DB·브로커·pandas 작업이 섞여 있으면 루프가 그동안 멈춰 병렬이 순차로
   무너진다. 이 값이 사이클 시간의 대부분이면 원인은 "네트워크를 기다린다"가 아니라
   "루프를 붙잡고 있다"이고, 해법도 완전히 다르다(캐시·중복 제거 대 스레드 분리).

## 사이클 밖에서는 아무것도 하지 않는다

계측 대상 함수들은 테스트·수동 매도·백필 등 사이클 밖에서도 불린다. 프로파일이
활성화되지 않은 컨텍스트에서 `phase()`는 아무 기록도 남기지 않고 곧바로 통과한다.
판정·주문 동작은 전혀 바꾸지 않는다.

## ContextVar를 쓰는 이유

사이클이 프로파일을 한 번 켜면 `asyncio.gather`가 만드는 사용자별 태스크, 그리고
`asyncio.to_thread`로 넘어간 작업까지 같은 프로파일 객체를 본다(둘 다 생성 시점의
컨텍스트를 복사한다). 모듈 전역을 쓰면 사이클 밖 호출과 섞이고, 인자로 넘기면
계측을 위해 수십 개 함수 시그니처를 바꿔야 한다.
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

# 루프 막힘 감시 주기와 기록 임계. 0.1초마다 깨어나는데 0.05초 넘게 늦으면 막힌 것으로 본다.
# 임계를 두는 이유는 스케줄러 지터(수 밀리초)를 막힘으로 오인해 합계를 부풀리지 않기 위함이다.
LOOP_LAG_PROBE_SECONDS = 0.1
LOOP_LAG_RECORD_THRESHOLD_SECONDS = 0.05

LOOP_BLOCKED_PHASE = "loop.blocked"


@dataclass
class PhaseStat:
    total_seconds: float = 0.0
    count: int = 0
    max_seconds: float = 0.0


class CycleProfile:
    """한 사이클 동안의 구간별 누적 시간."""

    def __init__(self) -> None:
        self._stats: dict[str, PhaseStat] = {}
        # to_thread로 넘어간 작업이 동시에 기록할 수 있다. dict 갱신이 원자적이지 않으므로
        # 잠근다. 기록 빈도는 사이클당 수백 회 수준이라 비용은 무시할 수 있다.
        self._lock = threading.Lock()

    def add(self, name: str, seconds: float) -> None:
        if seconds < 0:
            return
        with self._lock:
            stat = self._stats.setdefault(name, PhaseStat())
            stat.total_seconds += seconds
            stat.count += 1
            if seconds > stat.max_seconds:
                stat.max_seconds = seconds

    def snapshot(self) -> dict[str, PhaseStat]:
        with self._lock:
            return {
                name: PhaseStat(stat.total_seconds, stat.count, stat.max_seconds)
                for name, stat in self._stats.items()
            }

    def has_user_flows(self) -> bool:
        """사용자 흐름이 한 번이라도 돌았는가.

        휴장·가동 유저 없음으로 조기 반환한 사이클까지 요약을 남기면 비교할 가치가 없는
        줄이 쌓인다. 휴장 표본이 기준선을 오염시켜 회귀를 가렸던 전례(2026-09)가 있으므로
        요약은 실제로 매매 흐름이 돈 사이클에만 남긴다.
        """
        with self._lock:
            return any(name.startswith("user.") for name in self._stats)

    def summary(self, top: int = 12) -> str:
        """누적 시간이 큰 순서로 한 줄 요약을 만든다."""
        stats = self.snapshot()
        ordered = sorted(stats.items(), key=lambda item: item[1].total_seconds, reverse=True)
        parts = [
            f"{name}={stat.total_seconds:.1f}s/{stat.count}회(max {stat.max_seconds:.2f}s)"
            for name, stat in ordered[:top]
        ]
        return " | ".join(parts) if parts else "(기록 없음)"


_current_profile: contextvars.ContextVar[CycleProfile | None] = contextvars.ContextVar(
    "cycle_profile", default=None
)


def start_cycle_profile() -> tuple[CycleProfile, contextvars.Token]:
    """현재 컨텍스트에 새 프로파일을 켠다. 반환된 토큰으로 반드시 끈다."""
    profile = CycleProfile()
    token = _current_profile.set(profile)
    return profile, token


def end_cycle_profile(token: contextvars.Token) -> None:
    _current_profile.reset(token)


def current_profile() -> CycleProfile | None:
    return _current_profile.get()


@contextmanager
def phase(name: str):
    """구간 소요 시간을 현재 프로파일에 누적한다. 프로파일이 없으면 아무것도 하지 않는다.

    동기 컨텍스트 매니저라 async 함수 안에서 await를 감싸도 된다. 그 경우 기록되는 시간은
    await 대기를 포함한 벽시계 시간이다.
    """
    profile = _current_profile.get()
    if profile is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        profile.add(name, time.perf_counter() - started)


def _record_lag(profile: CycleProfile, elapsed: float) -> None:
    lag = elapsed - LOOP_LAG_PROBE_SECONDS
    if lag > LOOP_LAG_RECORD_THRESHOLD_SECONDS:
        profile.add(LOOP_BLOCKED_PHASE, lag)


async def monitor_loop_lag(profile: CycleProfile) -> None:
    """이벤트 루프가 막힌 시간을 누적한다.

    일정 주기로 잠들었다 깨어나며, 예정보다 늦게 깨어난 만큼이 그 사이 루프를 붙잡은
    동기 작업의 시간이다. 호출자는 사이클이 끝나면 반드시 태스크를 취소하고 기다려야 한다 -
    남겨 두면 `_run_cycle_with_drain`이 후속 태스크 정리를 기다리며 사이클마다 수 초를 잃는다.
    """
    loop = asyncio.get_running_loop()
    while True:
        before = loop.time()
        try:
            await asyncio.sleep(LOOP_LAG_PROBE_SECONDS)
        except asyncio.CancelledError:
            # 취소되는 순간의 구간도 반드시 기록한다.
            #
            # 사용자 흐름이 끝나 루프가 풀리면, 같은 루프 반복 안에서 사이클 본체가 먼저
            # 재개되어 이 태스크를 취소할 수 있다. 그러면 늦게 깨어난 사실을 확인하기 전에
            # 취소되어 사이클의 마지막 막힘 구간이 통째로 사라진다. 사이클 마지막의 동기
            # 작업은 흔히 가장 무거운 사용자 흐름이므로 이것을 놓치면 측정이 체계적으로
            # 과소평가된다(test_cycle_profiler 통합 테스트가 이 누락을 잡았다).
            _record_lag(profile, loop.time() - before)
            raise
        _record_lag(profile, loop.time() - before)


async def stop_loop_lag_monitor(task: asyncio.Task | None) -> None:
    """감시 태스크를 취소하고 끝날 때까지 기다린다."""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
