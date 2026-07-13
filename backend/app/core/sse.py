"""SSE 전송 계층 — Redis pub/sub 기반 멀티플렉스 이벤트 스트림 인프라 (Phase 1).

이 모듈은 **전송(delivery)만** 담당한다.
데이터 신선도(captured_at)는 payload에 동봉되어 흐르며, 이 모듈이 만들거나 판단하지 않는다.
실제 채널 publish 호출(스냅샷 갱신·스캔 완료·체결 등)은 Phase 2/3에서 각 생산자에 배선한다.

채널 설계:
  - sse:public       공용 데이터(스캐너·시장). 1회 publish → 전 구독자 팬아웃.
  - sse:user:{id}    개인 데이터(잔고·보유·봇상태 등).
  - sse:admin        관리자 전용(사용자 목록·시스템 로그 등).

멀티워커 안전성: publish가 Redis를 경유하므로, 스케줄러가 어느 워커에서 돌든
해당 클라이언트 연결을 쥔 워커의 구독자에게 전달된다.
"""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import logger
from app.core.redis_client import get_redis_client

CHANNEL_PUBLIC = "sse:public"
CHANNEL_ADMIN = "sse:admin"


def channel_user(user_id: int) -> str:
    return f"sse:user:{user_id}"


# 스트림 구독 전용 async Redis 클라이언트. 동기 주문-락 클라이언트와 커넥션을 분리해
# 장기 연결(pub/sub)이 짧은 요청-응답 락 경로를 방해하지 않도록 한다.
_async_redis: aioredis.Redis | None = None


def get_async_redis() -> aioredis.Redis:
    global _async_redis
    if _async_redis is None:
        _async_redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
            health_check_interval=30,
        )
        logger.info("[SSE] async Redis client initialized for pub/sub streaming")
    return _async_redis


async def close_async_redis() -> None:
    global _async_redis
    client = _async_redis
    _async_redis = None
    if client is not None:
        try:
            await client.aclose()
            logger.info("[SSE] async Redis client closed")
        except Exception:  # noqa: BLE001 - 종료 경로는 best-effort
            logger.warning("[SSE] async Redis close failed", exc_info=True)


def _encode(event: str, data: Any) -> str:
    """이벤트 봉투(envelope)를 JSON 문자열로 직렬화한다. data 안에는 captured_at이 동봉된다."""
    return json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)


def publish_sync(channel: str, event: str, data: Any) -> None:
    """동기 컨텍스트(스케줄러 스레드 등)에서 이벤트를 publish한다.

    전송은 best-effort다. Redis 장애로 실패해도 예외를 전파하지 않는다
    (클라이언트는 다음 이벤트/폴백 폴링으로 자연 복구).
    """
    try:
        get_redis_client().publish(channel, _encode(event, data))
    except Exception:  # noqa: BLE001
        logger.warning("[SSE] publish_sync failed channel=%s event=%s", channel, event, exc_info=True)


async def publish(channel: str, event: str, data: Any) -> None:
    """async 컨텍스트에서 이벤트를 publish한다. 전송은 best-effort."""
    try:
        await get_async_redis().publish(channel, _encode(event, data))
    except Exception:  # noqa: BLE001
        logger.warning("[SSE] publish failed channel=%s event=%s", channel, event, exc_info=True)


# ── 이벤트 이름 (프론트 EVENT_TO_KEY 매핑과의 계약) ──────────────────────────
# Phase 2/3 발행부와 프론트 프로바이더가 공유하는 이름. data=None → 클라이언트 revalidate(재조회).
EVENT_BALANCE = "balance"
EVENT_HOLDINGS = "holdings"
EVENT_TRADES = "trades"
EVENT_BOT_STATUS = "bot_status"
EVENT_WATCHLIST = "watchlist"
EVENT_ADMIN_USERS = "admin_users"
EVENT_SCANNER_LATEST = "scanner_latest"
EVENT_SWING = "swing"
EVENT_AFTER_HOURS = "after_hours"
EVENT_MARKET = "market"


def notify_user_equity(user_id: int, trade_event: bool = False) -> None:
    """유저 잔고/보유(및 관리자 랭킹)가 바뀌었음을 알린다(invalidate).

    스냅샷이 실제로 기록됐을 때만 호출한다. trade_event=True(체결·청산·리셋)면 거래 로그도 함께 무효화.
    동기 컨텍스트(record_equity_snapshot 등)에서 호출되므로 publish_sync를 쓴다.
    """
    user_ch = channel_user(user_id)
    publish_sync(user_ch, EVENT_BALANCE, None)
    publish_sync(user_ch, EVENT_HOLDINGS, None)
    if trade_event:
        publish_sync(user_ch, EVENT_TRADES, None)
    publish_sync(CHANNEL_ADMIN, EVENT_ADMIN_USERS, None)


def notify_bot_status(user_id: int) -> None:
    """봇 가동 상태 변경을 알린다(유저 화면 + 관리자 목록)."""
    publish_sync(channel_user(user_id), EVENT_BOT_STATUS, None)
    publish_sync(CHANNEL_ADMIN, EVENT_ADMIN_USERS, None)


def notify_watchlist(user_id: int) -> None:
    """관심종목 변경을 알린다."""
    publish_sync(channel_user(user_id), EVENT_WATCHLIST, None)
