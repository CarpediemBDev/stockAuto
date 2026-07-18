"""expose_slot_strategies

격리형 슬롯 모드를 유저 전략 카탈로그에 노출한다(사용자 결정: A안 슬롯 노출).
f3579(catalog meta)에서 슬롯을 is_selectable=0으로 숨겼던 것을 forward 마이그레이션으로
되돌린다. 함께 카탈로그 정렬값을 부여하고, 3슬롯 중복 별칭을 폴딩한다.

- multi_slot(2슬롯), multi_slot_3(3슬롯): 노출 + 메달 티어(10/20/30) 직후 밴드(40/50)에 배치.
- three_slot: multi_slot_3와 동일한 3슬롯 구성의 별칭 → 카탈로그 중복 카드 방지를 위해 숨김.
  (동작 라우팅 키는 유지되므로 이미 three_slot을 쓰는 계정에는 영향 없음)
- core_satellite은 f3579에서 내부 전용으로 숨긴 상태를 유지한다.

주: f3579는 이미 적용된 마이그레이션이므로 in-place 편집이 아니라 별도 forward 리비전으로
모든 환경(기존 DB·신규 DB)이 동일하게 수렴하도록 한다.

Revision ID: e1a2b3c4d5f6
Revises: f3579cf7ae49
Create Date: 2026-07-18 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5f6'
down_revision: Union[str, None] = 'f3579cf7ae49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # f3579는 헤드라인 전략에만 정렬값(10~210)을 부여하고 나머지를 0으로 남겨,
    # 미분류 전략이 오름차순 정렬 시 featured보다 앞에 오는 문제가 있었다.
    # 미분류(sort_order=0/NULL)를 featured 밴드 뒤(500)로 밀어 정렬 의미를 살린다.
    op.execute("UPDATE strategies SET sort_order=500 WHERE sort_order IS NULL OR sort_order=0")
    # 2슬롯 / 3슬롯 노출 + 메달 티어(10/20/30) 직후 밴드(40/50)에 배치 (위 500 덮어씀)
    op.execute("UPDATE strategies SET is_selectable=1, sort_order=40 WHERE strategy_type='multi_slot'")
    op.execute("UPDATE strategies SET is_selectable=1, sort_order=50 WHERE strategy_type='multi_slot_3'")
    # three_slot은 multi_slot_3와 동일 구성의 별칭 → 중복 카드 방지 위해 카탈로그에서 숨김(동작 키 유지)
    op.execute("UPDATE strategies SET is_selectable=0 WHERE strategy_type='three_slot'")


def downgrade() -> None:
    # 미분류 밴드(500) 원복 및 슬롯 상태 원복
    op.execute("UPDATE strategies SET sort_order=0 WHERE sort_order=500")
    op.execute(
        "UPDATE strategies SET is_selectable=0, sort_order=0 "
        "WHERE strategy_type IN ('multi_slot', 'multi_slot_3', 'three_slot')"
    )
