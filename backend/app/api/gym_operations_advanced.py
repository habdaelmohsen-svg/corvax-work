from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (
    BankAccount, Branch, GymAccessRecord, GymBranchTransfer, GymClassBooking, GymClassSession, GymDepartment, GymFacility,
    GymClassType, GymLocker, GymLockerAssignment, GymMemberLedger, GymMembershipModification,
    GymMembershipState, GymPTPackage, GymPTSale, GymPTSession, GymTrainer,
    GymTrainerCommissionBatch, GymTrainerCommissionLine, Member, MembershipContract, MembershipPlan,
    RevenueSchedule, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/gym", tags=["Gym operations RC14"])


def add_months(source: date, months: int) -> date:
    index = source.month - 1 + months
    year = source.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(source.day, calendar.monthrange(year, month)[1]))


def month_end(source: date) -> date:
    return date(source.year, source.month, calendar.monthrange(source.year, source.month)[1])


def _number(db: Session, model, company_id: int, prefix: str) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{date.today().year}-{count + 1:05d}"


def _contract(db: Session, company_id: int, contract_id: int) -> MembershipContract:
    row = db.scalar(
        select(MembershipContract)
        .where(MembershipContract.id == contract_id, MembershipContract.company_id == company_id)
        .options(selectinload(MembershipContract.schedules))
    )
    if not row:
        raise HTTPException(404, "Membership contract not found")
    return row


def _state(db: Session, contract: MembershipContract, branch_id: int | None = None) -> GymMembershipState:
    row = db.scalar(select(GymMembershipState).where(GymMembershipState.contract_id == contract.id))
    if row is None:
        row = GymMembershipState(
            company_id=contract.company_id,
            contract_id=contract.id,
            branch_id=branch_id,
            original_end_date=contract.end_date,
            total_frozen_days=0,
            refunded_net=0,
            refunded_vat=0,
            credit_balance=0,
        )
        db.add(row)
        db.flush()
    elif row.branch_id is None and branch_id is not None:
        row.branch_id = branch_id
    return row


def _recognized(contract: MembershipContract) -> Decimal:
    return money(sum((Decimal(str(s.amount)) for s in contract.schedules if s.status == "RECOGNIZED"), Decimal("0")))


def _pending(contract: MembershipContract) -> Decimal:
    return money(sum((Decimal(str(s.amount)) for s in contract.schedules if s.status == "PENDING"), Decimal("0")))


def _rebuild_schedule(db: Session, contract: MembershipContract, state: GymMembershipState, service_start: date) -> list[RevenueSchedule]:
    for row in contract.schedules:
        if row.status == "PENDING":
            row.status = "SUPERSEDED"
    recognized = _recognized(contract)
    remaining = money(Decimal(str(contract.net_amount)) - recognized - Decimal(str(state.refunded_net or 0)))
    if remaining <= 0 or service_start > contract.end_date or contract.status == "CANCELLED":
        return []
    dates: list[date] = []
    cursor = service_start
    while cursor <= contract.end_date:
        rec_date = min(month_end(cursor), contract.end_date)
        if not dates or dates[-1] != rec_date:
            dates.append(rec_date)
        cursor = add_months(date(cursor.year, cursor.month, 1), 1)
    if not dates:
        dates = [contract.end_date]
    base = money(remaining / len(dates))
    allocated = Decimal("0")
    next_period = max((s.period_number for s in contract.schedules), default=0) + 1
    created: list[RevenueSchedule] = []
    for index, recognition_date in enumerate(dates):
        amount = base if index < len(dates) - 1 else money(remaining - allocated)
        allocated += amount
        row = RevenueSchedule(
            period_number=next_period + index,
            recognition_date=recognition_date,
            amount=amount,
            status="PENDING",
        )
        contract.schedules.append(row)
        created.append(row)
    db.flush()
    return created


def _ledger(
    db: Session, *, company_id: int, member_id: int, contract_id: int | None, modification_id: int | None,
    transaction_date: date, transaction_type: str, reference: str, debit: Decimal = Decimal("0"),
    credit: Decimal = Decimal("0"), journal_id: int | None = None, bank_account_id: int | None = None,
    notes: str | None = None, user_id: int,
) -> GymMemberLedger:
    row = GymMemberLedger(
        company_id=company_id, member_id=member_id, contract_id=contract_id, modification_id=modification_id,
        transaction_date=transaction_date, transaction_type=transaction_type, reference=reference,
        debit=money(debit), credit=money(credit), journal_id=journal_id, bank_account_id=bank_account_id,
        notes=notes, created_by=user_id,
    )
    db.add(row)
    return row


def _member_balance(db: Session, company_id: int, member_id: int) -> Decimal:
    debit = db.scalar(select(func.coalesce(func.sum(GymMemberLedger.debit), 0)).where(
        GymMemberLedger.company_id == company_id, GymMemberLedger.member_id == member_id,
    )) or 0
    credit = db.scalar(select(func.coalesce(func.sum(GymMemberLedger.credit), 0)).where(
        GymMemberLedger.company_id == company_id, GymMemberLedger.member_id == member_id,
    )) or 0
    return money(Decimal(str(debit)) - Decimal(str(credit)))


def _validate_branch(db: Session, company_id: int, branch_id: int) -> Branch:
    row = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.company_id == company_id, Branch.active.is_(True)))
    if not row:
        raise HTTPException(404, "Branch not found")
    return row


def _active_contract_for_member(db: Session, company_id: int, member_id: int, on_date: date) -> MembershipContract | None:
    return db.scalar(
        select(MembershipContract)
        .where(
            MembershipContract.company_id == company_id,
            MembershipContract.member_id == member_id,
            MembershipContract.status.in_(["ACTIVE", "FROZEN"]),
            MembershipContract.start_date <= on_date,
            MembershipContract.end_date >= on_date,
        )
        .order_by(MembershipContract.id.desc())
        .options(selectinload(MembershipContract.schedules))
    )


def _contract_validity(db: Session, contract: MembershipContract, branch_id: int, on_date: date) -> tuple[bool, str, GymMembershipState]:
    state = _state(db, contract)
    if contract.status == "CANCELLED":
        return False, "MEMBERSHIP_CANCELLED", state
    if not (contract.start_date <= on_date <= contract.end_date):
        return False, "OUTSIDE_MEMBERSHIP_TERM", state
    if state.freeze_start and state.freeze_end and state.freeze_start <= on_date <= state.freeze_end:
        return False, "MEMBERSHIP_FROZEN", state
    if state.branch_id and state.branch_id != branch_id:
        return False, "WRONG_BRANCH", state
    if contract.status == "FROZEN" and (not state.freeze_end or on_date > state.freeze_end):
        contract.status = "ACTIVE"
    return True, "GRANTED", state


