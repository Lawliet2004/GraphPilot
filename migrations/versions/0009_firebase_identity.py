"""Explicit Firebase UID links; roles and repository ownership remain local."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("firebase_identity", sa.String(200), nullable=True))
    op.create_unique_constraint("uq_users_firebase_identity", "users", ["firebase_identity"])


def downgrade():
    op.drop_constraint("uq_users_firebase_identity", "users", type_="unique")
    op.drop_column("users", "firebase_identity")
