from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    BankAccount, Employee, EmployeeBenefitAssumption, EmployeeBenefitValuation,
    EmployeeBenefitValuationLine, EmployeeContract, OvertimeRequest, PayrollAdjustment,
    PayrollPolicy, PayrollRun, User, WpsBatch, WpsBatchLine,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.payroll import payroll_analysis_hash
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/hr-payroll", tags=["Advanced HR and payroll"])


class PayrollPolicyIn(BaseModel):
    company_id: int
    salary_day_basis: Decimal = Field(default=30, gt=0)
    standard_daily_hours: Decimal = Field(default=8, gt=0, le=24)
    gosi_basis: str = "BASIC_HOUSING"
    late_deduction_enabled: bool = True
    absence_deduction_enabled: bool = True
    overtime_basis: str = "BASIC"
    attendance_completeness_threshold: Decimal = Field(default=95, ge=0, le=100)
    require_three_user_approval: bool = True


class ContractIn(BaseModel):
    company_id: int
    employee_id: int
    contract_number: str
    contract_type: str = "UNLIMITED"
    start_date: date
    end_date: date | None = None
    probation_end_date: date | None = None
    basic_salary: Decimal = Field(gt=0)
    housing_allowance: Decimal = Field(default=0, ge=0)
    other_allowance: Decimal = Field(default=0, ge=0)
    working_hours_per_week: Decimal = Field(default=48, gt=0, le=72)
    notice_days: int = Field(default=60, ge=0, le=365)

    @model_validator(mode="after")
    def dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("Contract end date cannot precede start date")
        if self.probation_end_date and self.probation_end_date < self.start_date:
            raise ValueError("Probation end date cannot precede start date")
        return self


class OvertimeIn(BaseModel):
    company_id: int
    employee_id: int
    work_date: date
    requested_minutes: int = Field(gt=0, le=1440)
    rate_multiplier: Decimal = Field(default=Decimal("1.5"), ge=1, le=3)
    reason: str = Field(min_length=5, max_length=500)


class OvertimeApproveIn(BaseModel):
    approved_minutes: int = Field(ge=0, le=1440)


class AdjustmentIn(BaseModel):
    company_id: int
    employee_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    adjustment_type: str
    amount: Decimal = Field(gt=0)
    earning: bool = False
    gosi_applicable: bool = False
    reason: str = Field(min_length=5, max_length=500)


class WpsResponseLine(BaseModel):
    employee_id: int
    status: str
    rejection_code: str | None = None
    rejection_reason: str | None = None


class WpsResponseIn(BaseModel):
    status: str
    response_reference: str | None = None
    response_message: str | None = None
    lines: list[WpsResponseLine] = []


class BenefitAssumptionIn(BaseModel):
    company_id: int
    valuation_date: date
    discount_rate: Decimal = Field(gt=0, le=1)
    salary_growth_rate: Decimal = Field(ge=0, le=1)
    annual_turnover_rate: Decimal = Field(ge=0, le=1)
    retirement_age: int = Field(default=60, ge=45, le=75)
    mortality_survival_factor: Decimal = Field(default=Decimal("0.995"), gt=0, le=1)


class BenefitValuationIn(BaseModel):
    company_id: int
    assumption_id: int
    valuation_date: date


def _employee(db: Session, company_id: int, employee_id: int) -> Employee:
    row = db.scalar(select(Employee).where(Employee.id == employee_id, Employee.company_id == company_id))
    if not row:
        raise HTTPException(404, "Employee not found")
    return row


def _number(prefix: str, company_id: int) -> str:
    return f"{prefix}-{company_id}-{utc_now():%Y%m%d%H%M%S%f}"


@router.post("/policies", status_code=201)
def upsert_policy(data: PayrollPolicyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "payroll.manage")
    row = db.scalar(select(PayrollPolicy).where(PayrollPolicy.company_id == data.company_id))
    before = None
    if row:
        before = {"threshold": str(row.attendance_completeness_threshold), "gosi_basis": row.gosi_basis}
        for key, value in data.model_dump(exclude={"company_id"}).items():
            setattr(row, key, value)
        row.approved_by = None; row.approved_at = None; row.created_by = user.id
    else:
        row = PayrollPolicy(**data.model_dump(), created_by=user.id, active=True)
        db.add(row)
    db.flush()
    write_audit(db, action="PAYROLL_POLICY_PREPARED", entity_type="PAYROLL_POLICY", entity_id=row.id, user_id=user.id, company_id=data.company_id, before=before, after=data.model_dump(mode="json"))
    db.commit()
    return {"id": row.id, "company_id": row.company_id, "approved": bool(row.approved_by), "attendance_completeness_threshold": row.attendance_completeness_threshold}


