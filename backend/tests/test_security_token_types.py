from app.core.security import (
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_access_token_claims,
    decode_refresh_token,
)
import jwt


def test_access_and_refresh_tokens_are_not_interchangeable():
    access_token = create_access_token(subject=123, token_version=7)
    refresh_token = create_refresh_token(subject=123)

    assert decode_access_token(access_token) == "123"
    assert decode_refresh_token(refresh_token) == "123"
    assert decode_access_token(refresh_token) is None
    assert decode_refresh_token(access_token) is None
    assert decode_access_token_claims(access_token)["ver"] == 7


def test_refresh_token_without_subject_is_rejected():
    token = jwt.encode(
        {"type": "refresh"},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    assert decode_refresh_token(token) is None
