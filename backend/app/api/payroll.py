from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (
    BankAccount, Employee, OvertimeRequest, PayrollAdjustment, PayrollLine, PayrollPolicy,
    PayrollRun, User, WpsBatch,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.payroll import approved_policy, employee_period_inputs, payroll_analysis_hash
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/payroll", tags=["HR and payroll"])


class EmployeeIn(BaseModel):
    company_id: int
    employee_number: str
    name_ar: str
    name_en: str
    nationality_group: str = "SAUDI"
    national_id: str | None = None
    birth_date: date | None = None
    salary_bank_code: str | None = None
    hire_date: date
    basic_salary: Decimal = Field(gt=0)
    housing_allowance: Decimal = Field(default=0, ge=0)
    other_allowance: Decimal = Field(default=0, ge=0)
    employee_gosi_rate: Decimal = Field(default=0, ge=0, le=100)
    employer_gosi_rate: Decimal = Field(default=0, ge=0, le=100)
    iban: str | None = None
    branch_id: int | None = None
    cost_center_id: int | None = None


class PayrollRunIn(BaseModel):
    company_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    payment_date: date
    bank_account_id: int


class PayrollAdjustmentIn(BaseModel):
    employee_id: int
    other_deductions: Decimal = Field(default=0, ge=0)


class PayrollCreateWithAdjustments(PayrollRunIn):
    adjustments: list[PayrollAdjustmentIn] = []


class PayrollReviewIn(BaseModel):
    override_reason: str | None = Field(default=None, min_length=10, max_length=500)


@router.post("/employees", status_code=201)
def create_employee(data: EmployeeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "payroll.manage")
    if db.scalar(select(Employee).where(Employee.company_id == data.company_id, Employee.employee_number == data.employee_number)):
        raise HTTPException(409, "Employee number already exists")
    row = Employee(**data.model_dump(), active=True)
    db.add(row); db.flush()
    write_audit(db, action="EMPLOYEE_CREATED", entity_type="EMPLOYEE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"employee_number": row.employee_number})
    db.commit()
    return {"id": row.id, "employee_number": row.employee_number, "name_ar": row.name_ar, "name_en": row.name_en}


@router.get("/employees")
def list_employees(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, Employee)
    query = select(Employee).where(Employee.company_id == company_id, Employee.active.is_(True))
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.order_by(Employee.employee_number)).all()
    return [{"id": r.id, "employee_number": r.employee_number, "name_ar": r.name_ar, "name_en": r.name_en,
             "nationality_group": r.nationality_group, "hire_date": r.hire_date, "birth_date": r.birth_date,
             "salary_bank_code": r.salary_bank_code, "has_iban": bool(r.iban), "basic_salary": r.basic_salary,
             "housing_allowance": r.housing_allowance, "other_allowance": r.other_allowance,
             "employee_gosi_rate": r.employee_gosi_rate, "employer_gosi_rate": r.employer_gosi_rate} for r in rows]


def _legacy_policy(company_id: int, user_id: int) -> PayrollPolicy:
    return PayrollPolicy(company_id=company_id, salary_day_basis=30, standard_daily_hours=8, gosi_basis="BASIC",
                         late_deduction_enabled=True, absence_deduction_enabled=True, overtime_basis="BASIC",
                         attendance_completeness_threshold=0, require_three_user_approval=False,
                         active=True, created_by=user_id, approved_by=user_id)


@router.post("/runs", status_code=201)
def create_payroll_run(data: PayrollCreateWithAdjustments, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "payroll.manage")
    if db.scalar(select(PayrollRun).where(PayrollRun.company_id == data.company_id, PayrollRun.period_year == data.period_year, PayrollRun.period_month == data.period_month)):
        raise HTTPException(409, "Payroll run already exists for this period")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not bank: raise HTTPException(404, "Bank account not found")
    employees = db.scalars(select(Employee).where(Employee.company_id == data.company_id, Employee.active.is_(True))).all()
    if not employees: raise HTTPException(422, "No active employees")
    policy = approved_policy(db, data.company_id)
    if settings.payroll_strict_workflow and not policy:
        raise HTTPException(422, "An approved payroll policy is required")
    policy = policy or _legacy_policy(data.company_id, user.id)
    manual_adjustments = {row.employee_id: money(row.other_deductions) for row in data.adjustments}
    run = PayrollRun(company_id=data.company_id, period_year=data.period_year, period_month=data.period_month,
                     payment_date=data.payment_date, status="CALCULATED", bank_account_id=bank.id, created_by=user.id)
    totals = {"gross": Decimal("0"), "employee_gosi": Decimal("0"), "employer_gosi": Decimal("0"), "deductions": Decimal("0"), "net": Decimal("0")}
    completeness_values: list[Decimal] = []
    consumed_overtime: list[OvertimeRequest] = []
    consumed_adjustments: list[PayrollAdjustment] = []
    for employee in employees:
        inputs = employee_period_inputs(db, employee, data.period_year, data.period_month, policy)
        line = inputs["line"]
        if manual_adjustments.get(employee.id):
            extra = manual_adjustments[employee.id]
            line.other_deductions = money(Decimal(line.other_deductions) + extra)
            line.deduction_adjustments = money(Decimal(line.deduction_adjustments or 0) + extra)
            line.net_salary = money(Decimal(line.net_salary) - extra)
            if Decimal(line.net_salary) < 0: raise HTTPException(422, f"Negative net salary for employee {employee.employee_number}")
        run.lines.append(line)
        completeness_values.append(inputs["completeness"])
        consumed_overtime.extend(inputs["overtime_rows"])
        consumed_adjustments.extend(inputs["adjustment_rows"])
        totals["gross"] += Decimal(line.gross_salary); totals["employee_gosi"] += Decimal(line.employee_gosi)
        totals["employer_gosi"] += Decimal(line.employer_gosi); totals["deductions"] += Decimal(line.other_deductions)
        totals["net"] += Decimal(line.net_salary)
    run.total_gross = money(totals["gross"]); run.total_employee_gosi = money(totals["employee_gosi"])
    run.total_employer_gosi = money(totals["employer_gosi"]); run.total_deductions = money(totals["deductions"]); run.total_net = money(totals["net"])
    run.attendance_completeness_percent = money(sum(completeness_values, Decimal("0")) / Decimal(len(completeness_values)))
    run.analysis_hash = payroll_analysis_hash(run)
    db.add(run); db.flush()
    for row in consumed_overtime: row.payroll_run_id = run.id
    for row in consumed_adjustments: row.applied_payroll_run_id = run.id
    write_audit(db, action="PAYROLL_RUN_CALCULATED", entity_type="PAYROLL_RUN", entity_id=run.id, user_id=user.id, company_id=data.company_id,
                after={"period": f"{data.period_year}-{data.period_month:02d}", "employees": len(run.lines), "net": str(run.total_net),
                       "attendance_completeness": str(run.attendance_completeness_percent), "analysis_hash": run.analysis_hash})
    db.commit()
    return serialize_run(run, include_lines=True)


@router.post("/runs/{run_id}/review")
def review_payroll_run(run_id: int, data: PayrollReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(PayrollRun).where(PayrollRun.id == run_id).options(selectinload(PayrollRun.lines)))
    if not run: raise HTTPException(404, "Payroll run not found")
    ensure_permission(db, user, run.company_id, "payroll.review")
    if run.status != "CALCULATED": raise HTTPException(409, "Payroll run must be CALCULATED")
    if run.created_by == user.id: raise HTTPException(409, "Preparer cannot review own payroll run")
    if payroll_analysis_hash(run) != run.analysis_hash: raise HTTPException(409, "Payroll analysis integrity mismatch")
    policy = approved_policy(db, run.company_id)
    threshold = Decimal(policy.attendance_completeness_threshold) if policy else Decimal("0")
    if Decimal(run.attendance_completeness_percent) < threshold and not data.override_reason:
        raise HTTPException(422, f"Attendance completeness {run.attendance_completeness_percent}% is below policy threshold {threshold}%")
    run.status = "REVIEWED"; run.reviewed_by = user.id; run.reviewed_at = utc_now(); run.review_override_reason = data.override_reason
    write_audit(db, action="PAYROLL_RUN_REVIEWED", entity_type="PAYROLL_RUN", entity_id=run.id, user_id=user.id, company_id=run.company_id,
                after={"attendance_completeness": str(run.attendance_completeness_percent), "override_reason": data.override_reason})
    db.commit(); return serialize_run(run)


def _post_accrual(run: PayrollRun, user: User, db: Session):
    salary_expense = get_account(db, run.company_id, "611010")
    employer_gosi_expense = get_account(db, run.company_id, "618010")
    payroll_payable = get_account(db, run.company_id, "215010")
    gosi_payable = get_account(db, run.company_id, "215020")
    deductions_payable = get_account(db, run.company_id, "215030")
    lines = [
        {"account_id": salary_expense.id, "debit": run.total_gross, "credit": 0},
        {"account_id": employer_gosi_expense.id, "debit": run.total_employer_gosi, "credit": 0},
        {"account_id": payroll_payable.id, "debit": 0, "credit": run.total_net},
        {"account_id": gosi_payable.id, "debit": 0, "credit": money(run.total_employee_gosi + run.total_employer_gosi)},
    ]
    if run.total_deductions > 0: lines.append({"account_id": deductions_payable.id, "debit": 0, "credit": run.total_deductions})
    return create_posted_journal(db, company_id=run.company_id, user_id=user.id, posting_date=run.payment_date,
                                 reference=f"PAY-{run.period_year}-{run.period_month:02d}", description=f"Payroll accrual {run.period_year}-{run.period_month:02d}", lines=lines)


@router.post("/runs/{run_id}/approve")
def approve_payroll_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(PayrollRun).where(PayrollRun.id == run_id).options(selectinload(PayrollRun.lines)))
    if not run: raise HTTPException(404, "Payroll run not found")
    ensure_permission(db, user, run.company_id, "payroll.approve")
    if run.status != "REVIEWED": raise HTTPException(409, "Payroll run must be REVIEWED")
    if user.id in {run.created_by, run.reviewed_by}: raise HTTPException(409, "Approver must be independent")
    if payroll_analysis_hash(run) != run.analysis_hash: raise HTTPException(409, "Payroll analysis integrity mismatch")
    journal = _post_accrual(run, user, db)
    run.status = "APPROVED_POSTED"; run.journal_id = journal.id; run.posted_by = user.id; run.posted_at = utc_now(); run.approved_by = user.id; run.approved_at = utc_now()
    write_audit(db, action="PAYROLL_RUN_APPROVED_POSTED", entity_type="PAYROLL_RUN", entity_id=run.id, user_id=user.id, company_id=run.company_id, after={"journal": journal.number, "net": str(run.total_net)})
    db.commit(); return {**serialize_run(run), "journal": journal.number}


