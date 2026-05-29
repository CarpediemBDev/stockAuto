from apscheduler.schedulers.background import BackgroundScheduler
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import TradeLog, Holding, ActionLog, UserSettings
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import asyncio
import socket
import httpx
from requests.exceptions import RequestException as RequestsRequestException
from app.core.logging import logger
from app.core.config import settings
from app.scanner.data_provider import fetch_ohlcv
from app.core.telegram import send_message_async, send_daily_report_to_all_users_sync
from app.bot.fx_cache import FXRateCache

# 💡 네트워크 일시 장애에 따른 텔레그램 경고 도배 방지용 시간 기록 저장소
_user_network_alert_sent = {}

import time
# 매수 실패(단가 초과, 예수금 부족) 알림 도배 방지용 쿨타임 캐시 (1시간)
WARNING_COOLDOWN_CACHE = {}

# 💡 동적 손절선 및 트레일링 스탑 이탈 연속 횟수 추적 캐시 (Whipsaw 방지용 연속 2회 확정 가드)
# 키: (user_id, ticker) -> 값: int (연속 이탈 횟수)
BREACH_COUNT_CACHE = {}



from app.scanner.scanner import scan_overseas_market, analyze_single_ticker, check_market_sentiment

scheduler = BackgroundScheduler()


is_processing = False # 중복 실행 방지용 플래그
latest_scanned_signals = [] # 글로벌 실시간 마켓 스캔 시그널 캐시용

# 💡 KIS API 동시성 제어 세마포어 (초당 최대 15회 호출로 자동 제한 - 429 차단 철벽 방어)
kis_semaphore = asyncio.Semaphore(15)

async def safe_broker_call(func, *args, **kwargs):
    """
    KIS API의 초당 호출 제한(Rate Limit)을 철저히 준수하기 위해 동시성 세마포어 가드 하에
    동기식 브로커 함수를 비동기 스레드 풀(asyncio.to_thread)에서 안전하게 지연 호출합니다.
    """
    async with kis_semaphore:
        # 호출 사이에 아주 미세한 지연(40ms)을 주어 고르게 배분
        await asyncio.sleep(0.04)
        return await asyncio.to_thread(func, *args, **kwargs)

ET = ZoneInfo("America/New_York") # 미국 동부 표준시(ET)는 DST를 자동으로 반영합니다


def is_us_market_open() -> bool:
    """
    현재 시각이 미국 주식시장 정규 장중인지 확인합니다.
    NYSE/NASDAQ 정규 장: 월요일~금요일 09:30~16:00 ET
    """
    now_et = datetime.now(tz=ET)
    # 토/일 휴장
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close

async def get_realtime_price(ticker: str) -> float | None:
    """
    매수 직전 해당 종목의 실시간 현재가를 새롭게 조회합니다.
    데이터 프로바이더 1분봉 활용 (Period: 1d, Interval: 1m)
    """
    try:
        df = await fetch_ohlcv(ticker, interval="1m", period="1d")
        if df.empty:
            return None
        return float(df['Close'].iloc[-1])
    except Exception as e:
        logger.exception(f"[RealTimePrice] Failed to fetch {ticker}")
        return None


def log_action(db, user_id: int, message: str, level="INFO"):
    """활동 로그를 특정 사용자의 ID로 DB에 기록합니다."""
    db.add(ActionLog(user_id=user_id, message=message, level=level))
    db.commit()
    logger.info(f"[{level}] [User {user_id}] {message}")

