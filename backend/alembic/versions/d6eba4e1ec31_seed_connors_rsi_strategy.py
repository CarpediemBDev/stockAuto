"""seed_connors_rsi_strategy

Revision ID: d6eba4e1ec31
Revises: 7a1b2c3d4e5f
Create Date: 2026-07-09 22:50:24.873769

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6eba4e1ec31'
down_revision: Union[str, None] = '7a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO strategies (strategy_type, name_ko, name_en, is_active) "
        "VALUES ('connors_rsi', '래리코너스 ConnorsRSI', 'ConnorsRSI', 1)"
    )



def downgrade() -> None:
    op.execute(
        "DELETE FROM strategies WHERE strategy_type = 'connors_rsi'"
    )

