import asyncio
import math
import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.bot.us_market_calendar import nyse_regular_close
from app.core.logging import logger
from app.scanner.data_provider import fetch_bulk_ohlcv, fetch_ticker_news
from app.scanner.discovery import get_seed_tickers
from app.scanner.filters import CATALYST_KEYWORDS
from app.scanner.indicators import calculate_vwap
from app.translations.translator import Translator


ET = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
AFTER_HOURS_CLOSE = time(20, 0)
DEFAULT_SCAN_LIMIT = 80
NEWS_ENRICH_LIMIT = 12
AFTER_HOURS_REFRESH_COOLDOWN_SECONDS = 60

AFTER_HOURS_SYNC_EMPTY = "empty"
AFTER_HOURS_SYNC_FAILED = "failed"
AFTER_HOURS_SYNC_FRESH = "fresh"
AFTER_HOURS_SYNC_REFRESHING = "refreshing"
AFTER_HOURS_SYNC_STALE = "stale"

_cache_lock = threading.RLock()
_refresh_lock = threading.Lock()
_refresh_in_progress = False
_after_hours_cache = {
    "candidates": [],
    "scope": "global",
    "sync_status": AFTER_HOURS_SYNC_EMPTY,
    "updated_at": None,
    "universe_size": 0,
}


def _pct(new_value: float, old_value: float) -> float:
    if old_value <= 0:
        return 0.0
    return (new_value / old_value - 1.0) * 100.0


