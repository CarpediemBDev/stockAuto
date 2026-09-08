"""add holdings.risk_basis_price (위임 포지션의 리스크 기준가)

위임(DELEGATED)은 사용자가 이미 들고 있던 포지션을 봇에 넘기는 모드다. 이때 손절선을
avg_price 기준으로 잡으면 봇이 넘겨받는 즉시 청산해 버린다. 반토막 난 종목을 맡겼는데
"손절 -8%"가 이미 -50%로 뚫려 있기 때문이다. 위임 버튼이 곧 매도 버튼이 되면 아무도
누르지 않는다.

그렇다고 위임 시 avg_price를 현재가로 덮어쓸 수는 없다. 그러면 손절은 정상화되지만
실현손익이 조작된다. 사용자가 12만원에 산 것을 6만원에 산 것으로 바꿔 기록하는 셈이다.

용도가 둘이므로 값을 둘로 나눈다. avg_price는 실현손익 계산의 원천으로 남기고,
risk_basis_price를 리스크 판정(손절선·트레일링 하한 가드)의 앵커로 새로 판다.
NULL이면 avg_price로 폴백하므로 기존 레코드는 동작이 바뀌지 않는다.

Revision ID: b6d1af02c395
Revises: a5c9d71e3b48
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6d1af02c395'
down_revision: Union[str, None] = 'a5c9d71e3b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'holdings',
        sa.Column('risk_basis_price', sa.Numeric(precision=20, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('holdings', 'risk_basis_price')
