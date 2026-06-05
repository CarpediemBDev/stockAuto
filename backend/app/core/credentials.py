import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


ENCRYPTED_PREFIX = "enc:v1:"


class CredentialCryptoError(RuntimeError):
    """Raised when credential encryption or decryption cannot be completed."""


def _get_fernet() -> Fernet:
    key = os.getenv("KIS_CREDENTIAL_MASTER_KEY")
    if not key:
        raise CredentialCryptoError(
            "KIS_CREDENTIAL_MASTER_KEY 환경변수가 설정되어야 KIS 인증정보를 암호화 저장할 수 있습니다."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise CredentialCryptoError("KIS_CREDENTIAL_MASTER_KEY 값이 Fernet 키 형식이 아닙니다.") from exc


def is_encrypted_credential(value: Optional[str]) -> bool:
    return bool(value and value.startswith(ENCRYPTED_PREFIX))


def encrypt_credential(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if is_encrypted_credential(normalized):
        return normalized
    token = _get_fernet().encrypt(normalized.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_credential(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if not is_encrypted_credential(normalized):
        # Backward compatibility for existing plaintext values.
        return normalized
    token = normalized[len(ENCRYPTED_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialCryptoError("저장된 KIS 인증정보를 복호화할 수 없습니다.") from exc


def mask_credential(value: Optional[str], visible_prefix: int = 4, visible_suffix: int = 4) -> Optional[str]:
    decrypted = decrypt_credential(value)
    if not decrypted:
        return None
    if len(decrypted) <= visible_prefix + visible_suffix:
        return "*" * len(decrypted)
    return f"{decrypted[:visible_prefix]}...{decrypted[-visible_suffix:]}"
