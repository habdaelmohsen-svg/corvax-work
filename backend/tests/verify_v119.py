"""CORVAX RC19 VAT return classification and tax-code matrix verification."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v119.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-rc19-vat",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r9.4",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})

from fastapi.testclient import TestClient  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FiscalPeriod  # noqa: E402


def d(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def ok(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


def create_and_post_sales(client, headers, customer_id, code, amount, ref):
    row = ok(client.post("/api/v1/subledgers/sales-invoices", headers=headers, json={
        "company_id": 1, "invoice_date": "2026-10-10", "due_date": "2026-11-10",
        "customer_id": customer_id, "reference": ref,
        "lines": [{"description": ref, "account_code": "411010", "quantity": 1, "unit_price": amount, "tax_code": code}],
    }), 201)
    return ok(client.post(f"/api/v1/subledgers/sales-invoices/{row['id']}/post", headers=headers))


def create_and_post_purchase(client, headers, supplier_id, code, amount, ref):
    row = ok(client.post("/api/v1/subledgers/purchase-invoices", headers=headers, json={
        "company_id": 1, "invoice_date": "2026-10-12", "due_date": "2026-11-12",
        "supplier_id": supplier_id, "supplier_invoice_number": ref,
        "lines": [{"description": ref, "account_code": "613010", "quantity": 1, "unit_price": amount, "tax_code": code}],
    }), 201)
    return ok(client.post(f"/api/v1/subledgers/purchase-invoices/{row['id']}/post", headers=headers))


def main():
    with TestClient(app) as client:
        admin_login = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        admin = {"Authorization": f"Bearer {admin_login['access_token']}"}
        assert ok(client.get("/health"))["version"] == "1.0.0-agreement-completion-rc27.4-r9.4"
        with SessionLocal() as db:
            for period in db.query(FiscalPeriod).all():
                period.status = "OPEN"
            db.commit()

        created = client.post("/api/v1/admin/users", headers=admin, json={
            "name_ar": "مدير مالي RC19", "name_en": "RC19 CFO", "email": "rc19.cfo@corvaxplatform.com",
            "password": "Rc19CfoSecure@123", "require_password_change": False, "memberships": [{"company_id": 1, "role_code": "CFO"}],
        })
        assert created.status_code == 201, created.text
        cfo_login = ok(client.post("/api/v1/auth/login", json={"email": "rc19.cfo@corvaxplatform.com", "password": "Rc19CfoSecure@123"}))
        cfo = {"Authorization": f"Bearer {cfo_login['access_token']}"}

        codes = ok(client.get("/api/v1/compliance/tax-codes?company_id=1", headers=admin))
        assert {"S15", "S0", "SEX", "SE", "SOOS", "P15", "P0", "PE", "PIMP15", "PRC15", "PND15"}.issubset({x["code"] for x in codes})

        parties = ok(client.get("/api/v1/subledgers/parties?company_id=1", headers=admin))
        customer = next(x for x in parties if x["party_type"] in {"CUSTOMER", "BOTH"})
        supplier = next(x for x in parties if x["party_type"] in {"SUPPLIER", "BOTH"})

        sales_docs = {}
        for code, amount in [("S15", 1000), ("S0", 200), ("SEX", 300), ("SE", 400), ("SOOS", 500)]:
            sales_docs[code] = create_and_post_sales(client, admin, customer["id"], code, amount, f"RC19-{code}")

        # RC20+ requires approved export evidence before zero-rated exports enter the final export box.
        evidence = ok(client.post("/api/v1/operational-controls/exports/evidence", headers=admin, json={
            "company_id": 1, "sales_invoice_id": sales_docs["SEX"]["id"],
            "export_declaration_number": "EXP-RC19-REGRESSION", "export_date": "2026-10-11",
            "destination_country": "ARE", "exit_port": "Jeddah",
            "transport_document": "BL-RC19-REGRESSION", "evidence": {"exit_confirmation": True},
        }), 201)
        ok(client.post(f"/api/v1/operational-controls/exports/evidence/{evidence['id']}/submit", headers=admin))
        ok(client.post(f"/api/v1/operational-controls/exports/evidence/{evidence['id']}/approve", headers=cfo))
        for code, amount in [("P15", 1000), ("P0", 200), ("PE", 300), ("PND15", 400), ("PRC15", 500), ("PIMP15", 600)]:
            create_and_post_purchase(client, admin, supplier["id"], code, amount, f"RC19-{code}")

        vat = ok(client.post("/api/v1/compliance/vat-return", headers=admin, json={
            "company_id": 1, "period_start": "2026-10-01", "period_end": "2026-10-31",
        }), 201)
        by_box = {line["box_code"]: line for line in vat["lines"]}
        assert d(by_box["SALES_STANDARD"]["base_amount"]) == Decimal("1000.00")
        assert d(by_box["SALES_STANDARD"]["tax_amount"]) == Decimal("150.00")
        assert d(by_box["SALES_ZERO"]["base_amount"]) == Decimal("200.00")
        assert d(by_box["SALES_EXPORT"]["base_amount"]) == Decimal("300.00")
        assert d(by_box["SALES_EXEMPT"]["base_amount"]) == Decimal("400.00")
        assert d(by_box["SALES_OUT_OF_SCOPE"]["base_amount"]) == Decimal("500.00")
        assert d(by_box["PURCHASE_STANDARD"]["base_amount"]) == Decimal("1000.00")
        assert d(by_box["PURCHASE_STANDARD"]["tax_amount"]) == Decimal("150.00")
        assert d(by_box["PURCHASE_IMPORTS_CUSTOMS"]["tax_amount"]) == Decimal("90.00")
        assert d(by_box["PURCHASE_REVERSE_CHARGE"]["tax_amount"]) == Decimal("75.00")
        assert d(by_box["PURCHASE_NON_DEDUCTIBLE"]["tax_amount"]) == Decimal("60.00")
        assert d(vat["output_vat"]) == Decimal("225.00")
        assert d(vat["input_vat"]) == Decimal("315.00")
        assert d(vat["net_vat_payable"]) == Decimal("-90.00")
        assert d(vat["gl_output_vat"]) == Decimal("225.00")
        assert d(vat["gl_input_vat"]) == Decimal("315.00")
        assert vat["output_reconciled"] is True and vat["input_reconciled"] is True
        assert vat["classification_complete"] is True

        regenerated = ok(client.post("/api/v1/compliance/vat-return", headers=admin, json={
            "company_id": 1, "period_start": "2026-10-01", "period_end": "2026-10-31",
        }), 201)
        assert regenerated["id"] == vat["id"] and len(regenerated["lines"]) == len(vat["lines"])
        vat = regenerated

        submitted = ok(client.post(f"/api/v1/compliance/vat-returns/{vat['id']}/submit", headers=admin))
        assert submitted["status"] == "PENDING_APPROVAL"
        self_approval = client.post(f"/api/v1/compliance/vat-returns/{vat['id']}/approve", headers=admin)
        assert self_approval.status_code == 409, self_approval.text
        approved = ok(client.post(f"/api/v1/compliance/vat-returns/{vat['id']}/approve", headers=cfo))
        assert approved["status"] == "APPROVED"
        regenerate = client.post("/api/v1/compliance/vat-return", headers=admin, json={
            "company_id": 1, "period_start": "2026-10-01", "period_end": "2026-10-31",
        })
        assert regenerate.status_code == 409, regenerate.text

        bad = client.post("/api/v1/subledgers/sales-invoices", headers=admin, json={
            "company_id": 1, "invoice_date": "2026-10-20", "due_date": "2026-11-20", "customer_id": customer["id"],
            "lines": [{"description": "invalid direction", "account_code": "411010", "quantity": 1, "unit_price": 100, "tax_code": "P15"}],
        })
        assert bad.status_code == 422, bad.text

    print("CORVAX v1.0 RC19 VAT return classification and tax-code matrix: ALL VERIFICATIONS PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
