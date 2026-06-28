#!/usr/bin/env python3
"""
StockAuto 시크릿 키 원클릭 자동 로테이션 스크립트 (rotate_master_key.py)

기능:
1. 지정된 환경(.env.local, .env.dev, .env.prod)에 대해 각각 독립된 최신 Fernet 마스터키를 무작위 생성합니다.
2. 기존 주키(KIS_CREDENTIAL_MASTER_KEY)를 보조 백업키(OLD_KIS_CREDENTIAL_MASTER_KEY)로 이동시킵니다.
3. 데이터베이스(broker_credentials 테이블) 내 모든 암호화 자격증명(app_key, app_secret, account_no)을
   구키로 복호화한 후 신규 키로 안전하게 재암호화(Re-encrypt)합니다.
4. .env 파일들을 안전하게 업데이트합니다.
"""

import argparse
import os
import sys
from pathlib import Path

# 프로젝트 루트 및 백엔드 경로 추가
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
backend_dir = project_root / "backend"
sys.path.insert(0, str(backend_dir))

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.credentials import ENCRYPTED_PREFIX, decrypt_credential, encrypt_credential
from app.core.models import BrokerCredential


def generate_new_fernet_key() -> str:
    return Fernet.generate_key().decode("utf-8")


def read_env_file(file_path: Path) -> dict[str, str]:
    if not file_path.exists():
        return {}
    env_vars = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()
    return env_vars


def update_env_file(file_path: Path, new_master_key: str, old_master_key: str | None):
    lines = []
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_master = False
    updated_old = False

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("KIS_CREDENTIAL_MASTER_KEY="):
            new_lines.append(f"KIS_CREDENTIAL_MASTER_KEY={new_master_key}\n")
            updated_master = True
        elif stripped.startswith("OLD_KIS_CREDENTIAL_MASTER_KEY="):
            if old_master_key:
                new_lines.append(f"OLD_KIS_CREDENTIAL_MASTER_KEY={old_master_key}\n")
            updated_old = True
        else:
            new_lines.append(line)

    if not updated_master:
        new_lines.append(f"\nKIS_CREDENTIAL_MASTER_KEY={new_master_key}\n")
    if not updated_old and old_master_key:
        new_lines.append(f"OLD_KIS_CREDENTIAL_MASTER_KEY={old_master_key}\n")

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def reencrypt_database(db_path: Path, old_key: str, new_key: str):
    if not db_path.exists():
        print(f"  [i] DB 파일이 존재하지 않아 재암호화를 건너뜁니다: {db_path}")
        return

    # 임시로 os.environ 설정하여 decrypt/encrypt 서비스 가동
    orig_master = os.environ.get("KIS_CREDENTIAL_MASTER_KEY")
    orig_old = os.environ.get("OLD_KIS_CREDENTIAL_MASTER_KEY")

    try:
        engine = create_engine(f"sqlite:///{db_path}")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        credentials = session.query(BrokerCredential).all()
        if not credentials:
            print(f"  [i] 재암호화할 자격증명이 없습니다: {db_path}")
            session.close()
            return

        print(f"  [*] {len(credentials)}개의 자격증명 항목 재암호화 진행 중...")
        reencrypted_count = 0

        for cred in credentials:
            # 구키로 복호화하기 위해 환경변수 세팅
            os.environ["KIS_CREDENTIAL_MASTER_KEY"] = old_key
            if orig_master and orig_master != old_key:
                os.environ["OLD_KIS_CREDENTIAL_MASTER_KEY"] = orig_master

            raw_app_key = decrypt_credential(cred.app_key) if cred.app_key else None
            raw_app_secret = decrypt_credential(cred.app_secret) if cred.app_secret else None
            raw_account_no = decrypt_credential(cred.account_no) if cred.account_no else None

            # 신키로 암호화하기 위해 환경변수 세팅
            os.environ["KIS_CREDENTIAL_MASTER_KEY"] = new_key
            os.environ["OLD_KIS_CREDENTIAL_MASTER_KEY"] = old_key

            if raw_app_key:
                # 강제 재암호화를 위해 prefix 제거 후 encrypt
                clean_val = raw_app_key
                token = Fernet(new_key.encode("utf-8")).encrypt(clean_val.encode("utf-8")).decode("utf-8")
                cred.app_key = f"{ENCRYPTED_PREFIX}{token}"

            if raw_app_secret:
                clean_val = raw_app_secret
                token = Fernet(new_key.encode("utf-8")).encrypt(clean_val.encode("utf-8")).decode("utf-8")
                cred.app_secret = f"{ENCRYPTED_PREFIX}{token}"

            if raw_account_no:
                clean_val = raw_account_no
                token = Fernet(new_key.encode("utf-8")).encrypt(clean_val.encode("utf-8")).decode("utf-8")
                cred.account_no = f"{ENCRYPTED_PREFIX}{token}"

            reencrypted_count += 1

        session.commit()
        session.close()
        print(f"  [✓] {reencrypted_count}개 자격증명 항목 재암호화 완료!")

    finally:
        if orig_master is not None:
            os.environ["KIS_CREDENTIAL_MASTER_KEY"] = orig_master
        elif "KIS_CREDENTIAL_MASTER_KEY" in os.environ:
            del os.environ["KIS_CREDENTIAL_MASTER_KEY"]

        if orig_old is not None:
            os.environ["OLD_KIS_CREDENTIAL_MASTER_KEY"] = orig_old
        elif "OLD_KIS_CREDENTIAL_MASTER_KEY" in os.environ:
            del os.environ["OLD_KIS_CREDENTIAL_MASTER_KEY"]


def rotate_environment(env_name: str):
    env_file_name = f".env.{env_name}"
    env_path = backend_dir / env_file_name

    print(f"\n==========================================")
    print(f"🔄 [{env_name.upper()}] 환경 키 로테이션 시작 ({env_file_name})")
    print(f"==========================================")

    current_env = read_env_file(env_path)
    old_master_key = current_env.get("KIS_CREDENTIAL_MASTER_KEY")
    new_master_key = generate_new_fernet_key()

    print(f"  - 신규 마스터키 생성 완료: {new_master_key[:8]}...{new_master_key[-4:]}")
    if old_master_key:
        print(f"  - 이전 마스터키 보존 예정: {old_master_key[:8]}...{old_master_key[-4:]}")
    else:
        print(f"  - 이전 마스터키 없음 (최초 생성)")

    # 1. DB 재암호화
    db_path = backend_dir / "stockauto.db"
    if old_master_key:
        reencrypt_database(db_path, old_master_key, new_master_key)

    # 2. .env 파일 업데이트
    update_env_file(env_path, new_master_key, old_master_key)
    print(f"  [✓] {env_file_name} 환경 변수 업데이트 완료!")


def main():
    parser = argparse.ArgumentParser(description="StockAuto 시크릿 키 자동 로테이션 도구")
    parser.add_argument(
        "--env",
        choices=["local", "dev", "prod", "all"],
        default="all",
        help="로테이션 대상 환경 선택 (기본값: all)",
    )
    args = parser.parse_args()

    print("🛡️ StockAuto 시크릿 마스터키 무중단 자동 로테이션 가동")

    if args.env == "all":
        targets = ["local", "dev", "prod"]
    else:
        targets = [args.env]

    for env in targets:
        rotate_environment(env)

    print("\n🎉 모든 지정 환경의 마스터키 로테이션 및 DB 재암호화가 성공적으로 완료되었습니다!")


if __name__ == "__main__":
    main()
