"""add feature to ai_usage_logs

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.add_column(sa.Column("feature", sa.String(length=40), nullable=True))
    op.create_index("ix_ai_usage_logs_feature", "ai_usage_logs", ["feature"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_feature", table_name="ai_usage_logs")
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.drop_column("feature")
