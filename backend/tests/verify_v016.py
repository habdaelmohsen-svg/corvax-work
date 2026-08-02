from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v016.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["SECRET_KEY"] = "verification-secret-key-v016"
os.environ["ENVIRONMENT"] = "testing"
os.environ["BACKUP_DIR"] = str(DB_PATH.parent / "verify_backups")

from fastapi.testclient import TestClient
from app.core.security import _totp_code
from app.main import app


def ok(response, expected=200):
    assert response.status_code == expected, (response.status_code, response.text)
    return response.json()

with TestClient(app) as client:
    login = ok(client.post("/api/v1/auth/login", json={"email":"admin@corvaxplatform.com","password":"Corvax@123"}))
    admin = {"Authorization": f"Bearer {login['access_token']}"}
    assert ok(client.get("/health"))["version"] == "1.0.0-agreement-completion-rc27.4"

    # Create independent approver and security test users.
    cfo = ok(client.post("/api/v1/admin/users", headers=admin, json={
        "name_ar":"مدير مالي تجريبي","name_en":"Demo CFO","email":"cfo@corvaxplatform.com","password":"StrongCFO@2026!",
        "require_password_change": False, "memberships":[{"company_id":1,"role_code":"CFO"},{"company_id":4,"role_code":"CFO"}],
    }), 201)
    cfo_login = ok(client.post("/api/v1/auth/login", json={"email":"cfo@corvaxplatform.com","password":"StrongCFO@2026!"}))
    cfo_headers = {"Authorization": f"Bearer {cfo_login['access_token']}"}

    security_user = ok(client.post("/api/v1/admin/users", headers=admin, json={
        "name_ar":"مستخدم أمان","name_en":"Security User","email":"security@corvaxplatform.com","password":"Security@2026!",
        "require_password_change": False, "memberships":[{"company_id":1,"role_code":"ACCOUNTANT"}],
    }), 201)
    sec_login = ok(client.post("/api/v1/auth/login", json={"email":"security@corvaxplatform.com","password":"Security@2026!"}))
    sec_headers = {"Authorization": f"Bearer {sec_login['access_token']}"}
    setup = ok(client.post("/api/v1/auth/mfa/setup", headers=sec_headers))
    code = _totp_code(setup["secret"], __import__("time").time_ns() // 1_000_000_000 // 30)
    enabled = ok(client.post("/api/v1/auth/mfa/enable", headers=sec_headers, json={"code":code}))
    assert enabled["enabled"] is True
    assert client.post("/api/v1/auth/login", json={"email":"security@corvaxplatform.com","password":"Security@2026!"}).status_code == 401
    relogin_code = _totp_code(setup["secret"], __import__("time").time_ns() // 1_000_000_000 // 30)
    assert ok(client.post("/api/v1/auth/login", json={"email":"security@corvaxplatform.com","password":"Security@2026!","otp":relogin_code}))["user"]["mfa_enabled"] is True

    locked = ok(client.post("/api/v1/admin/users", headers=admin, json={
        "name_ar":"مستخدم قفل","name_en":"Lock User","email":"lock@corvaxplatform.com","password":"LockUser@2026!",
        "require_password_change": False, "memberships":[{"company_id":1,"role_code":"ACCOUNTANT"}],
    }), 201)
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email":"lock@corvaxplatform.com","password":"wrong-pass"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email":"lock@corvaxplatform.com","password":"LockUser@2026!"}).status_code == 423
    assert ok(client.post(f"/api/v1/admin/users/{locked['id']}/unlock?company_id=1", headers=admin))["status"] == "UNLOCKED"

    # Attendance and geofence.
    employees = ok(client.get("/api/v1/payroll/employees?company_id=1", headers=admin))
    employee = employees[0]
    shifts = ok(client.get("/api/v1/hr/shifts?company_id=1", headers=admin))
    attendance = ok(client.post("/api/v1/hr/attendance/clock-in", headers=admin, json={
        "company_id":1,"employee_id":employee["id"],"event_time":"2026-07-12T08:15:00","latitude":24.4672,"longitude":39.6111,"source":"WEB"
    }))
    assert attendance["status"] == "LATE" and attendance["late_minutes"] == 5
    attendance = ok(client.post("/api/v1/hr/attendance/clock-out", headers=admin, json={
        "company_id":1,"employee_id":employee["id"],"event_time":"2026-07-12T17:30:00","latitude":24.4672,"longitude":39.6111,"source":"WEB"
    }))
    assert attendance["overtime_minutes"] == 30

    leave_types = ok(client.get("/api/v1/hr/leave-types?company_id=1", headers=admin))
    leave = ok(client.post("/api/v1/hr/leaves", headers=admin, json={"company_id":1,"employee_id":employee["id"],"leave_type_id":leave_types[0]["id"],"start_date":"2026-08-02","end_date":"2026-08-06","reason":"Annual leave"}), 201)
    assert ok(client.post(f"/api/v1/hr/leaves/{leave['id']}/approve", headers=cfo_headers))["status"] == "APPROVED"
    balance = ok(client.get(f"/api/v1/hr/leaves/balance?company_id=1&employee_id={employee['id']}&as_of_date=2026-12-31", headers=admin))
    assert Decimal(str(balance["used_days"])) == Decimal("5.00")

    # Saudi EOS calculation and maker-checker posting.
    eos_employee = ok(client.post("/api/v1/payroll/employees", headers=admin, json={
        "company_id":1,"employee_number":"EMP-EOS","name_ar":"موظف نهاية خدمة","name_en":"EOS Employee","nationality_group":"SAUDI",
        "hire_date":"2018-01-01","basic_salary":9000,"housing_allowance":2250,"other_allowance":750,"employee_gosi_rate":9.75,"employer_gosi_rate":11.75
    }), 201)
    eos = ok(client.post("/api/v1/hr/end-of-service/calculate", headers=admin, json={
        "company_id":1,"employee_id":eos_employee["id"],"termination_date":"2026-07-12","termination_reason":"RESIGNATION","unused_leave_days":10,"deductions":500
    }), 201)
    assert Decimal(str(eos["entitlement_percent"])) > Decimal("66")
    eos_posted = ok(client.post(f"/api/v1/hr/end-of-service/{eos['id']}/approve", headers=cfo_headers, json={"payment_date":"2026-07-12"}))
    assert eos_posted["status"] == "APPROVED"

    # Actual sales invoice -> local Saudi e-invoice XML/hash chain/QR and VAT snapshot.
    parties = ok(client.get("/api/v1/subledgers/parties?company_id=1&party_type=CUSTOMER", headers=admin))
    invoice = ok(client.post("/api/v1/subledgers/sales-invoices", headers=admin, json={
        "company_id":1,"invoice_date":"2026-07-12","due_date":"2026-08-11","customer_id":parties[0]["id"],"reference":"ZATCA-V016",
        "lines":[{"description":"Professional services","account_code":"411010","quantity":1,"unit_price":1000,"vat_rate":15}]
    }), 201)
    ok(client.post(f"/api/v1/subledgers/sales-invoices/{invoice['id']}/post", headers=admin))
    einvoice = ok(client.post("/api/v1/compliance/e-invoices/generate", headers=admin, json={"company_id":1,"source_type":"SALES_INVOICE","source_id":invoice["id"]}), 201)
    assert einvoice["status"] == "LOCAL_VALIDATED" and "<Invoice" in einvoice["xml"] and einvoice["integration_status"] == "NOT_CONNECTED_TO_ZATCA"
    vat = ok(client.post("/api/v1/compliance/vat-return", headers=admin, json={"company_id":1,"period_start":"2026-07-01","period_end":"2026-07-31"}), 201)
    assert Decimal(str(vat["output_vat"])) >= Decimal("150.00")

    # Period close review and maker-checker close on manufacturing company July.
    years = ok(client.get("/api/v1/enterprise/companies/4/fiscal-years", headers=admin))
    periods = ok(client.get(f"/api/v1/enterprise/fiscal-years/{years[0]['id']}/periods", headers=admin))
    july = next(row for row in periods if row["number"] == 7)
    close_review = ok(client.post("/api/v1/period-close/review", headers=admin, json={"company_id":4,"fiscal_period_id":july["id"]}), 201)
    assert all(check["status"] != "FAIL" for check in close_review["checks"] if check["blocking"]), close_review
    closed = ok(client.post(f"/api/v1/period-close/{close_review['id']}/close", headers=cfo_headers))
    assert closed["status"] == "CLOSED"

    # Verified database backup.
    backup = ok(client.post("/api/v1/backups?company_id=1", headers=admin), 201)
    verified = ok(client.post(f"/api/v1/backups/{backup['id']}/verify", headers=admin))
    downloaded = client.get(f"/api/v1/backups/{backup['id']}/download", headers=admin)
    assert downloaded.status_code == 200 and downloaded.content
    assert verified["status"] == "VERIFIED"

    # Accounting control after automated EOS posting.
    tb = ok(client.get("/api/v1/finance/trial-balance?company_id=1&end_date=2026-07-31", headers=admin))
    assert tb["balanced"] is True

print("CORVAX v0.16 security, HR, compliance, close and backup: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
