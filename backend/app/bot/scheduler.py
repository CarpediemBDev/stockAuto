from apscheduler.schedulers.background import BackgroundScheduler
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import TradeLog, Holding, ActionLog, UserSettings
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import asyncio
import threading
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
_processing_lock = threading.Lock()  # 💡 is_processing 레이스 컨디션 방지용 스레드 락
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
    개별 사용자별 독자적인 자동매매 시나리오 처리 함수 (멀티테넌시 격리)
    ⭐ 격리형 3슬롯 멀티 전략 코어 (Modular Multi-Strategy Isolation) 실전 가동
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

        # 💡 멀티 전략 매니저 로드
        from app.bot.multi_strategy_manager import MultiStrategyManager
        strategy_type = getattr(user_settings, "strategy_type", "regime_switching")
        ms_manager = MultiStrategyManager(strategy_type=strategy_type)
        first_slot_key = list(ms_manager.SLOTS.keys())[0]

        # 2. 보유 종목(Holdings) 모니터링 및 매도/탈출 판정 (조기 익절 & 트레일링 스탑)
        holdings = db.query(Holding).filter(Holding.user_id == user_id).all()
        
        # 💡 레거시 마이그레이션 가드: 접두사 없는 기존 종목에 자동으로 첫 번째 슬롯 접두사 부여
        for h in holdings:
            if not ms_manager.get_slot_by_holding_ticker(h.ticker):
                legacy_ticker = h.ticker
                h.ticker = ms_manager.make_prefixed_ticker(first_slot_key, legacy_ticker)
                db.commit()
                log_action(db, user_id, f"[Migration Guard] Legacy holding migrated: {legacy_ticker} -> {h.ticker}", "INFO")

        # 💡 [Self-Healing] 보유 종목 실시간 계좌 정합성 동기화 가드 (Holding Sync Guard)
        # DB와 실제 증권사 계좌 보유 종목 간 유령 누락 및 수량 불일치 정화
        try:
            real_holdings = await safe_broker_call(broker.get_holdings)
            db_holdings_map = {db_h.ticker: db_h for db_h in holdings}
            real_ticker_set = set()
            
            for rh in real_holdings:
                r_ticker = rh.get("ticker", "")
                r_qty = int(rh.get("quantity", 0))
                r_price = float(rh.get("avg_price", 0.0))
                r_name = rh.get("ticker_name", r_ticker)
                
                if r_qty <= 0:
                    continue
                    
                real_ticker_set.add(r_ticker)
                
                # 접두사가 붙은 형태(EP_ASTC, RS_ASTC)로 DB에 있는지 탐색
                found_in_db = False
                for slot_key, cfg in ms_manager.SLOTS.items():
                    prefixed = ms_manager.make_prefixed_ticker(slot_key, r_ticker)
                    if prefixed in db_holdings_map:
                        found_in_db = True
                        db_h = db_holdings_map[prefixed]
                        # 수량 불일치 시 DB 동기화 강제 정화
                        if db_h.quantity != r_qty:
                            log_action(db, user_id, f"[Sync Guard] Quantity discrepancy fixed for {prefixed}: {db_h.quantity} -> {r_qty}", "WARNING")
                            db_h.quantity = r_qty
                            db.commit()
                        break
                
                if not found_in_db:
                    # DB에 유령 누락된 실제 보유 주식 발견! 자가 치료(Self-Healing) 작동
                    last_buy = db.query(TradeLog).filter(
                        TradeLog.user_id == user_id,
                        TradeLog.ticker.like(f"%_{r_ticker}"),
                        TradeLog.trade_type == "BUY"
                    ).order_by(TradeLog.executed_at.desc()).first()
                    
                    target_prefixed_ticker = None
                    if last_buy:
                        target_prefixed_ticker = last_buy.ticker
                    else:
                        target_prefixed_ticker = ms_manager.make_prefixed_ticker(first_slot_key, r_ticker)
                        
                    log_action(db, user_id, f"[Self-Healing] Phantom holding detected in account: {r_ticker} (Qty: {r_qty}). Restoring DB record as {target_prefixed_ticker}!", "ERROR")
                    
                    db.add(Holding(
                        user_id=user_id,
                        ticker=target_prefixed_ticker,
                        ticker_name=r_name,
                        avg_price=r_price,
                        quantity=r_qty,
                        highest_price=r_price,
                        regime_mode=sentiment,
                        buy_stage=1
                    ))
                    db.commit()
            
            # DB에는 있으나 실제 증권사 계좌에는 없는 종목 자동 청소 (장외 수동 청산 등 대응)
            for db_h in holdings:
                parsed = ms_manager.get_slot_by_holding_ticker(db_h.ticker)
                if parsed:
                    _, clean_t = parsed
                    if clean_t not in real_ticker_set:
                        log_action(db, user_id, f"[Self-Healing] DB Holding {db_h.ticker} does not exist in actual broker account. Sweeping legacy DB record.", "ERROR")
                        db.delete(db_h)
                        db.commit()
                        
            # 정화 후 DB holdings 최종 갱신
            holdings = db.query(Holding).filter(Holding.user_id == user_id).all()
        except Exception as sync_err:
            log_action(db, user_id, f"[Self-Healing] Failed to sync holding discrepancy: {sync_err}", "ERROR")

        # 💡 KIS 및 Simulated 잔고 실시간 조회 (Rate Limit 세마포어 적용)
        balance_data = await safe_broker_call(broker.get_account_balance)
        total_asset_krw = balance_data.get("total_asset", 10000000.0)
        cash_balance_krw = balance_data.get("cash_balance", 10000000.0)

        exchange_rate = FXRateCache.get_rate()
        total_asset_usd = total_asset_krw / exchange_rate
        cash_balance_usd = cash_balance_krw / exchange_rate

        # 💡 각 슬롯별 실시간 격리 예수금(Cash Balance) 및 평가자산 분배
        slot_allocations = ms_manager.calculate_slots_allocation(total_asset_usd, cash_balance_usd, holdings, sentiment)

        # 3. 11대 정예 포트폴리오 종목 실시간 기술적 분석 및 신규 스캔 시그널 확보
        target_signals = []
        for ticker in ms_manager.TARGET_TICKERS:
            # 스캐너 캐시에서 조회 시도
            sig = signal_map.get(ticker)
            if sig:
                target_signals.append(sig)
            else:
                # 캐시에 없는 경우 백그라운드 단독 정밀 분석 수행 (Dynamic Fallback)
                sig = await analyze_single_ticker(ticker)
                if sig:
                    target_signals.append(sig)

        target_signal_map = {s['ticker']: s for s in target_signals}

        # ------------------ (Part A) 보유 종목 실시간 감시 및 매도 주문 ------------------
        for h in holdings:
            try:
                # 보유 종목의 접두사에서 슬롯과 순수 티커 파싱
                parsed = ms_manager.get_slot_by_holding_ticker(h.ticker)
                if not parsed:
                    continue
                slot_key, clean_ticker = parsed
                
                # 해당 슬롯의 전략 인스턴스 획득
                strategy_instance = ms_manager.strategies[slot_key]
                
                # 실시간 가격 데이터 획득
                current_data = target_signal_map.get(clean_ticker)
                if not current_data:
                    current_data = await analyze_single_ticker(clean_ticker)
                
                if not current_data:
                    log_action(db, user_id, f"No technical data available for owned ticker {clean_ticker}. Skipping monitoring in this cycle.", "WARNING")
                    continue
                
                current_price = current_data['price']
                # 평가가치 업데이트용 임시 보정
                h.current_price = current_price
                
                profit_rate = ((current_price - h.avg_price) / h.avg_price) * 100
                
                # 보유 전략 인스턴스 기준 재계산된 실시간 스코어 및 익절 신호 판정
                current_score = strategy_instance.calculate_score(current_data['details'] or current_data, sentiment, is_entry=False)
                is_smart_exit = current_data.get('details', {}).get('is_smart_exit', False)

                # 최고가(Peak) 갱신
                if current_price > h.highest_price:
                    h.highest_price = current_price
                    log_action(db, user_id, f"[{strategy_instance.name}] New Peak for {clean_ticker}: ${current_price}", "SIGNAL")
                    db.commit()

                # ATR 기반 동적 익절/손절선 계산
                atr = current_data.get('details', {}).get('atr', 0.0)
                stop_loss_pct = strategy_instance.get_stop_loss_pct(atr, current_price)
                trailing_stop_pct = strategy_instance.get_trailing_stop_pct(atr, current_price)

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
                
                # 휩쏘 방지 연속 2회 확정 가드
                if is_breached:
                    cache_key = (user_id, h.ticker)
                    BREACH_COUNT_CACHE[cache_key] = BREACH_COUNT_CACHE.get(cache_key, 0) + 1
                    count = BREACH_COUNT_CACHE[cache_key]
                    
                    if count >= 2:
                        sell_reason = breach_reason + " [2회 연속 이탈 확정]"
                    else:
                        log_action(db, user_id, f"[Noise Buffer] {h.ticker} first breach detected ({breach_reason}). Delaying sell for noise protection (Count: {count}/2).", "INFO")
                else:
                    BREACH_COUNT_CACHE.pop((user_id, h.ticker), None)
                
                # 조기 스마트 익절
                if not sell_reason and profit_rate >= strategy_instance.min_smart_exit_profit and is_smart_exit:
                    sell_reason = f"스마트 조기 익절 (RSI-MACD 조건 충족 | 수익률: {profit_rate:.2f}%)"
                
                # 기술적 강세 시그널 붕괴
                elif not sell_reason and strategy_instance.is_signal_collapsed(current_score, sentiment):
                    sell_reason = f"강세 시그널 붕괴 ({current_score}점 도달)"

                if sell_reason:
                    log_action(db, user_id, f"[{strategy_instance.name}] EXIT SIGNAL: {h.ticker} ({clean_ticker}) | Reason: {sell_reason}", "SIGNAL")
                    
                    # 브로커 주문 시에는 순수 티커(clean_ticker) 전달
                    res = await safe_broker_call(broker.sell_order, clean_ticker, h.quantity, price=current_price)

                    if res["success"]:
                        filled_price = res["filled_price"]
                        filled_qty = res["filled_qty"]
                        
                        # 수수료 및 SEC Fee 차감 정밀 손익 계산
                        buy_gross = h.avg_price * filled_qty
                        buy_fee = buy_gross * settings.KIS_FEE_RATE
                        sell_gross = filled_price * filled_qty
                        sell_fee = sell_gross * settings.KIS_FEE_RATE
                        sec_fee = sell_gross * settings.SEC_FEE_RATE
                        
                        realized_pnl = sell_gross - buy_gross - buy_fee - sell_fee - sec_fee
                        calc_return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0

                        db.add(TradeLog(
                            user_id=user_id,
                            ticker=h.ticker,  # DB 로그에는 접두사가 붙은 티커 기록
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
                        BREACH_COUNT_CACHE.pop((user_id, h.ticker), None)
                        log_action(db, user_id, f"SUCCESS: {h.ticker} sold via {sell_reason} | Order: {res['order_no']}", "INFO")
                        
                        exchange_rate = FXRateCache.get_rate()
                        filled_price_krw = filled_price * exchange_rate
                        total_amount_usd = filled_price * filled_qty
                        total_amount_krw = total_amount_usd * exchange_rate
                        
                        pnl_sign = "+" if realized_pnl >= 0 else "-"
                        pnl_emoji = "📈" if realized_pnl >= 0 else "📉"
                        realized_pnl_abs = abs(realized_pnl)
                        
                        send_message_async(
                            user_id,
                            f"🔴 *[{strategy_instance.name} 자동매도 체결]*\n"
                            f"종목: {clean_ticker} ({h.ticker_name})\n"
                            f"• *체결 단가:* `${filled_price:,.2f}` (약 {filled_price_krw:,.0f}원)\n"
                            f"• *체결 수량:* `{filled_qty}주`\n"
                            f"• *체결 금액:* `${total_amount_usd:,.2f}` (약 {total_amount_krw:,.0f}원)\n"
                            f"• *매도 사유:* {sell_reason}\n\n"
                            f"{pnl_emoji} *실수익률:* `{pnl_sign}{calc_return_rate:.2f}%`\n"
                            f"💰 *실현 실수익:* `{pnl_sign}${realized_pnl_abs:,.2f}`\n"
                            f"• *주문 번호:* `{res['order_no']}`"
                        )
                    else:
                        log_action(db, user_id, f"SELL FAILED: {h.ticker} | {res['message']}", "ERROR")
            except Exception as item_err:
                log_action(db, user_id, f"Error processing holding {h.ticker}: {item_err}", "ERROR")

        # ------------------ (Part B) 3개 슬롯별 신규 매수 기회 검사 및 분할 매수 ------------------
        if not is_us_market_open():
            log_action(db, user_id, "[BUY SKIP] US market is currently closed. No new buy orders placed.", "INFO")
            return

        # 💡 최정예 종목 Focusing 필터 적용 (RVOL >= 2.0 이상 대량 거래량 매집봉 포착 5~10개 엄선)
        focused_tickers = ms_manager.get_focused_tickers(all_signals)
        log_action(db, user_id, f"[Focusing Filter] Selected {len(focused_tickers)} elite tickers for compressed investment: {', '.join(focused_tickers)}", "INFO")

        # 3개 슬롯을 완전히 순차적으로 루프 실행하여 상호 비간섭 격리 상태 유지
        for slot_key, slot_info in slot_allocations.items():
            # 💡 실시간 레짐 수위 조절 장치 (Regime Sluice) 작동
            # QQQ가 BEARISH / NEUTRAL(약세/횡보장)일 때는 마스터 레짐스위칭 V2 슬롯(40% 비중) 매수를 전면 차단하여 현금 100% 보호!
            if slot_key == "regime_switching" and sentiment != "BULLISH":
                log_action(db, user_id, f"[Regime Sluice] Regime Switching V2 slot DEACTIVATED in {sentiment} market to protect 100% cash.", "INFO")
                continue

            strategy_instance = ms_manager.strategies[slot_key]
            slot_cash_usd = slot_info["cash_balance"]
            slot_total_asset_usd = slot_info["total_asset"]
            slot_prefix = slot_info["prefix"]
            
            # 슬롯별 최대 보유 종목 제한 가드 계산 (슬롯별 최대 3종목씩 균등)
            slot_holdings_count = db.query(Holding).filter(
                Holding.user_id == user_id,
                Holding.ticker.like(f"{slot_prefix}%")
            ).count()
            
            # 각 전략별 장세 레짐 커트라인 점수 획득
            cutoff_score = strategy_instance.get_cutoff_score(sentiment)
            
            for s in target_signals:
                clean_ticker = s['ticker']
                
                # 💡 Focusing 필터에 포함된 종목만 진입 허용 (자금 파편화 원천 방지)
                if clean_ticker not in focused_tickers:
                    continue
                
                # 💡 [핵심] 각 전략 기준으로 스코어를 실시간 정밀 재계산 (동적 100% 격리 채점!)
                score = strategy_instance.calculate_score(s.get('details') or s, sentiment, is_entry=True)
                
                if score >= cutoff_score:
                    # 슬롯별 종목 수 제한 안전 가드 (각 슬롯당 최대 3종목 가이드라인 준수)
                    if slot_holdings_count >= 3:
                        continue
                        
                    prefixed_ticker = ms_manager.make_prefixed_ticker(slot_key, clean_ticker)
                    
                    # 해당 슬롯이 동일 종목을 이미 보유하고 있는지 판별 (피라미딩용)
                    existing_holding = db.query(Holding).filter(
                        Holding.user_id == user_id,
                        Holding.ticker == prefixed_ticker
                    ).first()
                    
                    proposed_alloc_factor = 1.0
                    next_stage = 3
                    
                    if existing_holding:
                        # 상승장에서만 불타기 추가 매수 허용
                        pyramid_trigger_1 = strategy_instance.get_pyramid_trigger(1)
                        if pyramid_trigger_1 > 100.0 or sentiment != "BULLISH":
                            continue
                            
                        buy_stage = existing_holding.buy_stage
                        current_price = s['price']
                        profit_rate = ((current_price - existing_holding.avg_price) / existing_holding.avg_price) * 100
                        pyramid_trigger_2 = strategy_instance.get_pyramid_trigger(2)

                        if buy_stage == 1:
                            if profit_rate >= pyramid_trigger_1:
                                proposed_alloc_factor = 0.35
                                next_stage = 2
                                log_action(db, user_id, f"[{strategy_instance.name}] [Pyramiding] {clean_ticker} meets 2nd Buy Condition (+{profit_rate:.2f}% profit). Placing 35% confirm order.", "SIGNAL")
                            else:
                                continue
                        elif buy_stage == 2:
                            if profit_rate >= pyramid_trigger_2:
                                proposed_alloc_factor = 0.50
                                next_stage = 3
                                log_action(db, user_id, f"[{strategy_instance.name}] [Pyramiding] {clean_ticker} meets 3rd Buy Condition (+{profit_rate:.2f}% profit). Placing 50% ultimate order.", "SIGNAL")
                            else:
                                continue
                        else:
                            continue
                    else:
                        # 신규 진입 분기
                        proposed_alloc_factor = strategy_instance.get_initial_entry_factor(sentiment)
                        if sentiment == "BULLISH" and proposed_alloc_factor < 1.0:
                            next_stage = 1  # 정찰병 15% 진입
                            log_action(db, user_id, f"[{strategy_instance.name}] [New Entry] {clean_ticker} scanned. Placing 15% scout order.", "INFO")
                        else:
                            next_stage = 3  # 즉시 풀비중 진입
                            log_action(db, user_id, f"[{strategy_instance.name}] [New Entry] {clean_ticker} scanned. Placing {proposed_alloc_factor*100:.0f}% single defensive order.", "INFO")

                    # ① 동적 쿨다운 검사 (Whipsaw 페이크 가드)
                    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.REENTRY_COOLDOWN_MINUTES)
                    recent_sell = db.query(TradeLog).filter(
                        TradeLog.user_id == user_id,
                        TradeLog.ticker == prefixed_ticker,
                        TradeLog.trade_type == "SELL",
                        TradeLog.executed_at >= cooldown_cutoff
                    ).first()
                    
                    if recent_sell:
                        continue

                    # ② 매수 직전 실시간 현재가 재조회
                    realtime_price = await get_realtime_price(clean_ticker)
                    if realtime_price is None:
                        continue

                    # ③ 급등 차단 필터 (+20% 초과 추격 매입 억제)
                    cached_price = s['price']
                    price_drift_pct = (realtime_price - cached_price) / cached_price * 100 if cached_price > 0 else 0
                    if price_drift_pct > 20.0:
                        log_action(db, user_id, f"[Surge Guard] {clean_ticker} has surged +{price_drift_pct:.1f}% since signal cached. Aborting purchase.", "WARNING")
                        continue

                    current_price = realtime_price

                    # ④ 슬롯 격리 예수금 안전 조건 검증
                    if slot_cash_usd < settings.MIN_CASH_BALANCE_USD:
                        continue

                    # 해당 슬롯의 총 자산 크기를 기준으로 투자 비중 배분
                    base_alloc_usd = slot_total_asset_usd * strategy_instance.base_allocation_pct
                    if strategy_instance.min_allocation_usd > 0.0:
                        base_alloc_usd = max(strategy_instance.min_allocation_usd, base_alloc_usd)

                    # ATR 변동성 조절 비율
                    atr = s.get('details', {}).get('atr', 0.0)
                    vol_factor = 1.0
                    if atr > 0:
                        atr_pct = (atr / current_price) * 100
                        if atr_pct > 0:
                            vol_factor = max(0.5, min(1.5, 2.0 / atr_pct))
                    
                    # 시그널 스코어 승수
                    score_factor = 1.0 + (score - cutoff_score) * 0.05
                    
                    # 슬롯 현금 한도 내 최적 주문 수량 계산
                    proposed_value_usd = base_alloc_usd * vol_factor * score_factor * proposed_alloc_factor
                    proposed_qty = proposed_value_usd / current_price
                    
                    max_order_budget_usd = slot_cash_usd * 0.95
                    final_qty = int(min(proposed_qty, max_order_budget_usd / current_price))
                    
                    if final_qty == 0 and max_order_budget_usd >= current_price:
                        final_qty = 1
                    
                    if final_qty < 1:
                        # 예수금 부족 / 단가 초과 스킵 알림 쿨다운 처리
                        is_budget_exceeded = proposed_qty < 1.0
                        reason_title = "단가 초과 - 최소 수량 미달" if is_budget_exceeded else "예수금 부족"
                        reason_desc = "💡 슬롯 내 주문 가능 현금이 부족합니다." if not is_budget_exceeded else "💡 1주 단가가 슬롯 가용 한도보다 높습니다."
                        
                        log_action(db, user_id, f"[{strategy_instance.name}] SKIP PURCHASE ({reason_title}): {clean_ticker}.", "WARNING")
                        
                        cache_key = (user_id, prefixed_ticker, reason_title)
                        now = time.time()
                        last_sent = WARNING_COOLDOWN_CACHE.get(cache_key, 0.0)
                        
                        if now - last_sent >= 3600.0:
                            current_price_krw = current_price * exchange_rate
                            send_message_async(
                                user_id,
                                f"⚠️ *[{strategy_instance.name} 자동매수 실패 - {reason_title}]*\n"
                                f"종목: {clean_ticker} ({s['name']})\n\n"
                                f"• *현재가:* `${current_price:,.2f}` (약 {current_price_krw:,.0f}원)\n"
                                f"• *매수 시도 금액:* `${proposed_value_usd:,.2f}`\n"
                                f"• *슬롯 예수금:* `${slot_cash_usd:,.2f}`\n\n"
                                f"{reason_desc}"
                            )
                            WARNING_COOLDOWN_CACHE[cache_key] = now
                        continue
                    
                    # 브로커에 실제 순수 티커로 주문 전송
                    res = await safe_broker_call(broker.buy_order, clean_ticker, final_qty, price=current_price)

                    if res["success"]:
                        filled_price = res["filled_price"]
                        filled_qty = res["filled_qty"]
                        
                        # 슬롯 예수금 차감 반영
                        slot_cash_usd -= (filled_price * filled_qty) * (1 + settings.KIS_FEE_RATE)
                        
                        if existing_holding:
                            # 추가 매수 평단가 가중 평균 계산
                            old_qty = existing_holding.quantity
                            old_avg = existing_holding.avg_price
                            
                            new_qty = old_qty + filled_qty
                            new_avg = ((old_avg * old_qty) + (filled_price * filled_qty)) / new_qty
                            
                            existing_holding.avg_price = round(new_avg, 4)
                            existing_holding.quantity = new_qty
                            existing_holding.buy_stage = next_stage
                            existing_holding.highest_price = max(existing_holding.highest_price, filled_price)
                            db.commit()
                            log_action(db, user_id, f"SUCCESS: {prefixed_ticker} Pyramiding Stage {next_stage} Add-on. New Avg: ${new_avg:.2f}", "INFO")
                        else:
                            # 신규 접두사 결합 티커로 Holding 저장
                            db.add(Holding(
                                user_id=user_id,
                                ticker=prefixed_ticker,
                                ticker_name=s['name'],
                                avg_price=filled_price,
                                quantity=filled_qty,
                                highest_price=filled_price,
                                regime_mode=sentiment,
                                buy_stage=next_stage
                            ))
                            db.commit()
                            log_action(db, user_id, f"SUCCESS: {prefixed_ticker} purchased ({filled_qty} shares)", "INFO")
                            
                            # 슬롯 내 종목수 증가 반영
                            slot_holdings_count += 1
                        
                        # 텔레그램 매수 알림 발송
                        current_price_krw = filled_price * exchange_rate
                        total_amount_usd = filled_price * filled_qty
                        total_amount_krw = total_amount_usd * exchange_rate
                        
                        send_message_async(
                            user_id,
                            f"🟢 *[{strategy_instance.name} 자동매수 체결]*\n"
                            f"종목: {clean_ticker} ({s['name']})\n\n"
                            f"• *체결 단가:* `${filled_price:,.2f}` (약 {current_price_krw:,.0f}원)\n"
                            f"• *체결 수량:* `{filled_qty}주` (피라미딩 {next_stage}단계)\n"
                            f"• *체결 금액:* `${total_amount_usd:,.2f}` (약 {total_amount_krw:,.0f}원)\n"
                            f"• *진입 레짐:* `{sentiment}`\n"
                            f"• *주문 번호:* `{res['order_no']}`"
                        )
                    else:
                        log_action(db, user_id, f"BUY FAILED: {prefixed_ticker} | {res['message']}", "ERROR")

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
    
    # 장 외 시간 API 비용/호출 낭비 방지 가드
    if not is_us_market_open():
        logger.info("[Scanner Cache] Market is closed. Skipping scan to save API quotas.")
        return
        
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
        asyncio.run(refresh_scanner_cache())
    except RuntimeError:
        # 💡 이미 실행 중인 이벤트 루프가 있는 경우 (FastAPI/uvicorn 내부 등)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(refresh_scanner_cache())
        else:
            loop.run_until_complete(refresh_scanner_cache())

async def async_trading_loop():
    """
    3-Mode 통합 자율 트레이딩 루프 (멀티유저 동시 기동 지원).
    스캔은 별도 10분 주기 잡에서 수행되며, 여기서는 캐시된 시그널만 사용합니다.
    """
    global is_processing
    with _processing_lock:
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
        asyncio.run(async_trading_loop())
    except RuntimeError:
        # 💡 이미 실행 중인 이벤트 루프가 있는 경우 (FastAPI/uvicorn 내부 등)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(async_trading_loop())
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
