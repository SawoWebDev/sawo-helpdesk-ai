"""add resolved_at/resolved_by to chat_reports

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_reports") as batch_op:
        batch_op.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        # Username snapshot, not a users.id FK — same reasoning as this
        # table's other fields (question_text/answer_text etc.): who
        # resolved it should still read correctly even if that account is
        # later deleted.
        batch_op.add_column(sa.Column("resolved_by", sa.String(length=150), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_reports") as batch_op:
        batch_op.drop_column("resolved_by")
        batch_op.drop_column("resolved_at")
