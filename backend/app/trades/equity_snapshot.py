"""자산 스냅샷 영속화 공통 로직.

API 컨트롤러(router_account)와 배치 스케줄러(scheduler)가 함께 호출하는 순수
비즈니스 로직을 한 곳에 격리한다. 이 모듈은 core.* 에만 의존하므로 어떤 도메인
라우터/스케줄러에서 import해도 순환 참조를 만들지 않는다. (선례: market_overview_cache)
"""
import math

from app.core.database import SessionLocal
from app.core.models import AccountEquitySnapshot, User, utc_now_aware
from app.core.config import settings
from app.core.logging import logger
from app.core.equity_repository import get_latest_equity_snapshot

# 유저별 관찰계정(obs_ 프리픽스) 여부 캐시. record_equity_snapshot이 매 스냅샷마다
# User 테이블을 재조회하지 않도록 하는 인메모리 메모이제이션(프로세스 수명 동안 유지).
_OBSERVATION_USER_IDS: dict[int, bool] = {}


def record_equity_snapshot(
    user_id: int,
    trade_mode: str,
    balance: dict,
    exchange_rate: float | None = None,
    force: bool = False,
) -> bool:
    """
    잔고 dict를 AccountEquitySnapshot으로 영속화합니다.
    force=True면 dedup을 우회합니다(체결 직후 즉시 갱신용).
    """
    total_asset = balance.get("total_asset")
    if total_asset is None or not math.isfinite(float(total_asset)):
        return False

    captured_at = utc_now_aware()
    snapshot_db = SessionLocal()
    try:
        latest_snapshot = get_latest_equity_snapshot(snapshot_db, user_id, trade_mode)
        # dedup 임계는 55초: 1분 벌크 잡(admin_balance_cache_sync)의 도착 시각이 59.x초로
        # 흔들리면 그 사이클이 통째로 skip되어 스냅샷 공백이 최대 2분으로 벌어지고,
        # 프론트 90초 stale 배지가 정상 상태에서 깜빡인다. 60초 정합 대신 5초 완충을 둔다.
        should_record = (
            force
            or latest_snapshot is None
            or (captured_at - latest_snapshot.captured_at).total_seconds() >= 55.0
        )
        if not should_record:
            return False

        snapshot_db.add(AccountEquitySnapshot(
            user_id=user_id,
            total_asset=float(total_asset),
            cash_balance=balance.get("cash_balance"),
            stock_balance=balance.get("stock_balance"),
            profit_rate=float(balance.get("profit_rate", 0.0)),
            profit_loss=balance.get("profit_loss"),
            fx_rate=balance.get("fx_rate", exchange_rate),
            trade_mode=trade_mode,
            captured_at=captured_at,
        ))
        snapshot_db.flush()

        # 장기 관찰/벤치마크 계정(obs_ 프리픽스)은 롤링 컷에서 제외해 자산곡선 전 구간을
        # 무제한 보존한다. 일반 유저만 보존 상한을 넘는 오래된 스냅샷을 삭제한다.
        is_observation_account = _OBSERVATION_USER_IDS.get(user_id)
        if is_observation_account is None:
            username = (
                snapshot_db.query(User.username)
                .filter(User.id == user_id)
                .scalar()
            )
            if username is None:
                # 고장 난 유저 매핑 가드: 경고 로그를 남기고, 유실 방지를 위해 프루닝에서 제외(defensive guard)
                logger.warning(
                    f"[EQUITY_SNAPSHOT] User id {user_id} not found in database. "
                    "Exempting from retention pruning defensively to prevent accidental data loss."
                )
                is_observation_account = True
            else:
                is_observation_account = username.lower().startswith(
                    settings.OBSERVATION_ACCOUNT_PREFIX.lower()
                )
            _OBSERVATION_USER_IDS[user_id] = is_observation_account

        if not is_observation_account:
            expired_snapshots = (
                snapshot_db.query(AccountEquitySnapshot)
                .filter(
                    AccountEquitySnapshot.user_id == user_id,
                    AccountEquitySnapshot.trade_mode == trade_mode,
                )
                .order_by(AccountEquitySnapshot.captured_at.desc())
                .offset(settings.EQUITY_SNAPSHOT_RETENTION_LIMIT)
                .all()
            )
            for expired_snapshot in expired_snapshots:
                snapshot_db.delete(expired_snapshot)
        snapshot_db.commit()

        # SSE: 스냅샷이 실제로 기록됐을 때만 유저 채널로 invalidate 발행(best-effort).
        # force=True는 체결·청산·리셋 등 거래 이벤트이므로 거래 로그(/trades)도 함께 무효화.
        from app.core import sse
        sse.notify_user_equity(user_id, trade_event=force)
        return True
    except Exception:
        snapshot_db.rollback()
        raise
    finally:
        snapshot_db.close()
