from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Index, UniqueConstraint, Text, Numeric
from sqlalchemy.orm import relationship
from datetime import UTC, datetime
from app.core.database import Base
from app.core.credentials import EncryptedString

from sqlalchemy import TypeDecorator
from datetime import timezone

class AwareDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if not value.tzinfo:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.replace(tzinfo=timezone.utc)
        return value

def utc_now_aware():
    """Timezone-aware datetime을 반환합니다."""
    return datetime.now(UTC)


# Holding.management 값 정본. 문자열 리터럴을 각 소비자에 흩뿌리면 오타 한 글자가
# 조용히 "봇이 안 건드림"을 "봇이 건드림"으로 뒤집으므로 여기서만 정의한다.
MANAGEMENT_BOT_OWNED = "BOT_OWNED"   # 봇이 매수한 포지션
MANAGEMENT_EXTERNAL = "EXTERNAL"     # 봇이 사지 않은 외부 유입 포지션 (봇 관할 밖)
MANAGEMENT_DELEGATED = "DELEGATED"   # 사용자가 봇에 넘긴 외부 포지션 (봇 관할 안, 원장은 분리)

# 봇이 매도·판정을 수행하는 값. EXTERNAL만 관할 밖이다.
# 새 값을 추가할 때 각 소비자에서 != EXTERNAL 조건을 일일이 고치는 대신 이 집합을 쓴다.
BOT_MANAGED_MANAGEMENTS = (MANAGEMENT_BOT_OWNED, MANAGEMENT_DELEGATED)

# EXTERNAL 보유분이 갖는 strategy_type. 어떤 전략 슬롯 키와도 겹치지 않아야 한다 -
# 슬롯 키와 겹치면 매도 판정 루프와 슬롯 자본 계산이 이 보유분을 봇 포지션으로 오인한다.
# (user_id, ticker, strategy_type) 유니크 제약 덕에 같은 티커를 봇 슬롯과 동시에 보유할 수 있다.
EXTERNAL_STRATEGY_TYPE = "external"

# Holding.guard_action 값 정본. 기본값이 ALERT_ONLY인 것이 계약의 핵심이다 -
# 되돌릴 수 없는 손실 확정은 사용자가 명시적으로 켜야 한다.
GUARD_ACTION_ALERT_ONLY = "ALERT_ONLY"   # 알림만. 주문 없음
GUARD_ACTION_SHADOW = "SHADOW"           # "팔았다면 이랬을 것"만 기록. 주문 없음
GUARD_ACTION_LIQUIDATE = "LIQUIDATE"     # 부분 청산 실행
GUARD_ACTIONS = (GUARD_ACTION_ALERT_ONLY, GUARD_ACTION_SHADOW, GUARD_ACTION_LIQUIDATE)

