import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.credentials import decrypt_credential, encrypt_credential
from scripts.rotate_master_key import rotate_environment


def test_multi_fernet_decryption_fallback(monkeypatch):
    primary_key = Fernet.generate_key().decode("utf-8")
    old_key = Fernet.generate_key().decode("utf-8")

    # 1. Old key로 암호화한 토큰 생성
    token_old = Fernet(old_key.encode("utf-8")).encrypt(b"secret_account_123").decode("utf-8")
    encrypted_val = f"enc:v1:{token_old}"

    # 2. 주키와 보조키를 환경변수에 설정
    monkeypatch.setenv("KIS_CREDENTIAL_MASTER_KEY", primary_key)
    monkeypatch.setenv("OLD_KIS_CREDENTIAL_MASTER_KEY", old_key)

    # 3. 주키로 먼저 복호화 시도 후 실패 시 보조키로 복호화 성공 검증
    decrypted = decrypt_credential(encrypted_val)
    assert decrypted == "secret_account_123"

    # 4. 새로운 암호화는 항상 주키로 진행되는지 검증
    new_encrypted = encrypt_credential("new_secret_456")
    token_new = new_encrypted.replace("enc:v1:", "")
    decrypted_new = Fernet(primary_key.encode("utf-8")).decrypt(token_new.encode("utf-8")).decode("utf-8")
    assert decrypted_new == "new_secret_456"
