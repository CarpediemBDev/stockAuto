"""add autonomous_slot_states + seed canary_allocation strategy

목표비중형 자율 슬롯(canary_allocation)의 월별 판단·집행 상태 테이블을 만들고,
전략 1:1 규칙에 따라 strategies 테이블에 전략 행 1개를 시딩한다.
설계: docs/plans/canary_allocation_live_port.md

Revision ID: f3a9c2e7d418
Revises: d4e1c8b7f206
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c2e7d418'
down_revision: Union[str, None] = 'd4e1c8b7f206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STRATEGY = "canary_allocation"


def upgrade() -> None:
    op.create_table(
        "autonomous_slot_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_key", sa.String(), nullable=False),
        sa.Column("decision_date", sa.String(), nullable=False),
        sa.Column("target_json", sa.Text(), nullable=False),
        sa.Column("signals_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "slot_key", "decision_date", name="uq_autonomous_slot_decision"),
    )
    op.create_index("ix_autonomous_slot_states_id", "autonomous_slot_states", ["id"])
    op.create_index("ix_autonomous_slot_states_user_id", "autonomous_slot_states", ["user_id"])
    op.execute(
        sa.text(
            "INSERT INTO strategies (strategy_type, name_ko, name_en, description, is_active, is_selectable, tier, regime, sort_order) "
            "SELECT :st, :ko, :en, :desc, 1, 1, 'single', 'ALL', 0 "
            "WHERE NOT EXISTS (SELECT 1 FROM strategies WHERE strategy_type = :st)"
        ).bindparams(
            st=_STRATEGY,
            ko="크로스에셋 카나리아 배분 (QQQ × 경보 7종)",
            en="Cross-Asset Canary Allocation (QQQ x 7 warnings)",
            desc="신흥국·채권·반도체·주택·금융·금융여건·반도체지수 7개 조기경보의 양호 비율만큼 QQQ 보유, 나머지 IEF/BIL. 월 1회 판단(1x).",
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM strategies WHERE strategy_type = :st").bindparams(st=_STRATEGY))
    op.drop_index("ix_autonomous_slot_states_user_id", table_name="autonomous_slot_states")
    op.drop_index("ix_autonomous_slot_states_id", table_name="autonomous_slot_states")
    op.drop_table("autonomous_slot_states")
