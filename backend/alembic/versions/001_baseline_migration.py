"""baseline migration

Revision ID: 001_baseline
Revises: 
Create Date: 2026-05-26 21:12:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users 테이블 생성
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # 2. user_settings 테이블 생성
    op.create_table(
        'user_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('trade_mode', sa.String(), nullable=True),
        sa.Column('broker_provider', sa.String(), nullable=True),
        sa.Column('kis_app_key', sa.String(), nullable=True),
        sa.Column('kis_app_secret', sa.String(), nullable=True),
        sa.Column('kis_account_no', sa.String(), nullable=True),
        sa.Column('telegram_chat_id', sa.String(), nullable=True),
        sa.Column('telegram_enabled', sa.Boolean(), nullable=True),
        sa.Column('is_running', sa.Boolean(), nullable=True),
        sa.Column('is_real_enabled', sa.Boolean(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_user_settings_id'), 'user_settings', ['id'], unique=False)

    # 3. trade_logs 테이블 생성
    op.create_table(
        'trade_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('ticker_name', sa.String(), nullable=True),
        sa.Column('trade_type', sa.String(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('order_no', sa.String(), nullable=True),
        sa.Column('regime_mode', sa.String(), nullable=True),
        sa.Column('signal_score', sa.Integer(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trade_logs_id'), 'trade_logs', ['id'], unique=False)
    op.create_index(op.f('ix_trade_logs_ticker'), 'trade_logs', ['ticker'], unique=False)

    # 4. holdings 테이블 생성
    op.create_table(
        'holdings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('ticker_name', sa.String(), nullable=True),
        sa.Column('avg_price', sa.Float(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('highest_price', sa.Float(), nullable=True),
        sa.Column('regime_mode', sa.String(), nullable=True),
        sa.Column('buy_stage', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'ticker', name='_user_ticker_uc')
    )
    op.create_index(op.f('ix_holdings_id'), 'holdings', ['id'], unique=False)
    op.create_index(op.f('ix_holdings_ticker'), 'holdings', ['ticker'], unique=False)

    # 5. action_logs 테이블 생성
    op.create_table(
        'action_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(), nullable=True),
        sa.Column('message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_action_logs_id'), 'action_logs', ['id'], unique=False)

    # 6. watch_lists 테이블 생성
    op.create_table(
        'watch_lists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('ticker_name', sa.String(), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'ticker', name='_user_watchlist_uc')
    )
    op.create_index(op.f('ix_watch_lists_id'), 'watch_lists', ['id'], unique=False)
    op.create_index(op.f('ix_watch_lists_ticker'), 'watch_lists', ['ticker'], unique=False)

    # 7. stock_translations 테이블 생성
    op.create_table(
        'stock_translations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('name_ko', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_translations_id'), 'stock_translations', ['id'], unique=False)
    op.create_index(op.f('ix_stock_translations_ticker'), 'stock_translations', ['ticker'], unique=True)


def downgrade() -> None:
    op.drop_table('stock_translations')
    op.drop_table('watch_lists')
    op.drop_table('action_logs')
    op.drop_table('holdings')
    op.drop_table('trade_logs')
    op.drop_table('user_settings')
    op.drop_table('users')
