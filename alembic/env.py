"""Alembic 配置"""

from logging.config import fileConfig

from alembic import context
from app.core.config import settings
from app.database.session import Base, engine
from app.models import (
    admin,
    brand,
    car,
    collection,
    prediction,
    review,
    sales,
)
from sqlalchemy import inspect, text

# 指定 alembic 要追踪的 models（避免扫描所有模块）
target_metadata = Base.metadata

config = context.config
fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

INITIAL_REVISION = "32100e704396"


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _adopt_existing_schema(connection) -> None:
    """兼容历史上由 create_all 创建、但没有 alembic_version 的线上数据库。"""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "algorithm_tasks" not in tables:
        return

    if "alembic_version" not in tables:
        connection.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        ))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": INITIAL_REVISION},
        )
        return

    has_version = connection.execute(text("SELECT 1 FROM alembic_version LIMIT 1")).first()
    if has_version is None:
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": INITIAL_REVISION},
        )


def run_migrations_online() -> None:
    # 直接复用应用数据库 engine，确保 Alembic 与 SQLAlchemy 使用完全一致的
    # Aiven/Render SSL 参数，避免 engine_from_config 绕过 session.py 的 SSL 配置。
    with engine.connect() as connection:
        _adopt_existing_schema(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
