import time
import psutil
import shutil
from pathlib import Path
from fastapi import APIRouter
from sqlalchemy import text
from app.core.database import SessionLocal, IS_SQLITE_DATABASE
from app.core.redis_client import ping_redis
# ⚠️ 모듈 자체를 임포트한다. `from ... import is_processing`로 값을 복사하면
# 임포트 시점의 False에 고정되어 매매 루프 실시간 상태를 반영하지 못한다.
from app.bot import scheduler as scheduler_module

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute)

# 앱이 실제로 구동되는 파일시스템(드라이브 루트)을 대상으로 디스크 사용량을 측정.
# Windows("C:\\")/Linux("/") 모두에서 올바른 경로를 얻기 위해 anchor를 사용한다.
_APP_DISK_PATH = Path(__file__).resolve().anchor or "/"

@router.get("/health/core")
async def health_core():
    """
    Core 인프라 헬스체크: Redis, Database, System Resources (Disk, Memory)
    빠른 응답(0.1s 이내)을 보장합니다.
    """
    # 1. Redis Check
    redis_start = time.time()
    redis_ok = await ping_redis()
    redis_latency_ms = int((time.time() - redis_start) * 1000)

    # 2. Database Check
    db_ok = False
    db_latency_ms = 0
    db = SessionLocal()
    try:
        db_start = time.time()
        db.execute(text("SELECT 1"))
        db_latency_ms = int((time.time() - db_start) * 1000)
        db_ok = True
    except Exception:
        pass
    finally:
        db.close()

    # 3. System Resources
    memory = psutil.virtual_memory()
    mem_usage_percent = memory.percent
    
    disk = shutil.disk_usage(_APP_DISK_PATH)
    disk_usage_percent = (disk.used / disk.total) * 100

    return {
        "redis": {
            "status": "connected" if redis_ok else "disconnected",
            "latency_ms": redis_latency_ms
        },
        "database": {
            "status": "connected" if db_ok else "disconnected",
            "latency_ms": db_latency_ms,
            "type": "sqlite" if IS_SQLITE_DATABASE else "postgresql"
        },
        "resources": {
            "memory_usage_percent": round(mem_usage_percent, 1),
            "disk_usage_percent": round(disk_usage_percent, 1),
            "memory_warning": mem_usage_percent > 90,
            "disk_warning": disk_usage_percent > 90
        }
    }

@router.get("/health/bot")
async def health_bot():
    """
    스케줄러(봇) 상태 헬스체크
    """
    return {
        "scheduler": {
            "is_running": scheduler_module.scheduler.running,
            "jobs_count": len(scheduler_module.scheduler.get_jobs()),
        },
        "trading_loop": {
            # 모듈 속성으로 접근해야 global 재대입된 최신 값이 반영된다.
            "is_processing": scheduler_module.is_processing
        }
    }

@router.get("/health/brokers")
async def health_brokers():
    """
    외부 증권사 API 상태 헬스체크 (응답 지연 가능성 있음).

    ⚠️ 아직 실제 브로커 서버 핑을 구현하지 않았다. 죽은 브로커를 "connected"로
    오보하면 관제가 오히려 위험해지므로, 구현 전까지는 상태를 조작하지 않고
    `not_implemented`로 정직하게 노출한다. 프론트는 이 값을 '미구현/미확인'으로 표시한다.
    """
    _not_implemented = {
        "status": "not_implemented",
        "latency_ms": None,
        "rate_limit_warning": False,
    }
    return {
        "kis": dict(_not_implemented),
        "toss": dict(_not_implemented),
    }
