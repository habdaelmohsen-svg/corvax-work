"""Regression gate for schema-only, restart-safe Render e203 migration."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
DB_PATH = Path("/tmp") / f"corvax_e203_schema_only_{os.getpid()}.db"
DB_PATH.unlink(missing_ok=True)


def alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite:///{DB_PATH}",
            "ENVIRONMENT": "testing",
        },
        check=True,
    )


def retained_details(sales_date: str) -> str:
    empty_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    return json.dumps({
        "daily": {
            sales_date: {
                "source": {
                    "orders": 0,
                    "lines": 0,
                    "payments": 0,
                    "quantity": "0.0000",
                    "subtotal": "0.00",
                    "vat": "0.00",
                    "gross": "0.00",
                    "paid": "0.00",
                    "returns": "0.00",
                    "discounts": "0.00",
                },
                "verification_hash": empty_hash,
            }
        }
    })


try:
    alembic("upgrade", "e20200000001")
    proof_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    with sqlite3.connect(DB_PATH) as db:
        # Match the two retained days visible in the failed 03:24 Render log.
        for sales_date, completed_at in (
            ("2026-08-18", "2026-08-18 21:46:58"),
            ("2026-08-20", "2026-08-19 21:02:49"),
        ):
            db.execute(
                """
                INSERT INTO dgtera_sync_runs (
                    connection_id, company_id, start_date, end_date, window_label,
                    status, source_orders, inserted_orders, updated_orders,
                    unchanged_orders, source_total, started_at, completed_at,
                    source_lines, source_payments, source_quantity, source_subtotal,
                    source_vat, source_paid, source_return, source_discount,
                    strict_reconciled, verification_hash, reconciliation_details
                ) VALUES (
                    1, 1, ?, ?, ?, 'COMPLETED', 0, 0, 0, 0, 0, ?, ?,
                    0, 0, 0, 0, 0, 0, 0, 0, 1, ?, ?
                )
                """,
                (
                    sales_date,
                    sales_date,
                    "00:00 / dgtera-source-date-line-report-strict-v10",
                    completed_at,
                    completed_at,
                    proof_hash,
                    retained_details(sales_date),
                ),
            )

    alembic("upgrade", "head")
    with sqlite3.connect(DB_PATH) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "e20300000001"
        # Schema migration must never import retained business data.
        assert db.execute("SELECT COUNT(*) FROM dgtera_daily_proofs").fetchone()[0] == 0
        index_names = {
            row[1] for row in db.execute("PRAGMA index_list('dgtera_daily_proofs')")
        }
        assert "ix_dgtera_daily_proofs_accounting_queue" in index_names

        # Reproduce an interrupted deployment: table and most indexes remain,
        # Alembic is still e202, and any attempted historical INSERT conflicts.
        db.execute(
            """
            INSERT INTO dgtera_daily_proofs (
                connection_id, company_id, sales_date, proof_generation,
                strict_reconciled, last_attempt_at, last_attempt_status,
                accounting_status, created_at, updated_at
            ) VALUES (
                1, 1, '2026-08-17', 'sentinel-existing-proof', 1,
                '2026-08-17 23:59:00', 'VERIFIED', 'PENDING',
                '2026-08-17 23:59:00', '2026-08-17 23:59:00'
            )
            """
        )
        db.execute("DROP INDEX ix_dgtera_daily_proofs_accounting_queue")
        db.execute("UPDATE alembic_version SET version_num = 'e20200000001'")
        db.execute(
            """
            CREATE TRIGGER reject_any_e203_backfill
            BEFORE INSERT ON dgtera_daily_proofs
            BEGIN
                SELECT RAISE(ABORT, 'e203 must not backfill during startup');
            END
            """
        )

    alembic("upgrade", "head")
    with sqlite3.connect(DB_PATH) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "e20300000001"
        proofs = db.execute(
            "SELECT sales_date, proof_generation FROM dgtera_daily_proofs"
        ).fetchall()
        assert proofs == [("2026-08-17", "sentinel-existing-proof")]
        index_names = {
            row[1] for row in db.execute("PRAGMA index_list('dgtera_daily_proofs')")
        }
        assert "ix_dgtera_daily_proofs_accounting_queue" in index_names

    migration_source = (
        BACKEND / "migrations/versions/e20300000001_dgtera_durable_daily_proofs.py"
    ).read_text(encoding="utf-8")
    assert "proof_table.insert" not in migration_source
    assert "_backfill_recent_verified_days" not in migration_source

    print("verify_e203_partial_migration_recovery: PASSED")
finally:
    DB_PATH.unlink(missing_ok=True)