@router.post("/runs/{run_id}/post")
def post_payroll_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compatibility endpoint. Production must use review -> approve."""
    run = db.scalar(select(PayrollRun).where(PayrollRun.id == run_id).options(selectinload(PayrollRun.lines)))
    if not run: raise HTTPException(404, "Payroll run not found")
    if settings.payroll_strict_workflow:
        raise HTTPException(409, "Direct payroll posting is disabled; use review and approve workflow")
    ensure_permission(db, user, run.company_id, "payroll.post")
    if run.status != "CALCULATED": raise HTTPException(409, "Payroll run must be CALCULATED")
    journal = _post_accrual(run, user, db)
    run.status = "POSTED"; run.journal_id = journal.id; run.posted_by = user.id; run.posted_at = utc_now()
    write_audit(db, action="PAYROLL_RUN_POSTED_LEGACY", entity_type="PAYROLL_RUN", entity_id=run.id, user_id=user.id, company_id=run.company_id, after={"journal": journal.number, "net": str(run.total_net)})
    db.commit(); return {**serialize_run(run), "journal": journal.number}


@router.post("/runs/{run_id}/pay")
def pay_payroll_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(PayrollRun).where(PayrollRun.id == run_id))
    if not run: raise HTTPException(404, "Payroll run not found")
    ensure_permission(db, user, run.company_id, "payroll.pay")
    if run.status not in {"POSTED", "APPROVED_POSTED"}: raise HTTPException(409, "Payroll run must be posted")
    if settings.payroll_strict_workflow:
        batch = db.scalar(select(WpsBatch).where(WpsBatch.payroll_run_id == run.id))
        if not batch or batch.status != "ACCEPTED": raise HTTPException(409, "Accepted WPS batch is required before payroll payment")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == run.bank_account_id, BankAccount.company_id == run.company_id))
    payroll_payable = get_account(db, run.company_id, "215010")
    journal = create_posted_journal(db, company_id=run.company_id, user_id=user.id, posting_date=run.payment_date,
                                    reference=f"WPS-{run.period_year}-{run.period_month:02d}", description=f"Payroll payment {run.period_year}-{run.period_month:02d}",
                                    lines=[{"account_id": payroll_payable.id, "debit": run.total_net, "credit": 0}, {"account_id": bank.gl_account_id, "debit": 0, "credit": run.total_net}],
                                    cash_flow_activity="OPERATING", cash_flow_kind="PAYROLL_PAYMENTS")
    run.status = "PAID"; run.payment_journal_id = journal.id
    write_audit(db, action="PAYROLL_RUN_PAID", entity_type="PAYROLL_RUN", entity_id=run.id, user_id=user.id, company_id=run.company_id, after={"journal": journal.number, "amount": str(run.total_net)})
    db.commit(); return {**serialize_run(run), "payment_journal": journal.number}


@router.get("/runs")
def list_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    rows = db.scalars(select(PayrollRun).where(PayrollRun.company_id == company_id).options(selectinload(PayrollRun.lines).selectinload(PayrollLine.employee)).order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())).all()
    return [serialize_run(r, include_lines=True) for r in rows]


@router.get("/summary")
def payroll_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    employees = db.scalars(select(Employee).where(Employee.company_id == company_id, Employee.active.is_(True))).all()
    latest = db.scalar(select(PayrollRun).where(PayrollRun.company_id == company_id).order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc()))
    return {"active_employees": len(employees), "latest_period": f"{latest.period_year}-{latest.period_month:02d}" if latest else None,
            "latest_status": latest.status if latest else None, "gross": latest.total_gross if latest else 0, "net": latest.total_net if latest else 0,
            "employee_gosi": latest.total_employee_gosi if latest else 0, "employer_gosi": latest.total_employer_gosi if latest else 0,
            "attendance_completeness_percent": latest.attendance_completeness_percent if latest else 0,
            "strict_workflow": settings.payroll_strict_workflow}


def serialize_run(run: PayrollRun, include_lines: bool = False) -> dict:
    data = {"id": run.id, "company_id": run.company_id, "period_year": run.period_year, "period_month": run.period_month,
            "payment_date": run.payment_date, "status": run.status, "employees": len(run.lines), "total_gross": run.total_gross,
            "total_employee_gosi": run.total_employee_gosi, "total_employer_gosi": run.total_employer_gosi,
            "total_deductions": run.total_deductions, "total_net": run.total_net,
            "attendance_completeness_percent": run.attendance_completeness_percent, "analysis_hash": run.analysis_hash}
    if include_lines:
        data["lines"] = [{"employee_id": l.employee_id, "employee_number": l.employee.employee_number,
                          "employee_name_ar": l.employee.name_ar, "employee_name_en": l.employee.name_en,
                          "gross_salary": l.gross_salary, "employee_gosi": l.employee_gosi, "employer_gosi": l.employer_gosi,
                          "other_deductions": l.other_deductions, "net_salary": l.net_salary, "working_days": l.working_days,
                          "paid_days": l.paid_days, "absent_days": l.absent_days, "unpaid_leave_days": l.unpaid_leave_days,
                          "late_minutes": l.late_minutes, "overtime_minutes": l.overtime_minutes,
                          "overtime_amount": l.overtime_amount or 0, "absence_deduction": l.absence_deduction or 0,
                          "unpaid_leave_deduction": l.unpaid_leave_deduction or 0,
                          "earning_adjustments": l.earning_adjustments or 0, "deduction_adjustments": l.deduction_adjustments or 0}
                         for l in run.lines]
    return data
