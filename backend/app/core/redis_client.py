import asyncio

import redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import logger


_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """이벤트 루프에 귀속되지 않는 동기 Redis 클라이언트를 반환합니다."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
            health_check_interval=30,
        )
        logger.info("[*] Redis client initialized for the configured endpoint")
    return _redis_client


async def ping_redis() -> bool:
    try:
        return bool(await asyncio.to_thread(get_redis_client().ping))
    except (RedisError, ValueError, OSError):
        logger.exception("[Redis] Connectivity check failed; trading orders will fail closed")
        return False


async def close_redis_client() -> None:
    global _redis_client
    client = _redis_client
    _redis_client = None
    if client is not None:
        await asyncio.to_thread(client.close)
        logger.info("[*] Redis client closed")
