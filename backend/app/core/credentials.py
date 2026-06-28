import os
from typing import Optional

from cryptography.fernet import Fernet, MultiFernet, InvalidToken


ENCRYPTED_PREFIX = "enc:v1:"


class CredentialCryptoError(RuntimeError):
    """Raised when credential encryption or decryption cannot be completed."""


def _get_fernet_instances() -> list[Fernet]:
    keys = []
    primary_key = os.getenv("KIS_CREDENTIAL_MASTER_KEY")
    if primary_key:
        keys.append(primary_key)
    
    old_key = os.getenv("OLD_KIS_CREDENTIAL_MASTER_KEY")
    if old_key:
        keys.append(old_key)

    if not keys:
        raise CredentialCryptoError(
            "KIS_CREDENTIAL_MASTER_KEY 환경변수가 설정되어야 KIS 인증정보를 암호화 저장할 수 있습니다."
        )

    fernet_list = []
    for k in keys:
        try:
            fernet_list.append(Fernet(k.encode("utf-8")))
        except Exception as exc:
            raise CredentialCryptoError("KIS_CREDENTIAL_MASTER_KEY 또는 OLD_KIS_CREDENTIAL_MASTER_KEY 값이 올바른 Fernet 키 형식이 아닙니다.") from exc
    return fernet_list


def _get_encryptor() -> Fernet:
    return _get_fernet_instances()[0]


def _get_decryptor() -> MultiFernet:
    return MultiFernet(_get_fernet_instances())


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
    token = _get_encryptor().encrypt(normalized.encode("utf-8")).decode("utf-8")
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
        return _get_decryptor().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialCryptoError("저장된 KIS 인증정보를 복호화할 수 없습니다.") from exc


def mask_credential(value: Optional[str], visible_prefix: int = 4, visible_suffix: int = 4) -> Optional[str]:
    decrypted = decrypt_credential(value)
    if not decrypted:
        return None
    if len(decrypted) <= visible_prefix + visible_suffix:
        return "*" * len(decrypted)
    return f"{decrypted[:visible_prefix]}...{decrypted[-visible_suffix:]}"
