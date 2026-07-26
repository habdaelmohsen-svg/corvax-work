"""End-to-end verification for CORVAX v1.0 RC5 food safety and access governance."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = BACKEND_DIR / "data" / "verify_v105.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v105-food-access"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import AccessReviewItem, UserCompanyRole  # noqa: E402


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client: TestClient, admin: dict[str, str], email: str, role_code: str) -> tuple[dict[str, str], int]:
    response = client.post(
        "/api/v1/admin/users", headers=admin,
        json={"name_ar": role_code, "name_en": role_code, "email": email, "password": "SecureRole@123", "memberships": [{"company_id": 4, "role_code": role_code}]},
    )
    assert response.status_code == 201, response.text
    return login(client, email, "SecureRole@123"), response.json()["id"]


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    quality, quality_id = create_user(client, admin, "quality.rc5@corvaxplatform.com", "QUALITY_MANAGER")
    auditor, auditor_id = create_user(client, admin, "auditor.rc5@corvaxplatform.com", "AUDITOR")
    it_manager, it_id = create_user(client, admin, "it.rc5@corvaxplatform.com", "IT_MANAGER")
    cfo, cfo_id = create_user(client, admin, "cfo.rc5@corvaxplatform.com", "CFO")

    item_id = client.get("/api/v1/inventory/items?company_id=4", headers=admin).json()[0]["id"]

    plan = client.post("/api/v1/food-safety/haccp-plans", headers=quality, json={
        "company_id": 4, "code": "HACCP-COOK", "name_ar": "خطة الطهي", "name_en": "Cooking HACCP plan",
        "product_item_id": item_id, "process_scope": "Receiving, preparation, cooking and release",
        "intended_use": "Ready to consume", "target_consumer": "General public", "version": 1,
        "effective_from": "2026-07-01"
    })
    assert plan.status_code == 201, plan.text
    hazard = client.post(f"/api/v1/food-safety/haccp-plans/{plan.json()['id']}/hazards", headers=quality, json={
        "step_number": 3, "process_step": "Thermal cooking", "hazard_type": "BIOLOGICAL",
        "hazard_description": "Survival of pathogenic microorganisms", "likelihood": 4, "severity": 5,
        "preventive_controls": "Validated time and temperature control", "is_ccp": True,
        "critical_limit": "Core temperature >= 75 C for 15 seconds", "monitoring_method": "Calibrated probe",
        "monitoring_frequency": "Every batch", "corrective_action": "Continue cooking or quarantine batch",
        "verification_method": "Daily supervisor review and monthly calibration", "records_required": "Cooking log"
    })
    assert hazard.status_code == 201, hazard.text
    assert hazard.json()["risk_score"] == 20 and hazard.json()["is_ccp"] is True
    assert client.post(f"/api/v1/food-safety/haccp-plans/{plan.json()['id']}/approve", headers=quality).status_code == 409
    approved = client.post(f"/api/v1/food-safety/haccp-plans/{plan.json()['id']}/approve", headers=auditor)
    assert approved.status_code == 200, approved.text

    monitor = client.post(f"/api/v1/food-safety/haccp-hazards/{hazard.json()['id']}/monitor", headers=quality, json={
        "measured_value": "71 C", "within_critical_limit": False,
        "deviation_details": "Batch below validated cooking temperature", "immediate_correction": "Continue cooking and quarantine pending retest"
    })
    assert monitor.status_code == 201, monitor.text
    assert monitor.json()["status"] == "DEVIATION_OPEN" and monitor.json()["corrective_action_id"]
    assert client.post(f"/api/v1/food-safety/haccp-monitoring/{monitor.json()['id']}/verify", headers=quality, json={"accepted": True, "notes": "self review"}).status_code == 409
    verified = client.post(f"/api/v1/food-safety/haccp-monitoring/{monitor.json()['id']}/verify", headers=auditor, json={"accepted": True, "notes": "Deviation and correction verified"})
    assert verified.status_code == 200, verified.text

    coa = client.post("/api/v1/food-safety/coa", headers=quality, json={
        "company_id": 4, "item_id": item_id, "lot_number": "LOT-RC5-001", "issue_date": "2026-07-13",
        "expiry_date": "2027-01-13", "specification_version": "SPEC-2026-03",
        "test_results": [
            {"test": "Microbiology", "specification": "Absent", "result": "Absent", "status": "PASS"},
            {"test": "Net weight", "specification": "500 +/- 5 g", "result": "501 g", "status": "PASS"}
        ], "remarks": "Released after laboratory review"
    })
    assert coa.status_code == 201, coa.text
    assert coa.json()["conclusion"] == "PASS"
    assert client.post(f"/api/v1/food-safety/coa/{coa.json()['id']}/approve", headers=quality).status_code == 409
    assert client.post(f"/api/v1/food-safety/coa/{coa.json()['id']}/approve", headers=auditor).json()["status"] == "RELEASED"

    recall = client.post("/api/v1/food-safety/recalls", headers=quality, json={
        "company_id": 4, "recall_date": "2026-07-13", "recall_class": "CLASS_I", "item_id": item_id,
        "lot_number": "LOT-RC5-001", "reason": "Mock recall exercise for allergen control",
        "scope": "All distributed units in Medina and Dammam", "quantity_distributed": 100
    })
    assert recall.status_code == 201, recall.text
    line = client.post(f"/api/v1/food-safety/recalls/{recall.json()['id']}/lines", headers=quality, json={
        "location": "Medina DC", "quantity_distributed": 100, "quantity_recovered": 0,
        "contact_status": "PENDING", "evidence_reference": "RCL-MOCK-001"
    })
    assert line.status_code == 201, line.text
    assert client.post(f"/api/v1/food-safety/recalls/{recall.json()['id']}/approve", headers=quality).status_code == 409
    assert client.post(f"/api/v1/food-safety/recalls/{recall.json()['id']}/approve", headers=auditor).status_code == 200
    recovery = client.post(f"/api/v1/food-safety/recall-lines/{line.json()['id']}/recovery", headers=quality, json={
        "quantity_recovered": 100, "contact_status": "RECOVERED", "evidence_reference": "RECOVERY-100-UNITS"
    })
    assert recovery.status_code == 200, recovery.text
    assert float(recovery.json()["recall_effectiveness_percent"]) == 100.0
    closed = client.post(f"/api/v1/food-safety/recalls/{recall.json()['id']}/close", headers=auditor, json={"quantity_disposed": 100})
    assert closed.status_code == 200 and closed.json()["status"] == "CLOSED", closed.text

    fs_dashboard = client.get("/api/v1/food-safety/dashboard?company_id=4", headers=quality)
    assert fs_dashboard.status_code == 200, fs_dashboard.text
    assert fs_dashboard.json()["approved_haccp_plans"] == 1
    assert fs_dashboard.json()["released_coa"] == 1
    assert all(fs_dashboard.json()["iso22000_haccp_core"].values())

    # Access governance: CFO role intentionally combines journal creation, approval and posting.
    scan = client.post("/api/v1/access-governance/scan/4", headers=it_manager)
    assert scan.status_code == 200, scan.text
    assert scan.json()["new_conflicts"] >= 2
    conflicts = client.get("/api/v1/access-governance/conflicts?company_id=4&status=OPEN", headers=auditor)
    assert conflicts.status_code == 200, conflicts.text
    cfo_conflicts = [c for c in conflicts.json() if c["user_id"] == cfo_id]
    assert cfo_conflicts and any(c["severity"] == "CRITICAL" for c in cfo_conflicts)

    campaign = client.post("/api/v1/access-governance/campaigns", headers=it_manager, json={
        "company_id": 4, "name": "Q3 2026 Privileged Access Certification", "period_start": "2026-07-01",
        "period_end": "2026-09-30", "scope": "ALL_USERS"
    })
    assert campaign.status_code == 201, campaign.text
    detail = client.get(f"/api/v1/access-governance/campaigns/{campaign.json()['id']}", headers=auditor).json()
    for item in detail["items"]:
        reviewer = it_manager if item["user_id"] == auditor_id else auditor
        decision = "REVOKE" if item["user_id"] == cfo_id else "RETAIN"
        notes = "Revoke excessive CFO test access after SoD conflict scan" if decision == "REVOKE" else "Access remains appropriate for current job responsibilities"
        result = client.post(f"/api/v1/access-governance/review-items/{item['id']}/decision", headers=reviewer, json={"decision": decision, "reviewer_notes": notes})
        assert result.status_code == 200, result.text
    assert client.post(f"/api/v1/access-governance/campaigns/{campaign.json()['id']}/approve", headers=it_manager).status_code == 403
    approved_campaign = client.post(f"/api/v1/access-governance/campaigns/{campaign.json()['id']}/approve", headers=auditor)
    assert approved_campaign.status_code == 200, approved_campaign.text
    assert approved_campaign.json()["revoked_memberships"] == 1

    with SessionLocal() as db:
        assert db.scalar(select(UserCompanyRole).where(UserCompanyRole.user_id == cfo_id, UserCompanyRole.company_id == 4)) is None
        revoked_item = db.scalar(select(AccessReviewItem).where(AccessReviewItem.campaign_id == campaign.json()["id"], AccessReviewItem.user_id == cfo_id))
        assert revoked_item is not None and revoked_item.decision == "REVOKE"

    access_dashboard = client.get("/api/v1/access-governance/dashboard?company_id=4", headers=auditor)
    assert access_dashboard.status_code == 200, access_dashboard.text
    assert access_dashboard.json()["pending_access_certifications"] == 0
    assert all(access_dashboard.json()["control_framework"].values())

print("CORVAX v1.0 RC5 food safety and access governance: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
