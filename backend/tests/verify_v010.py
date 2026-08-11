"""End-to-end verification for CORVAX v0.10 financial and subledger core."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v010.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key"
os.environ["SEED_DEMO_DATA"] = "true"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    assert client.get("/health").json()["version"] == "1.0.0-agreement-completion-rc27.4-r9.2"
    assert len(client.get("/api/v1/companies", headers=admin).json()) == 4

    create_user = client.post(
        "/api/v1/admin/users",
        headers=admin,
        json={
            "name_ar": "المدير المالي التجريبي",
            "name_en": "Demo CFO",
            "email": "cfo@corvaxplatform.com",
            "password": "CfoSecure@123",
            "require_password_change": False, "memberships": [{"company_id": 1, "role_code": "CFO"}],
        },
    )
    assert create_user.status_code == 201, create_user.text
    cfo = login(client, "cfo@corvaxplatform.com", "CfoSecure@123")

    manual_journal = {
        "company_id": 1,
        "entry_date": "2026-07-12",
        "reference": "VERIFY-001",
        "description": "Verification utility expense",
        "cash_flow_activity": "OPERATING",
        "cash_flow_kind": "OTHER_OPERATING_PAYMENTS",
        "lines": [
            {"account_code": "613010", "debit": 1250, "credit": 0},
            {"account_code": "111010", "debit": 0, "credit": 1250},
        ],
    }
    draft = client.post("/api/v1/finance/journals", headers=cfo, json=manual_journal)
    assert draft.status_code == 201 and draft.json()["status"] == "DRAFT", draft.text
    journal_id = draft.json()["id"]
    assert client.post(f"/api/v1/finance/journals/{journal_id}/submit", headers=cfo).json()["status"] == "PENDING_APPROVAL"
    assert client.post(f"/api/v1/finance/journals/{journal_id}/approve", headers=cfo).status_code == 409
    assert client.post(f"/api/v1/finance/journals/{journal_id}/approve", headers=admin).json()["status"] == "APPROVED"
    assert client.post(f"/api/v1/finance/journals/{journal_id}/post", headers=admin).json()["status"] == "POSTED"

    parties = client.get("/api/v1/subledgers/parties?company_id=1", headers=admin).json()
    banks = client.get("/api/v1/subledgers/bank-accounts?company_id=1", headers=admin).json()
    customer = next(row for row in parties if row["party_type"] == "CUSTOMER")
    supplier = next(row for row in parties if row["party_type"] == "SUPPLIER")
    bank = banks[0]

    sales = client.post(
        "/api/v1/subledgers/sales-invoices",
        headers=admin,
        json={
            "company_id": 1,
            "invoice_date": "2026-07-12",
            "due_date": "2026-08-11",
            "customer_id": customer["id"],
            "reference": "VERIFY-SALE",
            "lines": [{"description": "Operating sale", "account_code": "411010", "quantity": 2, "unit_price": 1000, "vat_rate": 15}],
        },
    )
    assert sales.status_code == 201 and sales.json()["total"] == 2300
    assert client.post(f"/api/v1/subledgers/sales-invoices/{sales.json()['id']}/post", headers=admin).status_code == 200
    assert client.post(
        "/api/v1/subledgers/receipts",
        headers=admin,
        json={"company_id": 1, "receipt_date": "2026-07-12", "customer_id": customer["id"], "bank_account_id": bank["id"], "amount": 2300, "reference": "VERIFY-RECEIPT"},
    ).status_code == 201

    purchase = client.post(
        "/api/v1/subledgers/purchase-invoices",
        headers=admin,
        json={
            "company_id": 1,
            "invoice_date": "2026-07-12",
            "due_date": "2026-08-11",
            "supplier_id": supplier["id"],
            "supplier_invoice_number": "VERIFY-PI-001",
            "lines": [{"description": "Utilities", "account_code": "613010", "quantity": 1, "unit_price": 1000, "vat_rate": 15}],
        },
    )
    assert purchase.status_code == 201 and purchase.json()["total"] == 1150
    assert client.post(f"/api/v1/subledgers/purchase-invoices/{purchase.json()['id']}/post", headers=admin).status_code == 200
    assert client.post(
        "/api/v1/subledgers/payments",
        headers=admin,
        json={"company_id": 1, "payment_date": "2026-07-12", "supplier_id": supplier["id"], "bank_account_id": bank["id"], "amount": 1150, "reference": "VERIFY-PAYMENT"},
    ).status_code == 201

    subledger = client.get("/api/v1/subledgers/summary?company_id=1", headers=admin).json()
    assert subledger["reconciliation"] == "NATIVE_OPEN_ITEM_ALLOCATION"
    assert subledger["sales_invoices"] == 1 and subledger["purchase_invoices"] == 1

    trial_balance = client.get("/api/v1/finance/trial-balance?company_id=1", headers=admin).json()
    assert trial_balance["balanced"] is True
    statements = client.get("/api/v1/finance/statements?company_id=1&method=direct", headers=admin).json()
    assert statements["source"] == "POSTED_GENERAL_LEDGER"
    assert statements["financial_position"]["balanced"] is True

    closed_period = {**manual_journal, "entry_date": "2026-06-12", "reference": "VERIFY-CLOSED"}
    assert client.post("/api/v1/finance/journals", headers=admin, json=closed_period).status_code == 422
    assert len(client.get("/api/v1/audit-log?company_id=1", headers=admin).json()) >= 12
    assert client.get("/").status_code == 200

print("CORVAX v0.10 financial and subledger core: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
