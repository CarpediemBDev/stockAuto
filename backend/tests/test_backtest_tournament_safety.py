import pytest
from fastapi import HTTPException

from app.admin.backtest_runner import _build_tournament_cache_path
from app.admin.router import _parse_backtest_date, _parse_backtest_tickers


def test_backtest_date_parser_rejects_invalid_format_and_calendar_date():
    with pytest.raises(HTTPException):
        _parse_backtest_date("2025/01/01", "시작일")

    with pytest.raises(HTTPException):
        _parse_backtest_date("2025-02-30", "시작일")


def test_backtest_ticker_parser_normalizes_and_deduplicates():
    assert _parse_backtest_tickers(" aapl,BRK.B,aapl ") == ["AAPL", "BRK.B"]

    with pytest.raises(HTTPException):
        _parse_backtest_tickers("../escape")


def test_backtest_cache_path_is_deterministic_and_stays_in_cache_directory():
    first = _build_tournament_cache_path(
        "2025-01-01",
        "2025-12-31",
        ["AAPL", "BRK.B", "../escape"],
    )
    second = _build_tournament_cache_path(
        "2025-01-01",
        "2025-12-31",
        ["../escape", "BRK.B", "AAPL"],
    )

    assert first == second
    assert first.parent.name == "backtest_cache"
    assert first.suffix == ".json"
    assert ".." not in first.name
    assert any(parent.name == "backend" for parent in first.parents)
