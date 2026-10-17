"""Durable retirement before deleting graph/source artifacts."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("snapshots", sa.Column("retired_at", sa.DateTime(timezone=True)))
    op.add_column("snapshots", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.create_index("ix_snapshots_retired_at", "snapshots", ["retired_at"])


def downgrade():
    op.drop_index("ix_snapshots_retired_at", "snapshots")
    op.drop_column("snapshots", "purged_at")
    op.drop_column("snapshots", "retired_at")
