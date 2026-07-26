"""Saudi withholding tax engine and monthly return RC22

Revision ID: e18300000001
Revises: e18200000001
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "e18300000001"
down_revision = "e18200000001"
branch_labels = None
depends_on = None

CATEGORIES = [
    ("MANAGEMENT_FEES", "أتعاب الإدارة", "Management fees", 20, "MANAGEMENT_FEES"),
    ("ROYALTIES", "الإتاوات", "Royalties", 15, "ROYALTIES"),
    ("DIVIDENDS", "توزيعات الأرباح", "Dividends", 5, "DIVIDENDS"),
    ("RENT", "الإيجار", "Rent", 5, "RENT"),
    ("INSURANCE", "التأمين وإعادة التأمين", "Insurance and reinsurance", 5, "INSURANCE_REINSURANCE"),
    ("LOAN_RETURNS", "عوائد القروض", "Loan returns", 5, "LOAN_RETURNS"),
    ("TECHNICAL_CONSULTING", "خدمات فنية واستشارية", "Technical and consulting services", 5, "TECHNICAL_CONSULTING"),
    ("AIR_SEA_FREIGHT", "تذاكر طيران وشحن جوي أو بحري", "Air tickets and air or sea freight", 5, "AIR_SEA_FREIGHT"),
    ("INTERNATIONAL_TELECOM", "اتصالات دولية", "International telecommunication services", 5, "INTERNATIONAL_TELECOM"),
    ("OTHER_KSA_SOURCE_SERVICES", "خدمات أخرى من مصدر في المملكة", "Other services from KSA sources", 15, "OTHER_SERVICES"),
    ("GOODS_PURCHASE", "شراء بضائع دون خدمات", "Pure purchase of goods", 0, "OUT_OF_SCOPE"),
    ("INTERNATIONAL_ROAMING", "تجوال دولي منفذ بالكامل خارج المملكة", "International roaming performed outside KSA", 0, "OUT_OF_SCOPE"),
]


def upgrade():
    op.create_table(
        "withholding_tax_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("statutory_rate", sa.Numeric(8,4), nullable=False, server_default="0"),
        sa.Column("income_type", sa.String(60), nullable=False),
        sa.Column("source_rule", sa.String(500)),
        sa.Column("system_code", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_wht_category_company_code"),
    )
    for col in ("company_id","code","income_type","active"):
        op.create_index(f"ix_withholding_tax_categories_{col}", "withholding_tax_categories", [col])

    op.create_table(
        "withholding_beneficiary_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_code", sa.String(3), nullable=False),
        sa.Column("tax_residency_country", sa.String(3), nullable=False),
        sa.Column("foreign_tax_id", sa.String(120)),
        sa.Column("non_resident", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("permanent_establishment_in_ksa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("related_party", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("beneficial_owner_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("treaty_country_code", sa.String(3)),
        sa.Column("residency_certificate_number", sa.String(150)),
        sa.Column("residency_certificate_expiry", sa.Date()),
        sa.Column("treaty_relief_approval_reference", sa.String(150)),
        sa.Column("treaty_relief_approval_expiry", sa.Date()),
        sa.Column("notes", sa.String(1000)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "party_id", name="uq_wht_beneficiary_company_party"),
    )
    for col in ("company_id","party_id","active"):
        op.create_index(f"ix_withholding_beneficiary_profiles_{col}", "withholding_beneficiary_profiles", [col])

    op.create_table(
        "withholding_tax_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("beneficiary_profile_id", sa.Integer(), sa.ForeignKey("withholding_beneficiary_profiles.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("withholding_tax_categories.id"), nullable=False),
        sa.Column("purchase_invoice_id", sa.Integer(), sa.ForeignKey("purchase_invoices.id")),
        sa.Column("debit_account_id", sa.Integer(), sa.ForeignKey("accounts.id")),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id"), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("statutory_rate", sa.Numeric(8,4), nullable=False),
        sa.Column("treaty_rate", sa.Numeric(8,4)),
        sa.Column("applied_rate", sa.Numeric(8,4), nullable=False),
        sa.Column("withholding_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("net_cash_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("gross_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dta_relief_method", sa.String(30), nullable=False, server_default="STATUTORY"),
        sa.Column("dta_reference", sa.String(200)),
        sa.Column("source_in_ksa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("reference", sa.String(150)),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), unique=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_wht_transaction_company_number"),
    )
    for col in ("company_id","number","payment_date","beneficiary_profile_id","category_id","purchase_invoice_id","debit_account_id","status"):
        op.create_index(f"ix_withholding_tax_transactions_{col}", "withholding_tax_transactions", [col])

    op.create_table(
        "withholding_tax_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("gross_payments", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("tax_withheld", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gl_withheld", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("reconciliation_difference", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("estimated_late_penalty", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("sadad_invoice_number", sa.String(120)),
        sa.Column("payment_reference", sa.String(150)),
        sa.Column("payment_date", sa.Date()),
        sa.Column("payment_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("paid_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("paid_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_start", "period_end", name="uq_wht_return_company_period"),
    )
    for col in ("company_id","number","period_start","period_end","status"):
        op.create_index(f"ix_withholding_tax_returns_{col}", "withholding_tax_returns", [col])

    op.create_table(
        "withholding_tax_return_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("return_id", sa.Integer(), sa.ForeignKey("withholding_tax_returns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("withholding_tax_categories.id"), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("return_id", "category_id", name="uq_wht_return_line_category"),
    )
    op.create_index("ix_withholding_tax_return_lines_return_id", "withholding_tax_return_lines", ["return_id"])
    op.create_index("ix_withholding_tax_return_lines_category_id", "withholding_tax_return_lines", ["category_id"])

    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("net_cash_amount", sa.Numeric(18,2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("withholding_tax_amount", sa.Numeric(18,2), nullable=False, server_default="0"))
    op.execute("update payments set net_cash_amount=amount where net_cash_amount=0")

    conn=op.get_bind()
    companies=[r[0] for r in conn.execute(sa.text("select id from companies")).fetchall()]
    for company_id in companies:
        parent=conn.execute(sa.text("select id from accounts where company_id=:c and code='210000'"),{"c":company_id}).scalar()
        exists=conn.execute(sa.text("select id from accounts where company_id=:c and code='218010'"),{"c":company_id}).scalar()
        if not exists:
            conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
              values(:c,'218010','ضريبة استقطاع مستحقة','Withholding Tax Payable','LIABILITY','CURRENT_LIABILITIES',:p,3,1,0,1)"""),{"c":company_id,"p":parent})
        for code,ar,en,rate,income_type in CATEGORIES:
            conn.execute(sa.text("""insert into withholding_tax_categories
              (company_id,code,name_ar,name_en,statutory_rate,income_type,source_rule,system_code,active,created_at)
              values(:c,:code,:ar,:en,:rate,:income_type,'Article 68 / Article 63 classification; validate source and treaty facts per transaction',1,1,CURRENT_TIMESTAMP)"""),
              {"c":company_id,"code":code,"ar":ar,"en":en,"rate":rate,"income_type":income_type})


def downgrade():
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("withholding_tax_amount")
        batch.drop_column("net_cash_amount")
    op.drop_table("withholding_tax_return_lines")
    op.drop_table("withholding_tax_returns")
    op.drop_table("withholding_tax_transactions")
    op.drop_table("withholding_beneficiary_profiles")
    op.drop_table("withholding_tax_categories")
