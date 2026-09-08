"""统一响应外壳与业务异常

前端 request.ts 拦截器约定：
- 成功：HTTP 200 + { code: 0, message: '', data, timestamp }
- 业务错误：HTTP 200 + { code: !=0, message }（与 Mock MockError 行为一致）
- 未认证：HTTP 401（前端自动登出）
"""

from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class BizError(Exception):
    """业务异常：等价于前端 Mock 的 MockError(code, message)"""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def envelope(data: Any = None, message: str = "") -> dict:
    import time
    return {"code": 0, "message": message, "data": data, "timestamp": int(time.time() * 1000)}


def error_envelope(code: int, message: str) -> dict:
    import time
    return {"code": code, "message": message, "data": None, "timestamp": int(time.time() * 1000)}


async def biz_error_handler(_request: Request, exc: BizError) -> JSONResponse:
    """业务错误：HTTP 200 + code（前端按 envelope 处理）"""
    return JSONResponse(status_code=200, content=error_envelope(exc.code, exc.message))


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """HTTP 异常：401 保持 401（触发前端登出），其余转 envelope"""
    if exc.status_code == 401:
        return JSONResponse(status_code=401, content=error_envelope(401, str(exc.detail)))
    # 404/403 等前端拦截器按 HTTP 状态码处理，同时给出 envelope 便于排查
    return JSONResponse(status_code=exc.status_code, content=error_envelope(exc.status_code, str(exc.detail)))


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """参数校验错误：HTTP 200 + code 422（对齐 Mock 的宽松行为）"""
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    msg = f"参数错误：{loc} {first.get('msg', 'invalid')}"
    return JSONResponse(status_code=200, content=error_envelope(422, msg))


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """兜底异常：HTTP 200 + code 500（避免前端拿到裸 500 HTML）"""
    return JSONResponse(status_code=200, content=error_envelope(500, f"服务内部错误：{exc}"))
