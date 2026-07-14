"""SSE 전송 계층 — Redis pub/sub 기반 멀티플렉스 이벤트 스트림 인프라.

이 모듈은 **전송(delivery)만** 담당한다.
데이터 신선도(captured_at)는 payload에 동봉되어 흐르며, 이 모듈이 만들거나 판단하지 않는다.
채널 publish는 각 생산자(스캐너·시장·스냅샷·봇 토글·관심종목)에 배선되어 있으며,
발행은 전부 publish_sync 하나로 통일한다(아래 get_async_redis 주석 참조).

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
#
# ⚠️ uvicorn 메인 이벤트 루프 전용(app/sse/router.py의 스트림 구독).
# asyncio 커넥션은 생성된 루프에 바인딩되므로, 스케줄러 잡처럼 asyncio.run()으로
# 일회용 루프를 만들었다 닫는 컨텍스트에서 이 싱글톤을 쓰면 닫힌 루프의 커넥션이
# 풀에 남아 이후 publish/subscribe가 조용히 실패한다. 발행은 컨텍스트 무관하게
# publish_sync(동기 클라이언트, 스레드 안전)만 사용한다.
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
    """유일한 발행 경로. 동기 Redis 클라이언트라 어떤 스레드·이벤트 루프에서도 안전하다.

    (과거의 async publish는 스케줄러 잡의 일회용 루프와 메인 루프가 asyncio 커넥션 풀을
    공유하다 발행이 조용히 죽는 문제로 제거됨 — async 컨텍스트에서도 이 함수를 쓴다.
    로컬 Redis publish는 sub-ms라 루프 블로킹 영향은 무시 가능.)

    전송은 best-effort다. Redis 장애로 실패해도 예외를 전파하지 않는다
    (클라이언트는 다음 이벤트/revalidateOnFocus로 자연 복구).
    """
    try:
        get_redis_client().publish(channel, _encode(event, data))
    except Exception:  # noqa: BLE001
        logger.warning("[SSE] publish_sync failed channel=%s event=%s", channel, event, exc_info=True)


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
    """유저 잔고/보유가 갱신됐음을 해당 유저 채널로 알린다(invalidate).

    스냅샷이 실제로 기록됐을 때만 호출한다(record_equity_snapshot 성공 경로).
    trade_event=True(체결·청산·리셋 등 force 스냅샷)면 거래 로그(/trades)도 함께
    무효화한다 — 이게 없으면 SSE on(폴링 off)에서 거래 로그가 포커스 전까지 낡는다.
    관리자 목록은 과다 무효화를 피하기 위해 여기서 쏘지 않고, 1분 벌크 동기
    (admin_balance_cache_sync)와 이산 이벤트(봇 토글)에서만 무효화한다.
    """
    user_ch = channel_user(user_id)
    publish_sync(user_ch, EVENT_BALANCE, None)
    publish_sync(user_ch, EVENT_HOLDINGS, None)
    if trade_event:
        publish_sync(user_ch, EVENT_TRADES, None)


def notify_admin_users() -> None:
    """관리자 사용자 목록(실시간 랭킹) 무효화. 1분 벌크 동기·이산 이벤트에서만 호출."""
    publish_sync(CHANNEL_ADMIN, EVENT_ADMIN_USERS, None)


def notify_bot_status(user_id: int) -> None:
    """봇 가동 상태 변경을 알린다(유저 화면 + 관리자 목록)."""
    publish_sync(channel_user(user_id), EVENT_BOT_STATUS, None)
    publish_sync(CHANNEL_ADMIN, EVENT_ADMIN_USERS, None)


def notify_watchlist(user_id: int) -> None:
    """관심종목 변경을 알린다."""
    publish_sync(channel_user(user_id), EVENT_WATCHLIST, None)
