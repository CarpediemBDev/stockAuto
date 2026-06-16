import pytest
import asyncio
from unittest.mock import patch, MagicMock
from app.scanner.toss_crawler import fetch_toss_market_scanners
from app.scanner.discovery import get_seed_tickers

@pytest.mark.asyncio
async def test_fetch_toss_market_scanners_success():
    """
    Node.js Puppeteer 서브프로세스가 정상적으로 성공하여 JSON을 반환하는 상황 검증
    """
    mock_json = '{"TOSS_TOTAL_AMT": ["AAPL", "TSLA"], "TOSS_TOTAL_VOL": ["NVDA"], "TOSS_MKT_AMT": [], "TOSS_MKT_VOL": [], "TOSS_SOAR": [], "TOSS_DESCENT": []}'
    
    # Mocking asyncio.create_subprocess_exec
    mock_process = MagicMock()
    mock_process.returncode = 0
    
    async def mock_communicate():
        return mock_json.encode('utf-8'), b''
    
    mock_process.communicate = mock_communicate

    with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
        results = await fetch_toss_market_scanners()
        
        assert "TOSS_TOTAL_AMT" in results
        assert "AAPL" in results["TOSS_TOTAL_AMT"]
        assert "TSLA" in results["TOSS_TOTAL_AMT"]
        assert "NVDA" in results["TOSS_TOTAL_VOL"]
        mock_exec.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_toss_market_scanners_failure_fallback():
    """
    Node.js 스크립트 실패 시 예외를 던지며, discovery가 Yahoo Finance로 Fallback 전환하는지 검증
    """
    mock_process = MagicMock()
    mock_process.returncode = 1 # 에러 반환
    
    async def mock_communicate():
        return b'', b'Puppeteer Error'
        
    mock_process.communicate = mock_communicate

    with patch('asyncio.create_subprocess_exec', return_value=mock_process):
        # Toss crawler 자체는 에러 로그만 남기고 빈 딕셔너리 반환해야 함
        results = await fetch_toss_market_scanners()
        assert results == {}

@pytest.mark.asyncio
async def test_discovery_fallback_to_yahoo():
    """
    Toss 수집 결과가 비어있을 경우 discovery.py가 Yahoo Finance 로직을 호출하는지 검증
    """
    # 1. Toss Crawler는 실패(빈 딕셔너리 반환)했다고 가정
    with patch('app.scanner.discovery.fetch_toss_market_scanners', return_value={}):
        # 2. Yahoo Finance Crawler는 성공했다고 가정
        mock_yahoo_results = {"YAHOO_ACTIVE": ["AMZN"]}
        with patch('app.scanner.discovery.fetch_yahoo_market_scanners', return_value=mock_yahoo_results) as mock_yahoo:
            tickers, source_map = await get_seed_tickers()
            
            # Yahoo 호출 확인
            mock_yahoo.assert_called_once()
            
            # 결과가 Yahoo 데이터 기반으로 잘 나왔는지 확인
            assert "AMZN" in tickers
            assert "YAHOO_ACTIVE" in source_map["AMZN"]
            assert "MARKET" in source_map["AMZN"]
