from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    BankStatement, FiscalPeriod, FiscalYear, JournalEntry, JournalLine, LeaseContract, LeaseSchedule,
    MembershipContract, NonConformance, PayrollRun, PeriodCloseCheck, PeriodCloseRun, PosOrder, RevenueSchedule,
    StockMovement, User, PrepaidExpense, PrepaidExpenseSchedule, AccrualEntry, RecurringJournalTemplate,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/period-close", tags=["financial close"])


class CloseRequestIn(BaseModel):
    company_id: int
    fiscal_period_id: int


class ReopenIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


def _period_company(db: Session, period_id: int, company_id: int) -> FiscalPeriod:
    period = db.scalar(
        select(FiscalPeriod)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalYear.company_id == company_id)
    )
    if not period:
        raise HTTPException(404, "Fiscal period not found")
    return period


def _checks(db: Session, company_id: int, period: FiscalPeriod) -> list[dict]:
    start, end = period.start_date, period.end_date
    unposted = db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.company_id == company_id, JournalEntry.entry_date.between(start, end), JournalEntry.status.not_in(["POSTED", "REVERSED"]))) or 0
    unreconciled = db.scalar(select(func.count(BankStatement.id)).where(BankStatement.company_id == company_id, BankStatement.statement_date.between(start, end), BankStatement.status != "RECONCILED")) or 0
    pending_pos = db.scalar(select(func.count(PosOrder.id)).where(PosOrder.company_id == company_id, PosOrder.order_date.between(start, end), PosOrder.status == "PENDING_SETTLEMENT")) or 0
    incomplete_payroll = db.scalar(select(func.count(PayrollRun.id)).where(PayrollRun.company_id == company_id, PayrollRun.period_year == start.year, PayrollRun.period_month == start.month, PayrollRun.status.not_in(["PAID"]))) or 0
    due_revenue = db.scalar(select(func.count(RevenueSchedule.id)).join(MembershipContract, MembershipContract.id == RevenueSchedule.contract_id).where(MembershipContract.company_id == company_id, RevenueSchedule.recognition_date <= end, RevenueSchedule.status == "PENDING")) or 0
    due_leases = db.scalar(select(func.count(LeaseSchedule.id)).join(LeaseContract, LeaseContract.id == LeaseSchedule.lease_id).where(LeaseContract.company_id == company_id, LeaseSchedule.payment_date <= end, LeaseSchedule.status == "PENDING")) or 0
    due_prepaids = db.scalar(select(func.count(PrepaidExpenseSchedule.id)).join(PrepaidExpense, PrepaidExpense.id == PrepaidExpenseSchedule.prepaid_expense_id).where(PrepaidExpense.company_id == company_id, PrepaidExpenseSchedule.period_date <= end, PrepaidExpenseSchedule.status == "PENDING")) or 0
    draft_accruals = db.scalar(select(func.count(AccrualEntry.id)).where(AccrualEntry.company_id == company_id, AccrualEntry.accrual_date <= end, AccrualEntry.status == "DRAFT")) or 0
    due_reversals = db.scalar(select(func.count(AccrualEntry.id)).where(AccrualEntry.company_id == company_id, AccrualEntry.status == "POSTED", AccrualEntry.auto_reverse.is_(True), AccrualEntry.reversal_date.is_not(None), AccrualEntry.reversal_date <= end, AccrualEntry.reversal_journal_id.is_(None))) or 0
    due_recurring = db.scalar(select(func.count(RecurringJournalTemplate.id)).where(RecurringJournalTemplate.company_id == company_id, RecurringJournalTemplate.active.is_(True), RecurringJournalTemplate.next_run_date <= end, (RecurringJournalTemplate.end_date.is_(None) | (RecurringJournalTemplate.next_run_date <= RecurringJournalTemplate.end_date)))) or 0
    overdue_ncr = db.scalar(select(func.count(NonConformance.id)).where(NonConformance.company_id == company_id, NonConformance.status.not_in(["CLOSED"]), NonConformance.due_date.is_not(None), NonConformance.due_date <= end)) or 0
    stock_rows = db.execute(select(StockMovement.item_id, StockMovement.warehouse_id, func.coalesce(func.sum(StockMovement.quantity), 0)).where(StockMovement.company_id == company_id, StockMovement.movement_date <= end).group_by(StockMovement.item_id, StockMovement.warehouse_id)).all()
    negative_stock = sum(1 for _, _, qty in stock_rows if Decimal(qty) < 0)
    debit, credit = db.execute(select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0)).join(JournalEntry, JournalEntry.id == JournalLine.journal_id).where(JournalEntry.company_id == company_id, JournalEntry.entry_date <= end, JournalEntry.status.in_(["POSTED", "REVERSED"]))).one()
    tb_diff = Decimal(debit) - Decimal(credit)
    return [
        {"code": "UNPOSTED_JOURNALS", "ar": "لا توجد قيود غير مرحلة", "en": "No unposted journals", "status": "PASS" if unposted == 0 else "FAIL", "blocking": True, "details": {"count": unposted}},
        {"code": "BANK_RECONCILIATION", "ar": "كشوف البنك مسواة", "en": "Bank statements reconciled", "status": "PASS" if unreconciled == 0 else "FAIL", "blocking": True, "details": {"count": unreconciled}},
        {"code": "POS_SETTLEMENTS", "ar": "تسويات نقاط البيع مكتملة", "en": "POS settlements completed", "status": "PASS" if pending_pos == 0 else "FAIL", "blocking": True, "details": {"count": pending_pos}},
        {"code": "PAYROLL_STATUS", "ar": "مسير الرواتب مكتمل", "en": "Payroll cycle completed", "status": "PASS" if incomplete_payroll == 0 else "FAIL", "blocking": True, "details": {"count": incomplete_payroll}},
        {"code": "NEGATIVE_INVENTORY", "ar": "لا يوجد مخزون سالب", "en": "No negative inventory", "status": "PASS" if negative_stock == 0 else "FAIL", "blocking": True, "details": {"count": negative_stock}},
        {"code": "REVENUE_RECOGNITION", "ar": "جداول الإيراد مستكملة", "en": "Revenue schedules posted", "status": "PASS" if due_revenue == 0 else "FAIL", "blocking": True, "details": {"count": due_revenue}},
        {"code": "LEASE_SCHEDULES", "ar": "جداول الإيجار مستكملة", "en": "Lease schedules posted", "status": "PASS" if due_leases == 0 else "FAIL", "blocking": True, "details": {"count": due_leases}},
        {"code": "PREPAID_AMORTIZATION", "ar": "إطفاء المصروفات المقدمة مستكمل", "en": "Prepaid amortization posted", "status": "PASS" if due_prepaids == 0 else "FAIL", "blocking": True, "details": {"count": due_prepaids}},
        {"code": "ACCRUALS_POSTED", "ar": "قيود الاستحقاق مستكملة", "en": "Accrual journals posted", "status": "PASS" if draft_accruals == 0 else "FAIL", "blocking": True, "details": {"count": draft_accruals}},
        {"code": "ACCRUAL_REVERSALS", "ar": "عكوس الاستحقاق المستحقة مستكملة", "en": "Due accrual reversals posted", "status": "PASS" if due_reversals == 0 else "FAIL", "blocking": True, "details": {"count": due_reversals}},
        {"code": "RECURRING_JOURNALS", "ar": "القيود المتكررة المستحقة مستكملة", "en": "Due recurring journals posted", "status": "PASS" if due_recurring == 0 else "FAIL", "blocking": True, "details": {"count": due_recurring}},
        {"code": "TRIAL_BALANCE", "ar": "ميزان المراجعة متوازن", "en": "Trial balance balanced", "status": "PASS" if tb_diff == 0 else "FAIL", "blocking": True, "details": {"difference": str(tb_diff)}},
        {"code": "QUALITY_NCR", "ar": "ملاحظات الجودة المتأخرة", "en": "Overdue quality NCRs", "status": "PASS" if overdue_ncr == 0 else "WARNING", "blocking": False, "details": {"count": overdue_ncr}},
    ]


