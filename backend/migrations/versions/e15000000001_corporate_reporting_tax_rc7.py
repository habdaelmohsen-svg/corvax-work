"""corporate reporting tax impairment and segment disclosures rc7

Revision ID: e15000000001
Revises: e14000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e15000000001"
down_revision = "e14000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "corporate_finance_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("deferred_tax_asset_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("deferred_tax_liability_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("deferred_tax_expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("deferred_tax_oci_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("impairment_expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("accumulated_impairment_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("configured_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
    )
    op.create_table(
        "deferred_tax_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("default_tax_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("total_recognized_dta", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_recognized_dtl", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_unrecognized_dta", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("net_deferred_tax_position", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_end", "version", name="uq_deferred_tax_run_period_version"),
    )
    op.create_table(
        "deferred_tax_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("deferred_tax_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("description_ar", sa.String(500), nullable=False),
        sa.Column("description_en", sa.String(500), nullable=False),
        sa.Column("source_account_id", sa.Integer(), sa.ForeignKey("accounts.id")),
        sa.Column("carrying_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_base", sa.Numeric(18, 2), nullable=False),
        sa.Column("temporary_difference", sa.Numeric(18, 2), nullable=False),
        sa.Column("difference_type", sa.String(20), nullable=False),
        sa.Column("tax_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("tax_effect", sa.Numeric(18, 2), nullable=False),
        sa.Column("recognition_status", sa.String(20), nullable=False, server_default="RECOGNIZED"),
        sa.Column("presentation_basis", sa.String(20), nullable=False, server_default="PNL"),
        sa.Column("recoverability_evidence", sa.Text()),
        sa.UniqueConstraint("run_id", "reference", name="uq_deferred_tax_item_reference"),
    )
    op.create_table(
        "goodwill_impairment_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("cgu_code", sa.String(50), nullable=False),
        sa.Column("cgu_name_ar", sa.String(250), nullable=False),
        sa.Column("cgu_name_en", sa.String(250), nullable=False),
        sa.Column("goodwill_carrying_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("other_assets_carrying_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("value_in_use", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("fair_value_less_costs", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("recoverable_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("impairment_loss", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("goodwill_impairment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("other_asset_impairment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("assumptions_payload", sa.Text(), nullable=False),
        sa.Column("sensitivity_payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_end", "cgu_code", name="uq_goodwill_test_company_period_cgu"),
    )
    op.create_table(
        "foreign_operation_translation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("functional_currency", sa.String(3), nullable=False),
        sa.Column("reporting_currency", sa.String(3), nullable=False),
        sa.Column("closing_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("average_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("historical_equity_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("foreign_assets", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("foreign_liabilities", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("foreign_equity", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("foreign_revenue", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("foreign_expenses", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("translated_net_assets", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("translated_equity", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("translated_profit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("cta_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("group_id", "member_company_id", "period_end", name="uq_translation_group_member_period"),
    )
    op.create_table(
        "management_performance_measures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("explanation_ar", sa.Text(), nullable=False),
        sa.Column("explanation_en", sa.Text(), nullable=False),
        sa.Column("base_report_run_id", sa.Integer(), sa.ForeignKey("financial_report_runs.id"), nullable=False),
        sa.Column("base_subtotal_code", sa.String(80), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("adjustments_payload", sa.Text(), nullable=False),
        sa.Column("total_adjustments", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_effect", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("nci_effect", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("measure_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_end", "code", name="uq_mpm_company_period_code"),
    )
    op.create_table(
        "earnings_per_share_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("profit_attributable", sa.Numeric(18, 2), nullable=False),
        sa.Column("preference_dividends", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("weighted_average_shares", sa.Numeric(18, 4), nullable=False),
        sa.Column("diluted_profit_adjustment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("incremental_shares", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("basic_eps", sa.Numeric(18, 6), nullable=False),
        sa.Column("diluted_eps", sa.Numeric(18, 6), nullable=False),
        sa.Column("anti_dilutive_excluded", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("support_reference", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_end", "version", name="uq_eps_company_period_version"),
    )
    op.create_table(
        "operating_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("codm_title", sa.String(250), nullable=False),
        sa.Column("reportable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", name="uq_operating_segment_company_code"),
    )
    op.create_table(
        "segment_report_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("base_report_run_id", sa.Integer(), sa.ForeignKey("financial_report_runs.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("reconciliation_payload", sa.Text(), nullable=False),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_end", "version", name="uq_segment_report_company_period_version"),
    )
    op.create_table(
        "segment_report_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("segment_report_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("segment_id", sa.Integer(), sa.ForeignKey("operating_segments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("external_revenue", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("intersegment_revenue", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("segment_profit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("segment_assets", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("segment_liabilities", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("measurement_basis", sa.String(500), nullable=False),
        sa.UniqueConstraint("run_id", "segment_id", name="uq_segment_report_line_segment"),
    )

    bind = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=bind)
    roles = sa.Table("roles", meta, autoload_with=bind)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=bind)
    companies = sa.Table("companies", meta, autoload_with=bind)
    accounts = sa.Table("accounts", meta, autoload_with=bind)

    defs = {
        "finance.corporate.read": ("عرض التقارير المؤسسية والضريبة المؤجلة", "View corporate reporting and deferred tax"),
        "finance.corporate.manage": ("إعداد التقارير المؤسسية والضريبة المؤجلة", "Prepare corporate reporting and deferred tax"),
        "finance.corporate.review": ("مراجعة التقارير المؤسسية والضريبة المؤجلة", "Review corporate reporting and deferred tax"),
        "finance.corporate.approve": ("اعتماد وترحيل التقارير المؤسسية والضريبة المؤجلة", "Approve and post corporate reporting and deferred tax"),
    }
    pids = {}
    for code, (ar, en) in defs.items():
        pid = bind.execute(sa.select(permissions.c.id).where(permissions.c.code == code)).scalar()
        if pid is None:
            result = bind.execute(permissions.insert().values(code=code, name_ar=ar, name_en=en))
            pid = result.inserted_primary_key[0]
        pids[code] = pid
    grants = {
        "ACCOUNTANT": ["finance.corporate.read", "finance.corporate.manage"],
        "FINANCIAL_CONTROLLER": list(defs),
        "CFO": list(defs),
        "AUDITOR": ["finance.corporate.read", "finance.corporate.review", "finance.corporate.approve"],
    }
    for role_code, codes in grants.items():
        rid = bind.execute(sa.select(roles.c.id).where(roles.c.code == role_code)).scalar()
        if rid is None:
            continue
        for code in codes:
            exists = bind.execute(sa.select(role_permissions.c.role_id).where(role_permissions.c.role_id == rid, role_permissions.c.permission_id == pids[code])).scalar()
            if exists is None:
                bind.execute(role_permissions.insert().values(role_id=rid, permission_id=pids[code]))

    account_specs = [
        ("154010", "أصل ضريبة مؤجلة", "Deferred Tax Asset", "ASSET", "NON_CURRENT_ASSETS", "150000", 3),
        ("154020", "الشهرة", "Goodwill", "ASSET", "NON_CURRENT_ASSETS", "150000", 3),
        ("154030", "مجمع خسائر انخفاض القيمة", "Accumulated Impairment Losses", "ASSET", "ACCUMULATED_DEPRECIATION", "150000", 3),
        ("223010", "التزام ضريبة مؤجلة", "Deferred Tax Liability", "LIABILITY", "NON_CURRENT_LIABILITIES", "220000", 3),
        ("313010", "احتياطي فروق ترجمة العملات", "Foreign Currency Translation Reserve", "EQUITY", "EQUITY", "300000", 2),
        ("313020", "الأثر الضريبي لبنود الدخل الشامل الآخر", "Tax Effects in Other Comprehensive Income", "EQUITY", "EQUITY", "300000", 2),
        ("620010", "خسائر انخفاض القيمة", "Impairment Losses", "EXPENSE", "OPERATING_EXPENSES", "600000", 2),
        ("812010", "مصروف الضريبة المؤجلة", "Deferred Tax Expense", "EXPENSE", "ZAKAT_TAX", "800000", 2),
    ]
    company_ids = [row[0] for row in bind.execute(sa.select(companies.c.id)).all()]
    for company_id in company_ids:
        by_code = {r[1]: r[0] for r in bind.execute(sa.select(accounts.c.id, accounts.c.code).where(accounts.c.company_id == company_id)).all()}
        for code, ar, en, account_type, group, parent_code, level in account_specs:
            if code in by_code:
                continue
            result = bind.execute(accounts.insert().values(
                company_id=company_id, code=code, name_ar=ar, name_en=en,
                account_type=account_type, statement_group=group,
                parent_id=by_code.get(parent_code), level=level,
                is_postable=True, is_cash=False, active=True,
            ))
            by_code[code] = result.inserted_primary_key[0]


def downgrade():
    op.drop_table("segment_report_lines")
    op.drop_table("segment_report_runs")
    op.drop_table("operating_segments")
    op.drop_table("earnings_per_share_runs")
    op.drop_table("management_performance_measures")
    op.drop_table("foreign_operation_translation_runs")
    op.drop_table("goodwill_impairment_tests")
    op.drop_table("deferred_tax_items")
    op.drop_table("deferred_tax_runs")
    op.drop_table("corporate_finance_configs")
