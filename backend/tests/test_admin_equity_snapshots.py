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
        assert db.query(AccountEquitySnapshot).count() == 1

        monkeypatch.setattr(
            broker_factory,
            "get_broker_client",
            lambda settings: FakeBroker(error=RuntimeError("balance unavailable")),
        )

        second_result = admin_router.list_users(current_user=admin, db=db)

        assert second_result[0]["equity_curve"] == first_result[0]["equity_curve"]
        assert second_result[0]["profit_rate"] == 2.5
        assert db.query(AccountEquitySnapshot).count() == 1
    finally:
        db.close()
        engine.dispose()
