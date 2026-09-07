"""add holdings harvest mode columns (수확 모드)

봇 관할 밖(EXTERNAL) 보유분에 "급등하면 수확" 옵션을 붙이기 위한 컬럼이다.

반토막 난 종목이 급등했다가 되돌아가는 것을 사용자가 자는 동안 지켜보기만 하는 문제를
해결한다. 봇은 고점을 예측하지 않고 관측 최고가를 기록만 하다가, 고점 대비 정해진 폭만큼
내려온 상태가 두 사이클 연속되면 판다.

observed_base_price를 avg_price와 분리하는 이유가 이 기능의 핵심이다. 기존 트레일링 스탑은
highest_price > avg_price 가드에 걸려 반토막 종목에서 영원히 발동하지 않는다(본전을 넘긴 적이
없으므로). 앵커를 "봇이 처음 본 가격"으로 옮겨야 $50까지 빠진 종목이 $90에서 꺾일 때 팔 수 있다.
같은 값이 매도 하한으로도 쓰인다 - 관측 시작가 아래에서는 절대 팔지 않는다.

harvest_enabled 기본값은 False다. EXTERNAL의 계약이 "봇이 안 건드림"이므로 자동 매도는
사용자가 종목별로 명시적으로 켜야 한다.

상세 설계는 docs/plans/holding_management_modes.md 5.2절.

Revision ID: b8d2fa46c931
Revises: a7c1e93b5d20
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d2fa46c931'
down_revision: Union[str, None] = 'a7c1e93b5d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'holdings',
        sa.Column('observed_base_price', sa.Numeric(precision=20, scale=4), nullable=True),
    )
    op.add_column(
        'holdings',
        sa.Column('harvest_enabled', sa.Boolean(), nullable=False, server_default='0'),
    )
    op.add_column(
        'holdings',
        sa.Column('harvest_armed', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('holdings', 'harvest_armed')
    op.drop_column('holdings', 'harvest_enabled')
    op.drop_column('holdings', 'observed_base_price')
