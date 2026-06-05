"""add_kis_credential_verification_status

Revision ID: c4f5a6b7c8d9
Revises: b7c8d9e0f1a2
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f5a6b7c8d9"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "kis_verification_status",
                sa.String(),
                nullable=False,
                server_default="unverified",
            )
        )
        batch_op.add_column(sa.Column("kis_verified_trade_mode", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("kis_verified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("kis_verified_at")
        batch_op.drop_column("kis_verified_trade_mode")
        batch_op.drop_column("kis_verification_status")
