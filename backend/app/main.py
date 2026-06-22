from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.exceptions import StockAutoException, stock_auto_exception_handler
from app.core.config import get_allowed_origins
from app.translations.translator import Translator
from app.bot.scheduler import start_scheduler
from app.bot.order_discovery import discover_orphan_orders_once
from app.bot.order_reconciler import reconcile_open_orders_once
from app.core.logging import logger
from app.core.redis_client import close_redis_client, ping_redis

# 💡 모듈형 아키텍처 라우터 전격 임포트
from app.auth.router import router as auth_router
from app.bot.router import router as bot_router
from app.trades.router_trades import router as trades_router
from app.trades.router_account import router as account_router
from app.scanner.router import router as scanner_router
from app.watchlist.router import router as watchlist_router
from app.trades.router_market import router as market_router
from app.translations.router import router as translations_router
from app.admin.router import router as admin_router
from app.report.router import router as report_router
from app.bot.router_backtest import router as backtest_router

# 💡 Alembic 프로그램 기반 자동 마이그레이션 실행 (스프링부트 Flyway 방식 이식)
from app.core.migrator import run_migrations_programmatically

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Backend Lifespan Starting: Applying database migrations...")
    run_migrations_programmatically()

    # Startup Caching & Seeding Stock Translations
    logger.info("Backend Lifespan Starting: Initializing Stock Translator Cache...")
    Translator.load_cache()

    logger.info("Backend Lifespan Starting: Recovering unresolved broker orders...")
    discover_orphan_orders_once()
    reconcile_open_orders_once()

    if await ping_redis():
        logger.info("Backend Lifespan: Redis order-lock service is ready")
    else:
        logger.critical(
            "Backend Lifespan: Redis is unavailable. The API remains online, "
            "but trading orders will fail closed."
        )

    # Start the background trading loop scheduler
    logger.info("Backend Lifespan: Initializing Scheduler...")
    start_scheduler()

    # 💡 Telegram Polling Daemon Startup (Phase 11)
    from app.core.telegram import start_telegram_bot, stop_telegram_bot
    logger.info("Backend Lifespan: Starting Telegram Bot...")
    start_telegram_bot()

    yield

    logger.info("=" * 50)
    logger.info("[Shutdown Step 1/4] 텔레그램 봇 폴링 통신 채널 안전 종료 중...")
    stop_telegram_bot()

    logger.info("[Shutdown Step 2/4] 자동매매 스케줄러 및 크롤링 프로세스 중지 중...")
    from app.bot.scheduler import stop_scheduler
    stop_scheduler()

    logger.info("[Shutdown Step 3/4] Redis 주문 락 클라이언트 종료 중...")
    await close_redis_client()

    logger.info("[Shutdown Step 4/4] FastAPI 서버 자원(DB 커넥션 등) 해제 완료 대기...")
    logger.info("=" * 50)
    logger.info("✅ 안전 종료 프로세스가 완료되었습니다. (모든 자원 반환 완료)")

app = FastAPI(title="StockAuto API", description="주식 자동매매 API 서버", lifespan=lifespan)

# 전역 예외 핸들러 등록
app.add_exception_handler(StockAutoException, stock_auto_exception_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(
        "Unhandled request error: %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "서버 내부 오류가 발생했습니다."
            }
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)

# 💡 API 라우터 바인딩
app.include_router(auth_router, prefix="/api/v1/auth", tags=["User Auth"])
app.include_router(bot_router, prefix="/api/v1/bot", tags=["Bot Control"])
app.include_router(trades_router, prefix="/api/v1/trades", tags=["Trade Logs"])
app.include_router(account_router, prefix="/api/v1/account", tags=["Account Balance"])
app.include_router(scanner_router, prefix="/api/v1/scanner", tags=["Market Scanner"])
app.include_router(watchlist_router, prefix="/api/v1/watchlist", tags=["Watch List"])
app.include_router(market_router, prefix="/api/v1/market", tags=["Market Data"])
app.include_router(translations_router, prefix="/api/v1/translations", tags=["System Translations"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin System"])
app.include_router(report_router, prefix="/api/v1/report", tags=["Trading Report"])
app.include_router(backtest_router, prefix="/api/v1/backtest", tags=["Backtest"])

@app.get("/")
def read_root():
    # Trigger reload to refresh translation cache dynamically
    return {"message": "StockAuto FastAPI Server is running in Modular Layered Architecture!"}
