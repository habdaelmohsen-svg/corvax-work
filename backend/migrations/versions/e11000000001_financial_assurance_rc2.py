"""financial assurance and certification rc2

Revision ID: e11000000001
Revises: e10000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e11000000001"
down_revision = "e10000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_assurance_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("fiscal_period_id", sa.Integer(), sa.ForeignKey("fiscal_periods.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("scope", sa.String(30), nullable=False, server_default="MONTH_END"),
        sa.Column("materiality_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("performance_materiality", sa.Numeric(18, 2), nullable=False),
        sa.Column("trivial_threshold", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("conclusion", sa.String(30), nullable=False, server_default="NOT_ASSESSED"),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("management_representation", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "fiscal_period_id", "scope", name="uq_assurance_company_period_scope"),
    )
    op.create_table(
        "financial_assurance_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assurance_run_id", sa.Integer(), sa.ForeignKey("financial_assurance_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metric_value", sa.Numeric(18, 2)),
        sa.Column("threshold_value", sa.Numeric(18, 2)),
        sa.Column("details", sa.Text()),
        sa.Column("remediation_owner_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("remediation_due_date", sa.Date()),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("assurance_run_id", "code", name="uq_assurance_check_code"),
    )
    op.create_table(
        "financial_certifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assurance_run_id", sa.Integer(), sa.ForeignKey("financial_assurance_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("certification_role", sa.String(40), nullable=False),
        sa.Column("certification_status", sa.String(25), nullable=False, server_default="PENDING"),
        sa.Column("statement_ar", sa.Text(), nullable=False),
        sa.Column("statement_en", sa.Text(), nullable=False),
        sa.Column("exceptions", sa.Text()),
        sa.Column("certified_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("certified_at", sa.DateTime()),
        sa.UniqueConstraint("assurance_run_id", "certification_role", name="uq_assurance_certification_role"),
    )

    bind = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=bind)
    roles = sa.Table("roles", meta, autoload_with=bind)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=bind)

    permission_defs = {
        "assurance.read": ("عرض ملف التأكيد المالي والرقابي", "View financial assurance file"),
        "assurance.review": ("إعداد ومراجعة ملف التأكيد المالي", "Prepare and review financial assurance file"),
        "assurance.approve": ("اعتماد الإقرارات المالية والرقابية", "Approve financial and control certifications"),
    }
    permission_ids = {}
    for code, (name_ar, name_en) in permission_defs.items():
        existing = bind.execute(sa.select(permissions.c.id).where(permissions.c.code == code)).scalar()
        if existing is None:
            result = bind.execute(permissions.insert().values(code=code, name_ar=name_ar, name_en=name_en))
            existing = result.inserted_primary_key[0]
        permission_ids[code] = existing

    role_id = bind.execute(sa.select(roles.c.id).where(roles.c.code == "FINANCIAL_CONTROLLER")).scalar()
    if role_id is None:
        result = bind.execute(roles.insert().values(code="FINANCIAL_CONTROLLER", name_ar="المراقب المالي", name_en="Financial Controller"))
        role_id = result.inserted_primary_key[0]

    grants = {
        "FINANCIAL_CONTROLLER": ["assurance.read", "assurance.review", "assurance.approve"],
        "CFO": ["assurance.read", "assurance.review", "assurance.approve"],
        "ACCOUNTANT": ["assurance.read", "assurance.review"],
        "AUDITOR": ["assurance.read", "assurance.approve"],
    }
    for role_code, permission_codes in grants.items():
        rid = bind.execute(sa.select(roles.c.id).where(roles.c.code == role_code)).scalar()
        if rid is None:
            continue
        for permission_code in permission_codes:
            pid = permission_ids[permission_code]
            exists = bind.execute(
                sa.select(role_permissions.c.role_id).where(
                    role_permissions.c.role_id == rid, role_permissions.c.permission_id == pid
                )
            ).scalar()
            if exists is None:
                bind.execute(role_permissions.insert().values(role_id=rid, permission_id=pid))


def downgrade():
    op.drop_table("financial_certifications")
    op.drop_table("financial_assurance_checks")
    op.drop_table("financial_assurance_runs")
