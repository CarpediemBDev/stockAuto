import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from app.main import app
import app.core.rate_limiter as rate_limiter_module

client = TestClient(app)


class FakeRedis:
    def __init__(self):
        self.counts = {}

    def eval(self, _script, _num_keys, key, _window_seconds):
        current = self.counts.get(key, 0) + 1
        self.counts[key] = current
        return current


class FailingRedis:
    def eval(self, *_args):
        raise OSError("redis unavailable")


@pytest.mark.real_rate_limiter
def test_rate_limiter_blocks_excessive_requests(monkeypatch):
    """
    로그인 API에 5번 초과 요청 시 429 에러가 반환되는지 확인
    """
    fake_redis = FakeRedis()
    monkeypatch.setattr(rate_limiter_module, "get_redis_client", lambda: fake_redis)
    # 1. 5번 정상 실패 (비밀번호 틀림 등 401 또는 400 반환)
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "dummy_user", "password": "wrongpassword123!"},
        )
        assert response.status_code in [400, 401, 404]

    # 2. 6번째 요청: 429 Too Many Requests 발생 확인
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "dummy_user", "password": "wrongpassword123!"},
    )
    assert response.status_code == 429
    assert "초과" in response.json()["detail"]


@pytest.mark.real_rate_limiter
def test_rate_limiter_ignores_spoofed_forwarded_ip_from_untrusted_client(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(rate_limiter_module, "get_redis_client", lambda: fake_redis)
    response = None
    for attempt in range(6):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "dummy_user", "password": "wrongpassword123!"},
            headers={"X-Forwarded-For": f"10.0.0.{attempt}"},
        )

    assert response is not None
    assert response.status_code == 429
    assert len(fake_redis.counts) == 2
    assert any(":username:" in key for key in fake_redis.counts)
    assert all("dummy_user" not in key for key in fake_redis.counts)
    assert any(":peer:testclient" in key for key in fake_redis.counts)


@pytest.mark.real_rate_limiter
def test_rate_limiter_uses_local_fallback_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(rate_limiter_module, "get_redis_client", lambda: FailingRedis())

    response = None
    for _ in range(6):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "dummy_user", "password": "wrongpassword123!"},
        )

    assert response is not None
    assert response.status_code == 429


def test_rate_limiter_fallback_storage_is_bounded(monkeypatch):
    limiter = rate_limiter_module.RateLimiter(max_requests=1, window_seconds=60)
    monkeypatch.setattr(rate_limiter_module, "_FALLBACK_MAX_KEYS", 3)
    monkeypatch.setattr(rate_limiter_module, "_FALLBACK_PRUNE_THRESHOLD", 1)

    for index in range(10):
        limiter._increment_fallback(f"key-{index}")

    assert len(limiter._fallback_windows) == 3


@pytest.mark.asyncio
@pytest.mark.real_rate_limiter
async def test_peer_limit_short_circuits_principal_key_creation(monkeypatch):
    fake_redis = FakeRedis()
    peer_key = "rate_limit:/api/v1/auth/login:peer:10.0.0.1"
    fake_redis.counts[peer_key] = 60
    monkeypatch.setattr(rate_limiter_module, "get_redis_client", lambda: fake_redis)
    body = b'{"username":"rotating-user","password":"secret"}'

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("10.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive,
    )
    limiter = rate_limiter_module.RateLimiter(
        max_requests=5,
        window_seconds=60,
        key_field="username",
        peer_max_requests=60,
    )

    with pytest.raises(Exception) as exc_info:
        await limiter(request)

    assert getattr(exc_info.value, "status_code", None) == 429
    assert set(fake_redis.counts) == {peer_key}
