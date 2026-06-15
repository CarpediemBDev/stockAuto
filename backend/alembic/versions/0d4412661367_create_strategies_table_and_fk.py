"""create_strategies_table_and_fk

Revision ID: 0d4412661367
Revises: cc508504ea6c
Create Date: 2026-06-15 21:37:05.554127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d4412661367'
down_revision: Union[str, None] = 'cc508504ea6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create strategies table
    op.create_table('strategies',
    sa.Column('strategy_type', sa.String(), nullable=False),
    sa.Column('name_ko', sa.String(), nullable=False),
    sa.Column('name_en', sa.String(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('strategy_type')
    )
    op.create_index(op.f('ix_strategies_strategy_type'), 'strategies', ['strategy_type'], unique=False)

    # 2. Insert initial strategy data from strategies.yml (to prevent FK violations on existing data)
    import os
    import yaml
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    yaml_path = os.path.join(backend_dir, "app", "translations", "strategies.yml")
    
    connection = op.get_bind()
    
    if os.path.exists(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as yf:
            yaml_strategies = yaml.safe_load(yf) or {}
        
        for s_type, info in yaml_strategies.items():
            name_ko = info.get("ko", s_type)
            name_en = info.get("en", s_type)
            connection.execute(
                sa.text(
                    "INSERT INTO strategies (strategy_type, name_ko, name_en, is_active) "
                    "VALUES (:s_type, :name_ko, :name_en, 1)"
                ),
                {"s_type": s_type, "name_ko": name_ko, "name_en": name_en}
            )
    else:
        default_strategies = [
            ("regime_switching", "마스터 레짐스위칭", "Regime Switching"),
            ("senior_simple", "시니어 단순화", "Strategy S"),
            ("episodic_pivot", "에피소딕 피벗", "Episodic Pivot"),
            ("qullamaggie", "쿨라매기 돌파", "Qullamaggie"),
            ("obv_only", "차트픽 OBV 매집", "OBV Only"),
            ("multi_slot", "격리형 2슬롯 (EP 50% : RS 50%)", "Modular 2-Slot (EP 50% : RS 50%)"),
            ("three_slot", "격리형 3슬롯 (EP 30% : ASQS 30% : RS 40%)", "Modular 3-Slot (EP 30% : ASQS 30% : RS 40%)"),
            ("asqs", "🚀 ASQS (초신성 퀀텀 스퀴즈) 🔥", "Asqs"),
            ("bb_squeeze", "존카터 BB스퀴즈", "TTM Squeeze"),
            ("rsi2_connors", "래리코너스 RSI 2", "RSI 2 Only"),
            ("strategy_c", "전략 C (11대 복합)", "Strategy C"),
        ]
        for s_type, name_ko, name_en in default_strategies:
            connection.execute(
                sa.text(
                    "INSERT INTO strategies (strategy_type, name_ko, name_en, is_active) "
                    "VALUES (:s_type, :name_ko, :name_en, 1)"
                ),
                {"s_type": s_type, "name_ko": name_ko, "name_en": name_en}
            )

    # 3. Create foreign keys using batch_alter_table for SQLite compatibility
    with op.batch_alter_table('broker_orders', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_broker_orders_strategy_type', 'strategies', ['strategy_type'], ['strategy_type'], onupdate='CASCADE')

    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_holdings_strategy_type', 'strategies', ['strategy_type'], ['strategy_type'], onupdate='CASCADE')

    with op.batch_alter_table('trade_logs', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_trade_logs_strategy_type', 'strategies', ['strategy_type'], ['strategy_type'], onupdate='CASCADE')

    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_user_settings_strategy_type', 'strategies', ['strategy_type'], ['strategy_type'], onupdate='CASCADE')


def downgrade() -> None:
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_settings_strategy_type', type_='foreignkey')

    with op.batch_alter_table('trade_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_trade_logs_strategy_type', type_='foreignkey')

    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_holdings_strategy_type', type_='foreignkey')

    with op.batch_alter_table('broker_orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_broker_orders_strategy_type', type_='foreignkey')

    op.drop_index(op.f('ix_strategies_strategy_type'), table_name='strategies')
    op.drop_table('strategies')
