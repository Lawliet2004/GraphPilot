"""Observable external worker presence; never inferred from API readiness."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("active_job_id", sa.String(36)),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_worker_heartbeats_last_seen", "worker_heartbeats", ["last_seen"])


def downgrade():
    op.drop_table("worker_heartbeats")
