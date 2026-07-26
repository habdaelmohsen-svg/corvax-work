"""CORVAX RC27.4 H13 - CIP projects, contracts, progress certificates + central attachments.

Adds GL accounts for every company:
  * 155010 - مشروعات تحت التنفيذ / Construction in Progress   (ASSET, non-current)
  * 217040 - مستحق لمقاولين / Contractors Payable             (LIABILITY)
  * 217050 - محتجز ضمان مقاولين / Contractor Retention Payable (LIABILITY)

Revision chain: follows the H12 head e19200000001.
"""
from alembic import op
import sqlalchemy as sa


revision = "e19300000001"
down_revision = "e19200000001"
branch_labels = None
depends_on = None


CIP_ACCOUNTS = [
    ("155010", "مشروعات تحت التنفيذ", "Construction in Progress", "ASSET", "NON_CURRENT_ASSETS", "150000"),
    ("217040", "مستحق لمقاولين", "Contractors Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000"),
    ("217050", "محتجز ضمان مقاولين", "Contractor Retention Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000"),
]


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=False, index=True),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_kind", sa.String(20), nullable=False, server_default="DB"),
        sa.Column("content", sa.LargeBinary()),
        sa.Column("external_url", sa.String(600)),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("description_ar", sa.String(300)),
        sa.Column("description_en", sa.String(300)),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cip_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("budget_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date()),
        sa.Column("expected_completion_date", sa.Date()),
        sa.Column("ready_for_use_date", sa.Date()),
        sa.Column("capitalized_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("expensed_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNING", index=True),
        sa.Column("fixed_asset_id", sa.Integer(), sa.ForeignKey("fixed_assets.id")),
        sa.Column("capitalization_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id")),
        sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "code", name="uq_cip_project_company_code"),
    )
    op.create_table(
        "cip_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("cip_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False, index=True),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("contract_type", sa.String(30), nullable=False, server_default="CONTRACTOR"),
        sa.Column("contract_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_rate", sa.Numeric(6, 2), nullable=False, server_default="15"),
        sa.Column("retention_rate", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("warranty_end_date", sa.Date()),
        sa.Column("signed_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cip_progress_certificates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("cip_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("certificate_date", sa.Date(), nullable=False),
        sa.Column("work_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("retention_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("net_payable", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("supplier_invoice_number", sa.String(80)),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cip_costs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("cip_projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("cost_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("treatment", sa.String(20), nullable=False, server_default="CAPITALIZE"),
        sa.Column("description_ar", sa.String(300), nullable=False),
        sa.Column("description_en", sa.String(300)),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id")),
        sa.Column("expense_account_code", sa.String(30)),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("warning_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cip_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("cip_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("certificate_id", sa.Integer(), sa.ForeignKey("cip_progress_certificates.id")),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("payment_kind", sa.String(20), nullable=False, server_default="CERTIFICATE"),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id"), nullable=False),
        sa.Column("reference", sa.String(120)),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Ensure CIP GL accounts exist for every company.
    conn = op.get_bind()
    companies = [row[0] for row in conn.execute(sa.text("SELECT id FROM companies"))]
    for company_id in companies:
        for code, name_ar, name_en, acc_type, group, parent_code in CIP_ACCOUNTS:
            exists = conn.execute(
                sa.text("SELECT 1 FROM accounts WHERE company_id = :cid AND code = :code"),
                {"cid": company_id, "code": code},
            ).first()
            if exists:
                continue
            parent = conn.execute(
                sa.text("SELECT id FROM accounts WHERE company_id = :cid AND code = :pcode"),
                {"cid": company_id, "pcode": parent_code},
            ).first()
            conn.execute(
                sa.text(
                    "INSERT INTO accounts (company_id, code, name_ar, name_en, account_type, statement_group, parent_id, level, is_postable, is_cash, active) "
                    "VALUES (:cid, :code, :nar, :nen, :atype, :grp, :pid, 3, true, false, true)"
                ),
                {"cid": company_id, "code": code, "nar": name_ar, "nen": name_en,
                 "atype": acc_type, "grp": group, "pid": parent[0] if parent else None},
            )


def downgrade() -> None:
    for table in ("cip_payments", "cip_costs", "cip_progress_certificates", "cip_contracts", "cip_projects", "attachments"):
        op.drop_table(table)
    conn = op.get_bind()
    for code, *_ in CIP_ACCOUNTS:
        conn.execute(sa.text("DELETE FROM accounts WHERE code = :code"), {"code": code})
