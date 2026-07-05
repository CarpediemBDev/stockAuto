from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.dependencies import get_current_user
from app.core.models import User
from app.core.redis_client import get_redis_client
import json

router = APIRouter()

# 허용된 명령 화이트리스트. 목록 밖 command_type은 거부한다.
ALLOWED_COMMANDS = {"BUY", "SELL", "CHANGE_STRATEGY"}
# 실거래 자금을 움직이는 비가역 명령. 명시적 confirm 없이는 큐에 적재하지 않는다.
DESTRUCTIVE_COMMANDS = {"BUY", "SELL"}

class ChatCommandRequest(BaseModel):
    command_type: str  # ALLOWED_COMMANDS 중 하나
    ticker: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    reason: Optional[str] = None
    # 파괴적 명령(BUY/SELL)은 confirm=True가 명시돼야만 실제 큐에 적재된다.
    confirm: bool = False

@router.post("/command")
async def execute_mcp_command(
    request: ChatCommandRequest,
    current_user: User = Depends(get_current_user),
):
    """
    [Command Sourcing]
    MCP (AI 챗봇)에서 전달된 사용자 명령을 직접 실행하지 않고 명령 큐에 적재합니다.
    - user_id는 요청 본문이 아니라 '인증 세션'에서만 도출하여 크로스유저 주문 주입을 차단합니다.
    - 파괴적 명령(BUY/SELL)은 confirm=True 없이는 적재를 거부하고 dry-run 프리뷰만 반환하여,
      자연어 오해석에 의한 비가역 청산을 방지합니다.
    자동 스캐너 봇과의 Race Condition을 방지하기 위해 단일 스레드 워커가 순차적으로 처리합니다.
    """
    command_type = request.command_type.strip().upper()
    if command_type not in ALLOWED_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않은 command_type입니다: {request.command_type}. 허용: {sorted(ALLOWED_COMMANDS)}",
        )

    command_data = {
        "user_id": current_user.id,
        "command_type": command_type,
        "ticker": request.ticker,
        "quantity": request.quantity,
        "price": request.price,
        "reason": request.reason,
        "status": "PENDING",
    }

    # 확인 게이트: 파괴적 명령은 confirm=True가 없으면 큐에 넣지 않고 프리뷰만 돌려준다.
    if command_type in DESTRUCTIVE_COMMANDS and not request.confirm:
        return {
            "status": "PREVIEW",
            "message": (
                "파괴적 명령(실거래)입니다. 아래 내용을 확인한 뒤 confirm=true로 다시 요청하세요. "
                "확인 전에는 실행 큐에 적재되지 않습니다."
            ),
            "preview": command_data,
            "requires_confirmation": True,
        }

    # Redis List를 명령 큐(Command Queue)로 활용 (RPUSH). 인증된 본인 큐에만 적재된다.
    redis_cli = get_redis_client()
    queue_key = f"mcp_command_queue:{current_user.id}"
    redis_cli.rpush(queue_key, json.dumps(command_data))

    return {
        "status": "QUEUED",
        "message": "명령이 안전하게 큐에 적재되었습니다. 워커가 순차적으로 처리합니다.",
        "queue_length": redis_cli.llen(queue_key),
    }

@router.get("/status")
async def get_mcp_status(current_user: User = Depends(get_current_user)):
    """현재 인증된 '본인'의 챗봇 명령 큐 상태만 확인합니다. (타인 큐 조회 차단)"""
    redis_cli = get_redis_client()
    queue_key = f"mcp_command_queue:{current_user.id}"
    length = redis_cli.llen(queue_key)
    return {
        "user_id": current_user.id,
        "pending_commands": length,
    }
