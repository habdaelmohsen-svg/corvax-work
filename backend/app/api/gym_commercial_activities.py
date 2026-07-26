from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (
    Account, BankAccount, Branch, CostCenter, GymCafeProductProfile, GymDepartment,
    GymDepartmentAccessRecord, GymDepartmentPlanAccess, GymFacility, GymFacilityBooking,
    GymMembershipState, Member, MembershipContract, MembershipPlan, MenuItem, PosOrder, User,
)
from app.services.audit import write_audit
from app.services.operations import money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/gym", tags=["Gym departments and cafe RC15"])

DEPARTMENT_TYPES = {
    "SWIMMING", "STRENGTH", "PADEL", "CARDIO", "GROUP_FITNESS", "MARTIAL_ARTS",
    "KIDS", "RECOVERY", "CAFE", "OTHER",
}
FACILITY_TYPES = {"POOL", "LANE", "PADEL_COURT", "COURT", "STUDIO", "HALL", "ZONE", "ROOM", "OTHER"}
ACCESS_MODES = {"INCLUDED", "ADDON", "PAY_PER_USE", "EXCLUDED"}
CAFE_CATEGORIES = {"COFFEE", "HEALTHY_MEAL", "COLD_DRINK", "HOT_DRINK", "PROTEIN", "SNACK", "OTHER"}
CAFE_PRODUCT_TYPES = {"PREPARED", "PACKAGED", "BEVERAGE"}


def _number(db: Session, model, company_id: int, prefix: str) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{date.today().year}-{count + 1:05d}"


def _department(db: Session, company_id: int, department_id: int, *, active: bool = True) -> GymDepartment:
    query = select(GymDepartment).where(GymDepartment.id == department_id, GymDepartment.company_id == company_id)
    if active:
        query = query.where(GymDepartment.active.is_(True))
    row = db.scalar(query)
    if not row:
        raise HTTPException(404, "Gym department not found")
    return row


def _valid_contract(db: Session, company_id: int, member_id: int, branch_id: int, on_date: date, contract_id: int | None = None) -> MembershipContract:
    query = select(MembershipContract).where(
        MembershipContract.company_id == company_id,
        MembershipContract.member_id == member_id,
        MembershipContract.status.in_(["ACTIVE", "FROZEN"]),
        MembershipContract.start_date <= on_date,
        MembershipContract.end_date >= on_date,
    )
    if contract_id is not None:
        query = query.where(MembershipContract.id == contract_id)
    contract = db.scalar(query.order_by(MembershipContract.id.desc()))
    if not contract:
        raise HTTPException(409, "NO_ACTIVE_MEMBERSHIP")
    state = db.scalar(select(GymMembershipState).where(GymMembershipState.contract_id == contract.id))
    if state:
        if state.branch_id and state.branch_id != branch_id:
            raise HTTPException(409, "WRONG_BRANCH")
        if state.freeze_start and state.freeze_end and state.freeze_start <= on_date <= state.freeze_end:
            raise HTTPException(409, "MEMBERSHIP_FROZEN")
    if contract.status == "FROZEN":
        raise HTTPException(409, "MEMBERSHIP_FROZEN")
    return contract


def _access_rule(db: Session, company_id: int, plan_id: int, department_id: int) -> GymDepartmentPlanAccess:
    rule = db.scalar(select(GymDepartmentPlanAccess).where(
        GymDepartmentPlanAccess.company_id == company_id,
        GymDepartmentPlanAccess.plan_id == plan_id,
        GymDepartmentPlanAccess.department_id == department_id,
        GymDepartmentPlanAccess.active.is_(True),
    ))
    if not rule or rule.access_mode == "EXCLUDED":
        raise HTTPException(409, "DEPARTMENT_NOT_INCLUDED_IN_MEMBERSHIP")
    return rule


def _booking_dict(row: GymFacilityBooking) -> dict:
    return {
        "id": row.id, "number": row.number, "facility_id": row.facility_id,
        "facility": row.facility.name_en, "department_id": row.facility.department_id,
        "member_id": row.member_id, "contract_id": row.contract_id,
        "starts_at": row.starts_at, "ends_at": row.ends_at, "participants": row.participants,
        "access_mode": row.access_mode, "net_amount": row.net_amount, "vat_amount": row.vat_amount,
        "total_amount": row.total_amount, "status": row.status, "requested_by": row.requested_by,
        "approved_by": row.approved_by, "sale_journal_id": row.sale_journal_id,
        "refund_journal_id": row.refund_journal_id,
    }


