import yfinance as yf
import pandas as pd
from app.bot.base_broker import BaseBroker
from app.core.database import SessionLocal
from app.core.models import Holding
from app.core.config import settings

class LocalSimulatedBroker(BaseBroker):
    """
    API 연동이 없을 때 로컬 SQLite 데이터베이스와 yfinance를 활용하여
    가상으로 작동하는 모의투자(Paper Trading) 브로커 클라이언트.
    """

    def get_account_balance(self) -> dict:
        db = SessionLocal()
        try:
            holdings = db.query(Holding).all()
        finally:
            db.close()

        initial_cash = 10000000.0  # 가상 시작 예수금: 1,000만 원 (10,000,000 KRW)
        exchange_rate = 1350.0      # 기본 환율 폴백
        
        # 실시간 환율 조회
        try:
            df_fx = yf.download("USDKRW=X", period="1d", progress=False)
            if not df_fx.empty:
                if isinstance(df_fx.columns, pd.MultiIndex):
                    df_fx.columns = df_fx.columns.get_level_values(0)
                exchange_rate = float(df_fx['Close'].iloc[-1])
        except Exception as e:
            print(f"[SimulatedBroker] FX rate download failed, using 1350.0: {e}")

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
            holdings = db.query(Holding).all()
        finally:
            db.close()

        if not holdings:
            return []

        exchange_rate = 1350.0
        try:
            df_fx = yf.download("USDKRW=X", period="1d", progress=False)
            if not df_fx.empty:
                if isinstance(df_fx.columns, pd.MultiIndex):
                    df_fx.columns = df_fx.columns.get_level_values(0)
                exchange_rate = float(df_fx['Close'].iloc[-1])
        except Exception as e:
            print(f"[SimulatedBroker] FX rate download failed, using 1350.0: {e}")

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
