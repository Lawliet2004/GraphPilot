"""Durable GitHub history records.
Revision ID: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "history_records",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("branch", sa.String(200), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("relationships", sa.JSON(), nullable=False),
    )
    op.create_index("ix_history_records_repository_id", "history_records", ["repository_id"])


def downgrade():
    op.drop_table("history_records")
