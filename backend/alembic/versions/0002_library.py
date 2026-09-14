"""library / knowledge base module

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("faq_entries") as batch_op:
        batch_op.add_column(sa.Column("source_label", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("status", sa.String(20), nullable=False, server_default="published")
        )
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_faq_entries_source_id_harvest_sources",
            "harvest_sources",
            ["source_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_faq_entries_status", "faq_entries", ["status"])
    op.create_index("ix_faq_entries_source_id", "faq_entries", ["source_id"])

    with op.batch_alter_table("harvest_sources") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_harvest_sources_category_id_categories",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.add_column(sa.Column("crawl_depth", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("auto_generate_faqs", sa.Boolean(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("faq_generation_status", sa.String(20), nullable=True))
        batch_op.add_column(
            sa.Column("generated_faq_count", sa.Integer(), nullable=False, server_default="0")
        )
    op.create_index("ix_harvest_sources_category_id", "harvest_sources", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_harvest_sources_category_id", table_name="harvest_sources")
    with op.batch_alter_table("harvest_sources") as batch_op:
        batch_op.drop_column("generated_faq_count")
        batch_op.drop_column("faq_generation_status")
        batch_op.drop_column("auto_generate_faqs")
        batch_op.drop_column("chunk_count")
        batch_op.drop_constraint("fk_harvest_sources_category_id_categories", type_="foreignkey")
        batch_op.drop_column("category_id")

    op.drop_index("ix_faq_entries_source_id", table_name="faq_entries")
    op.drop_index("ix_faq_entries_status", table_name="faq_entries")
    with op.batch_alter_table("faq_entries") as batch_op:
        batch_op.drop_constraint("fk_faq_entries_source_id_harvest_sources", type_="foreignkey")
        batch_op.drop_column("source_id")
        batch_op.drop_column("status")
        batch_op.drop_column("source_label")
