"""R7 competitive procurement employee cycle with negative-control evidence."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp/verify_r7_procurement_competitive_cycle.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}", "SECRET_KEY": "verify-r7-procurement-secret",
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
    password = "R7Procurement@123"
    ok(client.post("/api/v1/admin/users", headers=admin, json={
        "name_ar": email.split("@")[0], "name_en": email.split("@")[0],
        "email": email, "password": password, "require_password_change": False,
        "memberships": [{"company_id": 4, "role_code": role} for role in roles],
    }), 201)
    return login(client, email, password)


def main():
    with TestClient(app) as client:
        admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
        buyer = employee(client, admin, "r7.buyer@corvaxplatform.com", ["ACCOUNTANT", "CFO"])
        approver = employee(client, admin, "r7.proc.approver@corvaxplatform.com", ["CFO"])
        po_approver = employee(client, admin, "r7.po.approver@corvaxplatform.com", ["CFO"])

        suppliers = ok(client.get("/api/v1/subledgers/parties?company_id=4&party_type=SUPPLIER", headers=buyer))
        supplier_a = suppliers[0]
        supplier_b = ok(client.post("/api/v1/subledgers/parties", headers=buyer, json={
            "company_id": 4, "code": "R7-SUP-B", "name_ar": "مورد المنافسة ب",
            "name_en": "R7 Competitive Supplier B", "party_type": "SUPPLIER",
            "vat_number": "310000000000003", "credit_limit": 500000,
        }), 201)
        warehouse = ok(client.get("/api/v1/inventory/warehouses?company_id=4", headers=buyer))[0]
        raw = next(row for row in ok(client.get("/api/v1/inventory/items?company_id=4", headers=buyer)) if row["code"] == "RAW-001")

        pr = ok(client.post("/api/v1/procurement/requisitions", headers=buyer, json={
            "company_id": 4, "request_date": "2026-08-03", "needed_by": "2026-08-20",
            "warehouse_id": warehouse["id"], "department": "Production",
            "justification": "R7 production material replenishment after reorder alert",
            "lines": [{"item_id": raw["id"], "quantity": 200, "estimated_unit_price": 12, "specifications": "Lot tracked; expiry at least 12 months"}],
        }), 201)
        assert Decimal(str(pr["estimated_total"])) == Decimal("2400.00")
        ok(client.post(f"/api/v1/procurement/requisitions/{pr['id']}/submit", headers=buyer))
        assert client.post(f"/api/v1/procurement/requisitions/{pr['id']}/approve", headers=buyer).status_code == 409
        approved_pr = ok(client.post(f"/api/v1/procurement/requisitions/{pr['id']}/approve", headers=approver))
        assert approved_pr["status"] == "APPROVED" and approved_pr["approved_by"]

        one_supplier = client.post("/api/v1/procurement/rfqs", headers=buyer, json={
            "company_id": 4, "requisition_id": pr["id"], "issue_date": "2026-08-04",
            "closing_date": "2026-08-10", "supplier_ids": [supplier_a["id"]],
        })
        assert one_supplier.status_code == 422
        rfq = ok(client.post("/api/v1/procurement/rfqs", headers=buyer, json={
            "company_id": 4, "requisition_id": pr["id"], "issue_date": "2026-08-04",
            "closing_date": "2026-08-10", "supplier_ids": [supplier_a["id"], supplier_b["id"]],
        }), 201)
        assert len(rfq["suppliers"]) == 2 and len(rfq["lines"]) == 1
        rfq = ok(client.post(f"/api/v1/procurement/rfqs/{rfq['id']}/issue", headers=buyer))
        assert rfq["status"] == "ISSUED"
        rfq_line = rfq["lines"][0]

        quote_a = ok(client.post("/api/v1/procurement/quotations", headers=buyer, json={
            "company_id": 4, "rfq_id": rfq["id"], "supplier_id": supplier_a["id"],
            "supplier_reference": "SUP-A-R7-001", "quote_date": "2026-08-05", "valid_until": "2026-08-31",
            "lead_time_days": 7, "payment_terms": "30 days",
            "lines": [{"rfq_line_id": rfq_line["id"], "unit_price": 10, "vat_rate": 15}],
        }), 201)
        quote_b = ok(client.post("/api/v1/procurement/quotations", headers=buyer, json={
            "company_id": 4, "rfq_id": rfq["id"], "supplier_id": supplier_b["id"],
            "supplier_reference": "SUP-B-R7-001", "quote_date": "2026-08-05", "valid_until": "2026-08-31",
            "lead_time_days": 3, "payment_terms": "60 days",
            "lines": [{"rfq_line_id": rfq_line["id"], "unit_price": 11, "vat_rate": 15}],
        }), 201)
        assert Decimal(str(quote_a["total"])) == Decimal("2300.00")
        assert Decimal(str(quote_b["total"])) == Decimal("2530.00")
        assert client.post("/api/v1/procurement/quotations", headers=buyer, json={
            "company_id": 4, "rfq_id": rfq["id"], "supplier_id": supplier_a["id"],
            "supplier_reference": "DUP", "quote_date": "2026-08-05", "valid_until": "2026-08-31",
            "lines": [{"rfq_line_id": rfq_line["id"], "unit_price": 9, "vat_rate": 15}],
        }).status_code == 409

        comparison = ok(client.get(f"/api/v1/procurement/rfqs/{rfq['id']}/comparison", headers=approver))
        assert comparison["comparison_complete"] is True and comparison["quotations"][0]["id"] == quote_a["id"]
        assert client.post(f"/api/v1/procurement/rfqs/{rfq['id']}/award", headers=buyer, json={"quotation_id": quote_a["id"], "award_reason": "Lowest compliant offer"}).status_code == 409
        assert client.post(f"/api/v1/procurement/rfqs/{rfq['id']}/award", headers=approver, json={"quotation_id": quote_b["id"], "award_reason": "fast"}).status_code == 422
        award = ok(client.post(f"/api/v1/procurement/rfqs/{rfq['id']}/award", headers=approver, json={
            "quotation_id": quote_a["id"], "award_reason": "Lowest technically compliant total cost",
        }))
        po = award["purchase_order"]
        assert award["status"] == "AWARDED" and po["status"] == "DRAFT"
        assert client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/approve", headers=approver).status_code == 409
        approved_po = ok(client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/approve", headers=po_approver))
        assert approved_po["status"] == "APPROVED"

    print("CORVAX R7 PR -> independent approval -> two-supplier RFQ -> comparison -> award -> independent PO approval: PASS")


if __name__ == "__main__":
    main()
