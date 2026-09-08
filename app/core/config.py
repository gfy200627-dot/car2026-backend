"""应用配置：环境变量加载（不提交真实密码/密钥）"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库
    DATABASE_URL: str = "mysql+pymysql://root:change-me@127.0.0.1:3306/car2026?charset=utf8mb4"

    # 安全
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # CORS
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 应用
    APP_ENV: str = "development"
    API_PREFIX: str = "/api"

    # 数据时间轴（最近一个完整月；真实爬取数据覆盖 2025-01 ~ 2026-06）
    LATEST_YEAR: int = 2026
    LATEST_MONTH: int = 6

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def latest_month_str(self) -> str:
        return f"{self.LATEST_YEAR}-{self.LATEST_MONTH:02d}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
