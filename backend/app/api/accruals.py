from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (
    Account, AccrualEntry, Branch, CostCenter, RecurringJournalLine,
    RecurringJournalRun, RecurringJournalTemplate, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/accruals", tags=["accruals and recurring journals"])


class AccrualIn(BaseModel):
    company_id: int
    accrual_type: str = "EXPENSE_ACCRUAL"
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    reference: str | None = Field(default=None, max_length=120)
    accrual_date: date
    amount: Decimal = Field(gt=0)
    debit_account_code: str | None = None
    credit_account_code: str | None = None
    branch_id: int | None = None
    cost_center_id: int | None = None
    auto_reverse: bool = True
    reversal_date: date | None = None

    @model_validator(mode="after")
    def validate_reversal(self):
        self.accrual_type = self.accrual_type.upper()
        if self.accrual_type not in {"EXPENSE_ACCRUAL", "REVENUE_ACCRUAL"}:
            raise ValueError("Unsupported accrual type")
        if self.auto_reverse and not self.reversal_date:
            raise ValueError("Reversal date is required when auto reverse is enabled")
        if self.reversal_date and self.reversal_date <= self.accrual_date:
            raise ValueError("Reversal date must be after accrual date")
        return self


class ReversalRunIn(BaseModel):
    company_id: int
    as_of_date: date


class RecurringLineIn(BaseModel):
    account_code: str
    description: str | None = Field(default=None, max_length=500)
    debit: Decimal = Field(default=0, ge=0)
    credit: Decimal = Field(default=0, ge=0)
    branch_id: int | None = None
    cost_center_id: int | None = None


class RecurringTemplateIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=50)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    reference_prefix: str = Field(default="REC", min_length=2, max_length=80)
    frequency: str = "MONTHLY"
    start_date: date
    end_date: date | None = None
    auto_post: bool = True
    lines: list[RecurringLineIn] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_template(self):
        self.frequency = self.frequency.upper()
        if self.frequency not in {"MONTHLY", "QUARTERLY", "ANNUAL"}:
            raise ValueError("Frequency must be MONTHLY, QUARTERLY or ANNUAL")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        debit = sum((x.debit for x in self.lines), Decimal("0"))
        credit = sum((x.credit for x in self.lines), Decimal("0"))
        if debit <= 0 or debit != credit:
            raise ValueError("Recurring journal lines must be balanced")
        for line in self.lines:
            if (line.debit > 0) == (line.credit > 0):
                raise ValueError("Each recurring line must contain either debit or credit")
        return self


class RecurringRunIn(BaseModel):
    company_id: int
    as_of_date: date


def _validate_dimension(db: Session, company_id: int, branch_id: int | None, cost_center_id: int | None) -> None:
    if branch_id and not db.scalar(select(Branch.id).where(Branch.id == branch_id, Branch.company_id == company_id)):
        raise HTTPException(422, "Branch does not belong to company")
    if cost_center_id and not db.scalar(select(CostCenter.id).where(CostCenter.id == cost_center_id, CostCenter.company_id == company_id)):
        raise HTTPException(422, "Cost center does not belong to company")


def _next_accrual_number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(AccrualEntry.id)).where(AccrualEntry.company_id == company_id)) or 0
    return f"ACR-{company_id}-{year}-{count + 1:05d}"


