"""CORVAX RC18 AR/AP allocation and native aging verification."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v118.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-rc18-aging",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r9.4",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})

from fastapi.testclient import TestClient  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FiscalPeriod, FinancialSettlementAllocation  # noqa: E402


def d(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def ok(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


def create_sales_invoice(client, headers, customer_id, invoice_date, due_date, ref):
    row = ok(client.post("/api/v1/subledgers/sales-invoices", headers=headers, json={
        "company_id": 1, "invoice_date": invoice_date, "due_date": due_date,
        "customer_id": customer_id, "reference": ref,
        "lines": [{"description": ref, "account_code": "411010", "quantity": 1, "unit_price": 1000, "vat_rate": 15}],
    }), 201)
    return ok(client.post(f"/api/v1/subledgers/sales-invoices/{row['id']}/post", headers=headers))


def create_purchase_invoice(client, headers, supplier_id, invoice_date, due_date, ref):
    row = ok(client.post("/api/v1/subledgers/purchase-invoices", headers=headers, json={
        "company_id": 1, "invoice_date": invoice_date, "due_date": due_date,
        "supplier_id": supplier_id, "supplier_invoice_number": ref,
        "lines": [{"description": ref, "account_code": "613010", "quantity": 1, "unit_price": 1000, "vat_rate": 15}],
    }), 201)
    return ok(client.post(f"/api/v1/subledgers/purchase-invoices/{row['id']}/post", headers=headers))


def main():
    with TestClient(app) as client:
        login = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        h = {"Authorization": f"Bearer {login['access_token']}"}
        assert ok(client.get("/health"))["version"] == "1.0.0-agreement-completion-rc27.4-r9.4"
        with SessionLocal() as db:
            for period in db.query(FiscalPeriod).all():
                period.status = "OPEN"
            db.commit()

        parties = ok(client.get("/api/v1/subledgers/parties?company_id=1", headers=h))
        customer = next(x for x in parties if x["party_type"] in {"CUSTOMER", "BOTH"})
        supplier = next(x for x in parties if x["party_type"] in {"SUPPLIER", "BOTH"})
        bank = ok(client.get("/api/v1/subledgers/bank-accounts?company_id=1", headers=h))[0]

        # Four AR invoices deliberately span all practical aging ranges at 30 Sep 2026.
        for inv_date, due, ref in [
            ("2026-09-01", "2026-09-30", "AR-CURRENT"),
            ("2026-08-01", "2026-08-31", "AR-1-30"),
            ("2026-07-01", "2026-07-31", "AR-61-90"),
            ("2026-05-01", "2026-05-31", "AR-OVER-120"),
        ]:
            create_sales_invoice(client, h, customer["id"], inv_date, due, ref)

        ar_items = ok(client.get("/api/v1/subledgers/open-items?company_id=1&ledger_type=AR&as_of_date=2026-09-30", headers=h))
        assert len(ar_items) == 4 and all(d(x["original_amount"]) == Decimal("1150.00") for x in ar_items)

        receipt = ok(client.post("/api/v1/subledgers/receipts", headers=h, json={
            "company_id": 1, "receipt_date": "2026-09-15", "customer_id": customer["id"],
            "bank_account_id": bank["id"], "amount": 1700, "reference": "RC18-AR-ALLOC",
        }), 201)
        auto = ok(client.post(f"/api/v1/subledgers/receipts/{receipt['id']}/auto-allocate", headers=h))
        assert d(auto["allocated_amount"]) == Decimal("1700.00") and d(auto["unapplied_amount"]) == 0
        unapplied_receipt = ok(client.post("/api/v1/subledgers/receipts", headers=h, json={
            "company_id": 1, "receipt_date": "2026-09-20", "customer_id": customer["id"],
            "bank_account_id": bank["id"], "amount": 300, "reference": "RC18-AR-UNAPPLIED",
        }), 201)
        assert d(unapplied_receipt["unapplied_amount"]) == Decimal("300.00")
        receipt_register = ok(client.get("/api/v1/subledgers/receipts?company_id=1&include_fully_applied=false", headers=h))
        assert any(row["id"] == unapplied_receipt["id"] and d(row["unapplied_amount"]) == Decimal("300.00") for row in receipt_register)
        receipt_allocations = ok(client.get(f"/api/v1/subledgers/receipts/{receipt['id']}/allocations", headers=h))
        assert receipt_allocations and receipt_allocations[0]["ledger_type"] == "AR"

        ar = ok(client.get("/api/v1/subledgers/aging?company_id=1&ledger_type=AR&as_of_date=2026-09-30", headers=h))
        assert d(ar["gross_open_items"]) == Decimal("2900.00")
        assert d(ar["unapplied_settlements"]) == Decimal("300.00")
        assert d(ar["net_subledger_balance"]) == Decimal("2600.00")
        assert d(ar["gl_control_balance"]) == Decimal("2600.00")
        assert d(ar["reconciliation_difference"]) == 0 and ar["reconciled"] is True
        assert d(ar["buckets"]["CURRENT"]) == Decimal("1150.00")
        assert d(ar["buckets"]["1_30"]) == Decimal("1150.00")
        assert d(ar["buckets"]["61_90"]) == Decimal("600.00")
        assert d(ar["buckets"]["OVER_120"]) == 0

        # Detail the seeded AP control-account opening balance without reposting it to GL.
        ap_opening = ok(client.post("/api/v1/subledgers/open-items/opening-balances", headers=h, json={
            "company_id": 1, "ledger_type": "AP", "party_id": supplier["id"],
            "document_number": "AP-OPEN-DEMO-2026", "document_date": "2026-01-01", "due_date": "2026-01-31",
            "amount": 200000, "post_to_gl": False, "notes": "Detailed migration of existing AP control balance",
        }), 201)
        assert ap_opening["journal_id"] is None

        # AP invoice allocation, partial payment and unapplied supplier payment.
        for inv_date, due, ref in [
            ("2026-09-01", "2026-09-30", "AP-CURRENT"),
            ("2026-08-01", "2026-08-31", "AP-1-30"),
            ("2026-06-01", "2026-06-30", "AP-91-120"),
        ]:
            create_purchase_invoice(client, h, supplier["id"], inv_date, due, ref)
        payment = ok(client.post("/api/v1/subledgers/payments", headers=h, json={
            "company_id": 1, "payment_date": "2026-09-15", "supplier_id": supplier["id"],
            "bank_account_id": bank["id"], "amount": 1500, "reference": "RC18-AP-ALLOC",
        }), 201)
        ok(client.post(f"/api/v1/subledgers/payments/{payment['id']}/auto-allocate", headers=h))
        ok(client.post("/api/v1/subledgers/payments", headers=h, json={
            "company_id": 1, "payment_date": "2026-09-20", "supplier_id": supplier["id"],
            "bank_account_id": bank["id"], "amount": 200, "reference": "RC18-AP-UNAPPLIED",
        }), 201)
        ap = ok(client.get("/api/v1/subledgers/aging?company_id=1&ledger_type=AP&as_of_date=2026-09-30", headers=h))
        assert d(ap["gross_open_items"]) == Decimal("201950.00")
        assert d(ap["unapplied_settlements"]) == Decimal("200.00")
        assert d(ap["net_subledger_balance"]) == Decimal("201750.00")
        assert d(ap["gl_control_balance"]) == Decimal("201750.00")
        assert ap["reconciled"] is True

        # Detailed opening balance can post to GL and remains reconciled.
        opening = ok(client.post("/api/v1/subledgers/open-items/opening-balances", headers=h, json={
            "company_id": 1, "ledger_type": "AR", "party_id": customer["id"],
            "document_number": "AR-OPEN-2025-001", "document_date": "2026-01-01", "due_date": "2026-01-31",
            "amount": 500, "post_to_gl": True, "offset_account_code": "312010", "notes": "Detailed migrated opening item",
        }), 201)
        assert opening["source_type"] == "OPENING_BALANCE"
        ar_after_opening = ok(client.get("/api/v1/subledgers/aging?company_id=1&ledger_type=AR&as_of_date=2026-09-30", headers=h))
        assert d(ar_after_opening["reconciliation_difference"]) == 0 and ar_after_opening["reconciled"] is True

        # Reversing an allocation reopens the item and converts the same amount to unapplied cash without changing GL reconciliation.
        with SessionLocal() as db:
            allocation = db.query(FinancialSettlementAllocation).filter(FinancialSettlementAllocation.receipt_id == receipt["id"]).first()
            allocation_id = allocation.id
            allocation_amount = d(allocation.amount)
        reversed_row = ok(client.post(f"/api/v1/subledgers/allocations/{allocation_id}/reverse?reason=Incorrect+invoice+selection", headers=h))
        assert reversed_row["reversed"] is True
        ar_reversed = ok(client.get("/api/v1/subledgers/aging?company_id=1&ledger_type=AR&as_of_date=2026-09-30", headers=h))
        assert d(ar_reversed["gross_open_items"]) == d(ar_after_opening["gross_open_items"]) + allocation_amount
        assert d(ar_reversed["unapplied_settlements"]) == d(ar_after_opening["unapplied_settlements"]) + allocation_amount
        assert d(ar_reversed["reconciliation_difference"]) == 0 and ar_reversed["reconciled"] is True

        # Over-allocation is blocked.
        target = next(x for x in ok(client.get("/api/v1/subledgers/open-items?company_id=1&ledger_type=AR&as_of_date=2026-09-30", headers=h)) if d(x["outstanding_amount"]) > 0)
        blocked = client.post(f"/api/v1/subledgers/receipts/{unapplied_receipt['id']}/allocations", headers=h, json={
            "allocation_date": "2026-09-20", "allocations": [{"open_item_id": target["id"], "amount": 301}],
        })
        assert blocked.status_code == 409, blocked.text

        summary = ok(client.get("/api/v1/subledgers/summary?company_id=1", headers=h))
        assert summary["reconciliation"] == "NATIVE_OPEN_ITEM_ALLOCATION"

    print("CORVAX v1.0 RC18 AR/AP allocation and native aging: ALL VERIFICATIONS PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
