"""knowledge harvester + vault tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.create_table(
        "harvest_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("total_items", sa.Integer(), nullable=True),
        sa.Column("processed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "harvest_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("harvest_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("origin_url", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("extracted_char_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_harvest_sources_job_id", "harvest_sources", ["job_id"])
    op.create_index("ix_harvest_sources_status", "harvest_sources", ["status"])

    op.create_table(
        "vault_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("harvest_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_vault_entries_category_id", "vault_entries", ["category_id"])
    op.create_index("ix_vault_entries_source_id", "vault_entries", ["source_id"])
    op.create_index("ix_vault_entries_memory_enabled", "vault_entries", ["memory_enabled"])
    op.execute(
        "CREATE INDEX ix_vault_entries_embedding_hnsw ON vault_entries "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_vault_entries_search_vector_gin ON vault_entries "
        "USING gin (search_vector)"
    )
    op.execute(
        """
        CREATE TRIGGER vault_entries_search_vector_trigger
        BEFORE INSERT OR UPDATE ON vault_entries
        FOR EACH ROW EXECUTE FUNCTION
        tsvector_update_trigger(search_vector, 'pg_catalog.english', title, content)
        """
    )

    op.add_column(
        "chat_logs",
        sa.Column("matched_vault_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("chat_logs", "matched_vault_ids")

    op.execute("DROP TRIGGER IF EXISTS vault_entries_search_vector_trigger ON vault_entries")
    op.execute("DROP INDEX IF EXISTS ix_vault_entries_search_vector_gin")
    op.execute("DROP INDEX IF EXISTS ix_vault_entries_embedding_hnsw")
    op.drop_index("ix_vault_entries_memory_enabled", table_name="vault_entries")
    op.drop_index("ix_vault_entries_source_id", table_name="vault_entries")
    op.drop_index("ix_vault_entries_category_id", table_name="vault_entries")
    op.drop_table("vault_entries")

    op.drop_index("ix_harvest_sources_status", table_name="harvest_sources")
    op.drop_index("ix_harvest_sources_job_id", table_name="harvest_sources")
    op.drop_table("harvest_sources")

    op.drop_table("harvest_jobs")
