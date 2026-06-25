"""remove_broker_provider_and_trade_mode

Revision ID: d5e98c93f4d5
Revises: 6c7d8e9f0a1b
Create Date: 2026-06-25 22:38:39.095082

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e98c93f4d5'
down_revision: Union[str, None] = '6c7d8e9f0a1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('broker_orders', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('_user_provider_broker_order_uc'), type_='unique')
        batch_op.create_unique_constraint('_user_broker_order_uc', ['user_id', 'broker_order_no'])
        batch_op.drop_column('broker_provider')

    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('_user_ticker_strategy_mode_uc'), type_='unique')
        batch_op.create_unique_constraint('_user_ticker_strategy_uc', ['user_id', 'ticker', 'strategy_type'])
        batch_op.drop_column('trade_mode')
        batch_op.drop_column('broker_provider')

    with op.batch_alter_table('trade_logs', schema=None) as batch_op:
        batch_op.drop_column('trade_mode')


def downgrade() -> None:
    with op.batch_alter_table('trade_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trade_mode', sa.VARCHAR(), server_default=sa.text("'SIMULATED'"), nullable=False))

    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('broker_provider', sa.VARCHAR(), nullable=True))
        batch_op.add_column(sa.Column('trade_mode', sa.VARCHAR(), server_default=sa.text("'SIMULATED'"), nullable=False))
        batch_op.drop_constraint('_user_ticker_strategy_uc', type_='unique')
        batch_op.create_unique_constraint(op.f('_user_ticker_strategy_mode_uc'), ['user_id', 'ticker', 'strategy_type', 'trade_mode'])

    with op.batch_alter_table('broker_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('broker_provider', sa.VARCHAR(), nullable=True))
        batch_op.drop_constraint('_user_broker_order_uc', type_='unique')
        batch_op.create_unique_constraint(op.f('_user_provider_broker_order_uc'), ['user_id', 'broker_provider', 'broker_order_no'])