class Strategy(Base):
    __tablename__ = "strategies"

    strategy_type = Column(String, primary_key=True, index=True)
    name_ko = Column(String, nullable=False)
    name_en = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    tier = Column(String, default="single") # gold, silver, bronze, sandbox, single
    regime = Column(String, default="ALL") # ALL, BULLISH, BEARISH, NEUTRAL
    summary_ko = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    is_selectable = Column(Boolean, default=True)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(AwareDateTime, default=utc_now_aware)
    role = Column(String, default="USER", nullable=False)
    token_version = Column(Integer, default=0, nullable=False)

    # 보안 강화를 위한 로그인 잠금 및 브루트포스 방어 필드
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(AwareDateTime, nullable=True)

    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    holdings = relationship("Holding", back_populates="user", cascade="all, delete-orphan")
    trade_logs = relationship("TradeLog", back_populates="user", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", back_populates="user", cascade="all, delete-orphan")
    watch_lists = relationship("WatchList", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    broker_orders = relationship("BrokerOrder", back_populates="user", cascade="all, delete-orphan")
    equity_snapshots = relationship("AccountEquitySnapshot", back_populates="user", cascade="all, delete-orphan")

class SystemSetting(Base):
    """Service-wide runtime settings. Secrets must not be stored here."""
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=False)
    value_type = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_runtime = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(AwareDateTime, default=utc_now_aware)
    updated_at = Column(AwareDateTime, default=utc_now_aware, onupdate=utc_now_aware)

    updated_by_user = relationship("User", foreign_keys=[updated_by])

class RefreshToken(Base):
    """안전한 토큰 갱신 및 다중 기기 강제 로그아웃을 위한 세션 테이블"""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(AwareDateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(AwareDateTime, default=utc_now_aware)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

class UserSettings(Base):
    """사용자별 트레이딩 모드, 증권사 API Key 및 텔레그램 연동 정보 통합 테이블"""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # 트레이딩 모드 및 설정
    trade_mode = Column(String, default="SIMULATED") # SIMULATED, MOCK, REAL
    broker_provider = Column(String, nullable=True)

    # 텔레그램 설정
    telegram_chat_id = Column(String, nullable=True)
    telegram_enabled = Column(Boolean, default=False)

    # 텔레그램 연동 딥링크 토큰. 원본이 아닌 SHA-256 지문만 저장하며, 1회 사용 또는
    # 만료 즉시 NULL로 비운다. 사용자명 기반 연동(누구나 추측 가능)을 대체하는 소유권 증명 수단.
    telegram_link_token_hash = Column(String, nullable=True, index=True)
    telegram_link_token_expires_at = Column(AwareDateTime, nullable=True)
    
    # 다국어 설정 (ko/en)
    language = Column(String(10), default="ko")

    # 봇 기동 제어 스위치
    is_running = Column(Boolean, default=False)

    strategy_type = Column(String, default="regime_switching", nullable=False)

    updated_at = Column(AwareDateTime, default=utc_now_aware, onupdate=utc_now_aware)
    version_id = Column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version_id}

    # Relationships
    user = relationship("User", back_populates="settings")
    credentials = relationship("BrokerCredential", back_populates="user_settings", cascade="all, delete-orphan")


class BrokerCredential(Base):
    """증권사별 API 인증 정보를 담는 1:N 테이블"""
    __tablename__ = "broker_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_settings.user_id", ondelete="CASCADE"), nullable=False)
    broker_name = Column(String, nullable=False) # e.g., "KIS", "TOSS"

    app_key = Column(EncryptedString, nullable=True)
    app_secret = Column(EncryptedString, nullable=True)
    account_no = Column(EncryptedString, nullable=True)

    verification_status = Column(String, default="unverified", nullable=False)
    verified_trade_mode = Column(String, nullable=True)
    verified_at = Column(AwareDateTime, nullable=True)

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
    price = Column(Numeric(precision=20, scale=4, asdecimal=True))
    quantity = Column(Integer)
    order_no = Column(String, nullable=True)
    regime_mode = Column(String, nullable=True)     # ⭐ v2.0 장세 레짐 (BULLISH, BEARISH, NEUTRAL)
    signal_score = Column(Integer, nullable=True)   # ⭐ v2.0 매수 당시의 스캔 점수
    realized_pnl = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)     # ⭐ v2.0 Phase 22 매도 시 실현 손익 (수익금)
    return_rate = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)      # ⭐ v2.0 Phase 22 매도 시 수익률 (%)
    strategy_type = Column(String, default="regime_switching", nullable=False)
    executed_at = Column(AwareDateTime, default=utc_now_aware)

    # Relationships
    user = relationship("User", back_populates="trade_logs")

