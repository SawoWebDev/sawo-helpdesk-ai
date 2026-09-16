"""add session_id and ip_address to chat_logs

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-16

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.add_column(sa.Column("session_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.create_index("ix_chat_logs_session_id", "chat_logs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_logs_session_id", table_name="chat_logs")
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.drop_column("ip_address")
        batch_op.drop_column("session_id")
