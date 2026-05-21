from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.database import engine, Base
from app.core.exceptions import StockAutoException, stock_auto_exception_handler
from app.translations.translator import Translator
from app.bot.scheduler import start_scheduler
from app.core.models import SystemSettings
from app.core.config import settings
from app.core.database import SessionLocal

# 💡 모듈형 아키텍처 라우터 전격 임포트
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Caching & Seeding Stock Translations
    print("Backend Lifespan Starting: Initializing Stock Translator Cache...")
    Translator.load_cache()
    
    # 💡 Admin Settings Override (DB -> Memory)
    print("Backend Lifespan: Loading Admin Settings from DB...")
    db = SessionLocal()
    try:
        db_settings = db.query(SystemSettings).first()
        if db_settings:
            settings.TRADE_MODE = db_settings.trade_mode
            settings.IS_SIMULATED = db_settings.trade_mode == "SIMULATED"
            settings.IS_MOCK = db_settings.trade_mode == "MOCK"
            settings.IS_REAL = db_settings.trade_mode == "REAL"
            settings.BROKER_PROVIDER = db_settings.broker_provider
            settings.KIS_APP_KEY = db_settings.kis_app_key
            settings.KIS_APP_SECRET = db_settings.kis_app_secret
            settings.KIS_ACCOUNT_NO = db_settings.kis_account_no
            
            if settings.IS_REAL:
                settings.KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
                settings.TR_ID_BALANCE = "TTTC8434R"
                settings.TR_ID_BUY_OVERSEAS = "JTTT1002U"
                settings.TR_ID_SELL_OVERSEAS = "JTTT1001U"
                settings.TR_ID_OVERSEAS_BALANCE = "CTRP6504R"
                settings.TR_ID_ORDER_HISTORY = "JTTT3010R"
            else:
                settings.KIS_BASE_URL = "https://vts-openapi.koreainvestment.com:29443"
                settings.TR_ID_BALANCE = "VTTC8434R"
                settings.TR_ID_BUY_OVERSEAS = "VTTT1002U"
                settings.TR_ID_SELL_OVERSEAS = "VTTT1001U"
                settings.TR_ID_OVERSEAS_BALANCE = "VTRP6504R"
                settings.TR_ID_ORDER_HISTORY = "VTTS3010R"
            print(f"[*] Admin Settings Applied: Mode={settings.TRADE_MODE}")
    finally:
        db.close()
    
    # Start the background trading loop scheduler
    print("Backend Lifespan: Initializing Scheduler...")
    start_scheduler()
    yield
    print("Backend Lifespan Ending...")

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
