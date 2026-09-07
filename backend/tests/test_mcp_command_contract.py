"""MCP 명령 엔드포인트의 계약을 고정한다.

배경 - 이 엔드포인트는 "명령이 안전하게 큐에 적재되었습니다. 워커가 순차적으로
처리합니다"라고 응답했지만, 그 워커가 저장소에 존재한 적이 없다(LPOP·BRPOP·
RPOPLPUSH 0건). 사용자에게 실행을 약속하면서 아무 일도 일어나지 않았고, 큐 키에
TTL이 없어 적재분이 영구히 남았다. 나중에 워커를 붙이는 순간 오래된 BUY 명령이
한꺼번에 체결될 수 있는 잠복 위험이었다.

여기서 고정하는 것은 두 가지다.
1) 실행 계약 - 실행하지 않으면서 성공을 반환하지 않는다(501).
2) 응답 계약 - API_STANDARD의 표준 봉투를 따른다.

특히 test_confirmed_buy_is_never_queued는 안전 회귀 가드다. 적재를 되살리면서
워커를 함께 붙이지 않으면 이 테스트가 즉시 깨진다.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user
from app.core.exceptions import StockAutoException, stock_auto_exception_handler
from app.mcp import router as mcp_router


class RecordingRedis:
    """호출된 Redis 명령을 기록하는 가짜 클라이언트.

    관대한 페이크(무엇을 부르든 성공)를 쓰면 '적재하지 않는다'는 계약을 검증할 수
    없으므로, 쓰기 계열 호출을 전부 기록해 단언 대상으로 만든다.
    """

    def __init__(self, queue_length: int = 0):
        self.queue_length = queue_length
        self.calls: list[tuple] = []

    def rpush(self, key, value):
        self.calls.append(("rpush", key, value))
        self.queue_length += 1
        return self.queue_length

    def llen(self, key):
        self.calls.append(("llen", key))
        return self.queue_length

    @property
    def write_calls(self):
        return [c for c in self.calls if c[0] != "llen"]


class StubUser:
    id = 7


@pytest.fixture
def fake_redis(monkeypatch):
    client = RecordingRedis()
    monkeypatch.setattr(mcp_router, "get_redis_client", lambda: client)
    return client


@pytest.fixture
def client(fake_redis):
    app = FastAPI()
    app.include_router(mcp_router.router, prefix="/api/v1/mcp")
    app.add_exception_handler(StockAutoException, stock_auto_exception_handler)
    app.dependency_overrides[get_current_user] = lambda: StubUser()
    with TestClient(app) as test_client:
        yield test_client


def test_disallowed_command_type_is_rejected_with_standard_error(client):
    res = client.post("/api/v1/mcp/command", json={"command_type": "TRANSFER_ALL"})

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "MCP_COMMAND_NOT_ALLOWED"


def test_allowed_command_reports_not_implemented(client):
    res = client.post("/api/v1/mcp/command", json={"command_type": "CHANGE_STRATEGY"})

    # 실행하지 않으면서 200 QUEUED를 돌려주던 것이 이 슬라이스가 고친 거짓말이다.
    assert res.status_code == 501
    assert res.json()["error"]["code"] == "MCP_EXECUTION_NOT_IMPLEMENTED"


@pytest.mark.parametrize("confirm", [False, True])
def test_confirmed_buy_is_never_queued(client, fake_redis, confirm):
    """confirm 여부와 무관하게 주문이 적재되지 않는다.

    이 테스트가 안전 회귀 가드다. 실행 워커 없이 RPUSH만 되살리면 여기서 깨진다.
    """
    res = client.post(
        "/api/v1/mcp/command",
        json={"command_type": "BUY", "ticker": "AAPL", "quantity": 10, "confirm": confirm},
    )

    assert res.status_code == 501
    assert fake_redis.write_calls == []


def test_status_uses_standard_envelope_and_declares_no_worker(client, fake_redis):
    fake_redis.queue_length = 3  # 과거 구현이 남긴 잔여분

    res = client.get("/api/v1/mcp/status")

    assert res.status_code == 200
    body = res.json()
    assert body["code"] == "SUCCESS"
    assert body["data"] == {
        "user_id": StubUser.id,
        "pending_commands": 3,
        "worker_implemented": False,
    }


def test_status_reads_only_the_authenticated_users_queue(client, fake_redis):
    client.get("/api/v1/mcp/status")

    assert ("llen", f"{mcp_router.QUEUE_KEY_PREFIX}:{StubUser.id}") in fake_redis.calls
