import pytest
from freezegun import freeze_time
from datetime import datetime
from app.bot.scheduler import get_market_session
from app.bot.market_session import MarketSession

def test_market_session_weekend_closed():
    """
    [테스트 목적]
    주말(토/일)일 경우, 무조건 CLOSED(휴장) 상태를 반환하는지 검증합니다.
    """
    with freeze_time("2026-06-13 15:00:00"): # 토요일
        session = get_market_session()
        assert session == MarketSession.CLOSED
        
    with freeze_time("2026-06-14 09:30:00"): # 일요일
        session = get_market_session()
        assert session == MarketSession.CLOSED

def test_market_session_pre_market():
    """
    [테스트 목적]
    정규장 개장 전인 프리마켓(Pre-Market) 시간에 올바르게 PRE_MARKET 상태를 반환하는지 검증합니다.
    (ET 기준 04:00 ~ 09:30, 한국 시간 기준 UTC 08:00 ~ 13:30)
    """
    with freeze_time("2026-06-15 10:00:00"): # 한국 시간 월요일 19:00, ET 06:00
        session = get_market_session()
        assert session == MarketSession.PRE_MARKET

def test_market_session_regular_market():
    """
    [테스트 목적]
    정규 장(Regular Market) 시간 대일 때,
    정확하게 REGULAR 상태를 반환하는지 검증합니다.
    (ET 기준 09:30 ~ 16:00, 동절기 한국 시간 UTC 14:30 ~ 21:00 / 서머타임 13:30 ~ 20:00)
    """
    # 2026-06-15 14:00:00 (UTC 기준), 서머타임 시 ET 10:00 (정규장)
    with freeze_time("2026-06-15 14:00:00"):
        session = get_market_session()
        assert session == MarketSession.REGULAR
