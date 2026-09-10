"""add holdings.harvest_arm_pct / harvest_trailing_pct (수확 임계값 관측 스냅샷)

수확 모드의 무장 임계와 트레일링 폭은 ATR에서 파생되므로 시점마다 다르고 DB 어디에도
남지 않았다. 그래서 사용자는 자기 종목이 몇 % 올라야 무장되는지, 무장 뒤 몇 % 빠지면
팔리는지를 화면에서 알 수 없었다.

잔고 API가 직접 계산하려면 ATR을 얻으려 외부 시세를 호출해야 하는데, 이는 "유저 대면
경로 외부 호출 0건" 원칙에 어긋난다. 스케줄러는 이 두 값을 매 사이클 이미 계산하므로
계산을 옮기지 않고 결과만 영속화한다.

판정의 입력이 아니라 판정 결과의 기록이다. NULL이면 화면이 값을 감출 뿐이고 수확 판정은
종전대로 그 사이클에 계산한 값으로 동작한다.

Revision ID: d4e1c8b7f206
Revises: b6d1af02c395
Create Date: 2026-09-09 02:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e1c8b7f206'
down_revision: Union[str, None] = 'b6d1af02c395'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('holdings', sa.Column('harvest_arm_pct', sa.Float(), nullable=True))
    op.add_column('holdings', sa.Column('harvest_trailing_pct', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('holdings', 'harvest_trailing_pct')
    op.drop_column('holdings', 'harvest_arm_pct')
