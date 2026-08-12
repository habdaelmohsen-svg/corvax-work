"""Independent-style remediation verification for CORVAX v1.0 RC11."""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v111.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v111-audit-remediation"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["APP_VERSION"] = "1.0.0-agreement-completion-rc27.4-r9.4"
os.environ["MRP_INLINE_EXECUTION"] = "true"
os.environ["ENABLE_RATE_LIMIT_TESTING"] = "true"

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.middleware import RateLimitMiddleware  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    BankAccount, Company, JournalSequence, Party, Role, User, UserCompanyRole,
)
from app.services.posting import next_journal_number  # noqa: E402
from app.workers.mrp_worker import run_once  # noqa: E402

PASSWORD = "Corvax@123"


def login_payload(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def auth(payload: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {payload['access_token']}"}


def create_review_users() -> None:
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
        assert role
        users = [
            ("rc11-reviewer@corvaxplatform.com", "مراجع RC11", "RC11 Reviewer"),
            ("rc11-approver@corvaxplatform.com", "معتمد RC11", "RC11 Approver"),
        ]
        for email, name_ar, name_en in users:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(name_ar=name_ar, name_en=name_en, email=email,
                            password_hash=hash_password(PASSWORD), active=True)
                db.add(user); db.flush()
                for company_id in (1, 2, 3, 4):
                    db.add(UserCompanyRole(user_id=user.id, company_id=company_id, role_id=role.id))
        db.commit()


def verify_race_safe_sequence() -> None:
    with engine.connect() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))
        connection.execute(text("PRAGMA busy_timeout=10000"))
        connection.commit()

    def allocate(_: int) -> str:
        for attempt in range(12):
            try:
                with SessionLocal() as db:
                    number = next_journal_number(db, 1, date(2026, 7, 15))
                    db.commit()
                    return number
            except OperationalError:
                time.sleep(0.03 * (attempt + 1))
        raise AssertionError("Could not allocate journal number after retries")

    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(allocate, range(24)))
    assert len(numbers) == len(set(numbers)) == 24
    suffixes = sorted(int(number.rsplit("-", 1)[-1]) for number in numbers)
    assert suffixes == list(range(min(suffixes), min(suffixes) + 24))
    with SessionLocal() as db:
        sequence = db.scalar(select(JournalSequence).where(JournalSequence.company_id == 1, JournalSequence.fiscal_year == 2026))
        assert sequence and sequence.last_number >= max(suffixes)


def verify_encryption() -> None:
    with SessionLocal() as db:
        company = db.get(Company, 1)
        assert company
        company.vat_number = "310123456789003"
        company.commercial_registration = "4650001234"
        db.commit()
    with engine.connect() as connection:
        raw = connection.execute(text("SELECT vat_number, commercial_registration FROM companies WHERE id=1")).one()
        assert str(raw.vat_number).startswith("enc:v1:")
        assert str(raw.commercial_registration).startswith("enc:v1:")
        assert "310123456789003" not in str(raw)
    with SessionLocal() as db:
        company = db.get(Company, 1)
        assert company.vat_number == "310123456789003"
        assert company.commercial_registration == "4650001234"