class DepartmentIn(BaseModel):
    company_id: int
    branch_id: int
    code: str = Field(min_length=2, max_length=30)
    name_ar: str = Field(min_length=2, max_length=200)
    name_en: str = Field(min_length=2, max_length=200)
    department_type: str
    cost_center_id: int
    revenue_account_id: int
    capacity: int = Field(default=0, ge=0, le=10000)
    booking_required: bool = False

    @model_validator(mode="after")
    def validate_type(self):
        self.department_type = self.department_type.upper()
        if self.department_type not in DEPARTMENT_TYPES:
            raise ValueError("Unsupported gym department type")
        return self


@router.post("/departments", status_code=201)
def create_department(data: DepartmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.departments.manage")
    branch = db.scalar(select(Branch).where(Branch.id == data.branch_id, Branch.company_id == data.company_id, Branch.active.is_(True)))
    cost_center = db.scalar(select(CostCenter).where(CostCenter.id == data.cost_center_id, CostCenter.company_id == data.company_id, CostCenter.active.is_(True)))
    revenue = db.scalar(select(Account).where(Account.id == data.revenue_account_id, Account.company_id == data.company_id, Account.active.is_(True), Account.is_postable.is_(True)))
    if not branch: raise HTTPException(404, "Branch not found")
    if not cost_center: raise HTTPException(404, "Cost center not found")
    if not revenue or revenue.account_type != "REVENUE": raise HTTPException(422, "Postable revenue account is required")
    if db.scalar(select(GymDepartment).where(GymDepartment.company_id == data.company_id, GymDepartment.branch_id == data.branch_id, GymDepartment.code == data.code)):
        raise HTTPException(409, "Department code already exists in branch")
    row = GymDepartment(**data.model_dump(), active=True, created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="GYM_DEPARTMENT_CREATED", entity_type="GYM_DEPARTMENT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "type": row.department_type, "branch_id": row.branch_id})
    db.commit()
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "department_type": row.department_type, "branch_id": row.branch_id, "cost_center_id": row.cost_center_id, "capacity": row.capacity, "booking_required": row.booking_required, "active": row.active}


@router.get("/departments")
def list_departments(company_id: int, branch_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    query = select(GymDepartment).where(GymDepartment.company_id == company_id)
    if branch_id is not None: query = query.where(GymDepartment.branch_id == branch_id)
    rows = db.scalars(query.order_by(GymDepartment.branch_id, GymDepartment.code)).all()
    return [{"id": r.id, "branch_id": r.branch_id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "department_type": r.department_type, "cost_center_id": r.cost_center_id, "revenue_account_id": r.revenue_account_id, "capacity": r.capacity, "booking_required": r.booking_required, "active": r.active} for r in rows]


class PlanAccessIn(BaseModel):
    company_id: int
    plan_id: int
    department_id: int
    access_mode: str = "INCLUDED"
    monthly_visit_limit: int | None = Field(default=None, ge=1, le=1000)
    advance_booking_days: int = Field(default=7, ge=0, le=365)
    guest_allowed: bool = False

    @model_validator(mode="after")
    def validate_mode(self):
        self.access_mode = self.access_mode.upper()
        if self.access_mode not in ACCESS_MODES:
            raise ValueError("Unsupported access mode")
        return self


@router.post("/department-plan-access", status_code=201)
def set_department_plan_access(data: PlanAccessIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.departments.manage")
    _department(db, data.company_id, data.department_id)
    plan = db.scalar(select(MembershipPlan).where(MembershipPlan.id == data.plan_id, MembershipPlan.company_id == data.company_id, MembershipPlan.active.is_(True)))
    if not plan: raise HTTPException(404, "Membership plan not found")
    row = db.scalar(select(GymDepartmentPlanAccess).where(GymDepartmentPlanAccess.plan_id == data.plan_id, GymDepartmentPlanAccess.department_id == data.department_id))
    if row:
        for key, value in data.model_dump(exclude={"company_id", "plan_id", "department_id"}).items(): setattr(row, key, value)
        row.active = True
    else:
        row = GymDepartmentPlanAccess(**data.model_dump(), active=True, created_by=user.id); db.add(row)
    db.flush(); db.commit()
    return {"id": row.id, "plan_id": row.plan_id, "department_id": row.department_id, "access_mode": row.access_mode, "monthly_visit_limit": row.monthly_visit_limit, "advance_booking_days": row.advance_booking_days, "guest_allowed": row.guest_allowed}


@router.get("/department-plan-access")
def list_department_plan_access(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymDepartmentPlanAccess).where(GymDepartmentPlanAccess.company_id == company_id).order_by(GymDepartmentPlanAccess.plan_id, GymDepartmentPlanAccess.department_id)).all()
    return [{"id": r.id, "plan_id": r.plan_id, "plan": r.plan.code, "department_id": r.department_id, "department": r.department.code, "access_mode": r.access_mode, "monthly_visit_limit": r.monthly_visit_limit, "advance_booking_days": r.advance_booking_days, "guest_allowed": r.guest_allowed, "active": r.active} for r in rows]


class FacilityIn(BaseModel):
    company_id: int
    department_id: int
    code: str = Field(min_length=2, max_length=30)
    name_ar: str = Field(min_length=2, max_length=200)
    name_en: str = Field(min_length=2, max_length=200)
    facility_type: str
    capacity: int = Field(default=1, ge=1, le=10000)
    slot_minutes: int = Field(default=60, ge=15, le=1440)
    hourly_rate: Decimal = Field(default=0, ge=0)
    vat_rate: Decimal = Field(default=15, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_type(self):
        self.facility_type = self.facility_type.upper()
        if self.facility_type not in FACILITY_TYPES:
            raise ValueError("Unsupported facility type")
        return self


@router.post("/facilities", status_code=201)
def create_facility(data: FacilityIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.facilities.manage")
    _department(db, data.company_id, data.department_id)
    if db.scalar(select(GymFacility).where(GymFacility.department_id == data.department_id, GymFacility.code == data.code)):
        raise HTTPException(409, "Facility code already exists in department")
    row = GymFacility(**data.model_dump(), status="AVAILABLE", active=True, created_by=user.id)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "department_id": row.department_id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "facility_type": row.facility_type, "capacity": row.capacity, "slot_minutes": row.slot_minutes, "hourly_rate": row.hourly_rate, "vat_rate": row.vat_rate, "status": row.status}


@router.get("/facilities")
def list_facilities(company_id: int, department_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    query = select(GymFacility).where(GymFacility.company_id == company_id)
    if department_id is not None: query = query.where(GymFacility.department_id == department_id)
    rows = db.scalars(query.order_by(GymFacility.department_id, GymFacility.code)).all()
    return [{"id": r.id, "department_id": r.department_id, "department": r.department.code, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "facility_type": r.facility_type, "capacity": r.capacity, "slot_minutes": r.slot_minutes, "hourly_rate": r.hourly_rate, "vat_rate": r.vat_rate, "status": r.status, "active": r.active} for r in rows]


class FacilityStatusIn(BaseModel):
    status: str
    notes: str | None = Field(default=None, max_length=500)


@router.patch("/facilities/{facility_id}/status")
def update_facility_status(facility_id: int, data: FacilityStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymFacility).where(GymFacility.id == facility_id).with_for_update())
    if not row: raise HTTPException(404, "Facility not found")
    ensure_permission(db, user, row.company_id, "gym.facilities.manage")
    status = data.status.upper()
    if status not in {"AVAILABLE", "MAINTENANCE", "CLOSED"}: raise HTTPException(422, "Unsupported facility status")
    row.status = status; row.notes = data.notes
    db.commit(); return {"id": row.id, "status": row.status, "notes": row.notes}


class FacilityBookingIn(BaseModel):
    company_id: int
    facility_id: int
    starts_at: datetime
    ends_at: datetime
    participants: int = Field(default=1, ge=1, le=1000)
    member_id: int | None = None
    contract_id: int | None = None
    bank_account_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.contract_id and not self.member_id:
            raise ValueError("member_id is required with contract_id")
        return self


@router.post("/facility-bookings", status_code=201)
def create_facility_booking(data: FacilityBookingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.facilities.manage")
    facility = db.scalar(select(GymFacility).where(GymFacility.id == data.facility_id, GymFacility.company_id == data.company_id, GymFacility.active.is_(True)).with_for_update())
    if not facility: raise HTTPException(404, "Facility not found")
    if facility.status != "AVAILABLE": raise HTTPException(409, "Facility is not available")
    if data.participants > facility.capacity: raise HTTPException(422, "Participants exceed facility capacity")
    overlap = db.scalar(select(GymFacilityBooking.id).where(
        GymFacilityBooking.facility_id == facility.id,
        GymFacilityBooking.status.in_(["SUBMITTED", "CONFIRMED"]),
        GymFacilityBooking.starts_at < data.ends_at,
        GymFacilityBooking.ends_at > data.starts_at,
    ))
    if overlap: raise HTTPException(409, "Facility already booked for this time")
    access_mode = "PAY_PER_USE"
    contract = None
    if data.member_id is not None:
        member = db.scalar(select(Member).where(Member.id == data.member_id, Member.company_id == data.company_id, Member.active.is_(True)))
        if not member: raise HTTPException(404, "Member not found")
        contract = _valid_contract(db, data.company_id, member.id, facility.department.branch_id, data.starts_at.date(), data.contract_id)
        rule = _access_rule(db, data.company_id, contract.plan_id, facility.department_id)
        access_mode = rule.access_mode
        if data.starts_at.date() > date.today() and (data.starts_at.date() - date.today()).days > rule.advance_booking_days:
            raise HTTPException(409, "BOOKING_WINDOW_EXCEEDED")
    duration_hours = Decimal(str((data.ends_at - data.starts_at).total_seconds())) / Decimal("3600")
    net = Decimal("0") if access_mode == "INCLUDED" else money(Decimal(str(facility.hourly_rate)) * duration_hours)
    vat = money(net * Decimal(str(facility.vat_rate)) / Decimal("100")); total = money(net + vat)
    if total > 0 and not data.bank_account_id: raise HTTPException(422, "bank_account_id is required for paid booking")
    if data.bank_account_id:
        bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
        if not bank: raise HTTPException(404, "Bank account not found")
    row = GymFacilityBooking(
        company_id=data.company_id, number=_number(db, GymFacilityBooking, data.company_id, "GFB"),
        facility_id=facility.id, member_id=data.member_id, contract_id=contract.id if contract else None,
        starts_at=data.starts_at, ends_at=data.ends_at, participants=data.participants, access_mode=access_mode,
        net_amount=net, vat_amount=vat, total_amount=total, bank_account_id=data.bank_account_id,
        status="CONFIRMED" if total == 0 else "SUBMITTED", notes=data.notes, requested_by=user.id,
        approved_by=user.id if total == 0 else None, approved_at=utc_now() if total == 0 else None,
    )
    db.add(row); db.flush();
    write_audit(db, action="GYM_FACILITY_BOOKING_CREATED", entity_type="GYM_FACILITY_BOOKING", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": row.number, "facility_id": row.facility_id, "total": str(total), "status": row.status})
    db.commit(); return _booking_dict(row)


@router.post("/facility-bookings/{booking_id}/approve")
def approve_facility_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymFacilityBooking).where(GymFacilityBooking.id == booking_id).options(selectinload(GymFacilityBooking.facility).selectinload(GymFacility.department)).with_for_update())
    if not row: raise HTTPException(404, "Facility booking not found")
    ensure_permission(db, user, row.company_id, "gym.facilities.approve")
    if row.status != "SUBMITTED": raise HTTPException(409, "Booking is not awaiting approval")
    if row.requested_by == user.id: raise HTTPException(409, "Maker cannot approve own paid booking")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == row.bank_account_id, BankAccount.company_id == row.company_id, BankAccount.active.is_(True)))
    if not bank: raise HTTPException(404, "Bank account not found")
    output_vat = db.scalar(select(Account).where(Account.company_id == row.company_id, Account.code == "212010", Account.active.is_(True)))
    if not output_vat: raise HTTPException(422, "VAT output account not found")
    journal = create_posted_journal(
        db, company_id=row.company_id, user_id=user.id, posting_date=row.starts_at.date(), reference=row.number,
        description=f"Gym facility booking {row.number}",
        lines=[
            {"account_id": bank.gl_account_id, "debit": row.total_amount, "credit": 0, "branch_id": row.facility.department.branch_id, "cost_center_id": row.facility.department.cost_center_id},
            {"account_id": row.facility.department.revenue_account_id, "debit": 0, "credit": row.net_amount, "branch_id": row.facility.department.branch_id, "cost_center_id": row.facility.department.cost_center_id},
            {"account_id": output_vat.id, "debit": 0, "credit": row.vat_amount, "branch_id": row.facility.department.branch_id, "cost_center_id": row.facility.department.cost_center_id},
        ], cash_flow_activity="OPERATING", cash_flow_kind="CUSTOMER_RECEIPTS",
    )
    row.status = "CONFIRMED"; row.approved_by = user.id; row.approved_at = utc_now(); row.sale_journal_id = journal.id
    db.commit(); return _booking_dict(row)


class CancelBookingIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/facility-bookings/{booking_id}/cancel")
def cancel_facility_booking(booking_id: int, data: CancelBookingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymFacilityBooking).where(GymFacilityBooking.id == booking_id).options(selectinload(GymFacilityBooking.facility).selectinload(GymFacility.department)).with_for_update())
    if not row: raise HTTPException(404, "Facility booking not found")
    ensure_permission(db, user, row.company_id, "gym.facilities.approve")
    if row.status not in {"SUBMITTED", "CONFIRMED"}: raise HTTPException(409, "Booking cannot be cancelled")
    if row.starts_at <= utc_now(): raise HTTPException(409, "Started booking cannot be cancelled")
    if row.status == "CONFIRMED" and row.total_amount > 0:
        if row.requested_by == user.id: raise HTTPException(409, "Maker cannot approve own refund")
        bank = db.scalar(select(BankAccount).where(BankAccount.id == row.bank_account_id, BankAccount.company_id == row.company_id, BankAccount.active.is_(True)))
        output_vat = db.scalar(select(Account).where(Account.company_id == row.company_id, Account.code == "212010", Account.active.is_(True)))
        journal = create_posted_journal(
            db, company_id=row.company_id, user_id=user.id, posting_date=date.today(), reference=f"{row.number}-CANCEL",
            description=f"Gym facility booking refund {row.number}",
            lines=[
                {"account_id": row.facility.department.revenue_account_id, "debit": row.net_amount, "credit": 0, "branch_id": row.facility.department.branch_id, "cost_center_id": row.facility.department.cost_center_id},
                {"account_id": output_vat.id, "debit": row.vat_amount, "credit": 0, "branch_id": row.facility.department.branch_id, "cost_center_id": row.facility.department.cost_center_id},
                {"account_id": bank.gl_account_id, "debit": 0, "credit": row.total_amount, "branch_id": row.facility.department.branch_id, "cost_center_id": row.facility.department.cost_center_id},
            ], cash_flow_activity="OPERATING", cash_flow_kind="CUSTOMER_REFUNDS",
        )
        row.refund_journal_id = journal.id
    row.status = "CANCELLED"; row.cancelled_by = user.id; row.cancelled_at = utc_now(); row.cancellation_reason = data.reason
    db.commit(); return _booking_dict(row)


