"""Regression gate for the destructive Demo-data reset capability."""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / f"corvax_demo_data_reset_{os.getpid()}.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SECRET_KEY": "verification-secret-key-demo-reset-safety",
        "ENVIRONMENT": "testing",
        "SEED_DEMO_DATA": "true",
        "ALLOW_DATA_RESET": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
        "ENABLE_RATE_LIMIT_TESTING": "true",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.config import Settings, settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    DemoDataRecord,
    Item,
    JournalEntry,
    JournalLine,
    StockMovement,
    User,
    Warehouse,
)


def ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def auth(client: TestClient, email: str, password: str) -> dict[str, str]:
    payload = ok(
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
    )
    return {"Authorization": f"Bearer {payload['access_token']}"}


def assert_production_configuration_rejects_reset() -> None:
    assert Settings.model_fields["allow_data_reset"].default is False
    try:
        Settings(
            environment="production",
            secret_key="x" * 48,
            allowed_origins="https://corvax.example",
            trusted_hosts="corvax.example",
            seed_demo_data=False,
            allow_data_reset=True,
            auto_create_schema=False,
            jwt_algorithm="RS256",
            jwt_private_key_pem="PRIVATE",
            jwt_active_kid="test-kid",
            jwt_public_keys_json='{"test-kid":"PUBLIC"}',
            field_encryption_active_kid="field-kid",
            field_encryption_keys_json='{"field-kid":"KEY"}',
            enforce_sensitive_role_mfa=True,
            mrp_inline_execution=False,
            payroll_strict_workflow=True,
        )
    except ValidationError as exc:
        assert "Production ALLOW_DATA_RESET must be false" in str(exc)
    else:
        raise AssertionError("Production accepted ALLOW_DATA_RESET=true")


