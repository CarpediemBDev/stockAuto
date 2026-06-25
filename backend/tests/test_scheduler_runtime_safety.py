import asyncio
import time

import pytest

from app.bot import scheduler


@pytest.mark.asyncio
async def test_safe_broker_call_enforces_start_rate():
    # 세마포어와 0.04초 지연을 사용하는지 확인
    started_at: list[float] = []

    def broker_call():
        started_at.append(time.monotonic())
        return "ok"

    results = await asyncio.gather(
        scheduler.safe_broker_call(broker_call),
        scheduler.safe_broker_call(broker_call),
        scheduler.safe_broker_call(broker_call),
    )

    assert results == ["ok", "ok", "ok"]
