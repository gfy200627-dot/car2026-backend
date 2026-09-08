"""allow operation log user_id to be nullable for SET NULL foreign key

Revision ID: 6f4c1b2a9d10
Revises: 32100e704396
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f4c1b2a9d10"
down_revision: Union[str, None] = "32100e704396"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "operation_logs",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "operation_logs",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
