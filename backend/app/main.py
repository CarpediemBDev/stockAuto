from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.database import engine, Base
from app.core.exceptions import StockAutoException, stock_auto_exception_handler
from app.translations.translator import Translator
from app.bot.scheduler import start_scheduler
from app.core.config import settings
from app.core.database import SessionLocal

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

# Create SQLite tables in core engine database
Base.metadata.create_all(bind=engine)

# 💡 SQLite 자동 스키마 마이그레이션 (v2.0 신규 컬럼 강제 추가)
def migrate_db_columns():
    from sqlalchemy import text
    db = SessionLocal()
    try:
        # trade_logs 테이블에 regime_mode, signal_score 추가
        for col_name, col_type in [("regime_mode", "VARCHAR"), ("signal_score", "INTEGER")]:
            try:
                db.execute(text(f"ALTER TABLE trade_logs ADD COLUMN {col_name} {col_type}"))
                db.commit()
                print(f"[Migration] Column {col_name} successfully added to trade_logs table.")
            except Exception:
                db.rollback()
                
        # holdings 테이블에 regime_mode, buy_stage 추가
        for col_name, col_type in [("regime_mode", "VARCHAR"), ("buy_stage", "INTEGER DEFAULT 1")]:
            try:
                db.execute(text(f"ALTER TABLE holdings ADD COLUMN {col_name} {col_type}"))
                db.commit()
                print(f"[Migration] Column {col_name} successfully added to holdings table.")
            except Exception:
                db.rollback()
    finally:
        db.close()

migrate_db_columns()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Caching & Seeding Stock Translations
    print("Backend Lifespan Starting: Initializing Stock Translator Cache...")
    Translator.load_cache()
    
    # Start the background trading loop scheduler
    print("Backend Lifespan: Initializing Scheduler...")
    start_scheduler()
    
    # 💡 Telegram Polling Daemon Startup (Phase 11)
    from app.core.telegram import start_telegram_bot, stop_telegram_bot
    print("Backend Lifespan: Starting Telegram Bot...")
    start_telegram_bot()
    
    yield
    
    print("Backend Lifespan Ending: Stopping Telegram Bot...")
    stop_telegram_bot()

app = FastAPI(title="StockAuto API", description="주식 자동매매 API 서버", lifespan=lifespan)

# 전역 예외 핸들러 등록
app.add_exception_handler(StockAutoException, stock_auto_exception_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "traceback": traceback.format_exc() if not isinstance(exc, StockAutoException) else None
            }
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get("/")
def read_root():
    # Trigger reload to refresh translation cache dynamically
    return {"message": "StockAuto FastAPI Server is running in Modular Layered Architecture!"}
