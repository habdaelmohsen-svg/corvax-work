from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import BankAccount, PrepaidExpense, PrepaidExpenseSchedule, User
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/prepaids", tags=["prepaid expenses"])


class PrepaidIn(BaseModel):
    company_id: int
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    supplier_name: str | None = Field(default=None, max_length=250)
    payment_date: date
    service_start_date: date
    service_end_date: date
    net_amount: Decimal = Field(gt=0)
    vat_rate: Decimal = Field(default=0, ge=0, le=100)
    allocation_method: str = "MONTHLY_STRAIGHT_LINE"
    expense_account_code: str = "613010"
    prepaid_account_code: str = "117010"
    bank_account_id: int
    branch_id: int | None = None
    cost_center_id: int | None = None


class AmortizeIn(BaseModel):
    company_id: int
    as_of_date: date


def month_end(value: date) -> date:
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def next_month(value: date) -> date:
    return date(value.year + (1 if value.month == 12 else 0), 1 if value.month == 12 else value.month + 1, 1)


def next_number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(PrepaidExpense.id)).where(PrepaidExpense.company_id == company_id)) or 0
    return f"PP-{company_id}-{year}-{count + 1:05d}"


def build_schedule(start: date, end: date, amount: Decimal, method: str) -> list[tuple[date, Decimal]]:
    if end < start:
        raise HTTPException(422, "Service end date must be on or after start date")
    method = method.upper()
    if method not in {"MONTHLY_STRAIGHT_LINE", "DAILY_PRORATA"}:
        raise HTTPException(422, "Unsupported allocation method")
    periods: list[tuple[date, Decimal]] = []
    cursor = date(start.year, start.month, 1)
    total_days = Decimal((end - start).days + 1)
    while cursor <= end:
        p_end = month_end(cursor)
        overlap_start = max(start, cursor)
        overlap_end = min(end, p_end)
        if overlap_start <= overlap_end:
            if method == "DAILY_PRORATA":
                days = Decimal((overlap_end - overlap_start).days + 1)
                raw = amount * days / total_days
            else:
                raw = Decimal("0")
            periods.append((p_end, raw))
        cursor = next_month(cursor)
    if method == "MONTHLY_STRAIGHT_LINE":
        equal = money(amount / Decimal(len(periods)))
        periods = [(p, equal) for p, _ in periods]
    rounded: list[tuple[date, Decimal]] = []
    allocated = Decimal("0")
    for i, (period_date, raw) in enumerate(periods):
        value = money(amount - allocated) if i == len(periods) - 1 else money(raw)
        rounded.append((period_date, value))
        allocated += value
    return rounded


def serialize(row: PrepaidExpense) -> dict:
    return {
        "id": row.id,
        "number": row.number,
        "name_ar": row.name_ar,
        "name_en": row.name_en,
        "supplier_name": row.supplier_name,
        "payment_date": row.payment_date,
        "service_start_date": row.service_start_date,
        "service_end_date": row.service_end_date,
        "allocation_method": row.allocation_method,
        "net_amount": row.net_amount,
        "vat_amount": row.vat_amount,
        "gross_amount": row.gross_amount,
        "amortized_amount": row.amortized_amount,
        "remaining_amount": row.remaining_amount,
        "status": row.status,
        "schedules": [
            {"id": s.id, "period_date": s.period_date, "amount": s.amount, "status": s.status, "journal_id": s.journal_id}
            for s in sorted(row.schedules, key=lambda x: x.period_date)
        ],
    }


