"""CORVAX RC24 Saudi zakat and corporate income tax engine.

Revision ID: e18500000001
Revises: e18400000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e18500000001"
down_revision = "e18400000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "zakat_taxpayer_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zakat_registration_number", sa.String(120)),
        sa.Column("cit_registration_number", sa.String(120)),
        sa.Column("return_basis", sa.String(30), nullable=False, server_default="MIXED"),
        sa.Column("saudi_gcc_ownership_percent", sa.Numeric(8,4), nullable=False, server_default="100"),
        sa.Column("non_saudi_ownership_percent", sa.Numeric(8,4), nullable=False, server_default="0"),
        sa.Column("zakat_rate_hijri", sa.Numeric(10,6), nullable=False, server_default="2.5"),
        sa.Column("hijri_year_days", sa.Integer(), nullable=False, server_default="354"),
        sa.Column("income_tax_rate", sa.Numeric(10,6), nullable=False, server_default="20"),
        sa.Column("tax_loss_utilization_cap_percent", sa.Numeric(10,6), nullable=False, server_default="25"),
        sa.Column("zakat_method", sa.String(50), nullable=False, server_default="FINANCING_SOURCES_LESS_DEDUCTIBLE_ASSETS"),
        sa.Column("minimum_zakat_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", name="uq_zakat_taxpayer_profile_company"),
    )
    op.create_index("ix_zakat_taxpayer_profiles_company_id", "zakat_taxpayer_profiles", ["company_id"])
    op.create_index("ix_zakat_taxpayer_profiles_active", "zakat_taxpayer_profiles", ["active"])

    op.create_table(
        "tax_loss_carryforwards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin_year", sa.Integer(), nullable=False),
        sa.Column("original_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("utilized_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("expired_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="AVAILABLE"),
        sa.Column("evidence_reference", sa.String(250)),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "origin_year", name="uq_tax_loss_company_year"),
    )
    for col in ("company_id","origin_year","status"):
        op.create_index(f"ix_tax_loss_carryforwards_{col}", "tax_loss_carryforwards", [col])

    op.create_table(
        "zakat_income_tax_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("calculation_status", sa.String(50), nullable=False, server_default="PREPARATION_REVIEW_REQUIRED"),
        sa.Column("fiscal_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("accounting_profit_before_zakat_tax", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("cit_additions", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("cit_deductions", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("adjusted_taxable_profit", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("non_saudi_ownership_percent", sa.Numeric(8,4), nullable=False, server_default="0"),
        sa.Column("cit_base_before_losses", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("tax_losses_utilized", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("income_tax_base", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("income_tax_rate", sa.Numeric(10,6), nullable=False, server_default="20"),
        sa.Column("gross_income_tax", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("cit_credits", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("income_tax_payable", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gl_equity_balance", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gl_non_current_liabilities", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gl_deductible_non_current_assets", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("zakat_additions", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("zakat_deductions", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gross_zakat_base", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("saudi_gcc_ownership_percent", sa.Numeric(8,4), nullable=False, server_default="100"),
        sa.Column("zakat_base", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("zakat_rate", sa.Numeric(10,6), nullable=False, server_default="0"),
        sa.Column("gross_zakat", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("zakat_credits", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("zakat_payable", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("total_gross_charge", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("total_credits", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("total_payable", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("gl_payable", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("reconciliation_difference", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("accrual_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("payment_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("sadad_invoice_number", sa.String(120)),
        sa.Column("payment_reference", sa.String(150)),
        sa.Column("payment_date", sa.Date()),
        sa.Column("notes", sa.String(1500)),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("paid_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("paid_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_start", "period_end", name="uq_zakat_income_tax_return_period"),
    )
    for col in ("company_id","number","period_start","period_end","status"):
        op.create_index(f"ix_zakat_income_tax_returns_{col}", "zakat_income_tax_returns", [col])

    op.create_table(
        "zakat_tax_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("return_id", sa.Integer(), sa.ForeignKey("zakat_income_tax_returns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("regime", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("description_ar", sa.String(500), nullable=False),
        sa.Column("description_en", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(18,2), nullable=False),
        sa.Column("source_account_code", sa.String(30)),
        sa.Column("evidence_reference", sa.String(250)),
        sa.Column("recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("return_id","regime","direction","code"):
        op.create_index(f"ix_zakat_tax_adjustments_{col}", "zakat_tax_adjustments", [col])

    op.create_table(
        "tax_loss_utilizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("return_id", sa.Integer(), sa.ForeignKey("zakat_income_tax_returns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("loss_id", sa.Integer(), sa.ForeignKey("tax_loss_carryforwards.id"), nullable=False),
        sa.Column("amount", sa.Numeric(18,2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("return_id", "loss_id", name="uq_tax_loss_utilization_return_loss"),
    )
    op.create_index("ix_tax_loss_utilizations_return_id", "tax_loss_utilizations", ["return_id"])
    op.create_index("ix_tax_loss_utilizations_loss_id", "tax_loss_utilizations", ["loss_id"])

    conn = op.get_bind()
    company_ids = [r[0] for r in conn.execute(sa.text("select id from companies"))]
    for company_id in company_ids:
        current_parent = conn.execute(sa.text("select id from accounts where company_id=:c and code='210000'"), {"c": company_id}).scalar()
        asset_parent = conn.execute(sa.text("select id from accounts where company_id=:c and code='110000'"), {"c": company_id}).scalar()
        expense_parent = conn.execute(sa.text("select id from accounts where company_id=:c and code='800000'"), {"c": company_id}).scalar()
        specs = [
            ("218030","زكاة مستحقة","Zakat Payable","LIABILITY","CURRENT_LIABILITIES",current_parent),
            ("218040","ضريبة دخل مستحقة","Corporate Income Tax Payable","LIABILITY","CURRENT_LIABILITIES",current_parent),
            ("118020","دفعات زكاة وضريبة مقدمة","Zakat and Tax Prepayments","ASSET","OTHER_CURRENT_ASSETS",asset_parent),
            ("811020","مصروف ضريبة الدخل الحالية","Current Income Tax Expense","EXPENSE","ZAKAT_TAX",expense_parent),
        ]
        for code, ar, en, typ, group, parent in specs:
            if not conn.execute(sa.text("select id from accounts where company_id=:c and code=:code"), {"c": company_id, "code": code}).scalar():
                conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
                    values(:c,:code,:ar,:en,:typ,:grp,:parent,3,1,0,1)"""), {"c":company_id,"code":code,"ar":ar,"en":en,"typ":typ,"grp":group,"parent":parent})


