from app.strategies.strategy_c import StrategyC

class StrategyB(StrategyC):
    """
    🟠 전략 B (채점 분리 과도기)
    - 40% 기본 비중 할당 (최소 $2,000 보장)
    - 오리지널 +3% / +6% 피라미딩 불타기 적용
    - 스마트 익절 최소 마진 1.0% 적용 (전략 C보다 좁은 이익 실현)
    - Strategy C와 동일한 11대 기술지표 종합 가감점 스코어카드 및 소프트 감점 공유
    """
    
    def __init__(self):
        super().__init__(name="🟠 전략 B (채점 분리 + 40% 비중 + 1% 익절)")
        self.min_smart_exit_profit = 1.0  # 1.0% 조기 익절 마진

    def get_pyramid_trigger(self, stage: int) -> float:
        if stage == 1:
            return 3.0   # +3%에서 2단계 추가 진입
        elif stage == 2:
            return 6.0   # +6%에서 3단계 추가 진입
        return 999.0
