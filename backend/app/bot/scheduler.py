from apscheduler.schedulers.background import BackgroundScheduler
from app.bot.broker_factory import get_broker_client
from app.core.database import SessionLocal
from app.core.models import TradeLog, Holding, ActionLog, UserSettings
from datetime import datetime, timezone, timedelta
import asyncio
import yfinance as yf  # pyrefly: ignore [missing-import]


from app.scanner.scanner import scan_overseas_market, analyze_single_ticker

scheduler = BackgroundScheduler()


is_processing = False # 중복 실행 방지용 플래그
latest_scanned_signals = [] # 글로벌 실시간 마켓 스캔 시그널 캐시용

ET = timezone(timedelta(hours=-5)) # 미국 동부 표준시(ET)는 UTC-5 (DST 시 UTC-4, 추후 자동화 가능)

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
    yfinance 1분봉 최신 1개봉 활용 (Period: 1d, Interval: 1m)
    """
    try:
        df = await asyncio.to_thread(yf.download, ticker, period="1d", interval="1m", progress=False)
        if df.empty:
            return None
        if hasattr(df.columns, 'get_level_values'):
            df.columns = df.columns.get_level_values(0)
        return float(df['Close'].iloc[-1])
    except Exception as e:
        print(f"[RealTimePrice] Failed to fetch {ticker}: {e}")
        return None


def log_action(db, user_id: int, message: str, level="INFO"):
    """활동 로그를 특정 사용자의 ID로 DB에 기록합니다."""
    db.add(ActionLog(user_id=user_id, message=message, level=level))
    db.commit()
    print(f"[{level}] [User {user_id}] {message}")

async def run_user_trading_flow(user_id: int, signal_map: dict, all_signals: list):
    """
    개별 사용자별 독자적인 자동매매 시나리오 처리 함수 (멀티테넌시 격리)
    """
    db = SessionLocal()
    try:
        # 사용자 설정 로드
        user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not user_settings or not user_settings.is_running:
            return

        log_action(db, user_id, f"Scan Cycle Started (Mode: {user_settings.trade_mode})")

        # 1. 사용자 맞춤형 브로커 인스턴스 획득
        broker = get_broker_client(user_settings)

        # 2. 보유 종목(Holdings) 모니터링 및 매도 판정
        holdings = db.query(Holding).filter(Holding.user_id == user_id).all()
        for h in holdings:
            try:
                ticker = h.ticker
                current_data = signal_map.get(ticker)
                
                # 스캐너 후보군에 없더라도 보유 종목은 정밀 단독 기술 분석 수행
                if not current_data:
                    print(f"[Scheduler User {user_id}] Owned ticker {ticker} not in top scanned signals. Running dedicated technical analysis...")
                    current_data = await analyze_single_ticker(ticker)
                
                if not current_data:
                    log_action(db, user_id, f"No technical data available for owned ticker {ticker}. Skipping monitoring in this cycle.", "WARNING")
                    continue
                
                current_price = current_data['price']
                profit_rate = ((current_price - h.avg_price) / h.avg_price) * 100
                current_score = current_data['signal_score']

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
                
                # 지표 1. 동적 손절선 돌파
                if profit_rate <= -stop_loss_pct:
                    sell_reason = f"Dynamic Stop Loss ({profit_rate:.2f}% <= -{stop_loss_pct:.2f}%)"
                
                # 지표 2. 동적 트레일링 스탑 돌파
                elif current_price <= h.highest_price * (1 - trailing_stop_pct / 100) and h.highest_price > h.avg_price:
                    sell_reason = f"Dynamic Trailing Stop (-{trailing_stop_pct:.2f}% from peak ${h.highest_price})"
                
                # 지표 3. 기술적 강세 시그널 붕괴
                elif current_score < 40:
                    sell_reason = f"Signal Weakened ({current_score} pts - EMA/VWAP breakdown or Selling pressure)"

                if sell_reason:
                    log_action(db, user_id, f"EXIT SIGNAL: {ticker} | Reason: {sell_reason}", "SIGNAL")
                    
                    # 브로커를 통한 격리 매도 호출
                    res = broker.sell_order(ticker, h.quantity, price=current_price)

                    if res["success"]:
                        db.add(TradeLog(
                            user_id=user_id,
                            ticker=ticker,
                            ticker_name=h.ticker_name,
                            trade_type="SELL",
                            price=res["filled_price"],
                            quantity=res["filled_qty"],
                            order_no=res["order_no"]
                        ))
                        db.delete(h)
                        db.commit()
                        log_action(db, user_id, f"SUCCESS: {ticker} sold via {sell_reason} | Order: {res['order_no']}", "INFO")
                        
                        # 💡 텔레그램 매도 알림 전송 (Phase 11 멀티유저)
                        from app.core.telegram import send_message_async
                        send_message_async(
                            user_id,
                            f"🔴 *[자동매도 체결]* {ticker} ({h.ticker_name})\n"
                            f"• *체결 단가:* `${res['filled_price']:,.2f}`\n"
                            f"• *체결 수량:* `{res['filled_qty']}주`\n"
                            f"• *매도 사유:* {sell_reason}\n"
                            f"• *주문 번호:* `{res['order_no']}`"
                        )
                    else:
                        log_action(db, user_id, f"SELL FAILED: {ticker} | {res['message']}", "ERROR")
            except Exception as item_err:
                log_action(db, user_id, f"Error processing holding {h.ticker}: {item_err}", "ERROR")

        # 3. 신규 매수 기회 탐색
        # ① 미국 장 운영 시간 외에는 매수 시도 자체를 스킵 (장외 오더 방지)
        if not is_us_market_open():
            log_action(db, user_id, "[BUY SKIP] US market is currently closed. No new buy orders placed.", "INFO")
        elif all_signals:
            for s in all_signals:
                if s['signal_score'] >= 80:
                    ticker = s['ticker']
                    # 동일 사용자가 이미 보유 중인지 격리 조회
                    if db.query(Holding).filter(Holding.user_id == user_id, Holding.ticker == ticker).first():
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

                    # ④ 잔고 조회 및 달러 환산
                    balance_data = broker.get_account_balance()
                    total_asset_krw = balance_data.get("total_asset", 10000000.0)
                    cash_balance_krw = balance_data.get("cash_balance", 10000000.0)

                    from app.bot.fx_cache import FXRateCache
                    exchange_rate = FXRateCache.get_rate()

                    total_asset_usd = total_asset_krw / exchange_rate
                    cash_balance_usd = cash_balance_krw / exchange_rate

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
                    score_factor = 1.0 + (score - 80) * 0.05
                    
                    # 희망 달러 투자금 및 주수 계산
                    proposed_value_usd = base_alloc_usd * vol_factor * score_factor
                    proposed_qty = proposed_value_usd / current_price
                    
                    # 예수금 안전장치
                    max_order_budget_usd = cash_balance_usd * 0.95
                    
                    # 최종 수량 산출
                    final_qty = int(min(proposed_qty, max_order_budget_usd / current_price))
                    
                    log_action(db, user_id, (
                        f"ENTRY SIGNAL: {ticker} ({score} pts) | Price: ${current_price:.2f} | "
                        f"ATR: {atr:.4f} ({atr_pct:.1f}%) -> VolFactor: {vol_factor:.2f} | "
                        f"Proposed Qty: {proposed_qty:.1f} -> Final Safe Qty: {final_qty} shares "
                        f"(Budget Max: ${max_order_budget_usd:.1f})"
                    ), "SIGNAL")
                    
                    if final_qty < 1:
                        log_action(db, user_id, (
                            f"SKIP PURCHASE: Insufficient available cash for {ticker}. "
                            f"Required price: ${current_price:.2f} > Max Budget: ${max_order_budget_usd:.2f}"
                        ), "WARNING")
                        continue
                    
                    # 격리 매수 호출
                    res = broker.buy_order(ticker, final_qty, price=current_price)

                    if res["success"]:
                        db.add(Holding(
                            user_id=user_id,
                            ticker=ticker,
                            ticker_name=s['name'],
                            avg_price=res["filled_price"],
                            quantity=res["filled_qty"],
                            highest_price=res["filled_price"]
                        ))
                        db.add(TradeLog(
                            user_id=user_id,
                            ticker=ticker,
                            ticker_name=s['name'],
                            trade_type="BUY",
                            price=res["filled_price"],
                            quantity=res["filled_qty"],
                            order_no=res["order_no"]
                        ))
                        db.commit()
                        log_action(db, user_id, f"SUCCESS: {ticker} purchased ({res['filled_qty']} shares) | Order: {res['order_no']}", "INFO")
                        
                        # 💡 텔레그램 매수 알림 전송 (Phase 11 멀티유저)
                        from app.core.telegram import send_message_async
                        send_message_async(
                            user_id,
                            f"🟢 *[자동매수 체결]* {ticker} ({s['name']})\n"
                            f"• *체결 단가:* `${res['filled_price']:,.2f}`\n"
                            f"• *체결 수량:* `{res['filled_qty']}주`\n"
                            f"• *시그널 스코어:* `{score}점`\n"
                            f"• *주문 번호:* `{res['order_no']}`"
                        )
                    else:
                        log_action(db, user_id, f"BUY FAILED: {ticker} | {res['message']}", "ERROR")

    except Exception as e:
        print(f"[run_user_trading_flow] Error for user {user_id}: {e}")
    finally:
        db.close()

async def refresh_scanner_cache():
    """
    마켓 스캐너 캐시를 독립적으로 갱신하는 전용 비동기 함수 (10분 주기).
    자동매매 루프와 완전히 분리되어 Rate Limit 위험 없이 안전하게 동작합니다.
    """
    global latest_scanned_signals
    print("[Scanner Cache] Starting 10-min market scan refresh cycle...")
    try:
        signals = await scan_overseas_market()
        latest_scanned_signals = signals
        print(f"[Scanner Cache] Refresh complete. Cached {len(signals)} signals.")
    except Exception as e:
        print(f"[Scanner Cache] ERROR during market scan: {e}")

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
        print("[Scheduler] Previous loop still running. Skipping this cycle.")
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
        print(f"[Scheduler] CRITICAL ERROR in trading loop: {e}")
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
        scheduler.start()
        print("Background scheduler started (Multi-tenant 3-Mode Unified Engine).")
        print("  - main_trade_job  : every 1 min  (trading logic, uses cached signals)")
        print("  - scanner_cache_job: every 10 min (market scan + cache refresh)")
