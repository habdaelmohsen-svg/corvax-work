"""R6 end-to-end verification for traceable inventory, commissions and gym setup."""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_rc274_r6_inventory_commissions_gym.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}", "SECRET_KEY": "r6-inventory-commission-gym-secret",
    "SEED_DEMO_DATA": "true", "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
})
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account, BankAccount, Branch, CostCenter, FiscalPeriod, Item, JournalEntry, MenuItem,
    MembershipPlan, Party, Role, StockMovement, User, UserCompanyRole, Warehouse,
)

PASSWORD = "Corvax@123"


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def login(client, email):
    data = ok(client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}))
    return {"Authorization": f"Bearer {data['access_token']}"}


def setup():
    with SessionLocal() as db:
        for period in db.scalars(select(FiscalPeriod)).all():
            period.status = "OPEN"
        role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
        reviewer = User(name_ar="مراجع عمولات R6", name_en="R6 Commission Reviewer",
                        email="r6-commission-reviewer@corvaxplatform.com",
                        password_hash=hash_password(PASSWORD), active=True)
        db.add(reviewer); db.flush()
        db.add_all([UserCompanyRole(user_id=reviewer.id, company_id=1, role_id=role.id),
                    UserCompanyRole(user_id=reviewer.id, company_id=2, role_id=role.id)])
        db.commit()


