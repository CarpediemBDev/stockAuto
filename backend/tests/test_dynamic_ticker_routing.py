import pytest
from types import SimpleNamespace
from app.bot.scheduler import build_target_signals

class MockMSManager:
    def get_focused_tickers(self, all_signals):
        # Always return the exact tickers passed from the scanner, simulating 100% dynamic behavior
        return [sig['ticker'] for sig in all_signals]

class MockContext:
    def __init__(self, all_signals):
        self.all_signals = all_signals
        self.signal_map = {sig['ticker']: sig for sig in all_signals}
        self.ms_manager = MockMSManager()
        self.holdings = []
        self.session = "REGULAR_MARKET"
        self.user_id = 1
        self.db = None

@pytest.mark.asyncio
async def test_build_target_signals_is_completely_dynamic():
    """
    [방어 테스트] 스케줄러가 매수 후보를 고를 때, 특정 티커에 얽매이지 않고
    스캐너가 넘겨준 동적 종목을 100% 그대로 채택하는지 검증합니다.
    만약 누군가 코드를 수정해서 하드코딩된 특정 종목만 찾게 만든다면 이 테스트는 무조건 실패합니다.
    """
    
    # 가상의 스캐너가 발굴한 생소한 주식 3개
    fake_signals = [
        {"ticker": "DUMMY1", "price": 10},
        {"ticker": "DUMMY2", "price": 20},
        {"ticker": "UNKNOWN3", "price": 30}
    ]
    
    ctx = MockContext(all_signals=fake_signals)
    
    target_signals = await build_target_signals(ctx)
    
    assert target_signals is not None, "target_signals should not be None"
    assert len(target_signals) == 3, "Should dynamically pick all 3 valid signals"
    
    extracted_tickers = [sig['ticker'] for sig in target_signals]
    assert "DUMMY1" in extracted_tickers
    assert "DUMMY2" in extracted_tickers
    assert "UNKNOWN3" in extracted_tickers