def _add_months(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(absolute, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _next_run_date(value: date, frequency: str) -> date:
    return _add_months(value, {"MONTHLY": 1, "QUARTERLY": 3, "ANNUAL": 12}[frequency])


def _serialize_accrual(row: AccrualEntry) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number,
        "accrual_type": row.accrual_type, "name_ar": row.name_ar, "name_en": row.name_en,
        "reference": row.reference, "accrual_date": row.accrual_date, "amount": money(row.amount),
        "debit_account_id": row.debit_account_id, "credit_account_id": row.credit_account_id,
        "branch_id": row.branch_id, "cost_center_id": row.cost_center_id,
        "auto_reverse": row.auto_reverse, "reversal_date": row.reversal_date,
        "status": row.status, "journal_id": row.journal_id,
        "reversal_journal_id": row.reversal_journal_id, "created_at": row.created_at,
        "posted_at": row.posted_at, "reversed_at": row.reversed_at,
    }


def _serialize_template(row: RecurringJournalTemplate) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "code": row.code,
        "name_ar": row.name_ar, "name_en": row.name_en,
        "reference_prefix": row.reference_prefix, "frequency": row.frequency,
        "start_date": row.start_date, "end_date": row.end_date, "next_run_date": row.next_run_date,
        "auto_post": row.auto_post, "active": row.active,
        "lines": [
            {"account_code": x.account.code if x.account else None, "description": x.description,
             "debit": money(x.debit), "credit": money(x.credit),
             "branch_id": x.branch_id, "cost_center_id": x.cost_center_id}
            for x in row.lines
        ],
        "runs": [
            {"id": x.id, "run_date": x.run_date, "status": x.status,
             "journal_id": x.journal_id, "executed_at": x.executed_at}
            for x in sorted(row.runs, key=lambda r: r.run_date, reverse=True)
        ],
    }


@router.post("", status_code=201)
def create_accrual(data: AccrualIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "accruals.manage")
    _validate_dimension(db, data.company_id, data.branch_id, data.cost_center_id)
    if data.accrual_type == "EXPENSE_ACCRUAL":
        debit_code = data.debit_account_code or "613010"
        credit_code = data.credit_account_code or "217010"
    else:
        debit_code = data.debit_account_code or "118010"
        credit_code = data.credit_account_code or "411010"
    debit_account = get_account(db, data.company_id, debit_code)
    credit_account = get_account(db, data.company_id, credit_code)
    row = AccrualEntry(
        company_id=data.company_id, number=_next_accrual_number(db, data.company_id, data.accrual_date.year),
        accrual_type=data.accrual_type, name_ar=data.name_ar, name_en=data.name_en,
        reference=data.reference, accrual_date=data.accrual_date, amount=money(data.amount),
        debit_account_id=debit_account.id, credit_account_id=credit_account.id,
        branch_id=data.branch_id, cost_center_id=data.cost_center_id,
        auto_reverse=data.auto_reverse, reversal_date=data.reversal_date,
        status="DRAFT", created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="ACCRUAL_CREATED", entity_type="ACCRUAL", entity_id=row.id,
                user_id=user.id, company_id=data.company_id,
                after={"number": row.number, "type": row.accrual_type, "amount": str(row.amount)})
    db.commit()
    return _serialize_accrual(row)


