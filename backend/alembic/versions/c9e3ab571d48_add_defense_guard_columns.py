"""add holdings defense guard columns (방어 경보)

봇 관할 밖(EXTERNAL) 보유분에 "무너지면 알림" 옵션을 붙이기 위한 컬럼이다.
이 단계는 경보만 보내고 주문을 내지 않는다.

핵심은 절대 점수선을 쓰지 않는다는 것이다. -50% 물린 종목은 십중팔구 이미 시그널 점수가
붕괴선 아래이므로, 절대선으로 판정하면 방어를 켜는 순간 즉시 경보가 되어 이 프로젝트가
처음에 문제 삼았던 "관측 시작 즉시 청산"이 이름만 바꿔 재현된다. 상태(state)가 아니라
전이(transition)를 봐야 한다 - 켠 시점의 점수와 저가를 기준선으로 박고, 거기서 추가로
악화될 때만 울린다.

guard_enabled_at은 켠 직후 오발동을 막는 유예기간의 기준이고, guard_last_alert_at은
1분 사이클마다 같은 경보가 반복되지 않도록 하는 쿨다운의 기준이다. 둘 다 인메모리 캐시가
아니라 컬럼으로 두는 이유는 재기동 후에도 유예·쿨다운이 유지되어야 하기 때문이다.

상세 설계는 docs/plans/holding_management_modes.md 5.3절.

Revision ID: c9e3ab571d48
Revises: b8d2fa46c931
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e3ab571d48'
down_revision: Union[str, None] = 'b8d2fa46c931'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'holdings',
        sa.Column('guard_enabled', sa.Boolean(), nullable=False, server_default='0'),
    )
    op.add_column('holdings', sa.Column('guard_baseline_score', sa.Float(), nullable=True))
    op.add_column(
        'holdings',
        sa.Column('guard_baseline_low', sa.Numeric(precision=20, scale=4), nullable=True),
    )
    op.add_column('holdings', sa.Column('guard_enabled_at', sa.DateTime(), nullable=True))
    op.add_column('holdings', sa.Column('guard_last_alert_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('holdings', 'guard_last_alert_at')
    op.drop_column('holdings', 'guard_enabled_at')
    op.drop_column('holdings', 'guard_baseline_low')
    op.drop_column('holdings', 'guard_baseline_score')
    op.drop_column('holdings', 'guard_enabled')
