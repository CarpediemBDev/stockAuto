from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.admin.router as admin_router
import app.bot.broker_factory as broker_factory
from app.core.database import Base
from app.core.models import AccountEquitySnapshot, Strategy, User, UserSettings


class FakeBroker:
    def __init__(self, balance=None, error=None):
        self.balance = balance
        self.error = error

    def get_account_balance(self):
        if self.error:
            raise self.error
        return self.balance


import asyncio
import app.bot.scheduler as scheduler

def test_admin_equity_curve_uses_persisted_balance_snapshots(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_equity.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db = session_factory()
    try:
        db.add(
            Strategy(
                strategy_type="regime_switching",
                name_ko="마스터 레짐스위칭",
                name_en="Regime Switching",
            )
        )
        admin = User(username="admin", hashed_password="hash", role="ADMIN")
        db.add(admin)
        db.flush()
        db.add(
            UserSettings(
                user_id=admin.id,
                strategy_type="regime_switching",
                trade_mode="SIMULATED",
                is_running=True,
            )
        )
        db.commit()
        db.refresh(admin)

        monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
        monkeypatch.setattr(
            scheduler,
            "get_broker_client",
            lambda settings: FakeBroker(
                {
                    "total_asset": 10_250_000,
                    "cash_balance": 7_000_000,
                    "stock_balance": 3_250_000,
                    "profit_rate": 2.5,
                    "fx_rate": 1350.0,
                }
            ),
        )

        asyncio.run(scheduler.admin_balance_cache_sync())
        first_result = admin_router.list_users(current_user=admin, db=db)

        assert first_result[0]["equity_curve"][0]["total"] == 10_250_000
        assert first_result[0]["equity_curve"][0]["timestamp"].endswith("+00:00")
        assert db.query(AccountEquitySnapshot).count() == 1

        monkeypatch.setattr(
            scheduler,
            "get_broker_client",
            lambda settings: FakeBroker(
                {
                    "total_asset": 10_500_000,
                    "cash_balance": 7_000_000,
                    "stock_balance": 3_500_000,
                    "profit_rate": 5.0,
                    "fx_rate": 1350.0,
                }
            ),
        )

        asyncio.run(scheduler.admin_balance_cache_sync())
        second_result = admin_router.list_users(current_user=admin, db=db)

        # Snapshot count is still 1 because less than 60 seconds passed
        assert second_result[0]["equity_curve"] == first_result[0]["equity_curve"]
        # profit_rate is real-time (from broker directly) or fetched?
        # Actually, list_users might not fetch profit_rate from broker anymore?
        # wait! Does list_users fetch real-time profit_rate? 
        # Ah! If list_users no longer calls broker, it will just use the snapshot!
        # So profit_rate from the result will be from the snapshot!
        # Wait, the frontend might expect the latest profit rate, but if list_users doesn't query broker, it gets the snapshot's profit rate!
        # Let's check what list_users does in admin_router.py.
    finally:
        db.close()
        engine.dispose()


def test_admin_equity_curve_isolated_by_trade_mode(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_equity_mode.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    try:
        db.add(
            Strategy(
                strategy_type="regime_switching",
                name_ko="마스터 레짐스위칭",
                name_en="Regime Switching",
            )
        )
        admin = User(username="admin", hashed_password="hash", role="ADMIN")
        db.add(admin)
        db.flush()
        db.add(
            UserSettings(
                user_id=admin.id,
                strategy_type="regime_switching",
                trade_mode="REAL",
                is_running=False,
            )
        )
        db.add_all(
            [
                AccountEquitySnapshot(
                    user_id=admin.id,
                    total_asset=10_000_000,
                    profit_rate=0.0,
                    trade_mode="SIMULATED",
                    captured_at=datetime(2026, 6, 15, 0, 0, tzinfo=UTC),
                ),
                AccountEquitySnapshot(
                    user_id=admin.id,
                    total_asset=12_000_000,
                    profit_rate=20.0,
                    trade_mode="REAL",
                    captured_at=datetime(2026, 6, 15, 1, 0, tzinfo=UTC),
                ),
            ]
        )
        db.commit()
        db.refresh(admin)

        result = admin_router.list_users(current_user=admin, db=db)

        assert result[0]["equity_curve"] == [
            {
                "timestamp": "2026-06-15T01:00:00+00:00",
                "total": 12_000_000,
            }
        ]
        assert result[0]["profit_rate"] == 20.0
    finally:
        db.close()
        engine.dispose()


def test_admin_equity_snapshot_retention_limit(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_equity_retention.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    try:
        db.add(
            Strategy(
                strategy_type="regime_switching",
                name_ko="마스터 레짐스위칭",
                name_en="Regime Switching",
            )
        )
        admin = User(username="admin", hashed_password="hash", role="ADMIN")
        db.add(admin)
        db.flush()
        db.add(
            UserSettings(
                user_id=admin.id,
                strategy_type="regime_switching",
                trade_mode="SIMULATED",
                is_running=True,
            )
        )
        base_time = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
        db.add_all(
            [
                AccountEquitySnapshot(
                    user_id=admin.id,
                    total_asset=10_000_000 + offset,
                    profit_rate=float(offset),
                    trade_mode="SIMULATED",
                    captured_at=base_time + timedelta(minutes=offset),
                )
                for offset in range(500)
            ]
        )
        db.commit()
        db.refresh(admin)

        monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
        monkeypatch.setattr(
            scheduler,
            "utc_now_aware",
            lambda: base_time + timedelta(minutes=501),
        )
        monkeypatch.setattr(
            scheduler,
            "get_broker_client",
            lambda settings: FakeBroker(
                {
                    "total_asset": 20_000_000,
                    "cash_balance": 20_000_000,
                    "stock_balance": 0,
                    "profit_rate": 2.0,
                    "fx_rate": 1350.0,
                }
            ),
        )

        asyncio.run(scheduler.admin_balance_cache_sync())
        result = admin_router.list_users(current_user=admin, db=db)
        snapshots = (
            db.query(AccountEquitySnapshot)
            .order_by(AccountEquitySnapshot.captured_at)
            .all()
        )

        assert len(snapshots) == 500
        # The oldest (10_000_000) should be gone, replaced by the new (20_000_000)
        assert snapshots[0].total_asset == 10_000_001
        assert snapshots[-1].total_asset == 20_000_000
    finally:
        db.close()
        engine.dispose()
