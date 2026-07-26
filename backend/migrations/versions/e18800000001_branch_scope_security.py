"""branch scope security PH01

Revision ID: e18800000001
Revises: e18700000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e18800000001"
down_revision = "e18700000001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_company_roles") as batch:
        batch.add_column(sa.Column("branch_scope", sa.String(length=20), nullable=False, server_default="ALL"))
    op.create_table(
        "user_company_role_branches",
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["membership_id"], ["user_company_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("membership_id", "branch_id"),
        sa.UniqueConstraint("membership_id", "branch_id", name="uq_membership_branch"),
    )
    op.create_index("ix_user_company_role_branches_branch_id", "user_company_role_branches", ["branch_id"])


def downgrade():
    op.drop_index("ix_user_company_role_branches_branch_id", table_name="user_company_role_branches")
    op.drop_table("user_company_role_branches")
    with op.batch_alter_table("user_company_roles") as batch:
        batch.drop_column("branch_scope")
