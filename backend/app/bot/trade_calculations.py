from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class RealizedPnL:
    buy_gross: float
    buy_fee: float
    sell_gross: float
    sell_fee: float
    sec_fee: float
    net_revenue: float
    realized_pnl: float
    return_rate: float


def fee_rate_for_trade_mode(trade_mode: str | None) -> float:
    return (
        settings.SIMULATED_FEE_RATE
        if (trade_mode or "SIMULATED").upper() == "SIMULATED"
        else settings.KIS_FEE_RATE
    )


def calculate_buy_total(price: float, quantity: int, fee_rate: float) -> tuple[float, float, float]:
    gross = price * quantity
    fee = gross * fee_rate
    return gross, fee, gross + fee


def calculate_realized_pnl(
    avg_price: float,
    filled_price: float,
    quantity: int,
    fee_rate: float,
    sec_fee_rate: float = settings.SEC_FEE_RATE,
) -> RealizedPnL:
    buy_gross = avg_price * quantity
    buy_fee = buy_gross * fee_rate
    sell_gross = filled_price * quantity
    sell_fee = sell_gross * fee_rate
    sec_fee = sell_gross * sec_fee_rate
    net_revenue = sell_gross - sell_fee - sec_fee
    realized_pnl = net_revenue - (buy_gross + buy_fee)
    return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0
    return RealizedPnL(
        buy_gross=buy_gross,
        buy_fee=buy_fee,
        sell_gross=sell_gross,
        sell_fee=sell_fee,
        sec_fee=sec_fee,
        net_revenue=net_revenue,
        realized_pnl=realized_pnl,
        return_rate=return_rate,
    )
