"""End-to-end verification for R9 platform assurance without modifying main.py."""
from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB = Path("/tmp/corvax_verify_r9_platform.db")
DB.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB}", "SECRET_KEY": "r9-platform-verification-secret-key",
    "SEED_DEMO_DATA": "false", "AUTO_CREATE_SCHEMA": "true", "TRUSTED_HOSTS": "testserver",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r9",
})

from fastapi import Depends, FastAPI, Header  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401 - register the complete legacy metadata
from app.api.r9_platform import router  # noqa: E402
from app.db import Base, SessionLocal, engine, get_db  # noqa: E402
from app.dependencies import get_current_user  # noqa: E402
from app.models.core import Company, Permission, Role, User, UserCompanyRole  # noqa: E402


def current_user(x_test_user: int = Header(), db: Session = Depends(get_db)) -> User:
    user = db.get(User, x_test_user)
    assert user
    return user


app = FastAPI()
app.include_router(router, prefix="/api/v1")
app.dependency_overrides[get_current_user] = current_user


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def xlsx(rows: list[list[object]]) -> bytes:
    workbook = Workbook(); sheet = workbook.active
    for row in rows: sheet.append(row)
    output = BytesIO(); workbook.save(output)
    return output.getvalue()


def seed() -> tuple[int, int]:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        c1 = Company(code="R9A", name_ar="شركة أ", name_en="Company A")
        c2 = Company(code="R9B", name_ar="شركة ب", name_en="Company B")
        db.add_all([c1, c2]); db.flush()
        permissions = [Permission(code=code, name_ar=code, name_en=code) for code in
                       ["platform.view", "platform.manage", "import.stage", "import.approve", "zatca.manage"]]
        role = Role(code="R9_AUDIT", name_ar="رقابة R9", name_en="R9 assurance", permissions=permissions)
        maker = User(name_ar="معد", name_en="Maker", email="maker.r9@example.com", password_hash="unused", mfa_enabled=False)
        checker = User(name_ar="معتمد", name_en="Checker", email="checker.r9@example.com", password_hash="unused", mfa_enabled=True)
        db.add_all([role, maker, checker]); db.flush()
        db.add_all([UserCompanyRole(user_id=maker.id, company_id=c1.id, role_id=role.id),
                    UserCompanyRole(user_id=checker.id, company_id=c1.id, role_id=role.id)])
        db.commit(); return maker.id, checker.id


