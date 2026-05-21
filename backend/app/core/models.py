from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    holdings = relationship("Holding", back_populates="user", cascade="all, delete-orphan")
    trade_logs = relationship("TradeLog", back_populates="user", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", back_populates="user", cascade="all, delete-orphan")
    watch_lists = relationship("WatchList", back_populates="user", cascade="all, delete-orphan")

class UserSettings(Base):
    """사용자별 트레이딩 모드, 증권사 API Key 및 텔레그램 연동 정보 통합 테이블"""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # 트레이딩 모드 및 설정
    trade_mode = Column(String, default="SIMULATED") # SIMULATED, MOCK, REAL
    broker_provider = Column(String, default="KIS")
    kis_app_key = Column(String, nullable=True)
    kis_app_secret = Column(String, nullable=True)
    kis_account_no = Column(String, nullable=True)
    
    # 텔레그램 설정
    telegram_bot_token = Column(String, nullable=True)
    telegram_chat_id = Column(String, nullable=True)
    telegram_enabled = Column(Boolean, default=False)
    
    # 봇 기동 제어 스위치
    is_running = Column(Boolean, default=False)
    is_real_enabled = Column(Boolean, default=False)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="settings")

class TradeLog(Base):
    __tablename__ = "trade_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, index=True)
    ticker_name = Column(String)
    trade_type = Column(String) # 'BUY' or 'SELL'
    price = Column(Float)
    quantity = Column(Integer)
    order_no = Column(String, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="trade_logs")

class Holding(Base):
    """현재 사용자별 보유 중인 종목 상태 (트레일링 스탑용)"""
    __tablename__ = "holdings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, index=True)
    ticker_name = Column(String)
    avg_price = Column(Float)   # 평단가
    quantity = Column(Integer)  # 보유수량
    highest_price = Column(Float) # 구매 후 최고가 (트레일링 스탑 기준점)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="holdings")

    # 동일 사용자가 동일 티커를 이중으로 보유하는 것을 물리적으로 차단
    __table_args__ = (UniqueConstraint('user_id', 'ticker', name='_user_ticker_uc'),)

class ActionLog(Base):
    """봇의 실시간 사용자별 활동 기록 (스캔, 판단, 시스템 메시지 등)"""
    __tablename__ = "action_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level = Column(String, default="INFO") # INFO, WARN, ERROR, SIGNAL
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="action_logs")

class WatchList(Base):
    __tablename__ = "watch_lists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, index=True)
    ticker_name = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="watch_lists")

    # 동일 사용자가 관심 종목에 한 티커를 중복 추가하는 것을 차단
    __table_args__ = (UniqueConstraint('user_id', 'ticker', name='_user_watchlist_uc'),)

class StockTranslation(Base):
    """글로벌 번역 캐시 테이블 (사용자 불문 공용)"""
    __tablename__ = "stock_translations"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, index=True)
    name_ko = Column(String, nullable=False)
