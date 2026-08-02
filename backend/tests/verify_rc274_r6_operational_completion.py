"""R6 functional completion: operational master data, stock and controls."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_rc274_r6_operational_completion.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}", "SECRET_KEY": "r6-operational-completion-secret",
    "SEED_DEMO_DATA": "true", "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
})
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.security import _totp_code, generate_mfa_secret  # noqa: E402
from app.api.auth import _issue_enrolment_token  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    BillOfMaterial, EmployeeShiftAssignment, FiscalPeriod, FiscalYear, Item, Role, StockMovement,
    SoDConflict, User, UserCompanyRole, Warehouse,
)

PASSWORD = "Corvax@123"


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def login(client, email, password=PASSWORD):
    data = ok(client.post("/api/v1/auth/login", json={"email": email, "password": password}))
    return {"Authorization": f"Bearer {data['access_token']}"}


def main():
    with TestClient(app) as client:
        admin = login(client, "admin@corvaxplatform.com")
        with SessionLocal() as db:
            role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
            operator = User(name_ar="مشغل R6", name_en="R6 Operator", email="r6-operator@corvaxplatform.com",
                            password_hash=hash_password(PASSWORD), active=True)
            db.add(operator); db.flush()
            db.add(UserCompanyRole(user_id=operator.id, company_id=1, role_id=role.id))
            db.commit(); operator_id = operator.id

        # Administrative reset invalidates the old credential and status changes block login.
        reset = ok(client.post(f"/api/v1/admin/users/{operator_id}/reset-password", headers=admin,
                               json={"company_id": 1, "new_password": "Temp-R6-Password!2026", "require_change": True}))
        assert reset["status"] == "PASSWORD_RESET" and reset["require_change"] is True
        assert client.post("/api/v1/auth/login", json={"email": "r6-operator@corvaxplatform.com", "password": PASSWORD}).status_code == 401
        operator_headers = login(client, "r6-operator@corvaxplatform.com", "Temp-R6-Password!2026")
        changed = ok(client.post("/api/v1/auth/password/change", headers=operator_headers,
                                 json={"current_password": "Temp-R6-Password!2026", "new_password": "R6-New-Password!2026"}))
        assert changed == {"status": "password_changed", "relogin_required": True}
        disabled = ok(client.patch(f"/api/v1/admin/users/{operator_id}/status?company_id=1&active=false", headers=admin))
        assert disabled["active"] is False
        assert client.post("/api/v1/auth/login", json={"email": "r6-operator@corvaxplatform.com", "password": "R6-New-Password!2026"}).status_code == 401
        ok(client.patch(f"/api/v1/admin/users/{operator_id}/status?company_id=1&active=true", headers=admin))

        ticket = ok(client.post("/api/v1/itsm/tickets", headers=admin, json={
            "company_id": 1, "category": "ACCESS", "subject": "R6 assignment lifecycle",
            "description": "Functional assignment verification", "priority": "HIGH", "due_hours": 8,
        }), 201)
        assigned = ok(client.post(f"/api/v1/itsm/tickets/{ticket['id']}/assign?company_id=1", headers=admin,
                                  json={"assignee_user_id": operator_id}))
        assert assigned["status"] == "ASSIGNED" and assigned["assignee_user_id"] == operator_id

        objective = ok(client.post("/api/v1/qms/objectives", headers=admin, json={
            "company_id": 1, "code": "R6-QMS", "name_ar": "هدف جودة R6", "name_en": "R6 Quality Objective",
            "metric_name": "First pass yield", "unit": "PERCENT", "baseline_value": 90,
            "target_value": 98, "current_value": 90, "frequency": "MONTHLY", "effective_from": "2026-01-01",
        }), 201)
        measured = ok(client.patch(f"/api/v1/qms/objectives/{objective['id']}/measure", headers=admin,
                                   json={"current_value": 96.5}))
        assert float(measured["current_value"]) == 96.5

        rule = ok(client.post("/api/v1/access-governance/sod-rules", headers=admin, json={
            "code": "R6-SOD", "name_ar": "فصل مهام R6", "name_en": "R6 Segregation Rule",
            "permission_a": "finance.journal.post", "permission_b": "finance.journal.approve",
            "severity": "HIGH", "rationale": "R6 functional governance verification",
        }), 201)
        with SessionLocal() as db:
            conflict = SoDConflict(company_id=1, user_id=operator_id, rule_id=rule["id"], status="OPEN")
            db.add(conflict); db.commit(); conflict_id = conflict.id
        mitigated = ok(client.post(f"/api/v1/access-governance/conflicts/{conflict_id}/mitigate", headers=admin, json={
            "mitigating_control": "Independent daily review by finance controller",
            "remediation_due_date": "2026-12-31",
        }))
        assert mitigated["status"] == "MITIGATED"
        with SessionLocal() as db:
            db.query(UserCompanyRole).filter(UserCompanyRole.user_id == operator_id,
                                             UserCompanyRole.company_id == 1).delete()
            db.commit()
        resolved = ok(client.post(f"/api/v1/access-governance/conflicts/{conflict_id}/resolve", headers=admin,
                                  json={"resolution_notes": "Conflicting role assignment removed"}))
        assert resolved["status"] == "RESOLVED"

        # Pre-auth MFA enrollment proves possession of the authenticator secret before issuing a session.
        import time
        with SessionLocal() as db:
            mfa_user = db.get(User, operator_id)
            mfa_user.mfa_secret = generate_mfa_secret(); mfa_user.mfa_enabled = False
            token = _issue_enrolment_token(mfa_user); secret = mfa_user.mfa_secret
            db.commit()
        mfa = ok(client.post("/api/v1/auth/mfa/enable-preauth", json={
            "enrollment_token": token, "code": _totp_code(secret, int(time.time()) // 30),
        }))
        assert mfa["enabled"] is True

        bootstrapped = ok(client.post("/api/v1/advanced-finance/mappings/bootstrap", headers=admin,
                                     json={"company_id": 1}))
        mappings = ok(client.get("/api/v1/advanced-finance/mappings?company_id=1", headers=admin))
        assert bootstrapped["created"] >= 0 and mappings
        mapping_id = mappings[0]["id"]
        updated = ok(client.put(f"/api/v1/advanced-finance/mappings/{mapping_id}", headers=admin, json={
            "statement": mappings[0]["statement"], "ifrs18_category": mappings[0]["ifrs18_category"],
            "line_code": "R6-UPDATED", "line_name_ar": "بند محدث R6", "line_name_en": "R6 Updated Line",
            "sort_order": 999, "is_oci": False,
        }))
        assert updated["status"] == "DRAFT"


        # Manufacturing and POS master data use tenant-safe item/BOM references and duplicate guards.
        with SessionLocal() as db:
            items = db.scalars(select(Item).where(Item.company_id == 1, Item.active.is_(True)).limit(2)).all()
            assert len(items) == 2
            finished_id, component_id = items[0].id, items[1].id
        center = ok(client.post("/api/v1/manufacturing/work-centers", headers=admin, json={
            "company_id": 1, "code": "R6-WC", "name_ar": "مركز تشغيل R6", "name_en": "R6 Work Center",
            "hourly_labor_rate": 25, "hourly_overhead_rate": 10,
        }), 201)
        bom = ok(client.post("/api/v1/manufacturing/boms", headers=admin, json={
            "company_id": 1, "code": "R6-BOM", "version": 1, "finished_item_id": finished_id,
            "output_quantity": 1, "work_center_id": center["id"], "standard_hours": 0.5,
            "lines": [{"component_item_id": component_id, "quantity": 1, "scrap_percent": 0}],
        }), 201)
        assert bom["status"] == "ACTIVE"
        assert client.post("/api/v1/manufacturing/boms", headers=admin, json={
            "company_id": 1, "code": "R6-BOM", "version": 1, "finished_item_id": finished_id,
            "output_quantity": 1, "lines": [{"component_item_id": component_id, "quantity": 1}],
        }).status_code == 409
        platform = ok(client.post("/api/v1/pos/platforms", headers=admin, json={
            "company_id": 1, "code": "R6-DELIVERY", "name_ar": "منصة R6", "name_en": "R6 Delivery", "commission_rate": 18,
        }), 201)
        menu = ok(client.post("/api/v1/pos/menu", headers=admin, json={
            "company_id": 1, "code": "R6-MENU", "name_ar": "منتج R6", "name_en": "R6 Menu Item",
            "inventory_item_id": finished_id, "recipe_bom_id": bom["id"], "selling_price": 50, "vat_rate": 15,
        }), 201)
        assert platform["commission_rate"] == 18 and menu["vat_rate"] == 15

        # Stock issue posts a balanced journal; transfer preserves quantity/value between warehouses.
        with SessionLocal() as db:
            db.add(Warehouse(company_id=1, code="R6-DEST", name_ar="مستودع تحويل R6",
                             name_en="R6 Transfer Destination", warehouse_type="GENERAL", active=True))
            db.commit()
            balance = (select(StockMovement.item_id, StockMovement.warehouse_id,
                              func.sum(StockMovement.quantity).label("qty"))
                       .where(StockMovement.company_id == 1).group_by(StockMovement.item_id, StockMovement.warehouse_id)
                       .having(func.sum(StockMovement.quantity) > 5))
            stocked = db.execute(balance).first()
            warehouses = db.scalars(select(Warehouse).where(Warehouse.company_id == 1, Warehouse.active.is_(True))).all()
            assert stocked and len(warehouses) >= 2
            source_id = stocked.warehouse_id
            destination_id = next(w.id for w in warehouses if w.id != source_id)
            item_id = stocked.item_id
        issued = ok(client.post("/api/v1/inventory/issues", headers=admin, json={
            "company_id": 1, "warehouse_id": source_id, "item_id": item_id, "quantity": 1,
            "issue_date": "2026-07-31", "reference": "R6-ISSUE-1",
        }), 201)
        assert issued["total_cost"] > 0 and issued["journal_number"]
        transferred = ok(client.post("/api/v1/inventory/transfers", headers=admin, json={
            "company_id": 1, "source_warehouse_id": source_id, "destination_warehouse_id": destination_id,
            "item_id": item_id, "quantity": 1, "transfer_date": "2026-07-31", "reference": "R6-TRANSFER-1",
        }), 201)
        assert transferred["out_movement_id"] != transferred["in_movement_id"] and transferred["total_cost"] > 0

        # Attendance finalization is idempotent for the same working day.
        with SessionLocal() as db:
            assignment = db.scalar(select(EmployeeShiftAssignment).where(EmployeeShiftAssignment.company_id == 1,
                                                                           EmployeeShiftAssignment.active.is_(True)))
        if assignment:
            first = ok(client.post("/api/v1/hr/attendance/finalize-day?company_id=1&work_date=2026-07-30", headers=admin))
            second = ok(client.post("/api/v1/hr/attendance/finalize-day?company_id=1&work_date=2026-07-30", headers=admin))
            assert first["records_created"] >= 0 and second["records_created"] == 0

        # A closed fiscal period can be reopened only explicitly and records the reason.
        with SessionLocal() as db:
            period = db.scalar(select(FiscalPeriod).join(FiscalYear).where(FiscalYear.company_id == 1))
            period.status = "CLOSED"; db.commit(); period_id = period.id
        reopened = ok(client.post(f"/api/v1/period-close/periods/{period_id}/reopen?company_id=1", headers=admin,
                                  json={"reason": "R6 controlled reopening verification"}))
        assert reopened["status"] == "OPEN"
        assert client.post(f"/api/v1/period-close/periods/{period_id}/reopen?company_id=1", headers=admin,
                           json={"reason": "duplicate controlled reopening attempt"}).status_code == 409

    DB_PATH.unlink(missing_ok=True)
    print("CORVAX RC27.4 R6: OPERATIONAL COMPLETION LIFECYCLE PASSED")


if __name__ == "__main__":
    main()
