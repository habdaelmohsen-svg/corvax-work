from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account,
    FiscalPeriod,
    FiscalYear,
    JournalEntry,
    JournalLine,
    User,
    YearEndCloseCheck,
    YearEndCloseRun,
)
from app.services.audit import write_audit
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/year-end-close", tags=["year-end close"])


class YearEndReviewIn(BaseModel):
    company_id: int
    fiscal_year_id: int
    retained_earnings_account_id: int | None = None


class YearEndApproveIn(BaseModel):
    create_next_year: bool = True
    next_year_name: str | None = Field(default=None, max_length=50)


class YearEndReopenIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


def _fiscal_year(db: Session, company_id: int, fiscal_year_id: int) -> FiscalYear:
    year = db.scalar(select(FiscalYear).where(FiscalYear.id == fiscal_year_id, FiscalYear.company_id == company_id))
    if not year:
        raise HTTPException(404, "Fiscal year not found")
    return year


def _retained_earnings(db: Session, company_id: int, account_id: int | None) -> Account:
    account = db.get(Account, account_id) if account_id else db.scalar(
        select(Account).where(
            Account.company_id == company_id,
            Account.statement_group == "RETAINED_EARNINGS",
            Account.active.is_(True),
        )
    )
    if not account or account.company_id != company_id or account.account_type != "EQUITY" or not account.is_postable:
        raise HTTPException(422, "Valid postable retained earnings account is required")
    return account


def _account_balances(db: Session, company_id: int, year: FiscalYear) -> list[dict]:
    rows = db.execute(
        select(
            Account.id,
            Account.code,
            Account.name_ar,
            Account.name_en,
            Account.account_type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(
            Account.company_id == company_id,
            Account.account_type.in_(["REVENUE", "EXPENSE"]),
            JournalEntry.company_id == company_id,
            JournalEntry.entry_date.between(year.start_date, year.end_date),
            JournalEntry.status.in_(["POSTED", "REVERSED"]),
            ~JournalEntry.reference.like("YEC-%"),
        )
        .group_by(Account.id, Account.code, Account.name_ar, Account.name_en, Account.account_type)
        .order_by(Account.code)
    ).all()
    result = []
    for account_id, code, ar, en, account_type, debit, credit in rows:
        debit_d, credit_d = Decimal(debit), Decimal(credit)
        balance = (credit_d - debit_d) if account_type == "REVENUE" else (debit_d - credit_d)
        if balance != 0:
            result.append({
                "account_id": account_id,
                "code": code,
                "name_ar": ar,
                "name_en": en,
                "account_type": account_type,
                "balance": balance,
            })
    return result


def _current_result(balances: list[dict]) -> Decimal:
    revenue = sum((row["balance"] for row in balances if row["account_type"] == "REVENUE"), Decimal("0"))
    expenses = sum((row["balance"] for row in balances if row["account_type"] == "EXPENSE"), Decimal("0"))
    return revenue - expenses


def _checks(db: Session, company_id: int, year: FiscalYear, retained: Account) -> tuple[list[dict], Decimal]:
    periods = db.scalars(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == year.id).order_by(FiscalPeriod.number)).all()
    final_period = periods[-1] if periods else None
    prior_open = [p.number for p in periods[:-1] if p.status != "CLOSED"]
    final_status_ok = bool(final_period and final_period.status == "OPEN")
    unposted = db.scalar(select(func.count(JournalEntry.id)).where(
        JournalEntry.company_id == company_id,
        JournalEntry.entry_date.between(year.start_date, year.end_date),
        JournalEntry.status.not_in(["POSTED", "REVERSED"]),
    )) or 0
    debit, credit = db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(
            JournalEntry.company_id == company_id,
            JournalEntry.entry_date <= year.end_date,
            JournalEntry.status.in_(["POSTED", "REVERSED"]),
        )
    ).one()
    tb_diff = Decimal(debit) - Decimal(credit)
    duplicate = db.scalar(select(func.count(JournalEntry.id)).where(
        JournalEntry.company_id == company_id,
        JournalEntry.reference == f"YEC-{year.id}",
        JournalEntry.status.in_(["POSTED", "REVERSED"]),
    )) or 0
    balances = _account_balances(db, company_id, year)
    result = _current_result(balances)
    checks = [
        {"code": "FISCAL_PERIODS_EXIST", "ar": "الفترات المالية موجودة", "en": "Fiscal periods exist", "status": "PASS" if periods else "FAIL", "blocking": True, "details": {"count": len(periods)}},
        {"code": "PRIOR_PERIODS_CLOSED", "ar": "جميع الفترات السابقة مغلقة", "en": "All prior periods are closed", "status": "PASS" if not prior_open else "FAIL", "blocking": True, "details": {"open_periods": prior_open}},
        {"code": "FINAL_PERIOD_OPEN", "ar": "الفترة النهائية مفتوحة لقيد الإقفال", "en": "Final period is open for closing journal", "status": "PASS" if final_status_ok else "FAIL", "blocking": True, "details": {"period": final_period.number if final_period else None, "status": final_period.status if final_period else None}},
        {"code": "NO_UNPOSTED_JOURNALS", "ar": "لا توجد قيود غير مرحلة خلال السنة", "en": "No unposted journals in the year", "status": "PASS" if unposted == 0 else "FAIL", "blocking": True, "details": {"count": unposted}},
        {"code": "TRIAL_BALANCE", "ar": "ميزان المراجعة متوازن", "en": "Trial balance is balanced", "status": "PASS" if tb_diff == 0 else "FAIL", "blocking": True, "details": {"difference": str(tb_diff)}},
        {"code": "RETAINED_EARNINGS_ACCOUNT", "ar": "حساب الأرباح المبقاة صالح للترحيل", "en": "Retained earnings account is valid", "status": "PASS", "blocking": True, "details": {"account_id": retained.id, "code": retained.code}},
        {"code": "NO_EXISTING_CLOSE", "ar": "لم يتم إنشاء قيد إقفال سابق", "en": "No prior year-end closing journal", "status": "PASS" if duplicate == 0 else "FAIL", "blocking": True, "details": {"count": duplicate}},
        {"code": "PROFIT_LOSS_BALANCES", "ar": "تم احتساب أرصدة الإيرادات والمصروفات", "en": "Revenue and expense balances calculated", "status": "PASS", "blocking": False, "details": {"accounts": len(balances), "current_year_result": str(result)}},
    ]
    return checks, result


