from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.scanner.data_provider import fetch_ohlcv
from uuid import uuid4

from app.core.database import get_db
from app.brokers.broker_factory import get_broker_client
from app.bot.order_reconciler import (
    begin_order_submission,
    create_order_intent,
    finalize_order_submission,
    has_unresolved_orders,
)
from app.bot.trade_calculations import calculate_realized_pnl, fee_rate_for_trade_mode
import app.bot.scheduler as scheduler_mod
from app.trades.equity_snapshot import record_equity_snapshot
from app.core.equity_repository import get_latest_equity_snapshot
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

# 참고: 기존 폴링 기반 view-trigger(stale-while-revalidate)는 제거됨. 읽기 경로는 이제
# 스냅샷을 즉시 반환만 한다(트리거 없음). 신선도는 1분 스케줄러(admin_balance_cache_sync)와
# 거래 이벤트 스냅샷이 담당하고, 그 변경을 SSE가 push한다. 구독 라이프사이클 기반 주기
# 갱신은 스트림 내부 구현이 불안정해 미채택 — 후속 과제(스트림 밖 백그라운드 잡)로 남아 있음
# (docs/tasks/2026-07-14.md 인수인계 참조).
def _provider_label(settings_row, trade_mode: str) -> str:
    """스냅샷 응답용 provider 라벨을 브로커 호출 없이 설정값에서 파생합니다."""
    if trade_mode == "SIMULATED":
        return "Simulated"
    provider = (getattr(settings_row, "broker_provider", None) or "").upper()
    if provider == "KIS":
        return "KIS Live" if trade_mode == "REAL" else "KIS Mock"
    if provider == "TOSS":
        return "TOSS"
    return provider or "Unknown"


