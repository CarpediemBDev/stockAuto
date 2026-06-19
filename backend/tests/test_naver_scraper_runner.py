from unittest.mock import MagicMock, patch

import pytest

from app.scanner.naver_scraper_runner import fetch_naver_us_rankings


@pytest.mark.asyncio
async def test_fetch_naver_us_rankings_success():
    mock_process = MagicMock()
    mock_process.returncode = 0

    async def mock_communicate():
        return b'["AAPL", "NVDA", "AAPL"]', b""

    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        results = await fetch_naver_us_rankings()

    assert results == {"NAVER_US_RANKING": ["AAPL", "NVDA"]}
    mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_naver_us_rankings_malformed_json_returns_empty():
    mock_process = MagicMock()
    mock_process.returncode = 0

    async def mock_communicate():
        return b"not-json", b""

    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        results = await fetch_naver_us_rankings()

    assert results == {}


@pytest.mark.asyncio
async def test_fetch_naver_us_rankings_node_launch_failure_returns_empty():
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("node not found")):
        results = await fetch_naver_us_rankings()

    assert results == {}
