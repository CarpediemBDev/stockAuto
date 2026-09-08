"""add holdings.exit_breach_started_at (봇 소유 손절 노이즈 버퍼의 벽시계 기준)

방어 게이트·수확 버퍼에 이어 마지막으로 남아 있던 사이클 기반 대기다. 손절·트레일링·롤링박스
이탈을 두 번 확인한 뒤에 파는데, 그 "두 번"이 BREACH_COUNT_CACHE라는 인메모리 카운터로만
세어져 있었다.

문제는 두 가지다. 첫째, 사이클 주기가 등록값 1분이 아니라 실측 중앙값 124초(104~846초)라
같은 2사이클이 3분일 수도 28분일 수도 있다. 둘째, 카운터가 프로세스 메모리에만 있어서
재기동하면 진행 중이던 대기가 0으로 돌아간다. 코드를 고칠 때마다 서버를 내렸다 올리는데
그때마다 손절이 한 사이클씩 더 미뤄진다.

시각만 DB에 둔다. 관측 횟수는 인메모리 카운터로 계속 센다 - 재기동 후 한 번 더 관측해야
하는 비용은 있지만, 그것은 사이클 한 번이고 재기동 직후에는 어차피 워밍업 구간이다.
반면 시각을 잃으면 대기 자체가 처음부터 다시 시작되므로 손실이 훨씬 크다.

Revision ID: a5c9d71e3b48
Revises: f3b8e6a294c1
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5c9d71e3b48'
down_revision: Union[str, None] = 'f3b8e6a294c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('holdings', sa.Column('exit_breach_started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('holdings', 'exit_breach_started_at')