def _serialize(run: YearEndCloseRun, checks: list[YearEndCloseCheck]) -> dict:
    return {
        "id": run.id,
        "company_id": run.company_id,
        "fiscal_year_id": run.fiscal_year_id,
        "status": run.status,
        "retained_earnings_account_id": run.retained_earnings_account_id,
        "current_year_result": str(run.current_year_result),
        "closing_journal_id": run.closing_journal_id,
        "requested_by": run.requested_by,
        "approved_by": run.approved_by,
        "created_at": run.created_at,
        "closed_at": run.closed_at,
        "checks": [
            {
                "code": c.code,
                "name_ar": c.name_ar,
                "name_en": c.name_en,
                "status": c.status,
                "blocking": c.blocking,
                "details": json.loads(c.details or "{}"),
            }
            for c in checks
        ],
    }


def _create_next_year(db: Session, company_id: int, current: FiscalYear, name: str | None) -> FiscalYear:
    next_start = date(current.end_date.year + 1, 1, 1)
    next_end = date(current.end_date.year + 1, 12, 31)
    existing = db.scalar(select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.start_date == next_start))
    if existing:
        return existing
    next_year = FiscalYear(
        company_id=company_id,
        name=name or f"FY {next_start.year}",
        start_date=next_start,
        end_date=next_end,
        status="OPEN",
    )
    db.add(next_year)
    db.flush()
    for month in range(1, 13):
        start = date(next_start.year, month, 1)
        end = date(next_start.year, month, monthrange(next_start.year, month)[1])
        db.add(FiscalPeriod(
            fiscal_year_id=next_year.id,
            number=month,
            name_ar=f"الفترة {month}",
            name_en=f"Period {month}",
            start_date=start,
            end_date=end,
            status="OPEN" if month == 1 else "FUTURE",
        ))
    return next_year


