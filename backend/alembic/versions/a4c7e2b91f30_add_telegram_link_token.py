"""Add telegram link token to UserSettings

사용자명 기반 텔레그램 연동(소유권 증명 부재)을 대체하는 1회용·만료형 링크 토큰 컬럼.
원본이 아닌 SHA-256 지문만 저장하며, 소비 또는 만료 시 NULL로 비운다.

Revision ID: a4c7e2b91f30
Revises: 7c1e4b93af58
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c7e2b91f30'
down_revision: Union[str, None] = '7c1e4b93af58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 기존 연동(telegram_chat_id)은 그대로 유지된다. 신규/재연동에만 토큰이 요구된다.
    op.add_column('user_settings', sa.Column('telegram_link_token_hash', sa.String(), nullable=True))
    op.add_column('user_settings', sa.Column('telegram_link_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        'ix_user_settings_telegram_link_token_hash',
        'user_settings',
        ['telegram_link_token_hash'],
    )


def downgrade() -> None:
    op.drop_index('ix_user_settings_telegram_link_token_hash', table_name='user_settings')
    op.drop_column('user_settings', 'telegram_link_token_expires_at')
    op.drop_column('user_settings', 'telegram_link_token_hash')
