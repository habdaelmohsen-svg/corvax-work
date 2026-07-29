"""CORVAX RC13 restaurant operations and POS completion verification."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v113.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v113-restaurant-pos"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["APP_VERSION"] = "1.0.0-agreement-completion-rc27.4"
os.environ["ENABLE_RATE_LIMIT_TESTING"] = "true"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    BankAccount, Branch, DeliveryPlatform, Item, MenuItem, Role, User, UserCompanyRole, Warehouse,
)

PASSWORD = "Corvax@123"
COMPANY_ID = 3


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def ok(response):
    assert response.status_code in {200, 201, 202}, response.text
    return response.json()


def create_users() -> None:
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
        assert role
        for email, name in [
            ("rc13-reviewer@corvaxplatform.com", "RC13 Reviewer"),
            ("rc13-approver@corvaxplatform.com", "RC13 Approver"),
        ]:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(name_ar=name, name_en=name, email=email, password_hash=hash_password(PASSWORD), active=True)
                db.add(user); db.flush()
                db.add(UserCompanyRole(user_id=user.id, company_id=COMPANY_ID, role_id=role.id))
        db.commit()


def main() -> None:
    with TestClient(app) as client:
        create_users()
        admin = login(client, "admin@corvaxplatform.com")
        reviewer = login(client, "rc13-reviewer@corvaxplatform.com")
        approver = login(client, "rc13-approver@corvaxplatform.com")
        admin_json = {**admin, "Content-Type": "application/json"}
        reviewer_json = {**reviewer, "Content-Type": "application/json"}

        with SessionLocal() as db:
            branch = db.scalar(select(Branch).where(Branch.company_id == COMPANY_ID, Branch.active.is_(True)))
            warehouse = db.scalar(select(Warehouse).where(Warehouse.company_id == COMPANY_ID, Warehouse.active.is_(True)))
            bank = db.scalar(select(BankAccount).where(BankAccount.company_id == COMPANY_ID, BankAccount.active.is_(True)))
            platform = db.scalar(select(DeliveryPlatform).where(DeliveryPlatform.company_id == COMPANY_ID, DeliveryPlatform.active.is_(True)))
            menu = db.scalar(select(MenuItem).where(MenuItem.company_id == COMPANY_ID, MenuItem.active.is_(True)))
            raw_item = db.scalar(select(Item).where(Item.company_id == COMPANY_ID, Item.code == "RAW-001"))
            assert branch and warehouse and bank and platform and menu and raw_item
            branch_id, warehouse_id, bank_id = branch.id, warehouse.id, bank.id
            platform_id, menu_id, raw_item_id = platform.id, menu.id, raw_item.id
            commission_rate = Decimal(str(platform.commission_rate))

        table = ok(client.post("/api/v1/restaurant/tables", headers=admin_json, json={
            "company_id": COMPANY_ID, "branch_id": branch_id, "code": "T-RC13-01",
            "name_ar": "طاولة اختبار 1", "name_en": "RC13 Table 1", "area": "MAIN", "capacity": 4,
        }))
        reservation = ok(client.post("/api/v1/restaurant/reservations", headers=admin_json, json={
            "company_id": COMPANY_ID, "branch_id": branch_id, "table_id": table["id"],
            "customer_name": "عميل اختبار", "mobile": "0500000000", "guest_count": 2,
            "reservation_at": "2026-07-16T19:00:00", "duration_minutes": 90, "notes": "RC13 verification",
        }))
        station = ok(client.post("/api/v1/restaurant/kitchen/stations", headers=admin_json, json={
            "company_id": COMPANY_ID, "branch_id": branch_id, "code": "HOT-RC13",
            "name_ar": "المطبخ الساخن", "name_en": "Hot Kitchen", "sequence": 1,
        }))
        ok(client.post("/api/v1/restaurant/kitchen/menu-station", headers=admin_json, json={
            "menu_item_id": menu_id, "kitchen_station_id": station["id"],
        }))
        shift = ok(client.post("/api/v1/restaurant/cashier-shifts/open", headers=admin_json, json={
            "company_id": COMPANY_ID, "branch_id": branch_id, "bank_account_id": bank_id,
            "business_date": "2026-07-16", "opening_balance": 100,
        }))
        cash_order = ok(client.post("/api/v1/pos/orders", headers=admin_json, json={
            "company_id": COMPANY_ID, "order_date": "2026-07-16", "warehouse_id": warehouse_id,
            "branch_id": branch_id, "order_type": "DINE_IN", "table_id": table["id"],
            "reservation_id": reservation["id"], "cashier_shift_id": shift["id"], "guest_count": 2,
            "payment_channel": "CASH", "bank_account_id": bank_id,
            "lines": [{"menu_item_id": menu_id, "quantity": 2}],
        }))
        assert cash_order["order_type"] == "DINE_IN" and cash_order["table_id"] == table["id"]

        tickets = ok(client.get(f"/api/v1/restaurant/kitchen/tickets?company_id={COMPANY_ID}", headers=admin))
        assert len(tickets) == 1 and tickets[0]["status"] == "NEW"
        ticket_id = tickets[0]["id"]
        for status in ["ACCEPTED", "PREPARING", "READY", "SERVED"]:
            ticket = ok(client.patch(f"/api/v1/restaurant/kitchen/tickets/{ticket_id}/status", headers=admin_json, json={"status": status}))
            assert ticket["status"] == status

        control = ok(client.post(f"/api/v1/restaurant/orders/{cash_order['id']}/controls", headers=admin_json, json={
            "request_type": "RETURN", "reason": "Customer changed one item", "restore_inventory": False,
            "lines": [{"pos_order_line_id": cash_order["lines"][0]["id"] if "id" in cash_order["lines"][0] else 1, "quantity": 1}],
        }))
        assert client.post(f"/api/v1/restaurant/controls/{control['id']}/approve", headers=admin).status_code == 409
        approved_control = ok(client.post(f"/api/v1/restaurant/controls/{control['id']}/approve", headers=reviewer))
        assert approved_control["status"] == "APPROVED_POSTED" and Decimal(str(approved_control["refund_total"])) > 0

        ok(client.post(f"/api/v1/restaurant/orders/{cash_order['id']}/complete-service", headers=admin))
        expected_cash = Decimal("100") + Decimal(str(cash_order["total"])) - Decimal(str(approved_control["refund_total"]))
        submitted = ok(client.post(f"/api/v1/restaurant/cashier-shifts/{shift['id']}/submit-close", headers=admin_json, json={
            "counted_cash": str(expected_cash), "notes": "Exact RC13 close",
        }))
        assert Decimal(str(submitted["variance"])) == 0
        assert client.post(f"/api/v1/restaurant/cashier-shifts/{shift['id']}/approve", headers=admin).status_code == 409
        closed = ok(client.post(f"/api/v1/restaurant/cashier-shifts/{shift['id']}/approve", headers=reviewer))
        assert closed["status"] == "CLOSED"

        offline_payload = {
            "company_id": COMPANY_ID, "device_id": "POS-DEVICE-RC13", "client_transaction_id": "OFF-RC13-001",
            "order": {
                "company_id": COMPANY_ID, "order_date": "2026-07-16", "warehouse_id": warehouse_id,
                "branch_id": branch_id, "order_type": "DELIVERY", "payment_channel": "DELIVERY",
                "platform_id": platform_id, "lines": [{"menu_item_id": menu_id, "quantity": 1}],
            },
        }
        offline = ok(client.post("/api/v1/restaurant/offline/sync", headers=admin_json, json=offline_payload))
        assert offline["status"] == "PROCESSED" and offline["order"]["sync_status"] == "OFFLINE_SYNCED"
        duplicate = ok(client.post("/api/v1/restaurant/offline/sync", headers=admin_json, json=offline_payload))
        assert duplicate["order"]["id"] == offline["order"]["id"]

        # Offline orders must enter the same KDS workflow; complete their tickets before final summary.
        offline_tickets = ok(client.get(f"/api/v1/restaurant/kitchen/tickets?company_id={COMPANY_ID}", headers=admin))
        for ticket_row in [row for row in offline_tickets if row["order_id"] == offline["order"]["id"] and row["status"] not in {"SERVED", "CANCELLED"}]:
            for status in ("ACCEPTED", "PREPARING", "READY", "SERVED"):
                ticket_row = ok(client.patch(f"/api/v1/restaurant/kitchen/tickets/{ticket_row['id']}/status", headers=admin_json, json={"status": status}))

        gross = Decimal(str(offline["order"]["total"]))
        commission = (gross * commission_rate / Decimal("100")).quantize(Decimal("0.01"))
        received = gross - commission
        settlement = ok(client.post("/api/v1/restaurant/settlements", headers=admin_json, json={
            "company_id": COMPANY_ID, "platform_id": platform_id, "bank_account_id": bank_id,
            "settlement_reference": "SET-RC13-001", "settlement_date": "2026-07-16",
            "period_start": "2026-07-16", "period_end": "2026-07-16",
            "order_ids": [offline["order"]["id"]], "other_fees": 0, "received_net": str(received),
        }))
        assert Decimal(str(settlement["variance"])) == 0
        assert client.post(f"/api/v1/restaurant/settlements/{settlement['id']}/review", headers=admin).status_code == 409
        reviewed = ok(client.post(f"/api/v1/restaurant/settlements/{settlement['id']}/review", headers=reviewer))
        assert reviewed["status"] == "REVIEWED"
        assert client.post(f"/api/v1/restaurant/settlements/{settlement['id']}/approve", headers=reviewer).status_code == 409
        settled = ok(client.post(f"/api/v1/restaurant/settlements/{settlement['id']}/approve", headers=approver))
        assert settled["status"] == "APPROVED_POSTED"

        waste = ok(client.post("/api/v1/restaurant/waste", headers=admin_json, json={
            "company_id": COMPANY_ID, "branch_id": branch_id, "warehouse_id": warehouse_id,
            "item_id": raw_item_id, "waste_date": "2026-07-16", "quantity": 1,
            "reason_code": "EXPIRED", "reason": "RC13 controlled waste test",
        }))
        assert client.post(f"/api/v1/restaurant/waste/{waste['id']}/approve", headers=admin).status_code == 409
        approved_waste = ok(client.post(f"/api/v1/restaurant/waste/{waste['id']}/approve", headers=reviewer))
        assert approved_waste["status"] == "APPROVED_POSTED"

        summary = ok(client.get(f"/api/v1/restaurant/summary?company_id={COMPANY_ID}", headers=admin))
        assert summary["tables"] == 1
        assert summary["available_tables"] == 1
        assert summary["kds_open_tickets"] == 0
        assert Decimal(str(summary["approved_waste_cost"])) > 0
        assert Decimal(str(summary["settlement_variances"])) == 0

        print("CORVAX v1.0 RC13 restaurant operations and POS completion: ALL VERIFICATIONS PASSED")


if __name__ == "__main__":
    main()
