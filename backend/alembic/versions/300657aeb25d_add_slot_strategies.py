"""add_slot_strategies

Revision ID: 300657aeb25d
Revises: c1f7a3d5e204
Create Date: 2026-07-18 05:18:41.995986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '300657aeb25d'
down_revision: Union[str, None] = 'c1f7a3d5e204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    STRATEGIES_TO_ADD = (
        ("multi_slot", "격리형 2슬롯 (EP 50% : RS 50%)", "Modular 2-Slot (EP 50% : RS 50%)"),
        ("multi_slot_3", "격리형 3슬롯 (EP 30% : ASQS 30% : RS 40%)", "Modular 3-Slot (EP 30% : ASQS 30% : RS 40%)"),
        ("three_slot", "격리형 3슬롯 (EP 30% : ASQS 30% : RS 40%)", "Modular 3-Slot (EP 30% : ASQS 30% : RS 40%)"),
    )
    
    strategy_table = sa.table(
        "strategies",
        sa.column("strategy_type", sa.String()),
        sa.column("name_ko", sa.String()),
        sa.column("name_en", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    connection = op.get_bind()
    
    existing_keys = set(
        connection.execute(
            sa.select(strategy_table.c.strategy_type)
            .where(strategy_table.c.strategy_type.in_([s[0] for s in STRATEGIES_TO_ADD]))
        ).scalars()
    )
    
    missing_rows = [
        {
            "strategy_type": strategy_type,
            "name_ko": name_ko,
            "name_en": name_en,
            "is_active": True,
        }
        for strategy_type, name_ko, name_en in STRATEGIES_TO_ADD
        if strategy_type not in existing_keys
    ]
    if missing_rows:
        op.bulk_insert(strategy_table, missing_rows)


def downgrade() -> None:
    pass
