"""Focused acceptance gate for the visible, full UAT clean-slate reset."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp") / f"corvax_uat_full_reset_{os.getpid()}.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SECRET_KEY": "verification-secret-key-uat-full-reset-2026",
        "ENVIRONMENT": "testing",
        "SEED_DEMO_DATA": "true",
        "ALLOW_DATA_RESET": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
        "ENABLE_RATE_LIMIT_TESTING": "true",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.api.uat_reset import (  # noqa: E402
    CONFIRMATION_PHRASE,
    PROTECTED_FOUNDATION_TABLES,
    _classified_tables,
)
from app.core.config import settings  # noqa: E402
from app.db import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def main() -> None:
    page = (ROOT / "frontend/src/dashboard/dataResetPage.tsx").read_text(encoding="utf-8")
    nav = (ROOT / "frontend/src/dashboard/navigation.tsx").read_text(encoding="utf-8")
    selector = (ROOT / "frontend/src/components/CompanySelector.tsx").read_text(encoding="utf-8")
    assert "مسح بيانات UAT وبدء الإدخال" in page and "Delete all added data now" in page
    assert "key: 'dataReset'" in nav and "requires: ['data.reset']" in nav
    assert "context.permissions" in selector and "permissions_by_company" in selector

    targets, protected = _classified_tables()
    assert set(targets).isdisjoint(PROTECTED_FOUNDATION_TABLES)
    assert set(protected) == PROTECTED_FOUNDATION_TABLES
    assert set(targets) | set(protected) == set(Base.metadata.tables)
    assert len(targets) >= 250, len(targets)

    with TestClient(app) as client:
        login = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        with SessionLocal() as db:
            before_foundation = {
                name: int(db.scalar(select(func.count()).select_from(Base.metadata.tables[name])) or 0)
                for name in protected
            }

        preview = ok(client.get("/api/v1/uat-reset/preview?company_id=1", headers=headers))
        assert preview["enabled"] is True
        assert preview["total_rows"] > 0
        assert preview["scope"] == "ALL_COMPANIES_BUSINESS_DATA"
        assert preview["confirmation_phrase"] == CONFIRMATION_PHRASE

        wrong = client.post(
            "/api/v1/uat-reset/execute",
            headers=headers,
            json={"company_id": 1, "confirmation": "wrong", "backup_acknowledged": True, "dry_run": True},
        )
        assert wrong.status_code == 422
        no_backup = client.post(
            "/api/v1/uat-reset/execute",
            headers=headers,
            json={"company_id": 1, "confirmation": CONFIRMATION_PHRASE, "backup_acknowledged": False, "dry_run": True},
        )
        assert no_backup.status_code == 422

        dry = ok(client.post(
            "/api/v1/uat-reset/execute",
            headers=headers,
            json={"company_id": 1, "confirmation": CONFIRMATION_PHRASE, "backup_acknowledged": True, "dry_run": True},
        ))
        assert dry["rows_that_would_be_deleted"] == preview["total_rows"]
        assert dry["authorization_token"]

        result = ok(client.post(
            "/api/v1/uat-reset/execute",
            headers=headers,
            json={
                "company_id": 1,
                "confirmation": CONFIRMATION_PHRASE,
                "backup_acknowledged": True,
                "dry_run": False,
                "authorization_token": dry["authorization_token"],
            },
        ))
        assert result["rows_deleted"] == preview["total_rows"]

        after = ok(client.get("/api/v1/uat-reset/preview?company_id=1", headers=headers))
        assert after["total_rows"] == 0
        with SessionLocal() as db:
            after_foundation = {
                name: int(db.scalar(select(func.count()).select_from(Base.metadata.tables[name])) or 0)
                for name in protected
            }
        # Audit is append-only by design; every other protected table is unchanged.
        for name in protected:
            if name == "audit_logs":
                assert after_foundation[name] >= before_foundation[name]
            else:
                assert after_foundation[name] == before_foundation[name], name

        previous_environment = settings.environment
        previous_flag = settings.allow_data_reset
        settings.environment = "production"
        settings.allow_data_reset = True
        try:
            denied = client.post(
                "/api/v1/uat-reset/execute",
                headers=headers,
                json={"company_id": 1, "confirmation": CONFIRMATION_PHRASE, "backup_acknowledged": True, "dry_run": True},
            )
            assert denied.status_code == 403
        finally:
            settings.environment = previous_environment
            settings.allow_data_reset = previous_flag

    DB_PATH.unlink(missing_ok=True)
    print("verify_uat_full_reset: PASSED")


if __name__ == "__main__":
    main()
