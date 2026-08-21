"""Regression gate for Render e203 recovery and per-day conflict isolation."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
DB_PATH = Path("/tmp") / f"corvax_e203_recovery_{os.getpid()}.db"
CONFLICT_DB_PATH = Path("/tmp") / f"corvax_e203_conflict_{os.getpid()}.db"
for path in (DB_PATH, CONFLICT_DB_PATH):
    path.unlink(missing_ok=True)


def alembic(db_path: Path, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite:///{db_path}",
            "ENVIRONMENT": "testing",
        },
        check=True,
    )


def retained_details(sales_date: str, total: str = "115") -> str:
    return json.dumps({
        "daily": {
            sales_date: {
                "source": {
                    "orders": 1,
                    "lines": 1,
                    "payments": 1,
                    "quantity": "1",
                    "subtotal": "100",
                    "vat": "15",
                    "gross": total,
                    "paid": total,
                    "returns": "0",
                    "discounts": "0",
                },
                "verification_hash": "a" * 64,
            }
        }
    })


try:
    alembic(DB_PATH, "upgrade", "e20200000001")
    proof_hash = "a" * 64
    with sqlite3.connect(DB_PATH) as db:
        # Production contained retained completed runs with no completed_at.
        # The migration must use started_at instead of violating NOT NULL.
        db.execute(
            """
            INSERT INTO dgtera_sync_runs (
                connection_id, company_id, start_date, end_date, window_label,
                status, source_orders, inserted_orders, updated_orders,
                unchanged_orders, source_total, started_at, source_lines,
                source_payments, source_quantity, source_subtotal, source_vat,
                source_paid, source_return, source_discount, strict_reconciled,
                verification_hash, reconciliation_details
            ) VALUES (
                1, 1, '2026-08-20', '2026-08-20', ?, 'COMPLETED',
                0, 0, 0, 0, 0, '2026-08-20 00:00:00', 0, 0, 0, 0, 0,
                0, 0, 0, 1, ?, ?
            )
            """,
            (
                "00:00 / dgtera-source-date-line-report-strict-v10",
                proof_hash,
                retained_details("2026-08-20"),
            ),
        )

    alembic(DB_PATH, "upgrade", "head")
    with sqlite3.connect(DB_PATH) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "e20300000001"
        proof = db.execute(
            """
            SELECT last_attempt_at, verified_at, source_total
            FROM dgtera_daily_proofs
            WHERE connection_id = 1 AND sales_date = '2026-08-20'
            """
        ).fetchone()
        assert proof == ("2026-08-20 00:00:00", "2026-08-20 00:00:00", 115)

        # Reproduce Render after the original non-transactional SQLite failure:
        # the complete table/index set remains but Alembic is still on e202.
        db.execute("UPDATE alembic_version SET version_num = 'e20200000001'")

    alembic(DB_PATH, "upgrade", "head")
    with sqlite3.connect(DB_PATH) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "e20300000001"
        assert db.execute("SELECT COUNT(*) FROM dgtera_daily_proofs").fetchone()[0] == 1
        index_names = {
            row[1] for row in db.execute("PRAGMA index_list('dgtera_daily_proofs')")
        }
        assert "ix_dgtera_daily_proofs_accounting_queue" in index_names

    # Reproduce the new Render evidence from 03:24: e203 attempted a bulk
    # insert for two retained days and one integrity conflict aborted both.
    # A bad historical day must now roll back only to its savepoint, allowing
    # the other proof and the migration revision to commit.
    alembic(CONFLICT_DB_PATH, "upgrade", "head")
    with sqlite3.connect(CONFLICT_DB_PATH) as db:
        db.execute("UPDATE alembic_version SET version_num = 'e20200000001'")
        db.execute(
            """
            CREATE TRIGGER reject_one_legacy_dgtera_proof
            BEFORE INSERT ON dgtera_daily_proofs
            WHEN NEW.sales_date = '2026-08-18'
            BEGIN
                SELECT RAISE(ABORT, 'simulated retained integrity conflict');
            END
            """
        )
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

    alembic(CONFLICT_DB_PATH, "upgrade", "head")
    with sqlite3.connect(CONFLICT_DB_PATH) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "e20300000001"
        proofs = db.execute(
            "SELECT sales_date, source_total FROM dgtera_daily_proofs ORDER BY sales_date"
        ).fetchall()
        assert proofs == [("2026-08-20", 115)]

    print("verify_e203_partial_migration_recovery: PASSED")
finally:
    for path in (DB_PATH, CONFLICT_DB_PATH):
        path.unlink(missing_ok=True)
