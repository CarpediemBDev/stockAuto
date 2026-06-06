from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


def test_access_and_refresh_tokens_are_not_interchangeable():
    access_token = create_access_token(subject=123)
    refresh_token = create_refresh_token(subject=123)

    assert decode_access_token(access_token) == "123"
    assert decode_refresh_token(refresh_token) == "123"
    assert decode_access_token(refresh_token) is None
    assert decode_refresh_token(access_token) is None
