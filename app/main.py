"""FastAPI 主入口：中间件、路由、异常处理"""

import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.envelope import (
    BizError,
    biz_error_handler,
    envelope,
    error_envelope,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    print(f"🚀 AutoInsight 后端启动: env={settings.APP_ENV}, db={settings.DATABASE_URL[:20]}...")
    yield
    print("👋 AutoInsight 后端关闭")


app = FastAPI(
    title="AutoInsight 后端",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS：前端 localhost:5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 异常处理器
app.add_exception_handler(BizError, biz_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.middleware("http")
async def envelope_middleware(request: Request, call_next):
    """成功响应统一包裹 {code, message, data, timestamp}（与前端 Mock 契约一致）。

    仅处理 /api 下 200 的 JSON 响应；已带 code 的响应（异常处理器产出）原样透传，
    非成功状态码（401/403/404 等）保持原状态码，envelope 由异常处理器负责。
    """
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        return response
    if response.status_code != 200:
        return response
    if "application/json" not in response.headers.get("content-type", ""):
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return Response(content=body, status_code=response.status_code, media_type="application/json")
    if isinstance(payload, dict) and "code" in payload:
        # 已是 envelope（异常处理器/健康检查等），避免双重包裹
        return Response(content=body, status_code=response.status_code, media_type="application/json")

    wrapped = json.dumps(envelope(data=payload), ensure_ascii=False).encode("utf-8")
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(content=wrapped, status_code=200, headers=headers, media_type="application/json")


@app.get("/")
def root() -> dict:
    return envelope(message="AutoInsight 后端运行中")


@app.get("/health")
def health() -> dict:
    return envelope(data={"status": "ok"})


# 注册路由
from app.api import auth, dashboard, cars, market, sales, recommendations, predictions, sentiment, admin

app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(cars.router, prefix="/api", tags=["车型"])
app.include_router(market.router, prefix="/api", tags=["市场分析"])
app.include_router(sales.router, prefix="/api", tags=["销量"])
app.include_router(recommendations.router, prefix="/api", tags=["智能推荐"])
app.include_router(predictions.router, prefix="/api", tags=["销量预测"])
app.include_router(sentiment.router, prefix="/api", tags=["舆情分析"])
app.include_router(admin.router, prefix="/api", tags=["管理后台"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)