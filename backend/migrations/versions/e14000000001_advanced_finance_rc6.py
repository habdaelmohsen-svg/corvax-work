"""advanced financial reporting and lease modifications rc6

Revision ID: e14000000001
Revises: e13000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e14000000001"
down_revision = "e13000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_statement_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("statement", sa.String(30), nullable=False, server_default="PROFIT_OR_LOSS"),
        sa.Column("ifrs18_category", sa.String(30), nullable=False),
        sa.Column("line_code", sa.String(50), nullable=False, index=True),
        sa.Column("line_name_ar", sa.String(250), nullable=False),
        sa.Column("line_name_en", sa.String(250), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_oci", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "account_id", name="uq_financial_mapping_company_account"),
    )
    op.create_table(
        "financial_report_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False, index=True),
        sa.Column("comparative_start_date", sa.Date()),
        sa.Column("comparative_end_date", sa.Date()),
        sa.Column("framework", sa.String(30), nullable=False, server_default="IFRS_18"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("report_payload", sa.Text(), nullable=False),
        sa.Column("validation_payload", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
    )
    op.create_table(
        "financial_disclosure_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("note_code", sa.String(40), nullable=False),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("standard", sa.String(50), nullable=False),
        sa.Column("content_ar", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_en", sa.Text(), nullable=False, server_default=""),
        sa.Column("supporting_reference", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_end", "note_code", name="uq_disclosure_company_period_code"),
    )
    op.create_table(
        "lease_modifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lease_id", sa.Integer(), sa.ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=False, index=True),
        sa.Column("modification_type", sa.String(30), nullable=False, server_default="REMEASUREMENT"),
        sa.Column("new_end_date", sa.Date(), nullable=False),
        sa.Column("new_payment_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("new_discount_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("carrying_liability", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("remeasured_liability", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("rou_adjustment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
    )

    bind = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=bind)
    roles = sa.Table("roles", meta, autoload_with=bind)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=bind)
    defs = {
        "finance.reporting.manage": ("إعداد التقارير المالية المتقدمة", "Prepare advanced financial reporting"),
        "finance.reporting.approve": ("اعتماد التقارير المالية المتقدمة", "Approve advanced financial reporting"),
        "finance.disclosures.manage": ("إعداد الإيضاحات المالية", "Prepare financial disclosures"),
        "finance.disclosures.approve": ("مراجعة واعتماد الإيضاحات المالية", "Review and approve financial disclosures"),
        "leases.modify": ("إدارة تعديلات عقود الإيجار", "Manage lease modifications"),
        "leases.modify.approve": ("اعتماد تعديلات عقود الإيجار", "Approve lease modifications"),
    }
    pids = {}
    for code, (ar, en) in defs.items():
        pid = bind.execute(sa.select(permissions.c.id).where(permissions.c.code == code)).scalar()
        if pid is None:
            result = bind.execute(permissions.insert().values(code=code, name_ar=ar, name_en=en))
            pid = result.inserted_primary_key[0]
        pids[code] = pid
    grants = {
        "ACCOUNTANT": ["finance.reporting.manage", "finance.disclosures.manage", "leases.modify"],
        "FINANCIAL_CONTROLLER": list(defs),
        "CFO": list(defs),
        "AUDITOR": ["finance.reporting.approve", "finance.disclosures.approve", "leases.modify.approve"],
    }
    for role_code, codes in grants.items():
        rid = bind.execute(sa.select(roles.c.id).where(roles.c.code == role_code)).scalar()
        if rid is None:
            continue
        for code in codes:
            exists = bind.execute(sa.select(role_permissions.c.role_id).where(role_permissions.c.role_id == rid, role_permissions.c.permission_id == pids[code])).scalar()
            if exists is None:
                bind.execute(role_permissions.insert().values(role_id=rid, permission_id=pids[code]))


def downgrade():
    op.drop_table("lease_modifications")
    op.drop_table("financial_disclosure_notes")
    op.drop_table("financial_report_runs")
    op.drop_table("financial_statement_mappings")
