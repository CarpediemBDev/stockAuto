import asyncio
from dataclasses import dataclass, field

from redis.exceptions import RedisError

from app.core.logging import logger
from app.core.redis_client import get_redis_client


DEFAULT_USER_LOCK_TTL_SECONDS = 120
DEFAULT_SYMBOL_LOCK_TTL_SECONDS = 60


class RedisLockUnavailable(RuntimeError):
    """Redis 장애로 안전한 주문 락을 판정할 수 없을 때 발생합니다."""


_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""


async def _call_redis(method_name: str, *args, **kwargs):
    try:
        client = get_redis_client()
        method = getattr(client, method_name)
        return await asyncio.to_thread(method, *args, **kwargs)
    except (RedisError, ValueError, OSError) as exc:
        raise RedisLockUnavailable("Redis order lock is unavailable") from exc


@dataclass
class RedisLockLease:
    key: str
    request_id: str
    ttl_seconds: int
    _renew_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _released: bool = field(default=False, init=False, repr=False)

    def start_renewal(self) -> None:
        self._renew_task = asyncio.create_task(self._renew_loop())

    async def _renew_loop(self) -> None:
        import time
        interval = max(1.0, self.ttl_seconds / 3)
        start_time = time.monotonic()
        max_renew_duration = 600  # Hard timeout: 10 minutes
        try:
            while True:
                await asyncio.sleep(interval)
                if time.monotonic() - start_time > max_renew_duration:
                    logger.error("[RedisLock] Hard timeout reached. Stopping renewal for key=%s", self.key)
                    return
                renewed = await _call_redis(
                    "eval",
                    _RENEW_SCRIPT,
                    1,
                    self.key,
                    self.request_id,
                    self.ttl_seconds,
                )
                if not renewed:
                    logger.error("[RedisLock] Lease ownership was lost for key=%s", self.key)
                    return
        except asyncio.CancelledError:
            raise
        except RedisLockUnavailable:
            logger.exception("[RedisLock] Lease renewal failed for key=%s", self.key)

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        if self._renew_task is not None:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass
        try:
            await _call_redis(
                "eval",
                _RELEASE_SCRIPT,
                1,
                self.key,
                self.request_id,
            )
        except RedisLockUnavailable:
            logger.exception("[RedisLock] Failed to release key=%s", self.key)


async def _acquire_lease(
    key: str,
    request_id: str,
    ttl_seconds: int,
) -> RedisLockLease | None:
    acquired = await _call_redis(
        "set",
        key,
        request_id,
        nx=True,
        ex=ttl_seconds,
    )
    if not acquired:
        return None
    lease = RedisLockLease(key=key, request_id=request_id, ttl_seconds=ttl_seconds)
    lease.start_renewal()
    return lease


async def acquire_user_operation_lock(
    user_id: int,
    request_id: str,
    ttl_seconds: int = DEFAULT_USER_LOCK_TTL_SECONDS,
) -> RedisLockLease | None:
    return await _acquire_lease(
        f"lock:trading_user:{user_id}",
        request_id,
        ttl_seconds,
    )


async def acquire_symbol_order_lock(
    user_id: int,
    symbol: str,
    request_id: str,
    ttl_seconds: int = DEFAULT_SYMBOL_LOCK_TTL_SECONDS,
) -> RedisLockLease | None:
    normalized_symbol = symbol.strip().upper()
    return await _acquire_lease(
        f"lock:order_submit:{user_id}:{normalized_symbol}",
        request_id,
        ttl_seconds,
    )