@router.get("/facility-bookings")
def list_facility_bookings(company_id: int, department_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    query = select(GymFacilityBooking).join(GymFacility).where(GymFacilityBooking.company_id == company_id)
    if department_id is not None: query = query.where(GymFacility.department_id == department_id)
    rows = db.scalars(query.options(selectinload(GymFacilityBooking.facility)).order_by(GymFacilityBooking.starts_at.desc())).all()
    return [_booking_dict(r) for r in rows]


class DepartmentAccessIn(BaseModel):
    company_id: int
    department_id: int
    member_id: int
    contract_id: int | None = None
    occurred_at: datetime
    direction: str = "IN"
    method: str = "QR"


@router.post("/department-access", status_code=201)
def capture_department_access(data: DepartmentAccessIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.access.capture")
    department = _department(db, data.company_id, data.department_id)
    status, reason, contract = "GRANTED", "ACCESS_INCLUDED", None
    try:
        contract = _valid_contract(db, data.company_id, data.member_id, department.branch_id, data.occurred_at.date(), data.contract_id)
        rule = _access_rule(db, data.company_id, contract.plan_id, department.id)
        if rule.monthly_visit_limit and data.direction.upper() == "IN":
            start = datetime(data.occurred_at.year, data.occurred_at.month, 1)
            end = datetime(data.occurred_at.year + (1 if data.occurred_at.month == 12 else 0), 1 if data.occurred_at.month == 12 else data.occurred_at.month + 1, 1)
            visits = db.scalar(select(func.count(GymDepartmentAccessRecord.id)).where(
                GymDepartmentAccessRecord.member_id == data.member_id,
                GymDepartmentAccessRecord.department_id == department.id,
                GymDepartmentAccessRecord.direction == "IN",
                GymDepartmentAccessRecord.status == "GRANTED",
                GymDepartmentAccessRecord.occurred_at >= start,
                GymDepartmentAccessRecord.occurred_at < end,
            )) or 0
            if visits >= rule.monthly_visit_limit:
                raise HTTPException(409, "MONTHLY_VISIT_LIMIT_REACHED")
        reason = rule.access_mode
    except HTTPException as exc:
        status, reason = "DENIED", str(exc.detail)
    row = GymDepartmentAccessRecord(company_id=data.company_id, department_id=department.id, member_id=data.member_id,
                                    contract_id=contract.id if contract else data.contract_id, occurred_at=data.occurred_at,
                                    direction=data.direction.upper(), method=data.method.upper(), status=status, reason=reason,
                                    recorded_by=user.id)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "department_id": row.department_id, "member_id": row.member_id, "contract_id": row.contract_id, "occurred_at": row.occurred_at, "direction": row.direction, "method": row.method, "status": row.status, "reason": row.reason}


@router.get("/department-access")
def list_department_access(company_id: int, department_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    query = select(GymDepartmentAccessRecord).where(GymDepartmentAccessRecord.company_id == company_id)
    if department_id is not None: query = query.where(GymDepartmentAccessRecord.department_id == department_id)
    rows = db.scalars(query.order_by(GymDepartmentAccessRecord.occurred_at.desc()).limit(300)).all()
    return [{"id": r.id, "department_id": r.department_id, "member_id": r.member_id, "contract_id": r.contract_id, "occurred_at": r.occurred_at, "direction": r.direction, "method": r.method, "status": r.status, "reason": r.reason} for r in rows]


class CafeProductIn(BaseModel):
    company_id: int
    branch_id: int
    department_id: int
    menu_item_id: int
    category: str
    product_type: str
    member_price: Decimal | None = Field(default=None, gt=0)
    calories: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)
    carbs_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)
    sugar_g: Decimal | None = Field(default=None, ge=0)
    caffeine_mg: Decimal | None = Field(default=None, ge=0)
    allergens: str | None = None
    is_healthy: bool = True

    @model_validator(mode="after")
    def validate_types(self):
        self.category = self.category.upper(); self.product_type = self.product_type.upper()
        if self.category not in CAFE_CATEGORIES: raise ValueError("Unsupported cafe category")
        if self.product_type not in CAFE_PRODUCT_TYPES: raise ValueError("Unsupported cafe product type")
        return self


