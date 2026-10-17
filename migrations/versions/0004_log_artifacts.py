"""Permission-scoped redacted CI log artifacts with enforced expiration."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "log_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("branch", sa.String(200), nullable=False),
        sa.Column("node_id", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_log_artifacts_repository_id", "log_artifacts", ["repository_id"])
    op.create_index("ix_log_artifacts_expires_at", "log_artifacts", ["expires_at"])


def downgrade():
    op.drop_table("log_artifacts")
