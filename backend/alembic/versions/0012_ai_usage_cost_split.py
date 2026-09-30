"""add input/output cost split to ai_usage_logs

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-30

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.add_column(sa.Column("input_cost_usd", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("output_cost_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage_logs") as batch_op:
        batch_op.drop_column("output_cost_usd")
        batch_op.drop_column("input_cost_usd")
