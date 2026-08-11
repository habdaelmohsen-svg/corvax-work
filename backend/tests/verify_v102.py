"""End-to-end verification for CORVAX v1.0 RC2 financial assurance gate."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v102.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v102-assurance"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client: TestClient, admin: dict[str, str], email: str, role_code: str, name: str) -> None:
    response = client.post(
        "/api/v1/admin/users",
        headers=admin,
        json={
            "name_ar": name,
            "name_en": name,
            "email": email,
            "password": "AssuranceSecure@123",
            "require_password_change": False, "memberships": [{"company_id": 1, "role_code": role_code}],
        },
    )
    assert response.status_code == 201, response.text


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    assert client.get("/api/v1/system/release").json()["version"] == "1.0.0-agreement-completion-rc27.4-r9.2"

    create_user(client, admin, "accountant.assurance@corvaxplatform.com", "ACCOUNTANT", "Assurance Accountant")
    create_user(client, admin, "controller.assurance@corvaxplatform.com", "FINANCIAL_CONTROLLER", "Financial Controller")
    create_user(client, admin, "cfo.assurance@corvaxplatform.com", "CFO", "Chief Financial Officer")
    create_user(client, admin, "audit.assurance@corvaxplatform.com", "AUDITOR", "Internal Auditor")

    accountant = login(client, "accountant.assurance@corvaxplatform.com", "AssuranceSecure@123")
    controller = login(client, "controller.assurance@corvaxplatform.com", "AssuranceSecure@123")
    cfo = login(client, "cfo.assurance@corvaxplatform.com", "AssuranceSecure@123")

    years = client.get("/api/v1/enterprise/companies/1/fiscal-years", headers=admin)
    assert years.status_code == 200, years.text
    year_id = years.json()[0]["id"]
    periods = client.get(f"/api/v1/enterprise/fiscal-years/{year_id}/periods", headers=admin)
    assert periods.status_code == 200, periods.text
    period_1 = next(row for row in periods.json() if row["number"] == 1)
    period_2 = next(row for row in periods.json() if row["number"] == 2)

    close_review = client.post(
        "/api/v1/period-close/review",
        headers=admin,
        json={"company_id": 1, "fiscal_period_id": period_1["id"]},
    )
    assert close_review.status_code == 201, close_review.text
    closed = client.post(f"/api/v1/period-close/{close_review.json()['id']}/close", headers=controller)
    assert closed.status_code == 200, closed.text

    review = client.post(
        "/api/v1/assurance/review",
        headers=accountant,
        json={
            "company_id": 1,
            "fiscal_period_id": period_1["id"],
            "scope": "MONTH_END",
            "materiality_amount": 100000,
            "management_representation": "Management confirms completeness of period-one records and disclosures.",
        },
    )
    assert review.status_code == 201, review.text
    payload = review.json()
    assert payload["conclusion"] in {"READY", "CONDITIONAL"}, payload
    assert not [c for c in payload["checks"] if c["blocking"] and c["status"] == "FAIL"]
    run_id = payload["id"]

    submitted = client.post(f"/api/v1/assurance/{run_id}/submit", headers=accountant)
    assert submitted.status_code == 200, submitted.text
    assert len(submitted.json()["certifications"]) == 2

    bad_certification = client.post(
        f"/api/v1/assurance/{run_id}/certify",
        headers=accountant,
        json={
            "certification_role": "FINANCIAL_CONTROLLER",
            "statement_ar": "أقر بأنني راجعت ملف التأكيد والأدلة المؤيدة ولم أجد تحريفًا جوهريًا.",
            "statement_en": "I reviewed the assurance file and supporting evidence and found no material misstatement.",
        },
    )
    assert bad_certification.status_code in {403, 409}

    controller_cert = client.post(
        f"/api/v1/assurance/{run_id}/certify",
        headers=controller,
        json={
            "certification_role": "FINANCIAL_CONTROLLER",
            "statement_ar": "أقر بأنني راجعت التسويات والقيود والقوائم والأدلة ولم أجد تحريفًا جوهريًا.",
            "statement_en": "I reviewed reconciliations, journals, statements and evidence and found no material misstatement.",
        },
    )
    assert controller_cert.status_code == 200, controller_cert.text
    assert controller_cert.json()["status"] == "CERTIFICATION_IN_PROGRESS"

    cfo_cert = client.post(
        f"/api/v1/assurance/{run_id}/certify",
        headers=cfo,
        json={
            "certification_role": "CFO",
            "statement_ar": "أعتمد القوائم المالية للفترة بعد مراجعة الأحكام والتقديرات والاستثناءات الجوهرية.",
            "statement_en": "I approve the period financial statements after reviewing material judgments, estimates and exceptions.",
        },
    )
    assert cfo_cert.status_code == 200, cfo_cert.text
    assert cfo_cert.json()["status"] == "APPROVED"

    # Strict review: a high residual risk blocks a new assurance file.
    close_review_2 = client.post(
        "/api/v1/period-close/review",
        headers=admin,
        json={"company_id": 1, "fiscal_period_id": period_2["id"]},
    )
    assert close_review_2.status_code == 201, close_review_2.text
    assert client.post(f"/api/v1/period-close/{close_review_2.json()['id']}/close", headers=controller).status_code == 200
    risk = client.post(
        "/api/v1/governance/risks",
        headers=admin,
        json={
            "company_id": 1,
            "code": "R-ASSURANCE-BLOCK",
            "title_ar": "خطر جوهري غير معالج",
            "title_en": "Untreated material risk",
            "category": "FINANCIAL_REPORTING",
            "likelihood": 4,
            "impact": 5,
            "residual_score": 20,
        },
    )
    assert risk.status_code == 201, risk.text
    blocked_review = client.post(
        "/api/v1/assurance/review",
        headers=accountant,
        json={"company_id": 1, "fiscal_period_id": period_2["id"], "scope": "MONTH_END", "materiality_amount": 100000},
    )
    assert blocked_review.status_code == 201, blocked_review.text
    assert blocked_review.json()["conclusion"] == "NOT_READY"
    blocked_submit = client.post(f"/api/v1/assurance/{blocked_review.json()['id']}/submit", headers=accountant)
    assert blocked_submit.status_code == 409

    audit_log = client.get("/api/v1/audit-log?company_id=1&limit=200", headers=admin).json()
    actions = {row["action"] for row in audit_log}
    assert "FINANCIAL_ASSURANCE_REVIEWED" in actions
    assert "FINANCIAL_ASSURANCE_CERTIFIED" in actions

print("CORVAX v1.0 RC2 financial assurance gate: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