class ModificationIn(BaseModel):
    company_id: int
    contract_id: int
    modification_type: str
    effective_date: date
    freeze_start: date | None = None
    freeze_end: date | None = None
    extension_days: int = Field(default=0, ge=0, le=730)
    new_plan_id: int | None = None
    adjustment_net: Decimal = Field(default=0, ge=0)
    payment_method: str = "BANK"
    credit_used: Decimal = Field(default=0, ge=0)
    refund_net: Decimal | None = Field(default=None, ge=0)
    refund_method: str = "BANK"
    bank_account_id: int | None = None
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_type(self):
        self.modification_type = self.modification_type.upper()
        if self.modification_type not in {"FREEZE", "EXTENSION", "UPGRADE", "CANCEL", "REFUND"}:
            raise ValueError("Unsupported membership modification")
        if self.modification_type == "FREEZE" and (not self.freeze_start or not self.freeze_end or self.freeze_end < self.freeze_start):
            raise ValueError("Valid freeze_start and freeze_end are required")
        if self.modification_type == "EXTENSION" and self.extension_days <= 0:
            raise ValueError("extension_days must be positive")
        if self.modification_type == "UPGRADE" and not self.new_plan_id:
            raise ValueError("new_plan_id is required")
        self.payment_method = self.payment_method.upper()
        self.refund_method = self.refund_method.upper()
        if self.payment_method not in {"BANK", "CREDIT", "MIXED"}:
            raise ValueError("payment_method must be BANK, CREDIT or MIXED")
        if self.refund_method not in {"BANK", "CREDIT"}:
            raise ValueError("refund_method must be BANK or CREDIT")
        return self


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/membership-modifications", status_code=201)
def create_modification(data: ModificationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.memberships.manage")
    contract = _contract(db, data.company_id, data.contract_id)
    if contract.status == "CANCELLED":
        raise HTTPException(409, "Cancelled membership cannot be modified")
    if db.scalar(select(GymMembershipModification).where(
        GymMembershipModification.contract_id == contract.id,
        GymMembershipModification.status == "SUBMITTED",
    )):
        raise HTTPException(409, "A membership modification is already awaiting approval")
    state = _state(db, contract)
    plan = None
    adjustment_net = money(data.adjustment_net)
    if data.modification_type == "UPGRADE":
        plan = db.scalar(select(MembershipPlan).where(
            MembershipPlan.id == data.new_plan_id,
            MembershipPlan.company_id == data.company_id,
            MembershipPlan.active.is_(True),
        ))
        if not plan:
            raise HTTPException(404, "New membership plan not found")
        if adjustment_net == 0:
            adjustment_net = money(max(Decimal(str(plan.net_price)) - Decimal(str(contract.plan.net_price)), Decimal("0")))
    refundable = _pending(contract)
    refund_net = Decimal("0")
    if data.modification_type in {"CANCEL", "REFUND"}:
        refund_net = money(refundable if data.refund_net is None else data.refund_net)
        if refund_net > refundable:
            raise HTTPException(422, "Refund cannot exceed unrecognized deferred revenue")
    vat_rate = Decimal(str(contract.vat_amount)) / Decimal(str(contract.net_amount)) if Decimal(str(contract.net_amount)) else Decimal("0")
    adjustment_vat = money(adjustment_net * vat_rate)
    refund_vat = money(refund_net * vat_rate)
    available_credit = money(max(-_member_balance(db, data.company_id, contract.member_id), Decimal("0")))
    if data.credit_used > available_credit:
        raise HTTPException(422, "Credit used exceeds available member credit")
    cash_required = money(adjustment_net + adjustment_vat - data.credit_used)
    if (cash_required > 0 or (refund_net > 0 and data.refund_method == "BANK")) and not data.bank_account_id:
        raise HTTPException(422, "bank_account_id is required")
    if data.bank_account_id:
        bank = db.scalar(select(BankAccount).where(
            BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True),
        ))
        if not bank:
            raise HTTPException(404, "Bank account not found")
    row = GymMembershipModification(
        company_id=data.company_id, contract_id=contract.id,
        number=_number(db, GymMembershipModification, data.company_id, "GMM"),
        modification_type=data.modification_type, effective_date=data.effective_date,
        freeze_start=data.freeze_start, freeze_end=data.freeze_end, extension_days=data.extension_days,
        new_plan_id=data.new_plan_id, adjustment_net=adjustment_net, adjustment_vat=adjustment_vat,
        refund_net=refund_net, refund_vat=refund_vat, refund_total=money(refund_net + refund_vat),
        refund_method=data.refund_method, payment_method=data.payment_method, credit_used=money(data.credit_used),
        bank_account_id=data.bank_account_id, reason=data.reason, status="SUBMITTED", requested_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="GYM_MEMBERSHIP_MODIFICATION_SUBMITTED", entity_type="GYM_MEMBERSHIP_MODIFICATION", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"number": row.number, "type": row.modification_type, "contract": contract.number})
    db.commit()
    return _modification_dict(row)


def _modification_dict(row: GymMembershipModification) -> dict:
    return {
        "id": row.id, "number": row.number, "contract_id": row.contract_id, "contract_number": row.contract.number,
        "type": row.modification_type, "effective_date": row.effective_date, "freeze_start": row.freeze_start,
        "freeze_end": row.freeze_end, "extension_days": row.extension_days,
        "new_plan": row.new_plan.code if row.new_plan else None, "adjustment_net": row.adjustment_net,
        "adjustment_vat": row.adjustment_vat, "credit_used": row.credit_used, "refund_net": row.refund_net,
        "refund_vat": row.refund_vat, "refund_total": row.refund_total, "refund_method": row.refund_method,
        "status": row.status, "reason": row.reason,
    }


def _post_adjustment(db: Session, row: GymMembershipModification, contract: MembershipContract, state: GymMembershipState, user: User):
    total = money(Decimal(str(row.adjustment_net)) + Decimal(str(row.adjustment_vat)))
    if total <= 0:
        return None
    credit_used = money(row.credit_used or 0)
    cash = money(total - credit_used)
    available_credit = money(max(-_member_balance(db, row.company_id, contract.member_id), Decimal("0")))
    if credit_used > available_credit:
        raise HTTPException(422, "Insufficient member credit")
    deferred = get_account(db, row.company_id, "213010")
    vat = get_account(db, row.company_id, "212010")
    lines: list[dict] = []
    if cash > 0:
        bank = db.scalar(select(BankAccount).where(BankAccount.id == row.bank_account_id, BankAccount.company_id == row.company_id))
        if not bank:
            raise HTTPException(404, "Bank account not found")
        lines.append({"account_id": bank.gl_account_id, "debit": cash, "credit": 0})
    if credit_used > 0:
        member_credit = get_account(db, row.company_id, "213020")
        lines.append({"account_id": member_credit.id, "debit": credit_used, "credit": 0})
    lines.extend([
        {"account_id": deferred.id, "debit": 0, "credit": row.adjustment_net},
        {"account_id": vat.id, "debit": 0, "credit": row.adjustment_vat},
    ])
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.effective_date,
                                    reference=row.number, description=f"Gym membership modification {row.number}", lines=lines,
                                    cash_flow_activity="OPERATING" if cash > 0 else None,
                                    cash_flow_kind="CUSTOMER_RECEIPTS" if cash > 0 else None)
    if cash > 0:
        _ledger(db, company_id=row.company_id, member_id=contract.member_id, contract_id=contract.id, modification_id=row.id,
                transaction_date=row.effective_date, transaction_type="PAYMENT", reference=row.number,
                credit=cash, journal_id=journal.id, bank_account_id=row.bank_account_id, user_id=user.id)
    _ledger(db, company_id=row.company_id, member_id=contract.member_id, contract_id=contract.id, modification_id=row.id,
            transaction_date=row.effective_date, transaction_type="ADJUSTMENT_SALE", reference=row.number,
            debit=total, journal_id=journal.id, user_id=user.id)
    return journal


