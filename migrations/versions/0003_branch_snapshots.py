"""Branch heads and immutable evidence snapshots, preserving existing heads."""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("branch", sa.String(200), nullable=True))
    op.add_column("conversations", sa.Column("snapshot_id", sa.String(36), nullable=True))
    op.create_table(
        "repository_branches",
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("branch", sa.String(200), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("commit_sha", sa.String(64)),
        sa.Column("graph_name", sa.String(200)),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("sync_state", sa.JSON(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("branch", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("graph_name", sa.String(200), unique=True, nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("sync_state", sa.JSON(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "snapshots_repository_branch", "snapshots", ["repository_id", "branch", "created_at"]
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO repository_branches (repository_id,branch,status,commit_sha,graph_name,stats,sync_state,indexed_at,created_at) SELECT id,branch,status,commit_sha,graph_name,stats,sync_state,indexed_at,created_at FROM repositories"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE jobs SET branch = repositories.branch FROM repositories WHERE jobs.repository_id = repositories.id"
        )
    )
    rows = connection.execute(
        sa.text(
            "SELECT id,branch,commit_sha,graph_name,stats,sync_state,indexed_at,created_at FROM repositories WHERE graph_name IS NOT NULL AND commit_sha IS NOT NULL"
        )
    ).mappings()
    table = sa.table(
        "snapshots",
        sa.column("id", sa.String()),
        sa.column("repository_id", sa.String()),
        sa.column("branch", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("commit_sha", sa.String()),
        sa.column("graph_name", sa.String()),
        sa.column("stats", sa.JSON()),
        sa.column("sync_state", sa.JSON()),
        sa.column("indexed_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    for row in rows:
        connection.execute(
            table.insert().values(
                id=str(uuid.uuid4()),
                repository_id=row["id"],
                kind="index",
                **{k: row[k] for k in row if k != "id"},
            )
        )


def downgrade():
    op.drop_table("snapshots")
    op.drop_table("repository_branches")
    op.drop_column("conversations", "snapshot_id")
    op.drop_column("jobs", "branch")
