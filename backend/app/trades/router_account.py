from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.scanner.data_provider import fetch_ohlcv
from uuid import uuid4

from app.core.database import get_db
from app.bot.broker_factory import get_broker_client
from app.bot.order_reconciler import (
    begin_order_submission,
    create_order_intent,
    finalize_order_submission,
    has_unresolved_orders,
)
from fastapi.concurrency import run_in_threadpool
from app.core.dependencies import get_current_user
from app.core.models import User, Holding, TradeLog, ActionLog
from app.core.config import settings as app_settings
from app.core.locks import (
    RedisLockUnavailable,
    acquire_symbol_order_lock,
    acquire_user_operation_lock,
)

from app.core.response import SuccessResponseRoute
router = APIRouter(route_class=SuccessResponseRoute, tags=["Account"])

@router.get("/balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    현재 로그인한 사용자의 UserSettings에 맞춰 알맞은 증권사 API(또는 로컬 시뮬레이터)를 호출하여
    현재 계좌의 예수금, 주식 평가금, 총자산 및 전체 실시간 수익률 정보를 가져오며,
    실시간 QQQ 시장 레짐, 슬롯 격리 가상 지갑 자산 분배 정보, 그리고 최정예 돌파 관심종목 레이더 리스트를 추가 반환합니다.
    """
    from app.bot.fx_cache import FXRateCache
    from app.scanner.scanner import check_market_sentiment
    from app.bot.multi_strategy_manager import MultiStrategyManager
    import app.bot.scheduler as scheduler_mod

    broker = get_broker_client(current_user.settings)
    balance = await run_in_threadpool(broker.get_account_balance)

    try:
        # 💡 실시간 QQQ 지수 기반 시장 레짐 판별
        sentiment = await check_market_sentiment()

        # 💡 각 격리형 슬롯별 지갑 자산 정밀 분배 계산 (수학적 격리)
        strategy_type = current_user.settings.strategy_type if current_user.settings else "regime_switching"
        ms_manager = MultiStrategyManager(strategy_type=strategy_type)
        exchange_rate = FXRateCache.get_rate()

        total_asset_krw = balance.get(
            "total_asset",
            app_settings.SIMULATED_INITIAL_CASH_KRW,
        )
        cash_balance_krw = balance.get(
            "cash_balance",
            app_settings.SIMULATED_INITIAL_CASH_KRW,
        )

        total_asset_usd = total_asset_krw / exchange_rate
        cash_balance_usd = cash_balance_krw / exchange_rate

        holdings = db.query(Holding).filter(Holding.user_id == current_user.id).all()
        slot_allocations = ms_manager.calculate_slots_allocation(total_asset_usd, cash_balance_usd, holdings, sentiment)

        wallet_allocation = {
            slot_key: {
                "cash": int(alloc_info["cash_balance"] * exchange_rate),
                "stock_value": int(alloc_info["stock_value"] * exchange_rate),
                "name": alloc_info.get("name", slot_key),
                "weight": alloc_info.get("weight", 1.0)
            }
            for slot_key, alloc_info in slot_allocations.items()
        }

        # 현재 사용자의 관심종목 소유권을 공용 분석값과 결합한 뒤 레이더를 계산합니다.
        market_signals = getattr(scheduler_mod, "latest_scanned_signals", [])
        watchlists_by_user = scheduler_mod.load_watchlist_tickers_by_user(
            db,
            [current_user.id],
        )
        _, user_signals = scheduler_mod.build_user_signal_context(
            current_user.id,
            market_signals,
            watchlists_by_user,
            getattr(scheduler_mod, "latest_watchlist_signals", {}),
        )
        focused_set = ms_manager.get_focused_tickers(user_signals)
        focused_radar_tickers = sorted(list(focused_set))

        # 💡 기존 balance 데이터에 정밀 메타데이터 주입
        balance["qqq_regime"] = sentiment
        balance["wallet_allocation"] = wallet_allocation
        balance["focused_radar_tickers"] = focused_radar_tickers

    except Exception as e:
        print(f"[Balance Enricher] Error enriching balance data: {e}")
        # 오류 발생 시 기본값으로 폴백하여 대시보드 중단 방지
        balance["qqq_regime"] = "NEUTRAL"
        try:
            ms_manager = MultiStrategyManager(strategy_type=current_user.settings.strategy_type if current_user.settings else "regime_switching")
            balance["wallet_allocation"] = {
                slot_key: {
                    "cash": int(
                        balance.get(
                            "cash_balance",
                            app_settings.SIMULATED_INITIAL_CASH_KRW,
                        )
                        * slot_info["weight"]
                    ),
                    "stock_value": 0,
                    "name": slot_info.get("name", slot_key),
                    "weight": slot_info.get("weight", 1.0)
                }
                for slot_key, slot_info in ms_manager.SLOTS.items()
            }
        except Exception:
            from app.translations.translator import Translator

            fallback_cash = balance.get(
                "cash_balance",
                app_settings.SIMULATED_INITIAL_CASH_KRW,
            )
            balance["wallet_allocation"] = {
                "regime_switching": {
                    "cash": int(fallback_cash * 0.5),
                    "stock_value": 0,
                    "name": Translator.translate_strategy("regime_switching", "ko"),
                    "weight": 0.5,
                },
                "episodic_pivot": {
                    "cash": int(fallback_cash * 0.5),
                    "stock_value": 0,
                    "name": Translator.translate_strategy("episodic_pivot", "ko"),
                    "weight": 0.5,
                },
            }
        balance["focused_radar_tickers"] = []

    return balance

@router.get("/holdings")
def get_holdings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    현재 로그인한 사용자의 UserSettings에 맞춰 알맞은 증권사 API(또는 로컬 시뮬레이터)를 호출하여
    현재 보유 중인 종목 리스트와 개별 수익률을 가져옵니다.
    """
    broker = get_broker_client(current_user.settings)
    holdings = broker.get_holdings()
    from app.translations.translator import Translator

    db_holdings = db.query(Holding).filter(Holding.user_id == current_user.id).all()
    strategy_by_ticker = {
        holding.ticker: holding.strategy_type
        for holding in db_holdings
    }
    for holding in holdings:
        strategy_type = holding.get("strategy_type") or strategy_by_ticker.get(
            holding.get("ticker")
        )
        if strategy_type:
            holding["strategy_type"] = strategy_type
            holding["strategy_name"] = Translator.translate_strategy(
                strategy_type,
                "ko",
            )
    return holdings

@router.post("/reset-balance")
def reset_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [개인투자자 위험 영역] 모의투자(SIMULATED) 모드 잔고 및 매매기록 초기화.
    보유 자산 삭제, 거래 로그 및 활동 로그를 삭제하여 초기 가상 예수금(1,000만 원) 상태로 복원합니다.
    """
    settings = current_user.settings
    if not settings or settings.trade_mode != "SIMULATED":
        raise HTTPException(
            status_code=400,
            detail="모의투자(SIMULATED) 모드에서만 가상 계좌 자산 초기화가 가능합니다."
        )

    try:
        # 해당 사용자의 보유종목, 거래 로그, 행동 로그 일체 삭제
        db.query(Holding).filter(Holding.user_id == current_user.id).delete()
        db.query(TradeLog).filter(TradeLog.user_id == current_user.id).delete()
        db.query(ActionLog).filter(ActionLog.user_id == current_user.id).delete()
        db.commit()
        return {"message": "가상 모의투자 계좌 자산 및 로그가 성공적으로 초기화되었습니다."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"계좌 초기화 중 오류가 발생했습니다: {str(e)}")

@router.post("/force-liquidate")
async def force_liquidate(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [개인투자자 위험 영역] 보유 중인 모든 종목 즉시 시장가 전량 강제 매도 청산.
    현재 보유 중인 모든 종목을 실시간 시장 가격으로 일괄 일시 처분합니다.
    """
    operation_id = str(uuid4())
    try:
        user_lease = await acquire_user_operation_lock(current_user.id, operation_id)
    except RedisLockUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="주문 동시성 제어 서비스에 연결할 수 없어 청산을 시작하지 않았습니다.",
        ) from exc
    if user_lease is None:
        raise HTTPException(
            status_code=409,
            detail="이미 이 계정의 다른 거래 작업이 진행 중입니다.",
        )

    try:
        holdings = db.query(Holding).filter(Holding.user_id == current_user.id).all()
        if not holdings:
            return {"message": "현재 보유 주식이 없어 청산할 주식이 없습니다."}
        if has_unresolved_orders(db, current_user.id):
            raise HTTPException(
                status_code=409,
                detail="미해결 증권사 주문이 있어 전량 청산을 시작할 수 없습니다.",
            )

        broker = get_broker_client(current_user.settings)
        liquidated_tickers = []
        trade_mode = (current_user.settings.trade_mode or "SIMULATED").upper()
        is_kis_order = trade_mode in {"MOCK", "REAL"}

        from app.bot.market_session import MarketSession
        if is_kis_order:
            from app.bot.scheduler import get_market_session

            market_session = get_market_session()
            if market_session == MarketSession.CLOSED:
                raise HTTPException(
                    status_code=400,
                    detail="미국 시장이 닫혀 있어 전량 청산 주문을 전송할 수 없습니다.",
                )
        else:
            market_session = MarketSession.REGULAR

        for holding in holdings:
            clean_ticker = holding.ticker
            symbol_request_id = str(uuid4())
            try:
                symbol_lease = await acquire_symbol_order_lock(
                    current_user.id,
                    clean_ticker,
                    symbol_request_id,
                )
            except RedisLockUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"{clean_ticker} 주문 락을 확인할 수 없어 청산을 중단했습니다.",
                ) from exc
            if symbol_lease is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"{clean_ticker} 주문이 이미 진행 중입니다.",
                )

            try:
                try:
                    df = await fetch_ohlcv(clean_ticker, interval="1m", period="1d")
                    price = (
                        float(df["Close"].iloc[-1])
                        if not df.empty
                        else holding.highest_price or holding.avg_price
                    )
                except Exception:
                    price = holding.highest_price or holding.avg_price

                if is_kis_order:
                    metadata = await run_in_threadpool(
                        broker.get_order_metadata,
                        clean_ticker,
                        market_session,
                    )
                    order_intent = create_order_intent(
                        db,
                        current_user.settings,
                        side="SELL",
                        ticker=clean_ticker,
                        prefixed_ticker=holding.ticker,
                        strategy_type=holding.strategy_type,
                        ticker_name=holding.ticker_name,
                        requested_qty=holding.quantity,
                        submitted_price=price,
                        exchange_code=metadata.get("exchange_code"),
                        order_division=metadata.get("order_division"),
                        regime_mode="LIQUIDATE",
                        signal_score=0,
                        sell_reason="사용자 수동 전량 청산",
                        source="MANUAL_LIQUIDATION",
                    )
                    begin_order_submission(db, order_intent, current_user.settings)
                    try:
                        result = await run_in_threadpool(
                            broker.sell_order,
                            ticker=clean_ticker,
                            quantity=holding.quantity,
                            price=price,
                            session=market_session,
                            client_order_id=order_intent.intent_id,
                        )
                    except Exception as exc:
                        result = {
                            "success": False,
                            "order_submitted": True,
                            "submission_unknown": True,
                            "status": "ACK_UNKNOWN",
                            "order_no": "",
                            "filled_qty": 0,
                            "filled_price": 0.0,
                            "fill_confirmed": False,
                            "message": f"Broker acknowledgement unknown: {exc}",
                        }

                    application = finalize_order_submission(
                        db,
                        order_intent,
                        current_user.settings,
                        result,
                    )
                    if application.applied_qty > 0:
                        liquidated_tickers.append(holding.ticker)
                    if application.is_unresolved:
                        return {
                            "message": (
                                f"{holding.ticker} 청산 주문이 {order_intent.status} 상태입니다. "
                                "사용자 봇 설정을 유지하고 주문 재조정을 계속합니다."
                            )
                        }
                    if not result.get("success"):
                        return {
                            "message": (
                                f"{holding.ticker} 청산 주문이 거부되었습니다: "
                                f"{result.get('message', 'Unknown error')}"
                            )
                        }
                    continue

                result = await run_in_threadpool(
                    broker.sell_order,
                    ticker=clean_ticker,
                    quantity=holding.quantity,
                    price=price,
                    session=market_session,
                )
                if not result.get("success"):
                    continue

                filled_price = float(result.get("filled_price", price))
                filled_qty = int(result.get("filled_qty", holding.quantity))
                if filled_qty <= 0 or filled_qty > holding.quantity:
                    raise ValueError(
                        f"Invalid liquidation fill quantity for {holding.ticker}: {filled_qty}"
                    )
                order_no = result.get("order_no", "LIQUIDATE_MANUAL")
                buy_gross = holding.avg_price * filled_qty
                buy_fee = buy_gross * app_settings.SIMULATED_FEE_RATE
                sell_gross = filled_price * filled_qty
                sell_fee = sell_gross * app_settings.SIMULATED_FEE_RATE
                sec_fee = sell_gross * app_settings.SEC_FEE_RATE
                realized_pnl = sell_gross - buy_gross - buy_fee - sell_fee - sec_fee
                calc_return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0

                db.add(TradeLog(
                    user_id=current_user.id,
                    ticker=holding.ticker,
                    strategy_type=holding.strategy_type,
                    ticker_name=holding.ticker_name,
                    trade_type="SELL",
                    price=filled_price,
                    quantity=filled_qty,
                    order_no=order_no,
                    regime_mode="LIQUIDATE",
                    signal_score=0,
                    realized_pnl=round(realized_pnl, 2),
                    return_rate=round(calc_return_rate, 2),
                ))
                if filled_qty == holding.quantity:
                    db.delete(holding)
                else:
                    holding.quantity -= filled_qty
                db.commit()
                liquidated_tickers.append(holding.ticker)
            finally:
                await symbol_lease.release()

        return {
            "message": (
                f"보유 중인 {len(liquidated_tickers)}개 종목"
                f"({', '.join(liquidated_tickers)})이 시장가 청산 처리되었습니다."
            )
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"일괄 청산 과정 중 오류가 발생했습니다: {str(exc)}",
        ) from exc
    finally:
        await user_lease.release()