@router.post("/membership-modifications/{modification_id}/approve")
def approve_modification(modification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymMembershipModification).where(GymMembershipModification.id == modification_id).with_for_update())
    if not row:
        raise HTTPException(404, "Membership modification not found")
    ensure_permission(db, user, row.company_id, "gym.memberships.approve")
    if row.status != "SUBMITTED":
        raise HTTPException(409, "Modification is not awaiting approval")
    if row.requested_by == user.id:
        raise HTTPException(409, "Maker cannot approve own membership modification")
    contract = _contract(db, row.company_id, row.contract_id)
    state = _state(db, contract)
    journal = None
    if row.modification_type == "FREEZE":
        days = (row.freeze_end - row.freeze_start).days + 1
        state.freeze_start = row.freeze_start
        state.freeze_end = row.freeze_end
        state.total_frozen_days += days
        contract.end_date += timedelta(days=days)
        contract.status = "FROZEN" if row.freeze_start <= row.effective_date <= row.freeze_end else "ACTIVE"
        _rebuild_schedule(db, contract, state, row.freeze_end + timedelta(days=1))
    elif row.modification_type == "EXTENSION":
        journal = _post_adjustment(db, row, contract, state, user)
        contract.net_amount = money(Decimal(str(contract.net_amount)) + Decimal(str(row.adjustment_net)))
        contract.vat_amount = money(Decimal(str(contract.vat_amount)) + Decimal(str(row.adjustment_vat)))
        contract.total_amount = money(Decimal(str(contract.total_amount)) + Decimal(str(row.adjustment_net)) + Decimal(str(row.adjustment_vat)))
        contract.end_date += timedelta(days=row.extension_days)
        _rebuild_schedule(db, contract, state, row.effective_date)
    elif row.modification_type == "UPGRADE":
        journal = _post_adjustment(db, row, contract, state, user)
        contract.net_amount = money(Decimal(str(contract.net_amount)) + Decimal(str(row.adjustment_net)))
        contract.vat_amount = money(Decimal(str(contract.vat_amount)) + Decimal(str(row.adjustment_vat)))
        contract.total_amount = money(Decimal(str(contract.total_amount)) + Decimal(str(row.adjustment_net)) + Decimal(str(row.adjustment_vat)))
        contract.plan_id = row.new_plan_id
        upgraded_end = add_months(row.effective_date, row.new_plan.duration_months) - timedelta(days=1)
        if upgraded_end > contract.end_date:
            contract.end_date = upgraded_end
        _rebuild_schedule(db, contract, state, row.effective_date)
    else:
        refund_net = money(row.refund_net)
        refund_vat = money(row.refund_vat)
        refund_total = money(row.refund_total)
        for schedule in contract.schedules:
            if schedule.status == "PENDING":
                schedule.status = "CANCELLED"
        deferred = get_account(db, row.company_id, "213010")
        vat = get_account(db, row.company_id, "212010")
        if refund_total > 0:
            if row.refund_method == "BANK":
                bank = db.scalar(select(BankAccount).where(BankAccount.id == row.bank_account_id, BankAccount.company_id == row.company_id))
                if not bank:
                    raise HTTPException(404, "Bank account not found")
                credit_account_id = bank.gl_account_id
            else:
                credit_account_id = get_account(db, row.company_id, "213020").id
                state.credit_balance = money(Decimal(str(state.credit_balance or 0)) + refund_total)
            journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.effective_date,
                                            reference=row.number, description=f"Gym membership refund {row.number}",
                                            lines=[
                                                {"account_id": deferred.id, "debit": refund_net, "credit": 0},
                                                {"account_id": vat.id, "debit": refund_vat, "credit": 0},
                                                {"account_id": credit_account_id, "debit": 0, "credit": refund_total},
                                            ], cash_flow_activity="OPERATING" if row.refund_method == "BANK" else None,
                                            cash_flow_kind="CUSTOMER_REFUNDS" if row.refund_method == "BANK" else None)
            _ledger(db, company_id=row.company_id, member_id=contract.member_id, contract_id=contract.id, modification_id=row.id,
                    transaction_date=row.effective_date, transaction_type="CREDIT_NOTE", reference=row.number,
                    credit=refund_total, journal_id=journal.id, user_id=user.id)
            if row.refund_method == "BANK":
                _ledger(db, company_id=row.company_id, member_id=contract.member_id, contract_id=contract.id, modification_id=row.id,
                        transaction_date=row.effective_date, transaction_type="CASH_REFUND", reference=row.number,
                        debit=refund_total, journal_id=journal.id, bank_account_id=row.bank_account_id, user_id=user.id)
        state.refunded_net = money(Decimal(str(state.refunded_net or 0)) + refund_net)
        state.refunded_vat = money(Decimal(str(state.refunded_vat or 0)) + refund_vat)
        contract.end_date = min(contract.end_date, row.effective_date)
        contract.status = "CANCELLED"
    row.status = "APPROVED_POSTED"
    row.approved_by = user.id
    row.approved_at = utc_now()
    row.adjustment_journal_id = journal.id if journal and row.modification_type in {"EXTENSION", "UPGRADE"} else row.adjustment_journal_id
    row.refund_journal_id = journal.id if journal and row.modification_type in {"CANCEL", "REFUND"} else row.refund_journal_id
    state.last_modification_at = utc_now(); state.updated_at = utc_now()
    write_audit(db, action="GYM_MEMBERSHIP_MODIFICATION_APPROVED", entity_type="GYM_MEMBERSHIP_MODIFICATION", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"number": row.number, "type": row.modification_type, "status": row.status})
    db.commit()
    return _modification_dict(row)


@router.post("/membership-modifications/{modification_id}/reject")
def reject_modification(modification_id: int, data: RejectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymMembershipModification).where(GymMembershipModification.id == modification_id))
    if not row:
        raise HTTPException(404, "Membership modification not found")
    ensure_permission(db, user, row.company_id, "gym.memberships.approve")
    if row.status != "SUBMITTED":
        raise HTTPException(409, "Modification is not awaiting approval")
    if row.requested_by == user.id:
        raise HTTPException(409, "Maker cannot reject own membership modification")
    row.status = "REJECTED"; row.rejected_by = user.id; row.rejected_at = utc_now(); row.rejection_reason = data.reason
    write_audit(db, action="GYM_MEMBERSHIP_MODIFICATION_REJECTED", entity_type="GYM_MEMBERSHIP_MODIFICATION", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"reason": data.reason})
    db.commit(); return _modification_dict(row)


