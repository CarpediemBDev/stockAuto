from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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
    has_unresolved_orders_for_ticker,
)
from app.bot.trade_calculations import calculate_realized_pnl, fee_rate_for_trade_mode
import app.bot.scheduler as scheduler_mod
from app.trades.equity_snapshot import record_equity_snapshot
from app.core.equity_repository import get_latest_equity_snapshot
from fastapi.concurrency import run_in_threadpool
from app.core.dependencies import get_current_user
from app.core.holding_audit import delete_holding
from app.core.models import (
    User, Holding, TradeLog, ActionLog, utc_now_aware,
    MANAGEMENT_BOT_OWNED, MANAGEMENT_EXTERNAL,
    GUARD_ACTIONS, GUARD_ACTION_ALERT_ONLY,
)
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
    # 관할권은 티커 단위로 합쳐서 본다. 같은 티커를 봇 슬롯과 EXTERNAL로 동시에 보유할 수
    # 있는데(유니크 제약이 strategy_type까지 포함), 브로커 응답은 티커 하나로 합쳐서 오므로
    # 하나라도 봇 관할이면 봇 관할로 표시한다 - "안 건드림" 뱃지를 잘못 붙여 사용자가
    # 봇이 매도하지 않을 것으로 오인하는 쪽이 반대 오류보다 위험하다.
    management_by_ticker: dict[str, str] = {}
    # 수확 상태는 EXTERNAL 행에만 존재하므로 관할권 집계와 별도로 원본 행을 들고 간다.
    external_by_ticker: dict[str, Holding] = {}
    # 브로커 응답은 티커 하나로 합쳐 오지만 DB는 슬라이스별로 나뉜다. 매도 대상을 지정하려면
    # 클라이언트가 슬라이스 목록을 알아야 하는데, 응답의 id는 이 용도로 쓸 수 없다 -
    # KIS 경로는 목록 순번(idx+1000)을 id로 발급해 청산 한 번에 나머지 행의 id가 전부 밀리고,
    # Toss 경로는 id 자체가 없다. 매도 대상의 안정적인 키는 (ticker, strategy_type)이다.
    slices_by_ticker: dict[str, list[dict]] = {}
    for holding in db_holdings:
        value = holding.management or MANAGEMENT_BOT_OWNED
        if value == MANAGEMENT_EXTERNAL:
            external_by_ticker.setdefault(holding.ticker, holding)
        slices_by_ticker.setdefault(holding.ticker, []).append({
            "strategy_type": holding.strategy_type,
            "management": value,
            "quantity": holding.quantity,
        })
        if management_by_ticker.get(holding.ticker) == MANAGEMENT_BOT_OWNED:
            continue
        management_by_ticker[holding.ticker] = value
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
        management = management_by_ticker.get(
            holding.get("ticker"), MANAGEMENT_BOT_OWNED
        )
        holding["management"] = management
        holding["slices"] = slices_by_ticker.get(holding.get("ticker"), [])
        external_row = external_by_ticker.get(holding.get("ticker"))
        if external_row is not None:
            holding["harvest_enabled"] = bool(external_row.harvest_enabled)
            holding["harvest_armed"] = bool(external_row.harvest_armed)
            holding["observed_base_price"] = (
                float(external_row.observed_base_price)
                if external_row.observed_base_price is not None
                else None
            )
            holding["guard_enabled"] = bool(external_row.guard_enabled)
            holding["guard_baseline_score"] = external_row.guard_baseline_score
            holding["guard_baseline_low"] = (
                float(external_row.guard_baseline_low)
                if external_row.guard_baseline_low is not None
                else None
            )
            holding["guard_action"] = external_row.guard_action or GUARD_ACTION_ALERT_ONLY
            holding["guard_sell_ratio"] = float(external_row.guard_sell_ratio or 0.5)
        if management == MANAGEMENT_EXTERNAL:
            # EXTERNAL의 strategy_type("external")은 전략 카탈로그에 없어 번역기가
            # "단일 전략 (external)" 같은 폴백 문자열을 낸다. 전략이 아니라 관할권이므로
            # 표시 이름을 여기서 확정한다.
            holding["strategy_name"] = "봇 관리 안 함"
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
        # 여기만 delete_holding을 거치지 않는다(누락이 아니다). 계좌 초기화는 ActionLog까지
        # 함께 지우므로 감사 로그를 남겨도 같은 트랜잭션에서 사라진다. 사용자가 명시적으로
        # 요청한 전체 초기화라 "왜 사라졌는지"를 나중에 물을 일도 없다.
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

