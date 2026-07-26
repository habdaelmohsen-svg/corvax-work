from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB = BACKEND_DIR / "data" / "verify_v032.db"
DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["SECRET_KEY"] = "verification-secret-key-v032-long-enough"
os.environ["ENVIRONMENT"] = "testing"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import Account, FiscalPeriod, FiscalYear, JournalEntry, JournalLine, YearEndCloseRun
from app.services.posting import create_posted_journal


def ok(response, status=200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json()


with TestClient(app) as client:
    admin_login = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
    health = ok(client.get("/health"))
    assert health["version"] == "1.0.0-agreement-completion-rc27.3"
    assert health.get("status") == "ok"

    ok(client.post("/api/v1/admin/users", headers=admin_headers, json={
        "name_ar": "مدير مالي للاختبار",
        "name_en": "Verification CFO",
        "email": "cfo.v032@corvaxplatform.com",
        "password": "CfoVerify@123",
        "memberships": [{"company_id": 1, "role_code": "CFO"}],
    }), 201)
    cfo_login = ok(client.post("/api/v1/auth/login", json={"email": "cfo.v032@corvaxplatform.com", "password": "CfoVerify@123"}))
    cfo_headers = {"Authorization": f"Bearer {cfo_login['access_token']}"}

    with SessionLocal() as db:
        year = db.scalar(select(FiscalYear).where(FiscalYear.company_id == 1, FiscalYear.name == "FY 2026"))
        periods = db.scalars(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == year.id).order_by(FiscalPeriod.number)).all()
        for period in periods[:-1]:
            period.status = "CLOSED"
        periods[-1].status = "OPEN"
        accounts = {a.code: a for a in db.scalars(select(Account).where(Account.company_id == 1)).all()}
        admin_id = admin_login["user"]["id"]
        create_posted_journal(
            db,
            company_id=1,
            user_id=admin_id,
            posting_date=year.end_date,
            reference="V032-PROFIT",
            description="Year-end verification operating result",
            lines=[
                {"account_id": accounts["111010"].id, "debit": Decimal("100000"), "credit": 0},
                {"account_id": accounts["411010"].id, "debit": 0, "credit": Decimal("100000")},
            ],
        )
        create_posted_journal(
            db,
            company_id=1,
            user_id=admin_id,
            posting_date=year.end_date,
            reference="V032-EXPENSE",
            description="Year-end verification expenses",
            lines=[
                {"account_id": accounts["613010"].id, "debit": Decimal("60000"), "credit": 0},
                {"account_id": accounts["111010"].id, "debit": 0, "credit": Decimal("60000")},
            ],
        )
        db.commit()
        year_id = year.id
        retained_id = accounts["312010"].id

    review = ok(client.post("/api/v1/year-end-close/review", headers=admin_headers, json={
        "company_id": 1,
        "fiscal_year_id": year_id,
        "retained_earnings_account_id": retained_id,
    }), 201)
    assert Decimal(review["current_year_result"]) == Decimal("40000")
    assert not [c for c in review["checks"] if c["blocking"] and c["status"] == "FAIL"]

    blocked = client.post(f"/api/v1/year-end-close/{review['id']}/close", headers=admin_headers, json={"create_next_year": True})
    assert blocked.status_code == 409

    closed = ok(client.post(f"/api/v1/year-end-close/{review['id']}/close", headers=cfo_headers, json={
        "create_next_year": True,
        "next_year_name": "FY 2027",
    }))
    assert closed["status"] == "CLOSED"
    assert Decimal(closed["current_year_result"]) == Decimal("40000")
    assert closed["next_fiscal_year_id"]

    with SessionLocal() as db:
        year = db.get(FiscalYear, year_id)
        assert year.status == "CLOSED"
        run = db.scalar(select(YearEndCloseRun).where(YearEndCloseRun.fiscal_year_id == year_id))
        assert run.status == "CLOSED" and run.closing_journal_id
        pnl = db.execute(
            select(Account.account_type, func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
            .where(
                Account.company_id == 1,
                Account.account_type.in_(["REVENUE", "EXPENSE"]),
                JournalEntry.entry_date.between(year.start_date, year.end_date),
                JournalEntry.status.in_(["POSTED", "REVERSED"]),
            )
            .group_by(Account.account_type)
        ).all()
        assert all(Decimal(value) == 0 for _, value in pnl), pnl
        retained = db.scalar(
            select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0))
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
            .where(JournalLine.account_id == retained_id, JournalEntry.status.in_(["POSTED", "REVERSED"]))
        )
        assert Decimal(retained) >= Decimal("40000")
        next_year = db.get(FiscalYear, closed["next_fiscal_year_id"])
        next_periods = db.scalars(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == next_year.id).order_by(FiscalPeriod.number)).all()
        assert len(next_periods) == 12 and next_periods[0].status == "OPEN"

print("CORVAX v0.32 year-end close and retained earnings: ALL VERIFICATIONS PASSED")
DB.unlink(missing_ok=True)
