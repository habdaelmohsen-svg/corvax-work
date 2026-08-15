"""Serialize DGTERA work and index report proof lookups.

Revision ID: e20200000001
Revises: e20100000001
"""
from __future__ import annotations

from alembic import op


revision = "e20200000001"
down_revision = "e20100000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_dgtera_sales_orders_connection_sales_date",
        "dgtera_sales_orders",
        ["connection_id", "sales_date"],
        unique=False,
    )
    op.create_index(
        "ix_dgtera_sync_runs_connection_dates_status",
        "dgtera_sync_runs",
        ["connection_id", "start_date", "end_date", "status", "strict_reconciled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dgtera_sync_runs_connection_dates_status",
        table_name="dgtera_sync_runs",
    )
    op.drop_index(
        "ix_dgtera_sales_orders_connection_sales_date",
        table_name="dgtera_sales_orders",
    )
