"""food safety HACCP recall and access governance rc5

Revision ID: e13000000001
Revises: e12000000001
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = "e13000000001"
down_revision = "e12000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "haccp_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False, index=True),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("product_item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("process_scope", sa.Text(), nullable=False),
        sa.Column("intended_use", sa.Text()),
        sa.Column("target_consumer", sa.String(250)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", name="uq_haccp_plan_company_code"),
    )
    op.create_table(
        "haccp_hazards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("haccp_plans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("process_step", sa.String(250), nullable=False),
        sa.Column("hazard_type", sa.String(20), nullable=False),
        sa.Column("hazard_description", sa.Text(), nullable=False),
        sa.Column("likelihood", sa.Integer(), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("significant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preventive_controls", sa.Text(), nullable=False),
        sa.Column("is_ccp", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("critical_limit", sa.String(250)),
        sa.Column("monitoring_method", sa.Text()),
        sa.Column("monitoring_frequency", sa.String(100)),
        sa.Column("corrective_action", sa.Text()),
        sa.Column("verification_method", sa.Text()),
        sa.Column("records_required", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("plan_id", "step_number", "hazard_type", name="uq_haccp_hazard_step_type"),
    )
    op.create_table(
        "haccp_monitoring_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("hazard_id", sa.Integer(), sa.ForeignKey("haccp_hazards.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("monitored_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("measured_value", sa.String(100), nullable=False),
        sa.Column("within_critical_limit", sa.Boolean(), nullable=False),
        sa.Column("deviation_details", sa.Text()),
        sa.Column("immediate_correction", sa.Text()),
        sa.Column("corrective_action_id", sa.Integer(), sa.ForeignKey("quality_actions.id")),
        sa.Column("status", sa.String(20), nullable=False, server_default="RECORDED", index=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("verified_at", sa.DateTime()),
    )
    op.create_table(
        "certificates_of_analysis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("lot_number", sa.String(80), nullable=False, index=True),
        sa.Column("issue_date", sa.Date(), nullable=False, index=True),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("specification_version", sa.String(50), nullable=False),
        sa.Column("test_results_json", sa.Text(), nullable=False),
        sa.Column("conclusion", sa.String(20), nullable=False, server_default="PASS"),
        sa.Column("remarks", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_coa_company_number"),
    )
    op.create_table(
        "product_recalls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True),
        sa.Column("recall_date", sa.Date(), nullable=False, index=True),
        sa.Column("recall_class", sa.String(20), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("lot_number", sa.String(80), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("quantity_distributed", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("quantity_recovered", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("quantity_disposed", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("effectiveness_percent", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT", index=True),
        sa.Column("initiated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("closed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("closed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_recall_company_number"),
    )
    op.create_table(
        "product_recall_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recall_id", sa.Integer(), sa.ForeignKey("product_recalls.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id")),
        sa.Column("location", sa.String(250), nullable=False),
        sa.Column("quantity_distributed", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("quantity_recovered", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("contact_status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("evidence_reference", sa.String(250)),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "sod_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(60), nullable=False, index=True),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("permission_a", sa.String(100), nullable=False),
        sa.Column("permission_b", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="HIGH"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("code", name="uq_sod_rule_code"),
    )
    op.create_table(
        "sod_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("sod_rules.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN", index=True),
        sa.Column("mitigating_control", sa.Text()),
        sa.Column("remediation_due_date", sa.Date()),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "user_id", "rule_id", "status", name="uq_sod_conflict_open_state"),
    )
    op.create_table(
        "access_review_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False, server_default="ALL_USERS"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_access_review_company_number"),
    )
    op.create_table(
        "access_review_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("access_review_campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("membership_id", sa.Integer(), sa.ForeignKey("user_company_roles.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(20), nullable=False, server_default="PENDING", index=True),
        sa.Column("reviewer_notes", sa.Text()),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.UniqueConstraint("campaign_id", "membership_id", name="uq_access_review_membership"),
    )

    bind = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=bind)
    roles = sa.Table("roles", meta, autoload_with=bind)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=bind)
    defs = {
        "food_safety.read": ("عرض سلامة الغذاء وHACCP", "View food safety and HACCP"),
        "food_safety.manage": ("إدارة سلامة الغذاء وHACCP", "Manage food safety and HACCP"),
        "food_safety.approve": ("اعتماد خطط HACCP وCOA والاستدعاء", "Approve HACCP, COA and recalls"),
        "access.review": ("مراجعة الصلاحيات وفصل المهام", "Review access and segregation of duties"),
        "access.manage": ("إدارة مراجعات الصلاحيات وفصل المهام", "Manage access reviews and SoD"),
        "access.approve": ("اعتماد مراجعات الصلاحيات", "Approve access reviews"),
    }
    pids = {}
    for code, (ar, en) in defs.items():
        pid = bind.execute(sa.select(permissions.c.id).where(permissions.c.code == code)).scalar()
        if pid is None:
            result = bind.execute(permissions.insert().values(code=code, name_ar=ar, name_en=en))
            pid = result.inserted_primary_key[0]
        pids[code] = pid
    grants = {
        "QUALITY_MANAGER": ["food_safety.read", "food_safety.manage", "food_safety.approve"],
        "AUDITOR": ["food_safety.read", "access.review", "access.approve"],
        "IT_MANAGER": ["access.review", "access.manage"],
        "CFO": ["food_safety.read", "access.review", "access.approve"],
        "FINANCIAL_CONTROLLER": ["access.review"],
    }
    for role_code, codes in grants.items():
        rid = bind.execute(sa.select(roles.c.id).where(roles.c.code == role_code)).scalar()
        if rid is None: continue
        for code in codes:
            exists = bind.execute(sa.select(role_permissions.c.role_id).where(role_permissions.c.role_id == rid, role_permissions.c.permission_id == pids[code])).scalar()
            if exists is None:
                bind.execute(role_permissions.insert().values(role_id=rid, permission_id=pids[code]))

    sod_rules = sa.Table("sod_rules", meta, autoload_with=bind)
    defaults = [
        ("JE_CREATE_APPROVE", "إنشاء واعتماد القيود", "Journal creation and approval", "journals.create", "journals.approve", "CRITICAL", "No user should prepare and approve the same class of journal entries."),
        ("JE_CREATE_POST", "إنشاء وترحيل القيود", "Journal creation and posting", "journals.create", "journals.post", "HIGH", "Journal preparers should not independently post entries."),
        ("PAYROLL_MANAGE_PAY", "إدارة وصرف الرواتب", "Payroll preparation and payment", "payroll.manage", "payroll.pay", "CRITICAL", "Payroll preparation and cash disbursement must be separated."),
        ("BUDGET_MANAGE_APPROVE", "إعداد واعتماد الموازنة", "Budget preparation and approval", "budget.manage", "budget.approve", "HIGH", "Budget preparers should not approve their own budgets."),
        ("ACCESS_MANAGE_APPROVE", "إدارة واعتماد الصلاحيات", "Access management and approval", "access.manage", "access.approve", "CRITICAL", "Access provisioning and certification approval must be separated."),
    ]
    for code, ar, en, pa, pb, sev, rationale in defaults:
        if bind.execute(sa.select(sod_rules.c.id).where(sod_rules.c.code == code)).scalar() is None:
            bind.execute(sod_rules.insert().values(code=code, name_ar=ar, name_en=en, permission_a=pa, permission_b=pb, severity=sev, rationale=rationale, active=True, created_at=datetime.now(timezone.utc).replace(tzinfo=None)))


def downgrade():
    op.drop_table("access_review_items")
    op.drop_table("access_review_campaigns")
    op.drop_table("sod_conflicts")
    op.drop_table("sod_rules")
    op.drop_table("product_recall_lines")
    op.drop_table("product_recalls")
    op.drop_table("certificates_of_analysis")
    op.drop_table("haccp_monitoring_logs")
    op.drop_table("haccp_hazards")
    op.drop_table("haccp_plans")
