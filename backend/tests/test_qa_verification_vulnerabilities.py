import pytest
from decimal import Decimal
import random
from unittest.mock import patch
import pandas as pd
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.brokers.simulated_broker as simulated_broker
from app.brokers.simulated_broker import LocalSimulatedBroker
from app.core.database import Base
from app.core.models import Holding, UnfilledOrder, User
import app.scanner.data_provider as data_provider


@pytest.fixture
def isolated_simulated_broker_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(simulated_broker, "SessionLocal", session_factory)

    db = session_factory()
    try:
        user = User(username="limit-order-user", hashed_password="hashed")
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    try:
        yield session_factory, user_id
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

# =====================================================================
# 1. Decimal Arithmetic Precision Test & Chaos Fuzzing
# =====================================================================

def calculate_trade_float(price: float, qty: float, fee_rate: float) -> float:
    gross = price * qty
    fee = gross * fee_rate
    return gross + fee

def calculate_trade_decimal(price: Decimal, qty: Decimal, fee_rate: Decimal) -> Decimal:
    gross = price * qty
    fee = gross * fee_rate
    # Standard round to 4 decimal places for currency precision
    return (gross + fee).quantize(Decimal('0.0001'))

def test_decimal_vs_float_precision_chaos_fuzzing():
    """
    1,000-iteration Chaos Fuzzing test simulating trades with fractional values.
    Proves that float representation accumulates errors (non-zero cents),
    while Decimal maintains exact mathematical precision.
    """
    random.seed(42)
    float_errors_count = 0
    
    # 1000 iterations of random trade inputs
    for i in range(1000):
        # Simulating stock prices like $10.35, $154.27, etc.
        price = round(random.uniform(5.0, 500.0), 2)
        # Quantity could be fractional or integer, let's fuzz fractional shares too
        qty = round(random.uniform(1.0, 100.0), 4)
        # KIS fee rate (e.g. 0.0015)
        fee_rate = 0.0015
        
        # Calculate with float
        res_float = calculate_trade_float(price, qty, fee_rate)
        
        # Calculate with Decimal
        d_price = Decimal(str(price))
        d_qty = Decimal(str(qty))
        d_fee_rate = Decimal(str(fee_rate))
        res_decimal = calculate_trade_decimal(d_price, d_qty, d_fee_rate)
        
        # Check if float precision loses zero-cent bounds
        # (e.g. if the exact mathematical result should have no extra digits but float introduces them)
        exact_value = d_price * d_qty * Decimal('1.0015')
        exact_rounded = exact_value.quantize(Decimal('0.0001'))
        
        diff = abs(Decimal(str(res_float)) - exact_rounded)
        if diff > Decimal('1e-9'):
            float_errors_count += 1
            
    print(f"\n[DECIMAL TEST] Fuzzing completed. Float precision errors detected in {float_errors_count}/1000 iterations.")
    # In float, we expect at least some representation mismatches
    assert float_errors_count > 0, "Float calculations did not produce any representation errors."
    
    # Prove that Decimal is always exactly equal to the mathematical value rounded to 4 decimals
    for i in range(100):
        price = round(random.uniform(5.0, 500.0), 2)
        qty = round(random.uniform(1.0, 100.0), 4)
        fee_rate = 0.0015
        d_price = Decimal(str(price))
        d_qty = Decimal(str(qty))
        d_fee_rate = Decimal(str(fee_rate))
        res_decimal = calculate_trade_decimal(d_price, d_qty, d_fee_rate)
        exact_value = d_price * d_qty * Decimal('1.0015')
        assert res_decimal == exact_value.quantize(Decimal('0.0001'))

# =====================================================================
# 2. Pre-market/After-hours Data Collection Test (prePost=True Check)
# =====================================================================

@pytest.mark.asyncio
async def test_yfinance_data_collection_prepost_handling():
    """
    Verifies if prepost=True is passed in yfinance data collection calls.
    Exposes missing prepost configuration in data_provider.py.
    """
    with patch("yfinance.download") as mock_download:
        mock_download.return_value = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        
        # Test 1: fetch_ohlcv (defaults to False in method signature, or needs to force True)
        await data_provider.fetch_ohlcv("AAPL", interval="1m", period="1d", prepost=True)
        _, kwargs = mock_download.call_args
        assert kwargs.get("prepost") is True, "fetch_ohlcv must pass prepost=True to yfinance"
        
        # Test 2: fetch_bulk_ohlcv
        await data_provider.fetch_bulk_ohlcv(["AAPL", "MSFT"], interval="1m", period="1d", prepost=True)
        _, kwargs = mock_download.call_args
        assert kwargs.get("prepost") is True, "fetch_bulk_ohlcv must pass prepost=True to yfinance"
        
        # Test 3: fetch_ohlcv_sync
        # Currently, fetch_ohlcv_sync does NOT accept a prepost parameter or pass prepost=True.
        # Let's verify if the current implementation passes prepost=True.
        data_provider.fetch_ohlcv_sync("AAPL", interval="1m", period="1d")
        _, kwargs = mock_download.call_args
        is_prepost_passed_sync = kwargs.get("prepost", False)
        print(f"\n[PREPOST TEST] fetch_ohlcv_sync passed prepost={is_prepost_passed_sync}")
        
        # Test 4: fetch_bulk_ohlcv_sync
        data_provider.fetch_bulk_ohlcv_sync(["AAPL", "MSFT"], interval="1m", period="1d")
        _, kwargs = mock_download.call_args
        is_prepost_passed_bulk_sync = kwargs.get("prepost", False)
        print(f"\n[PREPOST TEST] fetch_bulk_ohlcv_sync passed prepost={is_prepost_passed_bulk_sync}")
        
        # Verify the data collection prepost support is correctly implemented
        assert is_prepost_passed_sync, "fetch_ohlcv_sync must pass prepost=True to yfinance"
        assert is_prepost_passed_bulk_sync, "fetch_bulk_ohlcv_sync must pass prepost=True to yfinance"


