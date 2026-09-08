"""Alembic 配置"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.database.session import Base
from app.models import (
    admin,
    brand,
    car,
    collection,
    prediction,
    review,
    sales,
)

# 指定 alembic 要追踪的 models（避免扫描所有模块）
target_metadata = Base.metadata

config = context.config
fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": settings.DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()