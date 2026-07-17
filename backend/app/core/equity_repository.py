"""자산 스냅샷(AccountEquitySnapshot) 조회 공통 쿼리.

"(user_id, trade_mode)의 최신 스냅샷 1건" 조회가 쓰기 경로(equity_snapshot)·
대시보드 폴백(router_account)·일일 리포트 폴백(telegram) 3곳에 복붙돼 있던 것을
단일 함수로 통합한다. core 레벨에 두어 trades·core 어느 도메인에서 호출해도
하향 의존만 발생하도록 한다(telegram이 core 도메인이라 trades에 두면 역방향).
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.models import AccountEquitySnapshot


def get_latest_equity_snapshot(
    db: Session, user_id: int, trade_mode: str
) -> Optional[AccountEquitySnapshot]:
    """(user_id, trade_mode)의 가장 최신 자산 스냅샷 1건을 반환한다. 없으면 None.

    세션 생성·종료는 호출부 책임이며, 여기서는 넘겨받은 세션을 그대로 사용한다.
    trade_mode 필터를 유지해 모드 전환 시 다른 모드 잔고가 섞이지 않도록 한다.
    """
    return (
        db.query(AccountEquitySnapshot)
        .filter(
            AccountEquitySnapshot.user_id == user_id,
            AccountEquitySnapshot.trade_mode == trade_mode,
        )
        .order_by(AccountEquitySnapshot.captured_at.desc())
        .first()
    )