def _serialize(run: PeriodCloseRun, checks: list[PeriodCloseCheck]) -> dict:
    return {
        "id": run.id, "company_id": run.company_id, "fiscal_period_id": run.fiscal_period_id,
        "status": run.status, "requested_by": run.requested_by, "approved_by": run.approved_by,
        "created_at": run.created_at, "closed_at": run.closed_at,
        "checks": [{"code": c.code, "name_ar": c.name_ar, "name_en": c.name_en, "status": c.status, "blocking": c.blocking, "details": json.loads(c.details or "{}") } for c in checks],
    }


@router.post("/review", status_code=201)
def review_close(data: CloseRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "period.close")
    period = _period_company(db, data.fiscal_period_id, data.company_id)
    if period.status == "CLOSED":
        raise HTTPException(409, "Period is already closed")
    run = db.scalar(select(PeriodCloseRun).where(PeriodCloseRun.company_id == data.company_id, PeriodCloseRun.fiscal_period_id == data.fiscal_period_id))
    if not run:
        run = PeriodCloseRun(company_id=data.company_id, fiscal_period_id=data.fiscal_period_id, status="REVIEWED", requested_by=user.id)
        db.add(run); db.flush()
    else:
        db.query(PeriodCloseCheck).filter(PeriodCloseCheck.close_run_id == run.id).delete()
        run.status = "REVIEWED"; run.requested_by = user.id; run.approved_by = None; run.closed_at = None
    generated = _checks(db, data.company_id, period)
    for item in generated:
        db.add(PeriodCloseCheck(close_run_id=run.id, code=item["code"], name_ar=item["ar"], name_en=item["en"], status=item["status"], blocking=item["blocking"], details=json.dumps(item["details"], default=str)))
    db.flush()
    checks = db.scalars(select(PeriodCloseCheck).where(PeriodCloseCheck.close_run_id == run.id).order_by(PeriodCloseCheck.id)).all()
    write_audit(db, action="PERIOD_CLOSE_REVIEWED", entity_type="PERIOD_CLOSE", entity_id=run.id, user_id=user.id, company_id=data.company_id, after={"period": period.number, "failed": [c.code for c in checks if c.status == "FAIL"]})
    db.commit()
    return _serialize(run, checks)


