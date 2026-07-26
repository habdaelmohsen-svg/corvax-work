"""year-end close v0.32

Revision ID: e32000000001
Revises: e28000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e32000000001"
down_revision = "e28000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "year_end_close_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fiscal_year_id", sa.Integer(), sa.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("retained_earnings_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("current_year_result", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("closing_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "fiscal_year_id", name="uq_year_end_company_year"),
    )
    op.create_index("ix_year_end_close_runs_company_id", "year_end_close_runs", ["company_id"])
    op.create_index("ix_year_end_close_runs_fiscal_year_id", "year_end_close_runs", ["fiscal_year_id"])
    op.create_index("ix_year_end_close_runs_status", "year_end_close_runs", ["status"])
    op.create_table(
        "year_end_close_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year_end_run_id", sa.Integer(), sa.ForeignKey("year_end_close_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("details", sa.Text()),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("year_end_run_id", "code", name="uq_year_end_check_code"),
    )
    op.create_index("ix_year_end_close_checks_year_end_run_id", "year_end_close_checks", ["year_end_run_id"])
    op.execute("""
        INSERT INTO permissions (code, name_ar, name_en)
        SELECT 'year.close', 'إقفال السنة المالية', 'Close fiscal year'
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'year.close')
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'CFO' AND p.code = 'year.close'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """)


def downgrade():
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'year.close')
    """)
    op.execute("DELETE FROM permissions WHERE code = 'year.close'")
    op.drop_table("year_end_close_checks")
    op.drop_table("year_end_close_runs")
