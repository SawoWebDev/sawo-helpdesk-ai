"""add feedback_reason to chat_logs and a chat_reports table

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.add_column(sa.Column("feedback_reason", sa.String(length=40), nullable=True))

    op.create_table(
        "chat_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chat_log_id",
            sa.Integer(),
            sa.ForeignKey("chat_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("reference_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_reports_chat_log_id", "chat_reports", ["chat_log_id"])
    op.create_index("ix_chat_reports_session_id", "chat_reports", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_reports_session_id", table_name="chat_reports")
    op.drop_index("ix_chat_reports_chat_log_id", table_name="chat_reports")
    op.drop_table("chat_reports")

    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.drop_column("feedback_reason")
