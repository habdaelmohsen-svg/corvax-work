"""R7 employee-cycle verification for customer setup, AR settlement and search.

The scenario deliberately uses separate sales, accounting and CFO users.  It
also records invalid and duplicate master-data attempts so a green result
proves both the happy path and the expected controls.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp/verify_r7_customer_receipt_search_cycle.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-r7-customer-receipt-search",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def login(client: TestClient, identity: str, password: str) -> dict[str, str]:
    payload = ok(client.post("/api/v1/auth/login", json={"email": identity, "password": password}))
    return {"Authorization": f"Bearer {payload['access_token']}"}


def create_employee(client: TestClient, admin: dict[str, str], *, email: str, role: str, name: str) -> dict[str, str]:
    password = "R7EmployeeControl@123"
    ok(client.post("/api/v1/admin/users", headers=admin, json={
        "name_ar": name,
        "name_en": name,
        "email": email,
        "password": password,
        "require_password_change": False,
        "memberships": [{"company_id": 1, "role_code": role}],
    }), 201)
    return login(client, email, password)


def main() -> None:
    with TestClient(app) as client:
        admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
        sales = create_employee(client, admin, email="r7.sales@corvaxplatform.com", role="SALES_MANAGER", name="مدير مبيعات R7")
        accountant = create_employee(client, admin, email="r7.accountant@corvaxplatform.com", role="ACCOUNTANT", name="محاسب R7")
        cfo = create_employee(client, admin, email="r7.cfo@corvaxplatform.com", role="CFO", name="مدير مالي R7")

        invalid = client.post("/api/v1/subledgers/parties", headers=sales, json={
            "company_id": 1, "code": "R7-CUST-BAD", "name_ar": "عميل رقم ضريبي خاطئ",
            "name_en": "Invalid VAT customer", "party_type": "CUSTOMER",
            "vat_number": "1234", "credit_limit": 25000,
        })
        assert invalid.status_code == 422, invalid.text

        customer = ok(client.post("/api/v1/subledgers/parties", headers=sales, json={
            "company_id": 1, "code": "R7-CUST-001", "name_ar": "عميل المحاكاة المتكاملة",
            "name_en": "R7 Integrated Simulation Customer", "party_type": "CUSTOMER",
            "vat_number": "310000000000003", "credit_limit": 25000,
        }), 201)
        duplicate = client.post("/api/v1/subledgers/parties", headers=sales, json={
            "company_id": 1, "code": "r7-cust-001", "name_ar": "عميل مكرر",
            "name_en": "Duplicate customer", "party_type": "CUSTOMER", "credit_limit": 0,
        })
        assert duplicate.status_code == 409, duplicate.text

        # Sales owns customer setup, but cannot bypass finance and post a GL invoice.
        invoice_body = {
            "company_id": 1, "invoice_date": "2026-07-20", "due_date": "2026-08-19",
            "customer_id": customer["id"], "reference": "R7-ORDER-SEARCH-001",
            "lines": [{"description": "R7 consulting service", "account_code": "411010", "quantity": 2, "unit_price": 500, "vat_rate": 15}],
        }
        assert client.post("/api/v1/subledgers/sales-invoices", headers=sales, json=invoice_body).status_code == 403
        invoice = ok(client.post("/api/v1/subledgers/sales-invoices", headers=accountant, json=invoice_body), 201)
        assert invoice["status"] == "DRAFT" and Decimal(str(invoice["total"])) == Decimal("1150.00")
        assert client.post(f"/api/v1/subledgers/sales-invoices/{invoice['id']}/post", headers=accountant).status_code == 403
        posted = ok(client.post(f"/api/v1/subledgers/sales-invoices/{invoice['id']}/post", headers=cfo))
        assert posted["status"] == "POSTED" and posted["journal_number"]

        bank = ok(client.get("/api/v1/subledgers/bank-accounts?company_id=1", headers=cfo))[0]
        receipt = ok(client.post("/api/v1/subledgers/receipts", headers=cfo, json={
            "company_id": 1, "receipt_date": "2026-07-21", "customer_id": customer["id"],
            "bank_account_id": bank["id"], "amount": 1150, "reference": "R7-BANK-SEARCH-001",
        }), 201)
        assert Decimal(str(receipt["unapplied_amount"])) == Decimal("1150.00")
        allocation = ok(client.post(f"/api/v1/subledgers/receipts/{receipt['id']}/auto-allocate", headers=cfo))
        assert Decimal(str(allocation["allocated_amount"])) == Decimal("1150.00")
        assert Decimal(str(allocation["unapplied_amount"])) == Decimal("0.00")
        open_items = ok(client.get(f"/api/v1/subledgers/open-items?company_id=1&ledger_type=AR&party_id={customer['id']}&include_closed=true", headers=cfo))
        assert len(open_items) == 1 and open_items[0]["status"] == "CLOSED"
        assert Decimal(str(open_items[0]["outstanding_amount"])) == Decimal("0.00")

        # Role-aware global search: sales can find the customer master but not the
        # finance document; CFO can find invoice, receipt and journal references.
        sales_search = ok(client.get("/api/v1/workspace/search?company_id=1&q=R7-CUST-001", headers=sales))
        assert any(row["item_type"] == "PARTY" for row in sales_search["results"])
        assert not any(row["item_type"] in {"SALES_INVOICE", "JOURNAL_ENTRY"} for row in sales_search["results"])
        finance_search = ok(client.get("/api/v1/workspace/search?company_id=1&q=R7-ORDER-SEARCH-001", headers=cfo))
        assert any(row["item_type"] == "SALES_INVOICE" and row.get("view") == "sales" for row in finance_search["results"])
        receipt_search = ok(client.get("/api/v1/workspace/search?company_id=1&q=R7-BANK-SEARCH-001", headers=cfo))
        assert any(row["item_type"] == "RECEIPT" for row in receipt_search["results"])
        journal_search = ok(client.get(f"/api/v1/workspace/search?company_id=1&q={receipt['number']}", headers=cfo))
        assert any(row["item_type"] == "RECEIPT" for row in journal_search["results"])
        assert any(row["item_type"] == "JOURNAL_ENTRY" for row in journal_search["results"])

    print("CORVAX R7 customer -> draft invoice -> independent post -> receipt allocation -> global search: PASS")


if __name__ == "__main__":
    main()
