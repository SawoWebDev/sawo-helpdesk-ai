"""add rating and rated_at to chat_logs

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.add_column(sa.Column("rating", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.drop_column("rated_at")
        batch_op.drop_column("rating")