@router.get("/membership-modifications")
def list_modifications(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymMembershipModification).where(GymMembershipModification.company_id == company_id).order_by(GymMembershipModification.id.desc())).all()
    return [_modification_dict(row) for row in rows]


class TrainerIn(BaseModel):
    company_id: int
    branch_id: int
    department_id: int | None = None
    employee_id: int | None = None
    code: str
    name_ar: str
    name_en: str
    commission_rate: Decimal = Field(default=0, ge=0, le=100)


@router.post("/trainers", status_code=201)
def create_trainer(data: TrainerIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.pt.manage")
    _validate_branch(db, data.company_id, data.branch_id)
    if data.department_id is not None and not db.scalar(select(GymDepartment).where(GymDepartment.id == data.department_id, GymDepartment.company_id == data.company_id, GymDepartment.branch_id == data.branch_id, GymDepartment.active.is_(True))):
        raise HTTPException(404, "Gym department not found")
    if db.scalar(select(GymTrainer).where(GymTrainer.company_id == data.company_id, GymTrainer.code == data.code)):
        raise HTTPException(409, "Trainer code already exists")
    row = GymTrainer(**data.model_dump(), active=True); db.add(row); db.flush()
    write_audit(db, action="GYM_TRAINER_CREATED", entity_type="GYM_TRAINER", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code})
    db.commit(); return {"id": row.id, "department_id": row.department_id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "commission_rate": row.commission_rate}


@router.get("/trainers")
def list_trainers(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymTrainer).where(GymTrainer.company_id == company_id, GymTrainer.active.is_(True)).order_by(GymTrainer.code).where(branch_scope_condition(db, user, company_id, GymTrainer) if branch_scope_condition(db, user, company_id, GymTrainer) is not None else sa_true())).all()
    return [{"id": r.id, "branch_id": r.branch_id, "department_id": r.department_id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "commission_rate": r.commission_rate} for r in rows]


class ClassTypeIn(BaseModel):
    company_id: int
    department_id: int | None = None
    code: str
    name_ar: str
    name_en: str
    duration_minutes: int = Field(default=60, ge=15, le=240)
    default_capacity: int = Field(default=20, ge=1, le=500)


