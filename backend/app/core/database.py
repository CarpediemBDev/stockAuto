import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool
from app.core.config import APP_ENV

# app/core/database.py의 위치를 기준으로 backend 루트 디렉터리에 있는 stockauto.db 경로를 절대 경로로 도출합니다.
core_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(core_dir)
backend_dir = os.path.dirname(app_dir)
db_path = os.path.join(backend_dir, "stockauto.db")


def _default_sqlite_url() -> str:
    return f"sqlite:///{db_path}"


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite:")


def _resolve_database_url() -> str:
    configured_url = os.getenv("DATABASE_URL", "").strip()
    if APP_ENV == "prod":
        if not configured_url:
            raise RuntimeError("DATABASE_URL is required when APP_ENV=prod.")
        if _is_sqlite_url(configured_url):
            raise RuntimeError("SQLite DATABASE_URL is not allowed when APP_ENV=prod.")
        return configured_url
    return configured_url or _default_sqlite_url()


SQLALCHEMY_DATABASE_URL = _resolve_database_url()
IS_SQLITE_DATABASE = _is_sqlite_url(SQLALCHEMY_DATABASE_URL)


def set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL") # WAL 모드 추가 (동시성 향상)
    finally:
        cursor.close()


if IS_SQLITE_DATABASE:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=QueuePool,
        pool_size=50,
        max_overflow=100,
        pool_timeout=60,
    )
    event.listen(engine, "connect", set_sqlite_pragma)
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
