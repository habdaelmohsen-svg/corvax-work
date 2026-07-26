"""End-to-end verification for CORVAX v1.0 RC8 financial close workbench."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = BACKEND_DIR / "data" / "verify_v108.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v108-financial-close"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["APP_VERSION"] = "1.0.0-agreement-completion-rc27.3"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Account, BankAccount, BusinessCombination, ConsolidationWorksheet, FinancialEvidence,
    JournalEntry, JournalLine, LeadSchedule, LeasePartialTermination,
)


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client: TestClient, admin: dict[str, str], email: str, role_code: str, companies=(1, 4)) -> dict[str, str]:
    response = client.post(
        "/api/v1/admin/users", headers=admin,
        json={"name_ar": role_code, "name_en": role_code, "email": email, "password": "SecureRole@123",
              "memberships": [{"company_id": company_id, "role_code": role_code} for company_id in companies]},
    )
    assert response.status_code == 201, response.text
    return login(client, email, "SecureRole@123")


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    preparer = create_user(client, admin, "preparer.rc8@corvaxplatform.com", "ACCOUNTANT")
    reviewer = create_user(client, admin, "reviewer.rc8@corvaxplatform.com", "FINANCIAL_CONTROLLER")
    approver = create_user(client, admin, "approver.rc8@corvaxplatform.com", "CFO")
    consolidation_preparer = create_user(client, admin, "consol.preparer.rc8@corvaxplatform.com", "CFO")
    auditor = create_user(client, admin, "auditor.rc8@corvaxplatform.com", "AUDITOR", companies=(4,))

    # IFRS 3 PPA: 80% acquisition, proportionate NCI and a balanced system-generated consolidation worksheet.
    group = client.post("/api/v1/fx-consolidation/groups", headers=admin, json={
        "code": "RC8-GROUP", "name_ar": "مجموعة الإقفال RC8", "name_en": "RC8 Close Group",
        "reporting_currency": "SAR", "member_company_ids": [1, 4],
    })
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]
    combination = client.post("/api/v1/financial-close/business-combinations", headers=preparer, json={
        "group_id": group_id, "acquirer_company_id": 1, "acquiree_company_id": 4,
        "acquisition_date": "2026-07-31", "ownership_percent": "0.80",
        "nci_measurement_method": "PROPORTIONATE_SHARE", "consideration_cash": 700000,
        "consideration_shares": 200000, "contingent_consideration": 0,
        "previously_held_interest_fv": 0, "tax_rate": "0.20",
        "rationale": {"control_assessment": "Voting rights and board control obtained", "valuation_report": "VAL-RC8-001"},
        "items": [
            {"item_code": "PPE", "item_type": "ASSET", "name_ar": "ممتلكات ومعدات", "name_en": "Property and equipment",
             "book_value": 1000000, "fair_value": 1200000, "tax_base": 1000000, "useful_life_months": 120,
             "evidence_reference": "VAL-PPE-RC8"},
            {"item_code": "CUSTOMER-REL", "item_type": "ASSET", "name_ar": "علاقات العملاء", "name_en": "Customer relationships",
             "book_value": 0, "fair_value": 300000, "tax_base": 0, "useful_life_months": 60,
             "identifiable_intangible": True, "evidence_reference": "VAL-INT-RC8"},
            {"item_code": "PAYABLES", "item_type": "LIABILITY", "name_ar": "التزامات تجارية", "name_en": "Trade liabilities",
             "book_value": 400000, "fair_value": 400000, "tax_base": 400000, "evidence_reference": "TB-ACQUIREE-RC8"},
        ],
    })
    assert combination.status_code == 201, combination.text
    combination_id = combination.json()["id"]
    assert Decimal(str(combination.json()["identifiable_net_assets_fv"])) == Decimal("1000000.00")
    assert Decimal(str(combination.json()["nci"])) == Decimal("200000.00")
    assert Decimal(str(combination.json()["goodwill"])) == Decimal("100000.00")
    assert client.post(f"/api/v1/financial-close/business-combinations/{combination_id}/review", headers=preparer).status_code in {403, 409}
    reviewed = client.post(f"/api/v1/financial-close/business-combinations/{combination_id}/review", headers=reviewer)
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "REVIEWED", reviewed.text
    assert client.post(f"/api/v1/financial-close/business-combinations/{combination_id}/approve", headers=reviewer).status_code == 409
    approved = client.post(f"/api/v1/financial-close/business-combinations/{combination_id}/approve", headers=approver)
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED_FOR_CONSOLIDATION", approved.text
    assert Decimal(str(approved.json()["worksheet_balance"])) == Decimal("0.00")

    # Manual consolidation worksheet: source references and strict three-step approval.
    worksheet = client.post("/api/v1/financial-close/consolidation-worksheets", headers=consolidation_preparer, json={
        "group_id": group_id, "period_end": "2026-07-31", "worksheet_type": "INTERCOMPANY_PROFIT",
        "reference": "ELIM-UP-001", "description_ar": "إلغاء ربح غير محقق في المخزون", "description_en": "Eliminate unrealized inventory profit",
        "lines": [
            {"adjustment_type": "UNREALIZED_PROFIT", "account_code": "511010", "description_ar": "تكلفة المبيعات", "description_en": "Cost of sales", "debit": 25000, "credit": 0, "source_reference": "IC-MATCH-001"},
            {"adjustment_type": "UNREALIZED_PROFIT", "account_code": "113010", "description_ar": "المخزون", "description_en": "Inventory", "debit": 0, "credit": 25000, "source_reference": "IC-MATCH-001"},
        ],
    })
    assert worksheet.status_code == 201 and worksheet.json()["status"] == "READY_FOR_REVIEW", worksheet.text
    worksheet_id = worksheet.json()["id"]
    assert client.post(f"/api/v1/financial-close/consolidation-worksheets/{worksheet_id}/review", headers=reviewer).status_code == 200
    worksheet_approved = client.post(f"/api/v1/financial-close/consolidation-worksheets/{worksheet_id}/approve", headers=approver)
    assert worksheet_approved.status_code == 200 and worksheet_approved.json()["status"] == "APPROVED_FOR_CONSOLIDATION", worksheet_approved.text

    # Lead schedule tied exactly to the posted GL plus hashed PDF evidence and independent sign-off.
    with SessionLocal() as db:
        bank = db.scalar(select(Account).where(Account.company_id == 4, Account.code == "111010"))
        balance = db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(JournalEntry).where(
            JournalLine.account_id == bank.id, JournalEntry.status.in_(("POSTED", "REVERSED")), JournalEntry.entry_date <= "2026-07-31"))
        bank_balance = Decimal(balance or 0).quantize(Decimal("0.01"))
    lead = client.post("/api/v1/financial-close/lead-schedules", headers=preparer, json={
        "company_id": 4, "period_end": "2026-07-31", "code": "CASH-BANK", "title_ar": "مطابقة النقد والبنوك", "title_en": "Cash and bank reconciliation",
        "account_code_from": "111010", "account_code_to": "111010",
        "conclusion_ar": "تمت مطابقة رصيد البنك مع دفتر الأستاذ دون فروقات غير مفسرة.",
        "conclusion_en": "The bank balance was reconciled to the general ledger with no unexplained difference.",
        "items": [{"reference": "BANK-GL-001", "description_ar": "رصيد البنك الرئيسي", "description_en": "Main bank balance", "amount": str(bank_balance), "status": "CLOSED"}],
    })
    assert lead.status_code == 201 and lead.json()["status"] == "READY_FOR_REVIEW", lead.text
    lead_id = lead.json()["id"]
    assert client.post(f"/api/v1/financial-close/lead-schedules/{lead_id}/review", headers=reviewer).status_code == 409
    evidence = client.post(f"/api/v1/financial-close/lead-schedules/{lead_id}/evidence", headers=preparer,
        files={"file": ("bank_confirmation.pdf", b"%PDF-1.4\nCORVAX RC8 bank confirmation\n%%EOF", "application/pdf")})
    assert evidence.status_code == 201 and len(evidence.json()["sha256"]) == 64, evidence.text
    assert client.post(f"/api/v1/financial-close/lead-schedules/{lead_id}/review", headers=reviewer).status_code == 200
    lead_approved = client.post(f"/api/v1/financial-close/lead-schedules/{lead_id}/approve", headers=approver)
    assert lead_approved.status_code == 200 and lead_approved.json()["status"] == "APPROVED_AND_SIGNED", lead_approved.text

    # IFRS 16 partial scope decrease: carrying amounts, controlled derecognition, gain/loss and proportional future schedule update.
    with SessionLocal() as db:
        bank_account_id = db.scalar(select(BankAccount.id).where(BankAccount.company_id == 4, BankAccount.active.is_(True)))
    lease = client.post("/api/v1/leases", headers=approver, json={
        "company_id": 4, "name_ar": "عقد مستودع جزئي", "name_en": "Partial warehouse lease",
        "commencement_date": "2026-07-01", "end_date": "2027-06-30", "payment_amount": 10000,
        "payment_frequency_months": 1, "payment_timing": "ARREARS", "annual_discount_rate": "0.06", "bank_account_id": bank_account_id,
    })
    assert lease.status_code == 201, lease.text
    lease_id = lease.json()["id"]
    partial = client.post("/api/v1/financial-close/lease-partial-terminations", headers=approver, json={
        "lease_id": lease_id, "effective_date": "2026-07-15", "reduction_percent": "0.25",
        "reason": "Permanent surrender of 25 percent of the warehouse floor area.",
    })
    assert partial.status_code == 201, partial.text
    partial_id = partial.json()["id"]
    assert client.post(f"/api/v1/financial-close/lease-partial-terminations/{partial_id}/approve", headers=approver).status_code == 409
    partial_approved = client.post(f"/api/v1/financial-close/lease-partial-terminations/{partial_id}/approve", headers=auditor)
    assert partial_approved.status_code == 200 and partial_approved.json()["status"] == "APPROVED_POSTED", partial_approved.text
    assert Decimal(str(partial_approved.json()["remaining_scope"])) == Decimal("0.750000")

    dashboard = client.get("/api/v1/financial-close/dashboard?company_id=4&period_end=2026-07-31", headers=reviewer)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["approved_signed_lead_schedules"] == 1
    assert dashboard.json()["approved_partial_lease_terminations"] == 1

    with SessionLocal() as db:
        combination_row = db.get(BusinessCombination, combination_id)
        assert combination_row.worksheet_id is not None
        ppa_sheet = db.get(ConsolidationWorksheet, combination_row.worksheet_id)
        assert Decimal(ppa_sheet.total_debit) == Decimal(ppa_sheet.total_credit)
        assert db.get(LeadSchedule, lead_id).status == "APPROVED_AND_SIGNED"
        assert db.scalar(select(func.count(FinancialEvidence.id)).where(FinancialEvidence.schedule_id == lead_id)) == 1
        term = db.get(LeasePartialTermination, partial_id)
        assert term.journal_id is not None
        assert db.get(JournalEntry, term.journal_id).status == "POSTED"

    health = client.get("/health")
    assert health.status_code == 200 and health.json()["version"] == "1.0.0-agreement-completion-rc27.3"
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["migrations"] == "expected_head_e17300000001"

print("CORVAX v1.0 RC8 financial close workbench: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
