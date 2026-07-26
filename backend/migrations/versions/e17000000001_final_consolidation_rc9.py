"""final consolidation and finance completion rc9

Revision ID: e17000000001
Revises: e16000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e17000000001"
down_revision = "e16000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consolidated_trial_balance_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_end", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ledger_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("ledger_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("consolidated_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("consolidated_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("balance_difference", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("pending_worksheet_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("group_id", "period_end", "version", name="uq_consolidated_tb_group_period_version"),
    )
    op.create_table(
        "consolidated_trial_balance_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("consolidated_trial_balance_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("account_code", sa.String(60), nullable=False, index=True),
        sa.Column("account_name_ar", sa.String(250), nullable=False),
        sa.Column("account_name_en", sa.String(250), nullable=False),
        sa.Column("account_type", sa.String(30), nullable=False),
        sa.Column("member_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("member_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("consolidated_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("consolidated_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("run_id", "account_code", name="uq_consolidated_tb_line_account"),
    )
    op.create_table(
        "contingent_consideration_remeasurements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("combination_id", sa.Integer(), sa.ForeignKey("business_combinations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("measurement_date", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("classification", sa.String(20), nullable=False, server_default="LIABILITY"),
        sa.Column("measurement_type", sa.String(40), nullable=False, server_default="SUBSEQUENT_REMEASUREMENT"),
        sa.Column("opening_fair_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("closing_fair_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("fair_value_change", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("evidence_reference", sa.String(500), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("combination_id", "measurement_date", "version", name="uq_contingent_consideration_measurement"),
    )
    op.create_table(
        "foreign_operation_disposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("translation_run_id", sa.Integer(), sa.ForeignKey("foreign_operation_translation_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("disposal_date", sa.Date(), nullable=False, index=True),
        sa.Column("disposal_type", sa.String(40), nullable=False),
        sa.Column("disposal_percent", sa.Numeric(9, 6), nullable=False),
        sa.Column("cta_before_disposal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("cta_recycled", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("remaining_cta", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("evidence_reference", sa.String(500), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("worksheet_id", sa.Integer(), sa.ForeignKey("consolidation_worksheets.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
    )

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
    additions = [
        ("224010", "التزام المقابل المحتمل", "Contingent Consideration Liability", "LIABILITY", "NON_CURRENT_LIABILITIES", "220000", 3),
        ("314010", "حقوق غير المسيطرين", "Non-controlling Interests", "EQUITY", "EQUITY", "300000", 2),
        ("422010", "أرباح إعادة قياس المقابل المحتمل", "Contingent Consideration Remeasurement Gains", "REVENUE", "OTHER_INCOME", "400000", 2),
        ("423010", "أرباح التخلص من عملية أجنبية", "Gain on Disposal of Foreign Operation", "REVENUE", "OTHER_INCOME", "400000", 2),
        ("622010", "خسائر إعادة قياس المقابل المحتمل", "Contingent Consideration Remeasurement Losses", "EXPENSE", "OPERATING_EXPENSES", "600000", 2),
        ("623010", "خسائر التخلص من عملية أجنبية", "Loss on Disposal of Foreign Operation", "EXPENSE", "OPERATING_EXPENSES", "600000", 2),
    ]
    for company_id in companies:
        parent_rows = bind.execute(sa.text("SELECT code, id FROM accounts WHERE company_id = :cid"), {"cid": company_id}).fetchall()
        parents = {row[0]: row[1] for row in parent_rows}
        existing = {row[0] for row in bind.execute(sa.text("SELECT code FROM accounts WHERE company_id = :cid"), {"cid": company_id}).fetchall()}
        rows = []
        for code, ar, en, acc_type, group, parent_code, level in additions:
            if code not in existing and parent_code in parents:
                rows.append({"company_id": company_id, "code": code, "name_ar": ar, "name_en": en,
                             "account_type": acc_type, "statement_group": group, "parent_id": parents[parent_code],
                             "level": level, "is_postable": True, "is_cash": False, "active": True})
        if rows:
            bind.execute(accounts.insert(), rows)


def downgrade():
    op.drop_table("foreign_operation_disposals")
    op.drop_table("contingent_consideration_remeasurements")
    op.drop_table("consolidated_trial_balance_lines")
    op.drop_table("consolidated_trial_balance_runs")
