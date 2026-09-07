"""매매 알림이 이벤트 루프 종료에 휩쓸려 유실되지 않는지 검증하는 회귀 테스트.

배경 결함 — `send_message_async`는 `loop.create_task`로 발송 코루틴을 띄웠다. 그런데 주
호출자인 매매 루프는 BackgroundScheduler 워커 스레드에서 `asyncio.run(async_trading_loop())`
으로 돈다(scheduler.trading_loop_wrapper). `asyncio.run`은 본문이 끝나는 즉시 남은 태스크를
전부 취소하고 루프를 닫으므로, 발송 태스크가 텔레그램 왕복(수백 ms)을 마치기 전에 사이클이
끝나면 알림이 아무 로그도 남기지 않고 통째로 사라졌다. 보유 종목이 줄어 사이클이 짧아질수록
유실률이 100%에 수렴한다 — 실제로 매도 체결은 로그에 남는데 알림만 오지 않았다.

같은 자리에서 `_schedule_background_task`로 띄우는 잔고 스냅샷 갱신도 동일한 원인으로
CancelledError를 맞고 죽어 왔다(운영 로그 339건).

여기서는 (a) 발송이 루프 수명과 무관한 스레드 풀로 나가는지, (b) 사이클 루프가 후속 태스크를
흘려보내고 닫히는지를 검증한다.
"""

import asyncio

import pytest

import app.bot.scheduler as scheduler_mod
import app.core.telegram as telegram_mod


@pytest.fixture
def captured_sync_sends(monkeypatch):
    """실제 HTTP 대신 텔레그램 왕복 지연만 흉내 내어 전송 시도를 관찰한다."""
    sent: list[tuple[int, str]] = []

    def fake_send_message_sync(user_id, text, db=None, parse_mode="Markdown", **kwargs):
        import time

        time.sleep(0.3)  # api.telegram.org 왕복
        sent.append((user_id, text))
        return True

    monkeypatch.setattr(telegram_mod, "send_message_sync", fake_send_message_sync)
    return sent


def test_alert_survives_immediate_loop_teardown(captured_sync_sends):
    """사이클이 발송 직후 곧바로 끝나도 알림은 반드시 전달된다."""

    async def trading_cycle_that_ends_immediately():
        telegram_mod.send_message_async(1, "SELL ADBE 체결")
        # 매도 뒤 남은 작업이 없는 사이클. 기존 구현은 여기서 발송 태스크가 취소됐다.

    asyncio.run(trading_cycle_that_ends_immediately())

    # 스레드 풀 발송이므로 루프가 닫힌 뒤에도 살아남아 완료된다.
    deadline = 5.0
    waited = 0.0
    while not captured_sync_sends and waited < deadline:
        import time

        time.sleep(0.05)
        waited += 0.05

    assert captured_sync_sends == [(1, "SELL ADBE 체결")]


def test_send_message_async_returns_waitable_future(captured_sync_sends):
    """호출자·테스트가 완료를 결정론적으로 기다릴 수 있어야 한다."""

    async def cycle():
        return telegram_mod.send_message_async(7, "BUY QQQ 체결")

    future = asyncio.run(cycle())
    assert future is not None
    assert future.result(timeout=5) is True
    assert captured_sync_sends == [(7, "BUY QQQ 체결")]


def test_cycle_drain_lets_post_fill_tasks_finish():
    """체결 후속 태스크가 루프 종료에 취소되지 않고 완주해야 한다."""
    finished: list[str] = []

    async def slow_post_fill_task():
        await asyncio.sleep(0.3)
        finished.append("equity-snapshot")

    async def cycle():
        scheduler_mod._schedule_background_task(slow_post_fill_task(), "equity-snapshot-refresh-1")
        # 사이클 본문은 후속 태스크보다 먼저 끝난다.

    asyncio.run(scheduler_mod._run_cycle_with_drain(cycle(), "trading_loop"))

    assert finished == ["equity-snapshot"]


def test_cycle_drain_gives_up_on_hung_task_instead_of_blocking_forever(monkeypatch):
    """멎어 버린 후속 태스크가 다음 사이클을 무한정 붙잡지 않아야 한다."""
    monkeypatch.setattr(scheduler_mod, "CYCLE_DRAIN_TIMEOUT_SECONDS", 0.2)

    async def hung_task():
        await asyncio.sleep(30)

    async def cycle():
        scheduler_mod._schedule_background_task(hung_task(), "hung")

    import time

    started = time.monotonic()
    asyncio.run(scheduler_mod._run_cycle_with_drain(cycle(), "trading_loop"))
    elapsed = time.monotonic() - started

    assert elapsed < 5.0