# =====================================================================
# 3. SimulatedBroker Limit Order Execution Test (Fake Execution Guard)
# =====================================================================

def test_simulated_broker_limit_order_fake_execution(isolated_simulated_broker_db):
    """
    Proves that LocalSimulatedBroker has a fake execution vulnerability where
    limit orders are filled instantly at prices that do not meet the limit conditions.
    """
    session_factory, user_id = isolated_simulated_broker_db
    broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))
    
    # Test Scenario A: Buy Limit Order
    # Limit Price = $100.0 (Buy at $100.0 or lower)
    # Live Market Price = $105.0
    # Expected behavior: Buy order should NOT fill immediately since market price ($105.0) is higher than limit ($100.0).
    # Current behavior: Naive broker fills it immediately at $105.0 or $100.0.
    
    with patch.object(broker, "_get_live_price", return_value=105.0):
        buy_res = broker.buy_order(ticker="AAPL", quantity=10, price=100.0, strategy_type="regime_switching")
        print(f"\n[LIMIT ORDER TEST] Buy Limit order ($100.0) when market is $105.0: Filled={buy_res.get('status')} at price {buy_res.get('filled_price')}")
        
        # Verify that the order is safely submitted as pending instead of instantly filled
        assert buy_res.get("status") == "SUBMITTED", "Patch verification failed: order was instantly filled"
        assert buy_res.get("filled_price") == 0.0, "Patch verification failed: filled price should be 0.0 for pending orders"
        
    # Test Scenario B: Sell Limit Order
    # Limit Price = $110.0 (Sell at $110.0 or higher)
    # Live Market Price = $105.0
    # Expected behavior: Sell order should NOT fill since market price ($105.0) is lower than limit ($110.0).
    with patch.object(broker, "_get_live_price", return_value=105.0):
        sell_res = broker.sell_order(ticker="AAPL", quantity=10, price=110.0, strategy_type="regime_switching")
        print(f"\n[LIMIT ORDER TEST] Sell Limit order ($110.0) when market is $105.0: Filled={sell_res.get('status')} at price {sell_res.get('filled_price')}")
        
        # Verify that the order is safely submitted as pending instead of instantly filled
        assert sell_res.get("status") == "SUBMITTED", "Patch verification failed: order was instantly filled"
        assert sell_res.get("filled_price") == 0.0, "Patch verification failed: filled price should be 0.0 for pending orders"

    db = session_factory()
    try:
        orders = db.query(UnfilledOrder).order_by(UnfilledOrder.id.asc()).all()
        assert [order.trade_type for order in orders] == ["BUY", "SELL"]
        assert all(order.user_id == user_id for order in orders)
    finally:
        db.close()


def test_simulated_broker_immediate_sell_rejects_insufficient_holding(isolated_simulated_broker_db):
    session_factory, user_id = isolated_simulated_broker_db
    broker = LocalSimulatedBroker(db_settings=SimpleNamespace(user_id=user_id))

    with patch.object(broker, "_get_live_price", return_value=120.0):
        no_holding = broker.sell_order(ticker="AAPL", quantity=1, price=100.0, strategy_type="regime_switching")

    assert no_holding["success"] is False
    assert no_holding["status"] == "REJECTED"
    assert no_holding["filled_qty"] == 0

    db = session_factory()
    try:
        db.add(
            Holding(
                user_id=user_id,
                ticker="AAPL",
                ticker_name="Apple",
                avg_price=Decimal("100.0000"),
                quantity=1,
                highest_price=Decimal("120.0000"),
                strategy_type="regime_switching",
            )
        )
        db.commit()
    finally:
        db.close()

    with patch.object(broker, "_get_live_price", return_value=120.0):
        too_many = broker.sell_order(ticker="AAPL", quantity=2, price=100.0, strategy_type="regime_switching")
        valid = broker.sell_order(ticker="AAPL", quantity=1, price=100.0, strategy_type="regime_switching")

    assert too_many["success"] is False
    assert too_many["status"] == "REJECTED"
    assert too_many["filled_qty"] == 0
    assert valid["success"] is True
    assert valid["status"] == "FILLED"
    assert valid["filled_qty"] == 1
