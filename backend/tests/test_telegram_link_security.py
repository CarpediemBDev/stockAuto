"""텔레그램 연동 딥링크의 계정 탈취 방어 회귀 테스트.

배경 결함 — 과거 `_process_global_message`는 `/start <사용자명>`을 받아 소유권 증명 없이
chat_id를 그 계정에 묶었다. 전역 봇은 아무 텔레그램 사용자의 메시지나 수신하므로,
피해자의 사용자명만 알면 (a) 피해자 포트폴리오를 /status로 조회하고 (b) /run·/stop으로
실거래 자동매매 루프를 켜고 끌 수 있었다. 사용자명은 비밀이 아니므로 인증 수단이 될 수 없다.

여기서는 사용자명 경로가 완전히 죽었는지, 그리고 대체 수단인 1회용·만료형 토큰이
1회성/만료/격리를 실제로 지키는지를 검증한다.
"""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.telegram as telegram_mod
from app.core.database import Base
from app.core.models import User, UserSettings, utc_now_aware
from app.core.security import hash_telegram_link_token
from app.core.telegram import (
    consume_telegram_link_token,
    issue_telegram_link_token,
)

VICTIM_CHAT_ID = "111111111"
ATTACKER_CHAT_ID = "999999999"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_user(db, username: str, chat_id: str | None = None) -> User:
    user = User(username=username, hashed_password="x")
    db.add(user)
    db.flush()
    db.add(
        UserSettings(
            user_id=user.id,
            telegram_chat_id=chat_id,
            telegram_enabled=bool(chat_id),
        )
    )
    db.commit()
    return user


def _settings_of(db, user_id: int) -> UserSettings:
    return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()


