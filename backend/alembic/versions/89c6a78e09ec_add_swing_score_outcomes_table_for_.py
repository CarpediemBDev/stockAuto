"""add swing_score_outcomes table for score calibration

Revision ID: 89c6a78e09ec
Revises: 78f9aaecb6fc
Create Date: 2026-07-22 00:39:28.407275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89c6a78e09ec'
down_revision: Union[str, None] = '78f9aaecb6fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 스윙 예측 점수와 익일 실제 등락을 짝지어 누적하는 캘리브레이션 관측 테이블.
    # 매매 경로와 무관한 순수 축적 원장이며 (예측일, 티커) 유니크로 잡 멱등성을 보장한다.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "swing_score_outcomes" in inspector.get_table_names():
        return

    op.create_table(
        "swing_score_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("predicted_date", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("score", sa.Numeric(precision=6, scale=2, asdecimal=True), nullable=False),
        sa.Column("baseline_close", sa.Numeric(precision=20, scale=4, asdecimal=True), nullable=False),
        sa.Column("observed_close", sa.Numeric(precision=20, scale=4, asdecimal=True), nullable=False),
        sa.Column("observed_date", sa.String(), nullable=False),
        sa.Column("return_pct", sa.Numeric(precision=20, scale=4, asdecimal=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("predicted_date", "ticker", name="uq_swing_outcome_date_ticker"),
    )
    op.create_index(op.f("ix_swing_score_outcomes_id"), "swing_score_outcomes", ["id"])
    op.create_index(op.f("ix_swing_score_outcomes_predicted_date"), "swing_score_outcomes", ["predicted_date"])
    op.create_index(op.f("ix_swing_score_outcomes_ticker"), "swing_score_outcomes", ["ticker"])
    op.create_index(op.f("ix_swing_score_outcomes_created_at"), "swing_score_outcomes", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "swing_score_outcomes" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_swing_score_outcomes_created_at"), table_name="swing_score_outcomes")
    op.drop_index(op.f("ix_swing_score_outcomes_ticker"), table_name="swing_score_outcomes")
    op.drop_index(op.f("ix_swing_score_outcomes_predicted_date"), table_name="swing_score_outcomes")
    op.drop_index(op.f("ix_swing_score_outcomes_id"), table_name="swing_score_outcomes")
    op.drop_table("swing_score_outcomes")
