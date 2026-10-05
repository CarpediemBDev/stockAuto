"""갭상승 청산 A/B의 런타임 부품: 정규장 갭 조회, 실험군 배정, 보유 시작 시점 판정.

판정식(임계값 비교)은 순수함수로 app/bot/trade_calculations.py에 있고, 이 모듈은 그 판정에
넣을 값을 모으는 일만 한다. 스케줄러는 여기서 받은 값으로 판정하고 매도 인자를 만든다.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd

from app.bot.market_session import ET, REGULAR_MARKET_OPEN
from app.bot.trade_calculations import compute_session_gap_pct
from app.core.models import TradeLog
from app.core.system_settings import SETTING_ENABLE_GAP_EXIT_AB, is_system_setting_enabled

GAP_EXIT_ARM_TREATMENT = "TREATMENT"
GAP_EXIT_ARM_CONTROL = "CONTROL"

# 정규장 갭은 장중에 바뀌지 않으므로 (티커, 거래일)당 한 번만 성공적으로 받으면 된다.
# 실패나 "오늘 봉 없음"은 캐시하지 않는다 - 개장 직후엔 일봉이 늦게 붙을 수 있어 다음
# 사이클에 다시 물어야 한다.
_gap_cache: dict[tuple[str, date], Decimal] = {}
_gap_cache_lock = threading.Lock()

# 대조군 "팔았다면" 기록과 처치군 매도 로그를 거래일당 한 번만 남기기 위한 표식.
# 인메모리라 재기동하면 같은 날 한 번 더 남을 수 있다 - 판독 시 (계정, 티커, 날짜)로 중복 제거한다.
_logged_events: set[tuple[int, str, date]] = set()
_logged_events_lock = threading.Lock()


def resolve_gap_exit_arm(user_id: int) -> str | None:
    """계정의 실험군을 돌려준다. 실험이 꺼져 있으면 None(규칙 미적용, 기존 동작).

    배정은 user_id 홀짝으로 고정한다. 계정 id는 전략과 무관하게 부여됐으므로 홀짝 분할이
    전략 구성을 한쪽으로 몰지 않고, 배정표를 저장하지 않아도 언제든 같은 분할을 재현할 수 있다.
    """
    if not is_system_setting_enabled(SETTING_ENABLE_GAP_EXIT_AB):
        return None
    return GAP_EXIT_ARM_TREATMENT if user_id % 2 == 0 else GAP_EXIT_ARM_CONTROL


def session_date_et(now_utc: datetime) -> date:
    return now_utc.astimezone(ET).date()


def regular_open_utc(session_day: date) -> datetime:
    """해당 거래일 정규장 개장 시각(UTC)."""
    open_et = datetime.combine(session_day, REGULAR_MARKET_OPEN, tzinfo=ET)
    return open_et.astimezone(timezone.utc)


def extract_session_gap_pct(df_daily: pd.DataFrame, session_day: date) -> Decimal | None:
    """일봉에서 session_day의 정규장 갭(%)을 뽑는다. 그날 봉이 아직 없으면 None.

    일봉을 쓰는 이유 - 일봉 Open은 프리마켓을 켜고 받아도 정규장 시가다(2026-09-23 HCTI
    시가 1.11 일치 확인). 분봉으로 재면 프리마켓 첫 체결가가 섞여 리서치와 다른 값을 본다.
    """
    if df_daily is None or df_daily.empty or len(df_daily) < 2:
        return None
    if "Open" not in df_daily.columns or "Close" not in df_daily.columns:
        return None
    last_day = pd.Timestamp(df_daily.index[-1]).date()
    if last_day != session_day:
        return None
    return compute_session_gap_pct(df_daily["Close"].iloc[-2], df_daily["Open"].iloc[-1])


async def get_session_gap_pct(ticker: str, session_day: date) -> Decimal | None:
    key = (ticker, session_day)
    with _gap_cache_lock:
        if key in _gap_cache:
            return _gap_cache[key]

    from app.scanner.data_provider import fetch_ohlcv

    df_daily = await fetch_ohlcv(ticker, interval="1d", period="5d")
    gap = extract_session_gap_pct(df_daily, session_day)
    if gap is not None:
        with _gap_cache_lock:
            _gap_cache[key] = gap
            # 지난 거래일 항목은 버린다. 하루치만 들고 있으면 된다.
            for stale in [k for k in _gap_cache if k[1] != session_day]:
                _gap_cache.pop(stale, None)
    return gap


def held_since_before_open(db, user_id: int, ticker: str, session_open_utc: datetime) -> bool:
    """이 보유분이 오늘 개장 전부터 들고 있던 것인지.

    갭은 전일 종가를 넘겨 들고 온 포지션의 위험이다. 오늘 장중에 산 종목을 갭을 이유로
    곧바로 파는 것은 매수 직후 왕복 수수료만 내는 휩쏘이므로 대상에서 뺀다.
    매수 기록이 없으면(위임 등 외부 유입) 개장 전부터 보유한 것으로 본다.
    """
    last_buy = (
        db.query(TradeLog.executed_at)
        .filter(
            TradeLog.user_id == user_id,
            TradeLog.ticker == ticker,
            TradeLog.trade_type == "BUY",
        )
        .order_by(TradeLog.executed_at.desc())
        .first()
    )
    if last_buy is None or last_buy[0] is None:
        return True
    return last_buy[0] < session_open_utc


def mark_event_logged(user_id: int, ticker: str, session_day: date) -> bool:
    """처음 기록하는 (계정, 티커, 거래일)이면 True. 이미 남겼으면 False."""
    key = (user_id, ticker, session_day)
    with _logged_events_lock:
        if key in _logged_events:
            return False
        _logged_events.add(key)
        for stale in [k for k in _logged_events if k[2] != session_day]:
            _logged_events.discard(stale)
        return True
