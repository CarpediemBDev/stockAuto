from apscheduler.schedulers.background import BackgroundScheduler
from app.bot.kis_api import KISClient
from app.core.database import SessionLocal
from app.core.models import BotStatus, TradeLog, Holding, ActionLog
from datetime import datetime
import asyncio

from app.scanner.scanner import scan_overseas_market
from app.core.config import settings

kis_client = KISClient()
scheduler = BackgroundScheduler()

# 전역 상태 및 캐시
latest_scanned_signals = []
is_processing = False # 중복 실행 방지용 플래그

def log_action(db, message, level="INFO"):
    """활동 로그를 DB에 기록합니다."""
    db.add(ActionLog(message=message, level=level))
    db.commit()
    print(f"[{level}] {message}")

async def async_trading_loop():
    """
    하이브리드 전략(트레일링 스탑 + 시그널 감시)이 적용된 자율 트레이딩 루프
    """
    global is_processing
    if is_processing:
        print("[Scheduler] Previous loop still running. Skipping this cycle.")
        return
        
    is_processing = True
    db = SessionLocal()
    try:
        # 1. 시스템 상태 확인
        status = db.query(BotStatus).first()
        if not status or not status.is_running:
            is_processing = False
            return

        is_real_enabled = settings.IS_REAL and status.is_real_enabled
        log_action(db, f"Scan Cycle Started (Mode: {settings.TRADE_MODE})")

        # 2. 실시간 마켓 스캔 (신규 매수 및 기존 보유주 시그널 업데이트용)
        global latest_scanned_signals
        all_signals = await scan_overseas_market()
        latest_scanned_signals = all_signals if all_signals else []
        
        signal_map = {s['ticker']: s for s in all_signals} if all_signals else {}

        # 3. 보유 종목(Holdings) 모니터링 및 매도 판정
        holdings = db.query(Holding).all()
        for h in holdings:
            try:
                ticker = h.ticker
                current_data = signal_map.get(ticker)
                if not current_data:
                    continue
                
                current_price = current_data['price']
                profit_rate = ((current_price - h.avg_price) / h.avg_price) * 100
                current_score = current_data['signal_score']

                # 최고가(Peak) 갱신
                if current_price > h.highest_price:
                    h.highest_price = current_price
                    log_action(db, f"New Peak for {ticker}: ${current_price}", "SIGNAL")
                    db.commit()

                # 3-1. ATR 기반 동적 익절/손절선 계산
                atr = current_data.get('details', {}).get('atr', 0.0)
                stop_loss_pct = 3.0 # 디폴트 3%
                trailing_stop_pct = 2.0 # 디폴트 2%
                
                if atr > 0:
                    atr_pct = (atr / current_price) * 100
                    # 최소값 보장 및 ATR의 1.5배/1.0배 동적 반영하여 변동성 노이즈 털림 방지
                    stop_loss_pct = max(3.0, atr_pct * 1.5)
                    trailing_stop_pct = max(2.0, atr_pct * 1.0)

                # 매도 조건 체크
                sell_reason = None
                if profit_rate <= -stop_loss_pct:
                    sell_reason = f"Dynamic Stop Loss ({profit_rate:.2f}% <= -{stop_loss_pct:.2f}%)"
                elif current_price <= h.highest_price * (1 - trailing_stop_pct / 100) and profit_rate > 0:
                    sell_reason = f"Dynamic Trailing Stop (-{trailing_stop_pct:.2f}% from peak ${h.highest_price})"
                elif current_score < 40:
                    sell_reason = f"Signal Weakened ({current_score} pts)"

                if sell_reason:
                    log_action(db, f"EXIT SIGNAL: {ticker} | Reason: {sell_reason}", "SIGNAL")
                    
                    if not is_real_enabled:
                        res = {"rt_cd": "0", "msg1": "Simulated", "output": {"ODNO": "MOCK-SELL"}}
                    else:
                        res = kis_client.sell_overseas_order(ticker, h.quantity, price=current_price)

                    if res and res.get("rt_cd") == "0":
                        order_no = res.get("output", {}).get("ODNO", "")
                        db.add(TradeLog(ticker=ticker, ticker_name=h.ticker_name, trade_type="SELL", price=current_price, quantity=h.quantity, order_no=order_no))
                        db.delete(h)
                        db.commit()
                        log_action(db, f"SUCCESS: {ticker} sold via {sell_reason}", "INFO")
            except Exception as item_err:
                log_action(db, f"Error processing holding {h.ticker}: {item_err}", "ERROR")

        # 4. 신규 매수 기회 탐색
        if all_signals:
            for s in all_signals:
                if s['signal_score'] >= 80:
                    ticker = s['ticker']
                    if db.query(Holding).filter(Holding.ticker == ticker).first():
                        continue
                        
                    log_action(db, f"ENTRY SIGNAL: {ticker} ({s['signal_score']} pts)", "SIGNAL")
                    
                    if not is_real_enabled:
                        res = {"rt_cd": "0", "msg1": "Simulated", "output": {"ODNO": "MOCK-BUY"}}
                    else:
                        res = kis_client.buy_overseas_order(ticker, 1, price=s['price'])

                    if res and res.get("rt_cd") == "0":
                        order_no = res.get("output", {}).get("ODNO", "")
                        db.add(Holding(ticker=ticker, ticker_name=s['name'], avg_price=s['price'], quantity=1, highest_price=s['price']))
                        db.add(TradeLog(ticker=ticker, ticker_name=s['name'], trade_type="BUY", price=s['price'], quantity=1, order_no=order_no))
                        db.commit()
                        log_action(db, f"SUCCESS: {ticker} purchased", "INFO")

    except Exception as e:
        log_action(db, f"CRITICAL ERROR in trading loop: {str(e)}", "ERROR")
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
        scheduler.add_job(trading_loop_wrapper, 'interval', minutes=1, id='main_trade_job', next_run_time=datetime.now())
        scheduler.start()
        print("Background scheduler started (Hybrid Mode).")
