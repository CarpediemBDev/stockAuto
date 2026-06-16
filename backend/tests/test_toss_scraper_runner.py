from unittest.mock import MagicMock, patch

import pytest

from app.scanner.discovery import get_seed_tickers
from app.scanner.toss_scraper_runner import fetch_toss_market_scanners


@pytest.mark.asyncio
async def test_fetch_toss_market_scanners_success():
    mock_json = (
        '{"TOSS_TOTAL_AMT": ["AAPL", "TSLA"], "TOSS_TOTAL_VOL": ["NVDA"], '
        '"TOSS_MKT_AMT": [], "TOSS_MKT_VOL": [], "TOSS_SOAR": [], "TOSS_DESCENT": []}'
    )
    mock_process = MagicMock()
    mock_process.returncode = 0

    async def mock_communicate():
        return mock_json.encode("utf-8"), b""

    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        results = await fetch_toss_market_scanners()

    assert "TOSS_TOTAL_AMT" in results
    assert "AAPL" in results["TOSS_TOTAL_AMT"]
    assert "TSLA" in results["TOSS_TOTAL_AMT"]
    assert "NVDA" in results["TOSS_TOTAL_VOL"]
    mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_toss_market_scanners_failure_fallback():
    mock_process = MagicMock()
    mock_process.returncode = 1

    async def mock_communicate():
        return b"", b"Puppeteer Error"

    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        results = await fetch_toss_market_scanners()

    assert results == {}


@pytest.mark.asyncio
async def test_fetch_toss_market_scanners_empty_result_with_stderr_is_failure():
    mock_process = MagicMock()
    mock_process.returncode = 0

    async def mock_communicate():
        return b'{"TOSS_TOTAL_AMT": [], "TOSS_TOTAL_VOL": []}', b"Navigation timeout"

    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        results = await fetch_toss_market_scanners()

    assert results == {}


@pytest.mark.asyncio
async def test_fetch_toss_market_scanners_malformed_json_returns_empty():
    mock_process = MagicMock()
    mock_process.returncode = 0

    async def mock_communicate():
        return b"not-json", b""

    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        results = await fetch_toss_market_scanners()

    assert results == {}


@pytest.mark.asyncio
async def test_fetch_toss_market_scanners_node_launch_failure_returns_empty():
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("node not found")):
        results = await fetch_toss_market_scanners()

    assert results == {}


@pytest.mark.asyncio
async def test_discovery_merges_toss_yahoo_and_naver():
    with patch(
        "app.scanner.discovery.fetch_toss_market_scanners",
        return_value={"TOSS_TOTAL_AMT": ["AAPL", "TSLA"]},
    ) as mock_toss:
        with patch(
            "app.scanner.discovery.fetch_yahoo_market_scanners",
            return_value={"YAHOO_ACTIVE": ["AAPL", "AMZN"]},
        ) as mock_yahoo:
            with patch(
                "app.scanner.discovery.fetch_naver_market_scanners",
                return_value={"NAVER_US_RANKING": ["AAPL", "NVDA"]},
            ) as mock_naver:
                tickers, source_map = await get_seed_tickers()

    mock_toss.assert_called_once()
    mock_yahoo.assert_called_once()
    mock_naver.assert_called_once()

    assert "AAPL" in tickers
    assert "TSLA" in tickers
    assert "AMZN" in tickers
    assert "NVDA" in tickers
    assert "TOSS_TOTAL_AMT" in source_map["AAPL"]
    assert "YAHOO_ACTIVE" in source_map["AAPL"]
    assert "NAVER_US_RANKING" in source_map["AAPL"]
    assert "TOSS_TOTAL_AMT" in source_map["TSLA"]
    assert "YAHOO_ACTIVE" in source_map["AMZN"]
    assert "NAVER_US_RANKING" in source_map["NVDA"]
    assert "MARKET" in source_map["AAPL"]


@pytest.mark.asyncio
async def test_discovery_uses_yahoo_when_toss_and_naver_are_empty():
    with patch("app.scanner.discovery.fetch_toss_market_scanners", return_value={}):
        with patch(
            "app.scanner.discovery.fetch_yahoo_market_scanners",
            return_value={"YAHOO_ACTIVE": ["AMZN"]},
        ) as mock_yahoo:
            with patch("app.scanner.discovery.fetch_naver_market_scanners", return_value={}) as mock_naver:
                tickers, source_map = await get_seed_tickers()

    mock_yahoo.assert_called_once()
    mock_naver.assert_called_once()

    assert "AMZN" in tickers
    assert "YAHOO_ACTIVE" in source_map["AMZN"]
    assert "MARKET" in source_map["AMZN"]


@pytest.mark.asyncio
async def test_discovery_uses_naver_when_toss_and_yahoo_fail():
    with patch("app.scanner.discovery.fetch_toss_market_scanners", side_effect=RuntimeError("toss down")):
        with patch("app.scanner.discovery.fetch_yahoo_market_scanners", side_effect=RuntimeError("yahoo down")):
            with patch(
                "app.scanner.discovery.fetch_naver_market_scanners",
                return_value={"NAVER_US_RANKING": ["NVDA"]},
            ):
                tickers, source_map = await get_seed_tickers()

    assert "NVDA" in tickers
    assert "NAVER_US_RANKING" in source_map["NVDA"]
    assert "MARKET" in source_map["NVDA"]


@pytest.mark.asyncio
async def test_discovery_uses_safety_list_when_all_sources_fail():
    with patch("app.scanner.discovery.fetch_toss_market_scanners", side_effect=RuntimeError("toss down")):
        with patch("app.scanner.discovery.fetch_yahoo_market_scanners", side_effect=RuntimeError("yahoo down")):
            with patch("app.scanner.discovery.fetch_naver_market_scanners", side_effect=RuntimeError("naver down")):
                tickers, source_map = await get_seed_tickers()

    assert "AAPL" in tickers
    assert "NVDA" in tickers
    assert source_map["AAPL"] == ["MARKET", "SAFETY_NET"]