@router.post("/cafe/products", status_code=201)
def create_cafe_product(data: CafeProductIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.cafe.manage")
    department = _department(db, data.company_id, data.department_id)
    if department.department_type != "CAFE": raise HTTPException(422, "Cafe product must belong to a CAFE department")
    if department.branch_id != data.branch_id: raise HTTPException(422, "Department and branch do not match")
    menu = db.scalar(select(MenuItem).where(MenuItem.id == data.menu_item_id, MenuItem.company_id == data.company_id, MenuItem.active.is_(True)))
    if not menu: raise HTTPException(404, "Menu item not found")
    if db.scalar(select(GymCafeProductProfile).where(GymCafeProductProfile.company_id == data.company_id, GymCafeProductProfile.branch_id == data.branch_id, GymCafeProductProfile.menu_item_id == data.menu_item_id)):
        raise HTTPException(409, "Cafe product already exists for branch")
    row = GymCafeProductProfile(**data.model_dump(), active=True, created_by=user.id)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "menu_item_id": row.menu_item_id, "code": row.menu_item.code, "name_ar": row.menu_item.name_ar, "name_en": row.menu_item.name_en, "category": row.category, "product_type": row.product_type, "selling_price": row.menu_item.selling_price, "member_price": row.member_price, "calories": row.calories, "protein_g": row.protein_g, "carbs_g": row.carbs_g, "fat_g": row.fat_g, "sugar_g": row.sugar_g, "caffeine_mg": row.caffeine_mg, "allergens": row.allergens, "is_healthy": row.is_healthy}


