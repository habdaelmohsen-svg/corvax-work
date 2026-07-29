"""End-to-end verification for CORVAX v1.0 RC4 QMS and audit integrity."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v104.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v104-qms"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import AuditLog  # noqa: E402


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client: TestClient, admin: dict[str, str], email: str, role_code: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/admin/users", headers=admin,
        json={"name_ar": role_code, "name_en": role_code, "email": email, "password": "QualitySecure@123", "require_password_change": False, "memberships": [{"company_id": 4, "role_code": role_code}]},
    )
    assert response.status_code == 201, response.text
    return login(client, email, "QualitySecure@123")


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    quality = create_user(client, admin, "quality.rc4@corvaxplatform.com", "QUALITY_MANAGER")
    auditor = create_user(client, admin, "auditor.rc4@corvaxplatform.com", "AUDITOR")

    items = client.get("/api/v1/inventory/items?company_id=4", headers=admin).json()
    parties = client.get("/api/v1/subledgers/parties?company_id=4", headers=admin).json()
    item_id = items[0]["id"]
    supplier_id = next(p["id"] for p in parties if p["party_type"] in {"SUPPLIER", "BOTH"})
    customer_id = next(p["id"] for p in parties if p["party_type"] in {"CUSTOMER", "BOTH"})

    objective = client.post("/api/v1/qms/objectives", headers=quality, json={
        "company_id": 4, "code": "QO-REJECT", "name_ar": "خفض الرفض", "name_en": "Reduce rejection",
        "metric_name": "Rejection rate", "unit": "PERCENT", "baseline_value": 3, "target_value": 1,
        "current_value": 2, "frequency": "MONTHLY", "effective_from": "2026-01-01", "effective_to": "2026-12-31"
    })
    assert objective.status_code == 201, objective.text
    assert client.post(f"/api/v1/qms/objectives/{objective.json()['id']}/approve", headers=quality).status_code == 409
    approved = client.post(f"/api/v1/qms/objectives/{objective.json()['id']}/approve", headers=auditor)
    assert approved.status_code == 200, approved.text

    plan = client.post("/api/v1/qms/inspection-plans", headers=quality, json={
        "company_id": 4, "code": "IP-FINAL", "name_ar": "فحص نهائي", "name_en": "Final inspection",
        "item_id": item_id, "inspection_stage": "FINAL", "sampling_method": "FIXED", "sample_size": 20,
        "acceptance_number": 0, "rejection_number": 1, "specification": "Approved specification", "test_method": "Visual test"
    })
    assert plan.status_code == 201, plan.text
    assert client.post(f"/api/v1/qms/inspection-plans/{plan.json()['id']}/approve", headers=auditor).status_code == 200

    action = client.post("/api/v1/qms/actions", headers=quality, json={
        "company_id": 4, "action_type": "CORRECTIVE", "source_type": "NCR", "source_id": 1,
        "title": "Seal correction", "description": "Correct seal drift", "root_cause_method": "5_WHY",
        "root_cause": "Temperature drift", "owner_user_id": 1, "due_date": "2026-12-31"
    })
    assert action.status_code == 201, action.text
    assert client.post(f"/api/v1/qms/actions/{action.json()['id']}/verify", headers=quality, json={"effectiveness_result": "EFFECTIVE", "effectiveness_notes": "Verified on three consecutive lots"}).status_code == 409
    verified = client.post(f"/api/v1/qms/actions/{action.json()['id']}/verify", headers=auditor, json={"effectiveness_result": "EFFECTIVE", "effectiveness_notes": "Verified on three consecutive lots"})
    assert verified.status_code == 200, verified.text

    complaint = client.post("/api/v1/qms/complaints", headers=quality, json={
        "company_id": 4, "received_date": "2026-07-13", "customer_id": customer_id, "item_id": item_id,
        "lot_number": "LOT-QMS-001", "channel": "DIRECT", "severity": "HIGH", "description": "Seal complaint",
        "immediate_containment": "Quarantine lot", "owner_user_id": 1, "due_date": "2026-07-31"
    })
    assert complaint.status_code == 201, complaint.text
    closed = client.post(f"/api/v1/qms/complaints/{complaint.json()['id']}/close", headers=auditor, json={"root_cause": "Incorrect setup", "resolution": "Setup locked and operator retrained"})
    assert closed.status_code == 200, closed.text

    evaluation = client.post("/api/v1/qms/supplier-evaluations", headers=quality, json={
        "company_id": 4, "supplier_id": supplier_id, "period_start": "2026-01-01", "period_end": "2026-06-30",
        "quality_score": 92, "delivery_score": 88, "documentation_score": 95, "notes": "Approved supplier"
    })
    assert evaluation.status_code == 201, evaluation.text
    assert str(evaluation.json()["overall_score"]) in {"91.40", "91.4"}
    assert evaluation.json()["classification"] == "A"

    review = client.post("/api/v1/qms/management-reviews", headers=quality, json={
        "company_id": 4, "review_date": "2026-07-13", "scope": "QMS and ISO 9001 core",
        "inputs_summary": "Objectives, complaints, supplier scores, audits and CAPA",
        "decisions": "Increase sample size for high-risk product", "improvement_opportunities": "Automate COA",
        "resource_needs": "Calibrated seal tester"
    })
    assert review.status_code == 201, review.text
    assert client.post(f"/api/v1/qms/management-reviews/{review.json()['id']}/approve", headers=quality).status_code == 409
    assert client.post(f"/api/v1/qms/management-reviews/{review.json()['id']}/approve", headers=auditor).status_code == 200

    dashboard = client.get("/api/v1/qms/dashboard?company_id=4", headers=quality)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["active_objectives"] == 1
    assert all(dashboard.json()["iso9001_core_controls"].values())

    integrity = client.get("/api/v1/audit-log/integrity?company_id=4", headers=auditor)
    assert integrity.status_code == 200, integrity.text
    assert integrity.json()["status"] == "VALID", integrity.text
    assert integrity.json()["verified_records"] >= 10

    # Deliberate tampering must be detected.
    with SessionLocal() as db:
        row = db.scalar(select(AuditLog).where(AuditLog.company_id == 4, AuditLog.record_hash.is_not(None)).order_by(AuditLog.id.asc()))
        row.after_json = '{"tampered":true}'
        db.commit()
    integrity_after = client.get("/api/v1/audit-log/integrity?company_id=4", headers=auditor)
    assert integrity_after.status_code == 200
    assert integrity_after.json()["status"] == "INVALID"
    assert integrity_after.json()["failures"]

print("CORVAX v1.0 RC4 QMS and audit integrity: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
