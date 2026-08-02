"""R6 AP/AR document detail and explicit payment allocation verification."""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_rc274_r6_subledger_details.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}", "SECRET_KEY": "r6-subledger-detail-secret",
    "SEED_DEMO_DATA": "true", "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
})
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FiscalPeriod  # noqa: E402


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def d(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def main() -> None:
    with TestClient(app) as client:
        login = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        h = {"Authorization": f"Bearer {login['access_token']}"}
        with SessionLocal() as db:
            for period in db.query(FiscalPeriod).all():
                period.status = "OPEN"
            db.commit()
        parties = ok(client.get("/api/v1/subledgers/parties?company_id=1", headers=h))
        customer = next(row for row in parties if row["party_type"] in {"CUSTOMER", "BOTH"})
        supplier = next(row for row in parties if row["party_type"] in {"SUPPLIER", "BOTH"})
        bank = ok(client.get("/api/v1/subledgers/bank-accounts?company_id=1", headers=h))[0]

        sales = ok(client.post("/api/v1/subledgers/sales-invoices", headers=h, json={
            "company_id": 1, "invoice_date": "2026-07-31", "due_date": "2026-08-31",
            "customer_id": customer["id"], "reference": "R6-SI-DETAIL",
            "lines": [{"description": "R6 service", "account_code": "411010", "quantity": 2, "unit_price": 500, "vat_rate": 15}],
        }), 201)
        ok(client.post(f"/api/v1/subledgers/sales-invoices/{sales['id']}/post", headers=h))
        sales_detail = ok(client.get(f"/api/v1/subledgers/sales-invoices/{sales['id']}?company_id=1", headers=h))
        assert sales_detail["id"] == sales["id"] and sales_detail["status"] == "POSTED"
        assert d(sales_detail["subtotal"]) == Decimal("1000.00") and d(sales_detail["total"]) == Decimal("1150.00")
        assert len(sales_detail["lines"]) == 1
        assert client.get(f"/api/v1/subledgers/sales-invoices/{sales['id']}?company_id=2", headers=h).status_code == 404

        purchase = ok(client.post("/api/v1/subledgers/purchase-invoices", headers=h, json={
            "company_id": 1, "invoice_date": "2026-07-31", "due_date": "2026-08-31",
            "supplier_id": supplier["id"], "supplier_invoice_number": "R6-PI-DETAIL",
            "lines": [{"description": "R6 expense", "account_code": "613010", "quantity": 1, "unit_price": 1000, "vat_rate": 15}],
        }), 201)
        ok(client.post(f"/api/v1/subledgers/purchase-invoices/{purchase['id']}/post", headers=h))
        purchase_detail = ok(client.get(f"/api/v1/subledgers/purchase-invoices/{purchase['id']}?company_id=1", headers=h))
        assert purchase_detail["id"] == purchase["id"] and purchase_detail["status"] == "POSTED"
        assert d(purchase_detail["total"]) == Decimal("1150.00")

        # Detail the seeded AP control opening balance without duplicating its GL entry.
        opening = ok(client.post("/api/v1/subledgers/open-items/opening-balances", headers=h, json={
            "company_id": 1, "ledger_type": "AP", "party_id": supplier["id"],
            "document_number": "R6-AP-OPENING", "document_date": "2026-01-01",
            "due_date": "2026-01-31", "amount": 200000, "post_to_gl": False,
            "notes": "R6 detail of seeded AP control opening balance",
        }), 201)
        assert opening["journal_id"] is None

        items = ok(client.get("/api/v1/subledgers/open-items?company_id=1&ledger_type=AP&as_of_date=2026-08-31", headers=h))
        target = next(row for row in items if row["source_id"] == purchase["id"])
        payment = ok(client.post("/api/v1/subledgers/payments", headers=h, json={
            "company_id": 1, "payment_date": "2026-08-15", "supplier_id": supplier["id"],
            "bank_account_id": bank["id"], "amount": 600, "reference": "R6-AP-MANUAL",
        }), 201)
        allocated = ok(client.post(f"/api/v1/subledgers/payments/{payment['id']}/allocations", headers=h, json={
            "allocation_date": "2026-08-15", "allocations": [{"open_item_id": target["id"], "amount": 600}],
        }))
        assert d(allocated["allocated_amount"]) == Decimal("600.00")
        allocation_rows = ok(client.get(f"/api/v1/subledgers/payments/{payment['id']}/allocations", headers=h))
        assert len(allocation_rows) == 1 and d(allocation_rows[0]["amount"]) == Decimal("600.00")
        assert allocation_rows[0]["document_number"] == purchase_detail["number"]

        # A second allocation above the payment's unapplied balance is blocked.
        blocked = client.post(f"/api/v1/subledgers/payments/{payment['id']}/allocations", headers=h, json={
            "allocation_date": "2026-08-15", "allocations": [{"open_item_id": target["id"], "amount": 1}],
        })
        assert blocked.status_code == 409

        aging = ok(client.get("/api/v1/subledgers/aging?company_id=1&ledger_type=AP&as_of_date=2026-08-31", headers=h))
        assert aging["reconciled"] is True and d(aging["reconciliation_difference"]) == 0

    DB_PATH.unlink(missing_ok=True)
    print("CORVAX RC27.4 R6 SUBLEDGER DETAILS AND PAYMENT ALLOCATION VERIFIED")


if __name__ == "__main__":
    main()