@router.post("/class-types", status_code=201)
def create_class_type(data: ClassTypeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.classes.manage")
    if data.department_id is not None and not db.scalar(select(GymDepartment).where(GymDepartment.id == data.department_id, GymDepartment.company_id == data.company_id, GymDepartment.active.is_(True))):
        raise HTTPException(404, "Gym department not found")
    if db.scalar(select(GymClassType).where(GymClassType.company_id == data.company_id, GymClassType.code == data.code)):
        raise HTTPException(409, "Class type code already exists")
    row = GymClassType(**data.model_dump(), active=True); db.add(row); db.flush(); db.commit()
    return {"id": row.id, "department_id": row.department_id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "duration_minutes": row.duration_minutes, "default_capacity": row.default_capacity}


@router.get("/class-types")
def list_class_types(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(
        select(GymClassType)
        .where(GymClassType.company_id == company_id, GymClassType.active.is_(True))
        .order_by(GymClassType.code)
    ).all()
    return [
        {
            "id": row.id,
            "department_id": row.department_id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "duration_minutes": row.duration_minutes,
            "default_capacity": row.default_capacity,
        }
        for row in rows
    ]


class ClassSessionIn(BaseModel):
    company_id: int
    branch_id: int
    class_type_id: int
    facility_id: int | None = None
    trainer_id: int | None = None
    starts_at: datetime
    capacity: int | None = Field(default=None, ge=1, le=500)
    waitlist_enabled: bool = True
    notes: str | None = None


@router.post("/class-sessions", status_code=201)
def create_class_session(data: ClassSessionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.classes.manage")
    _validate_branch(db, data.company_id, data.branch_id)
    class_type = db.scalar(select(GymClassType).where(GymClassType.id == data.class_type_id, GymClassType.company_id == data.company_id, GymClassType.active.is_(True)))
    if not class_type:
        raise HTTPException(404, "Class type not found")
    if data.trainer_id and not db.scalar(select(GymTrainer).where(GymTrainer.id == data.trainer_id, GymTrainer.company_id == data.company_id, GymTrainer.active.is_(True))):
        raise HTTPException(404, "Trainer not found")
    facility = None
    if data.facility_id is not None:
        facility = db.scalar(select(GymFacility).where(GymFacility.id == data.facility_id, GymFacility.company_id == data.company_id, GymFacility.active.is_(True), GymFacility.status == "AVAILABLE"))
        if not facility or facility.department.branch_id != data.branch_id:
            raise HTTPException(404, "Available facility not found in branch")
        if class_type.department_id and facility.department_id != class_type.department_id:
            raise HTTPException(422, "Class type and facility belong to different departments")
    ends_at = data.starts_at + timedelta(minutes=class_type.duration_minutes)
    if data.trainer_id and db.scalar(select(GymClassSession).where(
        GymClassSession.trainer_id == data.trainer_id, GymClassSession.status == "SCHEDULED",
        GymClassSession.starts_at < ends_at, GymClassSession.ends_at > data.starts_at,
    )):
        raise HTTPException(409, "Trainer already has an overlapping class")
    if facility and db.scalar(select(GymClassSession).where(GymClassSession.facility_id == facility.id, GymClassSession.status == "SCHEDULED", GymClassSession.starts_at < ends_at, GymClassSession.ends_at > data.starts_at)):
        raise HTTPException(409, "Facility already has an overlapping class")
    row = GymClassSession(company_id=data.company_id, branch_id=data.branch_id, class_type_id=data.class_type_id,
                          facility_id=data.facility_id, trainer_id=data.trainer_id, starts_at=data.starts_at, ends_at=ends_at,
                          capacity=data.capacity or class_type.default_capacity, waitlist_enabled=data.waitlist_enabled,
                          notes=data.notes, status="SCHEDULED", created_by=user.id)
    db.add(row); db.flush(); db.commit()
    return _class_session_dict(db, row)


def _class_session_dict(db: Session, row: GymClassSession) -> dict:
    booked = db.scalar(select(func.count(GymClassBooking.id)).where(GymClassBooking.session_id == row.id, GymClassBooking.status.in_(["BOOKED", "ATTENDED"]))) or 0
    waiting = db.scalar(select(func.count(GymClassBooking.id)).where(GymClassBooking.session_id == row.id, GymClassBooking.status == "WAITLISTED")) or 0
    return {"id": row.id, "branch_id": row.branch_id, "department_id": row.class_type.department_id, "facility_id": row.facility_id, "class_code": row.class_type.code, "class_name_ar": row.class_type.name_ar,
            "class_name_en": row.class_type.name_en, "trainer": row.trainer.name_en if row.trainer else None,
            "starts_at": row.starts_at, "ends_at": row.ends_at, "capacity": row.capacity, "booked": booked,
            "waiting": waiting, "available": max(row.capacity - booked, 0), "status": row.status}


@router.get("/class-sessions")
def list_class_sessions(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymClassSession).where(GymClassSession.company_id == company_id).order_by(GymClassSession.starts_at.desc()).where(branch_scope_condition(db, user, company_id, GymClassSession) if branch_scope_condition(db, user, company_id, GymClassSession) is not None else sa_true())).all()
    return [_class_session_dict(db, row) for row in rows]


class BookingIn(BaseModel):
    member_id: int
    contract_id: int


@router.post("/class-sessions/{session_id}/book", status_code=201)
def book_class(session_id: int, data: BookingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.scalar(select(GymClassSession).where(GymClassSession.id == session_id).with_for_update())
    if not session:
        raise HTTPException(404, "Class session not found")
    ensure_permission(db, user, session.company_id, "gym.bookings.manage")
    if session.status != "SCHEDULED":
        raise HTTPException(409, "Class session is not open for booking")
    contract = _contract(db, session.company_id, data.contract_id)
    if contract.member_id != data.member_id:
        raise HTTPException(422, "Contract does not belong to member")
    valid, reason, _ = _contract_validity(db, contract, session.branch_id, session.starts_at.date())
    if not valid:
        raise HTTPException(409, reason)
    if db.scalar(select(GymClassBooking).where(GymClassBooking.session_id == session.id, GymClassBooking.member_id == data.member_id)):
        raise HTTPException(409, "Member already booked or waitlisted")
    booked = db.scalar(select(func.count(GymClassBooking.id)).where(GymClassBooking.session_id == session.id, GymClassBooking.status.in_(["BOOKED", "ATTENDED"]))) or 0
    if booked < session.capacity:
        status, position = "BOOKED", None
    elif session.waitlist_enabled:
        status = "WAITLISTED"
        position = (db.scalar(select(func.max(GymClassBooking.waitlist_position)).where(GymClassBooking.session_id == session.id)) or 0) + 1
    else:
        raise HTTPException(409, "Class is full and waitlist is disabled")
    row = GymClassBooking(session_id=session.id, member_id=data.member_id, contract_id=contract.id, status=status,
                          waitlist_position=position, booked_by=user.id)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "session_id": row.session_id, "member_id": row.member_id, "status": row.status, "waitlist_position": row.waitlist_position}


def _promote_waitlist(db: Session, session_id: int) -> GymClassBooking | None:
    row = db.scalar(select(GymClassBooking).where(
        GymClassBooking.session_id == session_id, GymClassBooking.status == "WAITLISTED",
    ).order_by(GymClassBooking.waitlist_position, GymClassBooking.booked_at).with_for_update())
    if row:
        row.status = "BOOKED"; row.waitlist_position = None; row.promoted_at = utc_now()
    return row


@router.post("/class-bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymClassBooking).where(GymClassBooking.id == booking_id).with_for_update())
    if not row:
        raise HTTPException(404, "Class booking not found")
    ensure_permission(db, user, row.session.company_id, "gym.bookings.manage")
    if row.status not in {"BOOKED", "WAITLISTED"}:
        raise HTTPException(409, "Booking cannot be cancelled")
    was_booked = row.status == "BOOKED"
    row.status = "CANCELLED"; row.cancelled_at = utc_now(); row.waitlist_position = None
    promoted = _promote_waitlist(db, row.session_id) if was_booked else None
    db.commit()
    return {"id": row.id, "status": row.status, "promoted_booking_id": promoted.id if promoted else None}


class AttendanceIn(BaseModel):
    status: str = "ATTENDED"


@router.post("/class-bookings/{booking_id}/attendance")
def class_attendance(booking_id: int, data: AttendanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymClassBooking).where(GymClassBooking.id == booking_id))
    if not row:
        raise HTTPException(404, "Class booking not found")
    ensure_permission(db, user, row.session.company_id, "gym.classes.manage")
    status = data.status.upper()
    if status not in {"ATTENDED", "NO_SHOW"}:
        raise HTTPException(422, "Status must be ATTENDED or NO_SHOW")
    if row.status != "BOOKED":
        raise HTTPException(409, "Only booked members can be marked")
    row.status = status; row.checked_in_at = utc_now() if status == "ATTENDED" else None
    db.commit(); return {"id": row.id, "status": row.status}


class PTPackageIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    sessions_count: int = Field(ge=1, le=500)
    validity_days: int = Field(default=90, ge=1, le=730)
    net_price: Decimal = Field(gt=0)
    vat_rate: Decimal = Field(default=15, ge=0, le=100)


@router.post("/pt-packages", status_code=201)
def create_pt_package(data: PTPackageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.pt.manage")
    if db.scalar(select(GymPTPackage).where(GymPTPackage.company_id == data.company_id, GymPTPackage.code == data.code)):
        raise HTTPException(409, "PT package code already exists")
    row = GymPTPackage(**data.model_dump(), active=True); db.add(row); db.flush(); db.commit()
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "sessions_count": row.sessions_count, "validity_days": row.validity_days, "net_price": row.net_price, "vat_rate": row.vat_rate}


@router.get("/pt-packages")
def list_pt_packages(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(
        select(GymPTPackage)
        .where(GymPTPackage.company_id == company_id, GymPTPackage.active.is_(True))
        .order_by(GymPTPackage.code)
    ).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "sessions_count": row.sessions_count,
            "validity_days": row.validity_days,
            "net_price": row.net_price,
            "vat_rate": row.vat_rate,
        }
        for row in rows
    ]


class PTSaleIn(BaseModel):
    company_id: int
    branch_id: int
    member_id: int
    membership_contract_id: int | None = None
    package_id: int
    trainer_id: int
    bank_account_id: int
    sale_date: date


@router.post("/pt-sales", status_code=201)
def create_pt_sale(data: PTSaleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.pt.manage")
    _validate_branch(db, data.company_id, data.branch_id)
    member = db.scalar(select(Member).where(Member.id == data.member_id, Member.company_id == data.company_id, Member.active.is_(True)))
    package = db.scalar(select(GymPTPackage).where(GymPTPackage.id == data.package_id, GymPTPackage.company_id == data.company_id, GymPTPackage.active.is_(True)))
    trainer = db.scalar(select(GymTrainer).where(GymTrainer.id == data.trainer_id, GymTrainer.company_id == data.company_id, GymTrainer.active.is_(True)))
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not member: raise HTTPException(404, "Member not found")
    if not package: raise HTTPException(404, "PT package not found")
    if not trainer: raise HTTPException(404, "Trainer not found")
    if not bank: raise HTTPException(404, "Bank account not found")
    if data.membership_contract_id:
        contract = _contract(db, data.company_id, data.membership_contract_id)
        if contract.member_id != member.id: raise HTTPException(422, "Membership contract does not belong to member")
        valid, reason, _ = _contract_validity(db, contract, data.branch_id, data.sale_date)
        if not valid: raise HTTPException(409, reason)
    net = money(package.net_price); vat = money(net * Decimal(str(package.vat_rate)) / Decimal("100")); total = money(net + vat)
    deferred = get_account(db, data.company_id, "213010"); output_vat = get_account(db, data.company_id, "212010")
    number = _number(db, GymPTSale, data.company_id, "GPT")
    journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.sale_date,
                                    reference=number, description=f"PT package sale {number}",
                                    lines=[{"account_id": bank.gl_account_id, "debit": total, "credit": 0},
                                           {"account_id": deferred.id, "debit": 0, "credit": net},
                                           {"account_id": output_vat.id, "debit": 0, "credit": vat}],
                                    cash_flow_activity="OPERATING", cash_flow_kind="CUSTOMER_RECEIPTS")
    row = GymPTSale(company_id=data.company_id, branch_id=data.branch_id, member_id=member.id,
                    membership_contract_id=data.membership_contract_id, package_id=package.id, trainer_id=trainer.id,
                    bank_account_id=bank.id, number=number, sale_date=data.sale_date,
                    expiry_date=data.sale_date + timedelta(days=package.validity_days), sessions_total=package.sessions_count,
                    sessions_used=0, net_amount=net, vat_amount=vat, total_amount=total, deferred_balance=net,
                    status="ACTIVE", sale_journal_id=journal.id, created_by=user.id)
    db.add(row); db.flush()
    _ledger(db, company_id=data.company_id, member_id=member.id, contract_id=data.membership_contract_id, modification_id=None,
            transaction_date=data.sale_date, transaction_type="PT_SALE", reference=number, debit=total,
            journal_id=journal.id, user_id=user.id)
    _ledger(db, company_id=data.company_id, member_id=member.id, contract_id=data.membership_contract_id, modification_id=None,
            transaction_date=data.sale_date, transaction_type="PT_PAYMENT", reference=number, credit=total,
            journal_id=journal.id, bank_account_id=bank.id, user_id=user.id)
    db.commit(); return _pt_sale_dict(row)


def _pt_sale_dict(row: GymPTSale) -> dict:
    return {"id": row.id, "number": row.number, "member": row.member.name_en, "package": row.package.code,
            "trainer": row.trainer.name_en, "sale_date": row.sale_date, "expiry_date": row.expiry_date,
            "sessions_total": row.sessions_total, "sessions_used": row.sessions_used,
            "sessions_remaining": row.sessions_total - row.sessions_used, "net_amount": row.net_amount,
            "deferred_balance": row.deferred_balance, "status": row.status}


class PTSessionIn(BaseModel):
    pt_sale_id: int
    session_at: datetime
    notes: str | None = None


@router.post("/pt-sessions", status_code=201)
def create_pt_session(data: PTSessionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sale = db.scalar(select(GymPTSale).where(GymPTSale.id == data.pt_sale_id).with_for_update())
    if not sale: raise HTTPException(404, "PT sale not found")
    ensure_permission(db, user, sale.company_id, "gym.pt.manage")
    if sale.status != "ACTIVE" or sale.sessions_used >= sale.sessions_total:
        raise HTTPException(409, "PT package has no available sessions")
    if data.session_at.date() > sale.expiry_date:
        raise HTTPException(409, "PT package has expired")
    if db.scalar(select(GymPTSession).where(GymPTSession.trainer_id == sale.trainer_id, GymPTSession.status == "BOOKED",
                                            GymPTSession.session_at == data.session_at)):
        raise HTTPException(409, "Trainer already has a PT session at this time")
    row = GymPTSession(company_id=sale.company_id, pt_sale_id=sale.id, trainer_id=sale.trainer_id,
                       member_id=sale.member_id, branch_id=sale.branch_id, session_at=data.session_at,
                       status="BOOKED", booked_by=user.id, notes=data.notes)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "pt_sale_id": row.pt_sale_id, "session_at": row.session_at, "status": row.status}


@router.post("/pt-sessions/{session_id}/complete")
def complete_pt_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymPTSession).where(GymPTSession.id == session_id).with_for_update())
    if not row: raise HTTPException(404, "PT session not found")
    ensure_permission(db, user, row.company_id, "gym.pt.complete")
    if row.status != "BOOKED": raise HTTPException(409, "PT session is not booked")
    sale = row.sale
    if sale.sessions_used >= sale.sessions_total or Decimal(str(sale.deferred_balance)) <= 0:
        raise HTTPException(409, "PT package is fully consumed")
    remaining_sessions = sale.sessions_total - sale.sessions_used
    revenue = money(Decimal(str(sale.deferred_balance)) / remaining_sessions)
    commission = money(revenue * Decimal(str(row.trainer.commission_rate)) / Decimal("100"))
    deferred = get_account(db, row.company_id, "213010"); revenue_account = get_account(db, row.company_id, "412020")
    commission_expense = get_account(db, row.company_id, "625010"); commission_payable = get_account(db, row.company_id, "217020")
    revenue_journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.session_at.date(),
                                            reference=sale.number, description=f"PT session revenue {row.id}",
                                            lines=[{"account_id": deferred.id, "debit": revenue, "credit": 0},
                                                   {"account_id": revenue_account.id, "debit": 0, "credit": revenue}])
    commission_journal = None
    if commission > 0:
        commission_journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.session_at.date(),
                                                   reference=sale.number, description=f"Trainer commission accrual {row.id}",
                                                   lines=[{"account_id": commission_expense.id, "debit": commission, "credit": 0},
                                                          {"account_id": commission_payable.id, "debit": 0, "credit": commission}])
    row.status = "COMPLETED"; row.revenue_amount = revenue; row.commission_amount = commission
    row.commission_status = "ACCRUED" if commission > 0 else "NOT_APPLICABLE"
    row.revenue_journal_id = revenue_journal.id; row.commission_journal_id = commission_journal.id if commission_journal else None
    row.completed_by = user.id; row.completed_at = utc_now()
    sale.sessions_used += 1; sale.deferred_balance = money(Decimal(str(sale.deferred_balance)) - revenue)
    if sale.sessions_used >= sale.sessions_total:
        sale.status = "COMPLETED"; sale.deferred_balance = money(0)
    db.commit()
    return {"id": row.id, "status": row.status, "revenue_amount": row.revenue_amount,
            "commission_amount": row.commission_amount, "commission_status": row.commission_status,
            "sessions_used": sale.sessions_used, "deferred_balance": sale.deferred_balance}


