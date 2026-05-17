from typing import Any

def success_response(data: Any = None, message: str = "요청이 성공적으로 처리되었습니다."):
    return {
        "code": "SUCCESS",
        "message": message,
        "data": data
    }