def main() -> None:
    maker_id, checker_id = seed()
    maker = {"X-Test-User": str(maker_id)}; checker = {"X-Test-User": str(checker_id)}
    with TestClient(app) as client:
        # Health is company-scoped and exposes no connection URL, backup path, token or key.
        health = ok(client.get("/api/v1/r9-platform/health?company_id=1", headers=maker))
        encoded = str(health).lower()
        assert health["secrets_exposed"] is False and health["database"]["status"] == "UP"
        assert not any(term in encoded for term in ("password", "database_url", "storage_path", "secret_key", "metrics_token"))
        assert client.get("/api/v1/r9-platform/health?company_id=2", headers=maker).status_code == 403

        # Control scan generates actionable alerts and remains idempotent.
        first = ok(client.post("/api/v1/r9-platform/controls/scan?company_id=1", headers=maker))
        second = ok(client.post("/api/v1/r9-platform/controls/scan?company_id=1", headers=maker))
        assert first["created_alerts"] >= 2 and second["created_alerts"] == 0
        alerts = ok(client.get("/api/v1/r9-platform/alerts?company_id=1", headers=maker))
        assert {a["category"] for a in alerts} >= {"RESILIENCE"}
        alert_id = alerts[0]["id"]
        ok(client.post(f"/api/v1/r9-platform/alerts/{alert_id}/assign", headers=maker, json={"assigned_to": checker_id}))
        assert client.post(f"/api/v1/r9-platform/alerts/{alert_id}/resolve", headers=checker, json={"resolution_notes":"short"}).status_code == 422
        ok(client.post(f"/api/v1/r9-platform/alerts/{alert_id}/resolve", headers=checker,
                       json={"resolution_notes":"Evidence reviewed and the control was completed"}))
        reopened = ok(client.post("/api/v1/r9-platform/controls/scan?company_id=1", headers=maker))
        assert reopened["created_alerts"] == 1  # unresolved source condition reopens the same fingerprint

        # Workbook is staged then validated; maker cannot approve their own batch.
        content = xlsx([["code", "name", "vat_number"], ["SUP-1", "Supplier One", "310123456789003"]])
        staged = ok(client.post("/api/v1/r9-platform/imports/stage?company_id=1&target_type=SUPPLIERS",
            headers=maker, files={"file": ("suppliers.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}), 201)
        batch_id = staged["id"]
        assert "no master" in staged["message"].lower()
        validated = ok(client.post(f"/api/v1/r9-platform/imports/{batch_id}/validate", headers=maker))
        assert validated["status"] == "VALIDATED" and validated["invalid_rows"] == 0
        assert client.post(f"/api/v1/r9-platform/imports/{batch_id}/approve", headers=maker).status_code == 409
        approved = ok(client.post(f"/api/v1/r9-platform/imports/{batch_id}/approve", headers=checker))
        assert approved["status"] == "APPROVED_STAGING_ONLY" and approved["posted_to_master"] is False
        preview = ok(client.get(f"/api/v1/r9-platform/imports/{batch_id}", headers=checker))
        assert preview["posted_to_master"] is False and preview["rows"][0]["status"] == "VALID"
        unbalanced = xlsx([["account_code", "debit", "credit"], ["1100", 100, 0], ["2100", 0, 90]])
        bad_batch = ok(client.post("/api/v1/r9-platform/imports/stage?company_id=1&target_type=OPENING_BALANCES",
            headers=maker, files={"file": ("opening.xlsx", unbalanced, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}), 201)
        bad_validation = ok(client.post(f"/api/v1/r9-platform/imports/{bad_batch['id']}/validate", headers=maker))
        assert bad_validation["status"] == "VALIDATION_FAILED" and bad_validation["summary"]["batch_errors"]

        # ZATCA register cannot claim production; generated evidence remains sandbox-only.
        readiness = ok(client.put("/api/v1/r9-platform/zatca/readiness?company_id=1", headers=checker, json={
            "onboarding_status":"SANDBOX_READY", "seller_identity_ready":True,
            "certificate_configured":True, "signing_key_configured":True, "sdk_validation_ready":True,
        }))
        assert readiness["environment"] == "SANDBOX" and readiness["production_connected"] is False
        assert client.put("/api/v1/r9-platform/zatca/readiness?company_id=1", headers=checker,
                          json={"onboarding_status":"PRODUCTION_CONNECTED"}).status_code == 422
        document = ok(client.post("/api/v1/r9-platform/zatca/documents?company_id=1", headers=checker, json={
            "source_type":"SALES_INVOICE", "source_id":"INV-100", "seller_name":"R9 Company",
            "vat_number":"310123456789003", "issue_datetime":"2026-08-09T12:00:00+03:00",
            "total_with_vat":"115.00", "vat_total":"15.00", "canonical_xml":"<Invoice><ID>INV-100</ID></Invoice>",
        }), 201)
        assert document["validation_status"] == "INTERNALLY_VALIDATED"
        assert document["submission_status"] == "NOT_SUBMITTED" and document["production_connected"] is False
        evidence = ok(client.post(f"/api/v1/r9-platform/zatca/documents/{document['id']}/sandbox-evidence", headers=checker,
                                  json={"correlation_id":"sandbox-test-100", "result":"SANDBOX_ACCEPTED"}))
        assert evidence["environment"] == "SANDBOX" and evidence["production_connected"] is False
        assert client.post("/api/v1/r9-platform/zatca/documents?company_id=1", headers=checker, json={
            "source_type":"SALES_INVOICE", "source_id":"INV-NAIVE", "seller_name":"R9 Company",
            "vat_number":"310123456789003", "issue_datetime":"2026-08-09T12:00:00",
            "total_with_vat":"115", "vat_total":"15", "canonical_xml":"<Invoice><ID>INV-NAIVE</ID></Invoice>",
        }).status_code == 422

    print("CORVAX R9 PLATFORM CYCLE: PASS")


if __name__ == "__main__": main()
