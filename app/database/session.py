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
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}, database_url

    connect_args: dict = {}
    if database_url.startswith("mysql+pymysql://"):
        parts = urlsplit(database_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        ca_path = query.get("ssl_ca") or os.getenv("MYSQL_SSL_CA")
        verify_identity = query.get("ssl_verify_identity", "true").lower() == "true"
        verify_cert = query.get("ssl_verify_cert", "true").lower() == "true"

        if ca_path:
            ca_file = Path(ca_path).expanduser()
            if ca_file.exists():
                connect_args["ssl"] = {
                    "ca": str(ca_file),
                    "check_hostname": verify_identity,
                    "cert_reqs": ssl.CERT_REQUIRED if verify_cert and verify_identity else ssl.CERT_NONE,
                }
                query.pop("ssl_ca", None)
                query.pop("ssl_verify_cert", None)
                query.pop("ssl_verify_identity", None)
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