@router.get("/balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    스냅샷 기반 즉시 응답 잔고 API — 유저 대면 경로에서 외부 네트워크 호출 0건 원칙.

    백그라운드 스케줄러(admin_balance_cache_sync)가 DB에 영속화한 AccountEquitySnapshot을
    읽어 즉시 반환하고, QQQ 레짐·슬롯 지갑 분배·레이더는 메모리 캐시와 DB 숫자만으로 조립합니다.
    스냅샷이 없는 유저(신규 가입·trade_mode 전환 직후)만 최초 1회 직접 계산 후 스냅샷을 저장합니다.
    """
    from app.scanner.scanner import get_cached_market_sentiment
    from app.bot.multi_strategy_manager import MultiStrategyManager
    import app.bot.scheduler as scheduler_mod
    from app.core.models import MarketOverviewSnapshot, utc_now_aware

    settings_row = current_user.settings
    trade_mode = ((settings_row.trade_mode if settings_row else None) or "SIMULATED").upper()

    snapshot = get_latest_equity_snapshot(db, current_user.id, trade_mode)

    if snapshot is not None:
        balance = {
            "total_asset": int(float(snapshot.total_asset)),
            "cash_balance": int(float(snapshot.cash_balance)) if snapshot.cash_balance is not None else 0,
            "stock_balance": int(float(snapshot.stock_balance)) if snapshot.stock_balance is not None else 0,
            "profit_rate": float(snapshot.profit_rate or 0.0),
            "fx_rate": float(snapshot.fx_rate) if snapshot.fx_rate is not None else float(app_settings.SIMULATED_INITIAL_FX_RATE),
            "is_mock": trade_mode != "REAL",
            "provider": _provider_label(settings_row, trade_mode),
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        }
        if snapshot.profit_loss is not None:
            balance["profit_loss"] = int(float(snapshot.profit_loss))
    else:
        # 구멍 1·2 폴백: 스냅샷이 없을 때만 최초 1회 직접 계산 (threadpool로 이벤트 루프 보호)
        # 계산 결과를 즉시 영속화하므로 두 번째 요청부터는 스냅샷 경로를 탄다.
        broker = get_broker_client(settings_row)
        balance = await run_in_threadpool(broker.get_account_balance)
        balance["captured_at"] = utc_now_aware().isoformat()
        try:
            await run_in_threadpool(
                record_equity_snapshot,
                current_user.id, trade_mode, balance, None, True,
            )
        except Exception as persist_error:
            print(f"[Balance] First-time snapshot persist failed: {persist_error}")

    # 시장 레짐: 메모리 캐시 → MarketOverviewSnapshot(DB, 재시작 생존) → NEUTRAL. 네트워크 호출 없음.
    sentiment = get_cached_market_sentiment()
    if not sentiment:
        overview = (
            db.query(MarketOverviewSnapshot)
            .order_by(MarketOverviewSnapshot.created_at.desc(), MarketOverviewSnapshot.id.desc())
            .first()
        )
        sentiment = overview.market_condition if overview else "NEUTRAL"

    try:
        # 💡 각 격리형 슬롯별 지갑 자산 정밀 분배 계산 — 저장된 숫자만 쓰는 순수 로컬 연산
        strategy_type = settings_row.strategy_type if settings_row else "regime_switching"
        ms_manager = MultiStrategyManager(strategy_type=strategy_type)
        exchange_rate = balance.get("fx_rate") or float(app_settings.SIMULATED_INITIAL_FX_RATE)

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
        balance["qqq_regime"] = sentiment or "NEUTRAL"
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

        # 초기화 직후 대시보드에 낡은 스냅샷이 보이지 않도록 즉시 재계산·영속화 (dedup 우회)
        try:
            fresh_balance = get_broker_client(settings).get_account_balance()
            if isinstance(fresh_balance, dict):
                record_equity_snapshot(current_user.id, "SIMULATED", fresh_balance, None, True)
        except Exception as snapshot_error:
            print(f"[Reset Balance] Snapshot refresh failed: {snapshot_error}")

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
            from app.bot.market_session import get_market_session

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
                    strategy_type=holding.strategy_type,
                    regime_mode="LIQUIDATE",
                    signal_score=0,
                )
                if not result.get("success"):
                    continue

                filled_price = float(result.get("filled_price", price))
                filled_qty = int(result.get("filled_qty", holding.quantity))
                if filled_qty <= 0 or filled_qty > holding.quantity:
                    raise ValueError(
                        f"Invalid liquidation fill quantity for {holding.ticker}: {filled_qty}"
                    )
                order_no = result.get("order_no", f"LIQ-{uuid4().hex[:8]}")
                
                from sqlalchemy import update
                update_stmt = (
                    update(Holding)
                    .where(Holding.id == holding.id, Holding.quantity >= filled_qty)
                    .values(quantity=Holding.quantity - filled_qty)
                )
                res = db.execute(update_stmt)
                if res.rowcount == 0:
                    raise ValueError(f"Concurrency error: Failed to liquidate {holding.ticker} (insufficient quantity)")

                pnl = calculate_realized_pnl(
                    avg_price=holding.avg_price,
                    filled_price=filled_price,
                    quantity=filled_qty,
                    fee_rate=fee_rate_for_trade_mode(trade_mode),
                )

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
                    realized_pnl=round(pnl.realized_pnl, 2),
                    return_rate=round(pnl.return_rate, 2),
                ))
                liquidated_tickers.append(holding.ticker)
            finally:
                await symbol_lease.release()

        if not is_kis_order:
            db.commit()

            empty_holdings = db.query(Holding).filter(Holding.user_id == current_user.id, Holding.quantity <= 0).all()
            for eh in empty_holdings:
                db.delete(eh)
            db.commit()

        # 청산 직후 대시보드에 낡은 잔고가 보이지 않도록 스냅샷 즉시 갱신 (dedup 우회)
        try:
            fresh_balance = await run_in_threadpool(broker.get_account_balance)
            if isinstance(fresh_balance, dict):
                await run_in_threadpool(
                    record_equity_snapshot,
                    current_user.id, trade_mode, fresh_balance, None, True,
                )
        except Exception as snapshot_error:
            print(f"[Force Liquidate] Snapshot refresh failed: {snapshot_error}")

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
