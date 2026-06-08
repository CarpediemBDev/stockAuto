from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Index, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from datetime import UTC, datetime
from app.core.database import Base

def utc_now_naive():
    """SQLite 호환을 위해 UTC 기준 naive datetime을 저장합니다."""
    return datetime.now(UTC).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)
    role = Column(String, default="USER", nullable=False)

    # 보안 강화를 위한 로그인 잠금 및 브루트포스 방어 필드
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)

    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    holdings = relationship("Holding", back_populates="user", cascade="all, delete-orphan")
    trade_logs = relationship("TradeLog", back_populates="user", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", back_populates="user", cascade="all, delete-orphan")
    watch_lists = relationship("WatchList", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    broker_orders = relationship("BrokerOrder", back_populates="user", cascade="all, delete-orphan")

class RefreshToken(Base):
    """안전한 토큰 갱신 및 다중 기기 강제 로그아웃을 위한 세션 테이블"""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

class UserSettings(Base):
    """사용자별 트레이딩 모드, 증권사 API Key 및 텔레그램 연동 정보 통합 테이블"""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # 트레이딩 모드 및 설정
    trade_mode = Column(String, default="SIMULATED") # SIMULATED, MOCK, REAL
    broker_provider = Column(String, default="KIS")

    # 텔레그램 설정
    telegram_chat_id = Column(String, nullable=True)
    telegram_enabled = Column(Boolean, default=False)

    # 봇 기동 제어 스위치
    is_running = Column(Boolean, default=False)
    is_real_enabled = Column(Boolean, default=False)

    strategy_type = Column(String, default="regime_switching", nullable=False)

    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    # Relationships
    user = relationship("User", back_populates="settings")
    credentials = relationship("BrokerCredential", back_populates="user_settings", cascade="all, delete-orphan")


class BrokerCredential(Base):
    """증권사별 API 인증 정보를 담는 1:N 테이블"""
    __tablename__ = "broker_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_settings.user_id", ondelete="CASCADE"), nullable=False)
    broker_name = Column(String, nullable=False) # e.g., "KIS", "TOSS"
    
    app_key = Column(String, nullable=True)
    app_secret = Column(String, nullable=True)
    account_no = Column(String, nullable=True)
    
    verification_status = Column(String, default="unverified", nullable=False)
    verified_trade_mode = Column(String, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'broker_name', name='uq_user_broker'),
    )

    # Relationships
    user_settings = relationship("UserSettings", back_populates="credentials")

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
    regime_mode = Column(String, nullable=True)     # ⭐ v2.0 장세 레짐 (BULLISH, BEARISH, NEUTRAL)
    signal_score = Column(Integer, nullable=True)   # ⭐ v2.0 매수 당시의 스캔 점수
    realized_pnl = Column(Float, nullable=True)     # ⭐ v2.0 Phase 22 매도 시 실현 손익 (수익금)
    return_rate = Column(Float, nullable=True)      # ⭐ v2.0 Phase 22 매도 시 수익률 (%)
    executed_at = Column(DateTime, default=utc_now_naive)

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
    regime_mode = Column(String, nullable=True)     # ⭐ v2.0 진입 당시 장세 레짐
    buy_stage = Column(Integer, default=1)          # ⭐ v2.0 후지모토 시게루식 피라미딩 단계 (1, 2, 3단계)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    # Relationships
    user = relationship("User", back_populates="holdings")

    # 동일 사용자가 동일 티커를 이중으로 보유하는 것을 물리적으로 차단
    __table_args__ = (UniqueConstraint('user_id', 'ticker', name='_user_ticker_uc'),)

class BrokerOrder(Base):
    """증권사 주문의 누적 체결 상태와 DB 반영 수량을 보존하는 영구 원장."""
    __tablename__ = "broker_orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    intent_id = Column(String, nullable=False, unique=True, index=True)
    broker_order_no = Column(String, nullable=True)
    broker_order_date = Column(String, nullable=False)
    trade_mode = Column(String, nullable=False)
    side = Column(String, nullable=False)
    ticker = Column(String, nullable=False)
    prefixed_ticker = Column(String, nullable=False)
    ticker_name = Column(String, nullable=True)
    exchange_code = Column(String, nullable=True)
    order_division = Column(String, nullable=True)
    source = Column(String, nullable=False, default="STRATEGY")
    status = Column(String, nullable=False, default="INTENT_CREATED")
    requested_qty = Column(Integer, nullable=False)
    broker_filled_qty = Column(Integer, nullable=False, default=0)
    applied_filled_qty = Column(Integer, nullable=False, default=0)
    submitted_price = Column(Float, nullable=False)
    filled_price = Column(Float, nullable=True)
    buy_stage = Column(Integer, nullable=True)
    regime_mode = Column(String, nullable=True)
    signal_score = Column(Integer, nullable=True)
    sell_reason = Column(Text, nullable=True)
    submission_attempts = Column(Integer, nullable=False, default=0)
    discovery_attempts = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    resume_after_resolution = Column(Boolean, nullable=False, default=False)
    last_error = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=False, default=utc_now_naive)
    submission_started_at = Column(DateTime, nullable=True)
    response_received_at = Column(DateTime, nullable=True)
    last_discovery_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_alerted_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="broker_orders")

    __table_args__ = (
        UniqueConstraint("user_id", "broker_order_no", name="_user_broker_order_uc"),
        Index("ix_broker_orders_user_status", "user_id", "status"),
    )

