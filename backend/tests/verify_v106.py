"""End-to-end verification for CORVAX v1.0 RC6 advanced finance."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v106.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v106-advanced-finance"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import ConsolidationMember, FinancialReportRun, LeaseModification  # noqa: E402


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client: TestClient, admin: dict[str, str], email: str, role_code: str) -> tuple[dict[str, str], int]:
    response = client.post(
        "/api/v1/admin/users", headers=admin,
        json={"name_ar": role_code, "name_en": role_code, "email": email, "password": "SecureRole@123", "require_password_change": False, "memberships": [{"company_id": 4, "role_code": role_code}]},
    )
    assert response.status_code == 201, response.text
    return login(client, email, "SecureRole@123"), response.json()["id"]


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    accountant, accountant_id = create_user(client, admin, "accountant.rc6@corvaxplatform.com", "ACCOUNTANT")
    controller, controller_id = create_user(client, admin, "controller.rc6@corvaxplatform.com", "FINANCIAL_CONTROLLER")
    auditor, auditor_id = create_user(client, admin, "auditor.rc6@corvaxplatform.com", "AUDITOR")
    cfo, cfo_id = create_user(client, admin, "cfo.rc6@corvaxplatform.com", "CFO")

    # IFRS 18 mappings: bootstrap, maker-checker approval and report generation.
    bootstrap = client.post("/api/v1/advanced-finance/mappings/bootstrap", headers=controller, json={"company_id": 4})
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json()["created"] > 30
    mappings = client.get("/api/v1/advanced-finance/mappings?company_id=4", headers=accountant)
    assert mappings.status_code == 200, mappings.text
    assert len(mappings.json()) == bootstrap.json()["created"]
    first_mapping_id = mappings.json()[0]["id"]
    assert client.post(f"/api/v1/advanced-finance/mappings/{first_mapping_id}/approve", headers=controller).status_code == 409
    for mapping in mappings.json():
        approved = client.post(f"/api/v1/advanced-finance/mappings/{mapping['id']}/approve", headers=auditor)
        assert approved.status_code == 200, approved.text

    report = client.post("/api/v1/advanced-finance/reports", headers=controller, json={
        "company_id": 4,
        "start_date": "2026-01-01",
        "end_date": "2026-07-31",
        "comparative_start_date": "2025-01-01",
        "comparative_end_date": "2025-07-31"
    })
    assert report.status_code == 201, report.text
    report_data = report.json()
    assert report_data["status"] == "READY_FOR_APPROVAL", report.text
    assert report_data["validation"]["blocking_count"] == 0
    assert "operating_profit" in report_data["report"]["subtotals"]["current"]
    assert client.post(f"/api/v1/advanced-finance/reports/{report_data['id']}/approve", headers=controller).status_code == 409
    approved_report = client.post(f"/api/v1/advanced-finance/reports/{report_data['id']}/approve", headers=auditor)
    assert approved_report.status_code == 200, approved_report.text
    assert approved_report.json()["status"] == "APPROVED"

    # Disclosure workflow with mandatory note coverage and three-step control.
    mandatory_notes = [
        ("BASIS_OF_PREPARATION", "أساس الإعداد والعرض", "Basis of preparation and presentation", "IFRS 18"),
        ("SIGNIFICANT_ACCOUNTING_POLICIES", "السياسات المحاسبية الجوهرية", "Material accounting policies", "IAS 8"),
        ("REVENUE", "الإيرادات", "Revenue", "IFRS 15"),
        ("LEASES", "عقود الإيجار", "Leases", "IFRS 16"),
        ("FINANCIAL_INSTRUMENTS", "الأدوات المالية", "Financial instruments", "IFRS 7 / IFRS 9"),
        ("RELATED_PARTIES", "الأطراف ذات العلاقة", "Related parties", "IAS 24"),
        ("EVENTS_AFTER_REPORTING", "الأحداث اللاحقة", "Events after the reporting period", "IAS 10"),
    ]
    disclosure_ids = []
    for code, title_ar, title_en, standard in mandatory_notes:
        disclosure = client.post("/api/v1/advanced-finance/disclosures", headers=controller, json={
            "company_id": 4, "period_end": "2026-07-31", "note_code": code,
            "title_ar": title_ar, "title_en": title_en, "standard": standard,
            "content_ar": f"إيضاح رقابي معتمد {code} مستخرج من السجلات الداعمة.",
            "content_en": f"Controlled disclosure {code} supported by referenced records.",
            "supporting_reference": f"RC6-{code}-SUPPORT"
        })
        assert disclosure.status_code == 201, disclosure.text
        disclosure_id = disclosure.json()["id"]; disclosure_ids.append(disclosure_id)
        if code == "BASIS_OF_PREPARATION":
            assert client.post(f"/api/v1/advanced-finance/disclosures/{disclosure_id}/review", headers=controller).status_code == 409
        reviewed = client.post(f"/api/v1/advanced-finance/disclosures/{disclosure_id}/review", headers=auditor)
        assert reviewed.status_code == 200 and reviewed.json()["status"] == "REVIEWED", reviewed.text
        if code == "BASIS_OF_PREPARATION":
            assert client.post(f"/api/v1/advanced-finance/disclosures/{disclosure_id}/approve", headers=auditor).status_code == 409
        approved_note = client.post(f"/api/v1/advanced-finance/disclosures/{disclosure_id}/approve", headers=cfo)
        assert approved_note.status_code == 200 and approved_note.json()["status"] == "APPROVED", approved_note.text

    # Create and post an IFRS 16 lease through July, then perform an August modification.
    banks = client.get("/api/v1/subledgers/bank-accounts?company_id=4", headers=admin)
    assert banks.status_code == 200 and banks.json(), banks.text
    lease = client.post("/api/v1/leases", headers=admin, json={
        "company_id": 4, "name_ar": "إيجار مستودع RC6", "name_en": "RC6 warehouse lease",
        "commencement_date": "2026-07-01", "end_date": "2027-06-30",
        "payment_amount": 12000, "payment_frequency_months": 1, "payment_timing": "ARREARS",
        "annual_discount_rate": 0.06, "bank_account_id": banks.json()[0]["id"]
    })
    assert lease.status_code == 201, lease.text
    lease_id = lease.json()["id"]
    posted = client.post("/api/v1/leases/post-schedules", headers=admin, json={"company_id": 4, "as_of_date": "2026-07-31"})
    assert posted.status_code == 200 and posted.json()["posted_count"] >= 1, posted.text

    modification = client.post("/api/v1/advanced-finance/lease-modifications", headers=accountant, json={
        "lease_id": lease_id, "effective_date": "2026-07-31", "modification_type": "TERM_AND_PAYMENT",
        "new_end_date": "2027-12-31", "new_payment_amount": 13500, "new_discount_rate": 0.065,
        "reason": "Approved warehouse extension and revised commercial terms"
    })
    assert modification.status_code == 201, modification.text
    assert Decimal(str(modification.json()["rou_adjustment"])) != 0
    modification_id = modification.json()["id"]
    assert client.post(f"/api/v1/advanced-finance/lease-modifications/{modification_id}/approve", headers=accountant).status_code in {403, 409}
    approved_mod = client.post(f"/api/v1/advanced-finance/lease-modifications/{modification_id}/approve", headers=auditor)
    assert approved_mod.status_code == 200, approved_mod.text
    assert approved_mod.json()["status"] == "APPROVED_POSTED"
    assert approved_mod.json()["new_schedule_periods"] >= 11
    repost = client.post("/api/v1/leases/post-schedules", headers=admin, json={"company_id": 4, "as_of_date": "2026-07-31"})
    assert repost.status_code == 200, repost.text
    lease_disclosure = client.get("/api/v1/advanced-finance/lease-disclosures?company_id=4&as_of_date=2026-07-31", headers=controller)
    assert lease_disclosure.status_code == 200, lease_disclosure.text
    assert lease_disclosure.json()["active_leases"] >= 1
    assert Decimal(str(lease_disclosure.json()["right_of_use_assets"]["gross"])) > 0

    # Ownership and NCI analysis on a consolidation group.
    group = client.post("/api/v1/fx-consolidation/groups", headers=admin, json={
        "code": "RC6-GRP", "name_ar": "مجموعة RC6", "name_en": "RC6 Group",
        "reporting_currency": "SAR", "member_company_ids": [1, 4]
    })
    assert group.status_code == 201, group.text
    with SessionLocal() as db:
        subsidiary = db.scalar(select(ConsolidationMember).where(ConsolidationMember.group_id == group.json()["id"], ConsolidationMember.company_id == 4))
        assert subsidiary is not None
        subsidiary.ownership_percent = Decimal("80.0000")
        db.commit()
    ownership = client.get(f"/api/v1/advanced-finance/consolidation-ownership-analysis?group_id={group.json()['id']}&period_start=2026-01-01&period_end=2026-07-31", headers=admin)
    assert ownership.status_code == 200, ownership.text
    subsidiary_result = next(x for x in ownership.json()["members"] if x["company_id"] == 4)
    assert float(subsidiary_result["nci_percent"]) == 20.0

    readiness = client.get("/api/v1/advanced-finance/close-readiness?company_id=4&period_end=2026-07-31", headers=controller)
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "READY_TO_CLOSE", readiness.text
    assert all(check["passed"] for check in readiness.json()["checks"])

    with SessionLocal() as db:
        stored_report = db.get(FinancialReportRun, report_data["id"])
        stored_mod = db.get(LeaseModification, modification_id)
        assert stored_report is not None and stored_report.status == "APPROVED"
        assert stored_mod is not None and stored_mod.status == "APPROVED_POSTED" and stored_mod.journal_id is not None

print("CORVAX v1.0 RC6 advanced finance: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
