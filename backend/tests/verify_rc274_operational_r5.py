"""CORVAX RC27.4 R5 verification for the owner's video and six new requests."""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp/verify_rc274_operational_r5.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-rc274-operational-r5",
    "FIELD_ENCRYPTION_KEY": "verification-field-key-corvax-operational-r5",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r5",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AssetCategory, BankAccount, CipProject, FixedAsset, JournalEntry, JournalLine,
    Party, User, VatReturnSnapshot,
)


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def main() -> None:
    with TestClient(app) as client:
        with SessionLocal() as db:
            admin_user = db.scalar(select(User).where(User.email == "admin@corvaxplatform.com"))
            assert admin_user
            admin_user.require_password_change = False
            db.execute(text("update fiscal_periods set status='OPEN'"))
            db.commit()

        login = ok(client.post("/api/v1/auth/login", json={
            "email": "admin@corvaxplatform.com", "password": "Corvax@123",
        }))
        admin = {"Authorization": f"Bearer {login['access_token']}"}
        ok(client.post("/api/v1/admin/users", headers=admin, json={
            "name_ar": "معتمد R5", "name_en": "R5 Approver",
            "email": "r5.approver@corvaxplatform.com", "password": "R5Approver@123",
            "require_password_change": False,
            "memberships": [{"company_id": 1, "role_code": "SUPER_ADMIN"}],
        }), 201)
        approver_login = ok(client.post("/api/v1/auth/login", json={
            "email": "r5.approver@corvaxplatform.com", "password": "R5Approver@123",
        }))
        approver = {"Authorization": f"Bearer {approver_login['access_token']}"}

        # 1) HR setup is available from the same operational context that requires it.
        branch = ok(client.post("/api/v1/enterprise/branches", headers=admin, json={
            "company_id": 1, "code": "R5-BR", "name_ar": "فرع تحقق R5", "city_ar": "الرياض",
        }), 201)
        center = ok(client.post("/api/v1/enterprise/cost-centers", headers=admin, json={
            "company_id": 1, "code": "R5-CC", "name_ar": "مركز مشروع R5",
        }), 201)
        shift = ok(client.post("/api/v1/hr/shifts", headers=admin, json={
            "company_id": 1, "code": "R5-DAY", "name_ar": "وردية الأحد للخميس",
            "start_time": "08:00:00", "end_time": "17:00:00",
        }), 201)
        shifts = ok(client.get("/api/v1/hr/shifts?company_id=1", headers=admin))
        stored_shift = next(row for row in shifts if row["id"] == shift["id"])
        assert stored_shift["working_days"] == "0,1,2,3,4"

        # 2) Taxpayer profile and the 16-box return are system backed. Adjustments
        # survive regeneration and feed the net VAT amount.
        profile = ok(client.put("/api/v1/compliance/vat-taxpayer-profile?company_id=1", headers=admin, json={
            "legal_name_ar": "شركة تحقق إقرار R5",
            "legal_name_en": "R5 VAT Verification Co.",
            "vat_number": "310000000000003",
            "commercial_registration": "1010000001",
            "zatca_distinguished_number": "7000000001",
            "tax_account_number": "3100000000",
            "taxpayer_identity_number": "1010000001",
            "registered_address": "الرياض، المملكة العربية السعودية",
        }))
        assert profile["zatca_distinguished_number"] == "7000000001"
        vat = ok(client.post("/api/v1/compliance/vat-return", headers=admin, json={
            "company_id": 1, "period_start": "2026-01-01", "period_end": "2026-03-31",
        }), 201)
        assert {line["box_code"] for line in vat["lines"]} >= {
            "SALES_STANDARD", "SALES_ZERO", "SALES_EXPORT", "SALES_EXEMPT",
            "PURCHASE_STANDARD", "PURCHASE_IMPORTS_CUSTOMS", "PURCHASE_REVERSE_CHARGE",
            "PURCHASE_ZERO", "PURCHASE_EXEMPT",
        }
        adjusted = ok(client.put(f"/api/v1/compliance/vat-returns/{vat['id']}/adjustments", headers=admin, json={
            "lines": [{"box_code": line["box_code"], "adjustment_base": 10 if line["box_code"] == "SALES_STANDARD" else 0} for line in vat["lines"]],
            "prior_period_correction": 5,
            "carried_forward_vat": 2,
            "adjustment_reason": "R5 controlled verification adjustment",
        }))
        sales_line = next(line for line in adjusted["lines"] if line["box_code"] == "SALES_STANDARD")
        assert Decimal(str(sales_line["adjustment_base"])) == Decimal("10.00")
        assert Decimal(str(sales_line["adjustment_tax"])) == Decimal("1.50")
        assert Decimal(str(adjusted["net_vat_payable"])) == (
            Decimal(str(adjusted["output_vat"])) - Decimal(str(adjusted["input_vat"])) + Decimal("5") - Decimal("2")
        )
        regenerated = ok(client.post("/api/v1/compliance/vat-return", headers=admin, json={
            "company_id": 1, "period_start": "2026-01-01", "period_end": "2026-03-31",
        }), 201)
        regenerated_sales = next(line for line in regenerated["lines"] if line["box_code"] == "SALES_STANDARD")
        assert Decimal(str(regenerated_sales["adjustment_base"])) == Decimal("10.00")
        vat_detail = ok(client.get(f"/api/v1/compliance/vat-returns/{vat['id']}", headers=admin))
        assert vat_detail["id"] == vat["id"] and len(vat_detail["lines"]) == len(vat["lines"])

        # 3) The CIP lifecycle is exercised end to end with maker-checker,
        # dimensional posting, payment caps, and post-capitalization locks.
        with SessionLocal() as db:
            supplier = db.scalar(select(Party).where(Party.company_id == 1, Party.party_type == "SUPPLIER"))
            bank = db.scalar(select(BankAccount).where(BankAccount.company_id == 1, BankAccount.gl_account_id.is_not(None)))
            category = db.scalar(select(AssetCategory).where(AssetCategory.company_id == 1, AssetCategory.active.is_(True)))
            assert supplier and bank and category
            supplier_id, bank_id, category_id = supplier.id, bank.id, category.id
        project = ok(client.post("/api/v1/cip/projects", headers=admin, json={
            "company_id": 1, "code": "R5-CIP", "name_ar": "مشروع تحقق متكامل",
            "budget_amount": 500000, "start_date": "2026-01-01",
            "expected_completion_date": "2026-12-31",
            "branch_id": branch["id"], "cost_center_id": center["id"],
        }), 201)
        contract = ok(client.post("/api/v1/cip/contracts", headers=admin, json={
            "company_id": 1, "project_id": project["id"], "party_id": supplier_id,
            "title_ar": "عقد تنفيذ R5", "title_en": "R5 Build Contract",
            "contract_value": 100000, "vat_rate": 15, "retention_rate": 5,
            "signed_date": "2026-01-05",
        }), 201)
        certificate = ok(client.post("/api/v1/cip/certificates", headers=admin, json={
            "company_id": 1, "contract_id": contract["id"], "certificate_date": "2026-02-01",
            "work_value": 40000, "supplier_invoice_number": "SUP-R5-1",
        }), 201)
        listed = ok(client.get("/api/v1/cip/certificates?company_id=1", headers=admin))
        assert any(row["id"] == certificate["id"] and row["status"] == "DRAFT" for row in listed)
        assert client.post(f"/api/v1/cip/certificates/{certificate['id']}/approve?company_id=1", headers=admin).status_code == 403
        approved = ok(client.post(f"/api/v1/cip/certificates/{certificate['id']}/approve?company_id=1", headers=approver))
        assert approved["status"] == "APPROVED"
        cost = ok(client.post("/api/v1/cip/costs", headers=admin, json={
            "company_id": 1, "project_id": project["id"], "cost_date": "2026-02-02",
            "category": "ENGINEERING", "treatment": "CAPITALIZE",
            "description_ar": "إشراف هندسي", "amount": 5000, "vat_amount": 0,
        }), 201)
        assert cost["treatment"] == "CAPITALIZE"
        too_much = client.post("/api/v1/cip/payments", headers=admin, json={
            "company_id": 1, "contract_id": contract["id"], "certificate_id": certificate["id"],
            "payment_date": "2026-03-01", "amount": 999999, "payment_kind": "CERTIFICATE",
            "bank_account_id": bank_id,
        })
        assert too_much.status_code == 422
        payment = ok(client.post("/api/v1/cip/payments", headers=admin, json={
            "company_id": 1, "contract_id": contract["id"], "certificate_id": certificate["id"],
            "payment_date": "2026-03-01", "amount": float(certificate["net_payable"]),
            "payment_kind": "CERTIFICATE", "bank_account_id": bank_id,
        }), 201)
        assert payment["journal_number"]
        statement = ok(client.get(f"/api/v1/cip/contracts/{contract['id']}/statement?company_id=1", headers=admin))
        assert statement["contract"]["id"] == contract["id"]
        assert Decimal(str(statement["work"]["certified_value"])) == Decimal("40000.00")
        assert Decimal(str(statement["money"]["paid"])) == Decimal(str(payment["amount"]))
        capitalized = ok(client.post(f"/api/v1/cip/projects/{project['id']}/capitalize", headers=approver, json={
            "company_id": 1, "ready_for_use_date": "2026-04-01", "asset_category_id": category_id,
            "useful_life_months": 60, "residual_value": 0, "depreciation_method": "STRAIGHT_LINE",
            "bank_account_id": bank_id,
        }))
        assert capitalized["status"] == "CAPITALIZED" and capitalized["asset_number"]
        assert client.post("/api/v1/cip/costs", headers=admin, json={
            "company_id": 1, "project_id": project["id"], "cost_date": "2026-04-02",
            "category": "MATERIALS", "description_ar": "تكلفة بعد الإقفال", "amount": 1,
        }).status_code == 409
        assert client.post("/api/v1/cip/certificates", headers=admin, json={
            "company_id": 1, "contract_id": contract["id"], "certificate_date": "2026-04-02",
            "work_value": 1,
        }).status_code == 409

        # 4) Report categories and navigation placement match the owner's request.
        catalog = ok(client.get("/api/v1/system-reports/catalog?company_id=1", headers=admin))
        by_code = {report["code"]: report for report in catalog["reports"]}
        assert catalog["report_count"] == 57
        assert by_code["SAL-04"]["category"] == "SALES"
        assert by_code["PUR-02"]["category"] == "PURCHASES"
        assert by_code["FS-01"]["category"] == "FINANCIAL"

        # 5) Foundation and binary templates are not merely present in routing:
        # they must resolve for the active tenant and produce usable files.
        company_chart = ok(client.get("/api/v1/enterprise/companies/1/chart-of-accounts", headers=admin))
        assert company_chart and any(row["code"] == "111010" for row in company_chart)
        foundation = ok(client.get("/api/v1/enterprise/companies/1/foundation-summary", headers=admin))
        assert foundation["company_id"] == 1 and foundation["accounts"] > 0
        opening_template = client.get("/api/v1/opening-balances/template.xlsx?company_id=1", headers=admin)
        assert opening_template.status_code == 200
        assert opening_template.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert len(opening_template.content) > 1000

        with SessionLocal() as db:
            stored_project = db.get(CipProject, project["id"])
            assert stored_project.status == "CAPITALIZED" and stored_project.fixed_asset_id
            assert db.get(FixedAsset, stored_project.fixed_asset_id)
            journals = db.scalars(select(JournalEntry).where(
                JournalEntry.reference.in_([certificate["number"], f"CIPCOST-{stored_project.code}", stored_project.code])
            )).all()
            assert journals
            journal_id = journals[0].id
            lines = db.scalars(select(JournalLine).where(JournalLine.journal_id.in_([row.id for row in journals]))).all()
            assert all(line.branch_id == branch["id"] and line.cost_center_id == center["id"] for line in lines)
            assert not db.execute(select(JournalEntry.id).where(JournalEntry.total_debit != JournalEntry.total_credit)).all()
            assert not db.execute(text("PRAGMA foreign_key_check")).all()
            stored_vat = db.get(VatReturnSnapshot, vat["id"])
            assert stored_vat.adjustment_reason == "R5 controlled verification adjustment"
        journal_detail = ok(client.get(f"/api/v1/finance/journals/{journal_id}", headers=admin))
        assert journal_detail["id"] == journal_id and journal_detail["lines"]
        assert Decimal(str(journal_detail["total_debit"])) == Decimal(str(journal_detail["total_credit"]))

    # 5) Structural UI gates cover the video search bug and the exact four-page form.
    workspace = (PROJECT_DIR / "frontend/src/dashboard/workspacePage.tsx").read_text(encoding="utf-8")
    navigation = (PROJECT_DIR / "frontend/src/dashboard/navigation.tsx").read_text(encoding="utf-8")
    reports = (PROJECT_DIR / "frontend/src/dashboard/reportsCenterPage.tsx").read_text(encoding="utf-8")
    hr = (PROJECT_DIR / "frontend/src/dashboard/hrRealPage.tsx").read_text(encoding="utf-8")
    vat_page = (PROJECT_DIR / "frontend/src/dashboard/vatReturnPage.tsx").read_text(encoding="utf-8")
    assert "window.location.hash.split('?')" in workspace and "vatReturn" in workspace
    assert "{ key: 'vatReturn'" in navigation
    assert "{ key: 'finance'" not in navigation and "{ key: 'aging'" not in navigation
    assert "initialCategory" in reports
    assert "'setup'" in hr and "createBranch" in hr and "createCenter" in hr and "createShift" in hr
    assert all(f"page-{page}.png" in vat_page for page in range(1, 5))
    assert "مسودة داخلية" in vat_page and "NOT FILED" in vat_page

    print("CORVAX RC27.4 R5: VIDEO, VAT, HR SETUP, REPORT PLACEMENT AND CIP LIFECYCLE VERIFIED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