class Holding(Base):
    """현재 사용자별 보유 중인 종목 상태 (트레일링 스탑용)"""
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, index=True)
    ticker_name = Column(String)
    avg_price = Column(Numeric(precision=20, scale=4, asdecimal=True))   # 평단가
    quantity = Column(Integer)  # 보유수량
    highest_price = Column(Numeric(precision=20, scale=4, asdecimal=True)) # 구매 후 최고가 (트레일링 스탑 기준점)
    rolling_stop_price = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)  # 롤링 박스 스탑 래칫 가격 (단조 증가, opt-in 전략 한정)
    last_price = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)  # 최근 관측 현재가 (avg_price와 동일한 USD 기준)
    last_price_updated_at = Column(AwareDateTime, nullable=True)  # last_price 관측 시각 (신선도 판단 기준)
    regime_mode = Column(String, nullable=True)     # ⭐ v2.0 진입 당시 장세 레짐
    buy_stage = Column(Integer, default=1)          # ⭐ v2.0 후지모토 시게루식 피라미딩 단계 (1, 2, 3단계)
    strategy_type = Column(String, default="regime_switching", nullable=False)
    # 관리 관할권: 이 보유분을 봇이 다룰 수 있는지의 단일 기준.
    #   BOT_OWNED - 봇이 매수한 포지션. 기존 동작 그대로(손절·트레일링·시그널 붕괴·피라미딩).
    #   EXTERNAL  - 봇이 사지 않은 외부 유입 포지션. 매도·추가매수 대상이 아니고 슬롯 자본에서도 제외한다.
    # 값 후보를 String으로 여는 이유는 DELEGATED(위임)를 뒤에 붙일 때 마이그레이션을 두 번 하지 않기 위함이다.
    # 상세 설계는 docs/plans/holding_management_modes.md가 소유한다.
    management = Column(String, nullable=False, server_default=MANAGEMENT_BOT_OWNED, default=MANAGEMENT_BOT_OWNED)
    # 수확 모드 (EXTERNAL 보유분의 opt-in 하위 옵션). 급등 후 꺾일 때만 판다.
    # observed_base_price - 봇이 이 종목을 처음 관측한 가격. 무장 판정과 매도 하한의 앵커이며
    #   avg_price(사용자의 실제 매수가)와 분리해야 한다. 반토막 종목은 본전 기준으로는
    #   영원히 무장되지 않고, 본전 기준 손절은 관측 시작 즉시 발동한다.
    # harvest_armed - 급등 임계를 넘겨 추적이 시작됐는지. 무장 전에는 고점도 세지 않는다.
    observed_base_price = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    harvest_enabled = Column(Boolean, nullable=False, server_default="0", default=False)
    harvest_armed = Column(Boolean, nullable=False, server_default="0", default=False)
    harvest_breach_started_at = Column(AwareDateTime, nullable=True)  # 트레일링 이탈이 시작된 시각
    # 방어 경보 (EXTERNAL 보유분의 opt-in 하위 옵션). 경보만 보내고 주문은 내지 않는다.
    # 판정은 상태가 아니라 전이를 본다 - 이미 물린 종목은 절대 점수선을 상시 만족하므로,
    # 켠 시점의 점수·저가를 기준선으로 박고 거기서 추가로 악화될 때만 울린다.
    guard_enabled = Column(Boolean, nullable=False, server_default="0", default=False)
    guard_baseline_score = Column(Float, nullable=True)
    guard_baseline_low = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    guard_enabled_at = Column(AwareDateTime, nullable=True)   # 유예기간 기준 시각
    guard_last_alert_at = Column(AwareDateTime, nullable=True)  # 경보 쿨다운 기준 시각
    # 방어 조건 충족 시 무엇을 할지. 기본값은 알림만이며, 실제 청산은 사용자가 명시적으로 켜야 한다.
    #   ALERT_ONLY - 알림만 (기본)
    #   SHADOW     - "팔았다면 이랬을 것"을 기록만 한다. 주문 없음. 신호 품질 실측용
    #   LIQUIDATE  - guard_sell_ratio 만큼 실제 부분 청산
    guard_action = Column(String, nullable=False, server_default=GUARD_ACTION_ALERT_ONLY, default=GUARD_ACTION_ALERT_ONLY)
    guard_sell_ratio = Column(Float, nullable=False, server_default="0.5", default=0.5)
    guard_streak = Column(Integer, nullable=False, server_default="0", default=0)  # 연속 충족 사이클
    guard_streak_started_at = Column(AwareDateTime, nullable=True)  # 연속 충족이 시작된 시각(벽시계 게이트 기준)
    guard_last_action_at = Column(AwareDateTime, nullable=True)  # 일일 1회 캡 기준 시각
    # 봇 소유 포지션의 손절 노이즈 버퍼 기준 시각.
    # 순간적으로 손절선을 찔렀다 돌아오는 꼬리에 털리지 않으려고 이탈을 두 번 확인하는데,
    # 그 대기가 사이클 수로만 세어져 있었다. 사이클 주기는 시간에 안정적이지 않고(실측 104~846초)
    # 카운터가 인메모리라 재기동이 진행 중이던 대기를 통째로 지운다. 시각을 DB에 둬서
    # 대기의 하한을 벽시계로 고정한다.
    exit_breach_started_at = Column(AwareDateTime, nullable=True)
    # 위임(DELEGATED) 포지션의 리스크 기준가. 손절선과 트레일링 하한 가드가 이 값을 앵커로 쓴다.
    #
    # avg_price를 그대로 쓰면 안 되는 이유는 용도가 둘로 갈리기 때문이다. 실현손익은 사용자의
    # 실제 매수가로 계산해야 정직하고, 손절선은 위임 시점가를 기준으로 잡아야 봇이 물려받은
    # 과거 손실에 즉시 청산당하지 않는다. 위임 시 avg_price를 현재가로 덮어쓰면 손절은
    # 정상화되지만 실현손익이 조작되므로, 리스크 기준가만 따로 판다.
    #
    # NULL이면 avg_price로 폴백한다. 따라서 기존 BOT_OWNED 레코드는 아무 영향을 받지 않는다.
    risk_basis_price = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    updated_at = Column(AwareDateTime, default=utc_now_aware, onupdate=utc_now_aware)
    version_id = Column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version_id}

    # Relationships
    user = relationship("User", back_populates="holdings")

    # 동일 사용자가 동일 전략 하에서 동일 티커를 이중으로 보유하는 것을 물리적으로 차단
    __table_args__ = (UniqueConstraint('user_id', 'ticker', 'strategy_type', name='_user_ticker_strategy_uc'),)

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
    strategy_type = Column(String, default="regime_switching", nullable=False)
    ticker_name = Column(String, nullable=True)
    exchange_code = Column(String, nullable=True)
    order_division = Column(String, nullable=True)
    source = Column(String, nullable=False, default="STRATEGY")
    status = Column(String, nullable=False, default="INTENT_CREATED")
    requested_qty = Column(Integer, nullable=False)
    broker_filled_qty = Column(Integer, nullable=False, default=0)
    applied_filled_qty = Column(Integer, nullable=False, default=0)
    submitted_price = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=False)
    filled_price = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    buy_stage = Column(Integer, nullable=True)
    regime_mode = Column(String, nullable=True)
    signal_score = Column(Integer, nullable=True)
    sell_reason = Column(Text, nullable=True)
    submission_attempts = Column(Integer, nullable=False, default=0)
    discovery_attempts = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    submitted_at = Column(AwareDateTime, nullable=False, default=utc_now_aware)
    submission_started_at = Column(AwareDateTime, nullable=True)
    response_received_at = Column(AwareDateTime, nullable=True)
    last_discovery_at = Column(AwareDateTime, nullable=True)
    last_checked_at = Column(AwareDateTime, nullable=True)
    last_alerted_at = Column(AwareDateTime, nullable=True)
    resolved_at = Column(AwareDateTime, nullable=True)

    user = relationship("User", back_populates="broker_orders")

    __table_args__ = (
        UniqueConstraint("user_id", "broker_order_no", name="_user_broker_order_uc"),
        Index("ix_broker_orders_user_status", "user_id", "status"),
    )

