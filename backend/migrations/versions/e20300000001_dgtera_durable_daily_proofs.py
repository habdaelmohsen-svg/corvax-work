"""Create durable daily DGTERA proof and accounting state.

Revision ID: e20300000001
Revises: e20200000001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "e20300000001"
down_revision = "e20200000001"
branch_labels = None
depends_on = None

PROOF_TABLE = "dgtera_daily_proofs"
PROOF_INDEXES = {
    "ix_dgtera_daily_proofs_connection_id": ["connection_id"],
    "ix_dgtera_daily_proofs_company_id": ["company_id"],
    "ix_dgtera_daily_proofs_sales_date": ["sales_date"],
    "ix_dgtera_daily_proofs_strict_reconciled": ["strict_reconciled"],
    "ix_dgtera_daily_proofs_last_attempt_status": ["last_attempt_status"],
    "ix_dgtera_daily_proofs_accounting_status": ["accounting_status"],
    "ix_dgtera_daily_proofs_accounting_journal_id": ["accounting_journal_id"],
    "ix_dgtera_daily_proofs_connection_generation_date": [
        "connection_id", "proof_generation", "sales_date", "strict_reconciled",
    ],
    "ix_dgtera_daily_proofs_accounting_queue": [
        "connection_id", "strict_reconciled", "accounting_status", "sales_date",
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(PROOF_TABLE):
        op.create_table(
            PROOF_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("connection_id", sa.Integer(), sa.ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sales_date", sa.Date(), nullable=False),
            sa.Column("proof_generation", sa.String(length=100), nullable=False),
            sa.Column("strict_reconciled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_orders", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_lines", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_payments", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("source_subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("source_vat", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("source_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("source_paid", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("source_return", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("source_discount", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("verification_hash", sa.String(length=64)),
            sa.Column("verified_at", sa.DateTime()),
            sa.Column("last_attempt_at", sa.DateTime(), nullable=False),
            sa.Column("last_attempt_status", sa.String(length=30), nullable=False, server_default="PENDING"),
            sa.Column("last_error", sa.Text()),
            sa.Column("accounting_status", sa.String(length=30), nullable=False, server_default="PENDING"),
            sa.Column("accounting_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="SET NULL")),
            sa.Column("accounting_error", sa.Text()),
            sa.Column("accounting_updated_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("connection_id", "sales_date", name="uq_dgtera_daily_proof_date"),
            if_not_exists=True,
        )

    # SQLite may retain DDL after an interrupted deployment. Create only the
    # missing indexes, and use IF NOT EXISTS as a second idempotency guard.
    existing_indexes = {
        item["name"] for item in sa.inspect(bind).get_indexes(PROOF_TABLE)
    }
    for index_name, columns in PROOF_INDEXES.items():
        if index_name not in existing_indexes:
            op.create_index(
                index_name,
                PROOF_TABLE,
                columns,
                if_not_exists=True,
            )

    # Deliberately do not copy retained diagnostic rows here. Schema upgrades
    # must be independent of historical data quality. The serialized DGTERA
    # scheduler recreates strict daily proofs from the live source after the
    # service starts, one independently committed business day at a time.


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(PROOF_TABLE):
        return
    existing_indexes = {
        item["name"] for item in sa.inspect(bind).get_indexes(PROOF_TABLE)
    }
    for index_name in reversed(PROOF_INDEXES):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=PROOF_TABLE)
    op.drop_table(PROOF_TABLE)