class CommissionBatchIn(BaseModel):
    company_id: int
    trainer_id: int
    bank_account_id: int
    period_start: date
    period_end: date


@router.post("/commission-batches", status_code=201)
def create_commission_batch(data: CommissionBatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.commissions.review")
    trainer = db.scalar(select(GymTrainer).where(GymTrainer.id == data.trainer_id, GymTrainer.company_id == data.company_id))
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not trainer: raise HTTPException(404, "Trainer not found")
    if not bank: raise HTTPException(404, "Bank account not found")
    sessions = db.scalars(select(GymPTSession).where(
        GymPTSession.company_id == data.company_id, GymPTSession.trainer_id == data.trainer_id,
        GymPTSession.status == "COMPLETED", GymPTSession.commission_status == "ACCRUED",
        func.date(GymPTSession.session_at) >= data.period_start, func.date(GymPTSession.session_at) <= data.period_end,
    )).all()
    if not sessions: raise HTTPException(422, "No accrued commissions found for period")
    row = GymTrainerCommissionBatch(company_id=data.company_id, trainer_id=data.trainer_id, bank_account_id=data.bank_account_id,
                                    number=_number(db, GymTrainerCommissionBatch, data.company_id, "GCB"),
                                    period_start=data.period_start, period_end=data.period_end,
                                    total_amount=money(sum((Decimal(str(s.commission_amount)) for s in sessions), Decimal("0"))),
                                    status="DRAFT", prepared_by=user.id)
    for session in sessions:
        row.lines.append(GymTrainerCommissionLine(pt_session_id=session.id, amount=session.commission_amount))
        session.commission_status = "BATCHED"
    db.add(row); db.flush(); db.commit()
    return _commission_dict(row)


def _commission_dict(row: GymTrainerCommissionBatch) -> dict:
    return {"id": row.id, "number": row.number, "trainer": row.trainer.name_en,
            "period_start": row.period_start, "period_end": row.period_end, "total_amount": row.total_amount,
            "status": row.status, "sessions": len(row.lines)}


@router.post("/commission-batches/{batch_id}/review")
def review_commission_batch(batch_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymTrainerCommissionBatch).where(GymTrainerCommissionBatch.id == batch_id))
    if not row: raise HTTPException(404, "Commission batch not found")
    ensure_permission(db, user, row.company_id, "gym.commissions.review")
    if row.status != "DRAFT": raise HTTPException(409, "Commission batch is not draft")
    if row.prepared_by == user.id: raise HTTPException(409, "Preparer cannot review own commission batch")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit()
    return _commission_dict(row)


