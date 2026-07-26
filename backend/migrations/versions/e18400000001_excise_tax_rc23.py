"""CORVAX RC23 Saudi excise tax, tax warehouses and bi-monthly return.

Revision ID: e18400000001
Revises: e18300000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e18400000001"
down_revision = "e18300000001"
branch_labels = None
depends_on = None

CATEGORIES = [
    ("SOFT_DRINK", "المشروبات الغازية", "Soft drinks", 50, "GCC excise category"),
    ("SWEETENED_BEVERAGE", "المشروبات المحلاة", "Sweetened beverages", 50, "GCC excise category"),
    ("ENERGY_DRINK", "مشروبات الطاقة", "Energy drinks", 100, "GCC excise category"),
    ("TOBACCO", "التبغ ومشتقاته", "Tobacco and derivatives", 100, "Chapter 24 / GCC tariff"),
    ("E_SMOKING_DEVICE", "أجهزة وأدوات التدخين الإلكتروني", "Electronic smoking devices and tools", 100, "GCC tariff schedule"),
    ("E_SMOKING_LIQUID", "سوائل التدخين الإلكتروني", "Electronic smoking liquids", 100, "GCC tariff schedule"),
]


def upgrade():
    op.create_table(
        "excise_tax_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("statutory_rate", sa.Numeric(8,4), nullable=False),
        sa.Column("tariff_reference", sa.String(120)),
        sa.Column("system_code", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_excise_category_company_code"),
    )
    for col in ("company_id","code","active"):
        op.create_index(f"ix_excise_tax_categories_{col}", "excise_tax_categories", [col])

    op.create_table(
        "excise_warehouse_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("license_number", sa.String(150), nullable=False),
        sa.Column("license_start_date", sa.Date(), nullable=False),
        sa.Column("license_expiry_date", sa.Date(), nullable=False),
        sa.Column("permitted_activities", sa.String(250), nullable=False, server_default="STORE"),
        sa.Column("bank_guarantee_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("estimated_monthly_excise_value", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "warehouse_id", name="uq_excise_warehouse_company_warehouse"),
    )
    for col in ("company_id","warehouse_id","status"):
        op.create_index(f"ix_excise_warehouse_profiles_{col}", "excise_warehouse_profiles", [col])

    op.create_table(
        "excise_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("excise_tax_categories.id"), nullable=False),
        sa.Column("hs_code", sa.String(30)),
        sa.Column("zatca_registration_reference", sa.String(150)),
        sa.Column("registered_retail_price", sa.Numeric(18,4), nullable=False, server_default="0"),
        sa.Column("indicative_price", sa.Numeric(18,4), nullable=False, server_default="0"),
        sa.Column("package_quantity", sa.Numeric(18,4), nullable=False, server_default="1"),
        sa.Column("package_uom", sa.String(20), nullable=False, server_default="EA"),
        sa.Column("tax_stamp_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "item_id", name="uq_excise_product_company_item"),
    )
    for col in ("company_id","item_id","category_id","active"):
        op.create_index(f"ix_excise_products_{col}", "excise_products", [col])

    op.create_table(
        "excise_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("excise_products.id"), nullable=False),
        sa.Column("warehouse_profile_id", sa.Integer(), sa.ForeignKey("excise_warehouse_profiles.id")),
        sa.Column("destination_warehouse_profile_id", sa.Integer(), sa.ForeignKey("excise_warehouse_profiles.id")),
        sa.Column("quantity", sa.Numeric(18,4), nullable=False),
        sa.Column("taxable_unit_value", sa.Numeric(18,4), nullable=False, server_default="0"),
        sa.Column("taxable_value", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("excise_rate", sa.Numeric(8,4), nullable=False, server_default="0"),
        sa.Column("excise_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("customs_declaration_number", sa.String(150)),
        sa.Column("customs_excise_paid", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("tax_settlement_method", sa.String(30), nullable=False, server_default="SUSPENDED"),
        sa.Column("debit_account_id", sa.Integer(), sa.ForeignKey("accounts.id")),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id")),
        sa.Column("reference", sa.String(150)),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_excise_movement_company_number"),
    )
    for col in ("company_id","number","movement_date","event_type","product_id","warehouse_profile_id","destination_warehouse_profile_id","status"):
        op.create_index(f"ix_excise_movements_{col}", "excise_movements", [col])

    op.create_table(
        "excise_tax_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("taxable_value", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gross_excise", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("customs_paid", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("tax_payable", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gl_payable", sa.Numeric(18,2), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("company_id", "period_start", "period_end", name="uq_excise_return_company_period"),
    )
    for col in ("company_id","number","period_start","period_end","status"):
        op.create_index(f"ix_excise_tax_returns_{col}", "excise_tax_returns", [col])

    op.create_table(
        "excise_tax_return_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("return_id", sa.Integer(), sa.ForeignKey("excise_tax_returns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("excise_tax_categories.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(18,4), nullable=False, server_default="0"),
        sa.Column("taxable_value", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gross_excise", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("customs_paid", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("tax_payable", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("movement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("return_id", "category_id", name="uq_excise_return_line_category"),
    )
    op.create_index("ix_excise_tax_return_lines_return_id", "excise_tax_return_lines", ["return_id"])
    op.create_index("ix_excise_tax_return_lines_category_id", "excise_tax_return_lines", ["category_id"])

    conn = op.get_bind()
    companies = [r[0] for r in conn.execute(sa.text("select id from companies")).fetchall()]
    for company_id in companies:
        liability_parent = conn.execute(sa.text("select id from accounts where company_id=:c and code='210000'"), {"c": company_id}).scalar()
        expense_parent = conn.execute(sa.text("select id from accounts where company_id=:c and code='620000'"), {"c": company_id}).scalar()
        if expense_parent is None:
            expense_parent = conn.execute(sa.text("select id from accounts where company_id=:c and code='600000'"), {"c": company_id}).scalar()
        if not conn.execute(sa.text("select id from accounts where company_id=:c and code='218020'"), {"c": company_id}).scalar():
            conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
              values(:c,'218020','ضريبة انتقائية مستحقة','Excise Tax Payable','LIABILITY','CURRENT_LIABILITIES',:p,3,1,0,1)"""), {"c": company_id, "p": liability_parent})
        if not conn.execute(sa.text("select id from accounts where company_id=:c and code='624120'"), {"c": company_id}).scalar():
            conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
              values(:c,'624120','مصروف الضريبة الانتقائية','Excise Tax Expense','EXPENSE','OTHER_EXPENSE',:p,3,1,0,1)"""), {"c": company_id, "p": expense_parent})
        for code, ar, en, rate, ref in CATEGORIES:
            conn.execute(sa.text("""insert into excise_tax_categories
              (company_id,code,name_ar,name_en,statutory_rate,tariff_reference,system_code,active,created_at)
              values(:c,:code,:ar,:en,:rate,:ref,1,1,CURRENT_TIMESTAMP)"""),
              {"c": company_id, "code": code, "ar": ar, "en": en, "rate": rate, "ref": ref})


def downgrade():
    op.drop_table("excise_tax_return_lines")
    op.drop_table("excise_tax_returns")
    op.drop_table("excise_movements")
    op.drop_table("excise_products")
    op.drop_table("excise_warehouse_profiles")
    op.drop_table("excise_tax_categories")
