"""drop obsolete broker order auto-resume flag

Revision ID: d9f0a1234567
Revises: c8e9f0123456
Create Date: 2026-06-21 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9f0a1234567"
down_revision: Union[str, None] = "c8e9f0123456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.drop_column("resume_after_resolution")


def downgrade() -> None:
    with op.batch_alter_table("broker_orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "resume_after_resolution",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
