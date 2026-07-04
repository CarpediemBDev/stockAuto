"""add system settings

Revision ID: 6f1a2b3c4d5e
Revises: 4f294cc0a849
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f1a2b3c4d5e"
down_revision: Union[str, None] = "4f294cc0a849"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_runtime", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(op.f("ix_system_settings_key"), "system_settings", ["key"], unique=False)
    op.create_index(op.f("ix_system_settings_category"), "system_settings", ["category"], unique=False)

    op.execute(
        """
        INSERT INTO system_settings
            (key, value, value_type, category, description, is_runtime, is_public, created_at, updated_at)
        VALUES
            (
                'enable_gemini_news_analysis',
                'false',
                'bool',
                'ai',
                'Enable Gemini-backed AI analysis for scanner news headlines.',
                1,
                0,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_settings_category"), table_name="system_settings")
    op.drop_index(op.f("ix_system_settings_key"), table_name="system_settings")
    op.drop_table("system_settings")
