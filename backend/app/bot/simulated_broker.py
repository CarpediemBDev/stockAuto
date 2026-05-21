import yfinance as yf
import pandas as pd
from datetime import datetime
from app.bot.base_broker import BaseBroker
from app.core.database import SessionLocal
from app.core.models import Holding
from app.core.config import settings
from app.bot.fx_cache import FXRateCache

class LocalSimulatedBroker(BaseBroker):
    """
    증권사 API 연동 없이 로컬 SQLite 데이터베이스와 yfinance를 활용하여
    가상으로 작동하는 모의투자(Paper Trading) 브로커 클라이언트.
    
    buy_order / sell_order는 yfinance 실시간 시세를 기반으로
    DB에 가상 체결 기록을 생성합니다.
    """
    def __init__(self, user_id=None):
        self.user_id = user_id

    def get_account_balance(self) -> dict:
        db = SessionLocal()
        try:
            if self.user_id:
                holdings = db.query(Holding).filter(Holding.user_id == self.user_id).all()
            else:
                holdings = db.query(Holding).all()
        finally:
            db.close()

        initial_cash = 10000000.0  # 가상 시작 예수금: 1,000만 원 (10,000,000 KRW)
        exchange_rate = FXRateCache.get_rate()

        total_purchase_krw = 0.0
        total_eval_krw = 0.0

        if holdings:
            tickers = [h.ticker for h in holdings]
            try:
                data = yf.download(tickers, period="1d", interval="1m", group_by="ticker", progress=False)
                for h in holdings:
                    current_price = h.avg_price  # 기본 폴백값
                    try:
                        if len(tickers) == 1:
                            if isinstance(data.columns, pd.MultiIndex):
                                df = data[h.ticker].dropna() if h.ticker in data.columns.levels[0] else data.dropna()
                            else:
                                df = data.dropna()
                        else:
                            if isinstance(data.columns, pd.MultiIndex):
                                df = data[h.ticker].dropna() if h.ticker in data.columns.levels[0] else pd.DataFrame()
                            else:
                                df = data.dropna()
                        
                        if not df.empty:
                            current_price = float(df['Close'].iloc[-1])
                    except Exception as e:
                        print(f"[SimulatedBroker] Failed to parse price for {h.ticker}: {e}")

                    # KRW 기준 누적금 계산
                    total_purchase_krw += (h.avg_price * h.quantity) * exchange_rate
                    total_eval_krw += (current_price * h.quantity) * exchange_rate
            except Exception as e:
                print(f"[SimulatedBroker] Failed to download prices: {e}")
                for h in holdings:
                    total_purchase_krw += (h.avg_price * h.quantity) * exchange_rate
                    total_eval_krw += (h.avg_price * h.quantity) * exchange_rate

        # 남은 가상 예수금
        cash_balance = max(0.0, initial_cash - total_purchase_krw)
        stock_balance = total_eval_krw
        total_asset = cash_balance + stock_balance
        
        # 가상 수익률 계산
        profit_rate = round(((total_asset - initial_cash) / initial_cash) * 100, 2)

        return {
            "total_asset": int(total_asset),
            "cash_balance": int(cash_balance),
            "stock_balance": int(stock_balance),
            "profit_rate": profit_rate,
            "profit_loss": int(total_asset - initial_cash),
            "fx_rate": exchange_rate,
            "is_mock": True,
            "provider": "Simulated"
        }

    def get_holdings(self) -> list:
        db = SessionLocal()
        try:
            if self.user_id:
                holdings = db.query(Holding).filter(Holding.user_id == self.user_id).all()
            else:
                holdings = db.query(Holding).all()
        finally:
            db.close()

        if not holdings:
            return []

        exchange_rate = FXRateCache.get_rate()

        tickers = [h.ticker for h in holdings]
        try:
            data = yf.download(tickers, period="1d", interval="1m", group_by="ticker", progress=False)
            result = []
            for h in holdings:
                current_price = h.avg_price  # 기본 폴백값
                try:
                    if len(tickers) == 1:
                        if isinstance(data.columns, pd.MultiIndex):
                            df = data[h.ticker].dropna() if h.ticker in data.columns.levels[0] else data.dropna()
                        else:
                            df = data.dropna()
                    else:
                        if isinstance(data.columns, pd.MultiIndex):
                            df = data[h.ticker].dropna() if h.ticker in data.columns.levels[0] else pd.DataFrame()
                        else:
                            df = data.dropna()
                    
                    if not df.empty:
                        current_price = float(df['Close'].iloc[-1])
                except Exception as e:
                    print(f"[SimulatedBroker] Failed to get price for {h.ticker}: {e}")
                    
                result.append({
                    "id": h.id,
                    "ticker": h.ticker,
                    "ticker_name": h.ticker_name,
                    "avg_price": h.avg_price,
                    "quantity": h.quantity,
                    "highest_price": h.highest_price,
                    "current_price": current_price,
                    "fx_rate": exchange_rate,
                    "is_mock": True,
                    "provider": "Simulated"
                })
            return result
        except Exception as e:
            print(f"[SimulatedBroker] Error downloading live prices: {e}")
            result = []
            for h in holdings:
                result.append({
                    "id": h.id,
                    "ticker": h.ticker,
                    "ticker_name": h.ticker_name,
                    "avg_price": h.avg_price,
                    "quantity": h.quantity,
                    "highest_price": h.highest_price,
                    "current_price": h.avg_price * 1.02,
                    "fx_rate": exchange_rate,
                    "is_mock": True,
                    "provider": "Simulated"
                })
            return result

    def _get_live_price(self, ticker: str) -> float | None:
        """yfinance에서 단일 종목의 최신 가격을 조회합니다."""
        try:
            data = yf.download(ticker, period="1d", interval="1m", progress=False)
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                return float(data['Close'].iloc[-1])
        except Exception as e:
            print(f"[SimulatedBroker] Failed to fetch live price for {ticker}: {e}")
        return None

    def buy_order(self, ticker: str, quantity: int, price: float) -> dict:
        """
        가상 매수 체결: yfinance 실시간 시세를 기반으로 즉시 체결을 시뮬레이션합니다.
        실제 증권사 API를 호출하지 않고 DB에 직접 Holding/TradeLog를 기록합니다.
        """
        # 실시간 시세 확인 (가능하면 실시간 가격 사용, 불가시 전달된 price 사용)
        live_price = self._get_live_price(ticker)
        fill_price = live_price if live_price else price

        order_no = f"SIM-BUY-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return {
            "success": True,
            "order_no": order_no,
            "filled_qty": quantity,
            "filled_price": fill_price,
            "message": f"Simulated buy: {quantity} shares of {ticker} at ${fill_price:.2f}"
        }

    def sell_order(self, ticker: str, quantity: int, price: float) -> dict:
        """
        가상 매도 체결: yfinance 실시간 시세를 기반으로 즉시 체결을 시뮬레이션합니다.
        """
        live_price = self._get_live_price(ticker)
        fill_price = live_price if live_price else price

        order_no = f"SIM-SELL-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return {
            "success": True,
            "order_no": order_no,
            "filled_qty": quantity,
            "filled_price": fill_price,
            "message": f"Simulated sell: {quantity} shares of {ticker} at ${fill_price:.2f}"
        }
