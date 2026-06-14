from types import SimpleNamespace

import pytest

from app.bot.multi_strategy_manager import MultiStrategyManager


@pytest.mark.parametrize("session", ["PRE_MARKET", "AFTER_HOURS"])
def test_extended_sessions_reduce_new_entry_budget_by_half(session):
    manager = MultiStrategyManager("multi_slot")

    regular = manager.calculate_slots_allocation(
        total_asset_usd=10000.0,
        cash_balance_usd=10000.0,
        holdings=[],
        session="REGULAR_MARKET",
    )
    extended = manager.calculate_slots_allocation(
        total_asset_usd=10000.0,
        cash_balance_usd=10000.0,
        holdings=[],
        session=session,
    )

    for slot_key in manager.SLOTS:
        assert extended[slot_key]["cash_balance"] == pytest.approx(
            regular[slot_key]["cash_balance"] * 0.5
        )


def test_extended_session_penalty_does_not_change_existing_stock_value():
    manager = MultiStrategyManager("regime_switching")
    holdings = [
        SimpleNamespace(
            quantity=2,
            current_price=100.0,
            highest_price=100.0,
            avg_price=90.0,
            strategy_type="regime_switching",
        )
    ]

    allocation = manager.calculate_slots_allocation(
        total_asset_usd=1000.0,
        cash_balance_usd=800.0,
        holdings=holdings,
        session="PRE_MARKET",
    )

    assert allocation["regime_switching"]["stock_value"] == pytest.approx(200.0)
    assert allocation["regime_switching"]["cash_balance"] == pytest.approx(400.0)