@router.post("/review", status_code=201)
def review_year_end(data: YearEndReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "year.close")
    year = _fiscal_year(db, data.company_id, data.fiscal_year_id)
    if year.status == "CLOSED":
        raise HTTPException(409, "Fiscal year is already closed")
    retained = _retained_earnings(db, data.company_id, data.retained_earnings_account_id)
    run = db.scalar(select(YearEndCloseRun).where(YearEndCloseRun.company_id == data.company_id, YearEndCloseRun.fiscal_year_id == year.id))
    if not run:
        run = YearEndCloseRun(
            company_id=data.company_id,
            fiscal_year_id=year.id,
            status="REVIEWED",
            retained_earnings_account_id=retained.id,
            requested_by=user.id,
        )
        db.add(run)
        db.flush()
    else:
        if run.status == "CLOSED":
            raise HTTPException(409, "Year-end close already completed")
        db.query(YearEndCloseCheck).filter(YearEndCloseCheck.year_end_run_id == run.id).delete()
        run.status = "REVIEWED"
        run.retained_earnings_account_id = retained.id
        run.requested_by = user.id
        run.approved_by = None
        run.closed_at = None
    generated, result = _checks(db, data.company_id, year, retained)
    run.current_year_result = result
    for item in generated:
        db.add(YearEndCloseCheck(
            year_end_run_id=run.id,
            code=item["code"],
            name_ar=item["ar"],
            name_en=item["en"],
            status=item["status"],
            blocking=item["blocking"],
            details=json.dumps(item["details"], default=str),
        ))
    db.flush()
    checks = db.scalars(select(YearEndCloseCheck).where(YearEndCloseCheck.year_end_run_id == run.id).order_by(YearEndCloseCheck.id)).all()
    write_audit(db, action="YEAR_END_CLOSE_REVIEWED", entity_type="YEAR_END_CLOSE", entity_id=run.id, user_id=user.id, company_id=data.company_id, after={"year": year.name, "result": str(result), "failed": [c.code for c in checks if c.status == "FAIL"]})
    db.commit()
    return _serialize(run, checks)


