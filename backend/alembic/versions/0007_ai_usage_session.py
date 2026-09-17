"""add session_id to ai_usage_logs

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.add_column(sa.Column("session_id", sa.String(length=64), nullable=True))
    op.create_index("ix_ai_usage_logs_session_id", "ai_usage_logs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_session_id", table_name="ai_usage_logs")
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.drop_column("session_id")