@router.post("/commission-batches/{batch_id}/approve")
def approve_commission_batch(batch_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymTrainerCommissionBatch).where(GymTrainerCommissionBatch.id == batch_id).options(selectinload(GymTrainerCommissionBatch.lines)).with_for_update())
    if not row: raise HTTPException(404, "Commission batch not found")
    ensure_permission(db, user, row.company_id, "gym.commissions.approve")
    if row.status != "REVIEWED": raise HTTPException(409, "Commission batch must be reviewed first")
    if user.id in {row.prepared_by, row.reviewed_by}: raise HTTPException(409, "Approver must be independent")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == row.bank_account_id, BankAccount.company_id == row.company_id))
    payable = get_account(db, row.company_id, "217020")
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.period_end,
                                    reference=row.number, description=f"Trainer commission payout {row.number}",
                                    lines=[{"account_id": payable.id, "debit": row.total_amount, "credit": 0},
                                           {"account_id": bank.gl_account_id, "debit": 0, "credit": row.total_amount}],
                                    cash_flow_activity="OPERATING", cash_flow_kind="EMPLOYEE_PAYMENTS")
    for line in row.lines:
        line.session.commission_status = "PAID"
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.payout_journal_id = journal.id
    db.commit(); return _commission_dict(row)


class AccessIn(BaseModel):
    company_id: int
    branch_id: int
    member_id: int
    occurred_at: datetime
    direction: str = "IN"
    method: str = "MANUAL"


@router.post("/access-records", status_code=201)
def record_access(data: AccessIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.access.capture")
    _validate_branch(db, data.company_id, data.branch_id)
    member = db.scalar(select(Member).where(Member.id == data.member_id, Member.company_id == data.company_id, Member.active.is_(True)))
    if not member: raise HTTPException(404, "Member not found")
    contract = _active_contract_for_member(db, data.company_id, data.member_id, data.occurred_at.date())
    if contract:
        granted, reason, _ = _contract_validity(db, contract, data.branch_id, data.occurred_at.date())
    else:
        granted, reason = False, "NO_ACTIVE_MEMBERSHIP"
    row = GymAccessRecord(company_id=data.company_id, branch_id=data.branch_id, member_id=data.member_id,
                          contract_id=contract.id if contract else None, occurred_at=data.occurred_at,
                          direction=data.direction.upper(), method=data.method.upper(), status="GRANTED" if granted else "DENIED",
                          reason=None if granted else reason, recorded_by=user.id)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "member_id": row.member_id, "contract_id": row.contract_id,
            "status": row.status, "reason": row.reason, "occurred_at": row.occurred_at}


class LockerIn(BaseModel):
    company_id: int
    branch_id: int
    code: str


@router.post("/lockers", status_code=201)
def create_locker(data: LockerIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.lockers.manage")
    _validate_branch(db, data.company_id, data.branch_id)
    if db.scalar(select(GymLocker).where(GymLocker.company_id == data.company_id, GymLocker.branch_id == data.branch_id, GymLocker.code == data.code)):
        raise HTTPException(409, "Locker code already exists")
    row = GymLocker(**data.model_dump(), status="AVAILABLE", active=True); db.add(row); db.flush(); db.commit()
    return {"id": row.id, "branch_id": row.branch_id, "code": row.code, "status": row.status}


class LockerAssignmentIn(BaseModel):
    locker_id: int
    member_id: int
    contract_id: int
    start_date: date
    end_date: date | None = None
    deposit_amount: Decimal = Field(default=0, ge=0)


@router.post("/locker-assignments", status_code=201)
def assign_locker(data: LockerAssignmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    locker = db.scalar(select(GymLocker).where(GymLocker.id == data.locker_id).with_for_update())
    if not locker: raise HTTPException(404, "Locker not found")
    ensure_permission(db, user, locker.company_id, "gym.lockers.manage")
    if locker.status != "AVAILABLE" or not locker.active: raise HTTPException(409, "Locker is not available")
    contract = _contract(db, locker.company_id, data.contract_id)
    if contract.member_id != data.member_id: raise HTTPException(422, "Contract does not belong to member")
    valid, reason, _ = _contract_validity(db, contract, locker.branch_id, data.start_date)
    if not valid: raise HTTPException(409, reason)
    row = GymLockerAssignment(company_id=locker.company_id, locker_id=locker.id, member_id=data.member_id,
                              contract_id=contract.id, start_date=data.start_date, end_date=data.end_date,
                              deposit_amount=money(data.deposit_amount), status="ACTIVE", assigned_by=user.id)
    locker.status = "ASSIGNED"; db.add(row); db.flush(); db.commit()
    return {"id": row.id, "locker_id": row.locker_id, "member_id": row.member_id, "status": row.status}


@router.post("/locker-assignments/{assignment_id}/release")
def release_locker(assignment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymLockerAssignment).where(GymLockerAssignment.id == assignment_id).with_for_update())
    if not row: raise HTTPException(404, "Locker assignment not found")
    ensure_permission(db, user, row.company_id, "gym.lockers.manage")
    if row.status != "ACTIVE": raise HTTPException(409, "Locker assignment is not active")
    row.status = "ENDED"; row.end_date = row.end_date or date.today(); row.released_by = user.id; row.released_at = utc_now(); row.locker.status = "AVAILABLE"
    db.commit(); return {"id": row.id, "status": row.status, "locker_status": row.locker.status}


class BranchTransferIn(BaseModel):
    company_id: int
    member_id: int
    contract_id: int
    to_branch_id: int
    transfer_date: date
    reason: str = Field(min_length=3, max_length=500)


@router.post("/branch-transfers", status_code=201)
def create_branch_transfer(data: BranchTransferIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.transfers.manage")
    contract = _contract(db, data.company_id, data.contract_id)
    if contract.member_id != data.member_id: raise HTTPException(422, "Contract does not belong to member")
    state = _state(db, contract)
    if not state.branch_id: raise HTTPException(422, "Membership branch is not assigned")
    _validate_branch(db, data.company_id, data.to_branch_id)
    if state.branch_id == data.to_branch_id: raise HTTPException(409, "Target branch is the current branch")
    row = GymBranchTransfer(company_id=data.company_id, member_id=data.member_id, contract_id=contract.id,
                            from_branch_id=state.branch_id, to_branch_id=data.to_branch_id,
                            number=_number(db, GymBranchTransfer, data.company_id, "GBT"),
                            transfer_date=data.transfer_date, reason=data.reason, status="SUBMITTED", requested_by=user.id)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "number": row.number, "from_branch_id": row.from_branch_id, "to_branch_id": row.to_branch_id, "status": row.status}


@router.post("/branch-transfers/{transfer_id}/approve")
def approve_branch_transfer(transfer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GymBranchTransfer).where(GymBranchTransfer.id == transfer_id).with_for_update())
    if not row: raise HTTPException(404, "Branch transfer not found")
    ensure_permission(db, user, row.company_id, "gym.transfers.approve")
    if row.status != "SUBMITTED": raise HTTPException(409, "Branch transfer is not awaiting approval")
    if row.requested_by == user.id: raise HTTPException(409, "Maker cannot approve own branch transfer")
    contract = _contract(db, row.company_id, row.contract_id); state = _state(db, contract)
    if state.branch_id != row.from_branch_id: raise HTTPException(409, "Membership branch changed after request")
    assignments = db.scalars(select(GymLockerAssignment).join(GymLocker).where(
        GymLockerAssignment.contract_id == contract.id, GymLockerAssignment.status == "ACTIVE",
        GymLocker.branch_id == row.from_branch_id,
    )).all()
    for assignment in assignments:
        assignment.status = "ENDED"; assignment.end_date = row.transfer_date; assignment.released_by = user.id; assignment.released_at = utc_now(); assignment.locker.status = "AVAILABLE"
    state.branch_id = row.to_branch_id; state.updated_at = utc_now()
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    db.commit(); return {"id": row.id, "number": row.number, "status": row.status, "released_lockers": len(assignments)}


