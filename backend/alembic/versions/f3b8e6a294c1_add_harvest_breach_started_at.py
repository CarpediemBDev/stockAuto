"""add holdings.harvest_breach_started_at (수확 노이즈 버퍼의 벽시계 기준)

방어 조치 게이트와 같은 결함이 수확 노이즈 버퍼에도 있었다. 버퍼가 "2사이클 연속"이라
사이클 주기가 흔들리면 실제 대기 시간이 함께 흔들린다(실측 104~846초). 게다가 카운터가
인메모리 캐시라 재기동이 진행 중이던 대기를 지워버린다.

수확은 방어와 역할이 다르므로 시간 하한을 짧게 잡는다. 방어는 추세 붕괴가 실재하는지
확인하는 것이고, 수확은 순간적으로 찔렀다 돌아오는 꼬리만 걸러내면 된다. 오래 기다릴수록
급등분을 반납하므로 대기를 늘리는 것 자체가 비용이다.

관측 횟수는 여전히 인메모리 카운터로 센다. 재기동하면 두 번을 다시 관측해야 하는데 그것은
무해하다. 반면 시각은 DB에 둔다 - 재기동이 대기를 0으로 되돌리면 급등이 꺾인 뒤에도 매도가
계속 미뤄진다.

Revision ID: f3b8e6a294c1
Revises: e2a7d5c31f84
Create Date: 2026-09-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3b8e6a294c1'
down_revision: Union[str, None] = 'e2a7d5c31f84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('holdings', sa.Column('harvest_breach_started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('holdings', 'harvest_breach_started_at')
