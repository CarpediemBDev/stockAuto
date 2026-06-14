import pytest

from app.bot.multi_strategy_manager import MultiStrategyManager
from app.bot.scheduler import build_user_signal_context
from app.scanner import discovery


@pytest.mark.asyncio
async def test_public_seed_discovery_never_reads_or_tags_user_watchlists(monkeypatch):
    async def fake_market_scanners():
        return {
            "YAHOO_ACTIVE": ["AAPL"],
            "YAHOO_GAINER": [],
            "YAHOO_LOSER": [],
            "YAHOO_TECH": [],
        }

    monkeypatch.setattr(discovery, "fetch_yahoo_market_scanners", fake_market_scanners)

    tickers, source_map = await discovery.get_seed_tickers()

    assert "AAPL" in tickers
    assert "MARKET" in source_map["AAPL"]
    assert all("WATCHLIST" not in sources for sources in source_map.values())


def test_user_signal_context_routes_only_the_owners_watchlist():
    market_signals = [
        {"ticker": "QQQ", "source": ["MARKET"], "price": 100.0},
        {"ticker": "AAPL", "source": ["MARKET"], "price": 200.0},
    ]
    watchlists = {1: {"AAPL", "NVDA"}, 2: {"MSFT"}}
    watchlist_signal_map = {
        "NVDA": {"ticker": "NVDA", "price": 150.0},
        "MSFT": {"ticker": "MSFT", "price": 300.0},
    }

    user_one_map, _ = build_user_signal_context(
        1, market_signals, watchlists, watchlist_signal_map
    )
    user_two_map, _ = build_user_signal_context(
        2, market_signals, watchlists, watchlist_signal_map
    )

    assert set(user_one_map) == {"QQQ", "AAPL", "NVDA"}
    assert set(user_two_map) == {"QQQ", "AAPL", "MSFT"}
    assert "WATCHLIST" in user_one_map["AAPL"]["source"]
    assert "WATCHLIST" not in user_two_map["AAPL"]["source"]
    assert "MSFT" not in user_one_map
    assert "NVDA" not in user_two_map


def test_focusing_filter_keeps_user_watchlist_tickers_eligible():
    signals = [
        {
            "ticker": "WATCH",
            "source": ["WATCHLIST"],
            "details": {"rvol": 0.5, "premarket_gap_pct": 0.0, "risk": "LOW"},
        },
        {
            "ticker": "MARKET",
            "source": ["MARKET"],
            "details": {"rvol": 3.0, "premarket_gap_pct": 0.0, "risk": "LOW"},
        },
    ]

    focused = MultiStrategyManager.get_focused_tickers(object(), signals)

    assert focused == {"WATCH", "MARKET"}
