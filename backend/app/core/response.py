import json
from typing import Any, Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse


SUCCESS_CODE = "SUCCESS"
DEFAULT_SUCCESS_MESSAGE = "요청이 성공적으로 처리되었습니다."
WRAPPER_HEADER_EXCLUSIONS = {
    b"content-length",
    b"content-type",
    b"content-encoding",
    b"transfer-encoding",
}


def success_response(data: Any = None, message: str = DEFAULT_SUCCESS_MESSAGE):
    return {
        "code": SUCCESS_CODE,
        "message": message,
        "data": data,
    }


def _is_json_response(response: Response) -> bool:
    media_type = (response.media_type or "").split(";", 1)[0].lower()
    if media_type == "application/json":
        return True

    content_type = response.headers.get("content-type", "")
    return content_type.split(";", 1)[0].lower() == "application/json"


def _build_success_body(body: Any) -> dict[str, Any] | None:
    if isinstance(body, dict) and body.get("code") == SUCCESS_CODE:
        return None

    message = DEFAULT_SUCCESS_MESSAGE
    data = body

    if isinstance(body, dict):
        body_keys = set(body)
        if body_keys <= {"message"} and isinstance(body.get("message"), str):
            message = body["message"]
            data = None
        elif body_keys <= {"message", "data"} and isinstance(body.get("message"), str):
            message = body["message"]
            data = body.get("data")

    return {
        "code": SUCCESS_CODE,
        "message": message,
        "data": data,
    }


def _copy_safe_headers(source: Response, target: JSONResponse) -> None:
    preserved_headers = [
        (key, value)
        for key, value in source.raw_headers
        if key.lower() not in WRAPPER_HEADER_EXCLUSIONS
    ]
    generated_headers = [
        (key, value)
        for key, value in target.raw_headers
        if key.lower() in {b"content-length", b"content-type"}
    ]
    target.raw_headers = generated_headers + preserved_headers


class SuccessResponseRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response: Response = await original_route_handler(request)

            if (
                200 <= response.status_code < 300
                and response.status_code not in {204, 304}
                and _is_json_response(response)
            ):
                body_bytes = getattr(response, "body", b"")
                if not body_bytes:
                    return response

                body = json.loads(body_bytes)
                new_body = _build_success_body(body)
                if new_body is None:
                    return response

                wrapped_response = JSONResponse(
                    content=new_body,
                    status_code=response.status_code,
                    media_type=response.media_type,
                    background=response.background,
                )
                _copy_safe_headers(response, wrapped_response)
                return wrapped_response

            return response

        return custom_route_handler