@router.post("/{run_id}/close")
def close_year(run_id: int, data: YearEndApproveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(YearEndCloseRun, run_id)
    if not run:
        raise HTTPException(404, "Year-end close run not found")
    ensure_permission(db, user, run.company_id, "year.close")
    if run.requested_by == user.id:
        raise HTTPException(409, "Maker-checker control: requester cannot approve year-end close")
    if run.status == "CLOSED":
        raise HTTPException(409, "Year-end close already completed")
    year = _fiscal_year(db, run.company_id, run.fiscal_year_id)
    retained = _retained_earnings(db, run.company_id, run.retained_earnings_account_id)
    generated, result = _checks(db, run.company_id, year, retained)
    failures = [item["code"] for item in generated if item["blocking"] and item["status"] == "FAIL"]
    if failures:
        raise HTTPException(409, {"message": "Blocking year-end checks failed", "checks": failures})

    balances = _account_balances(db, run.company_id, year)
    lines: list[dict] = []
    total_revenue = Decimal("0")
    total_expense = Decimal("0")
    for row in balances:
        amount = row["balance"]
        if row["account_type"] == "REVENUE":
            total_revenue += amount
            lines.append({"account_id": row["account_id"], "debit": amount, "credit": 0, "description": f"Close revenue {row['code']}"})
        else:
            total_expense += amount
            lines.append({"account_id": row["account_id"], "debit": 0, "credit": amount, "description": f"Close expense {row['code']}"})
    if result > 0:
        lines.append({"account_id": retained.id, "debit": 0, "credit": result, "description": "Transfer current-year profit to retained earnings"})
    elif result < 0:
        lines.append({"account_id": retained.id, "debit": abs(result), "credit": 0, "description": "Transfer current-year loss to retained earnings"})
    if not lines:
        raise HTTPException(409, "No profit or loss balances to close")

    journal = create_posted_journal(
        db,
        company_id=run.company_id,
        user_id=user.id,
        posting_date=year.end_date,
        reference=f"YEC-{year.id}",
        description=f"Year-end closing entry {year.name}",
        lines=lines,
    )
    final_period = db.scalar(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == year.id).order_by(FiscalPeriod.number.desc()))
    if final_period:
        final_period.status = "CLOSED"
    year.status = "CLOSED"
    run.status = "CLOSED"
    run.current_year_result = result
    run.closing_journal_id = journal.id
    run.approved_by = user.id
    run.closed_at = utc_now()
    next_year = _create_next_year(db, run.company_id, year, data.next_year_name) if data.create_next_year else None
    write_audit(db, action="FISCAL_YEAR_CLOSED", entity_type="FISCAL_YEAR", entity_id=year.id, user_id=user.id, company_id=run.company_id, after={"year": year.name, "result": str(result), "closing_journal_id": journal.id, "next_year_id": next_year.id if next_year else None})
    db.commit()
    return {
        "run_id": run.id,
        "fiscal_year_id": year.id,
        "status": "CLOSED",
        "current_year_result": str(result),
        "closing_journal_id": journal.id,
        "next_fiscal_year_id": next_year.id if next_year else None,
        "closed_at": run.closed_at,
    }


@router.post("/{run_id}/reopen")
def reopen_year(run_id: int, data: YearEndReopenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(YearEndCloseRun, run_id)
    if not run:
        raise HTTPException(404, "Year-end close run not found")
    ensure_permission(db, user, run.company_id, "year.close")
    if run.status != "CLOSED" or not run.closing_journal_id:
        raise HTTPException(409, "Only a completed year-end close can be reopened")
    year = _fiscal_year(db, run.company_id, run.fiscal_year_id)
    final_period = db.scalar(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == year.id).order_by(FiscalPeriod.number.desc()))
    if not final_period:
        raise HTTPException(409, "Final fiscal period not found")
    year.status = "OPEN"
    final_period.status = "OPEN"
    closing = db.get(JournalEntry, run.closing_journal_id)
    if not closing:
        raise HTTPException(409, "Closing journal not found")
    reversal_lines = [{
        "account_id": line.account_id,
        "debit": line.credit,
        "credit": line.debit,
        "description": f"Reverse year-end close: {line.description or closing.description}",
    } for line in closing.lines]
    reversal = create_posted_journal(
        db,
        company_id=run.company_id,
        user_id=user.id,
        posting_date=year.end_date,
        reference=f"YER-{year.id}",
        description=f"Reopen fiscal year {year.name}: {data.reason}",
        lines=reversal_lines,
    )
    run.status = "REOPENED"
    run.approved_by = user.id
    write_audit(db, action="FISCAL_YEAR_REOPENED", entity_type="FISCAL_YEAR", entity_id=year.id, user_id=user.id, company_id=run.company_id, after={"reason": data.reason, "reversal_journal_id": reversal.id})
    db.commit()
    return {"run_id": run.id, "fiscal_year_id": year.id, "status": "REOPENED", "reversal_journal_id": reversal.id, "reason": data.reason}


@router.get("/runs")
def list_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    runs = db.scalars(select(YearEndCloseRun).where(YearEndCloseRun.company_id == company_id).order_by(YearEndCloseRun.created_at.desc())).all()
    result = []
    for run in runs:
        checks = db.scalars(select(YearEndCloseCheck).where(YearEndCloseCheck.year_end_run_id == run.id).order_by(YearEndCloseCheck.id)).all()
        result.append(_serialize(run, checks))
    return result
