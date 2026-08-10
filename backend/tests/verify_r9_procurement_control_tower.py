"""R9 procurement control tower, supplier profile, duplicate and SoD evidence."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp/verify_r9_procurement_control_tower.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}", "SECRET_KEY": "verify-r9-procurement-secret",
    "SEED_DEMO_DATA": "true", "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1", "ENABLE_RATE_LIMIT_TESTING": "true",
})

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def login(client, email, password):
    row = ok(client.post("/api/v1/auth/login", json={"email": email, "password": password}))
    return {"Authorization": f"Bearer {row['access_token']}"}


def employee(client, admin, email, roles):
    password = "R9Procurement@123"
    ok(client.post("/api/v1/admin/users", headers=admin, json={
        "name_ar": email.split("@")[0], "name_en": email.split("@")[0], "email": email,
        "password": password, "require_password_change": False,
        "memberships": [{"company_id": 4, "role_code": role} for role in roles],
    }), 201)
    return login(client, email, password)


def main():
    with TestClient(app) as client:
        admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
        maker = employee(client, admin, "r9.procurement.maker@corvaxplatform.com", ["ACCOUNTANT", "CFO"])
        checker = employee(client, admin, "r9.procurement.checker@corvaxplatform.com", ["CFO"])
        supplier = ok(client.get("/api/v1/subledgers/parties?company_id=4&party_type=SUPPLIER", headers=maker))[0]
        warehouse = ok(client.get("/api/v1/inventory/warehouses?company_id=4", headers=maker))[0]
        item = ok(client.get("/api/v1/inventory/items?company_id=4", headers=maker))[0]

        profile = ok(client.put(
            f"/api/v1/procurement/suppliers/{supplier['id']}/profile?company_id=4", headers=maker,
            json={"commercial_registration": "1010999999", "contact_name": "R9 Supplier Owner",
                  "contact_email": "supplier@example.com", "contact_phone": "+966500000000",
                  "payment_terms_days": 45, "delivery_score": 92, "quality_score": 96,
                  "price_score": 88, "rejection_rate": 1.5},
        ))
        assert profile["payment_terms_days"] == 45
        assert float(profile["overall_score"]) == 92.0

        requested = ok(client.post(
            f"/api/v1/procurement/suppliers/{supplier['id']}/iban-change?company_id=4", headers=maker,
            json={"iban": "SA0380000000608010167519", "reason": "Verified supplier bank letter received"},
        ))
        assert requested["iban_status"] == "PENDING_APPROVAL"
        assert requested["pending_iban_masked"].endswith("7519")
        assert client.post(f"/api/v1/procurement/suppliers/{supplier['id']}/iban-change/approve?company_id=4", headers=maker).status_code == 409
        approved = ok(client.post(f"/api/v1/procurement/suppliers/{supplier['id']}/iban-change/approve?company_id=4", headers=checker))
        assert approved["iban_status"] == "APPROVED" and approved["approved_iban_masked"].endswith("7519")

        pr = ok(client.post("/api/v1/procurement/requisitions", headers=maker, json={
            "company_id": 4, "request_date": "2026-08-09", "needed_by": "2026-08-20",
            "warehouse_id": warehouse["id"], "suggested_supplier_id": supplier["id"],
            "department": "Production", "justification": "R9 control tower integration test",
            "lines": [{"item_id": item["id"], "quantity": 5, "estimated_unit_price": 20}],
        }), 201)
        center = ok(client.get("/api/v1/procurement/workflow-center?company_id=4", headers=checker))
        tracked = next(x for x in center["rows"] if x["requisition"]["id"] == pr["id"])
        assert tracked["stage"] == "REQUISITION" and tracked["current_owner"] == "REQUESTER"
        assert tracked["requisition"]["path"].endswith(str(pr["id"]))
        assert "stalled_days" in tracked and "control_flags" in tracked

        invoice_number = "SUP-R9-DUP-0001"
        ok(client.post("/api/v1/subledgers/purchase-invoices", headers=maker, json={
            "company_id": 4, "invoice_date": "2026-07-15", "due_date": "2026-08-29",
            "supplier_id": supplier["id"], "supplier_invoice_number": invoice_number,
            "lines": [{"description": "R9 duplicate guard", "account_code": "613010",
                       "quantity": 1, "unit_price": 100, "vat_rate": 15}],
        }), 201)
        risk = ok(client.get(
            f"/api/v1/procurement/suppliers/{supplier['id']}/invoice-risk?company_id=4&invoice_number={invoice_number}&amount=115",
            headers=checker,
        ))
        assert risk["duplicate"] is True and risk["blocking"] is True and risk["match_count"] == 1
        bypass = client.post("/api/v1/subledgers/purchase-invoices", headers=maker, json={
            "company_id": 4, "invoice_date": "2026-07-16", "due_date": "2026-08-30",
            "supplier_id": supplier["id"], "supplier_invoice_number": f"  {invoice_number.lower()}  ",
            "lines": [{"description": "Direct API bypass attempt", "account_code": "613010",
                       "quantity": 1, "unit_price": 100, "vat_rate": 15}],
        })
        assert bypass.status_code == 409, bypass.text

    print("CORVAX R9 PROCUREMENT CONTROL TOWER + SUPPLIER SOD + DUPLICATE GUARD: PASS")


if __name__ == "__main__":
    main()