class HoldingManagementRequest(BaseModel):
    """보유 종목의 봇 위임 스위치 변경 요청.

    현재는 수확(harvest) 하나뿐이고 방어 경보·위임 스위치가 뒤에 붙는다. 스위치를 켜는
    행위 자체는 주문을 내지 않으므로 confirm 게이트를 두지 않는다 - 되돌릴 수 있고,
    끄면 즉시 봇이 손을 뗀다.
    """
    strategy_type: str | None = Field(default=None, description="같은 티커를 여러 슬라이스로 보유한 경우 대상 지정")
    harvest_enabled: bool | None = Field(default=None, description="급등 후 고점 이탈 시 자동 수확")
    guard_enabled: bool | None = Field(default=None, description="추가 악화 + 신저가 시 경보 전송. 매도는 하지 않는다")
    guard_action: str | None = Field(
        default=None,
        description="방어 조건 충족 시 동작. ALERT_ONLY(기본) / SHADOW(기록만) / LIQUIDATE(부분 청산)",
    )
    guard_sell_ratio: float | None = Field(
        default=None, gt=0.0, le=1.0, description="LIQUIDATE 시 매도 비율. 기본 0.5",
    )


@router.patch("/holdings/{ticker}/management")
def update_holding_management(
    ticker: str,
    payload: HoldingManagementRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """봇 관할 밖(EXTERNAL) 보유분의 위임 스위치를 켜고 끈다.

    EXTERNAL의 기본 계약은 "봇이 아무것도 안 함"이고, 사용자가 종목별로 원하는 만큼만
    권한을 연다. 봇이 산 종목(BOT_OWNED)에는 이 선택지가 없다 - 봇이 자기 규칙으로 산
    포지션을 규칙에서 빼면 계좌에 좀비 포지션이 쌓이고 전략 성과 측정이 깨진다.
    """
    clean_ticker = (ticker or "").strip().upper()
    holding = _resolve_target_holding(
        db, current_user.id, clean_ticker, payload.strategy_type
    )

    if (holding.management or MANAGEMENT_BOT_OWNED) != MANAGEMENT_EXTERNAL:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{clean_ticker}는 봇이 매수한 종목이라 위임 스위치를 바꿀 수 없습니다. "
                "봇 관할 밖(EXTERNAL) 보유분에만 적용됩니다."
            ),
        )

    if payload.harvest_enabled is not None:
        holding.harvest_enabled = payload.harvest_enabled
        if not payload.harvest_enabled:
            # 끄면 무장도 함께 해제한다. 다시 켰을 때 예전 무장 상태를 물려받으면
            # 급등 판정 없이 곧바로 매도 판정 구간에 들어간다.
            holding.harvest_armed = False

    # 스위치를 하나라도 건드리면 연속 충족을 두 축 모두 0부터 다시 센다.
    #
    # 횟수만 되돌리고 시각을 남기면 스케줄러의 (streak_started_at or now)가 옛 시각을
    # 물려받아 벽시계 가드가 처음부터 통과 상태가 된다. 즉 "되돌릴 수 없는 매도를 켠
    # 순간부터 20분은 지켜본다"는 보호가 시간 축에서만 조용히 뚫린다. 사이클 게이트가
    # 남아 있어 즉시 팔리지는 않으므로 눈에 잘 띄지 않는다.
    #
    # 분기마다 따로 쓰지 않고 여기서 한 번에 처리하는 이유는, 실제로 분기 네 개 중
    # 세 개에서 누락이 났기 때문이다(2026-09-06 stock-auto-mobile 세션 보고).
    def _restart_streak() -> None:
        holding.guard_streak = 0
        holding.guard_streak_started_at = None

    if payload.guard_enabled is not None:
        _restart_streak()
        holding.guard_enabled = payload.guard_enabled
        if payload.guard_enabled:
            # 기준선(점수·저가)은 시세를 아는 스케줄러가 다음 사이클에 채운다. 여기서는
            # 유예기간의 기준 시각만 박고 기준선을 비워 재설정을 유도한다 - 껐다 켤 때
            # 예전 기준선을 물려받으면 그 사이의 하락이 전부 "추가 악화"로 잡힌다.
            holding.guard_enabled_at = utc_now_aware()
            holding.guard_baseline_score = None
            holding.guard_baseline_low = None
            holding.guard_last_alert_at = None
        else:
            holding.guard_enabled_at = None
            holding.guard_baseline_score = None
            holding.guard_baseline_low = None
            # 조치 모드도 기본값으로 되돌린다. 끌 때 LIQUIDATE가 남으면, 나중에 방어를 다시
            # 켜는 순간 사용자가 의도하지 않은 채 청산 모드로 재개된다. 되돌릴 수 없는 매도는
            # 매번 명시적으로 선택되어야 한다 - 기준선·streak을 리셋하면서 모드만 남길 이유가 없다.
            holding.guard_action = GUARD_ACTION_ALERT_ONLY

    if payload.guard_action is not None:
        action = payload.guard_action.strip().upper()
        if action not in GUARD_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"허용되지 않은 guard_action입니다: {payload.guard_action}. 허용: {list(GUARD_ACTIONS)}",
            )
        if action != GUARD_ACTION_ALERT_ONLY and not (
            payload.guard_enabled if payload.guard_enabled is not None else holding.guard_enabled
        ):
            raise HTTPException(
                status_code=400,
                detail="방어 경보가 꺼진 상태에서는 조치 모드를 바꿀 수 없습니다. guard_enabled를 먼저 켜세요.",
            )
        holding.guard_action = action
        # 알림만으로 쌓인 연속 충족이 청산 모드로 전환하는 순간 조치 임계를 넘기면,
        # 사용자가 켠 직후 바로 팔리게 된다.
        _restart_streak()

    if payload.guard_sell_ratio is not None:
        # 비율 변경도 조치의 결과를 바꾼다(25%와 100%는 다른 결정이다). 같은 기준으로 다시 센다.
        holding.guard_sell_ratio = float(payload.guard_sell_ratio)
        _restart_streak()

    db.commit()
    db.refresh(holding)
    return {
        "ticker": holding.ticker,
        "strategy_type": holding.strategy_type,
        "management": holding.management,
        "harvest_enabled": bool(holding.harvest_enabled),
        "harvest_armed": bool(holding.harvest_armed),
        "observed_base_price": (
            float(holding.observed_base_price)
            if holding.observed_base_price is not None
            else None
        ),
        "guard_enabled": bool(holding.guard_enabled),
        "guard_baseline_score": holding.guard_baseline_score,
        "guard_baseline_low": (
            float(holding.guard_baseline_low)
            if holding.guard_baseline_low is not None
            else None
        ),
        "guard_action": holding.guard_action or GUARD_ACTION_ALERT_ONLY,
        "guard_sell_ratio": float(holding.guard_sell_ratio or 0.5),
    }


