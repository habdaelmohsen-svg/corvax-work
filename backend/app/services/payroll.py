from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord, Employee, EmployeeShiftAssignment, LeaveRequest, LeaveType,
    OvertimeRequest, PayrollAdjustment, PayrollLine, PayrollPolicy, Shift,
)
from app.services.operations import money


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def approved_policy(db: Session, company_id: int) -> PayrollPolicy | None:
    return db.scalar(select(PayrollPolicy).where(
        PayrollPolicy.company_id == company_id,
        PayrollPolicy.active.is_(True),
        PayrollPolicy.approved_by.is_not(None),
    ))


def overlap_days(start_a: date, end_a: date, start_b: date, end_b: date) -> Decimal:
    start = max(start_a, start_b)
    end = min(end_a, end_b)
    return Decimal(max(0, (end - start).days + 1))


def _assignment(db: Session, company_id: int, employee_id: int, start: date, end: date):
    return db.scalar(select(EmployeeShiftAssignment).where(
        EmployeeShiftAssignment.company_id == company_id,
        EmployeeShiftAssignment.employee_id == employee_id,
        EmployeeShiftAssignment.active.is_(True),
        EmployeeShiftAssignment.effective_from <= end,
        or_(EmployeeShiftAssignment.effective_to.is_(None), EmployeeShiftAssignment.effective_to >= start),
    ).order_by(EmployeeShiftAssignment.effective_from.desc()))


def scheduled_work_dates(db: Session, employee: Employee, start: date, end: date) -> list[date]:
    active_start = max(start, employee.hire_date)
    active_end = min(end, employee.termination_date or end)
    if active_end < active_start:
        return []
    assignment = _assignment(db, employee.company_id, employee.id, active_start, active_end)
    if not assignment:
        return []
    shift = db.get(Shift, assignment.shift_id)
    if not shift:
        return []
    weekdays = {int(x) for x in shift.working_days.split(",") if x.strip()}
    dates: list[date] = []
    cursor = active_start
    while cursor <= active_end:
        if cursor.weekday() in weekdays:
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


