"""에쿼티 커브 게이트 (Rolling Equity-Curve Gate).

(전략 슬롯 × 레짐)별 최근 청산 완료 트레이드의 롤링 윈도우 프로핏 팩터로
신규 매수 배분 계수를 산출한다. 가격 신호가 아니라 "이 전략이 지금 시장에서
실제로 먹히고 있는가"를 묻는 메타 리스크 레이어이며, 목표는 알파 창출이 아니라
손실 국면 노출 축소다.

설계 원칙:
- DB 읽기 전용. 스키마·매매 판정 로직을 건드리지 않는다.
- 콜드 스타트(표본 부족)와 내부 오류는 전부 계수 1.0(무개입)으로 폴백한다 —
  게이트는 부가 안전장치이지 매매 차단기가 아니다.
- 시차 오류 방지: 레짐별 분리 집계 + 최근 MAX_AGE_DAYS 이내 트레이드만 사용
  (스로틀 상태에서 거래 빈도가 줄어 낡은 성적에 고착되는 자기 강화 차단).
- 금융 수치 합산은 Decimal로 수행하고 비교 판정 직전에만 부동소수점화한다.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core import models
from app.core.logging import logger

# 롤링 윈도우 구성
WINDOW_TRADES = 20     # 최근 청산 트레이드 최대 표본 수
MIN_TRADES = 8         # 이 미만이면 콜드 스타트 — 판단 유보(계수 1.0)
MAX_AGE_DAYS = 30      # 시간 감쇠: 이보다 오래된 트레이드는 윈도우에서 제외

# 프로핏 팩터 → 배분 계수 매핑
PF_HEALTHY = Decimal("1.2")    # 이상이면 정상 배분
PF_MARGINAL = Decimal("1.0")   # 이상이면 경계 구간
FACTOR_HEALTHY = 1.0
FACTOR_MARGINAL = 0.6
FACTOR_UNHEALTHY = 0.3


def compute_gate_factor(realized_pnls: list[Decimal]) -> tuple[float, dict]:
    """실현 손익 목록(최신순 윈도우)에서 배분 계수와 진단 정보를 계산한다. 순수 함수."""
    sample_count = len(realized_pnls)
    diagnostics = {
        "sample_count": sample_count,
        "profit_factor": None,
        "reason": "",
    }

    if sample_count < MIN_TRADES:
        diagnostics["reason"] = f"cold_start (<{MIN_TRADES} trades)"
        return FACTOR_HEALTHY, diagnostics

    gross_profit = sum((p for p in realized_pnls if p > 0), Decimal("0"))
    gross_loss = -sum((p for p in realized_pnls if p < 0), Decimal("0"))

    if gross_loss == 0:
        # 무손실 윈도우 — PF 분모 0 특이점. 스로틀할 이유가 없으므로 정상 배분.
        diagnostics["reason"] = "no_loss_window"
        diagnostics["profit_factor"] = float("inf") if gross_profit > 0 else None
        return FACTOR_HEALTHY, diagnostics

    profit_factor = gross_profit / gross_loss
    diagnostics["profit_factor"] = float(profit_factor)

    if profit_factor >= PF_HEALTHY:
        diagnostics["reason"] = "healthy"
        return FACTOR_HEALTHY, diagnostics
    if profit_factor >= PF_MARGINAL:
        diagnostics["reason"] = "marginal"
        return FACTOR_MARGINAL, diagnostics
    diagnostics["reason"] = "unhealthy"
    return FACTOR_UNHEALTHY, diagnostics


def get_equity_gate_factor(db, user_id: int, strategy_type: str, regime: str) -> tuple[float, dict]:
    """(슬롯 × 레짐)의 최근 청산 기록을 읽어 배분 계수를 반환한다.

    조회·계산 중 어떤 오류가 나도 게이트는 무개입(1.0)으로 폴백한다.
    """
    try:
        age_cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
        rows = (
            db.query(models.TradeLog.realized_pnl)
            .filter(
                models.TradeLog.user_id == user_id,
                models.TradeLog.strategy_type == strategy_type,
                models.TradeLog.trade_type == "SELL",
                models.TradeLog.regime_mode == regime,
                models.TradeLog.realized_pnl.isnot(None),
                models.TradeLog.executed_at >= age_cutoff,
            )
            .order_by(models.TradeLog.executed_at.desc())
            .limit(WINDOW_TRADES)
            .all()
        )
        pnls = [Decimal(str(row[0])) for row in rows]
        return compute_gate_factor(pnls)
    except Exception as e:
        logger.warning(f"[Equity Gate] factor lookup failed for user={user_id} slot={strategy_type} regime={regime}, fail-open to 1.0: {e}")
        return FACTOR_HEALTHY, {"sample_count": 0, "profit_factor": None, "reason": f"error: {e}"}
