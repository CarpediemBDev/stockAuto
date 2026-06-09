import os
from sqlalchemy import inspect
from alembic.config import Config
from alembic import command

from app.core.database import engine
from app.core.logging import logger


def competitive_seed_enabled() -> bool:
    return os.getenv("SEED_COMPETITIVE_USERS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_migrations_programmatically():
    """Alembic 마이그레이션을 애플리케이션 시작 시 프로그램적으로 자동 실행하는 부트스트래퍼"""
    # migrator.py의 위치를 기준으로 backend 루트 디렉터리에 있는 alembic.ini 경로 도출
    core_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(core_dir)
    backend_dir = os.path.dirname(app_dir)
    ini_path = os.path.join(backend_dir, "alembic.ini")

    # Alembic 설정 객체 로드
    alembic_cfg = Config(ini_path)

    # DB 테이블 현황 검사
    inspector = inspect(engine)
    has_users = inspector.has_table("users")
    has_alembic = inspector.has_table("alembic_version")

    # 💡 [안전 조치] 기존에 존재하던 옛날 Alembic 버전 번호(e10797b8bd90)가 버전 테이블에 박혀 있는 경우 보정
    if has_alembic:
        from sqlalchemy import text
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            res = db.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            if res and res[0] == 'e10797b8bd90':
                logger.info("[Migration] 옛날 Alembic 버전('e10797b8bd90') 감지됨. 신규 표준 baseline('001_baseline')으로 버전 번호 자동 보정 중...")
                db.execute(text("UPDATE alembic_version SET version_num = '001_baseline'"))
                db.commit()
                logger.info("[Migration] Alembic 버전 번호 보정 완료.")
        except Exception as err:
            logger.warning(f"[Migration] Alembic 버전 번호 보정 시도 중 무시 가능한 경고 발생: {err}")
            db.rollback()
        finally:
            db.close()

    try:
        if has_users and not has_alembic:
            logger.info("[Migration] 기존 데이터베이스 감지됨 (Alembic 관리 상태 아님). 최신 버전으로 스탬핑(Stamp) 처리 중...")
            # 기존 DB의 경우 테이블 생성 단계를 건너뛰고 스키마가 최신(baseline) 상태라고 버전 테이블에 기록
            command.stamp(alembic_cfg, "head")
            logger.info("[Migration] 기존 데이터베이스 스탬핑 작업 완료 (head).")
        elif not has_users:
            logger.info("[Migration] 신규/비어있는 데이터베이스 감지됨. alembic upgrade head 실행하여 모든 테이블 생성 중...")
            # 신규 DB의 경우 모든 마이그레이션을 처음부터 순서대로 실행해 테이블 전체 생성
            command.upgrade(alembic_cfg, "head")
            logger.info("[Migration] 신규 데이터베이스 테이블 생성 완료.")
        else:
            logger.info("[Migration] Alembic 관리 데이터베이스 감지됨. alembic upgrade head 실행하여 신규 변경사항 체크 중...")
            # 이미 Alembic으로 관리되고 있는 경우 새로운 마이그레이션이 있으면 자동 업데이트 적용
            command.upgrade(alembic_cfg, "head")
            logger.info("[Migration] 데이터베이스 변경사항 체크 및 업그레이드 완료.")

        if competitive_seed_enabled():
            seed_competitive_users()
        else:
            logger.info("[Seeder] 경쟁용 사용자 자동 생성을 건너뜁니다.")

    except Exception as e:
        logger.error(f"[Migration] 마이그레이션 중 오류 발생: {e}", exc_info=True)
        raise e

def seed_competitive_users():
    """대결 참가용 5대 경쟁 어드민 유저 자동 Seeding"""
    from app.core.database import SessionLocal
    from app.core.models import User, UserSettings
    from app.core.security import get_password_hash

    db = SessionLocal()
    try:
        import secrets

        # 복잡한 환경 변수 및 난수 분기 로직을 전면 제거하고 기본값 'admin'을 직접 해싱
        logger.info("[Seeder] 경쟁용 사용자 및 관리자 비밀번호를 'admin'으로 자동 설정합니다.")
        hashed_pw_admin = get_password_hash("admin")
        hashed_pw_others = get_password_hash("admin")

        competitors = [
            {"username": "admin", "strategy": "regime_switching"},
            {"username": "admin2", "strategy": "senior_simple"},
            {"username": "admin3", "strategy": "episodic_pivot"},
            {"username": "admin4", "strategy": "qullamaggie"},
            {"username": "admin5", "strategy": "obv_only"},
            {"username": "admin6", "strategy": "multi_slot"},
            {"username": "admin7", "strategy": "three_slot"},
            {"username": "admin8", "strategy": "asqs"},
            {"username": "admin9", "strategy": "bb_squeeze"},
            {"username": "admin10", "strategy": "rsi2_connors"},
        ]

        for comp in competitors:
            # 유저 존재 여부 검사
            existing_user = db.query(User).filter(User.username == comp["username"]).first()
            if not existing_user:
                logger.info(f"[Seeder] 신규 유저 생성 중: {comp['username']} (전략: {comp['strategy']})")

                is_admin = (comp["username"] == "admin")
                hashed_pw = hashed_pw_admin if is_admin else hashed_pw_others
                user_role = "ADMIN" if is_admin else "USER"

                new_user = User(username=comp["username"], hashed_password=hashed_pw, role=user_role)
                db.add(new_user)
                db.commit()
                db.refresh(new_user)

                # 시딩 계정도 명시적으로 시작하기 전까지 자동매매를 정지 상태로 둡니다.
                new_settings = UserSettings(
                    user_id=new_user.id,
                    strategy_type=comp["strategy"],
                    trade_mode="SIMULATED",
                    is_running=False,
                )
                db.add(new_settings)
                db.commit()
                logger.info(f"[Seeder] 경쟁 유저 {comp['username']} 세팅 완료.")
            else:
                # 이미 존재하더라도 설정 확인 및 업데이트
                settings = existing_user.settings
                if not settings:
                    settings = UserSettings(
                        user_id=existing_user.id,
                        strategy_type=comp["strategy"],
                        trade_mode="SIMULATED",
                        is_running=False,
                    )
                    db.add(settings)
                    db.commit()

    except Exception as seed_err:
        logger.error(f"[Seeder] 데이터베이스 시딩 실패: {seed_err}")
        db.rollback()
    finally:
        db.close()
