"""스캐너 릴레이 파이프라인 (Watchlist Relay).

전일 저녁 애프터장 스캐너 캐시와 밤 스윙 예측 DB 스냅샷을 읽어,
다음날 아침 15분 스캐너(scan_market_expert)의 우선 감시 티커를 만든다.

설계 원칙:
- 자체 저장소를 만들지 않는다. 두 소스의 기존 캐시(인메모리 + DB 스냅샷)를 읽기만 한다.
- 어떤 소스가 실패/소실/노후화되어도 예외를 전파하지 않고 해당 몫만 비운다
  (릴레이 전체 실패 시 스캐너는 기존과 완전히 동일하게 동작 — 자연 강등).
- 우선 감시 대상은 Stage 1 점수 면제(WATCHLIST와 동급) + Stage 2 예약 슬롯으로 반영된다.
  Stage 2 상위 컷 정렬 자체는 바꾸지 않으므로 기존 후보 선정에는 영향이 없다(순수 추가형).
"""

from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.system_settings import (
    SETTING_ENABLE_SCANNER_RELAY,
    is_system_setting_enabled,
)

# 릴레이 출처 태그 (source_map에 병기되어 다운스트림에서 유래를 추적)
RELAY_SOURCE_AFTER_HOURS = "RELAY_AFTER_HOURS"
RELAY_SOURCE_SWING = "RELAY_SWING"
_RELAY_TAG_PREFIX = "RELAY_"

# 소스별 채택 기준
AFTER_HOURS_MIN_SCORE = 65.0   # after_hours_scanner의 AFTER_HOURS_WATCH 임계와 일치
SWING_MIN_SCORE = 60.0         # 스윙 예측 종합점수 하한
MAX_PER_SOURCE = 15            # 소스당 최대 채택 수 (score 내림차순 상위)
MAX_AGE_HOURS = 72.0           # 주말 갭을 고려한 캐시 신선도 상한

# Stage 2 예약 슬롯: 상위 컷에서 밀린 릴레이 후보를 추가로 편입하는 최대 개수
RELAY_RESERVED_SLOTS = 5


def _is_fresh(updated_at_iso: str | None, now: datetime | None = None) -> bool:
    if not updated_at_iso:
        return False
    try:
        updated_at = datetime.fromisoformat(updated_at_iso)
    except (TypeError, ValueError):
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return (now - updated_at) <= timedelta(hours=MAX_AGE_HOURS)


def _top_tickers(candidates: list, min_score: float) -> list[str]:
    """후보 목록에서 점수 하한을 넘긴 티커를 score 내림차순 상위 MAX_PER_SOURCE개 추출한다."""
    scored = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        ticker = str(candidate.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        try:
            score = float(candidate.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        if score >= min_score:
            scored.append((score, ticker))
    scored.sort(reverse=True)
    seen = set()
    result = []
    for _, ticker in scored:
        if ticker in seen:
            continue
        seen.add(ticker)
        result.append(ticker)
        if len(result) >= MAX_PER_SOURCE:
            break
    return result


def _collect_after_hours() -> list[str]:
    from app.scanner.after_hours_scanner import read_after_hours_candidate_cache

    cache = read_after_hours_candidate_cache()
    if not _is_fresh(cache.get("updated_at")):
        return []
    return _top_tickers(cache.get("candidates", []), AFTER_HOURS_MIN_SCORE)


def _collect_swing() -> list[str]:
    from app.scanner.swing_prediction_cache import (
        get_swing_cache_key,
        read_swing_prediction_cache,
    )

    db = SessionLocal()
    try:
        response = read_swing_prediction_cache(get_swing_cache_key(), db)
    finally:
        db.close()
    if not _is_fresh(response.get("updated_at")):
        return []
    return _top_tickers(response.get("candidates", []), SWING_MIN_SCORE)


def get_relay_priority_map() -> dict[str, list[str]]:
    """우선 감시 티커 → 릴레이 출처 태그 목록을 반환한다.

    동기 DB 접근이 포함되므로 async 컨텍스트에서는 asyncio.to_thread로 호출할 것.
    모든 실패는 삼켜지고 해당 소스 몫만 빈 채로 반환된다.

    킬 스위치(enable_scanner_relay)가 꺼져 있으면 빈 맵을 반환해, 스캐너가 릴레이
    도입 이전과 완전히 동일하게 동작한다. 스위치 조회 자체가 실패하면 기본값(ON)으로
    폴백하므로 일시적 DB 장애가 매매 대상을 조용히 축소하지 않는다.
    """
    priority: dict[str, list[str]] = {}

    if not is_system_setting_enabled(SETTING_ENABLE_SCANNER_RELAY):
        logger.info("[Relay] disabled by system setting — falling back to normal scan universe")
        return priority

    try:
        for ticker in _collect_after_hours():
            priority.setdefault(ticker, []).append(RELAY_SOURCE_AFTER_HOURS)
    except Exception as e:
        logger.warning(f"[Relay] after-hours source unavailable, skipping: {e}")

    try:
        for ticker in _collect_swing():
            priority.setdefault(ticker, []).append(RELAY_SOURCE_SWING)
    except Exception as e:
        logger.warning(f"[Relay] swing prediction source unavailable, skipping: {e}")

    return priority


def is_relay_source(sources: list) -> bool:
    """source_map 태그 목록에 릴레이 출처가 포함되어 있는지 판별한다."""
    if not isinstance(sources, (list, tuple, set)):
        return False
    return any(isinstance(s, str) and s.startswith(_RELAY_TAG_PREFIX) for s in sources)


def merge_reserved_candidates(ranked: list[dict], base_limit: int, reserved_limit: int = RELAY_RESERVED_SLOTS) -> list[dict]:
    """정렬된 Stage 1 통과 목록에서 상위 base_limit개를 취하고,
    컷에서 밀린 릴레이 후보를 최대 reserved_limit개까지 추가 편입한다.

    상위 컷 안의 구성·순서는 그대로 유지된다(순수 추가형).
    """
    selected = ranked[:base_limit]
    if reserved_limit <= 0:
        return selected
    overflow_relay = [
        cand for cand in ranked[base_limit:]
        if is_relay_source(cand.get("source", []))
    ]
    return selected + overflow_relay[:reserved_limit]
