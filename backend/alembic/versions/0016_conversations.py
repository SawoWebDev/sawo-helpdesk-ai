"""add conversations table and chat_logs.conversation_id

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_owner_hash", "conversations", ["owner_hash"])

    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_chat_logs_conversation_id_conversations",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_chat_logs_conversation_id", "chat_logs", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_logs_conversation_id", table_name="chat_logs")
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.drop_constraint("fk_chat_logs_conversation_id_conversations", type_="foreignkey")
        batch_op.drop_column("conversation_id")

    op.drop_index("ix_conversations_owner_hash", table_name="conversations")
    op.drop_table("conversations")
