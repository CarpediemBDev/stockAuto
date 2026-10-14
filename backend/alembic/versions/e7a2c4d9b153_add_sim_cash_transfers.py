"""add sim_cash_transfers (SIMULATED 계좌 입출금 원장)

시뮬 계좌의 현금은 "초기자금 + 실현손익 - 보유 매입금"으로 계산되고, 초기자금은 전역 설정
하나(SIMULATED_INITIAL_CASH_KRW)뿐이라 사용자별로 자본을 더할 방법이 없었다. 외부 보유분을
옮겨 넣으면 그 매입금이 시뮬 현금에서 빠져 봇이 쓸 돈이 사라졌다(2026-09-24 admin HCTI).

사용자별 입출금을 원장으로 남기고, 투입 자본 = 초기자금 + 원장 합계로 계산한다. 실계좌는
증권사가 잔고를 계산하므로 이 테이블을 읽지 않는다.

새 테이블만 만든다. 기존 행은 건드리지 않으므로 downgrade는 테이블 삭제로 완결된다.

Revision ID: e7a2c4d9b153
Revises: d4e1c8b7f206
Create Date: 2026-09-26 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a2c4d9b153'
down_revision: Union[str, None] = 'd4e1c8b7f206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sim_cash_transfers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount_krw', sa.Numeric(precision=20, scale=4, asdecimal=True), nullable=False),
        sa.Column('memo', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sim_cash_transfers_id'), 'sim_cash_transfers', ['id'], unique=False)
    op.create_index(op.f('ix_sim_cash_transfers_user_id'), 'sim_cash_transfers', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sim_cash_transfers_user_id'), table_name='sim_cash_transfers')
    op.drop_index(op.f('ix_sim_cash_transfers_id'), table_name='sim_cash_transfers')
    op.drop_table('sim_cash_transfers')
