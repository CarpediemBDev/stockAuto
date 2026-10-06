import pandas as pd
from sqlalchemy import func
from app.scanner.data_provider import fetch_bulk_ohlcv_sync, fetch_ohlcv_sync
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from app.brokers.base_broker import BaseBroker
from app.core.database import SessionLocal
from app.core.holding_audit import delete_holding
from app.core.models import Holding, SimCashTransfer, TradeLog, UnfilledOrder, MANAGEMENT_BOT_OWNED
from app.core.config import settings
from app.bot.fx_cache import FXRateCache
from app.bot.trade_calculations import to_decimal, calculate_realized_pnl, fee_rate_for_trade_mode

def purge_orphan_sell_orders(db, user_ids: list[int] | None = None) -> int:
    """팔 물건이 없는 매도 미체결 주문을 지운다. 시세를 조회하기 전에 먼저 돌린다.

    미체결 매도 주문은 체결되면 사라지지만, 체결되기 전에 같은 보유분이 다른 경로로 팔리면
    주문만 남는다. 그 주문은 가리키는 보유분이 없어 영원히 체결될 수 없는데도, 기존 정리
    코드가 "지정가 도달" 조건 안쪽에 있어 가격이 닿지 않으면 삭제 기회조차 오지 않았다.
    그래서 2026-09 기준 매도 미체결 605건 중 595건이 이런 고아 주문이었고, 매 사이클
    이들의 시세를 받느라 정규장 사이클의 72%를 썼다.

    매수 주문은 대상이 아니다. 매수는 체결되어야 보유분이 생기므로 보유분이 없는 것이 정상이다.
    """
    query = db.query(UnfilledOrder).filter(UnfilledOrder.trade_type == "SELL")
    if user_ids is not None:
        if not user_ids:
            return 0
        query = query.filter(UnfilledOrder.user_id.in_(user_ids))

    removed = 0
    for order in query.all():
        holding = db.query(Holding).filter(
            Holding.user_id == order.user_id,
            Holding.ticker == order.ticker,
            Holding.strategy_type == order.strategy_type,
        ).first()
        if holding is None or (holding.quantity or 0) <= 0:
            db.delete(order)
            removed += 1
    if removed:
        db.commit()
    return removed


def collect_unfilled_tickers(db, user_ids: list[int] | None = None) -> list[str]:
    """미체결 주문이 걸린 티커 목록. 유저가 달라도 같은 티커는 한 번만 담는다."""
    query = db.query(UnfilledOrder.ticker).distinct()
    if user_ids is not None:
        if not user_ids:
            return []
        query = query.filter(UnfilledOrder.user_id.in_(user_ids))
    return [row[0] for row in query.all() if row[0]]


