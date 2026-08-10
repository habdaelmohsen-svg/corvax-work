"""R9 end-to-end gate: mobile inspected PO receipt and operational alerts."""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_r9_inventory_mobile.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}", "SECRET_KEY": "r9-mobile-inventory-secret",
    "SEED_DEMO_DATA": "true", "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
})
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FiscalPeriod, GoodsReceipt, Item, Party, PurchaseOrderLine, Role, StockMovement, User, UserCompanyRole, Warehouse  # noqa: E402
from app.models.inbound_shipment import MobileReceiptInspection  # noqa: E402

PASSWORD = "Corvax@123"


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def login(client, email):
    data = ok(client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}))
    return {"Authorization": f"Bearer {data['access_token']}"}


def main():
    with TestClient(app) as client:
        with SessionLocal() as db:
            for period in db.scalars(select(FiscalPeriod)).all():
                period.status = "OPEN"
            role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
            reviewer = User(name_ar="مستلم مستودع R9", name_en="R9 Warehouse Receiver",
                            email="r9-warehouse@corvaxplatform.com",
                            password_hash=hash_password(PASSWORD), active=True)
            db.add(reviewer); db.flush()
            db.add(UserCompanyRole(user_id=reviewer.id, company_id=1, role_id=role.id))
            item = db.scalar(select(Item).where(Item.company_id == 1, Item.active.is_(True)))
            warehouse = db.scalar(select(Warehouse).where(Warehouse.company_id == 1, Warehouse.active.is_(True)))
            supplier = db.scalar(select(Party).where(Party.company_id == 1, Party.party_type.in_(["SUPPLIER", "BOTH"])))
            item.reorder_level = Decimal("500")
            ids = {"item": item.id, "warehouse": warehouse.id, "supplier": supplier.id}
            code = item.code
            db.commit()

        admin = login(client, "admin@corvaxplatform.com")
        receiver = login(client, "r9-warehouse@corvaxplatform.com")
        po = ok(client.post("/api/v1/inventory/purchase-orders", headers=admin, json={
            "company_id": 1, "order_date": "2026-07-15", "expected_receipt_date": "2026-07-20",
            "supplier_id": ids["supplier"], "warehouse_id": ids["warehouse"],
            "lines": [{"item_id": ids["item"], "quantity": 10, "unit_price": 12, "vat_rate": 15}],
        }), 201)
        ok(client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/approve", headers=receiver))
        scan_contract = ok(client.get(
            f"/api/v1/inventory/mobile-receipts/purchase-orders/{po['id']}?company_id=1", headers=receiver))
        assert scan_contract["lines"][0]["barcode_expected"] == code

        body = {"company_id": 1, "purchase_order_id": po["id"], "receipt_date": "2026-07-31", "lines": [{
            "purchase_order_line_id": po["lines"][0]["id"], "barcode_value": "WRONG-CODE",
            "accepted_quantity": 8, "rejected_quantity": 2, "rejection_reason": "Damaged cartons",
            "lot_number": "R9-LOT-001", "production_date": "2026-07-01", "expiry_date": "2026-08-10",
            "storage_location": "COLD-A-01", "evidence": [{"file_name": "inspection.jpg",
                "content_type": "image/jpeg", "size_bytes": 2048, "sha256": "a" * 64,
                "object_key": "mobile-evidence/r9/inspection.jpg"}],
        }]}
        assert client.post("/api/v1/inventory/mobile-receipts", headers=receiver, json=body).status_code == 422
        body["lines"][0]["barcode_value"] = f"CORVAX:ITEM:{code}"
        receipt = ok(client.post("/api/v1/inventory/mobile-receipts", headers=receiver, json=body), 201)
        assert receipt["po_status"] == "PARTIALLY_RECEIVED"
        assert Decimal(str(receipt["accepted_value"])) == Decimal("96.00")
        assert Decimal(str(receipt["rejected_quantity"])) == Decimal("2.0000")
        evidence = ok(client.get(
            f"/api/v1/inventory/mobile-receipts/{receipt['id']}/inspection?company_id=1", headers=receiver))
        assert evidence["lines"][0]["quality_status"] == "PARTIALLY_REJECTED"
        assert evidence["lines"][0]["evidence"][0]["sha256"] == "a" * 64

        alerts = ok(client.get("/api/v1/inventory/alerts?company_id=1&as_of=2026-07-31&expiry_days=30&slow_days=90", headers=receiver))
        types = {row["type"] for row in alerts["alerts"]}
        assert {"PO_DELAY", "LOW_STOCK", "EXPIRY"}.issubset(types), alerts

        with SessionLocal() as db:
            grn = db.scalar(select(GoodsReceipt).where(GoodsReceipt.id == receipt["id"]))
            inspection = db.scalar(select(MobileReceiptInspection).where(MobileReceiptInspection.goods_receipt_id == grn.id))
            po_line = db.scalar(select(PurchaseOrderLine).where(PurchaseOrderLine.id == po["lines"][0]["id"]))
            movement = db.scalar(select(StockMovement).where(StockMovement.reference_type == "GOODS_RECEIPT", StockMovement.reference_id == grn.id))
            assert grn and inspection and movement
            assert Decimal(inspection.accepted_quantity) == Decimal("8.0000")
            assert Decimal(inspection.rejected_quantity) == Decimal("2.0000")
            assert inspection.storage_location == "COLD-A-01" and "inspection.jpg" in inspection.evidence_metadata
            assert Decimal(po_line.received_quantity) == Decimal("8.0000")
            assert Decimal(movement.quantity) == Decimal("8.0000")  # rejected stock never enters inventory

    print("CORVAX R9 MOBILE INVENTORY + ALERTS GATE: PASS")


if __name__ == "__main__":
    main()
