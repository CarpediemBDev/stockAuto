"""회귀: 이벤트 루프 격리 — 2026-07-16 브라우저 QA 결함 1·2.

결함 1(치명): POST /api/v1/backtest/run 핸들러와 관리자 토너먼트 BackgroundTask가
async 경로에서 동기 pandas 중연산(sim.run / prepare_data)을 직접 실행해, 백테스트가
도는 내내 메인 이벤트 루프가 점거되고 전체 API가 무응답이 됐다(py-spy 스택 덤프로 확진).
수정 후 두 경로 모두 워커 스레드(asyncio.to_thread / Starlette 스레드풀)로 격리된다.

결함 2(높음): 모듈 전역 asyncio.Semaphore(kis_semaphore)가 최초 경합 시점의 루프에
바인딩된 채 APScheduler 잡들이 asyncio.run으로 만드는 단명 루프에서 재사용돼
"bound to a different event loop" RuntimeError로 유저 트레이딩 사이클이 통째로
중단됐다(백엔드 재기동 후에도 394회 재발). 수정 후 세마포어는 루프별로 발급된다.
"""

import ast
import asyncio
from pathlib import Path

import app.bot.scheduler as scheduler


def test_kis_semaphore_is_issued_per_event_loop():
    """동일 루프에서는 같은 인스턴스, 루프가 바뀌면 새 인스턴스를 발급해야 한다."""

    async def grab():
        first = scheduler.get_kis_semaphore()
        second = scheduler.get_kis_semaphore()
        assert first is second, "동일 루프 내에서는 세마포어가 재사용되어야 합니다 (동시성 상한 유지)"
        return first

    sem_loop_a = asyncio.run(grab())
    sem_loop_b = asyncio.run(grab())
    assert sem_loop_a is not sem_loop_b, (
        "루프가 달라졌는데 같은 세마포어를 반환하면 'bound to a different event loop' "
        "RuntimeError로 트레이딩 사이클이 중단됩니다 (2026-07-16 QA 결함 2 재발)"
    )


def test_sentiment_lock_is_issued_per_event_loop():
    """scanner.get_sentiment_lock: 동일 루프 재사용, 루프가 바뀌면 새 인스턴스 발급.

    구버전은 id(loop) 키 dict였다 — GC로 루프 id가 재사용되면 죽은 루프에 바인딩됐던
    Lock을 새 루프가 넘겨받아 결함 2와 동일한 RuntimeError가 재발할 수 있었다.
    """
    from app.scanner import scanner

    async def grab():
        first = scanner.get_sentiment_lock()
        second = scanner.get_sentiment_lock()
        assert first is second, "동일 루프 내에서는 sentiment 락이 재사용되어야 합니다 (동시 호출 차단 유지)"
        return first

    lock_loop_a = asyncio.run(grab())
    lock_loop_b = asyncio.run(grab())
    assert lock_loop_a is not lock_loop_b, (
        "루프가 달라졌는데 같은 Lock을 반환하면 'bound to a different event loop' "
        "RuntimeError가 재발합니다 (id(loop) 재사용 충돌)"
    )


def test_sentiment_lock_registry_does_not_leak_dead_loops():
    """죽은 루프의 레지스트리 항목은 자동 회수되어야 한다 (구버전 dict는 무한 증식)."""
    import gc

    from app.scanner import scanner

    async def grab():
        return scanner.get_sentiment_lock()

    for _ in range(10):
        asyncio.run(grab())
    gc.collect()

    live_loops = sum(1 for _ in scanner._sentiment_locks.keys())
    assert live_loops <= 1, (
        f"asyncio.run으로 만든 단명 루프 10개가 종료됐는데 레지스트리에 {live_loops}개가 "
        "남아 있습니다 — WeakKeyDictionary 자동 회수가 깨졌습니다 (메모리 누수 재발)"
    )


def test_safe_broker_call_survives_sequential_event_loops():
    """세마포어 경합(waiter 생성)을 일으킨 뒤 다른 루프에서 재호출해도 죽지 않아야 한다.

    구버전 전역 세마포어는 첫 루프의 경합에서 해당 루프에 바인딩되고, 두 번째 루프의
    경합 시 RuntimeError를 던졌다. APScheduler 잡이 매 사이클 새 루프를 만드는 실환경 재현.
    """
    burst_size = scheduler.KIS_MAX_CONCURRENT_CALLS + 5

    def blocking_probe(value):
        return value * 2

    async def contended_burst():
        tasks = [scheduler.safe_broker_call(blocking_probe, i) for i in range(burst_size)]
        return await asyncio.gather(*tasks)

    first = asyncio.run(contended_burst())
    second = asyncio.run(contended_burst())
    assert first == second == [i * 2 for i in range(burst_size)]


def test_tournament_background_task_stays_sync():
    """run_dynamic_tournament_task는 반드시 동기 함수여야 한다.

    Starlette BackgroundTask는 동기 함수만 스레드풀로 보내고, 코루틴 함수는 메인
    이벤트 루프에서 그대로 await하므로 async로 되돌리면 수 시간짜리 토너먼트가
    전체 API를 무응답으로 만든다 (2026-07-16 QA 결함 1 재발).
    """
    from app.admin.backtest_runner import run_dynamic_tournament_task

    assert not asyncio.iscoroutinefunction(run_dynamic_tournament_task)


def test_run_backtest_offloads_simulation_to_worker_thread():
    """AST 가드: run_backtest 핸들러가 sim.run/prepare_data를 직접 호출하면 실패한다."""
    import app.bot.router_backtest as router_backtest

    tree = ast.parse(Path(router_backtest.__file__).read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_backtest"
    )

    direct_sim_calls = [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"run", "prepare_data"}
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sim"
    ]
    assert not direct_sim_calls, (
        "run_backtest가 sim.run()/sim.prepare_data()를 핸들러(메인 이벤트 루프)에서 직접 "
        "호출하면 백테스트 내내 전체 API가 블로킹됩니다. "
        "asyncio.to_thread(_execute_backtest_blocking, sim) 경로를 유지하세요."
    )

    uses_to_thread = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
        for node in ast.walk(handler)
    )
    assert uses_to_thread, "run_backtest는 백테스트 실행을 asyncio.to_thread로 격리해야 합니다"