@router.post("/{accrual_id}/post")
def post_accrual(accrual_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(AccrualEntry, accrual_id)
    if not row:
        raise HTTPException(404, "Accrual not found")
    ensure_permission(db, user, row.company_id, "accruals.post")
    if row.status != "DRAFT":
        raise HTTPException(409, "Only draft accruals can be posted")
    journal = create_posted_journal(
        db, company_id=row.company_id, user_id=user.id, posting_date=row.accrual_date,
        reference=row.number, description=f"Accrual: {row.name_en}",
        lines=[
            {"account_id": row.debit_account_id, "debit": row.amount, "credit": 0,
             "branch_id": row.branch_id, "cost_center_id": row.cost_center_id},
            {"account_id": row.credit_account_id, "debit": 0, "credit": row.amount,
             "branch_id": row.branch_id, "cost_center_id": row.cost_center_id},
        ],
    )
    row.status = "POSTED"; row.journal_id = journal.id; row.posted_by = user.id; row.posted_at = utc_now()
    write_audit(db, action="ACCRUAL_POSTED", entity_type="ACCRUAL", entity_id=row.id,
                user_id=user.id, company_id=row.company_id,
                after={"journal_id": journal.id, "reversal_date": str(row.reversal_date) if row.reversal_date else None})
    db.commit()
    return _serialize_accrual(row)


@router.post("/run-reversals")
def run_reversals(data: ReversalRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "accruals.reverse")
    rows = db.scalars(
        select(AccrualEntry).where(
            AccrualEntry.company_id == data.company_id,
            AccrualEntry.status == "POSTED",
            AccrualEntry.auto_reverse.is_(True),
            AccrualEntry.reversal_date.is_not(None),
            AccrualEntry.reversal_date <= data.as_of_date,
            AccrualEntry.reversal_journal_id.is_(None),
        ).order_by(AccrualEntry.reversal_date, AccrualEntry.id)
    ).all()
    result = []
    for row in rows:
        journal = create_posted_journal(
            db, company_id=row.company_id, user_id=user.id, posting_date=row.reversal_date,
            reference=f"REV-{row.number}", description=f"Automatic reversal: {row.name_en}",
            lines=[
                {"account_id": row.credit_account_id, "debit": row.amount, "credit": 0,
                 "branch_id": row.branch_id, "cost_center_id": row.cost_center_id},
                {"account_id": row.debit_account_id, "debit": 0, "credit": row.amount,
                 "branch_id": row.branch_id, "cost_center_id": row.cost_center_id},
            ],
        )
        row.status = "REVERSED"; row.reversal_journal_id = journal.id
        row.reversed_by = user.id; row.reversed_at = utc_now()
        result.append({"accrual_id": row.id, "number": row.number, "journal_id": journal.id})
    write_audit(db, action="ACCRUAL_REVERSAL_RUN", entity_type="ACCRUAL_RUN", entity_id=str(data.as_of_date),
                user_id=user.id, company_id=data.company_id, after={"count": len(result)})
    db.commit()
    return {"reversed_count": len(result), "items": result}


@router.get("")
def list_accruals(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "accruals.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, AccrualEntry)
    query = select(AccrualEntry).where(AccrualEntry.company_id == company_id)
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.order_by(AccrualEntry.accrual_date.desc(), AccrualEntry.id.desc())).all()
    return [_serialize_accrual(x) for x in rows]


@router.get("/summary")
def summary(company_id: int, as_of_date: date = Query(default_factory=date.today), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "accruals.read")
    rows = db.scalars(select(AccrualEntry).where(AccrualEntry.company_id == company_id, AccrualEntry.accrual_date <= as_of_date)).all()
    templates_due = db.scalar(select(func.count(RecurringJournalTemplate.id)).where(
        RecurringJournalTemplate.company_id == company_id, RecurringJournalTemplate.active.is_(True),
        RecurringJournalTemplate.next_run_date <= as_of_date,
        (RecurringJournalTemplate.end_date.is_(None) | (RecurringJournalTemplate.next_run_date <= RecurringJournalTemplate.end_date)),
    )) or 0
    return {
        "entries": len(rows),
        "expense_accruals": money(sum((Decimal(x.amount) for x in rows if x.accrual_type == "EXPENSE_ACCRUAL" and x.status != "DRAFT"), Decimal("0"))),
        "revenue_accruals": money(sum((Decimal(x.amount) for x in rows if x.accrual_type == "REVENUE_ACCRUAL" and x.status != "DRAFT"), Decimal("0"))),
        "drafts": sum(1 for x in rows if x.status == "DRAFT"),
        "due_reversals": sum(1 for x in rows if x.status == "POSTED" and x.auto_reverse and x.reversal_date and x.reversal_date <= as_of_date),
        "recurring_due": templates_due,
    }


@router.post("/recurring", status_code=201)
def create_recurring_template(data: RecurringTemplateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "recurring.manage")
    if db.scalar(select(RecurringJournalTemplate.id).where(RecurringJournalTemplate.company_id == data.company_id, RecurringJournalTemplate.code == data.code)):
        raise HTTPException(409, "Recurring template code already exists")
    codes = {x.account_code for x in data.lines}
    accounts = {x.code: x for x in db.scalars(select(Account).where(Account.company_id == data.company_id, Account.code.in_(codes), Account.active.is_(True), Account.is_postable.is_(True))).all()}
    missing = codes - set(accounts)
    if missing:
        raise HTTPException(422, f"Unknown or non-postable accounts: {', '.join(sorted(missing))}")
    for line in data.lines:
        _validate_dimension(db, data.company_id, line.branch_id, line.cost_center_id)
    row = RecurringJournalTemplate(
        company_id=data.company_id, code=data.code, name_ar=data.name_ar, name_en=data.name_en,
        reference_prefix=data.reference_prefix, frequency=data.frequency, start_date=data.start_date,
        end_date=data.end_date, next_run_date=data.start_date, auto_post=data.auto_post,
        active=True, created_by=user.id,
    )
    for line in data.lines:
        row.lines.append(RecurringJournalLine(
            account_id=accounts[line.account_code].id, description=line.description,
            debit=money(line.debit), credit=money(line.credit), branch_id=line.branch_id, cost_center_id=line.cost_center_id,
        ))
    db.add(row); db.flush()
    write_audit(db, action="RECURRING_TEMPLATE_CREATED", entity_type="RECURRING_JOURNAL", entity_id=row.id,
                user_id=user.id, company_id=data.company_id,
                after={"code": row.code, "frequency": row.frequency, "next_run_date": str(row.next_run_date)})
    db.commit()
    row = db.scalar(select(RecurringJournalTemplate).options(selectinload(RecurringJournalTemplate.lines).selectinload(RecurringJournalLine.account), selectinload(RecurringJournalTemplate.runs)).where(RecurringJournalTemplate.id == row.id))
    return _serialize_template(row)


@router.post("/recurring/run")
def run_recurring(data: RecurringRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "recurring.run")
    templates = db.scalars(select(RecurringJournalTemplate).options(selectinload(RecurringJournalTemplate.lines)).where(
        RecurringJournalTemplate.company_id == data.company_id,
        RecurringJournalTemplate.active.is_(True),
        RecurringJournalTemplate.next_run_date <= data.as_of_date,
    ).order_by(RecurringJournalTemplate.next_run_date, RecurringJournalTemplate.id)).all()
    generated = []
    for template in templates:
        while template.active and template.next_run_date <= data.as_of_date:
            if template.end_date and template.next_run_date > template.end_date:
                template.active = False
                break
            run_date = template.next_run_date
            existing = db.scalar(select(RecurringJournalRun.id).where(RecurringJournalRun.template_id == template.id, RecurringJournalRun.run_date == run_date))
            if not existing:
                journal = create_posted_journal(
                    db, company_id=template.company_id, user_id=user.id, posting_date=run_date,
                    reference=f"{template.reference_prefix}-{run_date.isoformat()}",
                    description=f"Recurring journal: {template.name_en}",
                    lines=[{"account_id": x.account_id, "debit": x.debit, "credit": x.credit,
                            "branch_id": x.branch_id, "cost_center_id": x.cost_center_id,
                            "description": x.description} for x in template.lines],
                )
                db.add(RecurringJournalRun(template_id=template.id, run_date=run_date, status="POSTED", journal_id=journal.id, executed_by=user.id))
                generated.append({"template_id": template.id, "code": template.code, "run_date": run_date, "journal_id": journal.id})
            template.next_run_date = _next_run_date(run_date, template.frequency)
            if template.end_date and template.next_run_date > template.end_date:
                template.active = False
    write_audit(db, action="RECURRING_JOURNAL_RUN", entity_type="RECURRING_RUN", entity_id=str(data.as_of_date),
                user_id=user.id, company_id=data.company_id, after={"generated_count": len(generated)})
    db.commit()
    return {"generated_count": len(generated), "items": generated}


@router.get("/recurring")
def list_recurring(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "recurring.read")
    rows = db.scalars(select(RecurringJournalTemplate).options(
        selectinload(RecurringJournalTemplate.lines).selectinload(RecurringJournalLine.account),
        selectinload(RecurringJournalTemplate.runs),
    ).where(RecurringJournalTemplate.company_id == company_id).order_by(RecurringJournalTemplate.id.desc())).all()
    return [_serialize_template(x) for x in rows]
