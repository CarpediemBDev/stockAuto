from typing import Any, Callable
import json
from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

def success_response(data: Any = None, message: str = "요청이 성공적으로 처리되었습니다."):
    return {
        "code": "SUCCESS",
        "message": message,
        "data": data
    }

class SuccessResponseRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response: Response = await original_route_handler(request)
            
            # 2xx 응답이면서 JSONResponse인 경우에만 포장 처리
            if isinstance(response, JSONResponse) and 200 <= response.status_code < 300:
                body = json.loads(response.body)
                
                # 이미 규격대로 포장된 객체라면 패스
                if isinstance(body, dict) and body.get("code") == "SUCCESS":
                    return response
                
                new_body = {
                    "code": "SUCCESS",
                    "message": "요청이 성공적으로 처리되었습니다.",
                    "data": body
                }
                
                return JSONResponse(
                    content=new_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                    background=response.background
                )
            
            return response
            
        return custom_route_handler
