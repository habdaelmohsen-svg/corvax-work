"""R9.1 gate: friendly usernames and protected, system-wide UAT reset."""
from __future__ import annotations

import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / f"corvax_r9_1_uat_reset_{os.getpid()}.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SECRET_KEY": "verification-secret-key-r9-1-uat-reset-user-creation",
        "ENVIRONMENT": "testing",
        "SEED_DEMO_DATA": "true",
        "ALLOW_DATA_RESET": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
        "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r9.1",
        "ENABLE_RATE_LIMIT_TESTING": "true",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.api.data_reset import UAT_PRESERVED_TABLES, _uat_target_tables  # noqa: E402
from app.db import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    AuditLog,
    Branch,
    Company,
    DemoDataRecord,
    Item,
    JournalEntry,
    Role,
    User,
    UserCompanyRole,
)


def ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def auth(client: TestClient, login: str, password: str) -> dict[str, str]:
    payload = ok(client.post("/api/v1/auth/login", json={"email": login, "password": password}))
    return {"Authorization": f"Bearer {payload['access_token']}"}


def count(db, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def main() -> None:
    root = BACKEND_DIR.parent
    page = (root / "frontend/src/dashboard/dataResetPage.tsx").read_text(encoding="utf-8")
    users_page = (root / "frontend/src/dashboard/usersPage.tsx").read_text(encoding="utf-8")
    render = (root / "render.yaml").read_text(encoding="utf-8")
    assert "/api/v1/data-reset/uat-preview" in page
    assert "authorization_token" in page and "confirmation === phrase" in page
    assert "normaliseUsername" in users_page and "hussein.mahmoud" in users_page
    assert "value: uat" in render and "value: true" in render

    targets = _uat_target_tables()
    assert len(targets) == len(Base.metadata.tables) - len(UAT_PRESERVED_TABLES)
    assert len(targets) >= 279
    for table_name in UAT_PRESERVED_TABLES:
        for foreign_key in Base.metadata.tables[table_name].foreign_keys:
            assert foreign_key.column.table.name in UAT_PRESERVED_TABLES

    with TestClient(app) as client:
        admin = auth(client, "admin@corvaxplatform.com", "Corvax@123")

        created = ok(
            client.post(
                "/api/v1/admin/users",
                headers=admin,
                json={
                    "name_ar": "حسين محمود",
                    "name_en": "Hussein Mahmoud",
                    "email": "hussein.mahmoud@corvax.local",
                    "username": "Hussein Mahmoud",
                    "password": "HusseinCreate@123",
                    "require_password_change": False,
                    "memberships": [{"company_id": 1, "role_code": "CFO"}],
                },
            ),
            201,
        )
        assert created["username"] == "hussein.mahmoud"
        cfo = auth(client, "hussein.mahmoud", "HusseinCreate@123")
        denied = client.get("/api/v1/data-reset/uat-preview", headers=cfo)
        assert denied.status_code == 403, denied.text

        preview = ok(client.get("/api/v1/data-reset/uat-preview", headers=admin))
        assert preview["enabled"] is True
        assert preview["scope"] == "SYSTEM_WIDE_UAT"
        assert preview["total_rows"] > 0
        assert preview["tables_affected"] > 3
        assert preview["preserved"]["companies"] == 4
        phrase = preview["confirmation_phrase"]

        with SessionLocal() as db:
            preserved_before = {
                "companies": count(db, Company),
                "branches": count(db, Branch),
                "accounts": count(db, Account),
                "users": count(db, User),
                "roles": count(db, Role),
                "memberships": count(db, UserCompanyRole),
            }

        wrong = client.post(
            "/api/v1/data-reset/uat-execute",
            headers=admin,
            json={"confirmation": "wrong", "dry_run": True},
        )
        assert wrong.status_code == 422, wrong.text
        without_dry_run = client.post(
            "/api/v1/data-reset/uat-execute",
            headers=admin,
            json={"confirmation": phrase, "dry_run": False},
        )
        assert without_dry_run.status_code == 428, without_dry_run.text

        dry_run = ok(
            client.post(
                "/api/v1/data-reset/uat-execute",
                headers=admin,
                json={"confirmation": phrase, "dry_run": True},
            )
        )
        assert dry_run["rows_deleted"] == 0
        assert dry_run["authorization_token"]
        assert dry_run["rows_that_would_be_deleted"] == preview["total_rows"]

        result = ok(
            client.post(
                "/api/v1/data-reset/uat-execute",
                headers=admin,
                json={
                    "confirmation": phrase,
                    "dry_run": False,
                    "authorization_token": dry_run["authorization_token"],
                },
            )
        )
        assert result["rows_deleted"] == dry_run["rows_that_would_be_deleted"]
        assert result["tables_affected"] == dry_run["tables_affected"]

        after = ok(client.get("/api/v1/data-reset/uat-preview", headers=admin))
        assert after["total_rows"] == 0
        assert after["tables"] == {}

        with SessionLocal() as db:
            assert count(db, Company) == preserved_before["companies"]
            assert count(db, Branch) == preserved_before["branches"]
            assert count(db, Account) == preserved_before["accounts"]
            assert count(db, User) == preserved_before["users"]
            assert count(db, Role) == preserved_before["roles"]
            assert count(db, UserCompanyRole) == preserved_before["memberships"]
            assert db.scalar(select(User).where(User.username == "hussein.mahmoud")) is not None
            assert count(db, JournalEntry) == 0
            assert count(db, Item) == 0
            assert count(db, DemoDataRecord) == 0
            assert db.scalar(
                select(AuditLog.id).where(AuditLog.action == "UAT_OPERATIONAL_RESET_COMPLETED")
            )

        created_after_reset = ok(
            client.post(
                "/api/v1/admin/users",
                headers=admin,
                json={
                    "name_ar": "مستخدم تجربة جديد",
                    "name_en": "New UAT User",
                    "email": "new.uat.user@corvax.local",
                    "username": "New UAT User",
                    "password": "NewUatUser@123",
                    "require_password_change": False,
                    "memberships": [{"company_id": 1, "role_code": "ACCOUNTANT"}],
                },
            ),
            201,
        )
        assert created_after_reset["username"] == "new.uat.user"

    DB_PATH.unlink(missing_ok=True)
    print("verify_r9_1_uat_reset_user_creation: PASSED")


if __name__ == "__main__":
    main()