@pytest.fixture
def captured_direct_messages(monkeypatch):
    """_send_direct_message를 가로채 봇이 실제로 무엇을 회신했는지 관찰한다."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        telegram_mod,
        "_send_direct_message",
        lambda chat_id, text: sent.append((chat_id, text)) or True,
    )
    return sent


@pytest.fixture
def bind_session(db, monkeypatch):
    """_process_global_message가 여는 SessionLocal을 테스트 세션으로 고정한다."""
    monkeypatch.setattr(telegram_mod, "SessionLocal", lambda: db)
    # 테스트 세션을 핸들러가 닫아버리면 후속 검증이 불가하므로 close만 무력화한다.
    monkeypatch.setattr(db, "close", lambda: None)
    return db


class TestUsernamePathIsDead:
    """사용자명 기반 연동 경로가 남아 있지 않은지 확인한다(원 결함의 직접 재현)."""

    def test_start_with_victim_username_does_not_link(
        self, db, bind_session, captured_direct_messages
    ):
        victim = _make_user(db, "victim", chat_id=VICTIM_CHAT_ID)

        telegram_mod._process_global_message(ATTACKER_CHAT_ID, "/start victim")

        settings = _settings_of(db, victim.id)
        assert settings.telegram_chat_id == VICTIM_CHAT_ID, (
            "공격자 chat_id가 피해자 계정에 바인딩됐다 — 계정 탈취 결함이 되살아남"
        )
        assert settings.telegram_enabled is True
        assert captured_direct_messages, "거부 안내를 회신해야 한다"
        assert captured_direct_messages[0][0] == ATTACKER_CHAT_ID

    def test_start_with_username_does_not_create_settings_row(
        self, db, bind_session, captured_direct_messages
    ):
        """미연동 계정도 사용자명만으로는 새 연동이 생기지 않아야 한다."""
        victim = _make_user(db, "fresh_victim", chat_id=None)

        telegram_mod._process_global_message(ATTACKER_CHAT_ID, "/start fresh_victim")

        settings = _settings_of(db, victim.id)
        assert not settings.telegram_chat_id
        assert settings.telegram_enabled is False


class TestLinkTokenLifecycle:
    def test_valid_token_links_the_issuing_account_only(
        self, db, bind_session, captured_direct_messages
    ):
        owner = _make_user(db, "owner", chat_id=None)
        bystander = _make_user(db, "bystander", chat_id=None)

        token, _expires_at = issue_telegram_link_token(db, owner.id)
        db.commit()

        telegram_mod._process_global_message(ATTACKER_CHAT_ID, f"/start {token}")

        assert _settings_of(db, owner.id).telegram_chat_id == ATTACKER_CHAT_ID
        assert _settings_of(db, owner.id).telegram_enabled is True
        # 토큰을 발급하지 않은 제3자 계정은 아무 영향을 받지 않는다.
        assert not _settings_of(db, bystander.id).telegram_chat_id

    def test_token_is_single_use(self, db, bind_session, captured_direct_messages):
        owner = _make_user(db, "owner", chat_id=None)
        token, _ = issue_telegram_link_token(db, owner.id)
        db.commit()

        telegram_mod._process_global_message(VICTIM_CHAT_ID, f"/start {token}")
        assert _settings_of(db, owner.id).telegram_chat_id == VICTIM_CHAT_ID

        # 같은 토큰 재사용(채팅 기록·링크 유출 시나리오)은 거부돼야 한다.
        telegram_mod._process_global_message(ATTACKER_CHAT_ID, f"/start {token}")
        assert _settings_of(db, owner.id).telegram_chat_id == VICTIM_CHAT_ID, (
            "이미 사용된 토큰으로 재연동이 됐다 — 1회성이 깨짐"
        )

    def test_expired_token_is_rejected(self, db, bind_session, captured_direct_messages):
        owner = _make_user(db, "owner", chat_id=None)
        token, _ = issue_telegram_link_token(db, owner.id)
        settings = _settings_of(db, owner.id)
        settings.telegram_link_token_expires_at = utc_now_aware() - timedelta(seconds=1)
        db.commit()

        telegram_mod._process_global_message(ATTACKER_CHAT_ID, f"/start {token}")

        assert not _settings_of(db, owner.id).telegram_chat_id

    def test_reissue_invalidates_previous_token(self, db):
        owner = _make_user(db, "owner", chat_id=None)
        first_token, _ = issue_telegram_link_token(db, owner.id)
        db.commit()
        issue_telegram_link_token(db, owner.id)
        db.commit()

        assert consume_telegram_link_token(db, first_token) is None

    def test_token_is_stored_only_as_hash(self, db):
        owner = _make_user(db, "owner", chat_id=None)
        token, expires_at = issue_telegram_link_token(db, owner.id)
        db.commit()

        settings = _settings_of(db, owner.id)
        assert settings.telegram_link_token_hash != token
        assert settings.telegram_link_token_hash == hash_telegram_link_token(token)
        assert expires_at > utc_now_aware()

    @pytest.mark.parametrize("bad_token", ["", "   ", "not-a-real-token", "victim"])
    def test_garbage_tokens_are_rejected(self, db, bad_token):
        _make_user(db, "owner", chat_id=None)
        assert consume_telegram_link_token(db, bad_token) is None


class TestLinkTokenEndpoint:
    """발급 엔드포인트 → 봇 소비까지의 실제 HTTP 경로를 한 번 관통시킨다."""

    def _client(self, db, user: User):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.admin.router import router as admin_router
        from app.core.database import get_db
        from app.core.dependencies import get_current_user

        app = FastAPI()
        app.include_router(admin_router, prefix="/api/v1/admin")
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    def test_issued_deep_link_links_only_the_authenticated_account(
        self, db, bind_session, captured_direct_messages
    ):
        owner = _make_user(db, "owner", chat_id=None)
        victim = _make_user(db, "victim", chat_id=VICTIM_CHAT_ID)

        res = self._client(db, owner).post("/api/v1/admin/telegram/link-token")
        assert res.status_code == 200
        payload = res.json()
        payload = payload.get("data", payload)

        deep_link = payload["deep_link"]
        assert "?start=" in deep_link
        token = deep_link.split("?start=", 1)[1]
        # 딥링크 페이로드는 사용자명이 아니라 DB 지문과 대응하는 난수여야 한다(과거 결함의 형태 배제).
        assert token != owner.username
        assert _settings_of(db, owner.id).telegram_link_token_hash == hash_telegram_link_token(token)

        telegram_mod._process_global_message(ATTACKER_CHAT_ID, f"/start {token}")

        assert _settings_of(db, owner.id).telegram_chat_id == ATTACKER_CHAT_ID
        assert _settings_of(db, victim.id).telegram_chat_id == VICTIM_CHAT_ID

    def test_manual_chat_id_cannot_steal_another_accounts_binding(self, db):
        from app.admin.router import SettingsUpdateSchema, update_user_settings
        from fastapi import HTTPException

        _make_user(db, "victim", chat_id=VICTIM_CHAT_ID)
        attacker = _make_user(db, "attacker", chat_id=None)

        payload = SettingsUpdateSchema(
            trade_mode="SIMULATED",
            telegram_chat_id=VICTIM_CHAT_ID,
            telegram_enabled=True,
        )
        with pytest.raises(HTTPException) as exc:
            update_user_settings(payload, current_user=attacker, db=db)
        assert exc.value.status_code == 409


class TestChatIdOwnershipIsExclusive:
    def test_relink_clears_previous_owner_of_same_chat_id(
        self, db, bind_session, captured_direct_messages
    ):
        """1:1 매핑 보장 — 같은 chat_id를 쓰던 이전 계정 연동은 해제된다."""
        previous = _make_user(db, "previous", chat_id=ATTACKER_CHAT_ID)
        new_owner = _make_user(db, "new_owner", chat_id=None)

        token, _ = issue_telegram_link_token(db, new_owner.id)
        db.commit()
        telegram_mod._process_global_message(ATTACKER_CHAT_ID, f"/start {token}")

        assert _settings_of(db, new_owner.id).telegram_chat_id == ATTACKER_CHAT_ID
        assert not _settings_of(db, previous.id).telegram_chat_id
        assert _settings_of(db, previous.id).telegram_enabled is False
