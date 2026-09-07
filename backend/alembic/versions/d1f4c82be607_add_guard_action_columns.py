"""add holdings guard action columns (방어 자동 청산 + 섀도 모드)

4단계 방어 경보에 "무엇을 할지"를 붙인다. 기본값은 여전히 알림만이다.

이 단계를 만들면서 정정한 판단이 하나 있다. 당초에는 "경보가 실제 붕괴를 예측한다는
근거가 없으니 수 주간 실측한 뒤 착수"로 미뤄뒀는데, 그 실측을 사람이 로그를 보고 손으로
상관분석하라는 계획이었다. 그것은 코드가 할 일이다. SHADOW 모드를 이 단계 안에 넣으면
"팔았다면 이랬을 것"이 구조화된 로그로 쌓이고, 착수 근거가 이 기능 자체에서 나온다.

증거 부족은 기본값과 가드를 어떻게 잡을지의 근거이지 기능을 만들지 말라는 근거가 아니다.
그래서 가드를 다섯 겹으로 둔다 - 종목별 opt-in에 기본 ALERT_ONLY, 부분 청산 비율(기본
50%), 연속 충족 요구(수확의 2사이클보다 엄격한 10사이클), 일일 1회 캡, 활성화 시 고지.

guard_streak을 인메모리 캐시가 아니라 컬럼으로 두는 이유는, 되돌릴 수 없는 청산의
누적 조건이 재기동으로 리셋되면 안 되기 때문이다.

상세 설계는 docs/plans/holding_management_modes.md 5.4절.

Revision ID: d1f4c82be607
Revises: c9e3ab571d48
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1f4c82be607'
down_revision: Union[str, None] = 'c9e3ab571d48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'holdings',
        sa.Column('guard_action', sa.String(), nullable=False, server_default='ALERT_ONLY'),
    )
    op.add_column(
        'holdings',
        sa.Column('guard_sell_ratio', sa.Float(), nullable=False, server_default='0.5'),
    )
    op.add_column(
        'holdings',
        sa.Column('guard_streak', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('holdings', sa.Column('guard_last_action_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('holdings', 'guard_last_action_at')
    op.drop_column('holdings', 'guard_streak')
    op.drop_column('holdings', 'guard_sell_ratio')
    op.drop_column('holdings', 'guard_action')