@router.post("", status_code=201)
def create_prepaid(data: PrepaidIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "prepaids.manage")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not bank:
        raise HTTPException(404, "Bank account not found")
    net = money(data.net_amount)
    vat = money(net * data.vat_rate / Decimal("100"))
    gross = money(net + vat)
    prepaid_account = get_account(db, data.company_id, data.prepaid_account_code)
    expense_account = get_account(db, data.company_id, data.expense_account_code)
    vat_account = get_account(db, data.company_id, "114010") if vat else None
    schedule = build_schedule(data.service_start_date, data.service_end_date, net, data.allocation_method)
    number = next_number(db, data.company_id, data.payment_date.year)
    lines = [
        {"account_id": prepaid_account.id, "debit": net, "credit": 0, "branch_id": data.branch_id, "cost_center_id": data.cost_center_id},
        {"account_id": bank.gl_account_id, "debit": 0, "credit": gross, "branch_id": data.branch_id, "cost_center_id": data.cost_center_id},
    ]
    if vat:
        lines.insert(1, {"account_id": vat_account.id, "debit": vat, "credit": 0, "branch_id": data.branch_id, "cost_center_id": data.cost_center_id})
    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=data.payment_date,
        reference=number, description=f"Prepaid expense payment {number}", lines=lines,
        cash_flow_activity="OPERATING", cash_flow_kind="PREPAID_SERVICE_PAYMENT",
    )
    row = PrepaidExpense(
        company_id=data.company_id, number=number, name_ar=data.name_ar, name_en=data.name_en,
        supplier_name=data.supplier_name, payment_date=data.payment_date,
        service_start_date=data.service_start_date, service_end_date=data.service_end_date,
        allocation_method=data.allocation_method.upper(), net_amount=net, vat_rate=data.vat_rate,
        vat_amount=vat, gross_amount=gross, amortized_amount=Decimal("0"), remaining_amount=net,
        prepaid_account_id=prepaid_account.id, expense_account_id=expense_account.id,
        bank_account_id=bank.id, branch_id=data.branch_id, cost_center_id=data.cost_center_id,
        status="ACTIVE", initial_journal_id=journal.id, created_by=user.id,
    )
    for period_date, amount in schedule:
        row.schedules.append(PrepaidExpenseSchedule(period_date=period_date, amount=amount, status="PENDING"))
    db.add(row); db.flush()
    write_audit(db, action="PREPAID_EXPENSE_CREATED", entity_type="PREPAID_EXPENSE", entity_id=row.id,
                user_id=user.id, company_id=data.company_id,
                after={"number": number, "net_amount": str(net), "months": len(schedule), "journal": journal.number})
    db.commit(); db.refresh(row)
    return serialize(row)


@router.post("/amortize")
def amortize(data: AmortizeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "prepaids.amortize")
    rows = db.scalars(
        select(PrepaidExpense)
        .where(PrepaidExpense.company_id == data.company_id, PrepaidExpense.status == "ACTIVE")
        .options(selectinload(PrepaidExpense.schedules))
        .order_by(PrepaidExpense.id)
    ).all()
    posted = []
    for row in rows:
        due = [s for s in row.schedules if s.status == "PENDING" and s.period_date <= data.as_of_date]
        for schedule in sorted(due, key=lambda x: x.period_date):
            journal = create_posted_journal(
                db, company_id=data.company_id, user_id=user.id, posting_date=schedule.period_date,
                reference=row.number, description=f"Prepaid amortization {row.number} - {schedule.period_date}",
                lines=[
                    {"account_id": row.expense_account_id, "debit": schedule.amount, "credit": 0, "branch_id": row.branch_id, "cost_center_id": row.cost_center_id},
                    {"account_id": row.prepaid_account_id, "debit": 0, "credit": schedule.amount, "branch_id": row.branch_id, "cost_center_id": row.cost_center_id},
                ],
            )
            schedule.status = "POSTED"; schedule.journal_id = journal.id; schedule.posted_by = user.id; schedule.posted_at = utc_now()
            row.amortized_amount = money(row.amortized_amount + schedule.amount)
            row.remaining_amount = money(row.net_amount - row.amortized_amount)
            posted.append({"number": row.number, "period_date": schedule.period_date, "amount": schedule.amount, "journal": journal.number})
        if row.remaining_amount <= 0:
            row.remaining_amount = Decimal("0"); row.status = "CLOSED"
    write_audit(db, action="PREPAID_AMORTIZATION_RUN", entity_type="PREPAID_EXPENSE", entity_id="BATCH",
                user_id=user.id, company_id=data.company_id,
                after={"as_of_date": str(data.as_of_date), "posted_count": len(posted), "amount": str(sum((x["amount"] for x in posted), Decimal("0")))})
    db.commit()
    return {"company_id": data.company_id, "as_of_date": data.as_of_date, "posted_count": len(posted),
            "amortized_amount": sum((x["amount"] for x in posted), Decimal("0")), "entries": posted}


@router.get("")
def list_prepaids(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "prepaids.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, PrepaidExpense)
    query = select(PrepaidExpense).where(PrepaidExpense.company_id == company_id)
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.options(selectinload(PrepaidExpense.schedules)).order_by(PrepaidExpense.id.desc())).all()
    return [serialize(row) for row in rows]


@router.get("/summary")
def summary(company_id: int, as_of_date: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "prepaids.read")
    cutoff = as_of_date or date.today()
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, PrepaidExpense)
    query = select(PrepaidExpense).where(PrepaidExpense.company_id == company_id)
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.options(selectinload(PrepaidExpense.schedules))).all()
    return {
        "contracts": len(rows),
        "gross_prepaid": money(sum((Decimal(r.net_amount) for r in rows), Decimal("0"))),
        "amortized": money(sum((Decimal(r.amortized_amount) for r in rows), Decimal("0"))),
        "remaining": money(sum((Decimal(r.remaining_amount) for r in rows), Decimal("0"))),
        "due_unposted": sum(1 for r in rows for s in r.schedules if s.status == "PENDING" and s.period_date <= cutoff),
        "active": sum(1 for r in rows if r.status == "ACTIVE"),
    }
