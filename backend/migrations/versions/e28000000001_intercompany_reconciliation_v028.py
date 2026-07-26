"""intercompany reconciliation v0.28

Revision ID: e28000000001
Revises: e26000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e28000000001"
down_revision = "e26000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("intercompany_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counterparty_company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_number", sa.String(80), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("account_code", sa.String(30), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("foreign_amount", sa.Numeric(18,4), nullable=False, server_default="0"),
        sa.Column("local_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "document_number", "direction", name="uq_ic_record_company_doc_direction"),
    )
    op.create_index("ix_intercompany_records_company_id", "intercompany_records", ["company_id"])
    op.create_index("ix_intercompany_records_counterparty_company_id", "intercompany_records", ["counterparty_company_id"])
    op.create_index("ix_intercompany_records_document_number", "intercompany_records", ["document_number"])
    op.create_index("ix_intercompany_records_transaction_date", "intercompany_records", ["transaction_date"])
    op.create_index("ix_intercompany_records_status", "intercompany_records", ["status"])
    op.create_table("intercompany_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_a_id", sa.Integer(), sa.ForeignKey("intercompany_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_b_id", sa.Integer(), sa.ForeignKey("intercompany_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matched_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("variance_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="MATCHED"),
        sa.Column("notes", sa.String(500)),
        sa.Column("matched_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("matched_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("record_a_id", "record_b_id", name="uq_ic_match_pair"),
    )
    op.create_index("ix_intercompany_matches_record_a_id", "intercompany_matches", ["record_a_id"])
    op.create_index("ix_intercompany_matches_record_b_id", "intercompany_matches", ["record_b_id"])
    op.create_index("ix_intercompany_matches_status", "intercompany_matches", ["status"])
    op.create_table("consolidation_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("consolidation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("adjustment_type", sa.String(30), nullable=False, server_default="INTERCOMPANY"),
        sa.Column("reference", sa.String(120), nullable=False),
        sa.Column("debit_account_code", sa.String(30), nullable=False),
        sa.Column("credit_account_code", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(18,2), nullable=False),
        sa.Column("source_match_id", sa.Integer(), sa.ForeignKey("intercompany_matches.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_consolidation_adjustments_run_id", "consolidation_adjustments", ["run_id"])


def downgrade():
    op.drop_table("consolidation_adjustments")
    op.drop_table("intercompany_matches")
    op.drop_table("intercompany_records")
