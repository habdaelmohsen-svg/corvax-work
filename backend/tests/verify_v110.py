"""End-to-end verification for CORVAX v1.0 RC10 advanced manufacturing and costing."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v110.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v110-advanced-manufacturing"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["APP_VERSION"] = "1.0.0-agreement-completion-rc27.4-r9.3"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.main import app  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Account, BillOfMaterial, Item, JournalEntry, ManufacturingRouting, MRPPlanRun,
    ProductionCostClose, ProductionOperationLog, ProductionOrder, ProductionScrapRecord,
    Role, User, UserCompanyRole, Warehouse, WorkCenter,
)


def login(client: TestClient, email: str, password: str = "Corvax@123") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_independent_users() -> None:
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
        assert role
        for email, name in [("reviewer@corvaxplatform.com", "Cost Reviewer"), ("approver@corvaxplatform.com", "Cost Approver")]:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(name_ar=name, name_en=name, email=email, password_hash=hash_password("Corvax@123"), active=True)
                db.add(user)
                db.flush()
                for company_id in (1, 2, 3, 4):
                    db.add(UserCompanyRole(user_id=user.id, company_id=company_id, role_id=role.id))
        db.commit()


def main() -> None:
    with TestClient(app) as client:
        create_independent_users()
        admin = login(client, "admin@corvaxplatform.com")
        reviewer = login(client, "reviewer@corvaxplatform.com")
        approver = login(client, "approver@corvaxplatform.com")
        json_admin = {**admin, "Content-Type": "application/json"}
        json_reviewer = {**reviewer, "Content-Type": "application/json"}
        json_approver = {**approver, "Content-Type": "application/json"}

        items = client.get("/api/v1/inventory/items?company_id=4", headers=admin).json()
        warehouses = client.get("/api/v1/inventory/warehouses?company_id=4", headers=admin).json()
        centers = client.get("/api/v1/manufacturing/work-centers?company_id=4", headers=admin).json()
        boms = client.get("/api/v1/manufacturing/boms?company_id=4", headers=admin).json()
        item_by_code = {row["code"]: row for row in items}
        assert {"RAW-001", "PACK-001", "FG-001"}.issubset(item_by_code)
        warehouse = warehouses[0]
        center = centers[0]
        bom = next(row for row in boms if row["code"] == "BOM-FG-001")

        routing_response = client.post("/api/v1/manufacturing/advanced/routings", headers=json_admin, json={
            "company_id": 4,
            "code": "RT-FG-001",
            "version": 1,
            "finished_item_id": item_by_code["FG-001"]["id"],
            "bom_id": bom["id"],
            "effective_from": "2026-07-01",
            "operations": [
                {"sequence": 10, "operation_code": "MIX", "name_ar": "الخلط", "name_en": "Mixing",
                 "work_center_id": center["id"], "setup_minutes": 30, "run_minutes_per_unit": 1.2,
                 "standard_labor_rate": 120, "standard_overhead_rate": 80},
                {"sequence": 20, "operation_code": "PACK", "name_ar": "التعبئة", "name_en": "Packing",
                 "work_center_id": center["id"], "setup_minutes": 30, "run_minutes_per_unit": 0.6,
                 "standard_labor_rate": 120, "standard_overhead_rate": 80, "quality_gate": True},
            ],
        })
        assert routing_response.status_code == 201, routing_response.text
        routing = routing_response.json()
        self_approve = client.post(f"/api/v1/manufacturing/advanced/routings/{routing['id']}/approve", headers=admin)
        assert self_approve.status_code == 409
        approved_routing = client.post(f"/api/v1/manufacturing/advanced/routings/{routing['id']}/approve", headers=reviewer)
        assert approved_routing.status_code == 200, approved_routing.text
        assert approved_routing.json()["status"] == "APPROVED"

        mrp_response = client.post("/api/v1/manufacturing/advanced/mrp-runs", headers=json_admin, json={
            "company_id": 4,
            "warehouse_id": warehouse["id"],
            "planning_date": "2026-07-13",
            "horizon_end": "2026-08-31",
            "demands": [{"item_id": item_by_code["FG-001"]["id"], "due_date": "2026-08-15", "quantity": 7000,
                         "safety_stock": 100, "source_type": "SALES_FORECAST", "source_reference": "S&OP-AUG"}],
        })
        assert mrp_response.status_code == 201, mrp_response.text
        mrp = mrp_response.json()
        assert len(mrp["requirements"]) >= 3
        assert any(line["supply_type"] == "MAKE" for line in mrp["requirements"])
        assert any(line["supply_type"] == "BUY" and Decimal(str(line["net_requirement"])) > 0 for line in mrp["requirements"])
        assert client.post(f"/api/v1/manufacturing/advanced/mrp-runs/{mrp['id']}/approve", headers=admin).status_code == 409
        mrp_approval = client.post(f"/api/v1/manufacturing/advanced/mrp-runs/{mrp['id']}/approve", headers=reviewer)
        assert mrp_approval.status_code == 200, mrp_approval.text

        order_response = client.post("/api/v1/manufacturing/orders", headers=json_admin, json={
            "company_id": 4, "order_date": "2026-07-14", "bom_id": bom["id"],
            "warehouse_id": warehouse["id"], "planned_quantity": 100,
        })
        assert order_response.status_code == 201, order_response.text
        order = order_response.json()
        init = client.post(f"/api/v1/manufacturing/advanced/orders/{order['id']}/operations/initialize?routing_id={routing['id']}", headers=admin)
        assert init.status_code == 200, init.text
        assert init.json()["operations_created"] == 2

        issue = client.post(f"/api/v1/manufacturing/orders/{order['id']}/issue-materials", headers=admin)
        assert issue.status_code == 200, issue.text
        operations = client.get(f"/api/v1/manufacturing/advanced/orders/{order['id']}/operations", headers=admin).json()
        assert len(operations) == 2
        for idx, operation in enumerate(operations):
            started = client.post(f"/api/v1/manufacturing/advanced/operations/{operation['id']}/start", headers=admin)
            assert started.status_code == 200, started.text
            completed = client.post(f"/api/v1/manufacturing/advanced/operations/{operation['id']}/complete", headers=json_admin, json={
                "actual_setup_minutes": 35 if idx == 0 else 32,
                "actual_run_minutes": 130 if idx == 0 else 68,
                "good_quantity": 99,
                "rejected_quantity": 1,
                "actual_labor_rate": 125,
                "actual_overhead_rate": 85,
            })
            assert completed.status_code == 200, completed.text

        scrap = client.post(f"/api/v1/manufacturing/advanced/orders/{order['id']}/scrap", headers=json_admin, json={
            "record_date": "2026-07-14", "item_id": item_by_code["RAW-001"]["id"], "quantity": 2,
            "unit_cost": 10, "reason_code": "MACHINE_SETTING", "classification": "ABNORMAL",
            "disposition": "DISPOSE", "notes": "Documented setup loss above normal allowance",
        })
        assert scrap.status_code == 201, scrap.text
        assert Decimal(str(scrap.json()["total_cost"])) == Decimal("20.00")

        completion = client.post(f"/api/v1/manufacturing/orders/{order['id']}/complete", headers=json_admin, json={
            "completion_date": "2026-07-14", "completed_quantity": 99, "actual_hours": 4.6,
            "lot_number": "FG-RC10-001", "expiry_date": "2027-01-14",
        })
        assert completion.status_code == 200, completion.text

        close_response = client.post(f"/api/v1/manufacturing/advanced/orders/{order['id']}/cost-close", headers=json_admin, json={
            "close_date": "2026-07-14", "cost_method": "STANDARD",
        })
        assert close_response.status_code == 201, close_response.text
        close = close_response.json()
        assert close["status"] == "READY_FOR_REVIEW"
        assert Decimal(str(close["abnormal_scrap_cost"])) == Decimal("20.00")
        assert close["analysis_hash"] and len(close["analysis_hash"]) == 64
        assert client.post(f"/api/v1/manufacturing/advanced/cost-closes/{close['id']}/review", headers=admin).status_code == 409
        reviewed = client.post(f"/api/v1/manufacturing/advanced/cost-closes/{close['id']}/review", headers=reviewer)
        assert reviewed.status_code == 200, reviewed.text
        assert client.post(f"/api/v1/manufacturing/advanced/cost-closes/{close['id']}/approve", headers=reviewer).status_code == 409
        posted = client.post(f"/api/v1/manufacturing/advanced/cost-closes/{close['id']}/approve", headers=approver)
        assert posted.status_code == 200, posted.text
        assert posted.json()["status"] == "POSTED"
        assert posted.json()["journal_id"] is not None

        dashboard = client.get("/api/v1/manufacturing/advanced/dashboard?company_id=4", headers=admin)
        assert dashboard.status_code == 200, dashboard.text
        dashboard_data = dashboard.json()
        assert dashboard_data["approved_routings"] >= 1
        assert dashboard_data["mrp_runs"] >= 1
        assert dashboard_data["operations"] >= 2
        assert dashboard_data["posted_cost_closes"] >= 1

        release = client.get("/api/v1/system/release").json()
        from app.core.migration_head import expected_migration_head
        assert release["database_schema_head"] == expected_migration_head()
        health = client.get("/health").json()
        assert health.get("status") == "ok"

    with SessionLocal() as db:
        assert db.scalar(select(ManufacturingRouting).where(ManufacturingRouting.code == "RT-FG-001")).status == "APPROVED"
        assert db.scalar(select(MRPPlanRun)).status == "APPROVED"
        operation_count = len(db.scalars(select(ProductionOperationLog)).all())
        assert operation_count == 2
        assert db.scalar(select(ProductionScrapRecord)).classification == "ABNORMAL"
        cost_close = db.scalar(select(ProductionCostClose))
        assert cost_close.status == "POSTED"
        journal = db.get(JournalEntry, cost_close.journal_id)
        assert journal and journal.status == "POSTED" and journal.total_debit == journal.total_credit
        for code in ("624010", "624020", "624030", "624040", "624050", "624060", "624070", "624080"):
            assert db.scalar(select(Account).where(Account.company_id == 4, Account.code == code))
        assert db.scalar(select(ProductionOrder).where(ProductionOrder.id == cost_close.production_order_id)).status == "COMPLETED"

    print("CORVAX v1.0 RC10 advanced manufacturing and costing: ALL VERIFICATIONS PASSED")


if __name__ == "__main__":
    main()
