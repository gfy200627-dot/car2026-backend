"""数据库连接与会话"""

import os
import ssl
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _database_connect_args(database_url: str):
    """Build DBAPI connection args and normalize Render/Aiven CA settings."""
    database_url = database_url.strip()

    # 防止线上环境把 mysql:// 解析为 SQLAlchemy 的默认 MySQLdb 驱动。
    # 本项目明确使用 PyMySQL，所有 MySQL 连接统一走 mysql+pymysql://。
    if database_url.startswith("mysql://"):
        database_url = "mysql+pymysql://" + database_url[len("mysql://"):]

    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}, database_url

    connect_args: dict = {}
    if database_url.startswith("mysql+pymysql://"):
        parts = urlsplit(database_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))

        # PyMySQL 不接受名为 ssl-mode 的 DBAPI 参数。
        # MySQL URL 中常见的 ssl-mode=REQUIRED 需要转换为 PyMySQL 的 ssl 参数。
        ssl_mode = query.pop("ssl-mode", "").upper()
        ca_path = query.get("ssl_ca") or os.getenv("MYSQL_SSL_CA")
        verify_identity = query.get("ssl_verify_identity", "true").lower() == "true"
        verify_cert = query.get("ssl_verify_cert", "true").lower() == "true"

        if ca_path:
            ca_file = Path(ca_path).expanduser()
            if ca_file.exists():
                connect_args["ssl"] = {
                    "ca": str(ca_file),
                    "check_hostname": verify_identity,
                    "cert_reqs": ssl.CERT_REQUIRED if verify_cert else ssl.CERT_NONE,
                }
                query.pop("ssl_ca", None)
                query.pop("ssl_verify_cert", None)
                query.pop("ssl_verify_identity", None)
        elif ssl_mode in {"REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"}:
            # 没有单独 CA 文件时，至少保持 REQUIRED 的加密连接语义。
            # 若以后配置 CA，可通过 ssl_ca 或 MYSQL_SSL_CA 自动启用证书校验。
            connect_args["ssl"] = {
                "cert_reqs": ssl.CERT_NONE,
                "check_hostname": False,
            }

        clean_query = urlencode(query)
        database_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, clean_query, parts.fragment)
        )

    return connect_args, database_url


connect_args, engine_url = _database_connect_args(settings.DATABASE_URL)

engine = create_engine(
    engine_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