class SellHoldingRequest(BaseModel):
    """개별 종목 매도 요청.

    confirm 기본값이 False인 것이 이 계약의 핵심이다. 되돌릴 수 없는 금융 액션이므로
    첫 호출은 항상 주문 없는 프리뷰가 되고, 호출자가 명시적으로 confirm=true를 보내야
    주문이 나간다. user_id는 인증 세션에서만 도출하며 본문에서 받지 않는다
    (크로스유저 주문 주입 차단 - app/mcp/router.py docstring이 요구하는 조건).
    """
    quantity: int | None = Field(default=None, ge=1, description="매도 수량. 생략하면 전량")
    strategy_type: str | None = Field(default=None, description="같은 티커를 여러 슬라이스로 보유한 경우 대상 지정")
    confirm: bool = Field(default=False, description="true여야 실제 주문이 나간다. false면 프리뷰만")


def _resolve_target_holding(
    db: Session, user_id: int, ticker: str, strategy_type: str | None
) -> Holding:
    """티커로 매도 대상 슬라이스를 특정한다.

    같은 티커를 봇 슬롯과 EXTERNAL로 동시에 보유할 수 있으므로(유니크 제약이
    strategy_type까지 포함), 후보가 둘 이상인데 지정이 없으면 임의로 고르지 않고 거절한다.
    임의 선택은 사용자가 의도하지 않은 슬라이스를 파는 사고로 이어진다.
    """
    candidates = db.query(Holding).filter(
        Holding.user_id == user_id,
        Holding.ticker == ticker,
    ).all()
    candidates = [h for h in candidates if (h.quantity or 0) > 0]

    if not candidates:
        raise HTTPException(status_code=404, detail=f"보유하지 않은 종목입니다: {ticker}")

    if strategy_type:
        for h in candidates:
            if h.strategy_type == strategy_type:
                return h
        raise HTTPException(
            status_code=404,
            detail=f"{ticker}의 {strategy_type} 슬라이스를 보유하고 있지 않습니다.",
        )

    if len(candidates) > 1:
        slices = ", ".join(
            f"{h.strategy_type}({h.quantity}주, {h.management or MANAGEMENT_BOT_OWNED})"
            for h in candidates
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"{ticker}를 여러 슬라이스로 보유하고 있어 대상을 특정해야 합니다. "
                f"strategy_type을 지정하세요 - 후보: {slices}"
            ),
        )
    return candidates[0]


