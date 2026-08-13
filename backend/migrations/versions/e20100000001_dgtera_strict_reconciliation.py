"""DGTERA strict order, line and payment reconciliation evidence.

Revision ID: e20100000001
Revises: e19900000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e20100000001"
down_revision = "e19900000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dgtera_sync_runs") as batch:
        batch.add_column(sa.Column("source_lines", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("source_payments", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("source_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"))
        batch.add_column(sa.Column("source_subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("source_vat", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("source_paid", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("source_return", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("source_discount", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("strict_reconciled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("verification_hash", sa.String(64)))
        batch.add_column(sa.Column("reconciliation_details", sa.Text()))
        batch.create_index("ix_dgtera_sync_runs_strict_reconciled", ["strict_reconciled"])


def downgrade() -> None:
    with op.batch_alter_table("dgtera_sync_runs") as batch:
        batch.drop_index("ix_dgtera_sync_runs_strict_reconciled")
        batch.drop_column("reconciliation_details")
        batch.drop_column("verification_hash")
        batch.drop_column("strict_reconciled")
        batch.drop_column("source_discount")
        batch.drop_column("source_return")
        batch.drop_column("source_paid")
        batch.drop_column("source_vat")
        batch.drop_column("source_subtotal")
        batch.drop_column("source_quantity")
        batch.drop_column("source_payments")
        batch.drop_column("source_lines")
