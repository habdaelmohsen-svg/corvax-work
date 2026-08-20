"""Keep durable daily DGTERA proof and accounting state.

Revision ID: e20300000001
Revises: e20200000001
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "e20300000001"
down_revision = "e20200000001"
branch_labels = None
depends_on = None

LEGACY_PROOF_MARKER = "dgtera-source-date-line-report-strict-v10"
CURRENT_PROOF_MARKER = "dgtera-source-date-line-report-strict-v11-durable"


def _decimal_value(metrics: dict, key: str) -> str:
    return str(metrics.get(key) or "0")


def _backfill_recent_verified_days(bind, proof_table: sa.Table) -> None:
    """Promote retained V10 run evidence without trusting a later mismatch.

    Only a small diagnostic tail exists on SQLite installations. A later
    transport failure does not erase the last verified day; a later strict
    reconciliation failure does, because DGTERA returned a complete but
    different source snapshot.
    """
    runs = sa.table(
        "dgtera_sync_runs",
        sa.column("id", sa.Integer),
        sa.column("connection_id", sa.Integer),
        sa.column("company_id", sa.Integer),
        sa.column("start_date", sa.Date),
        sa.column("end_date", sa.Date),
        sa.column("status", sa.String),
        sa.column("strict_reconciled", sa.Boolean),
        sa.column("window_label", sa.String),
        sa.column("reconciliation_details", sa.Text),
        sa.column("error_message", sa.Text),
        sa.column("completed_at", sa.DateTime),
    )
    rows = bind.execute(
        sa.select(runs).where(
            runs.c.start_date == runs.c.end_date,
            runs.c.window_label.like(f"%{LEGACY_PROOF_MARKER}%"),
        ).order_by(runs.c.id)
    ).mappings().all()
    by_day: dict[tuple[int, object], dict] = {}
    for row in rows:
        key = (int(row["connection_id"]), row["start_date"])
        state = by_day.setdefault(key, {"success": None, "invalidated": False, "latest": None})
        state["latest"] = row
        if row["status"] == "COMPLETED" and bool(row["strict_reconciled"]):
            state["success"] = row
            state["invalidated"] = False
        elif row["status"] == "ERROR" and row["reconciliation_details"]:
            try:
                details = json.loads(row["reconciliation_details"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                details = {}
            if int(details.get("mismatch_count") or 0) > 0:
                state["invalidated"] = True

    inserts: list[dict] = []
    for (_, sales_date), state in by_day.items():
        row = state["success"]
        if row is None or state["invalidated"]:
            continue
        try:
            details = json.loads(row["reconciliation_details"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        evidence = (details.get("daily") or {}).get(sales_date.isoformat()) or {}
        metrics = evidence.get("source") or {}
        verification_hash = str(evidence.get("verification_hash") or "")
        if len(verification_hash) != 64:
            continue
        latest = state["latest"] or row
        inserts.append({
            "connection_id": int(row["connection_id"]),
            "company_id": int(row["company_id"]),
            "sales_date": sales_date,
            "proof_generation": CURRENT_PROOF_MARKER,
            "strict_reconciled": True,
            "source_orders": int(metrics.get("orders") or 0),
            "source_lines": int(metrics.get("lines") or 0),
            "source_payments": int(metrics.get("payments") or 0),
            "source_quantity": _decimal_value(metrics, "quantity"),
            "source_subtotal": _decimal_value(metrics, "subtotal"),
            "source_vat": _decimal_value(metrics, "vat"),
            "source_total": _decimal_value(metrics, "gross"),
            "source_paid": _decimal_value(metrics, "paid"),
            "source_return": _decimal_value(metrics, "returns"),
            "source_discount": _decimal_value(metrics, "discounts"),
            "verification_hash": verification_hash,
            "verified_at": row["completed_at"],
            "last_attempt_at": latest["completed_at"] or row["completed_at"],
            "last_attempt_status": "VERIFIED" if latest["id"] == row["id"] else "SOURCE_ERROR",
            "last_error": latest["error_message"] if latest["id"] != row["id"] else None,
            "accounting_status": "PENDING",
            "created_at": row["completed_at"],
            "updated_at": row["completed_at"],
        })
    if inserts:
        bind.execute(proof_table.insert(), inserts)


def upgrade() -> None:
    op.create_table(
        "dgtera_daily_proofs",
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
    )
    op.create_index("ix_dgtera_daily_proofs_connection_id", "dgtera_daily_proofs", ["connection_id"])
    op.create_index("ix_dgtera_daily_proofs_company_id", "dgtera_daily_proofs", ["company_id"])
    op.create_index("ix_dgtera_daily_proofs_sales_date", "dgtera_daily_proofs", ["sales_date"])
    op.create_index("ix_dgtera_daily_proofs_strict_reconciled", "dgtera_daily_proofs", ["strict_reconciled"])
    op.create_index("ix_dgtera_daily_proofs_last_attempt_status", "dgtera_daily_proofs", ["last_attempt_status"])
    op.create_index("ix_dgtera_daily_proofs_accounting_status", "dgtera_daily_proofs", ["accounting_status"])
    op.create_index("ix_dgtera_daily_proofs_accounting_journal_id", "dgtera_daily_proofs", ["accounting_journal_id"])
    op.create_index(
        "ix_dgtera_daily_proofs_connection_generation_date",
        "dgtera_daily_proofs",
        ["connection_id", "proof_generation", "sales_date", "strict_reconciled"],
    )
    op.create_index(
        "ix_dgtera_daily_proofs_accounting_queue",
        "dgtera_daily_proofs",
        ["connection_id", "strict_reconciled", "accounting_status", "sales_date"],
    )
    proof_table = sa.table(
        "dgtera_daily_proofs",
        *[sa.column(name) for name in (
            "connection_id", "company_id", "sales_date", "proof_generation", "strict_reconciled",
            "source_orders", "source_lines", "source_payments", "source_quantity", "source_subtotal",
            "source_vat", "source_total", "source_paid", "source_return", "source_discount",
            "verification_hash", "verified_at", "last_attempt_at", "last_attempt_status", "last_error",
            "accounting_status", "created_at", "updated_at",
        )],
    )
    _backfill_recent_verified_days(op.get_bind(), proof_table)


def downgrade() -> None:
    op.drop_index("ix_dgtera_daily_proofs_accounting_queue", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_connection_generation_date", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_accounting_journal_id", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_accounting_status", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_last_attempt_status", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_strict_reconciled", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_sales_date", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_company_id", table_name="dgtera_daily_proofs")
    op.drop_index("ix_dgtera_daily_proofs_connection_id", table_name="dgtera_daily_proofs")
    op.drop_table("dgtera_daily_proofs")
