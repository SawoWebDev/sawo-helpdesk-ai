"""add cost_usd to ai_usage_logs

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.add_column(sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.drop_column("cost_usd")
