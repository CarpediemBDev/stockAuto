"""add holdings.guard_streak_started_at (방어 조치 게이트의 벽시계 기준)

조치 게이트가 사이클 수만 요구하면 시간적으로 불안정하다. 스케줄러는 1분 간격으로
등록돼 있지만 사이클이 1분 안에 끝나지 않으면 겹치는 실행이 건너뛰어진다. 실측하니
중앙값 124초에 편차가 104~846초였다(2026-09-06 admin action_logs 40표본).

그래서 "10사이클 연속"이 20분일 수도 두 시간일 수도 있다. 되돌릴 수 없는 매도의
조건이 그렇게 흔들려서는 안 되고, 사용자 알림에 적는 지속 시간도 거짓이 된다.

이 컬럼은 연속 충족이 시작된 시각을 담아, 게이트가 사이클 수와 실제 경과 시간을
모두 요구하도록 만든다. 알림도 이 값으로 실제 경과 분을 계산한다.

Revision ID: e2a7d5c31f84
Revises: d1f4c82be607
Create Date: 2026-09-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2a7d5c31f84'
down_revision: Union[str, None] = 'd1f4c82be607'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('holdings', sa.Column('guard_streak_started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('holdings', 'guard_streak_started_at')
