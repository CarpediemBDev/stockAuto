import asyncio
import hashlib
import threading
import time
from fastapi import Request
from app.core.redis_client import get_redis_client
from app.core.exceptions import RateLimitExceededException
from app.core.logging import logger


_RATE_LIMIT_SCRIPT = """
local current = redis.call('incr', KEYS[1])
if current == 1 then
    redis.call('expire', KEYS[1], ARGV[1])
end
return current
"""
_FALLBACK_PRUNE_THRESHOLD = 1_024
_FALLBACK_MAX_KEYS = 10_000

_global_fallback_lock = threading.Lock()
_global_fallback_windows: dict[str, tuple[float, int]] = {}


class RateLimiter:
    """
    고속 Redis 캐시를 활용한 커스텀 Rate Limiter 의존성입니다.
    FastAPI 엔드포인트에서 Depends(RateLimiter(...)) 형태로 사용합니다.
    """

    def __init__(
        self,
        max_requests: int = 120,
        window_seconds: int = 60,
        key_field: str | None = None,
        peer_max_requests: int | None = None,
    ):
        if (
            max_requests <= 0
            or window_seconds <= 0
            or (peer_max_requests is not None and peer_max_requests <= 0)
        ):
            raise ValueError("RateLimiter limits must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_field = key_field
        self.peer_max_requests = peer_max_requests

    def _increment_fallback(self, key: str) -> int:
        """Redis 장애 시 동작하는 프로세스 전역 Fallback 캐시 증가 함수."""
        now = time.monotonic()
        with _global_fallback_lock:
            if len(_global_fallback_windows) >= _FALLBACK_PRUNE_THRESHOLD:
                expired_keys = [
                    stored_key
                    for stored_key, (started_at, _count) in _global_fallback_windows.items()
                    if now - started_at >= self.window_seconds
                ]
                for expired_key in expired_keys:
                    _global_fallback_windows.pop(expired_key, None)
            if len(_global_fallback_windows) >= _FALLBACK_MAX_KEYS:
                oldest_key = min(
                    _global_fallback_windows,
                    key=lambda stored_key: _global_fallback_windows[stored_key][0],
                )
                _global_fallback_windows.pop(oldest_key, None)
            started_at, count = _global_fallback_windows.get(key, (now, 0))
            if now - started_at >= self.window_seconds:
                started_at, count = now, 0
            count += 1
            _global_fallback_windows[key] = (started_at, count)
            return count

    async def __call__(self, request: Request) -> None:
        """FastAPI 의존성 호출. 제한 초과 시 RateLimitExceededException 발생."""
        client_ip = request.client.host if request.client else "127.0.0.1"

        path = request.url.path
        limits = [(f"rate_limit:{path}:peer:{client_ip}", self.peer_max_requests or self.max_requests)]

        if self.key_field:
            try:
                payload = await request.json()
            except Exception:
                raise RateLimitExceededException(message="잘못된 요청 페이로드입니다.")
            field_value = payload.get(self.key_field) if isinstance(payload, dict) else None
            if isinstance(field_value, str) and field_value.strip():
                normalized_value = field_value.strip().lower()
                principal_hash = hashlib.sha256(
                    normalized_value.encode("utf-8")
                ).hexdigest()
                limits.append(
                    (
                        f"rate_limit:{path}:{self.key_field}:{principal_hash}",
                        self.max_requests,
                    )
                )

        for key, limit in limits:
            await self._enforce_limit(key, limit, client_ip, path)

    async def _enforce_limit(
        self,
        key: str,
        limit: int,
        client_ip: str,
        path: str,
    ) -> None:
        """주어진 키에 대해 Redis(또는 Fallback) 기반으로 Rate Limit를 적용합니다."""
        try:
            client = get_redis_client()

            current_count = await asyncio.to_thread(
                client.eval,
                _RATE_LIMIT_SCRIPT,
                1,
                key,
                self.window_seconds,
            )

        except Exception as e:
            current_count = self._increment_fallback(key)
            logger.error(
                "[RateLimit] Redis error; using per-process fallback limiter: %s",
                e,
            )

        if current_count > limit:
            logger.warning("[RateLimit] IP %s exceeded limit on %s", client_ip, path)
            raise RateLimitExceededException(message="요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")
