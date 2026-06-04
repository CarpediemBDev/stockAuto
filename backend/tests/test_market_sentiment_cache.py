import asyncio

import pytest

import app.scanner.scanner as scanner


def reset_sentiment_cache() -> None:
    scanner._sentiment_cache["value"] = None
    scanner._sentiment_cache["timestamp"] = 0
    scanner._sentiment_locks = {}


@pytest.mark.asyncio
async def test_check_market_sentiment_serializes_concurrent_cache_misses(monkeypatch):
    reset_sentiment_cache()
    call_count = 0

    async def fake_calculate_market_sentiment() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return "BULLISH"

    monkeypatch.setattr(scanner, "_calculate_market_sentiment", fake_calculate_market_sentiment)

    results = await asyncio.gather(*(scanner.check_market_sentiment() for _ in range(10)))

    assert results == ["BULLISH"] * 10
    assert call_count == 1

    assert await scanner.check_market_sentiment() == "BULLISH"
    assert call_count == 1


@pytest.mark.asyncio
async def test_check_market_sentiment_refreshes_expired_cache(monkeypatch):
    reset_sentiment_cache()
    scanner._sentiment_cache["value"] = "BEARISH"
    scanner._sentiment_cache["timestamp"] = 0
    call_count = 0

    async def fake_calculate_market_sentiment() -> str:
        nonlocal call_count
        call_count += 1
        return "NEUTRAL"

    monkeypatch.setattr(scanner, "_calculate_market_sentiment", fake_calculate_market_sentiment)

    assert await scanner.check_market_sentiment() == "NEUTRAL"
    assert call_count == 1

    assert await scanner.check_market_sentiment() == "NEUTRAL"
    assert call_count == 1
