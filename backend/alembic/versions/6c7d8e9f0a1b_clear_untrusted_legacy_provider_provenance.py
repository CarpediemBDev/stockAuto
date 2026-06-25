"""Clear provider provenance that cannot be inferred from legacy settings.

Revision ID: 6c7d8e9f0a1b
Revises: 5b6c7d8e9f0a
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op


revision: str = "6c7d8e9f0a1b"
down_revision: Union[str, None] = "5b6c7d8e9f0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 5b revision이 이 후속 안전화 전에 적용된 로컬/preview DB도 보수합니다.
    # 과거 UserSettings는 원장 생성 시점의 provider 증거가 아니므로
    # 기존 출처는 모두 불명(NULL)으로 돌려 자동 주문을 fail-closed 합니다.
    op.execute("UPDATE holdings SET broker_provider = NULL")
    op.execute("UPDATE broker_orders SET broker_provider = NULL")


def downgrade() -> None:
    # 불명한 출처를 재생성할 수 없으므로 안전하게 NULL을 유지합니다.
    pass