@router.get("/cafe/products")
def list_cafe_products(company_id: int, branch_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    query = select(GymCafeProductProfile).where(GymCafeProductProfile.company_id == company_id, GymCafeProductProfile.active.is_(True))
    if branch_id is not None: query = query.where(GymCafeProductProfile.branch_id == branch_id)
    rows = db.scalars(query.options(selectinload(GymCafeProductProfile.menu_item)).order_by(GymCafeProductProfile.category, GymCafeProductProfile.id)).all()
    return [{"id": r.id, "branch_id": r.branch_id, "department_id": r.department_id, "menu_item_id": r.menu_item_id, "code": r.menu_item.code, "name_ar": r.menu_item.name_ar, "name_en": r.menu_item.name_en, "category": r.category, "product_type": r.product_type, "selling_price": r.menu_item.selling_price, "member_price": r.member_price, "calories": r.calories, "protein_g": r.protein_g, "carbs_g": r.carbs_g, "fat_g": r.fat_g, "sugar_g": r.sugar_g, "caffeine_mg": r.caffeine_mg, "allergens": r.allergens, "is_healthy": r.is_healthy} for r in rows]


@router.get("/cafe/orders")
def list_cafe_orders(company_id: int, branch_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    query = select(PosOrder).where(PosOrder.company_id == company_id, PosOrder.business_unit == "GYM_CAFE")
    if branch_id is not None: query = query.where(PosOrder.branch_id == branch_id)
    rows = db.scalars(query.order_by(PosOrder.id.desc()).limit(300)).all()
    return [{"id": r.id, "number": r.number, "order_date": r.order_date, "branch_id": r.branch_id, "department_id": r.gym_department_id, "member_id": r.gym_member_id, "subtotal": r.subtotal, "vat_amount": r.vat_amount, "total": r.total, "food_cost": r.food_cost, "gross_profit": money(Decimal(str(r.subtotal)) - Decimal(str(r.food_cost))), "payment_channel": r.payment_channel, "status": r.status} for r in rows]


@router.get("/commercial-summary")
def commercial_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    departments = db.scalars(select(GymDepartment).where(GymDepartment.company_id == company_id, GymDepartment.active.is_(True)).where(branch_scope_condition(db, user, company_id, GymDepartment) if branch_scope_condition(db, user, company_id, GymDepartment) is not None else sa_true())).all()
    facilities = db.scalars(select(GymFacility).where(GymFacility.company_id == company_id, GymFacility.active.is_(True))).all()
    bookings = db.scalars(select(GymFacilityBooking).where(GymFacilityBooking.company_id == company_id)).all()
    cafe_orders = db.scalars(select(PosOrder).where(PosOrder.company_id == company_id, PosOrder.business_unit == "GYM_CAFE", PosOrder.status.notin_(["VOIDED", "REFUNDED"]))).all()
    cafe_sales = money(sum((Decimal(str(r.subtotal)) for r in cafe_orders), Decimal("0")))
    cafe_cost = money(sum((Decimal(str(r.food_cost)) for r in cafe_orders), Decimal("0")))
    facility_revenue = money(sum((Decimal(str(r.net_amount)) for r in bookings if r.status == "CONFIRMED"), Decimal("0")))
    denied = db.scalar(select(func.count(GymDepartmentAccessRecord.id)).where(GymDepartmentAccessRecord.company_id == company_id, GymDepartmentAccessRecord.status == "DENIED")) or 0
    by_type = {}
    for department in departments: by_type[department.department_type] = by_type.get(department.department_type, 0) + 1
    return {
        "departments": len(departments), "departments_by_type": by_type,
        "facilities": len(facilities), "available_facilities": sum(1 for f in facilities if f.status == "AVAILABLE"),
        "confirmed_bookings": sum(1 for b in bookings if b.status == "CONFIRMED"),
        "pending_paid_bookings": sum(1 for b in bookings if b.status == "SUBMITTED"),
        "facility_net_revenue": facility_revenue,
        "cafe_orders": len(cafe_orders), "cafe_net_sales": cafe_sales, "cafe_food_cost": cafe_cost,
        "cafe_gross_profit": money(cafe_sales - cafe_cost),
        "cafe_food_cost_percent": money(cafe_cost / cafe_sales * Decimal("100")) if cafe_sales else 0,
        "denied_department_access": denied,
    }
