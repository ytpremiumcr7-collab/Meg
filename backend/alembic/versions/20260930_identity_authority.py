"""Invalidate sessions transactionally when identity authority changes."""
from alembic import op
import sqlalchemy as sa

revision = "20260930_identity_authority"
down_revision = "20260930_tez_timestamps"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("users", "auth_version")
