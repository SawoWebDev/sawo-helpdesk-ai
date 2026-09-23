"""add occurrence_count and last_asked_at to unanswered_questions

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("unanswered_questions") as batch_op:
        batch_op.add_column(
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("last_asked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("unanswered_questions") as batch_op:
        batch_op.drop_column("last_asked_at")
        batch_op.drop_column("occurrence_count")