def _finite(value: float, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _round(value: float, digits: int = 2) -> float:
    return round(_finite(value), digits)


def _parse_updated_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_frame_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    normalized = df.copy()
    index = pd.to_datetime(normalized.index)
    if index.tz is None:
        index = index.tz_localize(ET)
    else:
        index = index.tz_convert(ET)
    normalized.index = index
    return normalized.sort_index()


def _extract_ticker_frame(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    frame = pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        level0 = data.columns.get_level_values(0)
        level1 = data.columns.get_level_values(1)
        if ticker in level0:
            frame = data[ticker].copy()
        elif ticker in level1:
            frame = data.xs(ticker, level=1, axis=1).copy()
    else:
        frame = data.copy()

    if frame.empty:
        return pd.DataFrame()

    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(-1)
    frame = frame.loc[:, ~frame.columns.duplicated()]

    required_columns = {"Open", "High", "Low", "Close", "Volume"}
    if not required_columns.issubset(set(frame.columns)):
        return pd.DataFrame()

    cleaned = frame[list(required_columns)].dropna()
    return _normalize_frame_index(cleaned)


def _latest_extended_session(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if df.empty:
        return None

    market_dates = sorted({idx.date() for idx in df.index}, reverse=True)
    for market_date in market_dates:
        regular_close = nyse_regular_close(market_date)
        if regular_close is None:
            continue

        day_df = df[df.index.date == market_date]
        regular = day_df[
            (day_df.index.time >= REGULAR_OPEN)
            & (day_df.index.time < regular_close)
        ]
        after_hours = day_df[
            (day_df.index.time >= regular_close)
            & (day_df.index.time < AFTER_HOURS_CLOSE)
        ]
        if len(regular) >= 30 and len(after_hours) >= 2:
            return regular, after_hours
    return None


def _session_volume_ratio(current_regular: pd.DataFrame, historical_df: pd.DataFrame) -> float:
    regular_volume = float(current_regular["Volume"].sum())
    historical_volumes = []
    current_date = current_regular.index[-1].date()

    for market_date in sorted({idx.date() for idx in historical_df.index}):
        if market_date == current_date:
            continue
        regular_close = nyse_regular_close(market_date)
        if regular_close is None:
            continue
        day_df = historical_df[historical_df.index.date == market_date]
        regular = day_df[
            (day_df.index.time >= REGULAR_OPEN)
            & (day_df.index.time < regular_close)
        ]
        if len(regular) >= 30:
            historical_volumes.append(float(regular["Volume"].sum()))

    if not historical_volumes:
        return 1.0
    avg_volume = sum(historical_volumes) / len(historical_volumes)
    if avg_volume <= 0:
        return 1.0
    return regular_volume / avg_volume


def _build_candidate(ticker: str, source: list[str], df: pd.DataFrame) -> dict | None:
    session = _latest_extended_session(df)
    if session is None:
        return None

    regular, after_hours = session
    regular_close_time = regular.index[-1]
    regular_open = _finite(regular["Open"].iloc[0])
    regular_close = _finite(regular["Close"].iloc[-1])
    regular_high = _finite(regular["High"].max())
    regular_low = _finite(regular["Low"].min())
    regular_volume = _finite(regular["Volume"].sum())
    after_price = _finite(after_hours["Close"].iloc[-1])
    after_volume = _finite(after_hours["Volume"].sum())

    if regular_open <= 0 or regular_close <= 0 or after_price <= 0:
        return None

    final_hour_start = regular_close_time - timedelta(hours=1)
    final_hour = regular[regular.index >= final_hour_start]
    final_hour_reference = _finite(final_hour["Close"].iloc[0]) if not final_hour.empty else regular_open

    vwap = calculate_vwap(regular)
    vwap_last = _finite(vwap.iloc[-1]) if not vwap.empty else regular_close
    close_range = regular_high - regular_low
    close_position_pct = ((regular_close - regular_low) / close_range * 100.0) if close_range > 0 else 50.0

    regular_change_pct = _pct(regular_close, regular_open)
    final_hour_return_pct = _pct(regular_close, final_hour_reference)
    vwap_distance_pct = _pct(regular_close, vwap_last)
    regular_volume_ratio = _session_volume_ratio(regular, df)
    after_hours_change_pct = _pct(after_price, regular_close)
    after_hours_volume_ratio = after_volume / regular_volume if regular_volume > 0 else 0.0

    score = 0.0
    reasons: list[str] = []
    risk_flags: list[str] = []

    if close_position_pct >= 90:
        score += 20
        reasons.append("정규장 종가가 당일 고가권에서 마감")
    elif close_position_pct >= 80:
        score += 15
        reasons.append("정규장 종가 위치 양호")
    elif close_position_pct >= 70:
        score += 8

    if final_hour_return_pct >= 1.5:
        score += 15
        reasons.append("마감 전 1시간 매수세 강화")
    elif final_hour_return_pct >= 0.5:
        score += 10
    elif final_hour_return_pct > 0:
        score += 5

    if vwap_distance_pct >= 1.0:
        score += 15
        reasons.append("VWAP 위에서 강하게 마감")
    elif vwap_distance_pct >= 0:
        score += 10

    if regular_volume_ratio >= 2.0:
        score += 20
        reasons.append("정규장 거래량 급증")
    elif regular_volume_ratio >= 1.3:
        score += 12

    if after_hours_change_pct >= 2.0:
        score += 20
        reasons.append("에프터장에서 추가 상승 확인")
    elif after_hours_change_pct >= 0.5:
        score += 12
        reasons.append("에프터장 종가 상회 유지")
    elif after_hours_change_pct >= 0:
        score += 5
    else:
        score -= 10
        risk_flags.append("에프터장 가격이 정규장 종가 아래")

    if after_hours_volume_ratio >= 0.08:
        score += 10
        reasons.append("에프터장 거래량 동반")
    elif after_hours_volume_ratio >= 0.03:
        score += 6
    else:
        risk_flags.append("에프터장 거래량 부족")

    if regular_close < 5:
        score -= 10
        risk_flags.append("5달러 미만 저가주")
    if regular_change_pct >= 20 and after_hours_change_pct < 2:
        score -= 10
        risk_flags.append("정규장 급등 후 에프터장 추격 약함")
    if close_position_pct < 60:
        score -= 8
        risk_flags.append("정규장 고가권 마감 실패")

    score = max(0.0, min(100.0, score))
    signal_type = "STRONG_AFTER_HOURS" if score >= 80 else "AFTER_HOURS_WATCH" if score >= 65 else "WATCH"

    return {
        "ticker": ticker,
        "name": Translator.translate_cached(ticker, ticker),
        "source": source,
        "price": _round(after_price, 4),
        "regular_close": _round(regular_close, 4),
        "score": _round(score, 1),
        "signal_type": signal_type,
        "reasons": reasons,
        "risk_flags": risk_flags,
        "catalyst_keywords": [],
        "session_date": regular_close_time.date().isoformat(),
        "details": {
            "regular_change_pct": _round(regular_change_pct),
            "final_hour_return_pct": _round(final_hour_return_pct),
            "close_position_pct": _round(close_position_pct),
            "vwap_distance_pct": _round(vwap_distance_pct),
            "regular_volume_ratio": _round(regular_volume_ratio),
            "after_hours_change_pct": _round(after_hours_change_pct),
            "after_hours_volume_ratio": _round(after_hours_volume_ratio, 4),
            "after_hours_volume": int(after_volume),
            "regular_volume": int(regular_volume),
        },
    }


def _extract_news_text(news_item: dict) -> str:
    content = news_item.get("content") if isinstance(news_item, dict) else None
    title = ""
    if isinstance(content, dict):
        title = str(content.get("title") or "")
    if not title and isinstance(news_item, dict):
        title = str(news_item.get("title") or "")
    return title.lower()


async def _enrich_news_catalysts(candidates: list[dict]) -> list[dict]:
    if not candidates:
        return candidates

    top_candidates = candidates[:NEWS_ENRICH_LIMIT]
    news_results = await asyncio.gather(
        *(fetch_ticker_news(candidate["ticker"]) for candidate in top_candidates),
        return_exceptions=True,
    )

    for candidate, news in zip(top_candidates, news_results):
        if isinstance(news, Exception):
            continue
        matched_keywords = set()
        for item in news[:8]:
            text = _extract_news_text(item)
            for keyword in CATALYST_KEYWORDS:
                if keyword in text:
                    matched_keywords.add(keyword)
        if matched_keywords:
            candidate["catalyst_keywords"] = sorted(matched_keywords)
            candidate["reasons"].append("뉴스 촉매 키워드 감지")
            candidate["score"] = _round(min(100.0, candidate["score"] + 5.0), 1)
            if candidate["score"] >= 80:
                candidate["signal_type"] = "STRONG_AFTER_HOURS"
            elif candidate["score"] >= 65:
                candidate["signal_type"] = "AFTER_HOURS_WATCH"

    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def read_after_hours_candidate_cache() -> dict:
    with _cache_lock:
        response = {
            "candidates": [dict(candidate) for candidate in _after_hours_cache["candidates"]],
            "scope": _after_hours_cache["scope"],
            "sync_status": _after_hours_cache["sync_status"],
            "updated_at": _after_hours_cache["updated_at"],
            "universe_size": _after_hours_cache["universe_size"],
        }
    if is_after_hours_refresh_in_progress():
        response["sync_status"] = AFTER_HOURS_SYNC_REFRESHING
    return response


def is_after_hours_cache_fresh_enough(
    ttl_seconds: int = AFTER_HOURS_REFRESH_COOLDOWN_SECONDS,
) -> bool:
    with _cache_lock:
        if _after_hours_cache["sync_status"] != AFTER_HOURS_SYNC_FRESH:
            return False
        updated_at = _parse_updated_at(_after_hours_cache["updated_at"])
    if updated_at is None:
        return False
    return (datetime.now(tz=ET) - updated_at).total_seconds() < ttl_seconds


def reserve_after_hours_refresh() -> bool:
    global _refresh_in_progress
    with _refresh_lock:
        if _refresh_in_progress:
            return False
        _refresh_in_progress = True
    with _cache_lock:
        _after_hours_cache["sync_status"] = AFTER_HOURS_SYNC_REFRESHING
    return True


def release_after_hours_refresh() -> None:
    global _refresh_in_progress
    with _refresh_lock:
        _refresh_in_progress = False


def is_after_hours_refresh_in_progress() -> bool:
    with _refresh_lock:
        return _refresh_in_progress


def clear_after_hours_candidate_cache() -> None:
    with _cache_lock:
        _after_hours_cache.update({
            "candidates": [],
            "scope": "global",
            "sync_status": AFTER_HOURS_SYNC_EMPTY,
            "updated_at": None,
            "universe_size": 0,
        })
    release_after_hours_refresh()


async def refresh_after_hours_candidate_cache(
    limit: int = DEFAULT_SCAN_LIMIT,
    refresh_reserved: bool = False,
) -> dict:
    if not refresh_reserved and is_after_hours_cache_fresh_enough():
        return read_after_hours_candidate_cache()

    if not refresh_reserved and not reserve_after_hours_refresh():
        return read_after_hours_candidate_cache()

    try:
        tickers, source_map = await get_seed_tickers()
        scan_tickers = tickers[: max(1, min(limit, len(tickers)))]
        data = await fetch_bulk_ohlcv(scan_tickers, interval="1m", period="5d", prepost=True)

        candidates = []
        for ticker in scan_tickers:
            try:
                frame = _extract_ticker_frame(data, ticker)
                candidate = _build_candidate(ticker, source_map.get(ticker, ["MARKET"]), frame)
                if candidate:
                    candidates.append(candidate)
            except Exception:
                logger.exception("[AfterHoursScanner] Failed to score %s", ticker)

        candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)[:25]
        candidates = await _enrich_news_catalysts(candidates)
        sync_status = AFTER_HOURS_SYNC_FRESH if candidates else AFTER_HOURS_SYNC_EMPTY
        response = {
            "candidates": candidates,
            "scope": "global",
            "sync_status": sync_status,
            "updated_at": datetime.now(tz=ET).isoformat(),
            "universe_size": len(scan_tickers),
        }
        with _cache_lock:
            _after_hours_cache.update(response)
        return response
    except Exception:
        logger.exception("[AfterHoursScanner] Refresh failed")
        cached = read_after_hours_candidate_cache()
        cached["sync_status"] = (
            AFTER_HOURS_SYNC_STALE
            if cached["candidates"]
            else AFTER_HOURS_SYNC_FAILED
        )
        with _cache_lock:
            _after_hours_cache.update(cached)
        return cached
    finally:
        release_after_hours_refresh()


def trigger_after_hours_refresh():
    """스케줄러 또는 비동기 외부 스레드에서 에프터장 캐시 갱신을 동기식으로 호출합니다."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        asyncio.create_task(refresh_after_hours_candidate_cache(refresh_reserved=True))
    else:
        loop.run_until_complete(refresh_after_hours_candidate_cache(refresh_reserved=True))

