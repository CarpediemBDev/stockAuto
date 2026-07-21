"""add rolling_stop_price column to holdings

Revision ID: 78f9aaecb6fc
Revises: 57fac21b1d0f
Create Date: 2026-07-20 21:58:33.932163

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78f9aaecb6fc'
down_revision: Union[str, None] = '57fac21b1d0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 롤링 박스 스탑 래칫 가격 (단조 증가, opt-in 전략 한정). 기존 행은 NULL = 미시드 상태.
    # 세션 충돌 복구 이력으로 일부 DB(stockauto.db)에는 선행 적용본(구 238568cb20f4)이 이미
    # 컬럼을 만들어 둔 상태라, 중복 add_column 실패를 막기 위해 존재 여부를 검사한다.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("holdings")}
    if "rolling_stop_price" not in columns:
        op.add_column(
            "holdings",
            sa.Column("rolling_stop_price", sa.Numeric(precision=20, scale=4, asdecimal=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("holdings")}
    if "rolling_stop_price" in columns:
        op.drop_column("holdings", "rolling_stop_price")
