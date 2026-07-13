"""SSE 전송 계층(Phase 1) 단위 테스트.

Redis 없이 검증 가능한 계약만 다룬다:
  - 채널 네이밍
  - 이벤트 봉투 직렬화(captured_at 동봉 보존)
  - SSE 프레임 포맷(event/data/id 라인 + 종료 빈 줄)
  - Bearer 인증 실패 경로가 DB 접근 이전에 401을 던지는지
publish→subscribe 실제 왕복은 Redis 통합 환경(별도)에서 검증한다.
"""
import json

import pytest
from fastapi import HTTPException

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
