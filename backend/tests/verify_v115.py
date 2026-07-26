"""CORVAX RC15 gym departments, facilities and cafe end-to-end verification."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = BACKEND_DIR / "data" / "verify_v115.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-rc15",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.3",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import (
    BankAccount, Branch, GymDepartment, GymFacility, MenuItem, MembershipPlan, Role, User,
    UserCompanyRole, Warehouse,
)

PASSWORD = "Corvax@123"
COMPANY_ID = 2


def ok(response):
    assert response.status_code in {200, 201, 202}, response.text
    return response.json()


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def setup_users():
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN")); assert role
        for email, name in [
            ("rc15-reviewer@corvaxplatform.com", "RC15 Reviewer"),
            ("rc15-approver@corvaxplatform.com", "RC15 Approver"),
        ]:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(name_ar=name, name_en=name, email=email, password_hash=hash_password(PASSWORD), active=True)
                db.add(user); db.flush()
                db.add(UserCompanyRole(user_id=user.id, company_id=COMPANY_ID, role_id=role.id))
        db.commit()


def main():
    with TestClient(app) as client:
        setup_users()
        admin = login(client, "admin@corvaxplatform.com")
        reviewer = login(client, "rc15-reviewer@corvaxplatform.com")
        approver = login(client, "rc15-approver@corvaxplatform.com")
        aj = {**admin, "Content-Type": "application/json"}

        with SessionLocal() as db:
            branch = db.scalar(select(Branch).where(Branch.company_id == COMPANY_ID, Branch.active.is_(True)))
            bank = db.scalar(select(BankAccount).where(BankAccount.company_id == COMPANY_ID, BankAccount.active.is_(True)))
            warehouse = db.scalar(select(Warehouse).where(Warehouse.company_id == COMPANY_ID, Warehouse.active.is_(True)))
            plan = db.scalar(select(MembershipPlan).where(MembershipPlan.company_id == COMPANY_ID, MembershipPlan.code == "ANNUAL"))
            swim = db.scalar(select(GymDepartment).where(GymDepartment.company_id == COMPANY_ID, GymDepartment.code == "SWIM"))
            strength = db.scalar(select(GymDepartment).where(GymDepartment.company_id == COMPANY_ID, GymDepartment.code == "STRENGTH"))
            padel = db.scalar(select(GymDepartment).where(GymDepartment.company_id == COMPANY_ID, GymDepartment.code == "PADEL"))
            cafe = db.scalar(select(GymDepartment).where(GymDepartment.company_id == COMPANY_ID, GymDepartment.code == "CAFE"))
            lane = db.scalar(select(GymFacility).where(GymFacility.department_id == swim.id, GymFacility.code == "POOL-L1"))
            court = db.scalar(select(GymFacility).where(GymFacility.department_id == padel.id, GymFacility.code == "PADEL-C1"))
            coffee = db.scalar(select(MenuItem).where(MenuItem.company_id == COMPANY_ID, MenuItem.code == "GYM-COFFEE-001"))
            healthy = db.scalar(select(MenuItem).where(MenuItem.company_id == COMPANY_ID, MenuItem.code == "GYM-HEALTHY-001"))
            assert all([branch, bank, warehouse, plan, swim, strength, padel, cafe, lane, court, coffee, healthy])
            branch_id, bank_id, warehouse_id, plan_id = branch.id, bank.id, warehouse.id, plan.id
            swim_id, strength_id, padel_id, cafe_id = swim.id, strength.id, padel.id, cafe.id
            lane_id, court_id, coffee_id, healthy_id = lane.id, court.id, coffee.id, healthy.id

        member = ok(client.post("/api/v1/revenue-recognition/members", headers=aj, json={
            "company_id": COMPANY_ID, "member_number": "RC15-M1", "name_ar": "عضو أقسام", "name_en": "RC15 Department Member", "mobile": "0501515151",
        }))
        contract = ok(client.post("/api/v1/revenue-recognition/contracts", headers=aj, json={
            "company_id": COMPANY_ID, "member_id": member["id"], "plan_id": plan_id,
            "start_date": "2026-07-01", "bank_account_id": bank_id, "branch_id": branch_id,
        }))

        access = ok(client.post("/api/v1/gym/department-access", headers=aj, json={
            "company_id": COMPANY_ID, "department_id": swim_id, "member_id": member["id"],
            "contract_id": contract["id"], "occurred_at": "2026-07-16T08:00:00", "direction": "IN", "method": "QR",
        }))
        assert access["status"] == "GRANTED" and access["reason"] == "INCLUDED"

        trainer = ok(client.post("/api/v1/gym/trainers", headers=aj, json={
            "company_id": COMPANY_ID, "branch_id": branch_id, "department_id": swim_id,
            "code": "RC15-SWIM-TR", "name_ar": "مدرب سباحة", "name_en": "RC15 Swim Trainer", "commission_rate": "10",
        }))
        class_type = ok(client.post("/api/v1/gym/class-types", headers=aj, json={
            "company_id": COMPANY_ID, "department_id": swim_id, "code": "RC15-SWIM-CLASS",
            "name_ar": "تدريب سباحة", "name_en": "RC15 Swimming Class", "duration_minutes": 60, "default_capacity": 6,
        }))
        session = ok(client.post("/api/v1/gym/class-sessions", headers=aj, json={
            "company_id": COMPANY_ID, "branch_id": branch_id, "class_type_id": class_type["id"],
            "facility_id": lane_id, "trainer_id": trainer["id"], "starts_at": "2026-07-19T18:00:00", "capacity": 6,
        }))
        assert session["department_id"] == swim_id and session["facility_id"] == lane_id

        booking = ok(client.post("/api/v1/gym/facility-bookings", headers=aj, json={
            "company_id": COMPANY_ID, "facility_id": court_id, "starts_at": "2026-07-20T18:00:00",
            "ends_at": "2026-07-20T19:30:00", "participants": 4, "member_id": member["id"],
            "contract_id": contract["id"], "bank_account_id": bank_id, "notes": "RC15 padel booking",
        }))
        assert booking["status"] == "SUBMITTED" and Decimal(str(booking["net_amount"])) == Decimal("240.00")
        own_approval = client.post(f"/api/v1/gym/facility-bookings/{booking['id']}/approve", headers=admin)
        assert own_approval.status_code == 409
        approved = ok(client.post(f"/api/v1/gym/facility-bookings/{booking['id']}/approve", headers=reviewer))
        assert approved["status"] == "CONFIRMED" and approved["sale_journal_id"]
        overlapping = client.post("/api/v1/gym/facility-bookings", headers=aj, json={
            "company_id": COMPANY_ID, "facility_id": court_id, "starts_at": "2026-07-20T18:30:00",
            "ends_at": "2026-07-20T19:30:00", "participants": 2, "bank_account_id": bank_id,
        })
        assert overlapping.status_code == 409
        cancelled = ok(client.post(f"/api/v1/gym/facility-bookings/{booking['id']}/cancel", headers=approver, json={"reason": "RC15 cancellation and refund verification"}))
        assert cancelled["status"] == "CANCELLED" and cancelled["refund_journal_id"]

        cafe_order = ok(client.post("/api/v1/pos/orders", headers=aj, json={
            "company_id": COMPANY_ID, "order_date": "2026-07-16", "warehouse_id": warehouse_id,
            "branch_id": branch_id, "business_unit": "GYM_CAFE", "gym_department_id": cafe_id,
            "gym_member_id": member["id"], "payment_channel": "CARD", "bank_account_id": bank_id,
            "order_type": "TAKEAWAY", "client_order_id": "RC15-CAFE-ORDER-1",
            "lines": [{"menu_item_id": coffee_id, "quantity": "2"}, {"menu_item_id": healthy_id, "quantity": "1"}],
        }))
        assert cafe_order["business_unit"] == "GYM_CAFE" and cafe_order["gym_department_id"] == cafe_id
        prices = {line["menu_item_id"]: Decimal(str(line["unit_price"])) for line in cafe_order["lines"]}
        assert prices[coffee_id] == Decimal("15.00") and prices[healthy_id] == Decimal("28.00")

        cafe_summary = ok(client.get(f"/api/v1/pos/summary?company_id={COMPANY_ID}&business_unit=GYM_CAFE", headers=admin))
        restaurant_summary = ok(client.get(f"/api/v1/pos/summary?company_id={COMPANY_ID}", headers=admin))
        assert cafe_summary["orders"] == 1 and restaurant_summary["orders"] == 0
        commercial = ok(client.get(f"/api/v1/gym/commercial-summary?company_id={COMPANY_ID}", headers=admin))
        assert commercial["departments"] >= 4 and commercial["facilities"] >= 3 and commercial["cafe_orders"] == 1
        assert Decimal(str(commercial["cafe_gross_profit"])) > 0
        products = ok(client.get(f"/api/v1/gym/cafe/products?company_id={COMPANY_ID}", headers=admin))
        assert len(products) >= 2 and any(p["category"] == "HEALTHY_MEAL" for p in products)
        print("CORVAX v1.0 RC15 gym departments and cafe: ALL VERIFICATIONS PASSED")


if __name__ == "__main__":
    main()
