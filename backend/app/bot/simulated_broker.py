import pandas as pd
from app.scanner.data_provider import fetch_bulk_ohlcv_sync, fetch_ohlcv_sync
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from app.bot.base_broker import BaseBroker
from app.core.database import SessionLocal
from app.core.models import Holding, TradeLog, UnfilledOrder
from app.core.config import settings
from app.bot.fx_cache import FXRateCache
from app.bot.trade_calculations import to_decimal, calculate_realized_pnl, fee_rate_for_trade_mode

class LocalSimulatedBroker(BaseBroker):
    """
    증권사 API 연동 없이 로컬 SQLite 데이터베이스와 yfinance를 활용하여
    가상으로 작동하는 모의투자(Paper Trading) 브로커 클라이언트.

    buy_order / sell_order는 yfinance 실시간 시세를 기반으로
    지정가 조건을 충족하면 즉시 체결하고, 충족하지 못하면 unfilled_orders 테이블에 기록합니다.
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

        initial_cash = to_decimal(settings.SIMULATED_INITIAL_CASH_KRW)
        if exchange_rate is None:
            exchange_rate = FXRateCache.get_rate()
        dec_exchange_rate = to_decimal(exchange_rate)
        if dec_exchange_rate <= 0:
            raise ValueError("환율은 0보다 커야 합니다.")

        # 누적 실현 손익 계산 (TradeLog 기준 매매 누적 성과 - USD 기준)
        total_realized_pnl_usd = sum(to_decimal(log.realized_pnl) for log in trade_logs) if trade_logs else Decimal('0.0000')

        total_purchase_usd = Decimal('0.0000')
        total_eval_usd = Decimal('0.0000')

        if holdings:
            # 💡 [캐시 최적화] 스케줄러 캐시로부터 실시간 가격을 먼저 매핑하여 yfinance 무차별 호출 차단
            cache_prices = {}
            try:
                from app.bot.scheduler import latest_scanned_signals, latest_watchlist_signals
                for s in latest_scanned_signals:
                    if "ticker" in s and "price" in s:
                        cache_prices[s["ticker"]] = to_decimal(s["price"])
                for t, s in latest_watchlist_signals.items():
                    if isinstance(s, dict) and "price" in s:
                        cache_prices[t] = to_decimal(s["price"])
            except Exception as ce:
                print(f"[SimulatedBroker] Failed to load scheduler cache: {ce}")

            tickers_to_fetch = []
            for h in holdings:
                if h.ticker in cache_prices:
                    current_price = cache_prices[h.ticker]
                    total_purchase_usd += (to_decimal(h.avg_price) * h.quantity)
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
                        current_price = to_decimal(h.avg_price)  # 기본 폴백값
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
                                current_price = to_decimal(df['Close'].iloc[-1])
                        except Exception as e:
                            print(f"[SimulatedBroker] Failed to parse price for {h.ticker}: {e}")

                        total_purchase_usd += (to_decimal(h.avg_price) * h.quantity)
                        total_eval_usd += (current_price * h.quantity)
                except Exception as e:
                    print(f"[SimulatedBroker] Failed to download prices: {e}")
                    for h in holdings:
                        if h.ticker in tickers_to_fetch:
                            total_purchase_usd += (to_decimal(h.avg_price) * h.quantity)
                            total_eval_usd += (to_decimal(h.avg_price) * h.quantity)

        # 수익률은 외화 기준으로 계산합니다.
        strategy_initial_cash_usd = initial_cash / to_decimal(settings.SIMULATED_INITIAL_FX_RATE)
        cash_balance_usd = max(Decimal('0.0000'), strategy_initial_cash_usd + total_realized_pnl_usd - total_purchase_usd)
        cash_balance = cash_balance_usd * to_decimal(settings.SIMULATED_INITIAL_FX_RATE)
        stock_balance = total_eval_usd * to_decimal(settings.SIMULATED_INITIAL_FX_RATE)
        total_asset = cash_balance + stock_balance
        profit_loss = total_asset - initial_cash

        # 가상 수익률 계산
        profit_rate = ((profit_loss / initial_cash) * Decimal('100.0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if initial_cash > 0 else Decimal('0.0000')

        return {
            "total_asset": int(total_asset.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            "cash_balance": int(cash_balance.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            "stock_balance": int(stock_balance.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            "profit_rate": float(profit_rate),
            "profit_loss": int(profit_loss.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            "fx_rate": float(dec_exchange_rate),
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
                    cache_prices[s["ticker"]] = to_decimal(s["price"])
            for t, s in latest_watchlist_signals.items():
                if isinstance(s, dict) and "price" in s:
                    cache_prices[t] = to_decimal(s["price"])
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
                    "avg_price": float(to_decimal(h.avg_price)),
                    "quantity": h.quantity,
                    "highest_price": float(to_decimal(h.highest_price)),
                    "current_price": float(cache_prices[h.ticker]),
                    "fx_rate": float(exchange_rate),
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
                    current_price = to_decimal(h.avg_price)  # 기본 폴백값
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
                            current_price = to_decimal(df['Close'].iloc[-1])
                    except Exception as e:
                        print(f"[SimulatedBroker] Failed to get price for {h.ticker}: {e}")

                    result.append({
                        "id": h.id,
                        "ticker": h.ticker,
                        "ticker_name": h.ticker_name,
                        "strategy_type": h.strategy_type,
                        "strategy_name": Translator.translate_strategy(h.strategy_type, "ko"),
                        "avg_price": float(to_decimal(h.avg_price)),
                        "quantity": h.quantity,
                        "highest_price": float(to_decimal(h.highest_price)),
                        "current_price": float(current_price),
                        "fx_rate": float(exchange_rate),
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
                        "avg_price": float(to_decimal(h.avg_price)),
                        "quantity": h.quantity,
                        "highest_price": float(to_decimal(h.highest_price)),
                        "current_price": float(to_decimal(h.avg_price)),  # 💡 [예외 처리 리스크 개선] 통신 장애 시 강제 2% 펌핑 대신 평단가 적용
                        "fx_rate": float(exchange_rate),
                        "is_mock": True,
                        "provider": "Simulated"
                    })
        return result

    def process_unfilled_orders(self, db):
        """미체결 가상 지정가 주문들을 현재 실시간 시세 기준으로 체크하여 체결 처리합니다."""
        orders = db.query(UnfilledOrder).filter(UnfilledOrder.user_id == self.user_id).all() if self.user_id else db.query(UnfilledOrder).all()
        if not orders:
            return

        tickers = list({order.ticker for order in orders})
        prices = {}
        try:
            data = fetch_bulk_ohlcv_sync(tickers, period="1d", interval="1m", group_by="ticker")
            for ticker in tickers:
                clean_t = ticker
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
                        prices[ticker] = to_decimal(df['Close'].iloc[-1])
                except Exception as e:
                    print(f"[SimulatedBroker] Failed to parse price for {ticker}: {e}")
        except Exception as e:
            print(f"[SimulatedBroker] Failed to fetch prices for unfilled orders: {e}")

        for order in orders:
            live_price = prices.get(order.ticker)
            if live_price is None:
                continue

            is_filled = False
            if order.trade_type == "BUY":
                if live_price <= order.price:
                    is_filled = True
            elif order.trade_type == "SELL":
                if live_price >= order.price:
                    is_filled = True

            if is_filled:
                filled_price = order.price
                if order.trade_type == "BUY":
                    h = db.query(Holding).filter(
                        Holding.user_id == order.user_id,
                        Holding.ticker == order.ticker,
                        Holding.strategy_type == order.strategy_type
                    ).first()

                    if h:
                        old_qty = h.quantity
                        old_avg = to_decimal(h.avg_price)
                        new_qty = old_qty + order.quantity
                        new_avg = ((old_avg * old_qty) + (filled_price * order.quantity)) / new_qty

                        h.avg_price = new_avg.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
                        h.quantity = new_qty
                        if order.buy_stage is not None:
                            h.buy_stage = order.buy_stage
                        h.highest_price = max(to_decimal(h.highest_price), filled_price)
                    else:
                        h = Holding(
                            user_id=order.user_id,
                            ticker=order.ticker,
                            ticker_name=order.ticker_name or order.ticker,
                            avg_price=filled_price,
                            quantity=order.quantity,
                            highest_price=filled_price,
                            regime_mode=order.regime_mode,
                            buy_stage=order.buy_stage or 1,
                            strategy_type=order.strategy_type
                        )
                        db.add(h)

                    db.add(TradeLog(
                        user_id=order.user_id,
                        ticker=order.ticker,
                        strategy_type=order.strategy_type,
                        ticker_name=order.ticker_name or order.ticker,
                        trade_type="BUY",
                        price=filled_price,
                        quantity=order.quantity,
                        order_no=order.order_no,
                        regime_mode=order.regime_mode,
                        signal_score=order.signal_score,
                        realized_pnl=Decimal('0.0000'),
                        return_rate=Decimal('0.0000')
                    ))

                elif order.trade_type == "SELL":
                    h = db.query(Holding).filter(
                        Holding.user_id == order.user_id,
                        Holding.ticker == order.ticker,
                        Holding.strategy_type == order.strategy_type
                    ).first()

                    if not h:
                        print(f"[SimulatedBroker] SELL unfilled order {order.order_no} skipped: no matching Holding for {order.ticker}")
                        db.delete(order)
                        db.commit()
                        continue

                    if order.quantity > h.quantity:
                        print(f"[SimulatedBroker] SELL unfilled order {order.order_no} quantity {order.quantity} exceeds Holding quantity {h.quantity} for {order.ticker}. Clamping to available.")
                        if h.quantity <= 0:
                            db.delete(order)
                            db.commit()
                            continue
                        sell_qty = h.quantity
                    else:
                        sell_qty = order.quantity

                    fee_rate = fee_rate_for_trade_mode("SIMULATED")
                    pnl = calculate_realized_pnl(
                        avg_price=to_decimal(h.avg_price),
                        filled_price=filled_price,
                        quantity=sell_qty,
                        fee_rate=fee_rate
                    )

                    db.add(TradeLog(
                        user_id=order.user_id,
                        ticker=order.ticker,
                        strategy_type=order.strategy_type,
                        ticker_name=order.ticker_name or order.ticker,
                        trade_type="SELL",
                        price=filled_price,
                        quantity=sell_qty,
                        order_no=order.order_no,
                        regime_mode=order.regime_mode,
                        signal_score=order.signal_score,
                        realized_pnl=pnl.realized_pnl,
                        return_rate=pnl.return_rate
                    ))

                    if sell_qty >= h.quantity:
                        db.delete(h)
                    else:
                        h.quantity -= sell_qty

                db.delete(order)
                db.commit()
                print(f"[SimulatedBroker] Unfilled order {order.order_no} for {order.ticker} successfully filled at price {filled_price}.")

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
        strategy_type: str = "regime_switching",
        buy_stage: int | None = None,
        regime_mode: str | None = None,
        signal_score: int | None = None,
    ) -> dict:
        live_price = self._get_live_price(ticker)
        dec_price = to_decimal(price)
        dec_live_price = to_decimal(live_price) if live_price is not None else dec_price

        if live_price is not None and dec_live_price <= dec_price:
            fill_price = dec_live_price
            order_no = f"SIM-BUY-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return {
                "success": True,
                "order_submitted": True,
                "status": "FILLED",
                "fill_confirmed": True,
                "order_no": order_no,
                "filled_qty": quantity,
                "filled_price": float(fill_price),
                "message": f"Simulated buy: {quantity} shares of {ticker} at ${float(fill_price):.2f}"
            }
        else:
            order_no = f"SIM-BUY-UNFILLED-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            db = SessionLocal()
            try:
                unfilled = UnfilledOrder(
                    user_id=self.user_id,
                    ticker=ticker,
                    ticker_name="",
                    trade_type="BUY",
                    price=dec_price,
                    quantity=quantity,
                    strategy_type=strategy_type,
                    buy_stage=buy_stage,
                    regime_mode=regime_mode,
                    signal_score=signal_score,
                    order_no=order_no,
                )
                db.add(unfilled)
                db.commit()
            finally:
                db.close()
            return {
                "success": True,
                "order_submitted": True,
                "status": "SUBMITTED",
                "fill_confirmed": False,
                "order_no": order_no,
                "filled_qty": 0,
                "filled_price": 0.0,
                "message": f"Simulated buy order SUBMITTED (unfilled yet) for {ticker} at limit price ${float(dec_price):.2f}"
            }

    def sell_order(
        self,
        ticker: str,
        quantity: int,
        price: float,
        session: str = "REGULAR_MARKET",
        client_order_id: str | None = None,
        strategy_type: str = "regime_switching",
        buy_stage: int | None = None,
        regime_mode: str | None = None,
        signal_score: int | None = None,
    ) -> dict:
        live_price = self._get_live_price(ticker)
        dec_price = to_decimal(price)
        dec_live_price = to_decimal(live_price) if live_price is not None else dec_price

        if live_price is not None and dec_live_price >= dec_price:
            fill_price = dec_live_price
            order_no = f"SIM-SELL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return {
                "success": True,
                "order_submitted": True,
                "status": "FILLED",
                "fill_confirmed": True,
                "order_no": order_no,
                "filled_qty": quantity,
                "filled_price": float(fill_price),
                "message": f"Simulated sell: {quantity} shares of {ticker} at ${float(fill_price):.2f}"
            }
        else:
            order_no = f"SIM-SELL-UNFILLED-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            db = SessionLocal()
            try:
                unfilled = UnfilledOrder(
                    user_id=self.user_id,
                    ticker=ticker,
                    ticker_name="",
                    trade_type="SELL",
                    price=dec_price,
                    quantity=quantity,
                    strategy_type=strategy_type,
                    buy_stage=buy_stage,
                    regime_mode=regime_mode,
                    signal_score=signal_score,
                    order_no=order_no,
                )
                db.add(unfilled)
                db.commit()
            finally:
                db.close()
            return {
                "success": True,
                "order_submitted": True,
                "status": "SUBMITTED",
                "fill_confirmed": False,
                "order_no": order_no,
                "filled_qty": 0,
                "filled_price": 0.0,
                "message": f"Simulated sell order SUBMITTED (unfilled yet) for {ticker} at limit price ${float(dec_price):.2f}"
            }
