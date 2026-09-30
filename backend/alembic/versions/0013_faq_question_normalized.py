"""add indexed normalized question to faq_entries for exact-repeat lookups

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-30

"""
from alembic import op
import sqlalchemy as sa

from app.rag.question_normalize import normalize_question

# revision identifiers, used by Alembic.
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("faq_entries") as batch_op:
        batch_op.add_column(sa.Column("question_normalized", sa.Text(), nullable=True))
    op.create_index("ix_faq_entries_question_normalized", "faq_entries", ["question_normalized"])

    # Backfill existing rows. Same function the app's ORM hook uses on every
    # later write, so old and new rows share one key format.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, question FROM faq_entries")).fetchall()
    for row_id, question in rows:
        conn.execute(
            sa.text("UPDATE faq_entries SET question_normalized = :n WHERE id = :id"),
            {"n": normalize_question(question), "id": row_id},
        )


def downgrade() -> None:
    op.drop_index("ix_faq_entries_question_normalized", table_name="faq_entries")
    with op.batch_alter_table("faq_entries") as batch_op:
        batch_op.drop_column("question_normalized")