async def run_user_trading_flow(user_id: int, signal_map: dict, all_signals: list):
    """
    개별 사용자별 독자적인 자동매매 시나리오 처리 함수 (멀티테넌시 격리) - ⭐ v2.0 레짐 스위칭 & 피라미딩 & 조기익절 탑재
    """
    db = SessionLocal()
    try:
        # 사용자 설정 로드
        user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not user_settings or not user_settings.is_running:
            return

        # 💡 0. 시장 감정 분석 및 QQQ 레짐 모드 판정
        sentiment = await check_market_sentiment()
        log_action(db, user_id, f"Scan Cycle Started (Mode: {user_settings.trade_mode} | Market Regime: {sentiment})")

        # 1. 사용자 맞춤형 브로커 인스턴스 획득
        broker = get_broker_client(user_settings)

        # 2. 보유 종목(Holdings) 모니터링 및 매도/탈출 판정 (조기 익절 & 트레일링 스탑)
        holdings = db.query(Holding).filter(Holding.user_id == user_id).all()
        for h in holdings:
            try:
                ticker = h.ticker
                current_data = signal_map.get(ticker)
                
                # 스캐너 후보군에 없더라도 보유 종목은 백그라운드 정밀 단독 기술 분석 수행
                if not current_data:
                    logger.info(f"[Scheduler User {user_id}] Owned ticker {ticker} not in top scanned signals. Running dedicated technical analysis...")
                    current_data = await analyze_single_ticker(ticker)
                
                if not current_data:
                    log_action(db, user_id, f"No technical data available for owned ticker {ticker}. Skipping monitoring in this cycle.", "WARNING")
                    continue
                
                current_price = current_data['price']
                profit_rate = ((current_price - h.avg_price) / h.avg_price) * 100
                current_score = current_data['signal_score']
                is_smart_exit = current_data.get('details', {}).get('is_smart_exit', False)

                # 최고가(Peak) 갱신
                if current_price > h.highest_price:
                    h.highest_price = current_price
                    log_action(db, user_id, f"New Peak for {ticker}: ${current_price}", "SIGNAL")
                    db.commit()

                # ATR 기반 동적 익절/손절선 계산
                atr = current_data.get('details', {}).get('atr', 0.0)
                stop_loss_pct = 3.0 # 디폴트 3%
                trailing_stop_pct = 2.0 # 디폴트 2%
                
                if atr > 0:
                    atr_pct = (atr / current_price) * 100
                    stop_loss_pct = max(3.0, atr_pct * 1.5)
                    trailing_stop_pct = max(2.0, atr_pct * 1.0)

                # 매도 조건 체크
                sell_reason = None
                is_breached = False
                breach_reason = ""
                
                if profit_rate <= -stop_loss_pct:
                    is_breached = True
                    breach_reason = f"동적 손절선 이탈 (손절 기준 -{stop_loss_pct:.2f}% 돌파 | 현재 수익률: {profit_rate:.2f}%)"
                elif current_price <= h.highest_price * (1 - trailing_stop_pct / 100) and h.highest_price > h.avg_price:
                    is_breached = True
                    breach_reason = f"동적 트레일링 스탑 이탈 (최고가 ${h.highest_price:.2f} 대비 {trailing_stop_pct:.2f}% 하락 | 현재 수익률: {profit_rate:.2f}%)"
                
                # 💡 손절선/트레일링 스탑 이탈 감지 시, 연속 2회 확정식 가드 적용
                if is_breached:
                    cache_key = (user_id, ticker)
                    BREACH_COUNT_CACHE[cache_key] = BREACH_COUNT_CACHE.get(cache_key, 0) + 1
                    count = BREACH_COUNT_CACHE[cache_key]
                    
                    if count >= 2:
                        sell_reason = breach_reason + " [2회 연속 이탈 확정]"
                    else:
                        log_action(db, user_id, f"[Noise Buffer] {ticker} first breach detected ({breach_reason}). Delaying sell for noise protection (Count: {count}/2).", "INFO")
                else:
                    # 이탈 상태가 아니면 연속 이탈 횟수를 0으로 리셋 (캐시 제거)
                    BREACH_COUNT_CACHE.pop((user_id, ticker), None)
                
                # ⭐ 지표 1. 조기 스마트 익절 (RSI 하락 다이버전스 + MACD 데드크로스) - 스마트 익절은 버퍼 없이 즉시 실행
                if not sell_reason and profit_rate >= settings.MIN_SMART_EXIT_PROFIT_RATE and is_smart_exit:
                    sell_reason = f"스마트 조기 익절 (RSI-MACD 조건 충족 | 수익률: {profit_rate:.2f}%)"
                
                # 지표 4. 기술적 강세 시그널 붕괴 - 시그널 붕괴는 버퍼 없이 즉시 실행
                elif not sell_reason and ((sentiment == "BULLISH" and current_score < 40) or (sentiment != "BULLISH" and current_score < 50)):
                    sell_reason = f"강세 시그널 붕괴 ({current_score}점 - EMA/VWAP 지지선 이탈 또는 매도 압력)"

                if sell_reason:
                    log_action(db, user_id, f"EXIT SIGNAL: {ticker} | Reason: {sell_reason}", "SIGNAL")
                    
                    # 브로커를 통한 매도 주문 집행 (💡 safe_broker_call 세마포어 격리 가드 탑재)
                    res = await safe_broker_call(broker.sell_order, ticker, h.quantity, price=current_price)


                    if res["success"]:
                        filled_price = res["filled_price"]
                        filled_qty = res["filled_qty"]
                        
                        # 💡 [Phase 30] 매수/매도 수수료 및 SEC Fee가 정밀 차감된 실수익(Net) 연산
                        buy_gross = h.avg_price * filled_qty
                        buy_fee = buy_gross * settings.KIS_FEE_RATE
                        sell_gross = filled_price * filled_qty
                        sell_fee = sell_gross * settings.KIS_FEE_RATE
                        sec_fee = sell_gross * settings.SEC_FEE_RATE
                        
                        realized_pnl = sell_gross - buy_gross - buy_fee - sell_fee - sec_fee
                        calc_return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0

                        db.add(TradeLog(
                            user_id=user_id,
                            ticker=ticker,
                            ticker_name=h.ticker_name,
                            trade_type="SELL",
                            price=filled_price,
                            quantity=filled_qty,
                            order_no=res["order_no"],
                            regime_mode=sentiment,
                            signal_score=current_score,
                            realized_pnl=round(realized_pnl, 2),
                            return_rate=round(calc_return_rate, 2)
                        ))
                        db.delete(h)
                        db.commit()
                        BREACH_COUNT_CACHE.pop((user_id, ticker), None) # 매도 완료 후 캐시 제거
                        log_action(db, user_id, f"SUCCESS: {ticker} sold via {sell_reason} | Order: {res['order_no']}", "INFO")
                        
                        exchange_rate = FXRateCache.get_rate()
                        filled_price_krw = filled_price * exchange_rate
                        total_amount_usd = filled_price * filled_qty
                        total_amount_krw = total_amount_usd * exchange_rate
                        
                        pnl_sign = "+" if realized_pnl >= 0 else "-"
                        pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
                        realized_pnl_abs = abs(realized_pnl)
                        
                        # 텔레그램 매도 알림 전송 (초경량 정화 및 실수익 기준 부호 교정 완비)
                        send_message_async(
                            user_id,
                            f"🔴 *[자동매도 체결]* {ticker} ({h.ticker_name})\n"
                            f"• *체결 단가:* `${filled_price:,.2f}` (약 {filled_price_krw:,.0f}원)\n"
                            f"• *체결 수량:* `{filled_qty}주`\n"
                            f"• *체결 금액:* `${total_amount_usd:,.2f}` (약 {total_amount_krw:,.0f}원)\n"
                            f"• *매도 사유:* {sell_reason}\n\n"
                            f"{pnl_emoji} *실수익률:* `{pnl_sign}{calc_return_rate:.2f}%`\n"
                            f"💰 *실현 실수익:* `{pnl_sign}${realized_pnl_abs:,.2f}`\n"
                            f"• *주문 번호:* `{res['order_no']}`"
                        )
                    else:
                        log_action(db, user_id, f"SELL FAILED: {ticker} | {res['message']}", "ERROR")
            except Exception as item_err:
                log_action(db, user_id, f"Error processing holding {h.ticker}: {item_err}", "ERROR")

        # 3. 신규 매수 기회 탐색 및 1:2:6 피라미딩 자금 관리
        if not is_us_market_open():
            log_action(db, user_id, "[BUY SKIP] US market is currently closed. No new buy orders placed.", "INFO")
        elif all_signals:
            # 💡 [Phase 29] MAX_HOLDINGS 포트폴리오 안전 가드
            current_holdings_count = db.query(Holding).filter(Holding.user_id == user_id).count()
            if current_holdings_count >= settings.MAX_HOLDINGS:
                log_action(db, user_id, f"[BUY SKIP] Max holdings limit reached ({current_holdings_count}/{settings.MAX_HOLDINGS}). Skipping new buy scans.", "INFO")
                all_signals_to_process = []
            else:
                all_signals_to_process = all_signals

            # 장세별 통과 커트라인 점수 분기 (상승장 85점, 하락/횡보장 95점 (수수료 절감 최적화 적용))
            cutoff_score = 85 if sentiment == "BULLISH" else 95
            cached_balance_data = None # 💡 사용자별 1분 루프 내 KIS 잔고 임시 캐싱 (DDoS급 중복 조회 제거)
            
            for s in all_signals_to_process:
                if s['signal_score'] >= cutoff_score:
                    ticker = s['ticker']
                    
                    # 동일 사용자가 이미 보유 중인지 확인 (피라미딩 여부 판별)
                    existing_holding = db.query(Holding).filter(
                        Holding.user_id == user_id,
                        Holding.ticker == ticker
                    ).first()
                    
                    # 💡 v2.0 자금 관리 배분 팩터 및 피라미딩 단계 기본값 설정
                    proposed_alloc_factor = 1.0 # 기본 전체 비중
                    next_stage = 3             # 기본 최종 단계 (피라미딩 불허 시)
                    
                    if existing_holding:
                        # 💡 기존 보유 종목인 경우: 상승장(BULLISH) 모드에서만 피라미딩(불타기) 추가 매수 허용
                        if sentiment != "BULLISH":
                            continue # 하락/횡보장에서는 추가 매수 전면 스킵
                            
                        buy_stage = existing_holding.buy_stage
                        current_price = s['price']
                        profit_rate = ((current_price - existing_holding.avg_price) / existing_holding.avg_price) * 100
                        
                        if buy_stage == 1:
                            # 1단계 -> 2단계 피라미딩 조건: 평단 대비 +3.0% 이상 수익권 & 점수 85점 이상 유지
                            if profit_rate >= 3.0:
                                proposed_alloc_factor = 0.35 # 2차 추가 매수 비중: 35%
                                next_stage = 2
                                log_action(db, user_id, f"[Pyramiding] {ticker} meets 2nd Buy Condition (+{profit_rate:.2f}% profit). Placing 35% confirm order.", "SIGNAL")
                            else:
                                continue
                        elif buy_stage == 2:
                            # 2단계 -> 3단계 피라미딩 조건: 평단 대비 +6.0% 이상 수익권 & 점수 85점 이상 유지
                            if profit_rate >= 6.0:
                                proposed_alloc_factor = 0.50 # 3차 추가 매수 비중: 50%
                                next_stage = 3
                                log_action(db, user_id, f"[Pyramiding] {ticker} meets 3rd Buy Condition (+{profit_rate:.2f}% profit). Placing 50% ultimate order.", "SIGNAL")
                            else:
                                continue

                        else:
                            continue # 이미 3단계 풀배팅 완료 상태
                    else:
                        # 💡 신규 종목 첫 진입인 경우: 장세에 따른 피라미딩(상승장) / 1회성 단일 매수(약세장) 분기
                        if sentiment == "BULLISH":
                            # 상승장: 후지모토 시게루 1:2:6 기법에 따라 15% 비중의 정찰병 우선 진입
                            proposed_alloc_factor = 0.15
                            next_stage = 1
                            log_action(db, user_id, f"[New Entry] {ticker} scanned in BULLISH market. Placing 15% scout order.", "INFO")
                        else:
                            # 하락/횡보장: 피라미딩 금지, 1회성 격리 단일 매수집행 및 비중 제한
                            next_stage = 3 # 추가 불타기 불허
                            if sentiment == "BEARISH":
                                proposed_alloc_factor = 0.30 # 하락장: 비중 30% 제한
                                log_action(db, user_id, f"[New Entry] {ticker} scanned in BEARISH market. Placing 30% single defensive order.", "INFO")
                            else:
                                proposed_alloc_factor = 0.50 # 횡보장: 비중 50% 제한
                                log_action(db, user_id, f"[New Entry] {ticker} scanned in NEUTRAL market. Placing 50% single defensive order.", "INFO")

                    # ① 동적 쿨다운: 동일 종목 매도 후 일정 시간 재매수 금지 (Whipsaw 방지)
                    cooldown_cutoff = datetime.now() - timedelta(minutes=settings.REENTRY_COOLDOWN_MINUTES)
                    recent_sell = db.query(TradeLog).filter(
                        TradeLog.user_id == user_id,
                        TradeLog.ticker == ticker,
                        TradeLog.trade_type == "SELL",
                        TradeLog.executed_at >= cooldown_cutoff
                    ).first()
                    if recent_sell:
                        log_action(db, user_id,
                            f"[BUY SKIP] {ticker} cooldown active — sold at {recent_sell.executed_at.strftime('%H:%M')} ({settings.REENTRY_COOLDOWN_MINUTES}min cooldown).",
                            "INFO")
                        continue

                    # ② 매수 직전 실시간 현재가 재확인 (캐시 데이터 Staleness 방지)
                    realtime_price = await get_realtime_price(ticker)
                    if realtime_price is None:
                        log_action(db, user_id, f"[BUY SKIP] Could not fetch realtime price for {ticker}. Skipping.", "WARNING")
                        continue

                    # ③ 급등 필터: 캐시 가격 대비 20% 이상 급등 시 추격매수 차단
                    cached_price = s['price']
                    price_drift_pct = (realtime_price - cached_price) / cached_price * 100 if cached_price > 0 else 0
                    if price_drift_pct > 20.0:
                        log_action(db, user_id,
                            f"[BUY SKIP] {ticker} has surged +{price_drift_pct:.1f}% since signal cached (${cached_price:.2f} → ${realtime_price:.2f}). Chasing aborted.",
                            "WARNING")
                        continue

                    current_price = realtime_price  # 실시간 가격으로 교체

                    # ④ 잔고 조회 및 달러 환산 (💡 safe_broker_call 세마포어 및 사용자별 로컬 캐시 적용)
                    if cached_balance_data is None:
                        balance_data = await safe_broker_call(broker.get_account_balance)
                        cached_balance_data = balance_data
                    else:
                        balance_data = cached_balance_data
                        
                    total_asset_krw = balance_data.get("total_asset", 10000000.0)
                    cash_balance_krw = balance_data.get("cash_balance", 10000000.0)

                    exchange_rate = FXRateCache.get_rate()

                    total_asset_usd = total_asset_krw / exchange_rate
                    cash_balance_usd = cash_balance_krw / exchange_rate

                    # 💡 [Phase 29] 예수금 안전장치: MIN_CASH_BALANCE_USD 미만 시 조기 차단
                    if cash_balance_usd < settings.MIN_CASH_BALANCE_USD:
                        log_action(db, user_id, f"[BUY SKIP] Insufficient cash balance (${cash_balance_usd:.2f} < ${settings.MIN_CASH_BALANCE_USD:.2f}). Skipping {ticker}.", "WARNING")
                        continue

                    # 기준 투자금 (총 달러 자산의 10%, 최소 $500 보장)
                    base_alloc_usd = max(500.0, total_asset_usd * 0.10)

                    # ATR 변동성 조절 비율
                    atr = s.get('details', {}).get('atr', 0.0)
                    vol_factor = 1.0
                    atr_pct = 0.0
                    if atr > 0:
                        atr_pct = (atr / current_price) * 100
                        if atr_pct > 0:
                            vol_factor = max(0.5, min(1.5, 2.0 / atr_pct))
                    
                    # 시그널 스코어 가중치 배수
                    score = s['signal_score']
                    score_factor = 1.0 + (score - cutoff_score) * 0.05
                    
                    # 💡 희망 달러 투자금 및 주수 계산 (Proposed 비중 팩터 곱해 분할 매수 금액 결정)
                    proposed_value_usd = base_alloc_usd * vol_factor * score_factor * proposed_alloc_factor
                    proposed_qty = proposed_value_usd / current_price
                    
                    # 예수금 안전장치
                    max_order_budget_usd = cash_balance_usd * 0.95
                    
                    # 최종 수량 산출
                    final_qty = int(min(proposed_qty, max_order_budget_usd / current_price))
                    
                    log_action(db, user_id, (
                        f"ENTRY SIGNAL: {ticker} ({score} pts) | Price: ${current_price:.2f} | "
                        f"Alloc Factor: {proposed_alloc_factor:.2f} (Stage: {next_stage}) | "
                        f"Proposed Qty: {proposed_qty:.1f} -> Final Safe Qty: {final_qty} shares"
                    ), "SIGNAL")
                    
                    if final_qty < 1:
                        # 💡 스킵 원인 정밀 판별 (단가 초과 vs 진짜 예수금 부족)
                        is_budget_exceeded = proposed_qty < 1.0
                        
                        if is_budget_exceeded:
                            reason_title = "단가 초과 - 최소 수량 미달"
                            reason_desc = (
                                f"💡 해당 종목의 1주 단가가 이번 매수 시도 금액보다 높습니다.\n"
                                f"1주 미만(소수점 매매 미지원)으로 산출되어 매수가 안전하게 스킵되었습니다.\n"
                                f"포트폴리오 비중을 늘리거나 정찰병 비중을 넓혀보세요."
                            )
                        else:
                            reason_title = "예수금 부족"
                            reason_desc = "💡 계좌의 주문 가능 금액이 한 주를 매수하기에 부족합니다. 계좌 예수금을 충전해 주세요."

                        log_action(db, user_id, (
                            f"SKIP PURCHASE ({reason_title}): {ticker}. "
                            f"Required Price: ${current_price:.2f} > Safe Budget Limit: ${max_order_budget_usd:.2f} | "
                            f"Proposed Qty: {proposed_qty:.2f}"
                        ), "WARNING")
                        
                        # 💡 1시간 동안 중복 실패 경고 스팸 발송 차단 가드 적용
                        if reason_title == "예수금 부족":
                            cache_key = (user_id, "SYSTEM_INSUFFICIENT_CASH")
                        else:
                            cache_key = (user_id, ticker, reason_title)
                        now = time.time()
                        last_sent = WARNING_COOLDOWN_CACHE.get(cache_key, 0.0)
                        
                        if now - last_sent >= 3600.0:  # 1시간 쿨타임
                            current_price_krw = current_price * exchange_rate
                            send_message_async(
                                user_id,
                                f"⚠️ *[자동매수 실패 - {reason_title}]*\n"
                                f"종목: {ticker} ({s['name']})\n\n"
                                f"• *현재가:* `${current_price:,.2f}` (약 {current_price_krw:,.0f}원)\n"
                                f"• *매수 시도 금액:* `${proposed_value_usd:,.2f}`\n"
                                f"• *주문 가능 금액:* `${cash_balance_usd:,.2f}`\n\n"
                                f"{reason_desc}"
                            )
                            WARNING_COOLDOWN_CACHE[cache_key] = now
                        continue
                    
                    # 격리 매수 호출 (💡 safe_broker_call 세마포어 격리 가드 탑재)
                    res = await safe_broker_call(broker.buy_order, ticker, final_qty, price=current_price)

                    if res["success"]:
                        # 💡 주문 성공 시 잔고 상태가 변경되었으므로 다음 루프 시 새로 잔고를 조회하도록 임시 캐시 초기화
                        cached_balance_data = None
                        filled_price = res["filled_price"]
                        filled_qty = res["filled_qty"]
                        
                        if existing_holding:
                            # 💡 기존 보유에 피라미딩 추가 매수인 경우: 평단가 가중 평균 계산 및 수량 증가 업데이트
                            old_qty = existing_holding.quantity
                            old_avg = existing_holding.avg_price
                            
                            new_qty = old_qty + filled_qty
                            new_avg = ((old_avg * old_qty) + (filled_price * filled_qty)) / new_qty
                            
                            existing_holding.avg_price = round(new_avg, 4)
                            existing_holding.quantity = new_qty
                            existing_holding.buy_stage = next_stage
                            existing_holding.highest_price = max(existing_holding.highest_price, filled_price)
                            db.commit()
                            log_action(db, user_id, f"SUCCESS: {ticker} Pyramiding Stage {next_stage} Add-on. New Avg: ${new_avg:.2f}, Total Qty: {new_qty} shares", "INFO")
                        else:
                            # 💡 신규 진입인 경우: Holding 레코드 생성
                            db.add(Holding(
                                user_id=user_id,
                                ticker=ticker,
                                ticker_name=s['name'],
                                avg_price=filled_price,
                                quantity=filled_qty,
                                highest_price=filled_price,
                                regime_mode=sentiment,
                                buy_stage=next_stage
                            ))
                            db.commit()
                            log_action(db, user_id, f"SUCCESS: {ticker} purchased ({filled_qty} shares) | Order: {res['order_no']}", "INFO")
                    else:
                        log_action(db, user_id, f"BUY FAILED: {ticker} | {res['message']}", "ERROR")

        # 성공적으로 자동매매 루프가 수행되었으므로 장애 알림 기록 초기화 (자가 복구 완료)
        _user_network_alert_sent.pop(user_id, None)

    except (RequestsRequestException, httpx.RequestError, ConnectionError, socket.gaierror, socket.timeout, TimeoutError, OSError) as ne:
        db.rollback()
        logger.warning(f"[Scheduler Auto-Recovery] Network disruption detected for User {user_id}. DB rolled back. Error: {ne}")
        
        now = datetime.now()
        last_sent = _user_network_alert_sent.get(user_id)
        if not last_sent or (now - last_sent) > timedelta(minutes=30):
            _user_network_alert_sent[user_id] = now
            send_message_async(
                user_id,
                "⚠️ *[시스템 접속 장애 알림]*\n\n"
                "증권사(KIS) 또는 외부 네트워크 통신에 일시적인 장애가 감지되었습니다.\n"
                "시스템은 자동으로 자가 복구를 시도하며, 연결이 정상화되는 즉시 매매를 재개합니다."
            )
    except Exception as e:
        db.rollback()
        logger.exception(f"[run_user_trading_flow] Error for user {user_id}")
    finally:
        db.close()