class ActionLog(Base):
    """봇의 실시간 사용자별 활동 기록 (스캔, 판단, 시스템 메시지 등)"""
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level = Column(String, default="INFO") # INFO, WARN, ERROR, SIGNAL
    message = Column(String)
    created_at = Column(DateTime, default=utc_now_naive)

    # Relationships
    user = relationship("User", back_populates="action_logs")

class WatchList(Base):
    __tablename__ = "watch_lists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, index=True)
    ticker_name = Column(String, nullable=True)
    added_at = Column(DateTime, default=utc_now_naive)

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

class MarketOverviewSnapshot(Base):
    """시장 헤더와 자동매매 공통 컨텍스트가 참조하는 시장 개요 스냅샷"""
    __tablename__ = "market_overview_snapshots"
    __table_args__ = {
        "comment": "시장 개요 API가 즉시 반환할 수 있도록 저장하는 최신 시장 상태, NASDAQ, USD/KRW 스냅샷"
    }

    id = Column(Integer, primary_key=True, index=True)
    market_condition = Column(
        String,
        nullable=False,
        default="NEUTRAL",
        comment="QQQ 기반 시장 상태: BULLISH, BEARISH, NEUTRAL",
    )
    market_condition_sync_status = Column(
        String,
        nullable=False,
        default="failed",
        comment="시장 상태 동기화 상태: fresh, stale, failed, skipped",
    )
    nasdaq_symbol = Column(String, nullable=False, default="^IXIC", comment="NASDAQ 종합지수 Yahoo Finance 티커")
    nasdaq_current = Column(Float, nullable=True, comment="NASDAQ 종합지수 현재값")
    nasdaq_change = Column(Float, nullable=True, comment="NASDAQ 종합지수 전일 대비 등락폭")
    nasdaq_change_pct = Column(Float, nullable=True, comment="NASDAQ 종합지수 전일 대비 등락률")
    nasdaq_sync_status = Column(
        String,
        nullable=False,
        default="failed",
        comment="NASDAQ 데이터 동기화 상태: fresh, stale, failed, skipped",
    )
    exchange_rate_symbol = Column(String, nullable=False, default="USDKRW=X", comment="USD/KRW Yahoo Finance 티커")
    exchange_rate_current = Column(Float, nullable=True, comment="USD/KRW 현재 환율")
    exchange_rate_change = Column(Float, nullable=True, comment="USD/KRW 전일 대비 변화폭")
    exchange_rate_change_pct = Column(Float, nullable=True, comment="USD/KRW 전일 대비 변화율")
    exchange_rate_sync_status = Column(
        String,
        nullable=False,
        default="failed",
        comment="USD/KRW 데이터 동기화 상태: fresh, stale, failed, skipped",
    )
    created_at = Column(DateTime, default=utc_now_naive, index=True, comment="스냅샷 생성 시각")

class SwingPredictionSnapshot(Base):
    """스윙 예측 후보를 사용자 관심종목 조합별로 보존하는 스냅샷"""
    __tablename__ = "swing_prediction_snapshots"
    __table_args__ = {
        "comment": "스윙 예측 폴링 API가 대량 yfinance 분석 없이 즉시 반환할 수 있도록 저장하는 후보 스냅샷"
    }

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(
        String,
        nullable=False,
        index=True,
        comment="기본 스윙 풀과 사용자 관심종목을 정렬해 결합한 캐시 식별자",
    )
    ticker_universe = Column(
        Text,
        nullable=False,
        comment="분석 대상 티커 목록 JSON 배열",
    )
    candidates_json = Column(
        Text,
        nullable=False,
        comment="스윙 예측 후보 결과 JSON 배열",
    )
    sync_status = Column(
        String,
        nullable=False,
        default="fresh",
        comment="스윙 예측 동기화 상태: fresh, stale, refreshing, failed, empty",
    )
    created_at = Column(DateTime, default=utc_now_naive, index=True, comment="스냅샷 생성 시각")