def employee_period_inputs(db: Session, employee: Employee, year: int, month: int, policy: PayrollPolicy) -> dict:
    start, end = month_bounds(year, month)
    work_dates = scheduled_work_dates(db, employee, start, end)
    working_days = Decimal(len(work_dates))
    attendance = db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.company_id == employee.company_id,
        AttendanceRecord.employee_id == employee.id,
        AttendanceRecord.work_date >= start,
        AttendanceRecord.work_date <= end,
    )).all()
    attendance_by_date = {row.work_date: row for row in attendance}

    leaves = db.execute(select(LeaveRequest, LeaveType).join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id).where(
        LeaveRequest.company_id == employee.company_id,
        LeaveRequest.employee_id == employee.id,
        LeaveRequest.status == "APPROVED",
        LeaveRequest.start_date <= end,
        LeaveRequest.end_date >= start,
    )).all()
    paid_leave_dates: set[date] = set()
    unpaid_leave_dates: set[date] = set()
    for request, leave_type in leaves:
        cursor = max(start, request.start_date)
        leave_end = min(end, request.end_date)
        while cursor <= leave_end:
            if cursor in work_dates:
                (paid_leave_dates if leave_type.paid and not leave_type.affects_payroll else unpaid_leave_dates).add(cursor)
            cursor += timedelta(days=1)

    accounted_dates = set(attendance_by_date) | paid_leave_dates | unpaid_leave_dates
    completeness = Decimal("100") if working_days == 0 else (Decimal(len(accounted_dates & set(work_dates))) / working_days * Decimal("100"))
    absent_days = Decimal(sum(1 for row in attendance if row.status == "ABSENT"))
    unpaid_leave_days = Decimal(len(unpaid_leave_dates))
    late_minutes = sum(int(row.late_minutes or 0) for row in attendance)

    overtime = db.scalars(select(OvertimeRequest).where(
        OvertimeRequest.company_id == employee.company_id,
        OvertimeRequest.employee_id == employee.id,
        OvertimeRequest.work_date >= start,
        OvertimeRequest.work_date <= end,
        OvertimeRequest.status == "APPROVED",
        OvertimeRequest.payroll_run_id.is_(None),
    )).all()
    overtime_minutes = sum(int(row.approved_minutes or 0) for row in overtime)
    weighted_overtime_minutes = sum(Decimal(row.approved_minutes or 0) * Decimal(row.rate_multiplier or 1) for row in overtime)

    adjustments = db.scalars(select(PayrollAdjustment).where(
        PayrollAdjustment.company_id == employee.company_id,
        PayrollAdjustment.employee_id == employee.id,
        PayrollAdjustment.period_year == year,
        PayrollAdjustment.period_month == month,
        PayrollAdjustment.status == "APPROVED",
        PayrollAdjustment.applied_payroll_run_id.is_(None),
    )).all()
    earning_adjustments = money(sum((Decimal(row.amount or 0) for row in adjustments if row.earning), Decimal("0")))
    deduction_adjustments = money(sum((Decimal(row.amount or 0) for row in adjustments if not row.earning), Decimal("0")))
    gosi_adjustments = money(sum((Decimal(row.amount or 0) for row in adjustments if row.earning and row.gosi_applicable), Decimal("0")))

    basic = money(employee.basic_salary)
    housing = money(employee.housing_allowance)
    other = money(employee.other_allowance)
    salary_day_basis = Decimal(policy.salary_day_basis)
    daily_gross = (basic + housing + other) / salary_day_basis
    hourly_basis = (basic if policy.overtime_basis == "BASIC" else basic + housing + other) / salary_day_basis / Decimal(policy.standard_daily_hours)
    overtime_amount = money(hourly_basis * weighted_overtime_minutes / Decimal("60"))
    absence_deduction = money(daily_gross * absent_days) if policy.absence_deduction_enabled else Decimal("0")
    unpaid_leave_deduction = money(daily_gross * unpaid_leave_days)
    late_deduction = money(daily_gross / Decimal(policy.standard_daily_hours) / Decimal("60") * Decimal(late_minutes)) if policy.late_deduction_enabled else Decimal("0")
    deduction_adjustments = money(deduction_adjustments + late_deduction)

    base_gross = money(basic + housing + other)
    gross = money(base_gross + overtime_amount + earning_adjustments)
    if policy.gosi_basis == "BASIC":
        gosi_base = basic
    elif policy.gosi_basis == "GROSS":
        gosi_base = gross
    else:
        gosi_base = money(basic + housing)
    gosi_base = money(gosi_base + gosi_adjustments)
    employee_gosi = money(gosi_base * Decimal(employee.employee_gosi_rate) / Decimal("100"))
    employer_gosi = money(gosi_base * Decimal(employee.employer_gosi_rate) / Decimal("100"))
    deductions_total = money(absence_deduction + unpaid_leave_deduction + deduction_adjustments)
    net = money(gross - employee_gosi - deductions_total)
    if net < 0:
        raise HTTPException(422, f"Negative net salary for employee {employee.employee_number}")

    return {
        "line": PayrollLine(
            employee_id=employee.id,
            basic_salary=basic,
            housing_allowance=housing,
            other_allowance=other,
            gross_salary=gross,
            employee_gosi=employee_gosi,
            employer_gosi=employer_gosi,
            other_deductions=deductions_total,
            working_days=working_days,
            paid_days=max(Decimal("0"), working_days - absent_days - unpaid_leave_days),
            absent_days=absent_days,
            unpaid_leave_days=unpaid_leave_days,
            late_minutes=late_minutes,
            overtime_minutes=overtime_minutes,
            overtime_amount=overtime_amount,
            absence_deduction=absence_deduction,
            unpaid_leave_deduction=unpaid_leave_deduction,
            earning_adjustments=earning_adjustments,
            deduction_adjustments=deduction_adjustments,
            net_salary=net,
        ),
        "completeness": completeness.quantize(Decimal("0.01")),
        "overtime_rows": overtime,
        "adjustment_rows": adjustments,
    }


def payroll_analysis_hash(run) -> str:
    def dec(value) -> str:
        number = Decimal(str(value or 0)).normalize()
        return "0" if number == 0 else format(number, "f")

    payload = {
        "company_id": run.company_id,
        "period": f"{run.period_year:04d}-{run.period_month:02d}",
        "payment_date": str(run.payment_date),
        "totals": {
            "gross": dec(run.total_gross), "employee_gosi": dec(run.total_employee_gosi),
            "employer_gosi": dec(run.total_employer_gosi), "deductions": dec(run.total_deductions), "net": dec(run.total_net),
        },
        "attendance_completeness_percent": dec(run.attendance_completeness_percent),
        "lines": sorted([
            {
                "employee_id": line.employee_id, "gross": dec(line.gross_salary), "employee_gosi": dec(line.employee_gosi),
                "employer_gosi": dec(line.employer_gosi), "deductions": dec(line.other_deductions), "net": dec(line.net_salary),
                "working_days": dec(line.working_days), "absent_days": dec(line.absent_days), "unpaid_leave_days": dec(line.unpaid_leave_days),
                "late_minutes": int(line.late_minutes or 0), "overtime_minutes": int(line.overtime_minutes or 0),
                "overtime_amount": dec(line.overtime_amount), "earning_adjustments": dec(line.earning_adjustments),
                "deduction_adjustments": dec(line.deduction_adjustments),
            } for line in run.lines
        ], key=lambda row: row["employee_id"]),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
