"""스윙 예측 점수 캘리브레이션 기록 잡 (Score Calibration).

스윙 예측기는 매일 0~100점을 산출하지만, "85점 종목이 실제로 다음날 올랐는가"는
지금까지 아무도 검증하지 않았다. 본 모듈은 예측 점수와 익일 실제 등락을 짝지어
SwingScoreOutcome에 누적한다. 충분한 표본이 쌓이면 점수→실현 수익 매핑을 보정해
점수 인플레이션이나 예측력 없는 지표를 데이터로 적발할 수 있다.

설계 원칙:
- 매매에 관여하지 않는 순수 관측 레이어. 실패해도 트레이딩 경로에 영향이 없다.
- 멱등: (예측일, 티커) 유니크 제약 + 선조회로 재실행해도 중복 적재되지 않는다.
- 부분 실패 격리: 종목 단위로 예외를 삼키고 나머지를 계속 처리한다.
- 미해결 예측은 다음 실행에서 자동 재시도되며, MAX_BACKFILL_DAYS를 넘으면 포기한다
  (상장폐지·데이터 소실 종목이 영구 재시도로 잡을 갉아먹는 것을 방지).
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.bot.trade_calculations import to_decimal
from app.core import models
from app.core.logging import logger
from app.scanner.data_provider import fetch_ohlcv

# 예측일로부터 이 일수를 넘기면 관측을 포기한다 (데이터 소실·상장폐지 종목 무한 재시도 차단).
MAX_BACKFILL_DAYS = 10
# 한 번의 실행에서 처리할 최대 예측일 수 (잡 실행 시간 상한).
MAX_SNAPSHOT_DAYS_PER_RUN = 5
# 예측일당 관측할 최대 종목 수 (스윙 후보 상위 N개).
MAX_TICKERS_PER_DAY = 30


def _date_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def resolve_next_close(daily_bars, predicted_date: str) -> tuple[str, Decimal] | None:
    """일봉에서 예측일 '다음 거래일'의 종가를 찾는다. 순수 함수.

    주말·휴장일을 건너뛰기 위해 예측일보다 뒤에 오는 첫 완성 봉을 취한다.
    아직 다음 거래일 데이터가 없으면 None을 반환해 다음 실행에서 재시도하게 한다.
    """
    if daily_bars is None or len(daily_bars) == 0 or "Close" not in daily_bars.columns:
        return None
    for index_value, row in daily_bars.iterrows():
        bar_date = _date_key(index_value)
        if bar_date <= predicted_date:
            continue
        close_value = row["Close"]
        try:
            close_decimal = to_decimal(float(close_value))
        except (TypeError, ValueError):
            return None
        if close_decimal <= 0:
            return None
        return bar_date, close_decimal
    return None


def compute_return_pct(baseline_close: Decimal, observed_close: Decimal) -> Decimal:
    """익일 수익률(%)을 Decimal로 계산한다. 순수 함수."""
    if baseline_close <= 0:
        raise ValueError("baseline_close must be positive")
    return ((observed_close - baseline_close) / baseline_close) * Decimal("100")


def _pending_snapshots(db, now: datetime) -> list[tuple[str, list]]:
    """관측이 필요한 예측일별 후보 목록을 최신순으로 수집한다.

    같은 날 스냅샷이 여러 건이면 가장 이른 것(그날의 최초 예측)을 기준으로 삼는다.
    """
    oldest_allowed = now - timedelta(days=MAX_BACKFILL_DAYS)
    newest_allowed = now - timedelta(days=1)  # 예측 당일은 아직 익일 종가가 없다

    snapshots = (
        db.query(models.SwingPredictionSnapshot)
        .filter(
            models.SwingPredictionSnapshot.created_at >= oldest_allowed,
            models.SwingPredictionSnapshot.created_at <= newest_allowed,
        )
        .order_by(models.SwingPredictionSnapshot.created_at.asc())
        .all()
    )

    by_date: dict[str, list] = {}
    for snapshot in snapshots:
        if not snapshot.created_at:
            continue
        date_key = _date_key(snapshot.created_at)
        if date_key in by_date:
            continue  # 그날 최초 스냅샷만 사용
        try:
            candidates = json.loads(snapshot.candidates_json)
        except (TypeError, json.JSONDecodeError):
            logger.warning(f"[Calibration] snapshot {snapshot.id} has malformed candidates_json, skipping")
            continue
        if isinstance(candidates, list) and candidates:
            by_date[date_key] = candidates[:MAX_TICKERS_PER_DAY]

    ordered = sorted(by_date.items(), reverse=True)
    return ordered[:MAX_SNAPSHOT_DAYS_PER_RUN]


def _already_recorded(db, predicted_date: str) -> set[str]:
    rows = (
        db.query(models.SwingScoreOutcome.ticker)
        .filter(models.SwingScoreOutcome.predicted_date == predicted_date)
        .all()
    )
    return {row[0] for row in rows}


async def record_pending_outcomes(db, now: datetime | None = None) -> dict:
    """미관측 스윙 예측에 익일 실제 등락을 붙여 누적한다.

    반환: {"recorded": int, "skipped": int, "days": int}
    """
    now = now or datetime.now(timezone.utc)
    summary = {"recorded": 0, "skipped": 0, "days": 0}

    try:
        pending = _pending_snapshots(db, now)
    except Exception as e:
        logger.warning(f"[Calibration] failed to load pending snapshots, skipping run: {e}")
        return summary

    for predicted_date, candidates in pending:
        summary["days"] += 1
        recorded_tickers = _already_recorded(db, predicted_date)

        for candidate in candidates:
            if not isinstance(candidate, dict):
                summary["skipped"] += 1
                continue
            ticker = str(candidate.get("ticker") or "").upper().strip()
            if not ticker or ticker in recorded_tickers:
                summary["skipped"] += 1
                continue

            try:
                baseline_close = to_decimal(candidate.get("close"))
                if baseline_close <= 0:
                    summary["skipped"] += 1
                    continue

                daily_bars = await fetch_ohlcv(ticker, interval="1d", period="1mo")
                resolved = resolve_next_close(daily_bars, predicted_date)
                if resolved is None:
                    # 아직 익일 종가가 없거나 데이터 소실 — 다음 실행에서 재시도
                    summary["skipped"] += 1
                    continue

                observed_date, observed_close = resolved
                outcome = models.SwingScoreOutcome(
                    predicted_date=predicted_date,
                    ticker=ticker,
                    score=to_decimal(candidate.get("score")),
                    baseline_close=baseline_close,
                    observed_close=observed_close,
                    observed_date=observed_date,
                    return_pct=compute_return_pct(baseline_close, observed_close),
                )
                db.add(outcome)
                db.commit()
                recorded_tickers.add(ticker)
                summary["recorded"] += 1
            except IntegrityError:
                # 동시 실행 등으로 이미 적재됨 — 멱등 보장
                db.rollback()
                summary["skipped"] += 1
            except Exception as e:
                db.rollback()
                logger.warning(f"[Calibration] {ticker} @ {predicted_date} outcome failed, skipping: {e}")
                summary["skipped"] += 1

    if summary["recorded"]:
        logger.info(
            f"[Calibration] recorded {summary['recorded']} swing score outcomes "
            f"over {summary['days']} prediction day(s) (skipped {summary['skipped']})"
        )
    return summary


def swing_score_calibration_wrapper() -> None:
    """APScheduler 등록용 동기 래퍼.

    별도 이벤트 루프에서 실행해 메인 루프와 격리한다(scheduler의 다른 잡과 동일 패턴).
    관측 잡 실패가 트레이딩 사이클에 전파되지 않도록 예외를 전부 흡수한다.
    """
    import asyncio

    from app.core.database import SessionLocal

    async def _run():
        db = SessionLocal()
        try:
            await record_pending_outcomes(db)
        finally:
            db.close()

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.warning(f"[Calibration] scheduled run failed: {e}")


def summarize_calibration(db, bucket_size: int = 10) -> list[dict]:
    """누적된 관측을 점수 구간별로 집계한다 (승률·평균 수익률).

    점수가 높을수록 승률·평균 수익률이 단조 증가해야 정상이며, 그렇지 않다면
    해당 점수 구간이 예측력을 갖지 못한다는 뜻이다.
    """
    if bucket_size <= 0:
        raise ValueError("bucket_size must be positive")

    rows = db.query(models.SwingScoreOutcome.score, models.SwingScoreOutcome.return_pct).all()
    buckets: dict[int, list[Decimal]] = {}
    for score, return_pct in rows:
        bucket = int(Decimal(str(score)) // bucket_size) * bucket_size
        buckets.setdefault(bucket, []).append(Decimal(str(return_pct)))

    summary = []
    for bucket in sorted(buckets):
        returns = buckets[bucket]
        wins = sum(1 for r in returns if r > 0)
        summary.append(
            {
                "score_bucket": f"{bucket}-{bucket + bucket_size - 1}",
                "sample_count": len(returns),
                "win_rate": round(float(wins) / len(returns) * 100, 2),
                "avg_return_pct": round(float(sum(returns) / len(returns)), 4),
            }
        )
    return summary