def main():
    with TestClient(app) as client:
        setup()
        admin = login(client, "admin@corvaxplatform.com")
        reviewer = login(client, "r6-commission-reviewer@corvaxplatform.com")

        with SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.company_id == 1, Item.active.is_(True)))
            warehouse = db.scalar(select(Warehouse).where(Warehouse.company_id == 1, Warehouse.active.is_(True)))
            supplier = db.scalar(select(Party).where(Party.company_id == 1, Party.party_type.in_(["SUPPLIER", "BOTH"])))
            customer = db.scalar(select(Party).where(Party.company_id == 1, Party.party_type.in_(["CUSTOMER", "BOTH"])))
            bank = db.scalar(select(BankAccount).where(BankAccount.company_id == 1, BankAccount.active.is_(True)))
            branch = db.scalar(select(Branch).where(Branch.company_id == 2, Branch.active.is_(True)))
            center = db.scalar(select(CostCenter).where(CostCenter.company_id == 2, CostCenter.active.is_(True)))
            revenue = db.scalar(select(Account).where(Account.company_id == 2, Account.account_type == "REVENUE", Account.is_postable.is_(True), Account.active.is_(True)))
            plan = db.scalar(select(MembershipPlan).where(MembershipPlan.company_id == 2, MembershipPlan.active.is_(True)))
            source_menu = db.scalar(select(MenuItem).where(MenuItem.company_id == 2, MenuItem.active.is_(True)))
            menu = MenuItem(company_id=2, code="R6-CAFE-MENU", name_ar="منتج كافيه تحقق R6",
                            name_en="R6 Cafe Verification Product",
                            inventory_item_id=source_menu.inventory_item_id, recipe_bom_id=source_menu.recipe_bom_id,
                            selling_price=25, vat_rate=15, tax_code_id=source_menu.tax_code_id, active=True)
            db.add(menu); db.flush()
            assert all([item, warehouse, supplier, customer, bank, branch, center, revenue, plan, source_menu, menu])
            ids = {"item": item.id, "warehouse": warehouse.id, "supplier": supplier.id,
                   "customer": customer.id, "bank": bank.id, "branch": branch.id,
                   "center": center.id, "revenue": revenue.id, "plan": plan.id, "menu": menu.id}
            db.commit()

        # IAS 2 traceability: classify -> cost shipment -> receive -> journal/stock -> NRV.
        invalid_classification = client.post("/api/v1/inventory/items/classify", headers=admin, json={
            "company_id": 1, "item_id": ids["item"], "item_type": "RAW_MATERIAL",
            "item_subtype": "FOOD", "valuation_method": "WEIGHTED_AVERAGE", "physical_issue_method": "FEFO",
        })
        assert invalid_classification.status_code == 422
        classified = ok(client.post("/api/v1/inventory/items/classify", headers=admin, json={
            "company_id": 1, "item_id": ids["item"], "item_type": "RAW_MATERIAL",
            "item_subtype": "CORE_MATERIAL", "valuation_method": "WEIGHTED_AVERAGE", "physical_issue_method": "FEFO",
        }))
        assert classified["valuation_method"] == "WEIGHTED_AVERAGE" and classified["physical_issue_method"] == "FEFO"
        shipment = ok(client.post("/api/v1/inventory/inbound-shipments", headers=admin, json={
            "company_id": 1, "warehouse_id": ids["warehouse"], "supplier_id": ids["supplier"],
            "arrival_date": "2026-07-31", "container_number": "R6-CONT-0001",
            "packing_list_number": "R6-PL-0001", "commercial_invoice_number": "R6-CI-0001",
            "freight_cost": 100, "customs_duty": 50, "clearance_fees": 25, "other_costs": 25,
            "allocation_method": "VALUE", "lines": [{"item_id": ids["item"], "quantity": 100,
            "supplier_unit_cost": 10, "lot_number": "R6-LOT-1", "expiry_date": "2027-07-31"}],
        }), 201)
        assert shipment["status"] == "COSTED" and money(shipment["landed_cost_total"]) == Decimal("1200.00")
        detail = ok(client.get(f"/api/v1/inventory/inbound-shipments/{shipment['id']}?company_id=1", headers=admin))
        assert detail["lines"][0]["lot_number"] == "R6-LOT-1" and money(detail["lines"][0]["landed_unit_cost"]) == Decimal("12.00")
        received = ok(client.post(f"/api/v1/inventory/inbound-shipments/{shipment['id']}/receive?company_id=1", headers=admin))
        assert received["status"] == "RECEIVED" and received["journal_number"]
        assert client.post(f"/api/v1/inventory/inbound-shipments/{shipment['id']}/receive?company_id=1", headers=admin).status_code == 409
        nrv = ok(client.post("/api/v1/inventory/nrv-writedown", headers=admin, json={
            "company_id": 1, "item_id": ids["item"], "warehouse_id": ids["warehouse"],
            "nrv_per_unit": 0, "write_date": "2026-07-31",
        }))
        expected_writedown = money(Decimal(str(nrv["unit_cost"])) * Decimal(str(nrv["quantity"])))
        assert money(nrv["writedown"]) == expected_writedown > 0 and nrv["journal_number"]
        with SessionLocal() as db:
            movement = db.scalar(select(StockMovement).where(StockMovement.inbound_shipment_id == shipment["id"]))
            journal = db.scalar(select(JournalEntry).where(JournalEntry.number == received["journal_number"]))
            assert movement and money(movement.quantity) == Decimal("100.00") and money(movement.total_cost) == Decimal("1200.00")
            assert journal and money(journal.total_debit) == money(journal.total_credit) == Decimal("1200.00")

        # Commission lifecycle is tied to a posted and fully collected sales invoice.
        invoice = ok(client.post("/api/v1/subledgers/sales-invoices", headers=admin, json={
            "company_id": 1, "invoice_date": "2026-07-31", "due_date": "2026-08-31",
            "customer_id": ids["customer"], "reference": "R6-COMMISSION-SALE",
            "lines": [{"description": "Commissionable sale", "account_code": "411010", "quantity": 1, "unit_price": 1000, "vat_rate": 15}],
        }), 201)
        ok(client.post(f"/api/v1/subledgers/sales-invoices/{invoice['id']}/post", headers=admin))
        open_items = ok(client.get("/api/v1/subledgers/open-items?company_id=1&ledger_type=AR&as_of_date=2026-08-31", headers=admin))
        open_item = next(row for row in open_items if row["source_id"] == invoice["id"])
        ok(client.post("/api/v1/subledgers/receipts", headers=admin, json={
            "company_id": 1, "receipt_date": "2026-07-31", "customer_id": ids["customer"],
            "bank_account_id": ids["bank"], "amount": 1150, "reference": "R6-COMMISSION-COLLECTION",
            "allocations": [{"open_item_id": open_item["id"], "amount": 1150}],
        }), 201)
        beneficiary = ok(client.post("/api/v1/sales-commissions/beneficiaries", headers=admin, json={
            "company_id": 1, "code": "R6-SALES-REP", "name_ar": "مندوب تحقق R6",
            "name_en": "R6 Sales Representative", "beneficiary_type": "SALES_REP",
            "default_basis": "PERCENTAGE", "default_rate": 5,
        }), 201)
        accrual = ok(client.post("/api/v1/sales-commissions/accruals", headers=admin, json={
            "company_id": 1, "beneficiary_id": beneficiary["id"], "sales_invoice_id": invoice["id"],
        }), 201)
        assert money(accrual["amount"]) == Decimal("50.00") and money(accrual["payable_amount"]) == Decimal("50.00")
        refreshed = ok(client.post(f"/api/v1/sales-commissions/accruals/{accrual['id']}/refresh?company_id=1", headers=admin))
        assert refreshed["status"] == "PAYABLE" and Decimal(str(refreshed["collected_ratio"])) == Decimal("1.0000")
        assert client.post(f"/api/v1/sales-commissions/accruals/{accrual['id']}/approve?company_id=1", headers=admin).status_code == 403
        approved = ok(client.post(f"/api/v1/sales-commissions/accruals/{accrual['id']}/approve?company_id=1", headers=reviewer))
        paid = ok(client.post(f"/api/v1/sales-commissions/accruals/{accrual['id']}/pay", headers=reviewer,
                              json={"company_id": 1, "bank_account_id": ids["bank"]}))
        assert approved["status"] == "APPROVED" and paid["status"] == "PAID" and money(paid["paid_amount"]) == Decimal("50.00")

        # Gym configuration lifecycle, including tenant-safe references and duplicate guards.
        cafe = ok(client.post("/api/v1/gym/departments", headers=admin, json={
            "company_id": 2, "branch_id": ids["branch"], "code": "R6CAFE", "name_ar": "كافيه تحقق R6",
            "name_en": "R6 Verification Cafe", "department_type": "CAFE", "cost_center_id": ids["center"],
            "revenue_account_id": ids["revenue"], "capacity": 30,
        }), 201)
        access = ok(client.post("/api/v1/gym/department-plan-access", headers=admin, json={
            "company_id": 2, "plan_id": ids["plan"], "department_id": cafe["id"],
            "access_mode": "INCLUDED", "monthly_visit_limit": 20, "advance_booking_days": 14,
        }), 201)
        facility = ok(client.post("/api/v1/gym/facilities", headers=admin, json={
            "company_id": 2, "department_id": cafe["id"], "code": "R6ROOM", "name_ar": "قاعة R6",
            "name_en": "R6 Room", "facility_type": "ROOM", "capacity": 12, "slot_minutes": 60,
        }), 201)
        closed = ok(client.patch(f"/api/v1/gym/facilities/{facility['id']}/status", headers=admin,
                                 json={"status": "MAINTENANCE", "notes": "R6 safety inspection"}))
        product = ok(client.post("/api/v1/gym/cafe/products", headers=admin, json={
            "company_id": 2, "branch_id": ids["branch"], "department_id": cafe["id"], "menu_item_id": ids["menu"],
            "category": "HEALTHY_MEAL", "product_type": "PREPARED", "member_price": 20,
            "calories": 350, "protein_g": 30, "is_healthy": True,
        }), 201)
        assert access["access_mode"] == "INCLUDED" and closed["status"] == "MAINTENANCE" and product["is_healthy"] is True
        duplicate = client.post("/api/v1/gym/cafe/products", headers=admin, json={
            "company_id": 2, "branch_id": ids["branch"], "department_id": cafe["id"], "menu_item_id": ids["menu"],
            "category": "HEALTHY_MEAL", "product_type": "PREPARED",
        })
        assert duplicate.status_code == 409

    DB_PATH.unlink(missing_ok=True)
    print("CORVAX RC27.4 R6 INVENTORY, COMMISSIONS AND GYM LIFECYCLES VERIFIED")


if __name__ == "__main__":
    main()