def main() -> None:
    with TestClient(app) as client:
        create_review_users()
        admin_login = login_payload(client, "admin@corvaxplatform.com")
        admin = auth(admin_login)
        json_admin = {**admin, "Content-Type": "application/json"}
        settings.rate_limit_write_per_minute = 1000
        settings.rate_limit_read_per_minute = 1000

        # RS256 JWT, kid and rotating refresh sessions.
        assert admin_login["access_token"].count(".") == 2
        header = jwt.get_unverified_header(admin_login["access_token"])
        assert header["alg"] == "RS256" and header["kid"] == settings.jwt_active_kid
        first_refresh = client.cookies.get("corvax_refresh_token")
        assert first_refresh
        rotated = client.post("/api/v1/auth/refresh")
        assert rotated.status_code == 200, rotated.text
        second_refresh = client.cookies.get("corvax_refresh_token")
        assert second_refresh and second_refresh != first_refresh
        client.cookies.set(
            "corvax_refresh_token",
            first_refresh,
            path="/api/v1/auth",
        )
        assert client.post("/api/v1/auth/refresh").status_code == 401
        client.cookies.set(
            "corvax_refresh_token",
            second_refresh,
            path="/api/v1/auth",
        )
        admin_login = rotated.json()
        admin = auth(admin_login)
        json_admin = {**admin, "Content-Type": "application/json"}
        assert client.get("/api/v1/auth/me", headers=admin).status_code == 200
        reviewer_login = login_payload(client, "rc11-reviewer@corvaxplatform.com")
        approver_login = login_payload(client, "rc11-approver@corvaxplatform.com")
        reviewer = auth(reviewer_login)
        approver = auth(approver_login)

        verify_encryption()
        verify_race_safe_sequence()

        items = client.get("/api/v1/inventory/items?company_id=4", headers=admin).json()
        warehouses = client.get("/api/v1/inventory/warehouses?company_id=4", headers=admin).json()
        centers = client.get("/api/v1/manufacturing/work-centers?company_id=4", headers=admin).json()
        boms = client.get("/api/v1/manufacturing/boms?company_id=4", headers=admin).json()
        item_by_code = {row["code"]: row for row in items}
        warehouse = warehouses[0]
        center = centers[0]
        bom = next(row for row in boms if row["code"] == "BOM-FG-001")
        with SessionLocal() as db:
            supplier = db.scalar(select(Party).where(Party.company_id == 4, Party.party_type.in_(["SUPPLIER", "BOTH"])))
            assert supplier
            supplier_id = supplier.id

        routing = client.post("/api/v1/manufacturing/advanced/routings", headers=json_admin, json={
            "company_id": 4, "code": "RT-RC11-FG", "version": 1,
            "finished_item_id": item_by_code["FG-001"]["id"], "bom_id": bom["id"], "effective_from": "2026-07-01",
            "operations": [
                {"sequence": 10, "operation_code": "MAKE", "name_ar": "تصنيع", "name_en": "Manufacture",
                 "work_center_id": center["id"], "setup_minutes": 20, "run_minutes_per_unit": 0.20,
                 "standard_labor_rate": 120, "standard_overhead_rate": 80},
                {"sequence": 20, "operation_code": "PACK", "name_ar": "تعبئة", "name_en": "Pack",
                 "work_center_id": center["id"], "setup_minutes": 10, "run_minutes_per_unit": 0.10,
                 "standard_labor_rate": 120, "standard_overhead_rate": 80},
            ],
        })
        assert routing.status_code == 201, routing.text
        assert client.post(f"/api/v1/manufacturing/advanced/routings/{routing.json()['id']}/approve", headers=reviewer).status_code == 200

        planning = client.post("/api/v1/manufacturing/advanced/planning/supplier-items", headers=json_admin, json={
            "company_id": 4, "supplier_id": supplier_id, "item_id": item_by_code["RAW-001"]["id"],
            "lead_time_days": 7, "lot_sizing_policy": "FOQ", "minimum_order_quantity": 100,
            "order_multiple": 50, "fixed_order_quantity": 500, "preferred": True,
        })
        assert planning.status_code == 201, planning.text

        start = date(2026, 7, 13)
        for day_offset in range(35):
            calendar = client.post("/api/v1/manufacturing/advanced/planning/work-center-calendar", headers=json_admin, json={
                "company_id": 4, "work_center_id": center["id"], "work_date": str(start + timedelta(days=day_offset)),
                "shift_code": "DAY", "available_minutes": 480,
            })
            assert calendar.status_code == 201, calendar.text

        po = client.post("/api/v1/inventory/purchase-orders", headers=json_admin, json={
            "company_id": 4, "order_date": "2026-07-15", "expected_receipt_date": "2026-08-01",
            "supplier_id": supplier_id, "warehouse_id": warehouse["id"],
            "lines": [{"item_id": item_by_code["RAW-001"]["id"], "quantity": 500, "unit_price": 10, "vat_rate": 15}],
        })
        assert po.status_code == 201, po.text
        assert client.post(f"/api/v1/inventory/purchase-orders/{po.json()['id']}/approve", headers=reviewer).status_code == 200

        # Production mode path: durable queue + worker, not a long synchronous HTTP request.
        settings.mrp_inline_execution = False
        settings.rate_limit_mrp_per_minute = 10
        mrp_job = client.post("/api/v1/manufacturing/advanced/mrp-runs", headers=json_admin, json={
            "company_id": 4, "warehouse_id": warehouse["id"], "planning_date": "2026-07-13", "horizon_end": "2026-08-31",
            "demands": [{"item_id": item_by_code["FG-001"]["id"], "due_date": "2026-08-15", "quantity": 7000,
                         "safety_stock": 100, "source_type": "AUDIT_STRESS", "source_reference": "RC11"}],
        })
        assert mrp_job.status_code == 202, mrp_job.text
        job_id = mrp_job.json()["job_id"]
        assert run_once("verify-v111-worker") is True
        job = client.get(f"/api/v1/manufacturing/advanced/jobs/{job_id}", headers=admin)
        assert job.status_code == 200 and job.json()["status"] == "COMPLETED", job.text
        runs = client.get("/api/v1/manufacturing/advanced/mrp-runs?company_id=4", headers=admin).json()
        mrp = next(row for row in runs if row["id"] == job.json()["result_id"])
        raw = next(row for row in mrp["requirements"] if row["item_code"] == "RAW-001")
        fg = next(row for row in mrp["requirements"] if row["item_code"] == "FG-001")
        assert Decimal(str(raw["purchase_receipts"])) > 0
        assert raw["lead_time_days"] == 7 and raw["lot_sizing_policy"] == "FOQ"
        assert Decimal(str(raw["planned_order_quantity"])) % Decimal("50") == 0
        assert raw["planned_release_date"] < raw["planned_receipt_date"]
        assert fg["capacity_status"] in {"ALLOCATED", "INSUFFICIENT_CAPACITY"}
        assert fg["capacity_status"] != "PENDING"
        settings.mrp_inline_execution = True

        # IFRS 9 general approach: SPPI, three stages, PD/LGD/EAD, discounting and three-user approval.
        portfolio = client.post("/api/v1/risk-maintenance/ifrs9/portfolios", headers=json_admin, json={
            "company_id": 1, "code": "GENERAL-RC11", "name_ar": "محفظة عامة", "name_en": "General portfolio",
            "method": "GENERAL", "business_model": "HOLD_TO_COLLECT", "sicr_days_past_due": 30,
            "default_days_past_due": 90, "pd_sicr_multiplier": 2, "forward_looking_overlay": 1.10,
            "model_version": "RC11-1", "buckets": [],
        })
        assert portfolio.status_code == 201, portfolio.text
        portfolio_id = portfolio.json()["id"]
        assert client.post(f"/api/v1/risk-maintenance/ifrs9/portfolios/{portfolio_id}/review", headers=admin).status_code == 409
        assert client.post(f"/api/v1/risk-maintenance/ifrs9/portfolios/{portfolio_id}/review", headers=reviewer).status_code == 200
        assert client.post(f"/api/v1/risk-maintenance/ifrs9/portfolios/{portfolio_id}/approve", headers=approver).status_code == 200
        exposure_rows = [
            {"reference":"LOAN-S1","customer_name":"Stage 1","due_date":"2026-12-31","maturity_date":"2027-12-31",
             "gross_amount":100000,"carrying_amount":100000,"effective_interest_rate":0.06,"initial_12m_pd":0.01,
             "current_12m_pd":0.012,"lifetime_pd":0.05,"lgd":0.40},
            {"reference":"LOAN-S2","customer_name":"Stage 2","due_date":"2026-06-01","maturity_date":"2028-06-01",
             "gross_amount":50000,"carrying_amount":50000,"effective_interest_rate":0.06,"initial_12m_pd":0.01,
             "current_12m_pd":0.03,"lifetime_pd":0.15,"lgd":0.45,"forbearance_flag":True},
            {"reference":"LOAN-S3","customer_name":"Stage 3","due_date":"2026-01-01","maturity_date":"2027-01-01",
             "gross_amount":20000,"carrying_amount":20000,"effective_interest_rate":0.06,"initial_12m_pd":0.02,
             "current_12m_pd":0.50,"lifetime_pd":1,"lgd":0.60,"default_flag":True},
        ]
        for payload in exposure_rows:
            response = client.post("/api/v1/risk-maintenance/ifrs9/exposures", headers=json_admin,
                                   json={"company_id":1,"portfolio_id":portfolio_id,"instrument_type":"LOAN",
                                         "origination_date":"2025-01-01","business_model":"HOLD_TO_COLLECT",
                                         "sppi_passed":True, **payload})
            assert response.status_code == 201, response.text
        ecl = client.post("/api/v1/risk-maintenance/ifrs9/runs", headers=json_admin, json={
            "company_id":1,"portfolio_id":portfolio_id,"as_of_date":"2026-07-15",
            "expense_account_code":"620010","allowance_account_code":"154030"})
        assert ecl.status_code == 201, ecl.text
        ecl_id=ecl.json()["id"]
        assert Decimal(str(ecl.json()["stage_1_ecl"])) > 0 and Decimal(str(ecl.json()["stage_2_ecl"])) > 0 and Decimal(str(ecl.json()["stage_3_ecl"])) > 0
        assert client.post(f"/api/v1/risk-maintenance/ifrs9/runs/{ecl_id}/review", headers=admin).status_code == 409
        assert client.post(f"/api/v1/risk-maintenance/ifrs9/runs/{ecl_id}/review", headers=reviewer).status_code == 200
        ecl_approved=client.post(f"/api/v1/risk-maintenance/ifrs9/runs/{ecl_id}/approve", headers=approver)
        assert ecl_approved.status_code == 200 and ecl_approved.json()["status"] == "APPROVED_POSTED", ecl_approved.text

        # IFRS 16 advanced cases: variable payments, sale-and-leaseback and sublease classification.
        with SessionLocal() as db:
            bank = db.scalar(select(BankAccount).where(BankAccount.company_id == 1, BankAccount.active.is_(True)))
            assert bank
            bank_id = bank.id
        lease = client.post("/api/v1/leases", headers=json_admin, json={
            "company_id":1,"name_ar":"عقد تدقيق RC11","name_en":"RC11 audit lease",
            "commencement_date":"2026-07-15","end_date":"2027-06-30","payment_amount":10000,
            "payment_frequency_months":1,"payment_timing":"ARREARS","annual_discount_rate":0.06,"bank_account_id":bank_id})
        assert lease.status_code == 201, lease.text
        lease_id=lease.json()["id"]
        variable=client.post("/api/v1/leases/advanced/variable-payments",headers=json_admin,json={
            "lease_id":lease_id,"payment_date":"2026-07-20","payment_basis":"PERFORMANCE_USAGE",
            "amount":500,"reason":"Usage-linked rent for audit test","expense_account_code":"612010"})
        assert variable.status_code == 201, variable.text
        variable_id=variable.json()["id"]
        assert client.post(f"/api/v1/leases/advanced/variable-payments/{variable_id}/review",headers=reviewer).status_code == 200
        variable_approved=client.post(f"/api/v1/leases/advanced/variable-payments/{variable_id}/approve",headers=approver)
        assert variable_approved.status_code == 200, variable_approved.text
        liability=Decimal(str(lease.json()["initial_liability"])); fair=money = Decimal("150000.00")
        retained=(liability/fair).quantize(Decimal("0.000001"))
        slb=client.post("/api/v1/leases/advanced/sale-leasebacks",headers=json_admin,json={
            "company_id":1,"lease_id":lease_id,"transaction_date":"2026-07-15","transfer_is_sale":True,
            "carrying_amount":100000,"fair_value":str(fair),"sale_proceeds":str(fair),
            "retained_right_percent":str(retained),"evidence_reference":"Independent valuation RC11",
            "underlying_asset_account_code":"151010","gain_account_code":"421010",
            "financing_liability_account_code":"221010"})
        assert slb.status_code == 201, slb.text
        slb_id=slb.json()["id"]
        assert client.post(f"/api/v1/leases/advanced/sale-leasebacks/{slb_id}/review",headers=reviewer).status_code == 200
        slb_post=client.post(f"/api/v1/leases/advanced/sale-leasebacks/{slb_id}/approve",headers=approver)
        assert slb_post.status_code == 200, slb_post.text
        sub=client.post("/api/v1/leases/advanced/subleases",headers=json_admin,json={
            "company_id":1,"head_lease_id":lease_id,"code":"SUB-RC11","commencement_date":"2026-07-16",
            "end_date":"2027-05-31","payment_amount":9000,"discount_rate":0.06,"carrying_rou_asset":90000,
            "evidence_reference":"Sublease contract RC11","net_investment_account_code":"112010",
            "gain_loss_account_code":"421010"})
        assert sub.status_code == 201 and sub.json()["classification"] == "FINANCE", sub.text
        sub_id=sub.json()["id"]
        assert client.post(f"/api/v1/leases/advanced/subleases/{sub_id}/review",headers=reviewer).status_code == 200
        assert client.post(f"/api/v1/leases/advanced/subleases/{sub_id}/approve",headers=approver).status_code == 200

        release = client.get("/api/v1/system/release").json()
        from app.core.migration_head import expected_migration_head
        assert release["database_schema_head"] == expected_migration_head()
        assert release["version"] == "1.0.0-agreement-completion-rc27.4-r9.4"
        summary = client.get("/api/v1/modules/summary", headers=admin).json()
        assert summary["legacy_demo_endpoints"] == "REMOVED"
        assert summary["migration_head"] == expected_migration_head()
        metrics = client.get("/metrics")
        assert metrics.status_code == 200 and "corvax_http_requests_total" in metrics.text

        # Endpoint-aware rate limiting is enforced before authentication work.
        RateLimitMiddleware._events.clear()
        settings.rate_limit_login_per_minute = 2
        first = client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": PASSWORD})
        second = client.post("/api/v1/auth/login", json={"email": "missing2@example.com", "password": PASSWORD})
        third = client.post("/api/v1/auth/login", json={"email": "missing3@example.com", "password": PASSWORD})
        assert first.status_code == 401 and second.status_code == 401 and third.status_code == 429
        assert third.headers["X-RateLimit-Limit"] == "2"

    # Architecture evidence for HI-10/HI-11.
    assert sum(1 for _ in (ROOT_DIR / "frontend/src/components/Dashboard.tsx").open()) < 80
    model_files = list((BACKEND_DIR / "app/models").glob("*.py"))
    assert max(sum(1 for _ in path.open()) for path in model_files if path.name != "__init__.py") < 500
    assert not any("datetime.utcnow(" in path.read_text() for path in (BACKEND_DIR / "app").rglob("*.py"))
    assert "125750000" not in (BACKEND_DIR / "app/api/modules.py").read_text().replace("_", "")

    print("CORVAX v1.0 RC11 audit remediation: ALL VERIFICATIONS PASSED")


if __name__ == "__main__":
    main()
