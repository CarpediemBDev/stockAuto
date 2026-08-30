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

    assert len(rate_limiter_module._global_fallback_windows) == 3


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


@pytest.mark.real_rate_limiter
def test_signup_rate_limiter_blocks_excessive_requests(monkeypatch):
    """
    회원가입(/signup) API에 동일 username으로 10번 초과 요청 시 429 Too Many Requests가 반환되는지 확인
    """
    fake_redis = FakeRedis()
    monkeypatch.setattr(rate_limiter_module, "get_redis_client", lambda: fake_redis)

    for _ in range(10):
        response = client.post(
            "/api/v1/auth/signup",
            json={"username": "target_signup_user", "password": "Password123456!"},
        )
        assert response.status_code in [200, 201, 400]

    # 11번째 요청: 429 Too Many Requests 차단 확인
    response = client.post(
        "/api/v1/auth/signup",
        json={"username": "target_signup_user", "password": "Password123456!"},
    )
    assert response.status_code == 429


def test_auth_cookie_request_blocked_on_cross_site():
    """
    Sec-Fetch-Site가 cross-site인 경우 403 Forbidden으로 차단되는지 확인
    """
    # per-request cookies=는 starlette TestClient에서 폐기 예정(쿠키 지속 동작이 모호).
    # 클라이언트 인스턴스에 직접 설정하고, 다른 테스트로 새지 않도록 반드시 되돌린다.
    client.cookies.set("refresh_token", "some_dummy_token")
    try:
        response = client.post(
            "/api/v1/auth/refresh",
            headers={"sec-fetch-site": "cross-site"},
        )
    finally:
        client.cookies.clear()
    assert response.status_code == 403



@pytest.mark.real_rate_limiter
def test_login_ip_limit_is_decoupled_from_the_per_username_limit(monkeypatch):
    """로그인은 사용자당 5회지만 IP당으로는 그보다 많이 허용해야 한다.

    peer_max_requests를 주지 않으면 IP 한도가 max_requests와 같아진다. 그러면 공용 IP
    하나(가정, 사무실, NAT) 뒤의 여러 사용자가 서로의 시도를 잠가버린다 - 다섯 번이면
    그 IP 전체가 1분간 로그인 불가다. 브루트포스 방어는 계정 단위로 성립해야 하고
    IP 단위 상한은 그보다 넉넉해야 한다.

    이 테스트는 라우터의 배선(peer_max_requests=30)을 고정한다. 값을 빼면 서로 다른
    사용자명 6명째부터 막히므로 반드시 깨진다.
    """
    fake_redis = FakeRedis()
    monkeypatch.setattr(rate_limiter_module, "get_redis_client", lambda: fake_redis)

    # 서로 다른 사용자명 10명이 같은 IP에서 각 1회씩 시도해도 막히지 않는다.
    for index in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": f"peer_user_{index}", "password": "wrongpassword123!"},
        )
        assert response.status_code != 429, (
            f"{index + 1}번째 사용자에서 IP 한도에 걸렸다. "
            "로그인 라우터의 peer_max_requests 배선을 확인할 것"
        )

    # 그러나 한 사용자명에 대한 상한은 그대로 5회다.
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"username": "peer_user_0", "password": "wrongpassword123!"},
        )
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "peer_user_0", "password": "wrongpassword123!"},
    )
    assert response.status_code == 429, "사용자당 브루트포스 방어가 느슨해졌다"
