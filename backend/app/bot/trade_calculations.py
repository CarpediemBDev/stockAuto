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
