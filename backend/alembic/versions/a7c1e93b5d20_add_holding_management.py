"""add holdings.management (봇 관할권 구분)

봇이 매수하지 않은 보유 종목을 봇의 매도·추가매수 대상에서 분리하기 위한 컬럼이다.

배경 - 현재 sync_broker_holdings는 DB에 없는 브로커 보유분을 "유령 보유"로 간주해
첫 번째 전략 슬롯 아래에 Holding으로 자동 생성한다. 즉 기본값이 "봇이 건드린다"라서,
실증권 API를 연동하면 사용자가 봇 도입 이전에 직접 매수한 종목 전체가 봇 관리 대상이
되고 시그널이 나쁘면 그대로 청산된다. 2026-09-05 admin 계정 HCTI 실측에서 이 경로가
실제로 즉시 손절 매도를 냈다.

값은 Boolean이 아니라 String으로 연다. 3단계 위임(DELEGATED)이 뒤에 붙을 예정이고,
Boolean으로 파면 그때 마이그레이션을 두 번 하게 된다.

기존 행은 전부 BOT_OWNED로 채운다 - 지금까지 생성된 Holding은 모두 봇 매수 경로이거나
유령 보유 복원분이며, 후자를 EXTERNAL로 소급 판정할 근거가 DB에 없다. 소급 분류는
하지 않고 이후 동기화부터 새 기본값이 적용된다.

상세 설계는 docs/plans/holding_management_modes.md가 소유한다.

Revision ID: a7c1e93b5d20
Revises: d4e2f8a13c65
Create Date: 2026-09-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c1e93b5d20'
down_revision: Union[str, None] = 'd4e2f8a13c65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'holdings',
        sa.Column('management', sa.String(), nullable=False, server_default='BOT_OWNED'),
    )


def downgrade() -> None:
    op.drop_column('holdings', 'management')