def downgrade():
    conn = op.get_bind()
    for code in ("218030","218040","118020","811020"):
        conn.execute(sa.text("delete from accounts where code=:code"), {"code": code})
    op.drop_index("ix_tax_loss_utilizations_loss_id", table_name="tax_loss_utilizations")
    op.drop_index("ix_tax_loss_utilizations_return_id", table_name="tax_loss_utilizations")
    op.drop_table("tax_loss_utilizations")
    for col in ("return_id","regime","direction","code"):
        op.drop_index(f"ix_zakat_tax_adjustments_{col}", table_name="zakat_tax_adjustments")
    op.drop_table("zakat_tax_adjustments")
    for col in ("company_id","number","period_start","period_end","status"):
        op.drop_index(f"ix_zakat_income_tax_returns_{col}", table_name="zakat_income_tax_returns")
    op.drop_table("zakat_income_tax_returns")
    for col in ("company_id","origin_year","status"):
        op.drop_index(f"ix_tax_loss_carryforwards_{col}", table_name="tax_loss_carryforwards")
    op.drop_table("tax_loss_carryforwards")
    op.drop_index("ix_zakat_taxpayer_profiles_active", table_name="zakat_taxpayer_profiles")
    op.drop_index("ix_zakat_taxpayer_profiles_company_id", table_name="zakat_taxpayer_profiles")
    op.drop_table("zakat_taxpayer_profiles")
