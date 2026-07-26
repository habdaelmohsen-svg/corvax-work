"""IFRS 9 general approach and IFRS 16 advanced cases for RC11.

Revision ID: e17300000001
Revises: e17200000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e17300000001"
down_revision = "e17200000001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("credit_risk_portfolios") as batch:
        batch.add_column(sa.Column("business_model", sa.String(30), nullable=False, server_default="HOLD_TO_COLLECT"))
        batch.add_column(sa.Column("sicr_days_past_due", sa.Integer(), nullable=False, server_default="30"))
        batch.add_column(sa.Column("default_days_past_due", sa.Integer(), nullable=False, server_default="90"))
        batch.add_column(sa.Column("pd_sicr_multiplier", sa.Numeric(10, 4), nullable=False, server_default="2"))
        batch.add_column(sa.Column("forward_looking_overlay", sa.Numeric(10, 6), nullable=False, server_default="1"))
        batch.add_column(sa.Column("model_version", sa.String(40), nullable=False, server_default="1.0"))
        batch.add_column(sa.Column("status", sa.String(25), nullable=False, server_default="APPROVED"))
        batch.add_column(sa.Column("reviewed_by", sa.Integer()))
        batch.add_column(sa.Column("approved_by", sa.Integer()))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime()))
        batch.add_column(sa.Column("approved_at", sa.DateTime()))
        batch.create_foreign_key("fk_credit_portfolio_reviewed_by", "users", ["reviewed_by"], ["id"])
        batch.create_foreign_key("fk_credit_portfolio_approved_by", "users", ["approved_by"], ["id"])
        batch.create_index("ix_credit_risk_portfolios_status", ["status"])

    with op.batch_alter_table("credit_exposures") as batch:
        batch.add_column(sa.Column("instrument_type", sa.String(30), nullable=False, server_default="TRADE_RECEIVABLE"))
        batch.add_column(sa.Column("origination_date", sa.Date()))
        batch.add_column(sa.Column("maturity_date", sa.Date()))
        batch.add_column(sa.Column("undrawn_commitment", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("credit_conversion_factor", sa.Numeric(10, 6), nullable=False, server_default="1"))
        batch.add_column(sa.Column("effective_interest_rate", sa.Numeric(10, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("initial_12m_pd", sa.Numeric(10, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("current_12m_pd", sa.Numeric(10, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("lifetime_pd", sa.Numeric(10, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("lgd", sa.Numeric(10, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("collateral_value", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("credit_rating", sa.String(30)))
        batch.add_column(sa.Column("business_model", sa.String(30), nullable=False, server_default="HOLD_TO_COLLECT"))
        batch.add_column(sa.Column("sppi_passed", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("significant_increase_in_credit_risk", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("default_flag", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("forbearance_flag", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("stage_override", sa.Integer()))
        batch.add_column(sa.Column("stage_reason", sa.String(500)))

    with op.batch_alter_table("ecl_runs") as batch:
        batch.add_column(sa.Column("approach", sa.String(30), nullable=False, server_default="SIMPLIFIED"))
        batch.add_column(sa.Column("model_version", sa.String(40), nullable=False, server_default="1.0"))
        batch.add_column(sa.Column("stage_1_ecl", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("stage_2_ecl", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("stage_3_ecl", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("analysis_hash", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("expense_account_code", sa.String(30)))
        batch.add_column(sa.Column("allowance_account_code", sa.String(30)))
        batch.add_column(sa.Column("reviewed_by", sa.Integer()))
        batch.add_column(sa.Column("approved_by", sa.Integer()))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime()))
        batch.add_column(sa.Column("approved_at", sa.DateTime()))
        batch.create_foreign_key("fk_ecl_run_reviewed_by", "users", ["reviewed_by"], ["id"])
        batch.create_foreign_key("fk_ecl_run_approved_by", "users", ["approved_by"], ["id"])

    with op.batch_alter_table("ecl_run_lines") as batch:
        batch.add_column(sa.Column("stage", sa.Integer(), nullable=False, server_default="2"))
        batch.add_column(sa.Column("stage_reason", sa.String(500)))
        batch.add_column(sa.Column("pd_rate", sa.Numeric(10, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("lgd_rate", sa.Numeric(10, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("ead_amount", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("discount_factor", sa.Numeric(18, 10), nullable=False, server_default="1"))
        batch.add_column(sa.Column("base_ecl_amount", sa.Numeric(18, 2), nullable=False, server_default="0"))

    op.create_table(
        "lease_variable_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lease_id", sa.Integer(), sa.ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("payment_date", sa.Date(), nullable=False, index=True),
        sa.Column("payment_basis", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("included_in_liability", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remeasurement_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("pnl_expense_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
    )
    op.create_table(
        "sale_leaseback_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("lease_id", sa.Integer(), sa.ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("transaction_date", sa.Date(), nullable=False, index=True),
        sa.Column("transfer_is_sale", sa.Boolean(), nullable=False),
        sa.Column("carrying_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("fair_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("sale_proceeds", sa.Numeric(18, 2), nullable=False),
        sa.Column("retained_right_percent", sa.Numeric(9, 6), nullable=False),
        sa.Column("initial_rou_asset", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("lease_liability", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("gain_on_rights_transferred", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("financing_liability", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("off_market_adjustment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("evidence_reference", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
    )
    op.create_table(
        "sublease_arrangements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("head_lease_id", sa.Integer(), sa.ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("commencement_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("remaining_head_lease_months", sa.Integer(), nullable=False),
        sa.Column("sublease_months", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("payment_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("net_investment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("derecognized_rou_asset", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("gain_loss", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("evidence_reference", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
    )


def downgrade():
    op.drop_table("sublease_arrangements")
    op.drop_table("sale_leaseback_transactions")
    op.drop_table("lease_variable_payments")
    with op.batch_alter_table("ecl_run_lines") as batch:
        for name in ("base_ecl_amount", "discount_factor", "ead_amount", "lgd_rate", "pd_rate", "stage_reason", "stage"):
            batch.drop_column(name)
    with op.batch_alter_table("ecl_runs") as batch:
        batch.drop_constraint("fk_ecl_run_approved_by", type_="foreignkey")
        batch.drop_constraint("fk_ecl_run_reviewed_by", type_="foreignkey")
        for name in ("approved_at", "reviewed_at", "approved_by", "reviewed_by", "allowance_account_code", "expense_account_code", "analysis_hash", "stage_3_ecl", "stage_2_ecl", "stage_1_ecl", "model_version", "approach"):
            batch.drop_column(name)
    with op.batch_alter_table("credit_exposures") as batch:
        for name in ("stage_reason", "stage_override", "forbearance_flag", "default_flag", "significant_increase_in_credit_risk", "sppi_passed", "business_model", "credit_rating", "collateral_value", "lgd", "lifetime_pd", "current_12m_pd", "initial_12m_pd", "effective_interest_rate", "credit_conversion_factor", "undrawn_commitment", "maturity_date", "origination_date", "instrument_type"):
            batch.drop_column(name)
    with op.batch_alter_table("credit_risk_portfolios") as batch:
        batch.drop_index("ix_credit_risk_portfolios_status")
        batch.drop_constraint("fk_credit_portfolio_approved_by", type_="foreignkey")
        batch.drop_constraint("fk_credit_portfolio_reviewed_by", type_="foreignkey")
        for name in ("approved_at", "reviewed_at", "approved_by", "reviewed_by", "status", "model_version", "forward_looking_overlay", "pd_sicr_multiplier", "default_days_past_due", "sicr_days_past_due", "business_model"):
            batch.drop_column(name)