@router.post("/{run_id}/close")
def close_period(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(PeriodCloseRun, run_id)
    if not run:
        raise HTTPException(404, "Close run not found")
    ensure_permission(db, user, run.company_id, "period.close")
    if run.requested_by == user.id:
        raise HTTPException(409, "Maker-checker control: requester cannot approve period close")
    period = _period_company(db, run.fiscal_period_id, run.company_id)
    current = _checks(db, run.company_id, period)
    failures = [item["code"] for item in current if item["blocking"] and item["status"] == "FAIL"]
    if failures:
        raise HTTPException(409, {"message": "Blocking close checks failed", "checks": failures})
    db.query(PeriodCloseCheck).filter(PeriodCloseCheck.close_run_id == run.id).delete()
    for item in current:
        db.add(PeriodCloseCheck(close_run_id=run.id, code=item["code"], name_ar=item["ar"], name_en=item["en"], status=item["status"], blocking=item["blocking"], details=json.dumps(item["details"], default=str)))
    period.status = "CLOSED"; run.status = "CLOSED"; run.approved_by = user.id; run.closed_at = utc_now()
    write_audit(db, action="FISCAL_PERIOD_CLOSED", entity_type="FISCAL_PERIOD", entity_id=period.id, user_id=user.id, company_id=run.company_id, after={"period": period.number, "close_run": run.id})
    db.commit()
    return {"run_id": run.id, "period_id": period.id, "status": "CLOSED", "closed_at": run.closed_at}


@router.post("/periods/{period_id}/reopen")
def reopen_period(period_id: int, company_id: int, data: ReopenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "period.close")
    period = _period_company(db, period_id, company_id)
    if period.status != "CLOSED":
        raise HTTPException(409, "Only closed periods can be reopened")
    period.status = "OPEN"
    run = db.scalar(select(PeriodCloseRun).where(PeriodCloseRun.company_id == company_id, PeriodCloseRun.fiscal_period_id == period.id))
    if run:
        run.status = "REOPENED"
    write_audit(db, action="FISCAL_PERIOD_REOPENED", entity_type="FISCAL_PERIOD", entity_id=period.id, user_id=user.id, company_id=company_id, after={"reason": data.reason})
    db.commit()
    return {"period_id": period.id, "status": period.status, "reason": data.reason}


@router.get("/runs")
def list_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    runs = db.scalars(select(PeriodCloseRun).where(PeriodCloseRun.company_id == company_id).order_by(PeriodCloseRun.created_at.desc())).all()
    result = []
    for run in runs:
        checks = db.scalars(select(PeriodCloseCheck).where(PeriodCloseCheck.close_run_id == run.id).order_by(PeriodCloseCheck.id)).all()
        result.append(_serialize(run, checks))
    return result
