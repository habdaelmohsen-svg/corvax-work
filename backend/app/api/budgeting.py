from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Account, Budget, BudgetLine, FiscalPeriod, FiscalYear, JournalEntry, JournalLine, User
from app.services.audit import write_audit
from app.services.operations import get_account, money

router = APIRouter(prefix="/budgets", tags=["budget control"])


class BudgetLineIn(BaseModel):
    account_code: str
    cost_center_id: int | None = None
    period_number: int = Field(ge=1, le=12)
    amount: Decimal = Field(ge=0)


class BudgetIn(BaseModel):
    company_id: int
    fiscal_year_id: int
    name: str = Field(min_length=2, max_length=150)
    lines: list[BudgetLineIn] = Field(min_length=1)


@router.post("", status_code=201)
def create_budget(data: BudgetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "budget.manage")
    fiscal_year = db.scalar(select(FiscalYear).where(FiscalYear.id == data.fiscal_year_id, FiscalYear.company_id == data.company_id))
    if not fiscal_year:
        raise HTTPException(404, "Fiscal year not found")
    if db.scalar(select(Budget).where(Budget.company_id == data.company_id, Budget.fiscal_year_id == data.fiscal_year_id, Budget.name == data.name)):
        raise HTTPException(409, "Budget already exists")
    budget = Budget(company_id=data.company_id, fiscal_year_id=data.fiscal_year_id, name=data.name, status="DRAFT", created_by=user.id)
    for source in data.lines:
        account = get_account(db, data.company_id, source.account_code)
        budget.lines.append(BudgetLine(account_id=account.id, cost_center_id=source.cost_center_id, period_number=source.period_number, amount=money(source.amount)))
    db.add(budget)
    db.flush()
    write_audit(db, action="BUDGET_CREATED", entity_type="BUDGET", entity_id=budget.id, user_id=user.id, company_id=data.company_id, after={"name": budget.name, "lines": len(budget.lines)})
    db.commit()
    return {"id": budget.id, "name": budget.name, "status": budget.status, "total": sum((line.amount for line in budget.lines), Decimal("0"))}


@router.post("/{budget_id}/approve")
def approve_budget(budget_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    budget = db.get(Budget, budget_id)
    if not budget:
        raise HTTPException(404, "Budget not found")
    ensure_permission(db, user, budget.company_id, "budget.approve")
    if budget.status != "DRAFT":
        raise HTTPException(409, "Only draft budgets can be approved")
    budget.status = "APPROVED"
    budget.approved_by = user.id
    write_audit(db, action="BUDGET_APPROVED", entity_type="BUDGET", entity_id=budget.id, user_id=user.id, company_id=budget.company_id, before={"status": "DRAFT"}, after={"status": "APPROVED"})
    db.commit()
    return {"id": budget.id, "status": budget.status}


def _actual_for_line(db: Session, budget: Budget, line: BudgetLine) -> Decimal:
    period = db.scalar(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == budget.fiscal_year_id, FiscalPeriod.number == line.period_number))
    if not period:
        return Decimal("0")
    query = (
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(
            JournalEntry.company_id == budget.company_id,
            JournalEntry.status.in_(["POSTED", "REVERSED"]),
            JournalEntry.entry_date.between(period.start_date, period.end_date),
            JournalLine.account_id == line.account_id,
        )
    )
    if line.cost_center_id:
        query = query.where(JournalLine.cost_center_id == line.cost_center_id)
    value = Decimal(db.scalar(query) or 0)
    if line.account.account_type == "REVENUE":
        value = -value
    return money(value)


@router.get("/{budget_id}/control")
def budget_control(budget_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    budget = db.scalar(select(Budget).where(Budget.id == budget_id).options(selectinload(Budget.lines).selectinload(BudgetLine.account)))
    if not budget:
        raise HTTPException(404, "Budget not found")
    ensure_permission(db, user, budget.company_id, "budget.read")
    rows = []
    totals = {"budget": Decimal("0"), "actual": Decimal("0"), "committed": Decimal("0"), "reserved": Decimal("0"), "available": Decimal("0")}
    for line in budget.lines:
        actual = _actual_for_line(db, budget, line)
        available = money(line.amount - actual - line.committed_amount - line.reserved_amount)
        row = {
            "line_id": line.id,
            "account_code": line.account.code,
            "account_name_ar": line.account.name_ar,
            "account_name_en": line.account.name_en,
            "period_number": line.period_number,
            "budget": line.amount,
            "actual": actual,
            "committed": line.committed_amount,
            "reserved": line.reserved_amount,
            "available": available,
            "variance": money(line.amount - actual),
            "utilization_percent": money((actual + line.committed_amount + line.reserved_amount) / line.amount * 100) if line.amount else Decimal("0"),
        }
        rows.append(row)
        for key in totals:
            totals[key] += Decimal(row[key])
    return {"budget_id": budget.id, "name": budget.name, "status": budget.status, "totals": {key: money(value) for key, value in totals.items()}, "lines": rows}


@router.get("")
def list_budgets(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "budget.read")
    rows = db.scalars(select(Budget).where(Budget.company_id == company_id).options(selectinload(Budget.lines)).order_by(Budget.id.desc())).all()
    return [{"id": row.id, "name": row.name, "status": row.status, "version": row.version, "total": sum((line.amount for line in row.lines), Decimal("0"))} for row in rows]
