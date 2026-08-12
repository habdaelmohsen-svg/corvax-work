"""CORVAX RC12 HR and payroll completion verification."""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v112.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v112-hr-payroll"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["APP_VERSION"] = "1.0.0-agreement-completion-rc27.4-r9.4"
os.environ["PAYROLL_STRICT_WORKFLOW"] = "true"
os.environ["ENABLE_RATE_LIMIT_TESTING"] = "true"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    BankAccount, Branch, Employee, LeaveType, Role, User, UserCompanyRole,
)

PASSWORD = "Corvax@123"


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_users() -> None:
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
        assert role
        for email, ar, en in [
            ("rc12-reviewer@corvaxplatform.com", "مراجع الرواتب", "Payroll Reviewer"),
            ("rc12-approver@corvaxplatform.com", "معتمد الرواتب", "Payroll Approver"),
            ("rc12-payer@corvaxplatform.com", "مسؤول الصرف", "Payroll Payer"),
        ]:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(name_ar=ar, name_en=en, email=email, password_hash=hash_password(PASSWORD), active=True)
                db.add(user); db.flush()
                db.add(UserCompanyRole(user_id=user.id, company_id=1, role_id=role.id))
        # Isolate one employee for deterministic payroll.
        for employee in db.scalars(select(Employee).where(Employee.company_id == 1)).all():
            employee.active = False
        db.commit()


def ok(response):
    assert response.status_code in {200, 201, 202}, response.text
    return response.json()


