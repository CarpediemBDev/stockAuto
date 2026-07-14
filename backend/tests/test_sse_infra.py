"""SSE 전송 계층 단위 테스트.

Redis 없이 검증 가능한 계약을 다룬다:
  - 채널 네이밍
  - 이벤트 봉투 직렬화(captured_at 동봉 보존)
  - SSE 프레임 포맷(event/data/id 라인 + 종료 빈 줄)
  - Bearer 인증 실패 경로가 DB 접근 이전에 401을 던지는지
  - 발행 헬퍼(notify_*)가 올바른 채널·이벤트로 발행하는지(fake 동기 Redis)
  - 발행 봉투 → 스트림 프레임 왕복(스트림 엔드포인트, fake pubsub)
  - 발행 경로가 publish_sync 하나로 통일됐는지(async publish 재도입 방지)
실 Redis 네트워크 왕복만 수동/통합 환경 검증 영역으로 남는다.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core import sse
from app.sse import router as sse_router


def test_channel_naming():
    assert sse.CHANNEL_PUBLIC == "sse:public"
    assert sse.CHANNEL_ADMIN == "sse:admin"
    assert sse.channel_user(42) == "sse:user:42"


def test_encode_preserves_captured_at_inside_data():
    # 전송 계층은 payload를 건드리지 않는다 — captured_at이 data 안에 그대로 실려야 한다.
    encoded = sse._encode("balance", {"total_asset": 1000, "captured_at": "2026-07-13T00:00:00+00:00"})
    envelope = json.loads(encoded)
    assert envelope["event"] == "balance"
    assert envelope["data"]["captured_at"] == "2026-07-13T00:00:00+00:00"
    assert envelope["data"]["total_asset"] == 1000


def test_sse_frame_format():
    frame = sse_router._sse_frame("connected", {"server_time": "t"}, event_id="7")
    assert frame.endswith("\n\n")  # 프레임 종료 빈 줄
    lines = frame.rstrip("\n").split("\n")
    assert "id: 7" in lines
    assert "event: connected" in lines
    data_line = next(line for line in lines if line.startswith("data: "))
    assert json.loads(data_line[len("data: "):]) == {"server_time": "t"}


def test_sse_frame_without_id_omits_id_line():
    frame = sse_router._sse_frame("heartbeat", {})
    assert "id:" not in frame
    assert "event: heartbeat" in frame


def test_authenticate_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc:
        sse_router._authenticate(None)
    assert exc.value.status_code == 401


def test_authenticate_non_bearer_raises_401():
    with pytest.raises(HTTPException) as exc:
        sse_router._authenticate("Basic abc123")
    assert exc.value.status_code == 401


def test_authenticate_invalid_token_raises_401_before_db():
    # 형식이 깨진 토큰은 decode 단계에서 None → DB 접근 전에 401.
    with pytest.raises(HTTPException) as exc:
        sse_router._authenticate("Bearer not-a-real-jwt")
    assert exc.value.status_code == 401


# ── 발행 경로 계약 (fake 동기 Redis) ──────────────────────────────────────────

class _FakeSyncRedis:
    def __init__(self):
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = _FakeSyncRedis()
    monkeypatch.setattr(sse, "get_redis_client", lambda: fake)
    return fake


def _events_of(fake: _FakeSyncRedis) -> list[tuple[str, str]]:
    return [(ch, json.loads(msg)["event"]) for ch, msg in fake.published]


def test_notify_user_equity_publishes_balance_and_holdings(fake_redis):
    sse.notify_user_equity(7)
    assert _events_of(fake_redis) == [
        ("sse:user:7", sse.EVENT_BALANCE),
        ("sse:user:7", sse.EVENT_HOLDINGS),
    ]


def test_notify_user_equity_trade_event_also_invalidates_trades(fake_redis):
    # 체결·리셋(force 스냅샷) 경로: 거래 로그도 push해야 SSE on(폴링 off)에서 낡지 않는다.
    sse.notify_user_equity(7, trade_event=True)
    assert ("sse:user:7", sse.EVENT_TRADES) in _events_of(fake_redis)


def test_notify_admin_users_publishes_to_admin_channel(fake_redis):
    sse.notify_admin_users()
    assert _events_of(fake_redis) == [(sse.CHANNEL_ADMIN, sse.EVENT_ADMIN_USERS)]


def test_notify_bot_status_reaches_user_and_admin(fake_redis):
    sse.notify_bot_status(3)
    assert _events_of(fake_redis) == [
        ("sse:user:3", sse.EVENT_BOT_STATUS),
        (sse.CHANNEL_ADMIN, sse.EVENT_ADMIN_USERS),
    ]


def test_async_publish_is_removed():
    # 발행은 publish_sync 하나로 통일한다. async publish는 스케줄러 잡의 asyncio.run
    # 일회용 루프와 메인 루프가 커넥션 풀을 공유하다 조용히 죽는 문제로 제거됨 — 재도입 금지.
    assert not hasattr(sse, "publish")


def test_publish_sync_swallows_redis_failure(monkeypatch):
    # 전송은 best-effort: Redis 장애가 생산자(스케줄러/체결 경로)를 죽이면 안 된다.
    class _BrokenRedis:
        def publish(self, *_args):
            raise ConnectionError("redis down")

    monkeypatch.setattr(sse, "get_redis_client", lambda: _BrokenRedis())
    sse.notify_user_equity(1, trade_event=True)  # 예외가 전파되면 테스트 실패


# ── 발행 봉투 → 스트림 프레임 왕복 (fake pubsub, Redis 불필요) ────────────────

class _FakePubSub:
    """봉투 큐를 소진하면 exhausted=True — 테스트는 이를 클라이언트 disconnect로 연결해
    무한 스트림을 자연 종료시킨다(TestClient에서 스트림 강제 close는 행업 위험)."""

    def __init__(self, envelopes: list[str]):
        self._queue = list(envelopes)
        self.exhausted = not self._queue
        self.subscribed: tuple[str, ...] = ()
        self.cleaned_up = False

    async def subscribe(self, *channels: str) -> None:
        self.subscribed = channels

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float | None = None):
        if self._queue:
            message = {"type": "message", "data": self._queue.pop(0)}
            self.exhausted = not self._queue
            return message
        await asyncio.sleep(0)
        return None  # 실서버에선 keep-alive ping 경로

    async def unsubscribe(self, *channels: str) -> None:
        self.cleaned_up = True

    async def aclose(self) -> None:
        pass


class _FakeAsyncRedis:
    def __init__(self, pubsub: _FakePubSub):
        self._pubsub = pubsub

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


def _run_stream(monkeypatch, pubsub: _FakePubSub, user_id: int, role: str) -> list[str]:
    """fake pubsub으로 /events 스트림을 한 번 돌리고 수신 라인 전체를 반환한다.

    봉투 큐가 비면 request.is_disconnected()가 True를 돌려주도록 패치해
    스트림이 자연 종료된다(정리 경로 finally까지 실행됨을 보장).
    """
    monkeypatch.setattr(sse_router.sse, "get_async_redis", lambda: _FakeAsyncRedis(pubsub))
    monkeypatch.setattr(sse_router, "_authenticate", lambda authorization: (user_id, role))

    async def _fake_is_disconnected(self) -> bool:
        return pubsub.exhausted

    monkeypatch.setattr("starlette.requests.Request.is_disconnected", _fake_is_disconnected)

    app = FastAPI()
    app.include_router(sse_router.router, prefix="/api/v1/events")
    client = TestClient(app)

    lines: list[str] = []
    with client.stream("GET", "/api/v1/events", headers={"Authorization": "Bearer t"}) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        lines = list(res.iter_lines())
    return lines


def test_stream_round_trip_envelope_to_frame(monkeypatch):
    """생산자 봉투(publish 인코딩)가 스트림 엔드포인트에서 SSE 프레임으로 그대로 나오는지."""
    pubsub = _FakePubSub([sse._encode(sse.EVENT_BALANCE, None)])
    lines = _run_stream(monkeypatch, pubsub, user_id=7, role="USER")

    # connected 제어 프레임(서버 시각 동봉) → balance invalidate 프레임 순서로 도착해야 한다.
    assert "event: connected" in lines
    assert f"event: {sse.EVENT_BALANCE}" in lines
    assert "data: null" in lines
    # 일반 유저는 공용+본인 채널만 구독하고(관리자 채널 미포함), 종료 시 정리까지 수행한다.
    assert pubsub.subscribed == (sse.CHANNEL_PUBLIC, sse.channel_user(7))
    assert pubsub.cleaned_up


def test_stream_admin_role_subscribes_admin_channel(monkeypatch):
    pubsub = _FakePubSub([])
    lines = _run_stream(monkeypatch, pubsub, user_id=1, role="ADMIN")

    assert "event: connected" in lines
    assert pubsub.subscribed == (sse.CHANNEL_PUBLIC, sse.channel_user(1), sse.CHANNEL_ADMIN)
    assert pubsub.cleaned_up