class AccountEquitySnapshot(Base):
    """관리자 자산 곡선에 사용하는 실제 계좌 평가 시점별 스냅샷."""
    __tablename__ = "account_equity_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    total_asset = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=False)
    cash_balance = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    stock_balance = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    profit_rate = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    profit_loss = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)  # 평가손익 (KRW, 대시보드 표시용)
    fx_rate = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True)
    trade_mode = Column(String, nullable=False)
    captured_at = Column(AwareDateTime, default=utc_now_aware, nullable=False, index=True)

    user = relationship("User", back_populates="equity_snapshots")

class ActionLog(Base):
    """봇의 실시간 사용자별 활동 기록 (스캔, 판단, 시스템 메시지 등)"""
    __tablename__ = "action_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level = Column(String, default="INFO") # INFO, WARN, ERROR, SIGNAL
    message = Column(String)
    created_at = Column(AwareDateTime, default=utc_now_aware)

    # Relationships
    user = relationship("User", back_populates="action_logs")

class WatchList(Base):
    __tablename__ = "watch_lists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String, index=True)
    ticker_name = Column(String, nullable=True)
    added_at = Column(AwareDateTime, default=utc_now_aware)

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
    nasdaq_current = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True, comment="NASDAQ 종합지수 현재값")
    nasdaq_change = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True, comment="NASDAQ 종합지수 전일 대비 등락폭")
    nasdaq_change_pct = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True, comment="NASDAQ 종합지수 전일 대비 등락률")
    nasdaq_sync_status = Column(
        String,
        nullable=False,
        default="failed",
        comment="NASDAQ 데이터 동기화 상태: fresh, stale, failed, skipped",
    )
    exchange_rate_symbol = Column(String, nullable=False, default="USDKRW=X", comment="USD/KRW Yahoo Finance 티커")
    exchange_rate_current = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True, comment="USD/KRW 현재 환율")
    exchange_rate_change = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True, comment="USD/KRW 전일 대비 변화폭")
    exchange_rate_change_pct = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=True, comment="USD/KRW 전일 대비 변화율")
    exchange_rate_sync_status = Column(
        String,
        nullable=False,
        default="failed",
        comment="USD/KRW 데이터 동기화 상태: fresh, stale, failed, skipped",
    )
    created_at = Column(AwareDateTime, default=utc_now_aware, index=True, comment="스냅샷 생성 시각")

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
    created_at = Column(AwareDateTime, default=utc_now_aware, index=True, comment="스냅샷 생성 시각")

