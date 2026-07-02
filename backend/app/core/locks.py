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
    lost_ownership: bool = field(default=False, init=False, repr=False)

    def start_renewal(self) -> None:
        self._renew_task = asyncio.create_task(self._renew_loop())

    async def _renew_loop(self) -> None:
        import time
        import random
        interval = max(1.0, self.ttl_seconds / 3)
        start_time = time.monotonic()
        max_renew_duration = 600  # Hard timeout: 10 minutes
        try:
            while True:
                await asyncio.sleep(interval)
                if time.monotonic() - start_time > max_renew_duration:
                    logger.error("[RedisLock] Hard timeout reached. Stopping renewal for key=%s", self.key)
                    self.lost_ownership = True
                    return

                # 지수 백오프 + 지터 도입 (최대 3회 재시도)
                success = False
                total_backoff = 0.0
                for attempt in range(1, 4):
                    try:
                        if total_backoff >= self.ttl_seconds:
                            logger.error("[RedisLock] CRITICAL_LOST: Backoff wait time %.2fs exceeded TTL %ds for key=%s", total_backoff, self.ttl_seconds, self.key)
                            self.lost_ownership = True
                            return

                        renewed = await _call_redis(
                            "eval",
                            _RENEW_SCRIPT,
                            1,
                            self.key,
                            self.request_id,
                            self.ttl_seconds,
                        )
                        if renewed:
                            success = True
                            break
                        else:
                            # 락을 완전히 상실한 경우 (예: TTL 만료 등으로 다른 클라이언트가 락 획득)
                            logger.error("[RedisLock] CRITICAL_LOST: Lease ownership was lost for key=%s (renew returned 0)", self.key)
                            self.lost_ownership = True
                            return
                    except RedisLockUnavailable as e:
                        if attempt == 3:
                            logger.exception("[RedisLock] CRITICAL_LOST: Lease renewal failed after 3 attempts for key=%s", self.key)
                            self.lost_ownership = True
                            raise e
                        backoff = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.0, 0.1)
                        total_backoff += backoff
                        logger.warning(
                            "[RedisLock] Lease renewal attempt %d failed for key=%s. Retrying in %.2f seconds... Error: %s",
                            attempt, self.key, backoff, e
                        )
                        await asyncio.sleep(backoff)

                if not success:
                    self.lost_ownership = True
                    return

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[RedisLock] Unexpected error in lease renewal loop for key=%s", self.key)
            self.lost_ownership = True

    async def release(self) -> None:
        if self._released:
            return
        self._released = True

        async def _do_release():
            if self._renew_task is not None:
                self._renew_task.cancel()
                try:
                    await self._renew_task
                except (asyncio.CancelledError, Exception):
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

        # parent task의 강제 취소(CancelledError)로부터 release 처리 완결 보장
        try:
            await asyncio.shield(_do_release())
        except asyncio.CancelledError:
            pass


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


def acquire_bootstrap_file_lock():
    """
    Uvicorn과 백그라운드 스케줄러 기동 시 SQLite 마이그레이션 및 Seeding 중복 실행을
    방어하기 위해 파일 기반 분산 락(sqlite_migration.lock)을 획득합니다.
    """
    import os
    from filelock import FileLock

    # CWD 불일치에 따른 분할 뇌 방지를 위해 절대 경로로 지정
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    lock_path = os.path.join(backend_dir, "sqlite_migration.lock")

    # 60초 타임아웃
    return FileLock(lock_path, timeout=60)
