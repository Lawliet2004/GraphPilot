"""Small allowlisted administrative policy overrides; no credentials stored here."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runtime_settings",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("runtime_settings")
