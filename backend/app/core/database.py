import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# app/core/database.py의 위치를 기준으로 backend 루트 디렉터리에 있는 stockauto.db 경로를 절대 경로로 도출합니다.
core_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(core_dir)
backend_dir = os.path.dirname(app_dir)
db_path = os.path.join(backend_dir, "stockauto.db")

SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"


def set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
event.listen(engine, "connect", set_sqlite_pragma)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
