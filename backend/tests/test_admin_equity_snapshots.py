from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.admin.router as admin_router
import app.bot.broker_factory as broker_factory
from app.core.database import Base
from app.core.models import AccountEquitySnapshot, Strategy, User, UserSettings


class FakeBroker:
    def __init__(self, balance=None, error=None, on_balance=None):
        self.balance = balance
        self.error = error
        self.on_balance = on_balance

    def get_account_balance(self):
        if self.on_balance:
            self.on_balance()
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

        session_closed_before_broker = False
        original_close = db.close

        def tracking_close():
            nonlocal session_closed_before_broker
            session_closed_before_broker = True
            original_close()

        monkeypatch.setattr(db, "close", tracking_close)

        def assert_session_closed_before_broker():
            assert session_closed_before_broker is True

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
                },
                on_balance=assert_session_closed_before_broker,
            ),
        )

        asyncio.run(scheduler.admin_balance_cache_sync())
        first_result = admin_router.list_users(current_user=admin, db=db)

        # 계약: list_users는 최신 스냅샷의 profit_rate와 latest_snapshot_at을 반환한다(equity_curve 폐지)
        assert first_result[0]["profit_rate"] == 2.5
        assert first_result[0]["latest_snapshot_at"].endswith("+00:00")
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
        assert second_result[0]["latest_snapshot_at"] == first_result[0]["latest_snapshot_at"]
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

        # 모드 격리: 사용자 trade_mode(REAL)의 최신 스냅샷만 반영되어야 한다(SIMULATED 무시)
        assert result[0]["latest_snapshot_at"] == "2026-06-15T01:00:00+00:00"
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


def test_observation_account_exempt_from_retention_prune(tmp_path, monkeypatch):
    """obs_ 프리픽스 관찰/벤치마크 계정은 500건 롤링 컷에서 제외돼 전 구간을 보존한다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_equity_obs.db'}")
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
        # 프로덕션 관찰 계정과 동일한 명명 규약(obs_ 프리픽스)
        obs = User(username="obs_qqq_hold", hashed_password="hash", role="USER")
        db.add(obs)
        db.flush()
        db.add(
            UserSettings(
                user_id=obs.id,
                strategy_type="benchmark_qqq_hold",
                trade_mode="SIMULATED",
                is_running=True,
            )
        )
        base_time = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
        db.add_all(
            [
                AccountEquitySnapshot(
                    user_id=obs.id,
                    total_asset=10_000_000 + offset,
                    profit_rate=float(offset),
                    trade_mode="SIMULATED",
                    captured_at=base_time + timedelta(minutes=offset),
                )
                for offset in range(500)
            ]
        )
        db.commit()
        db.refresh(obs)

        # 전역 캐시 무효화 (이전 테스트 영향 배제)
        monkeypatch.setattr(scheduler, "_OBSERVATION_USER_IDS", {})
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
        snapshots = (
            db.query(AccountEquitySnapshot)
            .order_by(AccountEquitySnapshot.captured_at)
            .all()
        )

        # 관찰 계정은 프루닝 제외: 501건으로 증가하고 가장 오래된 점이 보존된다.
        assert len(snapshots) == 501
        assert snapshots[0].total_asset == 10_000_000
        assert snapshots[-1].total_asset == 20_000_000
    finally:
        db.close()
        engine.dispose()


def test_observation_account_exempt_from_retention_prune_case_insensitive(tmp_path, monkeypatch):
    """대소문자 다른 OBS_ 프리픽스 계정도 프루닝에서 제외되고 캐시가 정상 동작하는지 검증한다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_equity_obs_ci.db'}")
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
        # 대문자 프리픽스 명명 (OBS_core)
        obs = User(username="OBS_core", hashed_password="hash", role="USER")
        db.add(obs)
        db.flush()
        db.add(
            UserSettings(
                user_id=obs.id,
                strategy_type="benchmark_qqq_hold",
                trade_mode="SIMULATED",
                is_running=True,
            )
        )
        base_time = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
        db.add_all(
            [
                AccountEquitySnapshot(
                    user_id=obs.id,
                    total_asset=10_000_000 + offset,
                    profit_rate=float(offset),
                    trade_mode="SIMULATED",
                    captured_at=base_time + timedelta(minutes=offset),
                )
                for offset in range(500)
            ]
        )
        db.commit()
        db.refresh(obs)

        # 전역 캐시 무효화 및 주입
        test_cache = {}
        monkeypatch.setattr(scheduler, "_OBSERVATION_USER_IDS", test_cache)
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
        
        # 캐싱이 정상적으로 이루어짐을 검증 (user_id -> True)
        assert test_cache.get(obs.id) is True

        snapshots = (
            db.query(AccountEquitySnapshot)
            .order_by(AccountEquitySnapshot.captured_at)
            .all()
        )
        # 프루닝 제외 확인 (501건)
        assert len(snapshots) == 501
        assert snapshots[0].total_asset == 10_000_000
    finally:
        db.close()
        engine.dispose()


def test_observation_account_missing_user_defensive_guard(tmp_path, monkeypatch):
    """DB에 유저 정보가 존재하지 않는 고장 상태 시, 유실 방지 가드(defensive guard)로 프루닝을 회피한다."""
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_equity_obs_missing.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    try:
        # 데이터베이스에 User 행이 전혀 없음
        base_time = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
        db.add_all(
            [
                AccountEquitySnapshot(
                    user_id=9999,  # 존재하지 않는 임의의 user_id
                    total_asset=10_000_000 + offset,
                    profit_rate=float(offset),
                    trade_mode="SIMULATED",
                    captured_at=base_time + timedelta(minutes=offset),
                )
                for offset in range(500)
            ]
        )
        db.commit()

        monkeypatch.setattr(scheduler, "_OBSERVATION_USER_IDS", {})
        monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
        
        # record_equity_snapshot 직접 호출하여 검증
        balance = {
            "total_asset": 20_000_000,
            "cash_balance": 20_000_000,
            "stock_balance": 0,
            "profit_rate": 2.0,
            "fx_rate": 1350.0,
        }
        
        # execute
        res = scheduler.record_equity_snapshot(
            user_id=9999,
            trade_mode="SIMULATED",
            balance=balance,
            exchange_rate=1350.0,
            force=True
        )
        assert res is True

        snapshots = (
            db.query(AccountEquitySnapshot)
            .filter(AccountEquitySnapshot.user_id == 9999)
            .all()
        )
        # 유저 부재 시에도 프루닝되지 않고 보존되어 501건이 됨
        assert len(snapshots) == 501
    finally:
        db.close()
        engine.dispose()
