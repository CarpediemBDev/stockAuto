import pandas as pd
from app.scanner.data_provider import fetch_bulk_ohlcv_sync, fetch_ohlcv_sync
from datetime import datetime
from app.bot.base_broker import BaseBroker
from app.core.database import SessionLocal
from app.core.models import Holding, TradeLog
from app.core.config import settings
from app.bot.fx_cache import FXRateCache

class LocalSimulatedBroker(BaseBroker):
    """
    증권사 API 연동 없이 로컬 SQLite 데이터베이스와 yfinance를 활용하여
    가상으로 작동하는 모의투자(Paper Trading) 브로커 클라이언트.

    buy_order / sell_order는 yfinance 실시간 시세를 기반으로
    DB에 가상 체결 기록을 생성합니다.
    """
    def __init__(self, db_settings=None, db_credential=None):
        super().__init__(db_settings, db_credential)
        self.user_id = db_settings.user_id if db_settings else None

    def get_account_balance(self, exchange_rate: float | None = None) -> dict:
        db = SessionLocal()
        try:
            if self.user_id:
                holdings = db.query(Holding).filter(Holding.user_id == self.user_id).all()
                trade_logs = db.query(TradeLog).filter(
                    TradeLog.user_id == self.user_id,
                    TradeLog.trade_type == "SELL",
                    TradeLog.realized_pnl != None
                ).all()
            else:
                holdings = db.query(Holding).all()
                trade_logs = db.query(TradeLog).filter(
                    TradeLog.trade_type == "SELL",
                    TradeLog.realized_pnl != None
                ).all()
        finally:
            db.close()

        initial_cash = settings.SIMULATED_INITIAL_CASH_KRW
        if exchange_rate is None:
            exchange_rate = FXRateCache.get_rate()
        if exchange_rate <= 0:
            raise ValueError("환율은 0보다 커야 합니다.")

        # 시작 시점의 환율을 고정해야 평가 시점 환율 변화가 환차손익으로 반영됩니다.
        initial_cash_usd = initial_cash / settings.SIMULATED_INITIAL_FX_RATE

        # 누적 실현 손익 계산 (TradeLog 기준 매매 누적 성과 - USD 기준)
        total_realized_pnl_usd = sum(log.realized_pnl for log in trade_logs) if trade_logs else 0.0

        total_purchase_usd = 0.0
        total_eval_usd = 0.0

        if holdings:
            # 💡 [캐시 최적화] 스케줄러 캐시로부터 실시간 가격을 먼저 매핑하여 yfinance 무차별 호출 차단
            cache_prices = {}
            try:
                from app.bot.scheduler import latest_scanned_signals, latest_watchlist_signals
                for s in latest_scanned_signals:
                    if "ticker" in s and "price" in s:
                        cache_prices[s["ticker"]] = float(s["price"])
                for t, s in latest_watchlist_signals.items():
                    if isinstance(s, dict) and "price" in s:
                        cache_prices[t] = float(s["price"])
            except Exception as ce:
                print(f"[SimulatedBroker] Failed to load scheduler cache: {ce}")

            tickers_to_fetch = []
            for h in holdings:
                if h.ticker in cache_prices:
                    current_price = cache_prices[h.ticker]
                    total_purchase_usd += (h.avg_price * h.quantity)
                    total_eval_usd += (current_price * h.quantity)
                else:
                    tickers_to_fetch.append(h.ticker)

            if tickers_to_fetch:
                try:
                    data = fetch_bulk_ohlcv_sync(tickers_to_fetch, period="1d", interval="1m", group_by="ticker")
                    for h in holdings:
                        if h.ticker not in tickers_to_fetch:
                            continue
                        clean_t = h.ticker
                        current_price = h.avg_price  # 기본 폴백값
                        try:
                            if len(tickers_to_fetch) == 1:
                                if isinstance(data.columns, pd.MultiIndex):
                                    df = data[clean_t].dropna() if clean_t in data.columns.levels[0] else data.dropna()
                                else:
                                    df = data.dropna()
                            else:
                                if isinstance(data.columns, pd.MultiIndex):
                                    df = data[clean_t].dropna() if clean_t in data.columns.levels[0] else pd.DataFrame()
                                else:
                                    df = data.dropna()

                            if not df.empty:
                                current_price = float(df['Close'].iloc[-1])
                        except Exception as e:
                            print(f"[SimulatedBroker] Failed to parse price for {h.ticker}: {e}")

                        total_purchase_usd += (h.avg_price * h.quantity)
                        total_eval_usd += (current_price * h.quantity)
                except Exception as e:
                    print(f"[SimulatedBroker] Failed to download prices: {e}")
                    for h in holdings:
                        if h.ticker in tickers_to_fetch:
                            total_purchase_usd += (h.avg_price * h.quantity)
                            total_eval_usd += (h.avg_price * h.quantity)

        # 💡 [환율 왜곡 보정] 남은 가상 예수금을 USD 기준으로 산출한 뒤 최종 시점에 환율을 곱하여 원화 환산
        cash_balance_usd = max(0.0, initial_cash_usd + total_realized_pnl_usd - total_purchase_usd)
        cash_balance = cash_balance_usd * exchange_rate
        stock_balance = total_eval_usd * exchange_rate
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

    def get_holdings(self, exchange_rate: float | None = None) -> list:
        from app.translations.translator import Translator

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

        if exchange_rate is None:
            exchange_rate = FXRateCache.get_rate()

        # 💡 [캐시 최적화] 스케줄러 캐시로부터 실시간 가격을 먼저 매핑하여 yfinance 무차별 호출 차단
        cache_prices = {}
        try:
            from app.bot.scheduler import latest_scanned_signals, latest_watchlist_signals
            for s in latest_scanned_signals:
                if "ticker" in s and "price" in s:
                    cache_prices[s["ticker"]] = float(s["price"])
            for t, s in latest_watchlist_signals.items():
                if isinstance(s, dict) and "price" in s:
                    cache_prices[t] = float(s["price"])
        except Exception as ce:
            print(f"[SimulatedBroker] Failed to load scheduler cache: {ce}")

        result = []
        tickers_to_fetch = []

        for h in holdings:
            if h.ticker in cache_prices:
                result.append({
                    "id": h.id,
                    "ticker": h.ticker,
                    "ticker_name": h.ticker_name,
                    "strategy_type": h.strategy_type,
                    "strategy_name": Translator.translate_strategy(h.strategy_type, "ko"),
                    "avg_price": h.avg_price,
                    "quantity": h.quantity,
                    "highest_price": h.highest_price,
                    "current_price": cache_prices[h.ticker],
                    "fx_rate": exchange_rate,
                    "is_mock": True,
                    "provider": "Simulated"
                })
            else:
                tickers_to_fetch.append(h)

        if tickers_to_fetch:
            tickers = [h.ticker for h in tickers_to_fetch]
            try:
                data = fetch_bulk_ohlcv_sync(tickers, period="1d", interval="1m", group_by="ticker")
                for h in tickers_to_fetch:
                    clean_t = h.ticker
                    current_price = h.avg_price  # 기본 폴백값
                    try:
                        if len(tickers) == 1:
                            if isinstance(data.columns, pd.MultiIndex):
                                df = data[clean_t].dropna() if clean_t in data.columns.levels[0] else data.dropna()
                            else:
                                df = data.dropna()
                        else:
                            if isinstance(data.columns, pd.MultiIndex):
                                df = data[clean_t].dropna() if clean_t in data.columns.levels[0] else pd.DataFrame()
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
                        "strategy_type": h.strategy_type,
                        "strategy_name": Translator.translate_strategy(h.strategy_type, "ko"),
                        "avg_price": h.avg_price,
                        "quantity": h.quantity,
                        "highest_price": h.highest_price,
                        "current_price": current_price,
                        "fx_rate": exchange_rate,
                        "is_mock": True,
                        "provider": "Simulated"
                    })
            except Exception as e:
                print(f"[SimulatedBroker] Error downloading live prices: {e}")
                for h in tickers_to_fetch:
                    result.append({
                        "id": h.id,
                        "ticker": h.ticker,
                        "ticker_name": h.ticker_name,
                        "strategy_type": h.strategy_type,
                        "strategy_name": Translator.translate_strategy(h.strategy_type, "ko"),
                        "avg_price": h.avg_price,
                        "quantity": h.quantity,
                        "highest_price": h.highest_price,
                        "current_price": h.avg_price,  # 💡 [예외 처리 리스크 개선] 통신 장애 시 강제 2% 펌핑 대신 평단가 적용
                        "fx_rate": exchange_rate,
                        "is_mock": True,
                        "provider": "Simulated"
                    })
        return result

    def _get_live_price(self, ticker: str) -> float | None:
        """yfinance에서 단일 종목의 최신 가격을 조회합니다."""
        try:
            data = fetch_ohlcv_sync(ticker, period="1d", interval="1m")
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                return float(data['Close'].iloc[-1])
        except Exception as e:
            print(f"[SimulatedBroker] Failed to fetch live price for {ticker}: {e}")
        return None

    def check_order_status(self, order_no: str, order_date: str | None = None) -> dict:
        return {
            "status": "ERROR",
            "message": "Simulated orders are filled synchronously and are not reconciled.",
            "order_no": order_no,
        }

    def list_order_history(self, start_date: str, end_date: str) -> list[dict]:
        return []

    def get_order_metadata(self, ticker: str, session: str) -> dict:
        return {
            "exchange_code": "SIMULATED",
            "order_division": "00",
        }

    def buy_order(
        self,
        ticker: str,
        quantity: int,
        price: float,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ) -> dict:
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
            "order_submitted": True,
            "status": "FILLED",
            "fill_confirmed": True,
            "order_no": order_no,
            "filled_qty": quantity,
            "filled_price": fill_price,
            "message": f"Simulated buy: {quantity} shares of {ticker} at ${fill_price:.2f}"
        }

    def sell_order(
        self,
        ticker: str,
        quantity: int,
        price: float,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
    ) -> dict:
        """
        가상 매도 체결: yfinance 실시간 시세를 기반으로 즉시 체결을 시뮬레이션합니다.
        """
        live_price = self._get_live_price(ticker)
        fill_price = live_price if live_price else price

        order_no = f"SIM-SELL-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return {
            "success": True,
            "order_submitted": True,
            "status": "FILLED",
            "fill_confirmed": True,
            "order_no": order_no,
            "filled_qty": quantity,
            "filled_price": fill_price,
            "message": f"Simulated sell: {quantity} shares of {ticker} at ${fill_price:.2f}"
        }