def main() -> None:
    with TestClient(app) as client:
        create_users()
        admin = login(client, "admin@corvaxplatform.com")
        reviewer = login(client, "rc12-reviewer@corvaxplatform.com")
        approver = login(client, "rc12-approver@corvaxplatform.com")
        payer = login(client, "rc12-payer@corvaxplatform.com")
        admin_json = {**admin, "Content-Type": "application/json"}
        reviewer_json = {**reviewer, "Content-Type": "application/json"}
        approver_json = {**approver, "Content-Type": "application/json"}

        with SessionLocal() as db:
            branch = db.scalar(select(Branch).where(Branch.company_id == 1, Branch.active.is_(True)))
            bank = db.scalar(select(BankAccount).where(BankAccount.company_id == 1, BankAccount.active.is_(True)))
            unpaid = db.scalar(select(LeaveType).where(LeaveType.company_id == 1, LeaveType.code == "UNPAID"))
            assert branch and bank and unpaid
            branch_id, bank_id, unpaid_id = branch.id, bank.id, unpaid.id
            lat, lon = str(branch.latitude), str(branch.longitude)

        employee = ok(client.post("/api/v1/payroll/employees", headers=admin_json, json={
            "company_id": 1, "employee_number": "RC12-001", "name_ar": "موظف اختبار الرواتب", "name_en": "RC12 Payroll Employee",
            "nationality_group": "SAUDI", "national_id": "1000000001", "birth_date": "1990-01-01",
            "salary_bank_code": "RJHI", "iban": "SA0380000000608010167519", "hire_date": "2020-01-01",
            "basic_salary": 10000, "housing_allowance": 2500, "other_allowance": 500,
            "employee_gosi_rate": 9.75, "employer_gosi_rate": 11.75, "branch_id": branch_id,
        }))
        employee_id = employee["id"]

        policy = ok(client.post("/api/v1/hr-payroll/policies", headers=admin_json, json={
            "company_id": 1, "salary_day_basis": 30, "standard_daily_hours": 8, "gosi_basis": "BASIC_HOUSING",
            "late_deduction_enabled": True, "absence_deduction_enabled": True, "overtime_basis": "BASIC",
            "attendance_completeness_threshold": 5, "require_three_user_approval": True,
        }))
        assert client.post(f"/api/v1/hr-payroll/policies/{policy['id']}/approve", headers=admin).status_code == 409
        ok(client.post(f"/api/v1/hr-payroll/policies/{policy['id']}/approve", headers=approver))

        contract = ok(client.post("/api/v1/hr-payroll/contracts", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "contract_number": "C-RC12-001", "contract_type": "UNLIMITED",
            "start_date": "2026-01-01", "basic_salary": 10000, "housing_allowance": 2500, "other_allowance": 500,
            "working_hours_per_week": 48, "notice_days": 60,
        }))
        ok(client.post(f"/api/v1/hr-payroll/contracts/{contract['id']}/approve", headers=approver))

        shift = ok(client.post("/api/v1/hr/shifts", headers=admin_json, json={
            "company_id": 1, "code": "RC12-DAY", "name_ar": "وردية اختبار", "name_en": "RC12 Day",
            "start_time": "08:00:00", "end_time": "17:00:00", "grace_minutes": 10, "working_days": "0,1,2,3,4,5,6",
        }))
        ok(client.post("/api/v1/hr/shift-assignments", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "shift_id": shift["id"], "branch_id": branch_id, "effective_from": "2026-07-01",
        }))
        clock_in = ok(client.post("/api/v1/hr/attendance/clock-in", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "event_time": "2026-07-01T08:30:00", "latitude": lat, "longitude": lon, "source": "WEB",
        }))
        assert clock_in["late_minutes"] == 20
        ok(client.post("/api/v1/hr/attendance/clock-out", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "event_time": "2026-07-01T17:30:00", "latitude": lat, "longitude": lon, "source": "WEB",
        }))
        ok(client.post("/api/v1/hr/attendance/manual", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "work_date": "2026-07-02", "status": "ABSENT", "reason": "Approved audit test absence",
        }))
        leave = ok(client.post("/api/v1/hr/leaves", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "leave_type_id": unpaid_id, "start_date": "2026-07-03", "end_date": "2026-07-03", "reason": "RC12 test",
        }))
        ok(client.post(f"/api/v1/hr/leaves/{leave['id']}/approve", headers=reviewer))

        overtime = ok(client.post("/api/v1/hr-payroll/overtime", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "work_date": "2026-07-01", "requested_minutes": 120,
            "rate_multiplier": 1.5, "reason": "Approved month-end work",
        }))
        ok(client.post(f"/api/v1/hr-payroll/overtime/{overtime['id']}/approve", headers=reviewer_json, json={"approved_minutes": 90}))

        adjustment = ok(client.post("/api/v1/hr-payroll/adjustments", headers=admin_json, json={
            "company_id": 1, "employee_id": employee_id, "period_year": 2026, "period_month": 7,
            "adjustment_type": "PERFORMANCE_BONUS", "amount": 1000, "earning": True, "gosi_applicable": False,
            "reason": "Approved performance bonus",
        }))
        assert client.post(f"/api/v1/hr-payroll/adjustments/{adjustment['id']}/review", headers=admin).status_code == 409
        ok(client.post(f"/api/v1/hr-payroll/adjustments/{adjustment['id']}/review", headers=reviewer))
        ok(client.post(f"/api/v1/hr-payroll/adjustments/{adjustment['id']}/approve", headers=approver))

        run = ok(client.post("/api/v1/payroll/runs", headers=admin_json, json={
            "company_id": 1, "period_year": 2026, "period_month": 7, "payment_date": "2026-07-31", "bank_account_id": bank_id, "adjustments": [],
        }))
        assert run["status"] == "CALCULATED" and Decimal(str(run["total_net"])) > 0
        line = run["lines"][0]
        assert int(line["overtime_minutes"]) == 90
        assert Decimal(str(line["earning_adjustments"])) == Decimal("1000.00")
        assert Decimal(str(line["absence_deduction"])) > 0
        assert Decimal(str(line["unpaid_leave_deduction"])) > 0
        assert client.post(f"/api/v1/payroll/runs/{run['id']}/post", headers=admin).status_code == 409
        assert client.post(f"/api/v1/payroll/runs/{run['id']}/review", headers=admin_json, json={}).status_code == 409
        ok(client.post(f"/api/v1/payroll/runs/{run['id']}/review", headers=reviewer_json, json={}))
        approved_run = ok(client.post(f"/api/v1/payroll/runs/{run['id']}/approve", headers=approver))
        assert approved_run["status"] == "APPROVED_POSTED"

        wps = ok(client.post(f"/api/v1/hr-payroll/wps/{run['id']}/generate", headers=approver))
        file_response = client.get(f"/api/v1/hr-payroll/wps/{wps['id']}/file", headers=approver)
        assert file_response.status_code == 200 and "RC12-001" in file_response.text
        ok(client.post(f"/api/v1/hr-payroll/wps/{wps['id']}/response", headers=approver_json, json={
            "status": "ACCEPTED", "response_reference": "BANK-RC12-OK",
            "lines": [{"employee_id": employee_id, "status": "ACCEPTED"}],
        }))
        paid = ok(client.post(f"/api/v1/payroll/runs/{run['id']}/pay", headers=payer))
        assert paid["status"] == "PAID"

        assumption = ok(client.post("/api/v1/hr-payroll/benefits/assumptions", headers=admin_json, json={
            "company_id": 1, "valuation_date": "2026-07-31", "discount_rate": 0.055, "salary_growth_rate": 0.03,
            "annual_turnover_rate": 0.04, "retirement_age": 60, "mortality_survival_factor": 0.995,
        }))
        ok(client.post(f"/api/v1/hr-payroll/benefits/assumptions/{assumption['id']}/review", headers=reviewer))
        ok(client.post(f"/api/v1/hr-payroll/benefits/assumptions/{assumption['id']}/approve", headers=approver))
        valuation = ok(client.post("/api/v1/hr-payroll/benefits/valuations", headers=admin_json, json={
            "company_id": 1, "assumption_id": assumption["id"], "valuation_date": "2026-07-31",
        }))
        assert Decimal(str(valuation["total_dbo"])) > 0
        assert client.post(f"/api/v1/hr-payroll/benefits/valuations/{valuation['id']}/review", headers=admin).status_code == 409
        ok(client.post(f"/api/v1/hr-payroll/benefits/valuations/{valuation['id']}/review", headers=reviewer))
        approved_valuation = ok(client.post(f"/api/v1/hr-payroll/benefits/valuations/{valuation['id']}/approve", headers=approver))
        assert approved_valuation["status"] == "APPROVED_POSTED"

        summary = ok(client.get("/api/v1/hr-payroll/summary?company_id=1", headers=admin))
        assert summary["contracts"] == 1 and summary["wps_batches"] == 1 and summary["benefit_valuations"] == 1

        with engine.connect() as connection:
            raw_employee = connection.execute(text("SELECT national_id, iban FROM employees WHERE id=:id"), {"id": employee_id}).one()
            assert str(raw_employee.national_id).startswith("enc:v1:") and str(raw_employee.iban).startswith("enc:v1:")
            raw_wps = connection.execute(text("SELECT employee_iban, amount FROM wps_batch_lines LIMIT 1")).one()
            assert str(raw_wps.employee_iban).startswith("enc:v1:") and str(raw_wps.amount).startswith("enc:v1:")

        print("CORVAX v1.0 RC12 HR and payroll completion: ALL VERIFICATIONS PASSED")


if __name__ == "__main__":
    main()
