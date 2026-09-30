"""reviewed alternate phrasings for canonical FAQs + question-only vector tables

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-30

Additive only: a new table and two new vector tables; no existing row or
column is touched. The question-only vectors for existing FAQs are filled by
the boot-time stale-embedding repair (app/reindex_stale.py) rather than here,
since migrations must not call the embedding API. Until then the saved-answer
matcher falls back to embedding candidate questions on the fly.

"""
from alembic import op
import sqlalchemy as sa

from app.db.vec_store import FAQ_PHRASING_VEC_TABLE, FAQ_QUESTION_VEC_TABLE, create_vec_table_sql

# revision identifiers, used by Alembic.
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "faq_phrasings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("faq_id", sa.Integer(), sa.ForeignKey("faq_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phrasing", sa.Text(), nullable=False),
        sa.Column("phrasing_normalized", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("has_embedding", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_faq_phrasings_faq_id", "faq_phrasings", ["faq_id"])
    op.create_index("ix_faq_phrasings_phrasing_normalized", "faq_phrasings", ["phrasing_normalized"], unique=True)
    op.execute(create_vec_table_sql(FAQ_QUESTION_VEC_TABLE))
    op.execute(create_vec_table_sql(FAQ_PHRASING_VEC_TABLE))


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {FAQ_PHRASING_VEC_TABLE}")
    op.execute(f"DROP TABLE IF EXISTS {FAQ_QUESTION_VEC_TABLE}")
    op.drop_index("ix_faq_phrasings_phrasing_normalized", table_name="faq_phrasings")
    op.drop_index("ix_faq_phrasings_faq_id", table_name="faq_phrasings")
    op.drop_table("faq_phrasings")
