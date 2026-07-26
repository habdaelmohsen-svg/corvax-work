"""governance assurance and ITSM v1.0

Revision ID: e10000000001
Revises: e32000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e10000000001"
down_revision = "e32000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "governance_risks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="OPERATIONAL"),
        sa.Column("likelihood", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("impact", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("inherent_score", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("residual_score", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(25), nullable=False, server_default="OPEN"),
        sa.Column("mitigation_due_date", sa.Date()),
        sa.Column("description", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_governance_risk_company_code"),
    )
    op.create_index("ix_governance_risks_company_id", "governance_risks", ["company_id"])
    op.create_index("ix_governance_risks_code", "governance_risks", ["code"])
    op.create_index("ix_governance_risks_status", "governance_risks", ["status"])

    op.create_table(
        "governance_controls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_id", sa.Integer(), sa.ForeignKey("governance_risks.id", ondelete="SET NULL")),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("control_type", sa.String(30), nullable=False, server_default="PREVENTIVE"),
        sa.Column("frequency", sa.String(30), nullable=False, server_default="MONTHLY"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("design_status", sa.String(25), nullable=False, server_default="EFFECTIVE"),
        sa.Column("operating_status", sa.String(25), nullable=False, server_default="NOT_TESTED"),
        sa.Column("last_test_date", sa.Date()),
        sa.Column("next_test_date", sa.Date()),
        sa.Column("description", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_governance_control_company_code"),
    )
    op.create_index("ix_governance_controls_company_id", "governance_controls", ["company_id"])
    op.create_index("ix_governance_controls_risk_id", "governance_controls", ["risk_id"])
    op.create_index("ix_governance_controls_code", "governance_controls", ["code"])

    op.create_table(
        "audit_engagements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("audit_type", sa.String(30), nullable=False, server_default="INTERNAL"),
        sa.Column("scope", sa.Text()),
        sa.Column("status", sa.String(25), nullable=False, server_default="PLANNED"),
        sa.Column("risk_rating", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("planned_start", sa.Date()),
        sa.Column("planned_end", sa.Date()),
        sa.Column("actual_start", sa.Date()),
        sa.Column("actual_end", sa.Date()),
        sa.Column("lead_auditor_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_audit_engagement_company_code"),
    )
    op.create_index("ix_audit_engagements_company_id", "audit_engagements", ["company_id"])
    op.create_index("ix_audit_engagements_code", "audit_engagements", ["code"])
    op.create_index("ix_audit_engagements_status", "audit_engagements", ["status"])

    op.create_table(
        "audit_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text()),
        sa.Column("recommendation", sa.Text()),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(25), nullable=False, server_default="OPEN"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", name="uq_audit_finding_company_code"),
    )
    op.create_index("ix_audit_findings_company_id", "audit_findings", ["company_id"])
    op.create_index("ix_audit_findings_engagement_id", "audit_findings", ["engagement_id"])
    op.create_index("ix_audit_findings_code", "audit_findings", ["code"])
    op.create_index("ix_audit_findings_severity", "audit_findings", ["severity"])
    op.create_index("ix_audit_findings_status", "audit_findings", ["status"])

    op.create_table(
        "corrective_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(25), nullable=False, server_default="OPEN"),
        sa.Column("completion_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_reference", sa.String(500)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
    )
    op.create_index("ix_corrective_actions_company_id", "corrective_actions", ["company_id"])
    op.create_index("ix_corrective_actions_finding_id", "corrective_actions", ["finding_id"])
    op.create_index("ix_corrective_actions_status", "corrective_actions", ["status"])

    op.create_table(
        "controlled_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("document_type", sa.String(40), nullable=False, server_default="POLICY"),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("effective_date", sa.Date()),
        sa.Column("review_date", sa.Date()),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("content_summary", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", "version", name="uq_controlled_document_version"),
    )
    op.create_index("ix_controlled_documents_company_id", "controlled_documents", ["company_id"])
    op.create_index("ix_controlled_documents_code", "controlled_documents", ["code"])
    op.create_index("ix_controlled_documents_status", "controlled_documents", ["status"])

    op.create_table(
        "it_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_tag", sa.String(60), nullable=False),
        sa.Column("asset_type", sa.String(40), nullable=False),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("serial_number", sa.String(120)),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id")),
        sa.Column("assigned_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("purchase_date", sa.Date()),
        sa.Column("warranty_end", sa.Date()),
        sa.Column("status", sa.String(25), nullable=False, server_default="IN_SERVICE"),
        sa.Column("criticality", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "asset_tag", name="uq_it_asset_company_tag"),
    )
    op.create_index("ix_it_assets_company_id", "it_assets", ["company_id"])
    op.create_index("ix_it_assets_asset_tag", "it_assets", ["asset_tag"])
    op.create_index("ix_it_assets_status", "it_assets", ["status"])

    op.create_table(
        "service_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="GENERAL"),
        sa.Column("subject", sa.String(250), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(25), nullable=False, server_default="OPEN"),
        sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignee_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("due_at", sa.DateTime()),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("resolution", sa.Text()),
        sa.UniqueConstraint("company_id", "number", name="uq_service_ticket_company_number"),
    )
    op.create_index("ix_service_tickets_company_id", "service_tickets", ["company_id"])
    op.create_index("ix_service_tickets_number", "service_tickets", ["number"])
    op.create_index("ix_service_tickets_priority", "service_tickets", ["priority"])
    op.create_index("ix_service_tickets_status", "service_tickets", ["status"])

    op.create_table(
        "marketing_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False, server_default="DIGITAL"),
        sa.Column("budget", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("actual_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("status", sa.String(25), nullable=False, server_default="PLANNED"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_marketing_campaign_company_code"),
    )
    op.create_index("ix_marketing_campaigns_company_id", "marketing_campaigns", ["company_id"])
    op.create_index("ix_marketing_campaigns_code", "marketing_campaigns", ["code"])
    op.create_index("ix_marketing_campaigns_status", "marketing_campaigns", ["status"])

    op.create_table(
        "crm_leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("marketing_campaigns.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(60), nullable=False, server_default="DIRECT"),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(50)),
        sa.Column("status", sa.String(25), nullable=False, server_default="NEW"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("estimated_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("converted_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_crm_lead_company_number"),
    )
    op.create_index("ix_crm_leads_company_id", "crm_leads", ["company_id"])
    op.create_index("ix_crm_leads_number", "crm_leads", ["number"])
    op.create_index("ix_crm_leads_campaign_id", "crm_leads", ["campaign_id"])
    op.create_index("ix_crm_leads_status", "crm_leads", ["status"])

    op.create_table(
        "crm_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("crm_leads.id", ondelete="SET NULL")),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("marketing_campaigns.id", ondelete="SET NULL")),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("parties.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False, server_default="QUALIFICATION"),
        sa.Column("probability", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("expected_close_date", sa.Date()),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("loss_reason", sa.String(500)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_crm_opportunity_company_number"),
    )
    op.create_index("ix_crm_opportunities_company_id", "crm_opportunities", ["company_id"])
    op.create_index("ix_crm_opportunities_number", "crm_opportunities", ["number"])
    op.create_index("ix_crm_opportunities_lead_id", "crm_opportunities", ["lead_id"])
    op.create_index("ix_crm_opportunities_campaign_id", "crm_opportunities", ["campaign_id"])
    op.create_index("ix_crm_opportunities_stage", "crm_opportunities", ["stage"])

    permissions = [
        ("grc.read", "عرض المخاطر والضوابط والحوكمة", "View risk, controls and governance"),
        ("grc.manage", "إدارة المخاطر والضوابط والإجراءات التصحيحية", "Manage risks, controls and corrective actions"),
        ("audit.manage", "إدارة مهام وملاحظات المراجعة", "Manage audit engagements and findings"),
        ("documents.manage", "إدارة الوثائق والسياسات المضبوطة", "Manage controlled documents and policies"),
        ("itsm.read", "عرض الأصول التقنية وتذاكر الدعم", "View IT assets and service tickets"),
        ("itsm.manage", "إدارة الأصول التقنية وتذاكر الدعم", "Manage IT assets and service tickets"),
        ("crm.read", "عرض إدارة العملاء والتسويق", "View CRM and marketing"),
        ("crm.manage", "إدارة العملاء المحتملين والحملات والفرص", "Manage leads, campaigns and opportunities"),
    ]
    for code, ar, en in permissions:
        op.execute(sa.text(
            "INSERT INTO permissions (code, name_ar, name_en) "
            "SELECT :code, :ar, :en WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)"
        ).bindparams(code=code, ar=ar, en=en))

    roles = [
        ("IT_MANAGER", "مدير تقنية المعلومات", "IT Manager"),
        ("QUALITY_MANAGER", "مدير الجودة", "Quality Manager"),
        ("SALES_MANAGER", "مدير المبيعات والتسويق", "Sales and Marketing Manager"),
    ]
    for code, ar, en in roles:
        op.execute(sa.text(
            "INSERT INTO roles (code, name_ar, name_en) "
            "SELECT :code, :ar, :en WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = :code)"
        ).bindparams(code=code, ar=ar, en=en))

    role_permission_map = {
        "CFO": ["grc.read", "grc.manage", "audit.manage", "documents.manage", "itsm.read"],
        "AUDITOR": ["grc.read", "grc.manage", "audit.manage", "documents.manage", "itsm.read"],
        "ACCOUNTANT": ["grc.read", "itsm.read", "crm.read"],
        "IT_MANAGER": ["company.read", "masterdata.read", "audit.read", "itsm.read", "itsm.manage", "documents.manage"],
        "QUALITY_MANAGER": ["company.read", "masterdata.read", "quality.read", "quality.manage", "grc.read", "grc.manage", "documents.manage", "itsm.read"],
        "SALES_MANAGER": ["company.read", "masterdata.read", "inventory.read", "pos.read", "crm.read", "crm.manage"],
    }
    for role_code, permission_codes in role_permission_map.items():
        for permission_code in permission_codes:
            op.execute(sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = :permission_code "
                "WHERE r.code = :role_code AND NOT EXISTS ("
                "SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
            ).bindparams(role_code=role_code, permission_code=permission_code))


def downgrade():
    for table in [
        "crm_opportunities",
        "crm_leads",
        "marketing_campaigns",
        "service_tickets",
        "it_assets",
        "controlled_documents",
        "corrective_actions",
        "audit_findings",
        "audit_engagements",
        "governance_controls",
        "governance_risks",
    ]:
        op.drop_table(table)
    codes = "'grc.read','grc.manage','audit.manage','documents.manage','itsm.read','itsm.manage','crm.read','crm.manage'"
    op.execute(f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({codes}))")
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes})")
