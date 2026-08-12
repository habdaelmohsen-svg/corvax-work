"""End-to-end verification for CORVAX v1.0 RC9 final consolidation and finance completion."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v109.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v109-finance-completion"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["APP_VERSION"] = "1.0.0-agreement-completion-rc27.4-r9.4"

import subprocess  # noqa: E402
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=BACKEND_DIR,
    check=True,
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    BusinessCombination, Company, ConsolidatedTrialBalanceRun, ConsolidationWorksheet,
    ContingentConsiderationRemeasurement, ForeignOperationDisposal,
    ForeignOperationTranslationRun, JournalEntry,
)


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client: TestClient, admin: dict[str, str], email: str, role_code: str, companies=(1, 4)) -> dict[str, str]:
    response = client.post(
        "/api/v1/admin/users", headers=admin,
        json={"name_ar": role_code, "name_en": role_code, "email": email, "password": "SecureRole@123",
              "require_password_change": False, "memberships": [{"company_id": company_id, "role_code": role_code} for company_id in companies]},
    )
    assert response.status_code == 201, response.text
    return login(client, email, "SecureRole@123")


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    preparer = create_user(client, admin, "preparer.rc9@corvaxplatform.com", "ACCOUNTANT")
    reviewer = create_user(client, admin, "reviewer.rc9@corvaxplatform.com", "FINANCIAL_CONTROLLER")
    approver = create_user(client, admin, "approver.rc9@corvaxplatform.com", "CFO")

    # Make one member a foreign operation so the final TB must use an approved IAS 21 translation.
    with SessionLocal() as db:
        foreign = db.get(Company, 4)
        foreign.currency = "USD"
        db.commit()

    group = client.post("/api/v1/fx-consolidation/groups", headers=admin, json={
        "code": "RC9-GROUP", "name_ar": "مجموعة التوحيد النهائي RC9", "name_en": "RC9 Final Consolidation Group",
        "reporting_currency": "SAR", "member_company_ids": [1, 4],
    })
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]

    # IFRS 3 business combination with liability-classified contingent consideration.
    combination = client.post("/api/v1/financial-close/business-combinations", headers=preparer, json={
        "group_id": group_id, "acquirer_company_id": 1, "acquiree_company_id": 4,
        "acquisition_date": "2026-07-31", "ownership_percent": "0.80",
        "nci_measurement_method": "PROPORTIONATE_SHARE", "consideration_cash": 700000,
        "consideration_shares": 150000, "contingent_consideration": 100000,
        "previously_held_interest_fv": 0, "tax_rate": "0.20",
        "rationale": {"control_assessment": "Board and voting control obtained", "valuation_report": "VAL-RC9-001"},
        "items": [
            {"item_code": "PPE", "item_type": "ASSET", "name_ar": "ممتلكات ومعدات", "name_en": "Property and equipment",
             "book_value": 800000, "fair_value": 1000000, "tax_base": 800000, "useful_life_months": 120,
             "evidence_reference": "PPA-PPE-RC9"},
            {"item_code": "BRAND", "item_type": "ASSET", "name_ar": "علامة تجارية", "name_en": "Brand",
             "book_value": 0, "fair_value": 250000, "tax_base": 0, "useful_life_months": 120,
             "identifiable_intangible": True, "evidence_reference": "PPA-BRAND-RC9"},
            {"item_code": "PAYABLES", "item_type": "LIABILITY", "name_ar": "التزامات تجارية", "name_en": "Trade liabilities",
             "book_value": 350000, "fair_value": 350000, "tax_base": 350000, "evidence_reference": "PPA-AP-RC9"},
        ],
    })
    assert combination.status_code == 201, combination.text
    combination_id = combination.json()["id"]
    assert client.post(f"/api/v1/financial-close/business-combinations/{combination_id}/review", headers=reviewer).status_code == 200
    approved_combination = client.post(f"/api/v1/financial-close/business-combinations/{combination_id}/approve", headers=approver)
    assert approved_combination.status_code == 200, approved_combination.text

    # Subsequent liability remeasurement: increase is posted to P&L and contingent consideration liability.
    contingent = client.post("/api/v1/finance-completion/contingent-consideration", headers=preparer, json={
        "combination_id": combination_id, "measurement_date": "2026-07-31",
        "classification": "LIABILITY", "measurement_type": "SUBSEQUENT_REMEASUREMENT",
        "opening_fair_value": 100000, "closing_fair_value": 125000,
        "evidence_reference": "FV-CC-RC9-001", "rationale": "Updated probability-weighted forecast based on approved post-acquisition performance evidence.",
    })
    assert contingent.status_code == 201, contingent.text
    contingent_id = contingent.json()["id"]
    assert Decimal(str(contingent.json()["fair_value_change"])) == Decimal("25000.00")
    assert client.post(f"/api/v1/finance-completion/contingent-consideration/{contingent_id}/review", headers=preparer).status_code in {403, 409}
    assert client.post(f"/api/v1/finance-completion/contingent-consideration/{contingent_id}/review", headers=reviewer).status_code == 200
    assert client.post(f"/api/v1/finance-completion/contingent-consideration/{contingent_id}/approve", headers=reviewer).status_code == 409
    contingent_approved = client.post(f"/api/v1/finance-completion/contingent-consideration/{contingent_id}/approve", headers=approver)
    assert contingent_approved.status_code == 200 and contingent_approved.json()["status"] == "APPROVED_POSTED", contingent_approved.text
    assert contingent_approved.json()["journal_id"] is not None

    equity_remeasurement = client.post("/api/v1/finance-completion/contingent-consideration", headers=preparer, json={
        "combination_id": combination_id, "measurement_date": "2026-07-31",
        "classification": "EQUITY", "measurement_type": "SUBSEQUENT_REMEASUREMENT",
        "opening_fair_value": 125000, "closing_fair_value": 130000,
        "evidence_reference": "FV-CC-RC9-EQ", "rationale": "Attempted equity remeasurement should be blocked by the accounting control.",
    })
    assert equity_remeasurement.status_code == 422

    # IAS 21 translation and controlled CTA recycling on a partial disposal with loss of control.
    translation = client.post("/api/v1/corporate-reporting/foreign-operation-translations", headers=preparer, json={
        "group_id": group_id, "member_company_id": 4, "period_start": "2026-01-01", "period_end": "2026-07-31",
        "closing_rate": "3.75", "average_rate": "3.70", "historical_equity_rate": "3.50",
    })
    assert translation.status_code == 201, translation.text
    translation_id = translation.json()["id"]
    assert client.post(f"/api/v1/corporate-reporting/foreign-operation-translations/{translation_id}/review", headers=reviewer).status_code == 200
    translation_approved = client.post(f"/api/v1/corporate-reporting/foreign-operation-translations/{translation_id}/approve", headers=approver)
    assert translation_approved.status_code == 200, translation_approved.text
    assert Decimal(str(translation_approved.json()["cta_amount"])) != Decimal("0.00")

    disposal = client.post("/api/v1/finance-completion/foreign-operation-disposals", headers=preparer, json={
        "translation_run_id": translation_id, "disposal_date": "2026-07-31",
        "disposal_type": "PARTIAL_LOSS_OF_CONTROL", "disposal_percent": "0.50",
        "evidence_reference": "SPA-RC9-FOREIGN-001",
        "rationale": "Approved disposal transaction results in loss of control and requires proportional CTA recycling to profit or loss.",
    })
    assert disposal.status_code == 201, disposal.text
    disposal_id = disposal.json()["id"]
    assert client.post(f"/api/v1/finance-completion/foreign-operation-disposals/{disposal_id}/review", headers=reviewer).status_code == 200
    disposal_approved = client.post(f"/api/v1/finance-completion/foreign-operation-disposals/{disposal_id}/approve", headers=approver)
    assert disposal_approved.status_code == 200 and disposal_approved.json()["status"] == "APPROVED_FOR_CONSOLIDATION", disposal_approved.text
    assert disposal_approved.json()["worksheet_id"] is not None

    # Final consolidated TB: member ledgers + approved PPA/disposal worksheets + automatic CTA balancing.
    consolidated = client.post("/api/v1/finance-completion/consolidated-trial-balances", headers=preparer, json={
        "group_id": group_id, "period_end": "2026-07-31",
    })
    assert consolidated.status_code == 201, consolidated.text
    consolidated_id = consolidated.json()["id"]
    assert Decimal(str(consolidated.json()["balance_difference"])) == Decimal("0.00")
    assert consolidated.json()["pending_worksheet_count"] == 0
    assert len(consolidated.json()["report_hash"]) == 64
    assert client.post(f"/api/v1/finance-completion/consolidated-trial-balances/{consolidated_id}/review", headers=preparer).status_code in {403, 409}
    reviewed_tb = client.post(f"/api/v1/finance-completion/consolidated-trial-balances/{consolidated_id}/review", headers=reviewer)
    assert reviewed_tb.status_code == 200 and reviewed_tb.json()["status"] == "REVIEWED", reviewed_tb.text
    assert client.post(f"/api/v1/finance-completion/consolidated-trial-balances/{consolidated_id}/approve", headers=reviewer).status_code == 409
    approved_tb = client.post(f"/api/v1/finance-completion/consolidated-trial-balances/{consolidated_id}/approve", headers=approver)
    assert approved_tb.status_code == 200 and approved_tb.json()["status"] == "APPROVED_LOCKED", approved_tb.text
    assert Decimal(str(approved_tb.json()["consolidated_debit"])) == Decimal(str(approved_tb.json()["consolidated_credit"]))

    detail = client.get(f"/api/v1/finance-completion/consolidated-trial-balances/{consolidated_id}", headers=reviewer)
    assert detail.status_code == 200 and detail.json()["integrity_valid"] is True, detail.text
    assert any(line["account_code"] == "313010" for line in detail.json()["lines"])

    dashboard = client.get("/api/v1/finance-completion/dashboard?company_id=1", headers=reviewer)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["approved_locked_consolidated_trial_balances"] == 1
    assert dashboard.json()["contingent_consideration_measurements"] == 1
    assert dashboard.json()["approved_foreign_operation_disposals"] == 1

    with SessionLocal() as db:
        assert db.get(BusinessCombination, combination_id).status == "APPROVED_FOR_CONSOLIDATION"
        cc = db.get(ContingentConsiderationRemeasurement, contingent_id)
        assert cc.journal_id is not None and db.get(JournalEntry, cc.journal_id).status == "POSTED"
        translated = db.get(ForeignOperationTranslationRun, translation_id)
        assert translated.status == "APPROVED_FOR_CONSOLIDATION"
        disposed = db.get(ForeignOperationDisposal, disposal_id)
        assert disposed.worksheet_id is not None
        assert db.get(ConsolidationWorksheet, disposed.worksheet_id).status == "APPROVED_FOR_CONSOLIDATION"
        final_run = db.get(ConsolidatedTrialBalanceRun, consolidated_id)
        assert final_run.status == "APPROVED_LOCKED"
        assert db.scalar(select(func.count()).select_from(ConsolidationWorksheet).where(ConsolidationWorksheet.group_id == group_id, ConsolidationWorksheet.status == "APPROVED_FOR_CONSOLIDATION")) >= 2

    health = client.get("/health")
    assert health.status_code == 200 and health.json()["version"] == "1.0.0-agreement-completion-rc27.4-r9.4"
    assert health.json().get("status") == "ok"
    ready = client.get("/health/ready")
    from app.core.migration_head import expected_migration_head
    assert ready.status_code == 200 and ready.json()["migration_head"] == expected_migration_head()

print("CORVAX v1.0 RC9 final consolidation and finance completion: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
