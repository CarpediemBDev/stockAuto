from fastapi import Request
from fastapi.responses import JSONResponse

class StockAutoException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code

class RateLimitExceededException(StockAutoException):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(code="RATE_LIMIT_EXCEEDED", message=message, status_code=429)

async def stock_auto_exception_handler(request: Request, exc: StockAutoException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message
            }
        }
    )
