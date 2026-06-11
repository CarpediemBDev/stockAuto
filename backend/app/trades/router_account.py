from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.scanner.data_provider import fetch_ohlcv

from app.core.database import get_db
from app.bot.broker_factory import get_broker_client
from app.bot.order_reconciler import (
    begin_order_submission,
    create_order_intent,
    finalize_order_submission,
    has_unresolved_orders,
)
from app.core.response import success_response
from fastapi.concurrency import run_in_threadpool
from app.core.dependencies import get_current_user
from app.core.models import User, Holding, TradeLog, ActionLog
from app.core.config import settings as app_settings

router = APIRouter(tags=["Account"])

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

        total_asset_krw = balance.get("total_asset", 10000000.0)
        cash_balance_krw = balance.get("cash_balance", 10000000.0)

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

        # 💡 실시간 최정예 돌파 레이더 종목 (RVOL >= 2.0 이상 및 거래량 응축 종목)
        latest_signals = getattr(scheduler_mod, 'latest_scanned_signals', [])
        focused_set = ms_manager.get_focused_tickers(latest_signals)
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
                    "cash": int(balance.get("cash_balance", 10000000.0) * slot_info["weight"]),
                    "stock_value": 0,
                    "name": slot_info.get("name", slot_key),
                    "weight": slot_info.get("weight", 1.0)
                }
                for slot_key, slot_info in ms_manager.SLOTS.items()
            }
        except Exception:
            balance["wallet_allocation"] = {
                "regime_switching": {"cash": int(balance.get("cash_balance", 10000000.0) * 0.5), "stock_value": 0, "name": "마스터 레짐스위칭 V2", "weight": 0.5},
                "episodic_pivot": {"cash": int(balance.get("cash_balance", 10000000.0) * 0.5), "stock_value": 0, "name": "에피소딕 피벗 (Episodic Pivot)", "weight": 0.5}
            }
        balance["focused_radar_tickers"] = []

    return success_response(data=balance)

@router.get("/holdings")
def get_holdings(current_user: User = Depends(get_current_user)):
    """
    현재 로그인한 사용자의 UserSettings에 맞춰 알맞은 증권사 API(또는 로컬 시뮬레이터)를 호출하여
    현재 보유 중인 종목 리스트와 개별 수익률을 가져옵니다.
    """
    broker = get_broker_client(current_user.settings)
    holdings = broker.get_holdings()
    return success_response(data=holdings)

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
        return success_response(message="가상 모의투자 계좌 자산 및 로그가 성공적으로 초기화되었습니다.")
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
    holdings = db.query(Holding).filter(Holding.user_id == current_user.id).all()
    if not holdings:
        return success_response(message="현재 보유 주식이 없어 청산할 주식이 없습니다.")
    if has_unresolved_orders(db, current_user.id):
        raise HTTPException(
            status_code=409,
            detail="미해결 증권사 주문이 있어 전량 청산을 시작할 수 없습니다.",
        )



    broker = get_broker_client(current_user.settings)
    liquidated_tickers = []
    trade_mode = (current_user.settings.trade_mode or "SIMULATED").upper()
    is_kis_order = trade_mode in {"MOCK", "REAL"}
    was_running = bool(current_user.settings.is_running)

    if is_kis_order:
        from app.bot.scheduler import get_market_session

        market_session = get_market_session()
        if market_session == "CLOSED":
            raise HTTPException(
                status_code=400,
                detail="미국 시장이 닫혀 있어 전량 청산 주문을 전송할 수 없습니다.",
            )
        current_user.settings.is_running = False
        db.commit()
    else:
        market_session = "REGULAR_MARKET"

    try:
        for h in holdings:
            clean_ticker = h.ticker

            # 실시간 청산 가격 조회 (데이터 프로바이더 연동으로 결합도 해제)
            try:
                df = await fetch_ohlcv(clean_ticker, interval="1m", period="1d")
                if not df.empty:
                    price = float(df["Close"].iloc[-1])
                else:
                    price = h.highest_price or h.avg_price
            except Exception:
                price = h.highest_price or h.avg_price

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
                    prefixed_ticker=h.ticker,
                    ticker_name=h.ticker_name,
                    requested_qty=h.quantity,
                    submitted_price=price,
                    exchange_code=metadata.get("exchange_code"),
                    order_division=metadata.get("order_division"),
                    regime_mode="LIQUIDATE",
                    signal_score=0,
                    sell_reason="사용자 수동 전량 청산",
                    source="MANUAL_LIQUIDATION",
                    resume_after_resolution=False,
                )
                begin_order_submission(db, order_intent, current_user.settings)
                try:
                    res = await run_in_threadpool(
                        broker.sell_order,
                        ticker=clean_ticker,
                        quantity=h.quantity,
                        price=price,
                        session=market_session,
                        client_order_id=order_intent.intent_id,
                    )
                except Exception as exc:
                    res = {
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
                    res,
                )
                if application.applied_qty > 0:
                    liquidated_tickers.append(h.ticker)
                if application.is_unresolved:
                    return success_response(
                        message=(
                            f"{h.ticker} 청산 주문이 {order_intent.status} 상태입니다. "
                            "자동매매를 정지하고 주문 재조정을 계속합니다."
                        )
                    )
                if not res.get("success"):
                    if was_running:
                        current_user.settings.is_running = True
                        db.commit()
                    return success_response(
                        message=f"{h.ticker} 청산 주문이 거부되었습니다: {res.get('message', 'Unknown error')}"
                    )
                continue

            # SIMULATED 모드는 즉시 체결 결과를 기존 방식으로 반영합니다.
            res = await run_in_threadpool(
                broker.sell_order,
                ticker=clean_ticker,
                quantity=h.quantity,
                price=price,
                session=market_session,
            )

            if res.get("success"):
                filled_price = res.get("filled_price", price)
                filled_qty = res.get("filled_qty", h.quantity)
                order_no = res.get("order_no", "LIQUIDATE_MANUAL")

                # 💡 [수수료 정밀 반영] 스케줄러의 자동 매도와 동일한 수수료 공식 적용
                buy_gross = h.avg_price * filled_qty
                buy_fee = buy_gross * app_settings.KIS_FEE_RATE
                sell_gross = filled_price * filled_qty
                sell_fee = sell_gross * app_settings.KIS_FEE_RATE
                sec_fee = sell_gross * app_settings.SEC_FEE_RATE

                realized_pnl = sell_gross - buy_gross - buy_fee - sell_fee - sec_fee
                calc_return_rate = (realized_pnl / buy_gross) * 100 if buy_gross > 0 else 0.0

                db.add(TradeLog(
                    user_id=current_user.id,
                    ticker=h.ticker,
                    ticker_name=h.ticker_name,
                    trade_type="SELL",
                    price=filled_price,
                    quantity=filled_qty,
                    order_no=order_no,
                    regime_mode="LIQUIDATE",
                    signal_score=0,
                    realized_pnl=round(realized_pnl, 2),
                    return_rate=round(calc_return_rate, 2)
                ))
                db.delete(h)
                liquidated_tickers.append(h.ticker)

        if is_kis_order and was_running:
            current_user.settings.is_running = True
        db.commit()

        return success_response(
            message=f"보유 중인 {len(liquidated_tickers)}개 종목({', '.join(liquidated_tickers)})이 모두 시장가 일괄 청산되었습니다."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"일괄 청산 과정 중 오류가 발생했습니다: {str(e)}")