@router.post("/holdings/{ticker}/sell")
async def sell_holding(
    ticker: str,
    payload: SellHoldingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보유 중인 개별 종목을 시장가로 매도한다. 기본은 주문 없는 프리뷰.

    전량 청산(/force-liquidate)만 있고 종목을 지정해 파는 경로가 없어서, 봇 관할 밖
    (EXTERNAL) 보유분의 계약인 "봇이 안 건드림 = 사용자가 직접 관리"를 앱 안에서
    이행할 수단이 없었다. 이 엔드포인트가 그 수단이다.

    지키는 조건 3가지(app/mcp/router.py docstring):
      - user_id는 인증 세션에서만 도출한다. 요청 본문의 사용자 식별자는 받지 않는다
      - 파괴적 명령은 confirm 게이트 없이 실행하지 않고 먼저 dry-run 프리뷰를 준다
      - 자동 스캐너 봇과의 경합을 막기 위해 사용자·심볼 주문 락을 경유한다
    """
    clean_ticker = (ticker or "").strip().upper()
    if not clean_ticker:
        raise HTTPException(status_code=400, detail="종목 코드가 비어 있습니다.")

    holding = _resolve_target_holding(
        db, current_user.id, clean_ticker, payload.strategy_type
    )
    available_qty = int(holding.quantity or 0)
    sell_qty = int(payload.quantity) if payload.quantity is not None else available_qty
    if sell_qty <= 0:
        raise HTTPException(status_code=400, detail="매도 수량은 1주 이상이어야 합니다.")
    if sell_qty > available_qty:
        raise HTTPException(
            status_code=400,
            detail=f"보유 수량({available_qty}주)보다 많이 매도할 수 없습니다.",
        )

    trade_mode = (current_user.settings.trade_mode or "SIMULATED").upper()
    is_kis_order = trade_mode in {"MOCK", "REAL"}

    from app.bot.market_session import MarketSession
    if is_kis_order:
        from app.bot.market_session import get_market_session

        market_session = get_market_session()
        if market_session == MarketSession.CLOSED:
            raise HTTPException(
                status_code=400,
                detail="미국 시장이 닫혀 있어 매도 주문을 전송할 수 없습니다.",
            )
    else:
        market_session = MarketSession.REGULAR

    price = await _resolve_market_price(holding)
    management = holding.management or MANAGEMENT_BOT_OWNED

    # ---- 프리뷰: 주문을 내지 않고 예상 결과만 돌려준다 ----
    if not payload.confirm:
        pnl = calculate_realized_pnl(
            avg_price=holding.avg_price,
            filled_price=price,
            quantity=sell_qty,
            fee_rate=fee_rate_for_trade_mode(trade_mode),
        )
        return {
            "preview": True,
            "ticker": holding.ticker,
            "ticker_name": holding.ticker_name,
            "strategy_type": holding.strategy_type,
            "management": management,
            "held_quantity": available_qty,
            "sell_quantity": sell_qty,
            "estimated_price": price,
            "estimated_proceeds": round(price * sell_qty, 2),
            "estimated_realized_pnl": round(pnl.realized_pnl, 2),
            "estimated_return_rate": round(pnl.return_rate, 2),
            "message": (
                f"{holding.ticker} {sell_qty}주를 약 ${price:,.2f}에 매도할 예정입니다. "
                "실제로 실행하려면 confirm=true로 다시 요청하세요."
            ),
        }

    # ---- 실행: 여기서부터 주문이 나간다 ----
    if has_unresolved_orders_for_ticker(db, current_user.id, clean_ticker):
        raise HTTPException(
            status_code=409,
            detail=f"{clean_ticker}에 미해결 증권사 주문이 있어 매도를 시작할 수 없습니다.",
        )

    operation_id = str(uuid4())
    try:
        user_lease = await acquire_user_operation_lock(current_user.id, operation_id)
    except RedisLockUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="주문 동시성 제어 서비스에 연결할 수 없어 매도를 시작하지 않았습니다.",
        ) from exc
    if user_lease is None:
        raise HTTPException(
            status_code=409,
            detail="이미 이 계정의 다른 거래 작업이 진행 중입니다.",
        )

    try:
        symbol_request_id = str(uuid4())
        try:
            symbol_lease = await acquire_symbol_order_lock(
                current_user.id, clean_ticker, symbol_request_id
            )
        except RedisLockUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail=f"{clean_ticker} 주문 락을 확인할 수 없어 매도를 시작하지 않았습니다.",
            ) from exc
        if symbol_lease is None:
            raise HTTPException(
                status_code=409,
                detail=f"{clean_ticker} 주문이 이미 진행 중입니다.",
            )

        try:
            broker = get_broker_client(current_user.settings)
            outcome = await _sell_holding_slice(
                db,
                current_user,
                broker,
                holding,
                sell_qty,
                price=price,
                trade_mode=trade_mode,
                is_kis_order=is_kis_order,
                market_session=market_session,
                regime_label="MANUAL_SELL",
                sell_reason="사용자 수동 개별 매도",
                source="MANUAL_SELL",
            )
        finally:
            await symbol_lease.release()

        if not is_kis_order:
            db.commit()
            empty = (
                db.query(Holding)
                .filter(Holding.id == holding.id, Holding.quantity <= 0)
                .first()
            )
            if empty is not None:
                delete_holding(db, empty, actor="router_account.sell_holding",
                               reason="manual sell drained the slice")
                db.commit()
        else:
            db.commit()

        remaining = (
            db.query(Holding.quantity).filter(Holding.id == holding.id).scalar() or 0
        )
        return {
            "preview": False,
            "ticker": clean_ticker,
            "strategy_type": holding.strategy_type,
            "management": management,
            "status": outcome["status"],
            "sold_quantity": outcome.get("applied_qty", 0),
            "remaining_quantity": int(remaining),
            "filled_price": outcome.get("filled_price"),
            "realized_pnl": outcome.get("realized_pnl"),
            "return_rate": outcome.get("return_rate"),
            "message": outcome["message"],
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"개별 매도 처리 중 오류가 발생했습니다: {str(exc)}",
        ) from exc
    finally:
        await user_lease.release()


async def _resolve_market_price(holding: Holding) -> float:
    """시세 조회에 실패해도 주문을 포기하지 않도록 최고가·평단가로 폴백한다."""
    try:
        df = await fetch_ohlcv(holding.ticker, interval="1m", period="1d")
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return float(holding.highest_price or holding.avg_price)


async def _sell_holding_slice(
    db: Session,
    current_user: User,
    broker,
    holding: Holding,
    sell_qty: int,
    *,
    price: float,
    trade_mode: str,
    is_kis_order: bool,
    market_session,
    regime_label: str,
    sell_reason: str,
    source: str,
) -> dict:
    """보유 슬라이스 하나를 시장가로 매도한다. 전량 청산과 개별 매도의 공통 실행부.

    심볼 주문 락과 사용자 작업 락은 호출자가 잡는다 - 락 획득 실패의 응답 코드가
    호출 맥락마다 달라야 하기 때문이다(전량 청산은 중단, 개별 매도는 409).

    이 함수를 둘로 나누지 않는 이유: 주문 인텐트 생성·제출·정산(ACK_UNKNOWN 포함)과
    실현손익·수수료 계산이 매도 경로마다 복제되면 한쪽만 고쳐지는 순간 금액이 갈린다.
    반환값은 호출자가 응답을 조립할 수 있도록 결과만 담고 HTTP 예외를 던지지 않는다.
    """
    clean_ticker = holding.ticker

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
            requested_qty=sell_qty,
            submitted_price=price,
            exchange_code=metadata.get("exchange_code"),
            order_division=metadata.get("order_division"),
            regime_mode=regime_label,
            signal_score=0,
            sell_reason=sell_reason,
            source=source,
        )
        begin_order_submission(db, order_intent, current_user.settings)
        try:
            result = await run_in_threadpool(
                broker.sell_order,
                ticker=clean_ticker,
                quantity=sell_qty,
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
            db, order_intent, current_user.settings, result,
        )
        if application.is_unresolved:
            return {
                "status": "unresolved",
                "applied_qty": application.applied_qty,
                "order_status": order_intent.status,
                "message": (
                    f"{holding.ticker} 매도 주문이 {order_intent.status} 상태입니다. "
                    "사용자 봇 설정을 유지하고 주문 재조정을 계속합니다."
                ),
            }
        if not result.get("success"):
            return {
                "status": "rejected",
                "applied_qty": application.applied_qty,
                "message": (
                    f"{holding.ticker} 매도 주문이 거부되었습니다: "
                    f"{result.get('message', 'Unknown error')}"
                ),
            }
        return {
            "status": "filled" if application.applied_qty > 0 else "pending",
            "applied_qty": application.applied_qty,
            "filled_price": application.filled_price,
            "message": f"{holding.ticker} 매도 주문이 처리되었습니다.",
        }

    result = await run_in_threadpool(
        broker.sell_order,
        ticker=clean_ticker,
        quantity=sell_qty,
        price=price,
        session=market_session,
        strategy_type=holding.strategy_type,
        regime_mode=regime_label,
        signal_score=0,
    )
    if not result.get("success"):
        return {
            "status": "rejected",
            "applied_qty": 0,
            "message": (
                f"{holding.ticker} 매도 주문이 거부되었습니다: "
                f"{result.get('message', 'Unknown error')}"
            ),
        }

    filled_price = float(result.get("filled_price", price))
    filled_qty = int(result.get("filled_qty", sell_qty))
    if filled_qty <= 0 or filled_qty > sell_qty:
        raise ValueError(
            f"Invalid sell fill quantity for {holding.ticker}: {filled_qty}"
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
        raise ValueError(
            f"Concurrency error: Failed to sell {holding.ticker} (insufficient quantity)"
        )

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
        regime_mode=regime_label,
        signal_score=0,
        realized_pnl=round(pnl.realized_pnl, 2),
        return_rate=round(pnl.return_rate, 2),
    ))
    return {
        "status": "filled",
        "applied_qty": filled_qty,
        "filled_price": filled_price,
        "order_no": order_no,
        "realized_pnl": round(pnl.realized_pnl, 2),
        "return_rate": round(pnl.return_rate, 2),
        "message": f"{holding.ticker} {filled_qty}주가 시장가로 매도되었습니다.",
    }


@router.post("/force-liquidate")
async def force_liquidate(
    include_external: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [개인투자자 위험 영역] 보유 중인 모든 종목 즉시 시장가 전량 강제 매도 청산.
    현재 보유 중인 모든 종목을 실시간 시장 가격으로 일괄 일시 처분합니다.

    봇 관할 밖(EXTERNAL) 보유분은 기본적으로 제외한다. 사용자가 봇 도입 이전에 직접
    매수한 종목까지 이 버튼 하나로 함께 처분되면 "봇이 안 건드린다"는 계약이 깨지기
    때문이다. 함께 청산하려면 include_external=true를 명시해야 한다 - 기본값이 안전한
    쪽이어야 하고, 위험한 쪽은 호출자가 의도를 드러내야 한다.
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
        all_holdings = db.query(Holding).filter(Holding.user_id == current_user.id).all()
        if not all_holdings:
            return {"message": "현재 보유 주식이 없어 청산할 주식이 없습니다."}

        external_holdings = [
            h for h in all_holdings
            if (h.management or MANAGEMENT_BOT_OWNED) == MANAGEMENT_EXTERNAL
        ]
        holdings = all_holdings if include_external else [
            h for h in all_holdings if h not in external_holdings
        ]
        excluded_external_count = 0 if include_external else len(external_holdings)
        if not holdings:
            return {
                "message": (
                    f"봇 관할 밖(EXTERNAL) 보유 {excluded_external_count}종목만 있어 청산할 대상이 없습니다. "
                    "이 종목까지 청산하려면 include_external=true로 다시 요청하세요."
                ),
                "excluded_external_count": excluded_external_count,
                "liquidated_tickers": [],
            }
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
                price = await _resolve_market_price(holding)
                outcome = await _sell_holding_slice(
                    db,
                    current_user,
                    broker,
                    holding,
                    holding.quantity,
                    price=price,
                    trade_mode=trade_mode,
                    is_kis_order=is_kis_order,
                    market_session=market_session,
                    regime_label="LIQUIDATE",
                    sell_reason="사용자 수동 전량 청산",
                    source="MANUAL_LIQUIDATION",
                )
                if outcome.get("applied_qty", 0) > 0:
                    liquidated_tickers.append(holding.ticker)
                # 전량 청산은 미해결·거부를 만나면 나머지 종목을 건드리지 않고 즉시 보고한다.
                # 부분적으로 처분된 상태에서 계속 진행하면 사용자가 어디까지 팔렸는지 알 수 없다.
                if outcome["status"] == "unresolved":
                    return {"message": outcome["message"].replace("매도 주문", "청산 주문")}
                if outcome["status"] == "rejected":
                    if is_kis_order:
                        return {"message": outcome["message"].replace("매도 주문", "청산 주문")}
                    continue
            finally:
                await symbol_lease.release()

        if not is_kis_order:
            db.commit()

            empty_holdings = db.query(Holding).filter(Holding.user_id == current_user.id, Holding.quantity <= 0).all()
            for eh in empty_holdings:
                delete_holding(db, eh, actor="router_account.force_liquidate",
                               reason="liquidation drained the slice")
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

        external_notice = (
            f" 봇 관할 밖(EXTERNAL) {excluded_external_count}종목은 제외했습니다 - "
            "함께 청산하려면 include_external=true로 요청하세요."
            if excluded_external_count
            else ""
        )
        return {
            "message": (
                f"보유 중인 {len(liquidated_tickers)}개 종목"
                f"({', '.join(liquidated_tickers)})이 시장가 청산 처리되었습니다."
                f"{external_notice}"
            ),
            "excluded_external_count": excluded_external_count,
            "liquidated_tickers": liquidated_tickers,
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
