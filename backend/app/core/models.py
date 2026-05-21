from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from datetime import datetime
from app.core.database import Base

class BotStatus(Base):
    __tablename__ = "bot_status"

    id = Column(Integer, primary_key=True, index=True)
    is_running = Column(Boolean, default=False)
    is_real_enabled = Column(Boolean, default=False) # 실전 매매 안전 스위치
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TradeLog(Base):
    __tablename__ = "trade_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    ticker_name = Column(String)
    trade_type = Column(String) # 'BUY' or 'SELL'
    price = Column(Float) # 해외주식 소수점 대응
    quantity = Column(Integer)
    order_no = Column(String, nullable=True) # KIS 주문번호 (ODNO)
    executed_at = Column(DateTime, default=datetime.utcnow)

class Holding(Base):
    """현재 보유 중인 종목 상태 (트레일링 스탑용)"""
    __tablename__ = "holdings"
    
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True, unique=True)
    ticker_name = Column(String)
    avg_price = Column(Float)   # 평단가
    quantity = Column(Integer)  # 보유수량
    highest_price = Column(Float) # 구매 후 최고가 (트레일링 스탑 기준점)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ActionLog(Base):
    """봇의 실시간 활동 기록 (스캔, 판단, 시스템 메시지 등)"""
    __tablename__ = "action_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String, default="INFO") # INFO, WARN, ERROR, SIGNAL
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class WatchList(Base):
    __tablename__ = "watch_lists"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, index=True) # 중복 등록 방지
    ticker_name = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)

class StockTranslation(Base):
    __tablename__ = "stock_translations"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, index=True)
    name_ko = Column(String, nullable=False)

class SystemSettings(Base):
    """
    어드민 설정 대시보드 전용 글로벌 시스템 설정 (Phase 10).
    .env 파일보다 우선하여 런타임에 핫 리로드 적용됩니다.
    """
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    trade_mode = Column(String, default="SIMULATED") # SIMULATED, MOCK, REAL
    broker_provider = Column(String, default="KIS")
    kis_app_key = Column(String, nullable=True)
    kis_app_secret = Column(String, nullable=True)
    kis_account_no = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
