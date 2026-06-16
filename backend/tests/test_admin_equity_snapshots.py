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

        monkeypatch.setattr(
            broker_factory,
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

        first_result = admin_router.list_users(current_user=admin, db=db)

        assert first_result[0]["equity_curve"][0]["total"] == 10_250_000
        assert first_result[0]["equity_curve"][0]["timestamp"].endswith("+00:00")
        assert db.query(AccountEquitySnapshot).count() == 1

        monkeypatch.setattr(
            broker_factory,
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

        second_result = admin_router.list_users(current_user=admin, db=db)

        assert second_result[0]["equity_curve"] == first_result[0]["equity_curve"]
        assert second_result[0]["profit_rate"] == 5.0
        assert db.query(AccountEquitySnapshot).count() == 1

        monkeypatch.setattr(
            broker_factory,
            "get_broker_client",
            lambda settings: FakeBroker(error=RuntimeError("balance unavailable")),
        )

        third_result = admin_router.list_users(current_user=admin, db=db)

        assert third_result[0]["equity_curve"] == first_result[0]["equity_curve"]
        assert third_result[0]["profit_rate"] == 2.5
        assert db.query(AccountEquitySnapshot).count() == 1
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
                for offset in range(2)
            ]
        )
        db.commit()
        db.refresh(admin)

        monkeypatch.setattr(admin_router, "EQUITY_SNAPSHOT_RETENTION_LIMIT", 2)
        monkeypatch.setattr(
            admin_router,
            "utc_now_aware",
            lambda: base_time + timedelta(minutes=2),
        )
        monkeypatch.setattr(
            broker_factory,
            "get_broker_client",
            lambda settings: FakeBroker(
                {
                    "total_asset": 10_000_002,
                    "cash_balance": 10_000_002,
                    "stock_balance": 0,
                    "profit_rate": 2.0,
                    "fx_rate": 1350.0,
                }
            ),
        )

        result = admin_router.list_users(current_user=admin, db=db)
        snapshots = (
            db.query(AccountEquitySnapshot)
            .order_by(AccountEquitySnapshot.captured_at)
            .all()
        )

        assert len(snapshots) == 2
        assert [snapshot.total_asset for snapshot in snapshots] == [
            10_000_001,
            10_000_002,
        ]
        assert [point["total"] for point in result[0]["equity_curve"]] == [
            10_000_001,
            10_000_002,
        ]
    finally:
        db.close()
        engine.dispose()
