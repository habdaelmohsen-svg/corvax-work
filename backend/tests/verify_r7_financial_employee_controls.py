"""R7 employee-style verification for critical financial controls.

The script deliberately uses a brand-new database and proves accounting/state
effects, not only successful HTTP responses:

* IFRS 16 payments in advance model exactly twelve contractual payments and
  keep the reporting-period end separate from the cash-payment date.
* Bank statement preparation, matching and final reconciliation are performed
  by three different non-superusers.
* Partial and overlapping VAT return periods are rejected.
* A fiscal year can be closed, reopened and closed again without doubling the
  current-year profit or retained earnings.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

DB_PATH = Path("/tmp/verify_r7_financial_employee_controls.db")
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verify-r7-financial-employee-controls-secret"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["ENVIRONMENT"] = "testing"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    AuditLog,
    BankAccount,
    BankStatement,
    FiscalPeriod,
    FiscalYear,
    JournalEntry,
    JournalLine,
    LeaseContract,
    User,
)
from app.services.posting import create_posted_journal  # noqa: E402


def ok(response, status: int = 200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json()


def login(client: TestClient, email: str, password: str) -> tuple[dict[str, str], int]:
    payload = ok(client.post("/api/v1/auth/login", json={"email": email, "password": password}))
    return {"Authorization": f"Bearer {payload['access_token']}"}, int(payload["user"]["id"])


def create_employee(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    email: str,
    password: str,
    name_en: str,
    memberships: list[dict],
) -> tuple[dict[str, str], int]:
    ok(
        client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "name_ar": name_en,
                "name_en": name_en,
                "email": email,
                "password": password,
                "require_password_change": False,
                "memberships": memberships,
            },
        ),
        201,
    )
    return login(client, email, password)


def decimal(value) -> Decimal:
    return Decimal(str(value))


measurements: dict[str, object] = {}


try:
    with TestClient(app) as client:
        admin_headers, admin_id = login(
            client, "admin@corvaxplatform.com", "Corvax@123"
        )

        maker_headers, maker_id = create_employee(
            client,
            admin_headers,
            email="r7.bank.maker@corvaxplatform.com",
            password="R7BankMaker@123",
            name_en="R7 Bank Statement Maker",
            memberships=[{"company_id": 1, "role_code": "ACCOUNTANT"}],
        )
        matcher_headers, matcher_id = create_employee(
            client,
            admin_headers,
            email="r7.bank.matcher@corvaxplatform.com",
            password="R7BankMatcher@123",
            name_en="R7 Bank Statement Matcher",
            memberships=[{"company_id": 1, "role_code": "ACCOUNTANT"}],
        )
        reconciler_headers, reconciler_id = create_employee(
            client,
            admin_headers,
            email="r7.bank.reconciler@corvaxplatform.com",
            password="R7BankReconciler@123",
            name_en="R7 Bank Reconciliation Approver",
            memberships=[
                {"company_id": 1, "role_code": "FINANCIAL_CONTROLLER"},
                {"company_id": 4, "role_code": "CFO"},
            ],
        )
        assert len({maker_id, matcher_id, reconciler_id}) == 3

        # ------------------------------------------------------------------
        # IFRS 16 ADVANCE: 10,000 at commencement + 11 later instalments.
        # ------------------------------------------------------------------
        company_bank = ok(
            client.get("/api/v1/banking/accounts?company_id=1", headers=admin_headers)
        )[0]
        lease = ok(
            client.post(
                "/api/v1/leases",
                headers=admin_headers,
                json={
                    "company_id": 1,
                    "name_ar": "عقد إيجار مقدم لاختبار R7",
                    "name_en": "R7 Advance Lease",
                    "commencement_date": "2026-07-01",
                    "end_date": "2027-06-30",
                    "payment_amount": 10000,
                    "payment_frequency_months": 1,
                    "payment_timing": "ADVANCE",
                    "annual_discount_rate": 0.05,
                    "bank_account_id": company_bank["id"],
                },
            ),
            201,
        )
        assert len(lease["schedule"]) == 12

        # Open August only so the first future advance cash payment can be
        # posted independently from the July reporting-period accrual.
        with SessionLocal() as db:
            fy_2026 = db.scalar(
                select(FiscalYear).where(
                    FiscalYear.company_id == 1, FiscalYear.name == "FY 2026"
                )
            )
            august = db.scalar(
                select(FiscalPeriod).where(
                    FiscalPeriod.fiscal_year_id == fy_2026.id,
                    FiscalPeriod.number == 8,
                )
            )
            august.status = "OPEN"
            db.commit()

        first_run = ok(
            client.post(
                "/api/v1/leases/post-schedules",
                headers=admin_headers,
                json={"company_id": 1, "as_of_date": "2026-08-01"},
            )
        )
        assert first_run["posted_count"] == 1
        assert first_run["journal_count"] == 2

        with SessionLocal() as db:
            stored_lease = db.scalar(
                select(LeaseContract)
                .where(LeaseContract.id == lease["id"])
                .options(selectinload(LeaseContract.schedules))
            )
            schedules = sorted(stored_lease.schedules, key=lambda row: row.period_number)
            scheduled_cash = sum((decimal(row.payment) for row in schedules), Decimal("0"))
            bank = db.get(BankAccount, int(company_bank["id"]))
            commencement_cash = decimal(
                db.scalar(
                    select(func.coalesce(func.sum(JournalLine.credit), 0)).where(
                        JournalLine.journal_id == stored_lease.initial_journal_id,
                        JournalLine.account_id == bank.gl_account_id,
                    )
                )
            )
            contractual_cash = commencement_cash + scheduled_cash
            first_schedule = schedules[0]
            accrual_journal = db.get(JournalEntry, first_schedule.accrual_journal_id)
            cash_journal = db.get(JournalEntry, first_schedule.cash_journal_id)

            assert commencement_cash == Decimal("10000.00")
            assert scheduled_cash == Decimal("110000.00")
            assert contractual_cash == Decimal("120000.00")
            assert contractual_cash != Decimal("130000.00")
            assert first_schedule.period_end_date == date(2026, 7, 31)
            assert first_schedule.cash_payment_date == date(2026, 8, 1)
            assert accrual_journal.entry_date == first_schedule.period_end_date
            assert cash_journal.entry_date == first_schedule.cash_payment_date
            assert accrual_journal.id != cash_journal.id
            assert first_schedule.accrual_status == "POSTED"
            assert first_schedule.cash_status == "POSTED"

        measurements["ifrs16_advance"] = {
            "commencement_cash": str(commencement_cash),
            "future_scheduled_cash": str(scheduled_cash),
            "contractual_cash": str(contractual_cash),
            "wrong_130k_rejected": contractual_cash != Decimal("130000.00"),
            "first_period_end": str(first_schedule.period_end_date),
            "first_future_cash_date": str(first_schedule.cash_payment_date),
            "first_run_journals": first_run["journal_count"],
        }

        # ------------------------------------------------------------------
        # Bank SoD: maker -> independent matcher -> independent approver.
        # ------------------------------------------------------------------
        statement = ok(
            client.post(
                "/api/v1/banking/statements",
                headers=maker_headers,
                json={
                    "company_id": 1,
                    "bank_account_id": company_bank["id"],
                    "statement_date": "2026-01-01",
                    "opening_balance": 0,
                    "closing_balance": 2000000,
                    "lines": [
                        {
                            "transaction_date": "2026-01-01",
                            "reference": "OPENING",
                            "description": "R7 opening capital bank line",
                            "amount": 2000000,
                            "direction": "CREDIT",
                        }
                    ],
                },
            ),
            201,
        )

        maker_match_block = client.post(
            f"/api/v1/banking/statements/{statement['id']}/auto-match",
            headers=maker_headers,
        )
        assert maker_match_block.status_code == 409, maker_match_block.text
        reconciler_prepare_block = client.post(
            f"/api/v1/banking/statements/{statement['id']}/auto-match",
            headers=reconciler_headers,
        )
        assert reconciler_prepare_block.status_code == 403, reconciler_prepare_block.text

        matched = ok(
            client.post(
                f"/api/v1/banking/statements/{statement['id']}/auto-match",
                headers=matcher_headers,
            )
        )
        assert matched["status"] == "MATCHED"
        assert matched["matched_now"] == 1
        assert matched["unmatched"] == 0

        matcher_reconcile_block = client.post(
            f"/api/v1/banking/statements/{statement['id']}/reconcile",
            headers=matcher_headers,
        )
        assert matcher_reconcile_block.status_code == 403, matcher_reconcile_block.text
        reconciled = ok(
            client.post(
                f"/api/v1/banking/statements/{statement['id']}/reconcile",
                headers=reconciler_headers,
            )
        )
        assert reconciled["status"] == "RECONCILED"
        assert decimal(reconciled["gl_balance"]) == Decimal("2000000.00")
        assert decimal(reconciled["statement_balance"]) == Decimal("2000000.00")
        assert decimal(reconciled["difference"]) == Decimal("0.00")

        with SessionLocal() as db:
            stored_statement = db.get(BankStatement, statement["id"])
            assert stored_statement.created_by == maker_id
            assert stored_statement.matched_by == matcher_id
            assert stored_statement.reconciled_by == reconciler_id
            assert len(
                {
                    stored_statement.created_by,
                    stored_statement.matched_by,
                    stored_statement.reconciled_by,
                }
            ) == 3
            bank_audits = db.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "BANK_STATEMENT",
                    AuditLog.entity_id == str(statement["id"]),
                    AuditLog.action.in_(
                        [
                            "BANK_STATEMENT_CREATED",
                            "BANK_STATEMENT_AUTO_MATCHED",
                            "BANK_STATEMENT_RECONCILED",
                        ]
                    ),
                )
            ).all()
            action_users = {row.action: row.user_id for row in bank_audits}
            assert action_users == {
                "BANK_STATEMENT_CREATED": maker_id,
                "BANK_STATEMENT_AUTO_MATCHED": matcher_id,
                "BANK_STATEMENT_RECONCILED": reconciler_id,
            }

        measurements["bank_sod"] = {
            "maker_id": maker_id,
            "matcher_id": matcher_id,
            "reconciler_id": reconciler_id,
            "maker_match_block": maker_match_block.status_code,
            "reconciler_prepare_block": reconciler_prepare_block.status_code,
            "matcher_reconcile_block": matcher_reconcile_block.status_code,
            "gl_balance": str(decimal(reconciled["gl_balance"])),
            "statement_balance": str(decimal(reconciled["statement_balance"])),
            "difference": str(decimal(reconciled["difference"])),
        }

        # ------------------------------------------------------------------
        # VAT: reject an incomplete period and a valid-but-overlapping period.
        # ------------------------------------------------------------------
        partial_vat = client.post(
            "/api/v1/compliance/vat-return",
            headers=admin_headers,
            json={
                "company_id": 1,
                "period_start": "2026-07-01",
                "period_end": "2026-07-15",
            },
        )
        assert partial_vat.status_code == 422, partial_vat.text

        july_vat = ok(
            client.post(
                "/api/v1/compliance/vat-return",
                headers=admin_headers,
                json={
                    "company_id": 1,
                    "period_start": "2026-07-01",
                    "period_end": "2026-07-31",
                },
            ),
            201,
        )
        overlapping_vat = client.post(
            "/api/v1/compliance/vat-return",
            headers=admin_headers,
            json={
                "company_id": 1,
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
            },
        )
        assert overlapping_vat.status_code == 409, overlapping_vat.text

        measurements["vat_period_controls"] = {
            "partial_period_status": partial_vat.status_code,
            "valid_july_return_id": july_vat["id"],
            "valid_july_status": july_vat["status"],
            "overlapping_quarter_status": overlapping_vat.status_code,
        }

        # ------------------------------------------------------------------
        # Year close -> reopen -> close: profit remains 40k, never 80k.
        # Company 4 is intentionally isolated from the lease/VAT/bank cycle.
        # ------------------------------------------------------------------
        with SessionLocal() as db:
            year = db.scalar(
                select(FiscalYear).where(
                    FiscalYear.company_id == 4, FiscalYear.name == "FY 2026"
                )
            )
            periods = db.scalars(
                select(FiscalPeriod)
                .where(FiscalPeriod.fiscal_year_id == year.id)
                .order_by(FiscalPeriod.number)
            ).all()
            for period in periods[:-1]:
                period.status = "CLOSED"
            periods[-1].status = "OPEN"

            accounts = {
                row.code: row
                for row in db.scalars(
                    select(Account).where(Account.company_id == 4)
                ).all()
            }
            create_posted_journal(
                db,
                company_id=4,
                user_id=admin_id,
                posting_date=year.end_date,
                reference="R7-YEAR-PROFIT",
                description="R7 year-end revenue",
                lines=[
                    {"account_id": accounts["111010"].id, "debit": 100000, "credit": 0},
                    {"account_id": accounts["411010"].id, "debit": 0, "credit": 100000},
                ],
            )
            create_posted_journal(
                db,
                company_id=4,
                user_id=admin_id,
                posting_date=year.end_date,
                reference="R7-YEAR-EXPENSE",
                description="R7 year-end expense",
                lines=[
                    {"account_id": accounts["613010"].id, "debit": 60000, "credit": 0},
                    {"account_id": accounts["111010"].id, "debit": 0, "credit": 60000},
                ],
            )
            db.commit()
            year_id = year.id
            retained_id = accounts["312010"].id

        first_review = ok(
            client.post(
                "/api/v1/year-end-close/review",
                headers=admin_headers,
                json={
                    "company_id": 4,
                    "fiscal_year_id": year_id,
                    "retained_earnings_account_id": retained_id,
                },
            ),
            201,
        )
        first_profit = decimal(first_review["current_year_result"])
        assert first_profit == Decimal("40000")
        assert not [
            row
            for row in first_review["checks"]
            if row["blocking"] and row["status"] == "FAIL"
        ]

        same_user_close = client.post(
            f"/api/v1/year-end-close/{first_review['id']}/close",
            headers=admin_headers,
            json={"create_next_year": False},
        )
        assert same_user_close.status_code == 409, same_user_close.text

        first_close = ok(
            client.post(
                f"/api/v1/year-end-close/{first_review['id']}/close",
                headers=reconciler_headers,
                json={"create_next_year": False},
            )
        )
        assert decimal(first_close["current_year_result"]) == Decimal("40000")

        reopened = ok(
            client.post(
                f"/api/v1/year-end-close/{first_review['id']}/reopen",
                headers=reconciler_headers,
                json={"reason": "R7 controlled reopen and reclose verification"},
            )
        )
        assert reopened["status"] == "REOPENED"

        second_review = ok(
            client.post(
                "/api/v1/year-end-close/review",
                headers=admin_headers,
                json={
                    "company_id": 4,
                    "fiscal_year_id": year_id,
                    "retained_earnings_account_id": retained_id,
                },
            ),
            201,
        )
        second_profit = decimal(second_review["current_year_result"])
        assert second_profit == Decimal("40000")
        assert second_profit != Decimal("80000")
        assert not [
            row
            for row in second_review["checks"]
            if row["blocking"] and row["status"] == "FAIL"
        ]

        second_close = ok(
            client.post(
                f"/api/v1/year-end-close/{second_review['id']}/close",
                headers=reconciler_headers,
                json={"create_next_year": False},
            )
        )
        assert decimal(second_close["current_year_result"]) == Decimal("40000")
        assert second_close["closing_journal_id"] != first_close["closing_journal_id"]

        with SessionLocal() as db:
            original_close = db.get(JournalEntry, first_close["closing_journal_id"])
            assert original_close.status == "REVERSED"
            assert original_close.reversed_entry_id == reopened["reversal_journal_id"]

            pnl_rows = db.execute(
                select(
                    Account.account_type,
                    func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0),
                )
                .join(JournalLine, JournalLine.account_id == Account.id)
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                .where(
                    Account.company_id == 4,
                    Account.account_type.in_(["REVENUE", "EXPENSE"]),
                    JournalEntry.entry_date.between(date(2026, 1, 1), date(2026, 12, 31)),
                    JournalEntry.status.in_(["POSTED", "REVERSED"]),
                )
                .group_by(Account.account_type)
            ).all()
            pnl_by_type = {kind: decimal(value) for kind, value in pnl_rows}
            assert all(value == 0 for value in pnl_by_type.values()), pnl_by_type

            retained_net = decimal(
                db.scalar(
                    select(func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0))
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                    .where(
                        JournalLine.account_id == retained_id,
                        JournalEntry.status.in_(["POSTED", "REVERSED"]),
                    )
                )
            )
            assert retained_net == Decimal("40000.00")
            assert retained_net != Decimal("80000.00")

        measurements["year_end_reclose"] = {
            "first_profit": str(first_profit),
            "second_profit_after_reopen": str(second_profit),
            "wrong_80k_rejected": second_profit != Decimal("80000"),
            "retained_earnings_net": str(retained_net),
            "pnl_after_second_close": {
                key: str(value) for key, value in sorted(pnl_by_type.items())
            },
            "same_user_close_block": same_user_close.status_code,
            "first_closing_journal_id": first_close["closing_journal_id"],
            "reversal_journal_id": reopened["reversal_journal_id"],
            "second_closing_journal_id": second_close["closing_journal_id"],
        }

    print("R7 FINANCIAL EMPLOYEE CONTROLS: ALL VERIFICATIONS PASSED")
    for section, values in measurements.items():
        print(f"{section}: {values}")
finally:
    DB_PATH.unlink(missing_ok=True)
