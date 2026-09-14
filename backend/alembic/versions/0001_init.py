"""initial schema (SQLite + sqlite-vec + FTS5)

Revision ID: 0001
Revises:
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa

from app.core.config import settings

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = settings.embedding_dimensions


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "faq_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("image_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reference_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("has_embedding", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        f"CREATE VIRTUAL TABLE faq_entries_vec USING vec0("
        f"embedding float[{EMBEDDING_DIM}] distance_metric=cosine)"
    )

    op.create_table(
        "unanswered_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resulting_faq_id", sa.Integer(), sa.ForeignKey("faq_entries.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "chat_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("matched_faq_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("matched_vault_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("engine_used", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "harvest_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("total_items", sa.Integer(), nullable=True),
        sa.Column("processed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="0"),
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
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("harvest_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("has_embedding", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_vault_entries_category_id", "vault_entries", ["category_id"])
    op.create_index("ix_vault_entries_source_id", "vault_entries", ["source_id"])
    op.create_index("ix_vault_entries_memory_enabled", "vault_entries", ["memory_enabled"])
    op.execute(
        f"CREATE VIRTUAL TABLE vault_entries_vec USING vec0("
        f"embedding float[{EMBEDDING_DIM}] distance_metric=cosine)"
    )

    # FTS5 external-content table mirroring title+content, kept in sync via
    # triggers (FTS5 has no built-in "auto-index this table" like Postgres's
    # tsvector trigger function, so we wire the three cases up by hand).
    op.execute(
        "CREATE VIRTUAL TABLE vault_entries_fts USING fts5("
        "title, content, content='vault_entries', content_rowid='id')"
    )
    op.execute(
        """
        CREATE TRIGGER vault_entries_fts_ai AFTER INSERT ON vault_entries BEGIN
            INSERT INTO vault_entries_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER vault_entries_fts_ad AFTER DELETE ON vault_entries BEGIN
            INSERT INTO vault_entries_fts(vault_entries_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER vault_entries_fts_au AFTER UPDATE ON vault_entries BEGIN
            INSERT INTO vault_entries_fts(vault_entries_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO vault_entries_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS vault_entries_fts_au")
    op.execute("DROP TRIGGER IF EXISTS vault_entries_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS vault_entries_fts_ai")
    op.execute("DROP TABLE IF EXISTS vault_entries_fts")
    op.execute("DROP TABLE IF EXISTS vault_entries_vec")

    op.drop_index("ix_vault_entries_memory_enabled", table_name="vault_entries")
    op.drop_index("ix_vault_entries_source_id", table_name="vault_entries")
    op.drop_index("ix_vault_entries_category_id", table_name="vault_entries")
    op.drop_table("vault_entries")

    op.drop_index("ix_harvest_sources_status", table_name="harvest_sources")
    op.drop_index("ix_harvest_sources_job_id", table_name="harvest_sources")
    op.drop_table("harvest_sources")

    op.drop_table("harvest_jobs")
    op.drop_table("chat_logs")
    op.drop_table("unanswered_questions")

    op.execute("DROP TABLE IF EXISTS faq_entries_vec")
    op.drop_table("faq_entries")

    op.drop_table("settings")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.drop_table("categories")
