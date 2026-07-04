"""decimal_migration_and_unfilled_orders

Revision ID: 4f294cc0a849
Revises: d5e98c93f4d5
Create Date: 2026-06-30 22:34:13.772403

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f294cc0a849'
down_revision: Union[str, None] = 'd5e98c93f4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create unfilled_orders table
    op.create_table(
        'unfilled_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('ticker_name', sa.String(), nullable=True),
        sa.Column('trade_type', sa.String(), nullable=False),
        sa.Column('price', sa.Numeric(precision=20, scale=4, asdecimal=True), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('strategy_type', sa.String(), nullable=False),
        sa.Column('buy_stage', sa.Integer(), nullable=True),
        sa.Column('regime_mode', sa.String(), nullable=True),
        sa.Column('signal_score', sa.Integer(), nullable=True),
        sa.Column('order_no', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_unfilled_orders_id'), 'unfilled_orders', ['id'], unique=False)
    op.create_index(op.f('ix_unfilled_orders_user_id'), 'unfilled_orders', ['user_id'], unique=False)
    op.create_index(op.f('ix_unfilled_orders_ticker'), 'unfilled_orders', ['ticker'], unique=False)
    op.create_index(op.f('ix_unfilled_orders_order_no'), 'unfilled_orders', ['order_no'], unique=True)

    # 2. Alter column types to Numeric in batch mode for SQLite
    with op.batch_alter_table('trade_logs', schema=None) as batch_op:
        batch_op.alter_column('price',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('realized_pnl',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('return_rate',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)

    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.alter_column('avg_price',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('highest_price',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)

    with op.batch_alter_table('broker_orders', schema=None) as batch_op:
        batch_op.alter_column('submitted_price',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=False)
        batch_op.alter_column('filled_price',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)

    with op.batch_alter_table('account_equity_snapshots', schema=None) as batch_op:
        batch_op.alter_column('total_asset',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=False)
        batch_op.alter_column('cash_balance',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('stock_balance',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('profit_rate',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('fx_rate',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)

    with op.batch_alter_table('market_overview_snapshots', schema=None) as batch_op:
        batch_op.alter_column('nasdaq_current',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('nasdaq_change',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('nasdaq_change_pct',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('exchange_rate_current',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('exchange_rate_change',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)
        batch_op.alter_column('exchange_rate_change_pct',
               existing_type=sa.Float(),
               type_=sa.Numeric(precision=20, scale=4, asdecimal=True),
               existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('market_overview_snapshots', schema=None) as batch_op:
        batch_op.alter_column('exchange_rate_change_pct',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('exchange_rate_change',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('exchange_rate_current',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('nasdaq_change_pct',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('nasdaq_change',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('nasdaq_current',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)

    with op.batch_alter_table('account_equity_snapshots', schema=None) as batch_op:
        batch_op.alter_column('fx_rate',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('profit_rate',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('stock_balance',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('cash_balance',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('total_asset',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=False)

    with op.batch_alter_table('broker_orders', schema=None) as batch_op:
        batch_op.alter_column('filled_price',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('submitted_price',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=False)

    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.alter_column('highest_price',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('avg_price',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)

    with op.batch_alter_table('trade_logs', schema=None) as batch_op:
        batch_op.alter_column('return_rate',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('realized_pnl',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)
        batch_op.alter_column('price',
               existing_type=sa.Numeric(precision=20, scale=4, asdecimal=True),
               type_=sa.Float(),
               existing_nullable=True)

    op.drop_table('unfilled_orders')
