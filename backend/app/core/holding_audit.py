"""보유 종목 삭제의 단일 통로.

배경 - 2026-09-06 admin 계정에서 보유 행이 사라졌는데 원인을 특정하지 못했다. 삭제 경로가
8군데인데 로깅이 제각각이라, 원장만 봐서는 "앱이 지웠는지 누가 DB를 직접 건드렸는지"조차
가릴 수 없었다. 그때 원인을 좁힌 유일한 실마리는 매도 로그의 실현손익 역산이었고, 그건
매도가 한 번이라도 일어났기 때문에 가능했다. 동기화 차감처럼 매도 없이 수량만 줄어드는
경로였다면 흔적이 0이라 "줄었다"는 사실조차 알 수 없었다.

그래서 삭제를 이 함수 하나로 모으고 예외 없이 ActionLog를 남긴다. 그러면 소거법이 선다 -
로그 없이 사라진 행은 앱이 지운 것이 아니다.

한계를 분명히 해둔다. 이 가드는 DB 직접 조작을 막지도 기록하지도 못한다. SQL로 직접 지우면
애플리케이션을 거치지 않으므로 어떤 앱 레벨 필드도 채워지지 않는다. 여기서 얻는 것은
"앱 경로는 전부 기록된다"는 불변식이고, DB 조작까지 잡으려면 DB 트리거와 append-only
감사 테이블이 필요하다.
"""

from app.core.logging import logger
from app.core.models import ActionLog, Holding, MANAGEMENT_BOT_OWNED


def delete_holding(db, holding: Holding, *, reason: str, actor: str) -> None:
    """보유 행을 지우고 그 사실을 반드시 ActionLog에 남긴다.

    reason - 왜 지우는지 (예: "sync sweep: not in broker account")
    actor  - 어느 앱 경로인지 (예: "scheduler.sync_broker_holdings")

    커밋은 호출자가 한다. 로그와 삭제가 같은 트랜잭션에 묶여야 "지워졌는데 로그가 없다"거나
    그 반대인 상태가 생기지 않는다.
    """
    if holding is None:
        return

    user_id = holding.user_id
    detail = (
        f"[Holding Deleted] {holding.ticker} qty={holding.quantity} "
        f"strategy={holding.strategy_type} management={holding.management or MANAGEMENT_BOT_OWNED} "
        f"avg=${float(holding.avg_price or 0):.4f} | actor={actor} | reason={reason}"
    )
    db.add(ActionLog(user_id=user_id, message=detail, level="WARNING"))
    db.delete(holding)
    logger.info(f"[WARNING] [User {user_id}] {detail}")