class SwingScoreOutcome(Base):
    """스윙 예측 점수와 익일 실제 등락을 짝지어 누적하는 캘리브레이션 관측 테이블.

    '85점 종목이 실제로 다음날 올랐는가'를 사후 검증하기 위한 축적 원장이며,
    점수→실현 수익 매핑 보정(등화회귀 등)의 입력이 된다. 매매에는 관여하지 않는다.
    """
    __tablename__ = "swing_score_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    predicted_date = Column(String, nullable=False, index=True, comment="예측 스냅샷 기준일 (YYYY-MM-DD, UTC)")
    ticker = Column(String, nullable=False, index=True, comment="종목 영문 티커")
    score = Column(Numeric(precision=6, scale=2, asdecimal=True), nullable=False, comment="예측 당시 스윙 점수 (0~100)")
    baseline_close = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=False, comment="예측 시점 종가")
    observed_close = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=False, comment="예측일 다음 거래일 종가")
    observed_date = Column(String, nullable=False, comment="관측 종가의 거래일 (YYYY-MM-DD)")
    return_pct = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=False, comment="익일 수익률 (%)")
    created_at = Column(AwareDateTime, default=utc_now_aware, index=True, comment="관측 기록 시각")

    __table_args__ = (
        # 같은 예측일에 스냅샷이 여러 번 생성돼도 종목당 관측은 1건만 남긴다 (잡 재실행 멱등성).
        UniqueConstraint("predicted_date", "ticker", name="uq_swing_outcome_date_ticker"),
    )

class UnfilledOrder(Base):
    """미체결 가상 지정가 주문"""
    __tablename__ = "unfilled_orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    ticker_name = Column(String, nullable=True)
    trade_type = Column(String, nullable=False) # "BUY" or "SELL"
    price = Column(Numeric(precision=20, scale=4, asdecimal=True), nullable=False)
    quantity = Column(Integer, nullable=False)
    strategy_type = Column(String, nullable=False)
    buy_stage = Column(Integer, nullable=True)
    regime_mode = Column(String, nullable=True)
    signal_score = Column(Integer, nullable=True)
    order_no = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(AwareDateTime, default=utc_now_aware)

    user = relationship("User")
