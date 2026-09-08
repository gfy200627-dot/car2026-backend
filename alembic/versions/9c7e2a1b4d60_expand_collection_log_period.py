"""expand collection log data_period length

Revision ID: 9c7e2a1b4d60
Revises: 6f4c1b2a9d10
"""

from alembic import op
import sqlalchemy as sa


revision = "9c7e2a1b4d60"
down_revision = "6f4c1b2a9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "collection_logs",
        "data_period",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_comment="数据周期（如 2026-08）",
    )


def downgrade() -> None:
    op.alter_column(
        "collection_logs",
        "data_period",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_comment="数据周期（如 2026-08 或 2025-01 ~ 2026-06）",
    )
