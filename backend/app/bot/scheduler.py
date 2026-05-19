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
                        
                    # 4-1. 계좌 예수금 및 환율 조회 (수량 계산 및 예수금 한도 체크용)
                    balance_data = kis_client.get_account_balance()
                    total_asset_krw = balance_data.get("total_asset", 15420000.0)
                    cash_balance_krw = balance_data.get("cash_balance", 4500000.0)
                    
                    # 실시간 환율 조회 (기본 1350원 가정)
                    exchange_rate = 1350.0
                    try:
                        import yfinance as yf
                        import pandas as pd
                        df_fx = await asyncio.to_thread(yf.download, "USDKRW=X", period="1d", progress=False)
                        if not df_fx.empty:
                            if isinstance(df_fx.columns, pd.MultiIndex):
                                df_fx.columns = df_fx.columns.get_level_values(0)
                            exchange_rate = float(df_fx['Close'].iloc[-1])
                    except Exception as fx_err:
                        print(f"[Scheduler] FX rate fetch error: {fx_err}")
                    
                    # 자산을 달러로 환산
                    total_asset_usd = total_asset_krw / exchange_rate
                    cash_balance_usd = cash_balance_krw / exchange_rate
                    
                    # 4-2. 기준 투자금 (총 달러 자산의 10%, 최소 $500 보장)
                    base_alloc_usd = max(500.0, total_asset_usd * 0.10)
                    
                    # 4-3. ATR 변동성 조절 비율 (Volatility Factor)
                    current_price = s['price']
                    atr = s.get('details', {}).get('atr', 0.0)
                    
                    vol_factor = 1.0
                    atr_pct = 0.0
                    if atr > 0:
                        atr_pct = (atr / current_price) * 100
                        if atr_pct > 0:
                            vol_factor = max(0.5, min(1.5, 2.0 / atr_pct))
                    
                    # 4-4. 시그널 스코어 가중치 배수 (Signal Factor)
                    # 80점 = 1.0배, 90점 = 1.5배, 100점 = 2.0배
                    score = s['signal_score']
                    score_factor = 1.0 + (score - 80) * 0.05
                    
                    # 4-5. 희망 달러 투자금 및 주수 계산
                    proposed_value_usd = base_alloc_usd * vol_factor * score_factor
                    proposed_qty = proposed_value_usd / current_price
                    
                    # 4-6. 2차 방어막 (예수금 안전장치: 남은 예수금의 95%로 예산 한도 설정)
                    max_order_budget_usd = cash_balance_usd * 0.95
                    
                    # 최종 수량 산출 (소수점 버림)
                    final_qty = int(min(proposed_qty, max_order_budget_usd / current_price))
                    
                    log_action(db, (
                        f"ENTRY SIGNAL: {ticker} ({score} pts) | Price: ${current_price:.2f} | "
                        f"ATR: {atr:.4f} ({atr_pct:.1f}%) -> VolFactor: {vol_factor:.2f} | "
                        f"Proposed Qty: {proposed_qty:.1f} -> Final Safe Qty: {final_qty} shares "
                        f"(Budget Max: ${max_order_budget_usd:.1f})"
                    ), "SIGNAL")
                    
                    # 최종 수량이 1주 미만(0주)인 경우 매수 스킵
                    if final_qty < 1:
                        log_action(db, (
                            f"SKIP PURCHASE: Insufficient available cash for {ticker}. "
                            f"Required price: ${current_price:.2f} > Max Budget: ${max_order_budget_usd:.2f}"
                        ), "WARNING")
                        continue
                    
                    if not is_real_enabled:
                        res = {"rt_cd": "0", "msg1": "Simulated", "output": {"ODNO": "MOCK-BUY"}}
                    else:
                        res = kis_client.buy_overseas_order(ticker, final_qty, price=current_price)

                    if res and res.get("rt_cd") == "0":
                        order_no = res.get("output", {}).get("ODNO", "")
                        db.add(Holding(ticker=ticker, ticker_name=s['name'], avg_price=current_price, quantity=final_qty, highest_price=current_price))
                        db.add(TradeLog(ticker=ticker, ticker_name=s['name'], trade_type="BUY", price=current_price, quantity=final_qty, order_no=order_no))
                        db.commit()
                        log_action(db, f"SUCCESS: {ticker} purchased ({final_qty} shares)", "INFO")

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
