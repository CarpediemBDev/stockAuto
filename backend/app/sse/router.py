"""SSE 멀티플렉스 스트림 엔드포인트 (Phase 1).

GET /api/v1/events 하나의 장기 연결로 공용·유저·(관리자) 채널을 모두 실어 나른다.
브라우저 HTTP/1.1 6-커넥션 제한을 피하려 엔드포인트를 하나로 멀티플렉스한다.

인증: Authorization Bearer 헤더(네이티브 EventSource는 헤더 불가 → 프론트는 fetch 기반 클라이언트 사용).
      토큰 검증은 요청 진입 시 단명 DB 세션으로 1회만 수행하고 즉시 닫는다.
      스트리밍 응답이 커넥션 풀을 장기 점유하지 않도록 get_current_user(요청 수명 = DB 세션 수명) 대신
      수동 인증을 쓴다.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core import sse
from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.models import User, utc_now_aware
from app.core.security import decode_access_token_claims

router = APIRouter(tags=["SSE"])

# keep-alive 주석 프레임 주기(초). 프록시 idle timeout·죽은 연결 감지용.
PING_INTERVAL_SEC = 15


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authenticate(authorization: str | None) -> tuple[int, str]:
    """Bearer 토큰을 검증하고 (user_id, role)을 반환한다. DB 세션은 즉시 닫는다."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("인증 토큰이 필요합니다.")
    token = authorization.split(" ", 1)[1].strip()
    claims = decode_access_token_claims(token)
    sub = claims.get("sub") if claims else None
    if not sub:
        raise _unauthorized("유효하지 않거나 만료된 토큰입니다.")

    db = SessionLocal()
    try:
        try:
            user_id = int(sub)
        except (TypeError, ValueError):
            raise _unauthorized("토큰 서식이 올바르지 않습니다.")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise _unauthorized("사용자를 찾을 수 없습니다.")
        token_version = claims.get("ver", 0)
        if not isinstance(token_version, int) or token_version != user.token_version:
            raise _unauthorized("폐기된 로그인 세션입니다.")
        return user.id, user.role
    finally:
        db.close()


def _sse_frame(event: str, data, event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False, default=str)}")
    return "\n".join(lines) + "\n\n"


@router.get("", include_in_schema=True)
async def stream_events(
    request: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    user_id, role = _authenticate(authorization)

    channels = [sse.CHANNEL_PUBLIC, sse.channel_user(user_id)]
    if role == "ADMIN":
        channels.append(sse.CHANNEL_ADMIN)

    async def event_generator():
        pubsub = sse.get_async_redis().pubsub()
        try:
            # subscribe도 try 안에서 수행해 실패 시에도 finally의 aclose가 커넥션을 회수한다.
            await pubsub.subscribe(*channels)
            # connected: 서버 시각을 동봉해 클라이언트가 clock-skew 오프셋을 1회 산출하게 한다.
            # (낡음 배지가 now(클라)-captured_at(서버)을 계산할 때 시계 차이를 보정하기 위함)
            yield _sse_frame(
                "connected",
                {"server_time": utc_now_aware().isoformat(), "channels": channels},
            )
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=PING_INTERVAL_SEC,
                    )
                except (RedisConnectionError, RedisTimeoutError):
                    # Redis 순단 시 스트림을 조용히 닫는다. 프론트 fetch 클라이언트는
                    # 스트림 종료를 감지해 지터 백오프로 재연결하므로 예외 전파가 불필요하다.
                    logger.warning("[SSE] Redis connection lost mid-stream for user=%s; closing stream", user_id)
                    break
                if message is None:
                    # keep-alive 주석 프레임(이벤트로 파싱되지 않음)
                    yield ": ping\n\n"
                    continue
                raw = message.get("data")
                if not raw:
                    continue
                try:
                    envelope = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    continue
                yield _sse_frame(
                    envelope.get("event", "message"),
                    envelope.get("data"),
                    event_id=envelope.get("id"),
                )
        except asyncio.CancelledError:
            raise
        finally:
            # unsubscribe 실패(이미 끊긴 커넥션 등)와 무관하게 aclose는 반드시 실행해
            # pubsub 커넥션이 풀 밖에 잔류하는 누수를 막는다.
            try:
                await pubsub.unsubscribe(*channels)
            except Exception:  # noqa: BLE001
                logger.warning("[SSE] pubsub unsubscribe failed for user=%s", user_id, exc_info=True)
            finally:
                try:
                    await pubsub.aclose()
                except Exception:  # noqa: BLE001
                    logger.warning("[SSE] pubsub close failed for user=%s", user_id, exc_info=True)

    headers = {
        # no-transform 필수: Next.js rewrite 프록시(및 표준 compression 미들웨어)가
        # 이 지시가 없으면 SSE 응답을 gzip 버퍼에 잡아둬 프레임이 클라이언트에 도달하지 않는다
        # (로컬 실측: 프록시 경유 시 connected 프레임조차 미도달 → no-transform으로 즉시 통과).
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # nginx 버퍼링 비활성화(즉시 flush)
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
