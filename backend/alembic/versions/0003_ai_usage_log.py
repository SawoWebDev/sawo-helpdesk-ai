"""ai usage tracking (free-model token/request monitoring)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("is_free", sa.Boolean(), nullable=False),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_logs_created_at", "ai_usage_logs", ["created_at"])
    op.create_index("ix_ai_usage_logs_is_free", "ai_usage_logs", ["is_free"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_is_free", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_created_at", table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")
