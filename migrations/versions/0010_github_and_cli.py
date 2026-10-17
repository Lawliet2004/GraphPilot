"""GitHub App connections and scoped browser-approved CLI credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_tokens", sa.Column("scopes", sa.JSON(), nullable=False, server_default='["read"]')
    )
    op.add_column("repositories", sa.Column("github_repository_id", sa.String(30)))
    op.add_column("repositories", sa.Column("github_connection_user_id", sa.String(36)))
    op.create_foreign_key(
        "fk_repo_github_user", "repositories", "users", ["github_connection_user_id"], ["id"]
    )
    op.create_table(
        "github_connections",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("github_user_id", sa.String(30), nullable=False, unique=True),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "authorization_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("session_id", sa.String(64)),
        sa.Column("verifier", sa.Text(), nullable=False),
        sa.Column("code", sa.String(12), unique=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_poll_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_authorization_requests_expires_at", "authorization_requests", ["expires_at"]
    )


def downgrade():
    op.drop_table("authorization_requests")
    op.drop_table("github_connections")
    op.drop_constraint("fk_repo_github_user", "repositories", type_="foreignkey")
    op.drop_column("repositories", "github_connection_user_id")
    op.drop_column("repositories", "github_repository_id")
    op.drop_column("agent_tokens", "scopes")
