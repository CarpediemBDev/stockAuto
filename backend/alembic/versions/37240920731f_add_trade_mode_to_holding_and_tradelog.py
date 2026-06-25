"""Add trade_mode to Holding and TradeLog

Revision ID: 37240920731f
Revises: d9f0a1234567
Create Date: 2026-06-23 02:09:43.281317

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37240920731f'
down_revision: Union[str, None] = 'd9f0a1234567'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('holdings', sa.Column('trade_mode', sa.String(), nullable=False, server_default='SIMULATED'))
    op.add_column('trade_logs', sa.Column('trade_mode', sa.String(), nullable=False, server_default='SIMULATED'))


def downgrade() -> None:
    op.drop_column('trade_logs', 'trade_mode')
    op.drop_column('holdings', 'trade_mode')
