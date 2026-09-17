"""add provider, finish_reason, latency_ms to ai_usage_logs

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.add_column(sa.Column("provider", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("finish_reason", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.drop_column("latency_ms")
        batch_op.drop_column("finish_reason")
        batch_op.drop_column("provider")
