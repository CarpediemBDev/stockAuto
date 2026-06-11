"""add_strategy_type_to_holding_and_tradelog

Revision ID: cc508504ea6c
Revises: a1b2c3d4e5f6
Create Date: 2026-06-11 23:05:03.693660

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
"""add_strategy_type_to_holding_and_tradelog

Revision ID: cc508504ea6c
Revises: a1b2c3d4e5f6
Create Date: 2026-06-11 23:05:03.693660

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc508504ea6c'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. strategy_type 컬럼을 우선 nullable=True로 생성하여 SQLite의 기존 데이터 제약 충돌 방지
    op.add_column('holdings', sa.Column('strategy_type', sa.String(), nullable=True))
    op.add_column('trade_logs', sa.Column('strategy_type', sa.String(), nullable=True))
    op.add_column('broker_orders', sa.Column('strategy_type', sa.String(), nullable=True))

    # 2. 기존 데이터 마이그레이션 (Prefix를 분석하여 strategy_type 추출 및 ticker 필드에서 제거)
    connection = op.get_bind()
    
    # 2-1. holdings 테이블 마이그레이션
    holdings = connection.execute(sa.text("SELECT id, ticker FROM holdings")).fetchall()
    for h_id, ticker in holdings:
        strategy_type = "regime_switching"
        clean_ticker = ticker
        if ticker:
            if ticker.startswith("EP_"):
                strategy_type = "episodic_pivot"
                clean_ticker = ticker[3:]
            elif ticker.startswith("RS_"):
                strategy_type = "regime_switching"
                clean_ticker = ticker[3:]
            elif ticker.startswith("ASQS_"):
                strategy_type = "asqs"
                clean_ticker = ticker[5:]
            elif ticker.startswith("SS_"):
                strategy_type = "senior_simple"
                clean_ticker = ticker[3:]
            elif "_" in ticker:
                parts = ticker.split("_")
                if len(parts) > 1:
                    clean_ticker = parts[-1]
                    pref = parts[0] + "_"
                    if pref == "EP_": strategy_type = "episodic_pivot"
                    elif pref == "RS_": strategy_type = "regime_switching"
                    elif pref == "ASQS_": strategy_type = "asqs"
                    elif pref == "SS_": strategy_type = "senior_simple"

        connection.execute(
            sa.text("UPDATE holdings SET strategy_type = :st, ticker = :tk WHERE id = :id"),
            {"st": strategy_type, "tk": clean_ticker, "id": h_id}
        )

    # 2-2. trade_logs 테이블 마이그레이션
    trade_logs = connection.execute(sa.text("SELECT id, ticker FROM trade_logs")).fetchall()
    for t_id, ticker in trade_logs:
        strategy_type = "regime_switching"
        clean_ticker = ticker
        if ticker:
            if ticker.startswith("EP_"):
                strategy_type = "episodic_pivot"
                clean_ticker = ticker[3:]
            elif ticker.startswith("RS_"):
                strategy_type = "regime_switching"
                clean_ticker = ticker[3:]
            elif ticker.startswith("ASQS_"):
                strategy_type = "asqs"
                clean_ticker = ticker[5:]
            elif ticker.startswith("SS_"):
                strategy_type = "senior_simple"
                clean_ticker = ticker[3:]
            elif "_" in ticker:
                parts = ticker.split("_")
                if len(parts) > 1:
                    clean_ticker = parts[-1]
                    pref = parts[0] + "_"
                    if pref == "EP_": strategy_type = "episodic_pivot"
                    elif pref == "RS_": strategy_type = "regime_switching"
                    elif pref == "ASQS_": strategy_type = "asqs"
                    elif pref == "SS_": strategy_type = "senior_simple"

        connection.execute(
            sa.text("UPDATE trade_logs SET strategy_type = :st, ticker = :tk WHERE id = :id"),
            {"st": strategy_type, "tk": clean_ticker, "id": t_id}
        )

    # 2-3. broker_orders 테이블 마이그레이션 (prefixed_ticker에서 파싱)
    broker_orders = connection.execute(sa.text("SELECT id, prefixed_ticker FROM broker_orders")).fetchall()
    for o_id, prefixed_ticker in broker_orders:
        strategy_type = "regime_switching"
        if prefixed_ticker:
            if prefixed_ticker.startswith("EP_"):
                strategy_type = "episodic_pivot"
            elif prefixed_ticker.startswith("RS_"):
                strategy_type = "regime_switching"
            elif prefixed_ticker.startswith("ASQS_"):
                strategy_type = "asqs"
            elif prefixed_ticker.startswith("SS_"):
                strategy_type = "senior_simple"
            elif "_" in prefixed_ticker:
                parts = prefixed_ticker.split("_")
                if len(parts) > 1:
                    pref = parts[0] + "_"
                    if pref == "EP_": strategy_type = "episodic_pivot"
                    elif pref == "RS_": strategy_type = "regime_switching"
                    elif pref == "ASQS_": strategy_type = "asqs"
                    elif pref == "SS_": strategy_type = "senior_simple"

        connection.execute(
            sa.text("UPDATE broker_orders SET strategy_type = :st WHERE id = :id"),
            {"st": strategy_type, "id": o_id}
        )

    # 3. SQLite 배치 방식을 통한 nullable=False 반영 및 제약 조건 갱신
    with op.batch_alter_table('holdings') as batch_op:
        batch_op.alter_column('strategy_type', existing_type=sa.String(), nullable=False, server_default="regime_switching")
        batch_op.drop_constraint('_user_ticker_uc', type_='unique')
        batch_op.create_unique_constraint('_user_ticker_strategy_uc', ['user_id', 'ticker', 'strategy_type'])

    with op.batch_alter_table('trade_logs') as batch_op:
        batch_op.alter_column('strategy_type', existing_type=sa.String(), nullable=False, server_default="regime_switching")

    with op.batch_alter_table('broker_orders') as batch_op:
        batch_op.alter_column('strategy_type', existing_type=sa.String(), nullable=False, server_default="regime_switching")


def downgrade() -> None:
    with op.batch_alter_table('broker_orders') as batch_op:
        batch_op.drop_column('strategy_type')

    with op.batch_alter_table('trade_logs') as batch_op:
        batch_op.drop_column('strategy_type')

    with op.batch_alter_table('holdings') as batch_op:
        batch_op.drop_constraint('_user_ticker_strategy_uc', type_='unique')
        batch_op.create_unique_constraint('_user_ticker_uc', ['user_id', 'ticker'])
        batch_op.drop_column('strategy_type')