@router.post("/policies/{policy_id}/approve")
def approve_policy(policy_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(PayrollPolicy, policy_id)
    if not row: raise HTTPException(404, "Payroll policy not found")
    ensure_permission(db, user, row.company_id, "payroll.approve")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker control: policy preparer cannot approve")
    row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="PAYROLL_POLICY_APPROVED", entity_type="PAYROLL_POLICY", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit()
    return {"id": row.id, "approved": True}


@router.get("/policies")
def list_policies(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    row = db.scalar(select(PayrollPolicy).where(PayrollPolicy.company_id == company_id))
    if not row: return []
    return [{"id": row.id, "salary_day_basis": row.salary_day_basis, "standard_daily_hours": row.standard_daily_hours,
             "gosi_basis": row.gosi_basis, "attendance_completeness_threshold": row.attendance_completeness_threshold,
             "require_three_user_approval": row.require_three_user_approval, "approved": bool(row.approved_by)}]


@router.post("/contracts", status_code=201)
def create_contract(data: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "hr.contracts.manage")
    employee = _employee(db, data.company_id, data.employee_id)
    if db.scalar(select(EmployeeContract.id).where(EmployeeContract.company_id == data.company_id, EmployeeContract.contract_number == data.contract_number)):
        raise HTTPException(409, "Contract number already exists")
    row = EmployeeContract(**data.model_dump(), status="DRAFT", created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="EMPLOYEE_CONTRACT_CREATED", entity_type="EMPLOYEE_CONTRACT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"employee": employee.employee_number, "contract_number": row.contract_number})
    db.commit()
    return {"id": row.id, "contract_number": row.contract_number, "status": row.status}


@router.post("/contracts/{contract_id}/approve")
def approve_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(EmployeeContract, contract_id)
    if not row: raise HTTPException(404, "Contract not found")
    ensure_permission(db, user, row.company_id, "payroll.approve")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker control: contract preparer cannot approve")
    if row.status != "DRAFT": raise HTTPException(409, "Contract must be DRAFT")
    employee = db.get(Employee, row.employee_id)
    row.status = "ACTIVE"; row.approved_by = user.id; row.approved_at = utc_now()
    employee.contract_type = row.contract_type; employee.contract_end_date = row.end_date; employee.probation_end_date = row.probation_end_date
    employee.basic_salary = row.basic_salary; employee.housing_allowance = row.housing_allowance; employee.other_allowance = row.other_allowance
    write_audit(db, action="EMPLOYEE_CONTRACT_APPROVED", entity_type="EMPLOYEE_CONTRACT", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/contracts")
def list_contracts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    rows = db.scalars(select(EmployeeContract).where(EmployeeContract.company_id == company_id).order_by(EmployeeContract.start_date.desc())).all()
    return [{"id": r.id, "contract_number": r.contract_number, "employee_id": r.employee_id, "employee_number": r.employee.employee_number,
             "employee_name_ar": r.employee.name_ar, "employee_name_en": r.employee.name_en, "contract_type": r.contract_type,
             "start_date": r.start_date, "end_date": r.end_date, "status": r.status} for r in rows]


@router.post("/overtime", status_code=201)
def submit_overtime(data: OvertimeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "hr.overtime.manage")
    _employee(db, data.company_id, data.employee_id)
    row = OvertimeRequest(**data.model_dump(), number=_number("OT", data.company_id), approved_minutes=0, status="SUBMITTED", created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="OVERTIME_SUBMITTED", entity_type="OVERTIME", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"minutes": row.requested_minutes})
    db.commit()
    return {"id": row.id, "number": row.number, "status": row.status}


@router.post("/overtime/{overtime_id}/approve")
def approve_overtime(overtime_id: int, data: OvertimeApproveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(OvertimeRequest, overtime_id)
    if not row: raise HTTPException(404, "Overtime request not found")
    ensure_permission(db, user, row.company_id, "hr.overtime.approve")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker control: requester cannot approve overtime")
    if row.status != "SUBMITTED": raise HTTPException(409, "Overtime request must be SUBMITTED")
    if data.approved_minutes > row.requested_minutes: raise HTTPException(422, "Approved minutes cannot exceed requested minutes")
    row.approved_minutes = data.approved_minutes; row.status = "APPROVED" if data.approved_minutes else "REJECTED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="OVERTIME_DECIDED", entity_type="OVERTIME", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status, "approved_minutes": row.approved_minutes})
    db.commit()
    return {"id": row.id, "status": row.status, "approved_minutes": row.approved_minutes}


@router.get("/overtime")
def list_overtime(company_id: int, period_year: int | None = None, period_month: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    query = select(OvertimeRequest).where(OvertimeRequest.company_id == company_id)
    if period_year and period_month:
        query = query.where(func.extract("year", OvertimeRequest.work_date) == period_year, func.extract("month", OvertimeRequest.work_date) == period_month)
    rows = db.scalars(query.order_by(OvertimeRequest.work_date.desc())).all()
    return [{"id": r.id, "number": r.number, "employee_id": r.employee_id, "employee": r.employee.name_en, "work_date": r.work_date,
             "requested_minutes": r.requested_minutes, "approved_minutes": r.approved_minutes, "rate_multiplier": r.rate_multiplier, "status": r.status} for r in rows]


@router.post("/adjustments", status_code=201)
def create_adjustment(data: AdjustmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "payroll.adjustments.manage")
    _employee(db, data.company_id, data.employee_id)
    row = PayrollAdjustment(**data.model_dump(), number=_number("PADJ", data.company_id), status="SUBMITTED", created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="PAYROLL_ADJUSTMENT_SUBMITTED", entity_type="PAYROLL_ADJUSTMENT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"type": row.adjustment_type, "earning": row.earning, "amount": str(row.amount)})
    db.commit()
    return {"id": row.id, "number": row.number, "status": row.status}


@router.post("/adjustments/{adjustment_id}/review")
def review_adjustment(adjustment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(PayrollAdjustment, adjustment_id)
    if not row: raise HTTPException(404, "Adjustment not found")
    ensure_permission(db, user, row.company_id, "payroll.adjustments.review")
    if row.created_by == user.id: raise HTTPException(409, "Preparer cannot review own adjustment")
    if row.status != "SUBMITTED": raise HTTPException(409, "Adjustment must be SUBMITTED")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now()
    write_audit(db, action="PAYROLL_ADJUSTMENT_REVIEWED", entity_type="PAYROLL_ADJUSTMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/adjustments/{adjustment_id}/approve")
def approve_adjustment(adjustment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(PayrollAdjustment, adjustment_id)
    if not row: raise HTTPException(404, "Adjustment not found")
    ensure_permission(db, user, row.company_id, "payroll.adjustments.approve")
    if row.status != "REVIEWED": raise HTTPException(409, "Adjustment must be REVIEWED")
    if user.id in {row.created_by, row.reviewed_by}: raise HTTPException(409, "Approver must be independent")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="PAYROLL_ADJUSTMENT_APPROVED", entity_type="PAYROLL_ADJUSTMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return {"id": row.id, "status": row.status}


@router.get("/adjustments")
def list_adjustments(company_id: int, period_year: int | None = None, period_month: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    query = select(PayrollAdjustment).where(PayrollAdjustment.company_id == company_id)
    if period_year: query = query.where(PayrollAdjustment.period_year == period_year)
    if period_month: query = query.where(PayrollAdjustment.period_month == period_month)
    rows = db.scalars(query.order_by(PayrollAdjustment.created_at.desc())).all()
    return [{"id": r.id, "number": r.number, "employee_id": r.employee_id, "employee": r.employee.name_en, "period": f"{r.period_year}-{r.period_month:02d}",
             "adjustment_type": r.adjustment_type, "amount": r.amount, "earning": r.earning, "status": r.status} for r in rows]


def _wps_content(batch: WpsBatch) -> str:
    header = f"CORVAX-WPS|{batch.batch_number}|{batch.execution_date}|{batch.line_count}|{money(batch.total_amount)}"
    lines = [header]
    for line in sorted(batch.lines, key=lambda r: r.employee_id):
        lines.append(f"{line.employee.employee_number}|{line.employee_iban}|{line.bank_code}|{money(line.amount)}")
    return "\n".join(lines) + "\n"


@router.post("/wps/{run_id}/generate", status_code=201)
def generate_wps(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(PayrollRun).where(PayrollRun.id == run_id).options(selectinload(PayrollRun.lines)))
    if not run: raise HTTPException(404, "Payroll run not found")
    ensure_permission(db, user, run.company_id, "payroll.wps")
    if run.status not in {"APPROVED_POSTED", "POSTED"}: raise HTTPException(409, "Payroll run must be approved and posted")
    if db.scalar(select(WpsBatch.id).where(WpsBatch.payroll_run_id == run.id)): raise HTTPException(409, "WPS batch already exists")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == run.bank_account_id, BankAccount.company_id == run.company_id))
    if not bank: raise HTTPException(404, "Payroll bank account not found")
    batch = WpsBatch(company_id=run.company_id, payroll_run_id=run.id, batch_number=_number("WPS", run.company_id), bank_account_id=bank.id,
                     execution_date=run.payment_date, status="GENERATED", total_amount=run.total_net, line_count=len(run.lines), file_hash="PENDING", generated_by=user.id)
    for line in run.lines:
        employee = db.get(Employee, line.employee_id)
        if not employee or not employee.iban or not employee.salary_bank_code:
            raise HTTPException(422, f"Employee {employee.employee_number if employee else line.employee_id} is missing IBAN or bank code")
        batch.lines.append(WpsBatchLine(employee_id=employee.id, employee_iban=employee.iban, bank_code=employee.salary_bank_code, amount=line.net_salary, status="PENDING"))
    db.add(batch); db.flush()
    content = _wps_content(batch)
    batch.file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    write_audit(db, action="WPS_BATCH_GENERATED", entity_type="WPS_BATCH", entity_id=batch.id, user_id=user.id, company_id=run.company_id, after={"line_count": batch.line_count, "amount": str(batch.total_amount), "file_hash": batch.file_hash})
    db.commit()
    return {"id": batch.id, "batch_number": batch.batch_number, "status": batch.status, "total_amount": batch.total_amount, "line_count": batch.line_count, "file_hash": batch.file_hash}


@router.get("/wps/{batch_id}/file")
def download_wps(batch_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    batch = db.scalar(select(WpsBatch).where(WpsBatch.id == batch_id).options(selectinload(WpsBatch.lines).selectinload(WpsBatchLine.employee)))
    if not batch: raise HTTPException(404, "WPS batch not found")
    ensure_permission(db, user, batch.company_id, "payroll.wps")
    content = _wps_content(batch)
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != batch.file_hash: raise HTTPException(409, "WPS file integrity mismatch")
    return Response(content=content, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{batch.batch_number}.txt"'})


@router.post("/wps/{batch_id}/response")
def record_wps_response(batch_id: int, data: WpsResponseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    batch = db.scalar(select(WpsBatch).where(WpsBatch.id == batch_id).options(selectinload(WpsBatch.lines)))
    if not batch: raise HTTPException(404, "WPS batch not found")
    ensure_permission(db, user, batch.company_id, "payroll.wps")
    allowed = {"SUBMITTED_MANUALLY", "ACCEPTED", "PARTIALLY_REJECTED", "REJECTED"}
    if data.status not in allowed: raise HTTPException(422, "Invalid WPS response status")
    by_employee = {line.employee_id: line for line in batch.lines}
    for response_line in data.lines:
        line = by_employee.get(response_line.employee_id)
        if not line: raise HTTPException(422, f"Employee {response_line.employee_id} is not in batch")
        line.status = response_line.status; line.rejection_code = response_line.rejection_code; line.rejection_reason = response_line.rejection_reason
    batch.status = data.status; batch.response_reference = data.response_reference; batch.response_message = data.response_message
    if data.status == "SUBMITTED_MANUALLY": batch.submitted_at = utc_now()
    if data.status == "ACCEPTED": batch.accepted_at = utc_now()
    write_audit(db, action="WPS_RESPONSE_RECORDED", entity_type="WPS_BATCH", entity_id=batch.id, user_id=user.id, company_id=batch.company_id, after=data.model_dump(mode="json"))
    db.commit(); return {"id": batch.id, "status": batch.status, "response_reference": batch.response_reference}


@router.get("/wps")
def list_wps(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    rows = db.scalars(select(WpsBatch).where(WpsBatch.company_id == company_id).order_by(WpsBatch.generated_at.desc())).all()
    return [{"id": r.id, "batch_number": r.batch_number, "execution_date": r.execution_date, "status": r.status,
             "total_amount": r.total_amount, "line_count": r.line_count, "file_hash": r.file_hash} for r in rows]


@router.post("/benefits/assumptions", status_code=201)
def create_benefit_assumption(data: BenefitAssumptionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "benefits.manage")
    if db.scalar(select(EmployeeBenefitAssumption.id).where(EmployeeBenefitAssumption.company_id == data.company_id, EmployeeBenefitAssumption.valuation_date == data.valuation_date)):
        raise HTTPException(409, "Assumptions already exist for this valuation date")
    row = EmployeeBenefitAssumption(**data.model_dump(), status="DRAFT", prepared_by=user.id)
    db.add(row); db.flush(); write_audit(db, action="BENEFIT_ASSUMPTIONS_PREPARED", entity_type="BENEFIT_ASSUMPTION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after=data.model_dump(mode="json")); db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/benefits/assumptions/{assumption_id}/review")
def review_benefit_assumption(assumption_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(EmployeeBenefitAssumption, assumption_id)
    if not row: raise HTTPException(404, "Assumptions not found")
    ensure_permission(db, user, row.company_id, "benefits.review")
    if row.prepared_by == user.id: raise HTTPException(409, "Preparer cannot review assumptions")
    if row.status != "DRAFT": raise HTTPException(409, "Assumptions must be DRAFT")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.post("/benefits/assumptions/{assumption_id}/approve")
def approve_benefit_assumption(assumption_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(EmployeeBenefitAssumption, assumption_id)
    if not row: raise HTTPException(404, "Assumptions not found")
    ensure_permission(db, user, row.company_id, "benefits.approve")
    if row.status != "REVIEWED": raise HTTPException(409, "Assumptions must be REVIEWED")
    if user.id in {row.prepared_by, row.reviewed_by}: raise HTTPException(409, "Approver must be independent")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


def _age(birth_date: date, as_of: date) -> Decimal:
    return Decimal((as_of - birth_date).days) / Decimal("365.25")


def _valuation_hash(row: EmployeeBenefitValuation) -> str:
    def dec(value) -> str:
        number = Decimal(str(value or 0)).normalize()
        return "0" if number == 0 else format(number, "f")
    payload = {"company_id": row.company_id, "valuation_date": str(row.valuation_date), "assumption_id": row.assumption_id,
               "total_dbo": dec(row.total_dbo), "current_service_cost": dec(row.current_service_cost), "interest_cost": dec(row.interest_cost),
               "actuarial_gain_loss": dec(row.actuarial_gain_loss), "lines": sorted([
                   {"employee_id": l.employee_id, "current_wage": dec(l.current_wage), "projected_final_wage": dec(l.projected_final_wage),
                    "service_years": dec(l.service_years), "future_service_years": dec(l.future_service_years), "survival_probability": dec(l.survival_probability),
                    "present_value_obligation": dec(l.present_value_obligation)} for l in row.lines], key=lambda x: x["employee_id"])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@router.post("/benefits/valuations", status_code=201)
def create_benefit_valuation(data: BenefitValuationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "benefits.manage")
    assumption = db.scalar(select(EmployeeBenefitAssumption).where(EmployeeBenefitAssumption.id == data.assumption_id, EmployeeBenefitAssumption.company_id == data.company_id, EmployeeBenefitAssumption.status == "APPROVED"))
    if not assumption: raise HTTPException(422, "Approved assumptions not found")
    employees = db.scalars(select(Employee).where(Employee.company_id == data.company_id, Employee.active.is_(True))).all()
    missing = [e.employee_number for e in employees if not e.birth_date]
    if missing: raise HTTPException(422, {"message": "Birth date is required for employee-benefit valuation", "employees": missing})
    version = (db.scalar(select(func.max(EmployeeBenefitValuation.version)).where(EmployeeBenefitValuation.company_id == data.company_id, EmployeeBenefitValuation.valuation_date == data.valuation_date)) or 0) + 1
    row = EmployeeBenefitValuation(company_id=data.company_id, assumption_id=assumption.id, valuation_date=data.valuation_date, version=version,
                                   status="READY_FOR_REVIEW", total_dbo=0, current_service_cost=0, interest_cost=0, actuarial_gain_loss=0,
                                   employee_count=0, analysis_hash="PENDING", prepared_by=user.id)
    previous = db.scalar(select(EmployeeBenefitValuation).where(EmployeeBenefitValuation.company_id == data.company_id, EmployeeBenefitValuation.status == "APPROVED_POSTED", EmployeeBenefitValuation.valuation_date < data.valuation_date).order_by(EmployeeBenefitValuation.valuation_date.desc()))
    total_dbo = Decimal("0"); current_service_cost = Decimal("0")
    for employee in employees:
        current_wage = money(Decimal(employee.basic_salary) + Decimal(employee.housing_allowance) + Decimal(employee.other_allowance))
        age = _age(employee.birth_date, data.valuation_date)
        service = max(Decimal("0"), Decimal((data.valuation_date - employee.hire_date).days + 1) / Decimal("365.25"))
        future = max(Decimal("0"), Decimal(assumption.retirement_age) - age)
        projected = money(current_wage * ((Decimal("1") + Decimal(assumption.salary_growth_rate)) ** future))
        total_service = max(service + future, Decimal("0.0001"))
        gross_benefit = projected * Decimal("0.5") * min(total_service, Decimal("5")) + projected * max(Decimal("0"), total_service - Decimal("5"))
        accrued_share = min(Decimal("1"), service / total_service)
        survival = ((Decimal("1") - Decimal(assumption.annual_turnover_rate)) ** future) * (Decimal(assumption.mortality_survival_factor) ** future)
        discount = (Decimal("1") + Decimal(assumption.discount_rate)) ** future
        obligation = money(gross_benefit * accrued_share * survival / discount)
        service_cost = money(gross_benefit / total_service * survival / discount)
        row.lines.append(EmployeeBenefitValuationLine(employee_id=employee.id, current_wage=current_wage, projected_final_wage=projected,
                                                       service_years=service.quantize(Decimal("0.000001")),
                                                       future_service_years=future.quantize(Decimal("0.000001")),
                                                       survival_probability=survival.quantize(Decimal("0.00000001")),
                                                       present_value_obligation=obligation))
        total_dbo += obligation; current_service_cost += service_cost
    row.total_dbo = money(total_dbo); row.current_service_cost = money(current_service_cost)
    row.interest_cost = money(Decimal(previous.total_dbo) * Decimal(assumption.discount_rate)) if previous else Decimal("0")
    row.actuarial_gain_loss = money(row.total_dbo - (Decimal(previous.total_dbo) + row.current_service_cost + row.interest_cost)) if previous else Decimal("0")
    row.employee_count = len(row.lines); row.analysis_hash = _valuation_hash(row)
    db.add(row); db.flush(); write_audit(db, action="BENEFIT_VALUATION_PREPARED", entity_type="BENEFIT_VALUATION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"employees": row.employee_count, "dbo": str(row.total_dbo), "analysis_hash": row.analysis_hash}); db.commit()
    return {"id": row.id, "status": row.status, "employee_count": row.employee_count, "total_dbo": row.total_dbo, "current_service_cost": row.current_service_cost, "interest_cost": row.interest_cost, "actuarial_gain_loss": row.actuarial_gain_loss, "analysis_hash": row.analysis_hash}


@router.post("/benefits/valuations/{valuation_id}/review")
def review_benefit_valuation(valuation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmployeeBenefitValuation).where(EmployeeBenefitValuation.id == valuation_id).options(selectinload(EmployeeBenefitValuation.lines)))
    if not row: raise HTTPException(404, "Valuation not found")
    ensure_permission(db, user, row.company_id, "benefits.review")
    if row.prepared_by == user.id: raise HTTPException(409, "Preparer cannot review valuation")
    if row.status != "READY_FOR_REVIEW": raise HTTPException(409, "Valuation must be READY_FOR_REVIEW")
    if _valuation_hash(row) != row.analysis_hash: raise HTTPException(409, "Valuation integrity mismatch")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.post("/benefits/valuations/{valuation_id}/approve")
def approve_benefit_valuation(valuation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(EmployeeBenefitValuation).where(EmployeeBenefitValuation.id == valuation_id).options(selectinload(EmployeeBenefitValuation.lines)))
    if not row: raise HTTPException(404, "Valuation not found")
    ensure_permission(db, user, row.company_id, "benefits.approve")
    if row.status != "REVIEWED": raise HTTPException(409, "Valuation must be REVIEWED")
    if user.id in {row.prepared_by, row.reviewed_by}: raise HTTPException(409, "Approver must be independent")
    if _valuation_hash(row) != row.analysis_hash: raise HTTPException(409, "Valuation integrity mismatch")
    expense = get_account(db, row.company_id, "619010"); liability = get_account(db, row.company_id, "216010")
    previous = db.scalar(select(EmployeeBenefitValuation).where(EmployeeBenefitValuation.company_id == row.company_id, EmployeeBenefitValuation.status == "APPROVED_POSTED", EmployeeBenefitValuation.valuation_date < row.valuation_date).order_by(EmployeeBenefitValuation.valuation_date.desc()))
    previous_dbo = Decimal(previous.total_dbo) if previous else Decimal("0")
    delta = money(Decimal(row.total_dbo) - previous_dbo)
    if delta == 0:
        raise HTTPException(422, "No valuation movement to post")
    lines = [{"account_id": expense.id, "debit": max(delta, Decimal("0")), "credit": max(-delta, Decimal("0"))},
             {"account_id": liability.id, "debit": max(-delta, Decimal("0")), "credit": max(delta, Decimal("0"))}]
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.valuation_date,
                                    reference=f"IAS19-{row.valuation_date}-V{row.version}", description="Employee benefit valuation movement", lines=lines)
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.journal_id = journal.id
    write_audit(db, action="BENEFIT_VALUATION_APPROVED_POSTED", entity_type="BENEFIT_VALUATION", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"journal": journal.number, "delta": str(delta)})
    db.commit(); return {"id": row.id, "status": row.status, "journal": journal.number, "total_dbo": row.total_dbo}


@router.get("/benefits/valuations")
def list_benefit_valuations(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    rows = db.scalars(select(EmployeeBenefitValuation).where(EmployeeBenefitValuation.company_id == company_id).order_by(EmployeeBenefitValuation.valuation_date.desc(), EmployeeBenefitValuation.version.desc())).all()
    return [{"id": r.id, "valuation_date": r.valuation_date, "version": r.version, "status": r.status, "employee_count": r.employee_count,
             "total_dbo": r.total_dbo, "current_service_cost": r.current_service_cost, "interest_cost": r.interest_cost, "actuarial_gain_loss": r.actuarial_gain_loss} for r in rows]


@router.get("/summary")
def advanced_hr_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "payroll.read")
    return {
        "contracts": db.scalar(select(func.count(EmployeeContract.id)).where(EmployeeContract.company_id == company_id)) or 0,
        "pending_overtime": db.scalar(select(func.count(OvertimeRequest.id)).where(OvertimeRequest.company_id == company_id, OvertimeRequest.status == "SUBMITTED")) or 0,
        "approved_adjustments": db.scalar(select(func.count(PayrollAdjustment.id)).where(PayrollAdjustment.company_id == company_id, PayrollAdjustment.status == "APPROVED", PayrollAdjustment.applied_payroll_run_id.is_(None))) or 0,
        "wps_batches": db.scalar(select(func.count(WpsBatch.id)).where(WpsBatch.company_id == company_id)) or 0,
        "benefit_valuations": db.scalar(select(func.count(EmployeeBenefitValuation.id)).where(EmployeeBenefitValuation.company_id == company_id)) or 0,
    }