async def refresh_scanner_cache():
    """
    마켓 스캐너 캐시를 독립적으로 갱신하는 전용 비동기 함수 (10분 주기).
    자동매매 루프와 완전히 분리되어 Rate Limit 위험 없이 안전하게 동작합니다.
    """
    global latest_scanned_signals
    logger.info("[Scanner Cache] Starting 10-min market scan refresh cycle...")
    try:
        signals = await scan_overseas_market()
        latest_scanned_signals = signals
        logger.info(f"[Scanner Cache] Refresh complete. Cached {len(signals)} signals.")
    except Exception as e:
        logger.exception("[Scanner Cache] ERROR during market scan")

def scanner_cache_wrapper():
    """스캐너 캐시 갱신용 동기 래퍼 (APScheduler 호출용)"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        asyncio.create_task(refresh_scanner_cache())
    else:
        loop.run_until_complete(refresh_scanner_cache())

async def async_trading_loop():
    """
    3-Mode 통합 자율 트레이딩 루프 (멀티유저 동시 기동 지원).
    스캔은 별도 10분 주기 잡에서 수행되며, 여기서는 캐시된 시그널만 사용합니다.
    """
    global is_processing
    if is_processing:
        logger.info("[Scheduler] Previous loop still running. Skipping this cycle.")
        return

    is_processing = True
    db = SessionLocal()
    try:
        # 1. 자동매매 기동 중인 활성 유저 리스트 로드
        active_users = db.query(UserSettings).filter(UserSettings.is_running == True).all()
        if not active_users:
            is_processing = False
            return

        # 2. 캐시된 시그널 사용 (scan_overseas_market 직접 호출 X → Rate Limit 방지)
        all_signals = latest_scanned_signals
        signal_map = {s['ticker']: s for s in all_signals} if all_signals else {}

        # 3. 각 활성 유저별 자동매매 시나리오 병렬 실행
        tasks = [run_user_trading_flow(u.user_id, signal_map, all_signals) for u in active_users]
        await asyncio.gather(*tasks)

    except Exception as e:
        db.rollback()
        logger.exception("[Scheduler] CRITICAL ERROR in trading loop")
    finally:
        is_processing = False
        db.close()

def trading_loop_wrapper():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        asyncio.create_task(async_trading_loop())
    else:
        loop.run_until_complete(async_trading_loop())

def start_scheduler():
    if not scheduler.running:
        # ① 자동매매 루프: 1분 주기 (캐시된 시그널로 봇 실행 사용자 처리)
        scheduler.add_job(trading_loop_wrapper, 'interval', minutes=1, id='main_trade_job', next_run_time=datetime.now())
        # ② 스캐너 캐시 갱신: 10분 주기 (yfinance 대규모 API 호출 - Rate Limit 안전)
        scheduler.add_job(scanner_cache_wrapper, 'interval', minutes=10, id='scanner_cache_job', next_run_time=datetime.now())
        # ③ 텔레그램 일일 리포트 발송: 매일 한국시간 17:10 (미국장 마감 직후)
        scheduler.add_job(send_daily_report_to_all_users_sync, 'cron', hour=17, minute=10, id='daily_telegram_report_job')
        scheduler.start()
        logger.info("Background scheduler started (Multi-tenant 3-Mode Unified Engine).")
        logger.info("  - main_trade_job  : every 1 min  (trading logic, uses cached signals)")
        logger.info("  - scanner_cache_job: every 10 min (market scan + cache refresh)")
        logger.info("  - daily_telegram_report_job: daily at 17:10 KST")
