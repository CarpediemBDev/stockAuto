import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from app.core.config import settings


@dataclass(frozen=True)
class RealizedPnL:
    buy_gross: Decimal
    buy_fee: Decimal
    sell_gross: Decimal
    sell_fee: Decimal
    sec_fee: Decimal
    net_revenue: Decimal
    realized_pnl: Decimal
    return_rate: Decimal
    return_rate_on_cost: Decimal
    return_rate_on_gross: Decimal


def to_decimal(val) -> Decimal:
    """금융 연산 경계면에서 모든 float/int/None 값을 안전하게 Decimal로 변환합니다."""
    if val is None:
        return Decimal('0.0000')
    if isinstance(val, Decimal):
        return val
    # float의 지수 표기법 등을 감안해 문자열을 거쳐 변환합니다.
    return Decimal(str(val))


def fee_rate_for_trade_mode(trade_mode: str | None) -> Decimal:
    rate = (
        settings.SIMULATED_FEE_RATE
        if (trade_mode or "SIMULATED").upper() == "SIMULATED"
        else settings.KIS_FEE_RATE
    )
    return to_decimal(rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def calculate_buy_total(price: float | Decimal, quantity: int, fee_rate: float | Decimal) -> tuple[Decimal, Decimal, Decimal]:
    dec_price = to_decimal(price)
    dec_qty = to_decimal(quantity)
    dec_fee_rate = to_decimal(fee_rate)

    gross = (dec_price * dec_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    fee = (gross * dec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    total = (gross + fee).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return gross, fee, total


def calculate_realized_pnl(
    avg_price: float | Decimal,
    filled_price: float | Decimal,
    quantity: int,
    fee_rate: float | Decimal,
    sec_fee_rate: float | Decimal = settings.SEC_FEE_RATE,
) -> RealizedPnL:
    dec_avg_price = to_decimal(avg_price)
    dec_filled_price = to_decimal(filled_price)
    dec_qty = to_decimal(quantity)
    dec_fee_rate = to_decimal(fee_rate)
    dec_sec_fee_rate = to_decimal(sec_fee_rate)

    buy_gross = (dec_avg_price * dec_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    buy_fee = (buy_gross * dec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    sell_gross = (dec_filled_price * dec_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    sell_fee = (sell_gross * dec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    sec_fee = (sell_gross * dec_sec_fee_rate).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    net_revenue = (sell_gross - sell_fee - sec_fee).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    realized_pnl = (net_revenue - (buy_gross + buy_fee)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    buy_total_cost = (buy_gross + buy_fee).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    if buy_total_cost > 0:
        return_rate_on_cost = ((realized_pnl / buy_total_cost) * Decimal('100.0')).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    else:
        return_rate_on_cost = Decimal('0.0000')

    if buy_gross > 0:
        return_rate_on_gross = ((realized_pnl / buy_gross) * Decimal('100.0')).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    else:
        return_rate_on_gross = Decimal('0.0000')

    return RealizedPnL(
        buy_gross=buy_gross,
        buy_fee=buy_fee,
        sell_gross=sell_gross,
        sell_fee=sell_fee,
        sec_fee=sec_fee,
        net_revenue=net_revenue,
        realized_pnl=realized_pnl,
        return_rate=return_rate_on_cost,
        return_rate_on_cost=return_rate_on_cost,
        return_rate_on_gross=return_rate_on_gross,
    )


def calculate_avg_price(old_avg: float | Decimal | None, old_qty: int, filled_price: float | Decimal, delta_qty: int) -> Decimal:
    dec_old_avg = to_decimal(old_avg)
    dec_old_qty = to_decimal(old_qty)
    dec_filled_price = to_decimal(filled_price)
    dec_delta_qty = to_decimal(delta_qty)
    new_qty = dec_old_qty + dec_delta_qty
    if new_qty == 0:
        return Decimal('0.0000')
    new_avg = ((dec_old_avg * dec_old_qty) + (dec_filled_price * dec_delta_qty)) / new_qty
    return new_avg.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def calculate_profit_rate(current_price: float | Decimal, avg_price: float | Decimal) -> Decimal:
    dec_current_price = to_decimal(current_price)
    dec_avg_price = to_decimal(avg_price)
    if dec_avg_price == 0:
        return Decimal('0.0000')
    rate = ((dec_current_price - dec_avg_price) / dec_avg_price) * Decimal('100.0')
    return rate.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def check_stop_loss_breach(profit_rate: float | Decimal, stop_loss_pct: float | Decimal | None) -> bool:
    if stop_loss_pct is None:
        return False
    dec_stop_loss_pct = to_decimal(stop_loss_pct)
    if dec_stop_loss_pct <= 0:
        return False
    dec_profit_rate = to_decimal(profit_rate)
    return dec_profit_rate <= -dec_stop_loss_pct


def check_trailing_stop_breach(
    current_price: float | Decimal,
    highest_price: float | Decimal,
    trailing_stop_pct: float | Decimal | None,
    avg_price: float | Decimal
) -> bool:
    if trailing_stop_pct is None:
        return False
    dec_trailing_stop_pct = to_decimal(trailing_stop_pct)
    if dec_trailing_stop_pct <= 0:
        return False

    dec_current_price = to_decimal(current_price)
    dec_highest_price = to_decimal(highest_price)
    dec_avg_price = to_decimal(avg_price)

    threshold = dec_highest_price * (Decimal('1.0') - dec_trailing_stop_pct / Decimal('100.0'))
    return dec_current_price <= threshold and dec_highest_price > dec_avg_price


# 롤링 박스 트레일링 스탑의 박스 길이는 '봉 개수'가 아니라 '시간 길이(분)'로 정의한다.
# 봉 개수로 두면 같은 값이 라이브(15분봉)와 백테스트(전략 인터벌)에서 서로 다른
# 실시간 길이를 뜻하게 되어, 백테스트 검증 결과가 라이브로 전이되지 않는다.
DEFAULT_ROLLING_BOX_MINUTES = 150      # 2.5시간 (15분봉 10개 — 기존 라이브 동작과 동일)
# 라이브 스캐너가 공급할 수 있는 상한. 이보다 긴 박스를 전략이 선언해도 라이브에서
# 데이터가 모자라 조용히 미발동되는 것을 막기 위해 환산 단계에서 잘라낸다.
MAX_ROLLING_BOX_MINUTES = 480          # 8시간
MIN_ROLLING_BOX_BARS = 2               # 1봉 박스는 직전 봉 저점과 같아 의미가 없다
LIVE_BOX_BAR_MINUTES = 15              # 라이브 스캐너가 박스 계산에 쓰는 봉 주기

# 백테스트 인터벌별 봉 1개의 길이(분). 1d는 정규장 6.5시간을 기준으로 한다.
_INTERVAL_BAR_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": 390}


def bar_minutes_for_interval(interval: str) -> int:
    """백테스트 인터벌 문자열을 봉 1개의 길이(분)로 환산한다. 미지의 값은 60분으로 본다."""
    return _INTERVAL_BAR_MINUTES.get(interval, 60)


def resolve_rolling_box_bars(box_minutes: float, bar_minutes: int) -> int:
    """박스 길이(분)를 해당 타임프레임의 봉 개수로 환산한다.

    라이브와 백테스트가 같은 실시간 길이의 박스를 쓰도록 보장하는 단일 환산 지점이다.
    나눗셈이 딱 떨어지지 않으면 반올림(0.5는 올림)하며, 결과는 MIN_ROLLING_BOX_BARS
    이상으로 보정된다 — 예컨대 일봉에서는 2.5시간 박스를 표현할 수 없으므로 2봉이 된다.
    """
    if bar_minutes <= 0:
        raise ValueError("bar_minutes must be positive")
    minutes = min(max(float(box_minutes), 0.0), float(MAX_ROLLING_BOX_MINUTES))
    bars = int(math.floor(minutes / bar_minutes + 0.5))
    return max(MIN_ROLLING_BOX_BARS, bars)


def compute_box_low(recent_lows, bars: int) -> float | None:
    """완성 봉 저점 목록에서 최근 bars개의 최저값을 구한다. 순수 함수.

    봉이 bars개만큼 쌓이지 않았으면 None — 짧은 박스로 인한 조기 발동을 막는다.
    """
    if not recent_lows or bars <= 0:
        return None
    window = list(recent_lows)[-bars:]
    if len(window) < bars:
        return None
    try:
        numeric = [float(value) for value in window]
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(value) or value <= 0 for value in numeric):
        return None
    return min(numeric)


def compute_rolling_box_stop(
    prev_stop: float | Decimal | None,
    window_low: float | Decimal | None,
) -> Decimal:
    """롤링 박스 스탑 가격을 래칫(단조 증가) 조건으로 갱신합니다.

    새 스탑 = max(직전 스탑, 최근 N봉 저점). 윈도우 저점이 주가를 따라 내려가도
    스탑은 절대 후퇴하지 않는다 — 이 래칫이 없으면 하락 중 스탑이 주가를 쫓아
    내려가며 영원히 발동하지 않는 역주행이 발생한다(설계 핵심 불변식).
    """
    dec_prev = to_decimal(prev_stop)
    dec_window_low = to_decimal(window_low)
    return dec_prev if dec_prev >= dec_window_low else dec_window_low


def check_rolling_box_breach(
    current_price: float | Decimal,
    rolling_stop: float | Decimal | None,
    highest_price: float | Decimal,
    avg_price: float | Decimal,
) -> bool:
    """롤링 박스 스탑 이탈 여부를 판정합니다.

    ATR 트레일링과 동일하게 포지션이 한 번이라도 수익권(최고가 > 평단)에
    진입한 뒤에만 활성화된다 — 진입 직후 박스 하단이 평단 위에 있어
    즉시 청산되는 오발동을 차단하기 위함. 손실 방어는 기존 동적 손절선 담당.
    """
    dec_rolling_stop = to_decimal(rolling_stop)
    if dec_rolling_stop <= 0:
        return False
    dec_current_price = to_decimal(current_price)
    dec_highest_price = to_decimal(highest_price)
    dec_avg_price = to_decimal(avg_price)
    return dec_current_price < dec_rolling_stop and dec_highest_price > dec_avg_price