def main() -> None:
    assert_production_configuration_rejects_reset()
    root = BACKEND_DIR.parent
    navigation = (root / "frontend/src/dashboard/navigation.tsx").read_text(
        encoding="utf-8"
    )
    page = (root / "frontend/src/dashboard/dataResetPage.tsx").read_text(
        encoding="utf-8"
    )
    assert (
        "key: 'dataReset'" in navigation
        and "requires: ['data.reset']" in navigation
    )
    assert "authorization_token" in page and "confirmation === phrase" in page

    with TestClient(app) as client:
        admin = auth(client, "admin@corvaxplatform.com", "Corvax@123")

        # A normal accounting role must not see/use the capability.  The
        # dedicated data.reset permission is not assigned to ACCOUNTANT.
        ok(
            client.post(
                "/api/v1/admin/users",
                headers=admin,
                json={
                    "name_ar": "محاسب اختبار الحذف",
                    "name_en": "Reset Safety Accountant",
                    "email": "reset.accountant@corvaxplatform.com",
                    "password": "ResetSafety@123",
                    "require_password_change": False,
                    "memberships": [{"company_id": 1, "role_code": "ACCOUNTANT"}],
                },
            ),
            201,
        )
        accountant = auth(
            client,
            "reset.accountant@corvaxplatform.com",
            "ResetSafety@123",
        )
        denied = client.get(
            "/api/v1/data-reset/preview?company_id=1",
            headers=accountant,
        )
        assert denied.status_code == 403, denied.text

        # Insert a real/manual journal AFTER demo seeding.  It deliberately lives
        # in the same table as Demo journals and therefore proves that the API
        # does not delete by table/company scope.
        with SessionLocal() as db:
            admin_user = db.scalar(
                select(User).where(User.email == "admin@corvaxplatform.com")
            )
            manual = JournalEntry(
                company_id=1,
                number="MANUAL-KEEP-0001",
                entry_date=date(2026, 7, 28),
                reference="MANUAL-REAL-DATA",
                description="Manual row that must survive Demo purge",
                status="POSTED",
                total_debit=Decimal("125.00"),
                total_credit=Decimal("125.00"),
                created_by=admin_user.id,
                approved_by=admin_user.id,
                posted_by=admin_user.id,
            )
            manual.lines.extend(
                [
                    JournalLine(
                        account_id=1,
                        description="Manual debit",
                        debit=Decimal("125.00"),
                        credit=Decimal("0"),
                    ),
                    JournalLine(
                        account_id=2,
                        description="Manual credit",
                        debit=Decimal("0"),
                        credit=Decimal("125.00"),
                    ),
                ]
            )
            db.add(manual)
            db.commit()
            manual_id = manual.id
            manual_line_ids = [line.id for line in manual.lines]
            warehouse = db.scalar(
                select(Warehouse).where(
                    Warehouse.company_id == 1,
                    Warehouse.code == "MAIN",
                )
            )
            item = db.scalar(
                select(Item).where(
                    Item.company_id == 1,
                    Item.code == "RAW-001",
                )
            )
            manual_stock = StockMovement(
                company_id=1,
                warehouse_id=warehouse.id,
                item_id=item.id,
                movement_date=date(2026, 7, 28),
                movement_type="RECEIPT",
                quantity=Decimal("7"),
                unit_cost=Decimal("11"),
                total_cost=Decimal("77"),
                reference_type="MANUAL_TEST",
                created_by=admin_user.id,
            )
            db.add(manual_stock)
            db.commit()
            manual_stock_id = manual_stock.id
            assert not db.scalar(
                select(DemoDataRecord.id).where(
                    DemoDataRecord.table_name == "journal_entries",
                    DemoDataRecord.record_id == str(manual_id),
                )
            )
            assert not db.scalar(
                select(DemoDataRecord.id).where(
                    DemoDataRecord.table_name == "stock_movements",
                    DemoDataRecord.record_id == str(manual_stock_id),
                )
            )
            company_two_demo_before = int(
                db.scalar(
                    select(func.count(DemoDataRecord.id)).where(
                        DemoDataRecord.company_id == 2
                    )
                )
                or 0
            )
            protected_demo_entry_id = int(
                db.scalar(
                    select(DemoDataRecord.record_id)
                    .where(
                        DemoDataRecord.company_id == 1,
                        DemoDataRecord.table_name == "journal_entries",
                    )
                    .order_by(DemoDataRecord.id)
                )
            )
            manual.reversed_entry_id = protected_demo_entry_id
            db.commit()

        # A manual row linked to Demo data blocks the whole purge.  This prevents
        # a database cascade from silently taking real data with the Demo row.
        blocked_preview = ok(
            client.get("/api/v1/data-reset/preview?company_id=1", headers=admin)
        )
        assert blocked_preview["blocking_dependencies"]["journal_entries.reversed_entry_id"] == 1
        blocked_attempt = client.post(
            "/api/v1/data-reset/execute",
            headers=admin,
            json={
                "company_id": 1,
                "confirmation": blocked_preview["confirmation_phrase"],
                "dry_run": True,
            },
        )
        assert blocked_attempt.status_code == 409, blocked_attempt.text
        with SessionLocal() as db:
            manual = db.get(JournalEntry, manual_id)
            manual.reversed_entry_id = None
            db.commit()

        preview = ok(
            client.get("/api/v1/data-reset/preview?company_id=1", headers=admin)
        )
        assert preview["enabled"] is True
        assert preview["total_rows"] > 0
        assert preview["preserved_unregistered"]["journal_entries"] >= 1
        assert preview["preserved_unregistered"]["journal_lines"] >= 2
        assert preview["preserved_unregistered"]["stock_movements"] >= 1
        assert preview["blocking_dependencies"] == {}
        phrase = preview["confirmation_phrase"]

        # Confirmation is API-enforced, and a real delete cannot skip dry run.
        assert (
            client.post(
                "/api/v1/data-reset/execute",
                headers=admin,
                json={
                    "company_id": 1,
                    "confirmation": "wrong",
                    "dry_run": True,
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/data-reset/execute",
                headers=admin,
                json={
                    "company_id": 1,
                    "confirmation": phrase,
                    "dry_run": False,
                },
            ).status_code
            == 428
        )

        dry_run = ok(
            client.post(
                "/api/v1/data-reset/execute",
                headers=admin,
                json={
                    "company_id": 1,
                    "confirmation": phrase,
                    "dry_run": True,
                },
            )
        )
        assert dry_run["rows_deleted"] == 0
        assert dry_run["authorization_token"]
        assert dry_run["manual_rows_preserved"] >= 4

        # The API itself remains closed in production even if the in-memory flag
        # is forcefully toggled after startup.
        previous_environment = settings.environment
        previous_allow = settings.allow_data_reset
        settings.environment = "production"
        settings.allow_data_reset = True
        try:
            production_attempt = client.post(
                "/api/v1/data-reset/execute",
                headers=admin,
                json={
                    "company_id": 1,
                    "confirmation": phrase,
                    "dry_run": True,
                },
            )
            assert production_attempt.status_code == 403, production_attempt.text
        finally:
            settings.environment = previous_environment
            settings.allow_data_reset = previous_allow

        result = ok(
            client.post(
                "/api/v1/data-reset/execute",
                headers=admin,
                json={
                    "company_id": 1,
                    "confirmation": phrase,
                    "dry_run": False,
                    "authorization_token": dry_run["authorization_token"],
                },
            )
        )
        assert result["rows_deleted"] == dry_run["rows_that_would_be_deleted"]
        assert result["manual_rows_preserved"] >= 4

        with SessionLocal() as db:
            assert db.get(JournalEntry, manual_id) is not None
            assert all(db.get(JournalLine, line_id) is not None for line_id in manual_line_ids)
            assert db.get(StockMovement, manual_stock_id) is not None
            assert (
                db.scalar(
                    select(func.count(DemoDataRecord.id)).where(
                        DemoDataRecord.company_id == 1
                    )
                )
                == 0
            )
            assert (
                db.scalar(
                    select(func.count(DemoDataRecord.id)).where(
                        DemoDataRecord.company_id == 2
                    )
                )
                == company_two_demo_before
            )
            assert db.scalar(
                select(AuditLog.id).where(
                    AuditLog.company_id == 1,
                    AuditLog.action == "DEMO_DATA_RESET_COMPLETED",
                )
            )

    DB_PATH.unlink(missing_ok=True)
    print("verify_demo_data_reset_safety: PASSED")


if __name__ == "__main__":
    main()