def fetch_unfilled_prices(tickers: list[str]) -> dict:
    """미체결 판정에 쓸 현재가를 한 번에 받는다.

    유저마다 따로 받으면 같은 티커를 여러 번 내려받고, 그 호출이 이벤트 루프 위에서
    순차로 돌아 사이클을 통째로 붙잡는다(실측: 유저 54명 순회에 241초). 티커를 합쳐
    한 번만 받으면 호출 수가 유저 수와 무관해진다.
    """
    if not tickers:
        return {}
    prices: dict = {}
    try:
        data = fetch_bulk_ohlcv_sync(tickers, period="1d", interval="1m", group_by="ticker")
    except Exception as exc:  # noqa: BLE001
        print(f"[SimulatedBroker] Failed to fetch prices for unfilled orders: {exc}")
        return prices

    for ticker in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if len(tickers) == 1:
                    df = data[ticker].dropna() if ticker in data.columns.levels[0] else data.dropna()
                else:
                    df = data[ticker].dropna() if ticker in data.columns.levels[0] else pd.DataFrame()
            else:
                df = data.dropna()
            if not df.empty:
                prices[ticker] = to_decimal(df['Close'].iloc[-1])
        except Exception as exc:  # noqa: BLE001
            print(f"[SimulatedBroker] Failed to parse price for {ticker}: {exc}")
    return prices


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
            # 누적 실현 손익: SELL TradeLog를 전량 로드해 파이썬 sum 하던 것을 DB SQL SUM 스칼라
            # 집계로 대체한다. 행을 로드하지 않고 합계 하나만 받으므로 거래 이력이 쌓여도 비용이 일정하다.
            # realized_pnl은 Numeric(20,4)이라 집계도 Decimal 정밀 연산이며, scale 4로 양자화해
            # SQLite(float 경유)에서도 프로덕션(Decimal)과 동일한 결과를 보장한다.
            realized_pnl_query = db.query(func.sum(TradeLog.realized_pnl)).filter(
                TradeLog.trade_type == "SELL",
                TradeLog.realized_pnl != None,
            )
            # 입출금 원장 합계. 실현손익과 같은 범위(사용자 단위)로 집계한다.
            transfers_query = db.query(func.sum(SimCashTransfer.amount_krw))
            if self.user_id:
                holdings = db.query(Holding).filter(Holding.user_id == self.user_id).all()
                realized_pnl_query = realized_pnl_query.filter(TradeLog.user_id == self.user_id)
                transfers_query = transfers_query.filter(SimCashTransfer.user_id == self.user_id)
            else:
                holdings = db.query(Holding).all()
            total_realized_pnl_usd = to_decimal(realized_pnl_query.scalar()).quantize(
                Decimal('0.0001'), rounding=ROUND_HALF_UP
            )
            total_transfers_krw = to_decimal(transfers_query.scalar()).quantize(
                Decimal('0.0001'), rounding=ROUND_HALF_UP
            )
        finally:
            db.close()

        # 투입 자본 = 초기자금 + 입출금 합계. 현금·손익·수익률이 모두 이 값을 기준으로 한다.
        # 손익을 초기자금 기준으로 두면 1천만원 입금이 +100% 수익으로 잡힌다.
        invested_capital = to_decimal(settings.SIMULATED_INITIAL_CASH_KRW) + total_transfers_krw
        if exchange_rate is None:
            exchange_rate = FXRateCache.get_rate()
        dec_exchange_rate = to_decimal(exchange_rate)
        if dec_exchange_rate <= 0:
            raise ValueError("환율은 0보다 커야 합니다.")

        total_purchase_usd = Decimal('0.0000')
        total_eval_usd = Decimal('0.0000')

        if holdings:
            # 💡 유저 대면 경로 외부 호출 0건 원칙: 스케줄러가 DB에 영속화한 last_price로 평가.
            # last_price가 아직 없으면(신규 매수 직후 등) 평단가로 폴백하여 손익 0으로 표시.
            for h in holdings:
                current_price = to_decimal(h.last_price) if h.last_price is not None else to_decimal(h.avg_price)
                total_purchase_usd += (to_decimal(h.avg_price) * h.quantity)
                total_eval_usd += (current_price * h.quantity)

        # 수익률은 외화 기준으로 계산합니다.
        invested_capital_usd = invested_capital / to_decimal(settings.SIMULATED_INITIAL_FX_RATE)
        cash_balance_usd = max(Decimal('0.0000'), invested_capital_usd + total_realized_pnl_usd - total_purchase_usd)
        cash_balance = cash_balance_usd * to_decimal(settings.SIMULATED_INITIAL_FX_RATE)
        stock_balance = total_eval_usd * to_decimal(settings.SIMULATED_INITIAL_FX_RATE)
        total_asset = cash_balance + stock_balance
        profit_loss = total_asset - invested_capital

        # 가상 수익률 계산
        profit_rate = ((profit_loss / invested_capital) * Decimal('100.0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if invested_capital > 0 else Decimal('0.0000')

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

        # 💡 유저 대면 경로 외부 호출 0건 원칙: DB에 영속화된 last_price로 평가 (없으면 평단가 폴백)
        result = []
        for h in holdings:
            current_price = to_decimal(h.last_price) if h.last_price is not None else to_decimal(h.avg_price)
            result.append({
                "id": h.id,
                "ticker": h.ticker,
                "ticker_name": h.ticker_name,
                "strategy_type": h.strategy_type,
                "strategy_name": Translator.translate_strategy(h.strategy_type, "ko"),
                # 관할권은 시뮬레이터가 DB에서 그대로 읽어 넘긴다. 실증권 브로커는 계좌
                # 응답에 이 개념이 없어 라우터가 DB와 대조해 채운다(router_account.get_holdings).
                "management": h.management or MANAGEMENT_BOT_OWNED,
                "avg_price": float(to_decimal(h.avg_price)),
                "quantity": h.quantity,
                "highest_price": float(to_decimal(h.highest_price)),
                "current_price": float(current_price),
                "fx_rate": float(exchange_rate),
                "is_mock": True,
                "provider": "Simulated"
            })
        return result

    def process_unfilled_orders(self, db, prices: dict | None = None):
        """미체결 가상 지정가 주문들을 현재 실시간 시세 기준으로 체크하여 체결 처리합니다.

        prices를 받으면 그 값을 쓰고 네트워크를 타지 않는다. 사이클이 모든 유저의 티커를
        한 번에 받아 넘겨주기 위한 통로다(scheduler.async_trading_loop). 넘어오지 않으면
        예전처럼 스스로 받는다 - 테스트와 단독 호출 경로를 그대로 유지한다.
        """
        # 팔 물건이 없는 매도 주문을 먼저 지운다. 시세를 받아 봐야 체결될 수 없고,
        # 남겨 두면 다음 사이클에도 같은 조회를 반복한다.
        purge_orphan_sell_orders(db, [self.user_id] if self.user_id else None)

        orders = db.query(UnfilledOrder).filter(UnfilledOrder.user_id == self.user_id).all() if self.user_id else db.query(UnfilledOrder).all()
        if not orders:
            return

        if prices is None:
            prices = fetch_unfilled_prices(list({order.ticker for order in orders}))

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
                    # [글로벌 아키텍처 2] 멱등성 키(Idempotency Key) 방어선: 이미 처리된 체결인지 고유 order_no로 확인
                    existing_log = db.query(TradeLog).filter(TradeLog.order_no == order.order_no).first()
                    if existing_log:
                        print(f"[SimulatedBroker] BUY order {order.order_no} already processed (Idempotency Guard). Skipping.")
                        db.delete(order)
                        db.commit()
                        continue

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
                    from sqlalchemy import update
                    
                    # [글로벌 아키텍처 2] 멱등성 키(Idempotency Key) 방어선: 이미 처리된 체결인지 고유 order_no로 확인
                    existing_log = db.query(TradeLog).filter(TradeLog.order_no == order.order_no).first()
                    if existing_log:
                        print(f"[SimulatedBroker] SELL order {order.order_no} already processed (Idempotency Guard). Skipping.")
                        db.delete(order)
                        db.commit()
                        continue

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

                    sell_qty = order.quantity if order.quantity <= h.quantity else h.quantity
                    if sell_qty <= 0:
                        db.delete(order)
                        db.commit()
                        continue

                    # [글로벌 아키텍처 1] 파이썬 계산을 버리고 DB 레벨 Atomic In-place Update 실행
                    update_stmt = (
                        update(Holding)
                        .where(
                            Holding.id == h.id,
                            Holding.quantity >= sell_qty  # 원자성: 잔고가 뺄셈하려는 수량보다 크거나 같을 때만 DB가 허가함
                        )
                        .values(quantity=Holding.quantity - sell_qty)
                    )
                    res = db.execute(update_stmt)
                    
                    # 만약 찰나의 순간 다른 스레드가 수량을 빼가서 조건에 안 맞게 되었다면(Rowcount 0), 롤백 후 다음 사이클로 넘김
                    if res.rowcount == 0:
                        print(f"[SimulatedBroker] Atomic Update Failed: Insufficient quantity for {order.ticker} during execution.")
                        db.rollback()
                        continue

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

                    # Atomic 차감 후 남은 수량이 0 이하라면(즉 h.quantity - sell_qty == 0) 삭제
                    # (여기서 h 객체는 DB와 분리되어 있으므로 수동 평가하거나 쿼리로 지움)
                    if (h.quantity - sell_qty) <= 0:
                        delete_holding(db, h, actor="simulated_broker.fill_unfilled_orders",
                                       reason=f"unfilled sell filled ({order.order_no})")

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
        *,
        strategy_type: str,
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
        *,
        strategy_type: str,
        buy_stage: int | None = None,
        regime_mode: str | None = None,
        signal_score: int | None = None,
    ) -> dict:
        def reject_sell(message: str) -> dict:
            return {
                "success": False,
                "order_submitted": False,
                "status": "REJECTED",
                "fill_confirmed": False,
                "order_no": "",
                "filled_qty": 0,
                "filled_price": 0.0,
                "message": message,
            }

        if quantity <= 0:
            return reject_sell(f"Simulated sell rejected: invalid quantity {quantity} for {ticker}")

        live_price = self._get_live_price(ticker)
        dec_price = to_decimal(price)
        dec_live_price = to_decimal(live_price) if live_price is not None else dec_price

        # 같은 보유분에 걸린 기존 대기 주문을 먼저 거둔다 - 재시도는 주문을 쌓는 것이 아니라
        # 갱신(정정)이어야 한다.
        #
        # 실제 증권사는 매도 주문을 걸면 그 수량을 묶어 두어 같은 물량을 다시 팔 수 없다.
        # 이 시뮬레이터에는 그 예약이 없어서, 체결되지 않은 주문을 남겨 둔 채 다음 사이클에
        # 또 매도하면 같은 87주에 주문이 겹쳤다(실측 최대 10건). 그렇게 겹친 주문은 하나가
        # 체결되어 보유분이 사라지는 순간 전부 고아가 된다.
        #
        # 막는 방향(대기 주문이 있으면 매도 금지)은 택하지 않았다. 체결되지 않은 손절이
        # 다음 사이클에 다시 시도되는 것이 지금의 재시도 경로인데, 그것을 막으면 주문 하나가
        # 걸려 있는 동안 그 종목은 아무리 떨어져도 팔지 못한다. 손절을 얼리는 대가로
        # 고아 주문을 막는 셈이라 더 나쁘다.
        #
        # 한 보유분에 대기 주문이 최대 하나만 존재한다는 불변식이 곧 이중 매도 방지다.
        # 그래서 아래 가용 수량 검사는 보유 수량을 그대로 써도 안전하다.
        replaced = 0
        if self.user_id is not None:
            db = SessionLocal()
            try:
                stale = db.query(UnfilledOrder).filter(
                    UnfilledOrder.user_id == self.user_id,
                    UnfilledOrder.ticker == ticker,
                    UnfilledOrder.strategy_type == strategy_type,
                    UnfilledOrder.trade_type == "SELL",
                ).all()
                for order in stale:
                    db.delete(order)
                    replaced += 1
                if replaced:
                    db.commit()
            finally:
                db.close()
        if replaced:
            print(f"[SimulatedBroker] Replaced {replaced} pending SELL order(s) for {ticker} before re-submitting.")

        if live_price is not None and dec_live_price >= dec_price:
            if self.user_id is None:
                return reject_sell(f"Simulated sell rejected: missing user context for {ticker}")

            db = SessionLocal()
            try:
                holding = db.query(Holding).filter(
                    Holding.user_id == self.user_id,
                    Holding.ticker == ticker,
                    Holding.strategy_type == strategy_type,
                ).first()
                available_qty = int(holding.quantity or 0) if holding else 0
                if quantity > available_qty:
                    return reject_sell(
                        f"Simulated sell rejected: requested {quantity} shares of {ticker}, "
                        f"available {available_qty}"
                    )
            finally:
                db.close()

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
