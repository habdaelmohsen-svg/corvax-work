from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    AttendanceRecord, Branch, Employee, EmployeeShiftAssignment, EndOfServiceSettlement,
    LeaveRequest, LeaveType, LegalRuleVersion, Shift, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/hr", tags=["HR operations and Saudi compliance"])


class ShiftIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    start_time: time
    end_time: time
    grace_minutes: int = Field(default=10, ge=0, le=180)
    working_days: str = "6,0,1,2,3"


class AssignmentIn(BaseModel):
    company_id: int
    employee_id: int
    shift_id: int
    branch_id: int
    effective_from: date
    effective_to: date | None = None


class ClockInOut(BaseModel):
    company_id: int
    employee_id: int
    event_time: datetime
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    source: str = "WEB"


class ManualAttendanceIn(BaseModel):
    company_id: int
    employee_id: int
    work_date: date
    status: str
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    reason: str = Field(min_length=5, max_length=500)


class LeaveRequestIn(BaseModel):
    company_id: int
    employee_id: int
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot precede start date")
        return self


class EosCalculateIn(BaseModel):
    company_id: int
    employee_id: int
    termination_date: date
    termination_reason: str
    last_wage: Decimal | None = Field(default=None, gt=0)
    unused_leave_days: Decimal = Field(default=0, ge=0)
    deductions: Decimal = Field(default=0, ge=0)


class EosApproveIn(BaseModel):
    payment_date: date


def _assignment_for(db: Session, company_id: int, employee_id: int, work_date: date) -> EmployeeShiftAssignment:
    row = db.scalar(
        select(EmployeeShiftAssignment).where(
            EmployeeShiftAssignment.company_id == company_id,
            EmployeeShiftAssignment.employee_id == employee_id,
            EmployeeShiftAssignment.active.is_(True),
            EmployeeShiftAssignment.effective_from <= work_date,
            or_(EmployeeShiftAssignment.effective_to.is_(None), EmployeeShiftAssignment.effective_to >= work_date),
        ).order_by(EmployeeShiftAssignment.effective_from.desc())
    )
    if not row:
        raise HTTPException(422, "Employee has no active shift assignment for this date")
    return row


