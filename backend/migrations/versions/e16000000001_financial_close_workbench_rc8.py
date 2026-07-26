"""financial close workbench, IFRS 3 and lease scope reductions rc8

Revision ID: e16000000001
Revises: e15000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e16000000001"
down_revision = "e15000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consolidation_worksheets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("worksheet_type", sa.String(40), nullable=False, server_default="MANUAL_ADJUSTMENT"),
        sa.Column("reference", sa.String(120), nullable=False),
        sa.Column("description_ar", sa.String(500), nullable=False),
        sa.Column("description_en", sa.String(500), nullable=False),
        sa.Column("total_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("balance_difference", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(40), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("group_id", "period_end", "version", name="uq_consolidation_worksheet_group_period_version"),
    )
    op.create_table(
        "consolidation_worksheet_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("worksheet_id", sa.Integer(), sa.ForeignKey("consolidation_worksheets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("adjustment_type", sa.String(40), nullable=False),
        sa.Column("account_code", sa.String(60), nullable=False),
        sa.Column("description_ar", sa.String(500), nullable=False),
        sa.Column("description_en", sa.String(500), nullable=False),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.UniqueConstraint("worksheet_id", "line_number", name="uq_consolidation_worksheet_line_number"),
    )
    op.create_table(
        "business_combinations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("acquirer_company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("acquiree_company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("acquisition_date", sa.Date(), nullable=False, index=True),
        sa.Column("ownership_percent", sa.Numeric(9, 6), nullable=False),
        sa.Column("nci_measurement_method", sa.String(30), nullable=False, server_default="PROPORTIONATE_SHARE"),
        sa.Column("consideration_cash", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("consideration_shares", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("contingent_consideration", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("previously_held_interest_fv", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("nci_fair_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("identifiable_assets_fv", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("identifiable_liabilities_fv", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("deferred_tax_net_liability", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("identifiable_net_assets_fv", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("acquisition_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("goodwill", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("bargain_purchase_gain", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(40), nullable=False, server_default="DRAFT", index=True),
        sa.Column("rationale_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("worksheet_id", sa.Integer(), sa.ForeignKey("consolidation_worksheets.id", name="fk_business_combination_worksheet")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("group_id", "acquiree_company_id", "acquisition_date", name="uq_business_combination_group_acquiree_date"),
    )
    op.create_table(
        "purchase_price_allocation_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("combination_id", sa.Integer(), sa.ForeignKey("business_combinations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_code", sa.String(60), nullable=False),
        sa.Column("item_type", sa.String(30), nullable=False),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("book_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("fair_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_base", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("fair_value_adjustment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("deferred_tax_effect", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("useful_life_months", sa.Integer()),
        sa.Column("identifiable_intangible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_reference", sa.String(500), nullable=False),
        sa.UniqueConstraint("combination_id", "item_code", name="uq_ppa_item_combination_code"),
    )
    op.create_table(
        "lead_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("account_code_from", sa.String(30), nullable=False),
        sa.Column("account_code_to", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ledger_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("schedule_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("difference", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(40), nullable=False, server_default="DRAFT", index=True),
        sa.Column("conclusion_ar", sa.Text(), nullable=False, server_default=""),
        sa.Column("conclusion_en", sa.Text(), nullable=False, server_default=""),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "period_end", "code", "version", name="uq_lead_schedule_company_period_code_version"),
    )
    op.create_table(
        "lead_schedule_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("lead_schedules.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("reference", sa.String(120), nullable=False),
        sa.Column("description_ar", sa.String(500), nullable=False),
        sa.Column("description_en", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reconciling_item", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ageing_days", sa.Integer()),
        sa.Column("owner", sa.String(250)),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.UniqueConstraint("schedule_id", "reference", name="uq_lead_schedule_item_reference"),
    )
    op.create_table(
        "financial_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("lead_schedules.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("lead_schedule_items.id", ondelete="SET NULL"), index=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(700), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, index=True),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "lease_partial_terminations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lease_id", sa.Integer(), sa.ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=False, index=True),
        sa.Column("reduction_percent", sa.Numeric(9, 6), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("carrying_liability", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("carrying_rou_asset", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("liability_reduction", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("rou_reduction", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("gain_loss", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(40), nullable=False, server_default="DRAFT", index=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
    )

    # Upgrade existing company charts with dedicated IFRS 16 scope-decrease gain/loss accounts.
    bind = op.get_bind()
    accounts = sa.table(
        "accounts",
        sa.column("company_id", sa.Integer()), sa.column("code", sa.String()),
        sa.column("name_ar", sa.String()), sa.column("name_en", sa.String()),
        sa.column("account_type", sa.String()), sa.column("statement_group", sa.String()),
        sa.column("parent_id", sa.Integer()), sa.column("level", sa.Integer()),
        sa.column("is_postable", sa.Boolean()), sa.column("is_cash", sa.Boolean()), sa.column("active", sa.Boolean()),
    )
    companies = [row[0] for row in bind.execute(sa.text("SELECT id FROM companies")).fetchall()]
    for company_id in companies:
        existing = {row[0] for row in bind.execute(sa.text("SELECT code FROM accounts WHERE company_id = :cid AND code IN ('421010','621010')"), {"cid": company_id}).fetchall()}
        parents = {row[0]: row[1] for row in bind.execute(sa.text("SELECT code, id FROM accounts WHERE company_id = :cid AND code IN ('400000','600000')"), {"cid": company_id}).fetchall()}
        rows = []
        if "421010" not in existing and "400000" in parents:
            rows.append({"company_id": company_id, "code": "421010", "name_ar": "أرباح إنهاء وتعديل عقود الإيجار", "name_en": "Lease Termination and Modification Gains", "account_type": "REVENUE", "statement_group": "OTHER_INCOME", "parent_id": parents["400000"], "level": 2, "is_postable": True, "is_cash": False, "active": True})
        if "621010" not in existing and "600000" in parents:
            rows.append({"company_id": company_id, "code": "621010", "name_ar": "خسائر إنهاء وتعديل عقود الإيجار", "name_en": "Lease Termination and Modification Losses", "account_type": "EXPENSE", "statement_group": "OPERATING_EXPENSES", "parent_id": parents["600000"], "level": 2, "is_postable": True, "is_cash": False, "active": True})
        if rows:
            bind.execute(accounts.insert(), rows)


def downgrade():
    op.drop_table("lease_partial_terminations")
    op.drop_table("financial_evidence")
    op.drop_table("lead_schedule_items")
    op.drop_table("lead_schedules")
    op.drop_table("purchase_price_allocation_items")
    op.drop_table("business_combinations")
    op.drop_table("consolidation_worksheet_lines")
    op.drop_table("consolidation_worksheets")
