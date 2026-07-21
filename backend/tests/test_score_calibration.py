"""스윙 예측 점수 캘리브레이션 기록 잡(score_calibration) 회귀 테스트.

핵심 불변식:
1. 다음 거래일 해석은 주말·휴장일을 건너뛰고, 예측일 이전/당일 봉은 절대 쓰지 않는다.
2. 익일 종가가 아직 없으면 기록하지 않고 다음 실행에 재시도한다(부분 적재 금지).
3. 재실행해도 (예측일, 티커) 중복 적재되지 않는다(멱등).
4. 종목 단위 실패는 격리되어 나머지 처리를 막지 않는다.
5. 수익률은 Decimal로 계산되어 부동소수점 오차가 없다.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import models
from app.core.database import Base
from app.scanner import score_calibration as calib


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _bars(dates, closes):
    return pd.DataFrame({"Close": closes, "Open": closes, "High": closes, "Low": closes},
                        index=pd.to_datetime(dates))


class TestResolveNextClose:
    def test_picks_first_bar_strictly_after_prediction_date(self):
        bars = _bars(["2026-07-20", "2026-07-21", "2026-07-22"], [100.0, 110.0, 120.0])
        assert calib.resolve_next_close(bars, "2026-07-20") == ("2026-07-21", Decimal("110.0"))

    def test_skips_weekend_gap(self):
        # 금요일 예측 → 다음 봉은 월요일
        bars = _bars(["2026-07-17", "2026-07-20"], [100.0, 105.0])
        assert calib.resolve_next_close(bars, "2026-07-17") == ("2026-07-20", Decimal("105.0"))

    def test_returns_none_when_next_session_not_available_yet(self):
        bars = _bars(["2026-07-20", "2026-07-21"], [100.0, 110.0])
        assert calib.resolve_next_close(bars, "2026-07-21") is None

    def test_never_uses_prediction_day_or_earlier_bar(self):
        bars = _bars(["2026-07-19", "2026-07-20"], [999.0, 888.0])
        assert calib.resolve_next_close(bars, "2026-07-20") is None

    def test_rejects_nonpositive_close(self):
        bars = _bars(["2026-07-20", "2026-07-21"], [100.0, 0.0])
        assert calib.resolve_next_close(bars, "2026-07-20") is None

    def test_handles_empty_and_malformed_input(self):
        assert calib.resolve_next_close(None, "2026-07-20") is None
        assert calib.resolve_next_close(pd.DataFrame(), "2026-07-20") is None


class TestComputeReturnPct:
    def test_gain_and_loss(self):
        assert calib.compute_return_pct(Decimal("100"), Decimal("110")) == Decimal("10")
        assert calib.compute_return_pct(Decimal("100"), Decimal("90")) == Decimal("-10")

    def test_decimal_precision_no_float_drift(self):
        # float이면 0.1+0.2 계열 오차가 나는 조합
        result = calib.compute_return_pct(Decimal("3"), Decimal("3.3"))
        assert result == Decimal("10")

    def test_zero_baseline_raises(self):
        with pytest.raises(ValueError):
            calib.compute_return_pct(Decimal("0"), Decimal("10"))


def _seed_snapshot(db, created_at, candidates):
    db.add(models.SwingPredictionSnapshot(
        cache_key="GLOBAL_SWING_POOL",
        ticker_universe=json.dumps([c["ticker"] for c in candidates]),
        candidates_json=json.dumps(candidates),
        sync_status="fresh",
        created_at=created_at,
    ))
    db.commit()


@pytest.mark.asyncio
class TestRecordPendingOutcomes:
    async def test_records_outcome_and_is_idempotent(self, db, monkeypatch):
        now = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
        _seed_snapshot(db, now - timedelta(days=1), [{"ticker": "AAA", "score": 85.0, "close": 100.0}])

        async def fake_fetch(ticker, interval="1d", period="1mo"):
            return _bars(["2026-07-21", "2026-07-22"], [100.0, 110.0])

        monkeypatch.setattr(calib, "fetch_ohlcv", fake_fetch)

        first = await calib.record_pending_outcomes(db, now=now)
        assert first["recorded"] == 1

        row = db.query(models.SwingScoreOutcome).one()
        assert row.ticker == "AAA"
        assert row.predicted_date == "2026-07-21"
        assert row.observed_date == "2026-07-22"
        assert Decimal(str(row.return_pct)) == Decimal("10")

        # 재실행해도 중복 적재되지 않는다
        second = await calib.record_pending_outcomes(db, now=now)
        assert second["recorded"] == 0
        assert db.query(models.SwingScoreOutcome).count() == 1

    async def test_skips_when_next_close_missing_and_retries_later(self, db, monkeypatch):
        now = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
        _seed_snapshot(db, now - timedelta(days=1), [{"ticker": "BBB", "score": 70.0, "close": 50.0}])

        async def no_next_session(ticker, interval="1d", period="1mo"):
            return _bars(["2026-07-21"], [50.0])

        monkeypatch.setattr(calib, "fetch_ohlcv", no_next_session)
        result = await calib.record_pending_outcomes(db, now=now)
        assert result["recorded"] == 0
        assert db.query(models.SwingScoreOutcome).count() == 0

        # 데이터가 도착하면 다음 실행에서 기록된다
        async def with_next_session(ticker, interval="1d", period="1mo"):
            return _bars(["2026-07-21", "2026-07-22"], [50.0, 55.0])

        monkeypatch.setattr(calib, "fetch_ohlcv", with_next_session)
        result = await calib.record_pending_outcomes(db, now=now)
        assert result["recorded"] == 1

    async def test_per_ticker_failure_is_isolated(self, db, monkeypatch):
        now = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
        _seed_snapshot(db, now - timedelta(days=1), [
            {"ticker": "BAD", "score": 90.0, "close": 100.0},
            {"ticker": "GOOD", "score": 80.0, "close": 100.0},
        ])

        async def flaky(ticker, interval="1d", period="1mo"):
            if ticker == "BAD":
                raise RuntimeError("delisted")
            return _bars(["2026-07-21", "2026-07-22"], [100.0, 120.0])

        monkeypatch.setattr(calib, "fetch_ohlcv", flaky)
        result = await calib.record_pending_outcomes(db, now=now)
        assert result["recorded"] == 1
        assert db.query(models.SwingScoreOutcome).one().ticker == "GOOD"

    async def test_ignores_same_day_prediction(self, db, monkeypatch):
        now = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
        _seed_snapshot(db, now, [{"ticker": "AAA", "score": 85.0, "close": 100.0}])

        async def fake_fetch(ticker, interval="1d", period="1mo"):
            raise AssertionError("당일 예측은 조회 대상이 아니어야 한다")

        monkeypatch.setattr(calib, "fetch_ohlcv", fake_fetch)
        result = await calib.record_pending_outcomes(db, now=now)
        assert result == {"recorded": 0, "skipped": 0, "days": 0}

    async def test_ignores_predictions_older_than_backfill_window(self, db, monkeypatch):
        now = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
        _seed_snapshot(db, now - timedelta(days=calib.MAX_BACKFILL_DAYS + 2),
                       [{"ticker": "OLD", "score": 85.0, "close": 100.0}])

        async def fake_fetch(ticker, interval="1d", period="1mo"):
            raise AssertionError("백필 윈도우를 벗어난 예측은 조회하지 않아야 한다")

        monkeypatch.setattr(calib, "fetch_ohlcv", fake_fetch)
        result = await calib.record_pending_outcomes(db, now=now)
        assert result["days"] == 0

    async def test_skips_nonpositive_baseline_close(self, db, monkeypatch):
        now = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
        _seed_snapshot(db, now - timedelta(days=1), [{"ticker": "ZERO", "score": 85.0, "close": 0.0}])

        async def fake_fetch(ticker, interval="1d", period="1mo"):
            raise AssertionError("기준가가 0이면 조회 전에 걸러야 한다")

        monkeypatch.setattr(calib, "fetch_ohlcv", fake_fetch)
        result = await calib.record_pending_outcomes(db, now=now)
        assert result["recorded"] == 0

    async def test_malformed_snapshot_json_does_not_crash(self, db, monkeypatch):
        now = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
        db.add(models.SwingPredictionSnapshot(
            cache_key="GLOBAL_SWING_POOL",
            ticker_universe="[]",
            candidates_json="{not json",
            sync_status="fresh",
            created_at=now - timedelta(days=1),
        ))
        db.commit()
        result = await calib.record_pending_outcomes(db, now=now)
        assert result["days"] == 0


class TestSummarizeCalibration:
    def _add(self, db, score, return_pct):
        db.add(models.SwingScoreOutcome(
            predicted_date=f"2026-07-{10 + int(score) % 10:02d}",
            ticker=f"T{score}{return_pct}",
            score=Decimal(str(score)),
            baseline_close=Decimal("100"),
            observed_close=Decimal("100") + Decimal(str(return_pct)),
            observed_date="2026-07-22",
            return_pct=Decimal(str(return_pct)),
        ))

    def test_buckets_by_score_with_win_rate(self, db):
        self._add(db, 85, 5)
        self._add(db, 88, -1)
        self._add(db, 62, 2)
        db.commit()

        summary = calib.summarize_calibration(db, bucket_size=10)
        by_bucket = {row["score_bucket"]: row for row in summary}
        assert by_bucket["80-89"]["sample_count"] == 2
        assert by_bucket["80-89"]["win_rate"] == 50.0
        assert by_bucket["80-89"]["avg_return_pct"] == 2.0
        assert by_bucket["60-69"]["win_rate"] == 100.0

    def test_empty_dataset_returns_empty(self, db):
        assert calib.summarize_calibration(db) == []

    def test_invalid_bucket_size_raises(self, db):
        with pytest.raises(ValueError):
            calib.summarize_calibration(db, bucket_size=0)
