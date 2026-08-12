"""End-to-end verification for CORVAX v1.0 release candidate governance and ITSM."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v100.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v100-release-candidate"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"

import subprocess  # noqa: E402
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=BACKEND_DIR,
    check=True,
)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ready"
    assert ready.headers.get("X-Request-ID")
    assert ready.headers.get("X-Content-Type-Options") == "nosniff"
    assert client.get("/api/v1/system/release").json()["version"] == "1.0.0-agreement-completion-rc27.4-r9.4"

    create_user = client.post(
        "/api/v1/admin/users",
        headers=admin,
        json={
            "name_ar": "مدير تقنية الاختبار",
            "name_en": "Verification IT Manager",
            "email": "it.manager@corvaxplatform.com",
            "password": "ITManagerSecure@123",
            "require_password_change": False, "memberships": [{"company_id": 1, "role_code": "IT_MANAGER"}],
        },
    )
    assert create_user.status_code == 201, create_user.text
    it_user_id = create_user.json()["id"]
    it_manager = login(client, "it.manager@corvaxplatform.com", "ITManagerSecure@123")

    risk = client.post(
        "/api/v1/governance/risks",
        headers=admin,
        json={
            "company_id": 1,
            "code": "R-FIN-001",
            "title_ar": "تجاوز حدود الاعتماد المالي",
            "title_en": "Financial approval threshold override",
            "category": "FINANCIAL",
            "likelihood": 4,
            "impact": 5,
            "residual_score": 12,
            "mitigation_due_date": "2026-09-30",
        },
    )
    assert risk.status_code == 201, risk.text
    assert risk.json()["inherent_score"] == 20

    control = client.post(
        "/api/v1/governance/controls",
        headers=admin,
        json={
            "company_id": 1,
            "risk_id": risk.json()["id"],
            "code": "C-FIN-001",
            "name_ar": "فصل المنشئ عن المعتمد",
            "name_en": "Maker-checker segregation",
            "control_type": "PREVENTIVE",
            "frequency": "CONTINUOUS",
            "design_status": "EFFECTIVE",
            "operating_status": "EFFECTIVE",
        },
    )
    assert control.status_code == 201, control.text

    audit = client.post(
        "/api/v1/governance/audits",
        headers=admin,
        json={
            "company_id": 1,
            "code": "AUD-2026-001",
            "title_ar": "مراجعة دورة المصروفات",
            "title_en": "Expenditure cycle audit",
            "audit_type": "INTERNAL",
            "scope": "Budget, procurement, payments and approvals",
            "risk_rating": "HIGH",
            "planned_start": "2026-08-01",
            "planned_end": "2026-08-15",
        },
    )
    assert audit.status_code == 201, audit.text

    finding = client.post(
        "/api/v1/governance/findings",
        headers=admin,
        json={
            "company_id": 1,
            "engagement_id": audit.json()["id"],
            "code": "F-2026-001",
            "title_ar": "نقص توثيق الاستثناءات",
            "title_en": "Exception documentation gap",
            "severity": "HIGH",
            "description": "Exception approvals require supporting evidence.",
            "root_cause": "Manual handling",
            "recommendation": "Make evidence mandatory.",
            "due_date": "2026-09-01",
        },
    )
    assert finding.status_code == 201, finding.text

    action = client.post(
        f"/api/v1/governance/findings/{finding.json()['id']}/actions",
        headers=admin,
        json={"company_id": 1, "description": "Implement mandatory evidence workflow.", "due_date": "2026-09-01"},
    )
    assert action.status_code == 201, action.text
    completed = client.patch(
        f"/api/v1/governance/actions/{action.json()['id']}?company_id=1",
        headers=admin,
        json={"status": "COMPLETED", "completion_percent": 100, "evidence_reference": "EVID-001"},
    )
    assert completed.status_code == 200 and completed.json()["status"] == "COMPLETED"

    document = client.post(
        "/api/v1/governance/documents",
        headers=admin,
        json={
            "company_id": 1,
            "code": "POL-DOA",
            "title_ar": "سياسة تفويض الصلاحيات",
            "title_en": "Delegation of authority policy",
            "document_type": "POLICY",
            "version": "1.0",
            "effective_date": "2026-08-01",
            "review_date": "2027-08-01",
            "content_summary": "Approval limits, maker-checker and exceptions.",
        },
    )
    assert document.status_code == 201, document.text
    assert client.post(f"/api/v1/governance/documents/{document.json()['id']}/approve?company_id=1", headers=admin).status_code == 409

    asset = client.post(
        "/api/v1/itsm/assets",
        headers=it_manager,
        json={
            "company_id": 1,
            "asset_tag": "IT-LAP-001",
            "asset_type": "LAPTOP",
            "name": "Finance Manager Workstation",
            "serial_number": "SN-CORVAX-001",
            "criticality": "HIGH",
            "purchase_date": "2026-07-01",
            "warranty_end": "2029-06-30",
        },
    )
    assert asset.status_code == 201, asset.text

    ticket = client.post(
        "/api/v1/itsm/tickets",
        headers=it_manager,
        json={
            "company_id": 1,
            "category": "ACCESS",
            "subject": "Quarterly finance access review",
            "description": "Review privileged roles.",
            "priority": "HIGH",
            "assignee_user_id": it_user_id,
            "due_hours": 48,
        },
    )
    assert ticket.status_code == 201, ticket.text
    ticket_id = ticket.json()["id"]
    assert client.post(f"/api/v1/itsm/tickets/{ticket_id}/start?company_id=1", headers=it_manager).json()["status"] == "IN_PROGRESS"
    resolved = client.post(
        f"/api/v1/itsm/tickets/{ticket_id}/resolve?company_id=1",
        headers=it_manager,
        json={"resolution": "Privileged access reviewed and obsolete membership removed."},
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "RESOLVED"

    campaign = client.post(
        "/api/v1/crm/campaigns",
        headers=admin,
        json={"company_id": 1, "code": "CMP-2026-001", "name_ar": "حملة نمو المبيعات", "name_en": "Sales growth campaign", "channel": "DIGITAL", "budget": 25000, "start_date": "2026-08-01", "end_date": "2026-09-30"},
    )
    assert campaign.status_code == 201, campaign.text
    lead = client.post(
        "/api/v1/crm/leads",
        headers=admin,
        json={"company_id": 1, "campaign_id": campaign.json()["id"], "source": "DIGITAL", "name": "Verification Customer", "email": "verification.lead@example.com", "estimated_value": 120000},
    )
    assert lead.status_code == 201, lead.text
    opportunity = client.post(
        f"/api/v1/crm/leads/{lead.json()['id']}/convert?company_id=1",
        headers=admin,
        json={"title": "Enterprise platform opportunity", "amount": 120000, "probability": 35, "expected_close_date": "2026-10-31"},
    )
    assert opportunity.status_code == 201, opportunity.text
    won = client.patch(
        f"/api/v1/crm/opportunities/{opportunity.json()['id']}?company_id=1",
        headers=admin,
        json={"stage": "WON", "probability": 100, "amount": 120000, "expected_close_date": "2026-10-31"},
    )
    assert won.status_code == 200 and won.json()["stage"] == "WON"
    crm_summary = client.get("/api/v1/crm/summary?company_id=1", headers=admin).json()
    assert crm_summary["leads"] == 1 and float(crm_summary["won_amount"]) == 120000

    grc_summary = client.get("/api/v1/governance/summary?company_id=1", headers=admin).json()
    assert grc_summary["risks"] == 1 and grc_summary["controls"] == 1 and grc_summary["open_findings"] == 1
    itsm_summary = client.get("/api/v1/itsm/summary?company_id=1", headers=it_manager).json()
    assert itsm_summary["it_assets"] == 1 and itsm_summary["resolved_tickets"] == 1

    audit_log = client.get("/api/v1/audit-log?company_id=1&limit=100", headers=admin).json()
    actions = {row["action"] for row in audit_log}
    assert "GRC_RISK_CREATED" in actions
    assert "SERVICE_TICKET_RESOLVED" in actions
    assert "CRM_LEAD_CONVERTED" in actions
    assert "CRM_OPPORTUNITY_UPDATED" in actions

print("CORVAX v1.0 RC governance, assurance, ITSM and CRM: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
