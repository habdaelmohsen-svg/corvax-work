"""CORVAX Final Internal Release verification."""
from __future__ import annotations
import os, sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_final_internal.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-final-internal",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r9.2",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})
import subprocess
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=True)
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.db import SessionLocal
from app.main import app
from app.models import FiscalPeriod, FiscalYear, InternalCostRun, JournalEntry, PlanningScenario, ReadinessAssessment, User


def D(v): return Decimal(str(v)).quantize(Decimal("0.01"))
def ok(r, status=200): assert r.status_code == status, r.text; return r.json()


def main():
    with TestClient(app) as c:
        # The release test validates business workflows, not the interactive
        # first-login screen. Mark only the seeded test administrator as having
        # completed that mandatory step.
        with SessionLocal() as db:
            admin_user = db.scalar(select(User).where(User.email == "admin@corvaxplatform.com"))
            assert admin_user
            admin_user.require_password_change = False
            db.commit()
        login = ok(c.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        admin = {"Authorization": f"Bearer {login['access_token']}"}
        assert ok(c.get("/health"))["version"] == "1.0.0-agreement-completion-rc27.4-r9.2"
        # Compare against the live head so this test cannot rot (audit M-05).
        from app.core.migration_head import expected_migration_head
        assert ok(c.get("/health/ready"))["migration_head"] == expected_migration_head()
        for email, name in (("final.reviewer@corvaxplatform.com", "Final Reviewer"), ("final.approver@corvaxplatform.com", "Final Approver")):
            ok(c.post("/api/v1/admin/users", headers=admin, json={
                "name_ar": name, "name_en": name, "email": email, "password": "FinalControl@123",
                "require_password_change": False,
                "memberships": [{"company_id": 1, "role_code": "SUPER_ADMIN"}],
            }), 201)
        reviewer_login = ok(c.post("/api/v1/auth/login", json={"email": "final.reviewer@corvaxplatform.com", "password": "FinalControl@123"}))
        approver_login = ok(c.post("/api/v1/auth/login", json={"email": "final.approver@corvaxplatform.com", "password": "FinalControl@123"}))
        reviewer = {"Authorization": f"Bearer {reviewer_login['access_token']}"}
        approver = {"Authorization": f"Bearer {approver_login['access_token']}"}

        with SessionLocal() as db:
            db.execute(text("update fiscal_periods set status='OPEN'"))
            year = db.scalar(select(FiscalYear).where(FiscalYear.company_id == 1).order_by(FiscalYear.start_date.desc()))
            assert year
            period = db.scalar(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == year.id, FiscalPeriod.start_date <= date(2026,7,31), FiscalPeriod.end_date >= date(2026,7,31)))
            assert period
            year_id, period_id = year.id, period.id
            horizon_start, horizon_end = year.start_date.isoformat(), year.end_date.isoformat()
            db.commit()

        cost = ok(c.post("/api/v1/internal-completion/costing/runs", headers=admin, json={
            "company_id":1,"code":"FINAL-COST-01","period_start":"2026-07-01","period_end":"2026-07-31","posting_date":"2026-07-31",
            "standard_output_quantity":1000,"actual_output_quantity":950,
            "materials":[
                {"code":"RM-A","name_ar":"مادة أ","name_en":"Material A","standard_quantity":500,"actual_quantity":520,"standard_price":10,"actual_price":11,"source_reference":"ISSUE-A"},
                {"code":"RM-B","name_ar":"مادة ب","name_en":"Material B","standard_quantity":250,"actual_quantity":240,"standard_price":6,"actual_price":5.5,"source_reference":"ISSUE-B"}
            ],
            "labor":{"standard_hours":300,"actual_hours":330,"standard_rate":25,"actual_rate":27},
            "overhead":{"standard_variable_rate":8,"actual_variable_rate":9,"standard_fixed_rate":12,"budgeted_fixed_overhead":3600,"actual_fixed_overhead":3900,"normal_capacity_hours":400,"productive_hours":330},
            "joint_cost_total":10000,
            "joint_outputs":[
                {"code":"MAIN-A","quantity":600,"selling_price":40,"separable_cost":2000,"is_byproduct":False},
                {"code":"MAIN-B","quantity":300,"selling_price":30,"separable_cost":1000,"is_byproduct":False},
                {"code":"BY-P","quantity":50,"selling_price":8,"separable_cost":50,"is_byproduct":True}
            ],
            "service_pools":[
                {"code":"MAINT","name_ar":"الصيانة","name_en":"Maintenance","direct_cost":1000,"allocations":[{"target_code":"IT","percent":0.2},{"target_code":"PROD-A","percent":0.8}]},
                {"code":"IT","name_ar":"تقنية المعلومات","name_en":"IT","direct_cost":500,"allocations":[{"target_code":"PROD-A","percent":0.6},{"target_code":"PROD-B","percent":0.4}]}
            ],
            "rework_cost":300,"reference":"FINAL-TEST"
        }), 201)
        categories = {x["category"] for x in cost["lines"]}
        assert {"MATERIAL_PRICE","MATERIAL_MIX","MATERIAL_YIELD","LABOR_RATE","LABOR_EFFICIENCY","VARIABLE_OH_SPENDING","VARIABLE_OH_EFFICIENCY","FIXED_OH_BUDGET","FIXED_OH_VOLUME","IDLE_CAPACITY_MEMO","JOINT_COST_ALLOCATION","SERVICE_DEPARTMENT_ALLOCATION","REWORK"}.issubset(categories)
        assert D(cost["idle_capacity_cost"]) == D(840)
        assert c.post(f"/api/v1/internal-completion/costing/runs/{cost['id']}/review", headers=admin).status_code == 409
        ok(c.post(f"/api/v1/internal-completion/costing/runs/{cost['id']}/review", headers=reviewer))
        assert c.post(f"/api/v1/internal-completion/costing/runs/{cost['id']}/approve-post", headers=reviewer).status_code == 409
        cost = ok(c.post(f"/api/v1/internal-completion/costing/runs/{cost['id']}/approve-post", headers=approver))
        assert cost["status"] == "APPROVED_POSTED" and cost["journal_id"]
        drill = ok(c.get("/api/v1/internal-completion/drilldown?company_id=1&account_code=624010&start_date=2026-07-01&end_date=2026-07-31", headers=admin))
        assert drill["rows"] and drill["rows"][0]["source_hint"] == "COST_VARIANCE"
        export = c.get("/api/v1/internal-completion/costing/runs/export.csv?company_id=1", headers=admin)
        assert export.status_code == 200 and export.content.startswith(b"\xef\xbb\xbf")

        scenario = ok(c.post("/api/v1/internal-completion/planning/scenarios", headers=admin, json={
            "company_id":1,"fiscal_year_id":year_id,"name":"Final Operating Budget","scenario_type":"BUDGET",
            "horizon_start":horizon_start,"horizon_end":horizon_end,"assumptions":{"volume_growth":0.10},
            "commentary_ar":"موازنة تشغيلية نهائية","commentary_en":"Final operating budget",
            "lines":[{"account_code":"624010","period_start":"2026-07-01","period_end":"2026-07-31","granularity":"MONTHLY","amount":500,"department_code":"FACTORY","source_type":"DRIVER","driver_name":"Output units","driver_value":950}]
        }), 201)
        ok(c.post(f"/api/v1/internal-completion/planning/scenarios/{scenario['id']}/submit", headers=admin))
        ok(c.post(f"/api/v1/internal-completion/planning/scenarios/{scenario['id']}/review", headers=reviewer))
        ok(c.post(f"/api/v1/internal-completion/planning/scenarios/{scenario['id']}/approve", headers=approver))
        scenario = ok(c.post(f"/api/v1/internal-completion/planning/scenarios/{scenario['id']}/freeze", headers=approver))
        assert scenario["status"] == "FROZEN"
        variance = ok(c.get(f"/api/v1/internal-completion/planning/scenarios/{scenario['id']}/variance", headers=admin))
        assert len(variance["rows"]) == 1 and D(variance["rows"][0]["actual"]) != D(0)

        backup = ok(c.post("/api/v1/backups?company_id=1", headers=admin), 201)
        backup = ok(c.post(f"/api/v1/backups/{backup['id']}/verify", headers=admin))
        assert backup["status"] == "VERIFIED"

        close = ok(c.post("/api/v1/internal-completion/close/runs", headers=admin, json={"company_id":1,"fiscal_period_id":period_id}), 201)
        assert close["blocker_count"] == 0, close
        assert any(x["code"] == "VERIFIED_BACKUP" and x["status"] == "PASS" for x in close["checks"])
        ok(c.post(f"/api/v1/internal-completion/close/runs/{close['id']}/review", headers=reviewer))
        close = ok(c.post(f"/api/v1/internal-completion/close/runs/{close['id']}/approve-close", headers=approver))
        assert close["status"] == "CLOSED"

        ready = ok(c.post("/api/v1/internal-completion/readiness/assessments", headers=admin, json={"company_id":1,"environment_name":"TEST","target_stage":"INTERNAL_RELEASE","evidence":{"restore_drill_passed":True}}), 201)
        assert ready["blocker_count"] == 0
        assert any(x["code"] == "ZATCA" and x["status"] == "EXTERNAL" for x in ready["checks"])
        ok(c.post(f"/api/v1/internal-completion/readiness/assessments/{ready['id']}/review", headers=reviewer))
        ready = ok(c.post(f"/api/v1/internal-completion/readiness/assessments/{ready['id']}/approve", headers=approver))
        assert ready["status"] == "APPROVED"
        ready_export = c.get(f"/api/v1/internal-completion/readiness/assessments/{ready['id']}/export.csv", headers=admin)
        assert ready_export.status_code == 200 and ready_export.content.startswith(b"\xef\xbb\xbf")

        with SessionLocal() as db:
            assert db.scalar(select(InternalCostRun).where(InternalCostRun.code == "FINAL-COST-01")).status == "APPROVED_POSTED"
            assert db.scalar(select(PlanningScenario).where(PlanningScenario.name == "Final Operating Budget")).status == "FROZEN"
            assert db.scalar(select(ReadinessAssessment).where(ReadinessAssessment.id == ready["id"])).status == "APPROVED"
            assert not db.execute(select(JournalEntry.id).where(JournalEntry.total_debit != JournalEntry.total_credit)).all()
            assert not db.execute(text("PRAGMA foreign_key_check")).all()
    print("CORVAX v1.0 Final Internal Release: ALL VERIFICATIONS PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__": main()