def _distance_m(lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2 - lat1))
    dlambda = math.radians(float(lon2 - lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _geofence(branch: Branch, lat: Decimal | None, lon: Decimal | None) -> bool | None:
    if branch.latitude is None or branch.longitude is None:
        return None
    if lat is None or lon is None:
        return False
    return _distance_m(Decimal(branch.latitude), Decimal(branch.longitude), lat, lon) <= int(branch.geofence_radius_m)


def _serialize_attendance(row: AttendanceRecord) -> dict:
    return {
        "id": row.id, "employee_id": row.employee_id, "shift_id": row.shift_id, "branch_id": row.branch_id,
        "work_date": row.work_date, "clock_in": row.clock_in, "clock_out": row.clock_out, "status": row.status,
        "late_minutes": row.late_minutes, "early_leave_minutes": row.early_leave_minutes,
        "overtime_minutes": row.overtime_minutes, "source": row.source, "geofence_valid": row.geofence_valid,
        "manual_reason": row.manual_reason,
    }


@router.post("/shifts", status_code=201)
def create_shift(data: ShiftIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attendance.manage")
    if db.scalar(select(Shift).where(Shift.company_id == data.company_id, Shift.code == data.code)):
        raise HTTPException(409, "Shift code already exists")
    row = Shift(**data.model_dump(), active=True)
    db.add(row); db.flush()
    write_audit(db, action="SHIFT_CREATED", entity_type="SHIFT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after=data.model_dump(mode="json"))
    db.commit()
    return {"id": row.id, "code": row.code, "start_time": row.start_time, "end_time": row.end_time}


@router.get("/shifts")
def list_shifts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attendance.read")
    rows = db.scalars(select(Shift).where(Shift.company_id == company_id, Shift.active.is_(True)).order_by(Shift.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "start_time": r.start_time, "end_time": r.end_time, "grace_minutes": r.grace_minutes, "working_days": r.working_days} for r in rows]


@router.post("/shift-assignments", status_code=201)
def assign_shift(data: AssignmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attendance.manage")
    employee = db.scalar(select(Employee).where(Employee.id == data.employee_id, Employee.company_id == data.company_id, Employee.active.is_(True)))
    shift = db.scalar(select(Shift).where(Shift.id == data.shift_id, Shift.company_id == data.company_id, Shift.active.is_(True)))
    branch = db.scalar(select(Branch).where(Branch.id == data.branch_id, Branch.company_id == data.company_id, Branch.active.is_(True)))
    if not employee or not shift or not branch:
        raise HTTPException(404, "Employee, shift, or branch not found")
    overlaps = db.scalar(select(EmployeeShiftAssignment).where(
        EmployeeShiftAssignment.employee_id == data.employee_id,
        EmployeeShiftAssignment.active.is_(True),
        EmployeeShiftAssignment.effective_from <= (data.effective_to or date.max),
        or_(EmployeeShiftAssignment.effective_to.is_(None), EmployeeShiftAssignment.effective_to >= data.effective_from),
    ))
    if overlaps:
        raise HTTPException(409, "An overlapping active assignment already exists")
    row = EmployeeShiftAssignment(**data.model_dump(), active=True, created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="SHIFT_ASSIGNED", entity_type="EMPLOYEE_SHIFT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"employee_id": data.employee_id, "shift_id": data.shift_id})
    db.commit()
    return {"id": row.id, "employee_id": row.employee_id, "shift_id": row.shift_id, "branch_id": row.branch_id}


@router.post("/attendance/clock-in")
def clock_in(data: ClockInOut, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attendance.capture")
    work_date = data.event_time.date()
    assignment = _assignment_for(db, data.company_id, data.employee_id, work_date)
    shift = db.get(Shift, assignment.shift_id); branch = db.get(Branch, assignment.branch_id)
    if work_date.weekday() not in {int(x) for x in shift.working_days.split(",") if x.strip()}:
        raise HTTPException(422, "The assigned shift is not scheduled on this weekday")
    if db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == data.employee_id, AttendanceRecord.work_date == work_date)):
        raise HTTPException(409, "Attendance record already exists")
    scheduled = datetime.combine(work_date, shift.start_time)
    late = max(0, int((data.event_time - scheduled).total_seconds() // 60) - shift.grace_minutes)
    geo_valid = _geofence(branch, data.latitude, data.longitude)
    if geo_valid is False:
        raise HTTPException(422, "Attendance location is outside the branch geofence")
    row = AttendanceRecord(
        company_id=data.company_id, employee_id=data.employee_id, shift_id=shift.id, branch_id=branch.id,
        work_date=work_date, clock_in=data.event_time, status="PRESENT" if late == 0 else "LATE",
        late_minutes=late, source=data.source, latitude=data.latitude, longitude=data.longitude, geofence_valid=geo_valid,
    )
    db.add(row); db.flush()
    write_audit(db, action="ATTENDANCE_CLOCK_IN", entity_type="ATTENDANCE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"late_minutes": late, "geofence_valid": geo_valid})
    db.commit()
    return _serialize_attendance(row)


@router.post("/attendance/clock-out")
def clock_out(data: ClockInOut, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attendance.capture")
    work_date = data.event_time.date()
    row = db.scalar(select(AttendanceRecord).where(AttendanceRecord.company_id == data.company_id, AttendanceRecord.employee_id == data.employee_id, AttendanceRecord.work_date == work_date))
    if not row or not row.clock_in:
        raise HTTPException(404, "Clock-in record not found")
    if row.clock_out:
        raise HTTPException(409, "Employee is already clocked out")
    branch = db.get(Branch, row.branch_id); shift = db.get(Shift, row.shift_id)
    geo_valid = _geofence(branch, data.latitude, data.longitude)
    if geo_valid is False:
        raise HTTPException(422, "Attendance location is outside the branch geofence")
    scheduled_end = datetime.combine(work_date, shift.end_time)
    if shift.end_time <= shift.start_time:
        scheduled_end += timedelta(days=1)
    row.clock_out = data.event_time
    row.early_leave_minutes = max(0, int((scheduled_end - data.event_time).total_seconds() // 60))
    row.overtime_minutes = max(0, int((data.event_time - scheduled_end).total_seconds() // 60))
    row.geofence_valid = geo_valid if geo_valid is not None else row.geofence_valid
    write_audit(db, action="ATTENDANCE_CLOCK_OUT", entity_type="ATTENDANCE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"early_leave_minutes": row.early_leave_minutes, "overtime_minutes": row.overtime_minutes})
    db.commit()
    return _serialize_attendance(row)


@router.post("/attendance/manual")
def manual_attendance(data: ManualAttendanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attendance.override")
    assignment = _assignment_for(db, data.company_id, data.employee_id, data.work_date)
    row = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == data.employee_id, AttendanceRecord.work_date == data.work_date))
    before = _serialize_attendance(row) if row else None
    if not row:
        row = AttendanceRecord(company_id=data.company_id, employee_id=data.employee_id, shift_id=assignment.shift_id, branch_id=assignment.branch_id, work_date=data.work_date)
        db.add(row)
    row.status = data.status.upper(); row.clock_in = data.clock_in; row.clock_out = data.clock_out
    row.source = "MANUAL"; row.manual_reason = data.reason; row.approved_by = user.id
    db.flush()
    write_audit(db, action="ATTENDANCE_MANUAL_OVERRIDE", entity_type="ATTENDANCE", entity_id=row.id, user_id=user.id, company_id=data.company_id, before=before, after=_serialize_attendance(row))
    db.commit()
    return _serialize_attendance(row)


@router.post("/attendance/finalize-day")
def finalize_day(company_id: int, work_date: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attendance.manage")
    assignments = db.scalars(select(EmployeeShiftAssignment).where(
        EmployeeShiftAssignment.company_id == company_id, EmployeeShiftAssignment.active.is_(True),
        EmployeeShiftAssignment.effective_from <= work_date,
        or_(EmployeeShiftAssignment.effective_to.is_(None), EmployeeShiftAssignment.effective_to >= work_date),
    )).all()
    created = 0
    for assignment in assignments:
        shift = db.get(Shift, assignment.shift_id)
        if work_date.weekday() not in {int(x) for x in shift.working_days.split(",") if x.strip()}:
            continue
        existing = db.scalar(select(AttendanceRecord.id).where(AttendanceRecord.employee_id == assignment.employee_id, AttendanceRecord.work_date == work_date))
        approved_leave = db.scalar(select(LeaveRequest.id).where(
            LeaveRequest.employee_id == assignment.employee_id, LeaveRequest.status == "APPROVED",
            LeaveRequest.start_date <= work_date, LeaveRequest.end_date >= work_date,
        ))
        if not existing:
            db.add(AttendanceRecord(company_id=company_id, employee_id=assignment.employee_id, shift_id=assignment.shift_id, branch_id=assignment.branch_id, work_date=work_date, status="ON_LEAVE" if approved_leave else "ABSENT", source="SYSTEM"))
            created += 1
    write_audit(db, action="ATTENDANCE_DAY_FINALIZED", entity_type="ATTENDANCE_DAY", entity_id=str(work_date), user_id=user.id, company_id=company_id, after={"records_created": created})
    db.commit()
    return {"work_date": work_date, "records_created": created}


@router.get("/attendance")
def list_attendance(company_id: int, start_date: date, end_date: date, employee_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attendance.read")
    query = select(AttendanceRecord).where(AttendanceRecord.company_id == company_id, AttendanceRecord.work_date.between(start_date, end_date))
    if employee_id:
        query = query.where(AttendanceRecord.employee_id == employee_id)
    rows = db.scalars(query.order_by(AttendanceRecord.work_date.desc(), AttendanceRecord.employee_id)).all()
    return [_serialize_attendance(row) for row in rows]


@router.get("/leave-types")
def list_leave_types(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "leave.read")
    rows = db.scalars(select(LeaveType).where(LeaveType.company_id == company_id, LeaveType.active.is_(True)).order_by(LeaveType.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "paid": r.paid, "affects_payroll": r.affects_payroll} for r in rows]


@router.post("/leaves", status_code=201)
def create_leave(data: LeaveRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "leave.manage")
    employee = db.scalar(select(Employee).where(Employee.id == data.employee_id, Employee.company_id == data.company_id, Employee.active.is_(True)))
    leave_type = db.scalar(select(LeaveType).where(LeaveType.id == data.leave_type_id, LeaveType.company_id == data.company_id, LeaveType.active.is_(True)))
    if not employee or not leave_type:
        raise HTTPException(404, "Employee or leave type not found")
    overlap = db.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id == data.employee_id, LeaveRequest.status.in_(["SUBMITTED", "APPROVED"]), LeaveRequest.start_date <= data.end_date, LeaveRequest.end_date >= data.start_date))
    if overlap:
        raise HTTPException(409, "Leave dates overlap an existing request")
    days = Decimal((data.end_date - data.start_date).days + 1)
    number = f"LV-{data.company_id}-{utc_now():%Y%m%d%H%M%S%f}"
    row = LeaveRequest(**data.model_dump(), number=number, days=days, status="SUBMITTED", created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="LEAVE_SUBMITTED", entity_type="LEAVE_REQUEST", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"employee_id": row.employee_id, "days": str(days)})
    db.commit()
    return {"id": row.id, "number": row.number, "days": row.days, "status": row.status}


@router.post("/leaves/{leave_id}/approve")
def approve_leave(leave_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(LeaveRequest, leave_id)
    if not row:
        raise HTTPException(404, "Leave request not found")
    ensure_permission(db, user, row.company_id, "leave.approve")
    if row.status != "SUBMITTED":
        raise HTTPException(409, "Only submitted leave can be approved")
    if row.created_by == user.id:
        raise HTTPException(409, "Maker-checker control: requester cannot approve the same leave")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="LEAVE_APPROVED", entity_type="LEAVE_REQUEST", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"days": str(row.days)})
    db.commit()
    return {"id": row.id, "number": row.number, "status": row.status}


@router.get("/leaves/balance")
def leave_balance(company_id: int, employee_id: int, as_of_date: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "leave.read")
    employee = db.scalar(select(Employee).where(Employee.id == employee_id, Employee.company_id == company_id))
    if not employee:
        raise HTTPException(404, "Employee not found")
    service_days = max(0, (as_of_date - employee.hire_date).days + 1)
    accrued = money(Decimal(service_days) / Decimal("365") * Decimal(employee.annual_leave_days))
    used = db.scalar(select(func.coalesce(func.sum(LeaveRequest.days), 0)).join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id).where(LeaveRequest.employee_id == employee_id, LeaveRequest.status == "APPROVED", LeaveType.paid.is_(True), LeaveRequest.start_date <= as_of_date)) or Decimal("0")
    return {"employee_id": employee_id, "as_of_date": as_of_date, "accrued_days": accrued, "used_days": money(used), "available_days": money(accrued - Decimal(used))}


def _active_eos_rule(db: Session, termination_date: date) -> LegalRuleVersion:
    rule = db.scalar(select(LegalRuleVersion).where(
        LegalRuleVersion.code == "SA_LABOR_EOS", LegalRuleVersion.active.is_(True),
        LegalRuleVersion.effective_from <= termination_date,
        or_(LegalRuleVersion.effective_to.is_(None), LegalRuleVersion.effective_to >= termination_date),
    ).order_by(LegalRuleVersion.effective_from.desc()))
    if not rule:
        raise HTTPException(422, "No active Saudi end-of-service rule version found")
    return rule


def _eos_entitlement(reason: str, years: Decimal) -> Decimal:
    reason = reason.upper()
    if reason == "PROBATION":
        return Decimal("0")
    if reason in {"EMPLOYER_TERMINATION", "CONTRACT_EXPIRY", "FORCE_MAJEURE", "RETIREMENT", "DEATH", "DISABILITY"}:
        return Decimal("100")
    if reason == "RESIGNATION":
        if years < Decimal("2"):
            return Decimal("0")
        if years <= Decimal("5"):
            return Decimal("33.3333")
        if years < Decimal("10"):
            return Decimal("66.6667")
        return Decimal("100")
    return Decimal("100")


@router.post("/end-of-service/calculate", status_code=201)
def calculate_eos(data: EosCalculateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "eos.manage")
    employee = db.scalar(select(Employee).where(Employee.id == data.employee_id, Employee.company_id == data.company_id))
    if not employee:
        raise HTTPException(404, "Employee not found")
    if data.termination_date < employee.hire_date:
        raise HTTPException(422, "Termination date cannot precede hire date")
    rule = _active_eos_rule(db, data.termination_date)
    service_days = (data.termination_date - employee.hire_date).days + 1
    years = Decimal(service_days) / Decimal("365")
    wage = money(data.last_wage or (Decimal(employee.basic_salary) + Decimal(employee.housing_allowance) + Decimal(employee.other_allowance)))
    first_years = min(years, Decimal("5")); later_years = max(Decimal("0"), years - Decimal("5"))
    gross = money(wage * Decimal("0.5") * first_years + wage * later_years)
    entitlement = _eos_entitlement(data.termination_reason, years)
    award = money(gross * entitlement / Decimal("100"))
    leave_encashment = money(wage / Decimal("30") * data.unused_leave_days)
    net = money(award + leave_encashment - data.deductions)
    number = f"EOS-{data.company_id}-{utc_now():%Y%m%d%H%M%S%f}"
    row = EndOfServiceSettlement(
        company_id=data.company_id, number=number, employee_id=employee.id, termination_date=data.termination_date,
        termination_reason=data.termination_reason.upper(), service_days=service_days, last_wage=wage, gross_award=gross,
        entitlement_percent=entitlement, award_amount=award, leave_encashment=leave_encashment,
        deductions=money(data.deductions), net_settlement=net, rule_version_id=rule.id, status="CALCULATED", created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="EOS_CALCULATED", entity_type="EOS_SETTLEMENT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"service_days": service_days, "entitlement_percent": str(entitlement), "net": str(net), "rule": rule.code})
    db.commit()
    return {"id": row.id, "number": row.number, "service_days": service_days, "service_years": years.quantize(Decimal("0.0001")), "last_wage": wage, "gross_award": gross, "entitlement_percent": entitlement, "award_amount": award, "leave_encashment": leave_encashment, "deductions": row.deductions, "net_settlement": net, "status": row.status, "rule_source": rule.source_url}


@router.post("/end-of-service/{settlement_id}/approve")
def approve_eos(settlement_id: int, data: EosApproveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(EndOfServiceSettlement, settlement_id)
    if not row:
        raise HTTPException(404, "Settlement not found")
    ensure_permission(db, user, row.company_id, "eos.approve")
    if row.status != "CALCULATED":
        raise HTTPException(409, "Settlement must be CALCULATED")
    if row.created_by == user.id:
        raise HTTPException(409, "Maker-checker control: calculator cannot approve settlement")
    eos_expense = get_account(db, row.company_id, "619010")
    eos_payable = get_account(db, row.company_id, "216010")
    deductions_payable = get_account(db, row.company_id, "215030")
    gross_due = money(row.award_amount + row.leave_encashment)
    lines = [{"account_id": eos_expense.id, "debit": gross_due, "credit": 0}, {"account_id": eos_payable.id, "debit": 0, "credit": row.net_settlement}]
    if row.deductions > 0:
        lines.append({"account_id": deductions_payable.id, "debit": 0, "credit": row.deductions})
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=data.payment_date, reference=row.number, description=f"End-of-service accrual {row.number}", lines=lines)
    row.status = "APPROVED"; row.approved_by = user.id; row.journal_id = journal.id
    employee = db.get(Employee, row.employee_id); employee.employment_status = "TERMINATED"; employee.termination_date = row.termination_date; employee.active = False
    write_audit(db, action="EOS_APPROVED_POSTED", entity_type="EOS_SETTLEMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"journal": journal.number, "net": str(row.net_settlement)})
    db.commit()
    return {"id": row.id, "number": row.number, "status": row.status, "journal": journal.number, "net_settlement": row.net_settlement}

@router.get("/summary")
def hr_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attendance.read")
    today = date.today()
    return {
        "company_id": company_id,
        "active_employees": db.scalar(select(func.count(Employee.id)).where(Employee.company_id == company_id, Employee.active.is_(True))) or 0,
        "shift_assignments": db.scalar(select(func.count(EmployeeShiftAssignment.id)).where(EmployeeShiftAssignment.company_id == company_id, EmployeeShiftAssignment.active.is_(True))) or 0,
        "attendance_today": db.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.company_id == company_id, AttendanceRecord.work_date == today)) or 0,
        "late_today": db.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.company_id == company_id, AttendanceRecord.work_date == today, AttendanceRecord.status == "LATE")) or 0,
        "approved_leave_requests": db.scalar(select(func.count(LeaveRequest.id)).where(LeaveRequest.company_id == company_id, LeaveRequest.status == "APPROVED")) or 0,
        "eos_settlements": db.scalar(select(func.count(EndOfServiceSettlement.id)).where(EndOfServiceSettlement.company_id == company_id)) or 0,
        "shift_required": True,
        "geofence_control": True,
        "manual_override_audited": True,
    }
