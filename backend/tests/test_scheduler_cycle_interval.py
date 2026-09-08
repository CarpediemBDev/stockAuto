"""매매 사이클의 실제 주기가 등록값과 다른 이유를 재현으로 고정한다.

main_trade_job은 `'interval', minutes=1`로 등록되어 있는데 실측 간격은 중앙값 124초
(범위 104~846초)였다. 이 파일은 그 차이가 환경 탓이나 우연이 아니라 APScheduler의
확정적인 동작이라는 것을 증명한다.

메커니즘은 두 가지가 겹친 것이다.

1. interval 트리거는 다음 시각을 "직전 완료 시각"이 아니라 "직전 예정 시각"에서 뽑는다.
   따라서 예정 시각은 사이클 길이와 무관하게 T, T+60, T+120 으로 고정된다.
2. 잡 기본값이 max_instances=1이라, 앞 사이클이 아직 돌고 있는 동안 도착한 틱은
   실행되지 못하고 버려진다. 그 틱은 뒤로 밀리는 것이 아니라 사라진다.

결과적으로 사이클이 61초 걸리면 다음 실행은 60초 뒤가 아니라 120초 뒤다. 사이클 수를
시간 단위처럼 쓰는 게이트는 전부 이만큼 조용히 늘어진다. 그래서 방어·수확 게이트를
벽시계 기준으로 바꾼 것이다.
"""

import logging
import time
from datetime import datetime

import pytest
from apscheduler.events import EVENT_JOB_MAX_INSTANCES
from apscheduler.schedulers.background import BackgroundScheduler


def test_apscheduler_job_defaults_are_the_ones_production_inherits():
    """운영 잡이 물려받는 기본값을 고정한다.

    main_trade_job은 max_instances를 명시하지 않으므로 이 기본값이 그대로 적용된다.
    APScheduler가 기본값을 바꾸면 이 테스트가 먼저 깨져야 한다.
    """
    scheduler = BackgroundScheduler()
    try:
        defaults = scheduler._job_defaults
        assert defaults["max_instances"] == 1
        assert defaults["coalesce"] is True
        assert defaults["misfire_grace_time"] == 1
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_slow_job_loses_the_overlapping_tick_and_doubles_the_interval():
    """사이클이 주기보다 길면 다음 틱이 버려지고 실제 간격이 배로 늘어난다."""
    interval_seconds = 0.5
    job_duration_seconds = 0.7  # 주기보다 길게 잡아 반드시 겹치게 한다

    starts: list[float] = []
    max_instances_events: list[object] = []

    def slow_job():
        starts.append(time.monotonic())
        time.sleep(job_duration_seconds)

    scheduler = BackgroundScheduler()
    scheduler.add_listener(max_instances_events.append, EVENT_JOB_MAX_INSTANCES)
    scheduler.add_job(
        slow_job,
        "interval",
        seconds=interval_seconds,
        id="slow_job",
        next_run_time=datetime.now(),
    )
    scheduler.start()
    try:
        time.sleep(3.2)
    finally:
        scheduler.shutdown(wait=False)

    assert len(starts) >= 3, f"표본이 부족하다: {starts}"

    gaps = [later - earlier for earlier, later in zip(starts, starts[1:])]

    # 겹친 틱이 실제로 버려졌다는 직접 증거. 이 이벤트가 없으면 아래 간격 주장은
    # 단순히 머신이 느렸다는 뜻일 수도 있으므로 반드시 함께 확인한다.
    assert max_instances_events, "겹친 틱이 버려지지 않았다 - 재현 실패"

    # 등록값은 0.5초인데 실제 간격은 그 두 배에 가깝다. 부하가 있는 CI에서도
    # 흔들리지 않도록 하한만 넉넉히 잡는다.
    assert min(gaps) > interval_seconds * 1.5, (
        f"간격이 등록값 근처에 머물렀다 - 스킵이 재현되지 않았다: {gaps}"
    )


def test_apscheduler_skip_warning_reaches_the_application_log():
    """스킵 경고가 stockauto.log까지 도달하는지 확인한다.

    이 조치 전까지 경고는 apscheduler 전용 로거에만 남았고 그 로거에는 파일 핸들러가
    없었다. 그래서 주기가 두 배로 늘어져 있어도 로그상으로는 아무 흔적이 없었다.
    관측 불가가 이 결함을 오래 살려둔 이유이므로 배선 자체를 테스트로 고정한다.
    """
    from app.core.logging import file_handler  # noqa: F401  (임포트 시 배선이 수행된다)

    executor_logger = logging.getLogger("apscheduler.executors.default")

    assert file_handler in executor_logger.handlers, (
        "APScheduler 실행기 로거가 애플리케이션 파일 핸들러에 연결되지 않았다"
    )
    # WARNING이어야 스킵 경고는 남고 잡 등록·실행 INFO 잡음은 걸러진다.
    assert executor_logger.level == logging.WARNING
