"""add role to users

Revision ID: 74c5ea7a03b5
Revises: c4f5a6b7c8d9
Create Date: 2026-06-06 16:23:09.266786

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74c5ea7a03b5'
down_revision: Union[str, None] = 'c4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('role', sa.String(), nullable=False, server_default='USER'),
    )
    op.execute("UPDATE users SET role = 'ADMIN' WHERE username = 'admin'")


def downgrade() -> None:
    op.drop_column('users', 'role')
