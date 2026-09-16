"""add label to harvest_jobs

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-16

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("harvest_jobs") as batch_op:
        batch_op.add_column(sa.Column("label", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("harvest_jobs") as batch_op:
        batch_op.drop_column("label")