@router.get("/member-ledger")
def member_ledger(company_id: int, member_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymMemberLedger).where(GymMemberLedger.company_id == company_id, GymMemberLedger.member_id == member_id).order_by(GymMemberLedger.transaction_date, GymMemberLedger.id)).all()
    running = Decimal("0"); result = []
    for row in rows:
        running = money(running + Decimal(str(row.debit)) - Decimal(str(row.credit)))
        result.append({"id": row.id, "date": row.transaction_date, "type": row.transaction_type, "reference": row.reference,
                       "debit": row.debit, "credit": row.credit, "balance": running, "notes": row.notes})
    return {"member_id": member_id, "balance": running, "credit_available": money(max(-running, Decimal("0"))), "transactions": result}


@router.get("/pt-sales")
def list_pt_sales(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymPTSale).where(GymPTSale.company_id == company_id).order_by(GymPTSale.id.desc()).where(branch_scope_condition(db, user, company_id, GymPTSale) if branch_scope_condition(db, user, company_id, GymPTSale) is not None else sa_true())).all()
    return [_pt_sale_dict(row) for row in rows]


@router.get("/access-records")
def list_access(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymAccessRecord).where(GymAccessRecord.company_id == company_id).order_by(GymAccessRecord.occurred_at.desc()).limit(200).where(branch_scope_condition(db, user, company_id, GymAccessRecord) if branch_scope_condition(db, user, company_id, GymAccessRecord) is not None else sa_true())).all()
    return [{"id": r.id, "branch_id": r.branch_id, "member_id": r.member_id, "contract_id": r.contract_id,
             "occurred_at": r.occurred_at, "direction": r.direction, "method": r.method, "status": r.status, "reason": r.reason} for r in rows]


@router.get("/lockers")
def list_lockers(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(GymLocker).where(GymLocker.company_id == company_id).order_by(GymLocker.branch_id, GymLocker.code).where(branch_scope_condition(db, user, company_id, GymLocker) if branch_scope_condition(db, user, company_id, GymLocker) is not None else sa_true())).all()
    return [{"id": r.id, "branch_id": r.branch_id, "code": r.code, "status": r.status, "active": r.active} for r in rows]


@router.get("/summary")
def gym_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    contracts = db.scalars(select(MembershipContract).where(MembershipContract.company_id == company_id).options(selectinload(MembershipContract.schedules))).all()
    active = sum(1 for c in contracts if c.status in {"ACTIVE", "FROZEN"})
    frozen = sum(1 for c in contracts if c.status == "FROZEN")
    recognized = money(sum((Decimal(str(s.amount)) for c in contracts for s in c.schedules if s.status == "RECOGNIZED"), Decimal("0")))
    deferred = money(sum((Decimal(str(s.amount)) for c in contracts for s in c.schedules if s.status == "PENDING"), Decimal("0")))
    classes = db.scalar(select(func.count(GymClassSession.id)).where(GymClassSession.company_id == company_id, GymClassSession.status == "SCHEDULED")) or 0
    waitlisted = db.scalar(select(func.count(GymClassBooking.id)).join(GymClassSession).where(GymClassSession.company_id == company_id, GymClassBooking.status == "WAITLISTED")) or 0
    pt_deferred = db.scalar(select(func.coalesce(func.sum(GymPTSale.deferred_balance), 0)).where(GymPTSale.company_id == company_id)) or 0
    commissions = db.scalar(select(func.coalesce(func.sum(GymPTSession.commission_amount), 0)).where(GymPTSession.company_id == company_id, GymPTSession.commission_status.in_(["ACCRUED", "BATCHED"]))) or 0
    denied = db.scalar(select(func.count(GymAccessRecord.id)).where(GymAccessRecord.company_id == company_id, GymAccessRecord.status == "DENIED")) or 0
    available_lockers = db.scalar(select(func.count(GymLocker.id)).where(GymLocker.company_id == company_id, GymLocker.status == "AVAILABLE", GymLocker.active.is_(True))) or 0
    pending_modifications = db.scalar(select(func.count(GymMembershipModification.id)).where(GymMembershipModification.company_id == company_id, GymMembershipModification.status == "SUBMITTED")) or 0
    return {"contracts": len(contracts), "active_memberships": active, "frozen_memberships": frozen,
            "recognized_membership_revenue": recognized, "deferred_membership_revenue": deferred,
            "scheduled_classes": classes, "waitlisted_bookings": waitlisted, "pt_deferred_revenue": money(pt_deferred),
            "unpaid_trainer_commissions": money(commissions), "denied_access_records": denied,
            "available_lockers": available_lockers, "pending_modifications": pending_modifications}
