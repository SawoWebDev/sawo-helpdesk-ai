"""switch to OpenRouter embeddings (768 -> 1536 dims)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OLD_DIM = 768
NEW_DIM = 1536


def upgrade() -> None:
    # Existing vectors were produced by Ollama's nomic-embed-text (768 dims) and
    # cannot be reinterpreted at the new width, so they're dropped here. Callers
    # must run POST /api/admin/reindex afterwards to re-embed FAQ and vault
    # entries via OpenRouter.
    op.execute("DROP INDEX IF EXISTS ix_faq_entries_embedding_hnsw")
    op.execute("UPDATE faq_entries SET embedding = NULL")
    op.alter_column(
        "faq_entries",
        "embedding",
        existing_type=Vector(OLD_DIM),
        type_=Vector(NEW_DIM),
        postgresql_using="NULL",
    )
    op.execute(
        "CREATE INDEX ix_faq_entries_embedding_hnsw ON faq_entries "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.execute("DROP INDEX IF EXISTS ix_vault_entries_embedding_hnsw")
    op.execute("UPDATE vault_entries SET embedding = NULL")
    op.alter_column(
        "vault_entries",
        "embedding",
        existing_type=Vector(OLD_DIM),
        type_=Vector(NEW_DIM),
        postgresql_using="NULL",
    )
    op.execute(
        "CREATE INDEX ix_vault_entries_embedding_hnsw ON vault_entries "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vault_entries_embedding_hnsw")
    op.execute("UPDATE vault_entries SET embedding = NULL")
    op.alter_column(
        "vault_entries",
        "embedding",
        existing_type=Vector(NEW_DIM),
        type_=Vector(OLD_DIM),
        postgresql_using="NULL",
    )
    op.execute(
        "CREATE INDEX ix_vault_entries_embedding_hnsw ON vault_entries "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.execute("DROP INDEX IF EXISTS ix_faq_entries_embedding_hnsw")
    op.execute("UPDATE faq_entries SET embedding = NULL")
    op.alter_column(
        "faq_entries",
        "embedding",
        existing_type=Vector(NEW_DIM),
        type_=Vector(OLD_DIM),
        postgresql_using="NULL",
    )
    op.execute(
        "CREATE INDEX ix_faq_entries_embedding_hnsw ON faq_entries "
        "USING hnsw (embedding vector_cosine_ops)"
    )
