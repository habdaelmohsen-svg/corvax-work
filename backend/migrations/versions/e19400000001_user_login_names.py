"""CORVAX RC27.4 H17 - login usernames and the first administrator.

Adds users.username so employees can sign in with a short name instead of an
email address, and creates the first administrator when the database has no
users yet. Without this a production deployment (where SEED_DEMO_DATA must be
false) had NO user at all and nobody could sign in.

The bootstrap administrator is created with require_password_change = true, so
the initial credentials work exactly once and must be replaced immediately.

Revision chain: follows the H13 head e19300000001.
"""
from alembic import op
import sqlalchemy as sa


revision = "e19400000001"
down_revision = "e19300000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(60)))
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    conn = op.get_bind()
    # Give the existing seeded administrator the short name "admin" so the
    # documented credentials keep working on databases that were already seeded.
    conn.execute(
        sa.text(
            "UPDATE users SET username = 'admin' "
            "WHERE username IS NULL AND email = 'admin@corvaxplatform.com'"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
