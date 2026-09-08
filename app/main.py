"""FastAPI 主入口：中间件、路由、异常处理"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
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