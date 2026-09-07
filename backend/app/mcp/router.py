from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.core.dependencies import get_current_user
from app.core.exceptions import StockAutoException
from app.core.models import User
from app.core.redis_client import get_redis_client
from app.core.response import SuccessResponseRoute

router = APIRouter(route_class=SuccessResponseRoute)

# 허용된 명령 화이트리스트. 목록 밖 command_type은 거부한다.
ALLOWED_COMMANDS = {"BUY", "SELL", "CHANGE_STRATEGY"}
# 실거래 자금을 움직이는 비가역 명령. 실행 워커를 붙일 때 confirm 게이트를 반드시 함께 복원한다.
DESTRUCTIVE_COMMANDS = {"BUY", "SELL"}

# 과거 구현이 명령을 적재하던 키. 현재는 읽기만 하며 새로 쓰지 않는다.
QUEUE_KEY_PREFIX = "mcp_command_queue"


class ChatCommandRequest(BaseModel):
    command_type: str  # ALLOWED_COMMANDS 중 하나
    ticker: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    reason: Optional[str] = None
    # 실행 워커가 생기면 파괴적 명령의 확인 게이트에 다시 쓰인다.
    confirm: bool = False


@router.post("/command")
async def execute_mcp_command(
    request: ChatCommandRequest,
    current_user: User = Depends(get_current_user),
):
    """
    MCP(AI 챗봇) 명령 접수 엔드포인트. **현재 명령을 실행하지 않는다.**

    과거 구현은 명령을 Redis List에 RPUSH하고 "워커가 순차적으로 처리합니다"라고
    응답했으나, 그 워커는 저장소에 존재한 적이 없다(LPOP·BRPOP·RPOPLPUSH 0건).
    사용자에게 실행을 약속하면서 실제로는 아무 일도 일어나지 않는 상태였고, 큐 키에
    TTL도 없어 적재분이 영구히 남았다. 나중에 워커를 붙이는 순간 오래된 BUY 명령이
    한꺼번에 체결될 수 있는 잠복 위험이었다.

    그래서 적재를 중단하고 501을 반환한다. 큐에 쌓아두고 조용히 방치하느니 접수
    자체를 거절하는 편이 안전하고 정직하다.

    실행 워커를 구현할 때 함께 복원해야 하는 것:
    - user_id는 요청 본문이 아니라 인증 세션에서만 도출한다(크로스유저 주문 주입 차단).
    - 파괴적 명령(BUY/SELL)은 confirm=True 없이 적재하지 않고 dry-run 프리뷰만 준다.
    - 자동 스캐너 봇과의 경합을 막기 위해 주문 락(app/core/locks.py)을 경유한다.
    """
    command_type = request.command_type.strip().upper()
    if command_type not in ALLOWED_COMMANDS:
        raise StockAutoException(
            code="MCP_COMMAND_NOT_ALLOWED",
            message=(
                f"허용되지 않은 command_type입니다: {request.command_type}. "
                f"허용: {sorted(ALLOWED_COMMANDS)}"
            ),
            status_code=400,
        )

    raise StockAutoException(
        code="MCP_EXECUTION_NOT_IMPLEMENTED",
        message=(
            "MCP 명령 실행 파이프라인이 아직 구현되지 않았습니다. "
            "명령은 접수되지 않으며 큐에도 적재되지 않습니다."
        ),
        status_code=501,
    )


@router.get("/status")
async def get_mcp_status(current_user: User = Depends(get_current_user)):
    """본인의 레거시 명령 큐 잔여분만 조회한다. (타인 큐 조회 차단)

    실행 워커가 없으므로 pending_commands는 과거 구현이 남긴 잔여분을 뜻하며,
    새 명령으로 늘어나지 않는다.
    """
    redis_cli = get_redis_client()
    queue_key = f"{QUEUE_KEY_PREFIX}:{current_user.id}"
    return {
        "user_id": current_user.id,
        "pending_commands": redis_cli.llen(queue_key),
        "worker_implemented": False,
    }
