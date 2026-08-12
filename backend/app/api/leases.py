from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import BankAccount, LeaseContract, LeaseSchedule, User
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/leases", tags=["IFRS 16 leases"])


class LeaseIn(BaseModel):
    company_id: int
    name_ar: str
    name_en: str
    commencement_date: date
    end_date: date
    payment_amount: Decimal = Field(gt=0)
    payment_frequency_months: int = Field(default=1, ge=1, le=12)
    payment_timing: str = "ARREARS"
    annual_discount_rate: Decimal = Field(ge=0, le=1)
    bank_account_id: int


class LeaseRunIn(BaseModel):
    company_id: int
    as_of_date: date


class LeaseOpeningValueIn(BaseModel):
    company_id: int
    opening_date: date
    lease_liability: Decimal = Field(gt=0)
    rou_asset: Decimal = Field(gt=0)


def add_months(source: date, months: int) -> date:
    index = source.month - 1 + months
    year = source.year + index // 12
    month = index % 12 + 1
    day = min(source.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_end(source: date) -> date:
    return date(source.year, source.month, calendar.monthrange(source.year, source.month)[1])


def months_between(start: date, end: date) -> int:
    value = (end.year - start.year) * 12 + end.month - start.month + 1
    return max(value, 1)


def _number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(LeaseContract.id)).where(LeaseContract.company_id == company_id)) or 0
    return f"LEASE-{company_id}-{year}-{count + 1:04d}"


@router.post("", status_code=201)
def create_lease(data: LeaseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "leases.manage")
    if data.end_date <= data.commencement_date:
        raise HTTPException(422, "Lease end date must be after commencement date")
    timing = data.payment_timing.upper()
    if timing not in {"ARREARS", "ADVANCE"}:
        raise HTTPException(422, "Payment timing must be ARREARS or ADVANCE")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not bank:
        raise HTTPException(404, "Bank account not found")

    months = months_between(data.commencement_date, data.end_date)
    frequency = data.payment_frequency_months
    monthly_rate = float(data.annual_discount_rate) / 12.0
    payment_months = list(range(frequency if timing == "ARREARS" else frequency, months + 1, frequency))
    if payment_months and payment_months[-1] < months:
        payment_months.append(months)
    elif not payment_months:
        payment_months = [months]
    advance_payment = money(data.payment_amount) if timing == "ADVANCE" else Decimal("0")
    cash_flows = [(month, money(data.payment_amount)) for month in payment_months]
    liability = money(sum((float(amount) / ((1 + monthly_rate) ** month) for month, amount in cash_flows), 0.0))
    rou_asset = money(liability + advance_payment)

    rou = get_account(db, data.company_id, "152010")
    liability_account = get_account(db, data.company_id, "222010")
    initial_lines = [{"account_id": rou.id, "debit": rou_asset, "credit": 0}, {"account_id": liability_account.id, "debit": 0, "credit": liability}]
    if advance_payment:
        initial_lines.append({"account_id": bank.gl_account_id, "debit": 0, "credit": advance_payment})
    number = _number(db, data.company_id, data.commencement_date.year)
    initial_journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.commencement_date, reference=number, description=f"IFRS 16 initial recognition {number}", lines=initial_lines, cash_flow_activity="OPERATING" if advance_payment else None, cash_flow_kind="LEASE_PAYMENTS" if advance_payment else None)

    lease = LeaseContract(company_id=data.company_id, number=number, name_ar=data.name_ar, name_en=data.name_en, commencement_date=data.commencement_date, end_date=data.end_date, payment_amount=money(data.payment_amount), payment_frequency_months=frequency, payment_timing=timing, annual_discount_rate=data.annual_discount_rate, initial_liability=liability, initial_rou_asset=rou_asset, status="ACTIVE", bank_account_id=bank.id, initial_journal_id=initial_journal.id, created_by=user.id)
    opening = liability
    depreciation = money(rou_asset / months)
    for month in range(1, months + 1):
        interest = money(opening * Decimal(str(monthly_rate)))
        payment = money(data.payment_amount) if month in payment_months else Decimal("0")
        principal = money(payment - interest) if payment else Decimal("0")
        closing = money(opening + interest - payment)
        if month == months and abs(closing) <= Decimal("1.00"):
            principal = money(principal + closing)
            payment = money(payment + closing)
            closing = Decimal("0")
        lease.schedules.append(LeaseSchedule(period_number=month, payment_date=month_end(add_months(data.commencement_date, month - 1)), opening_liability=opening, interest=interest, payment=payment, principal=principal, closing_liability=closing, depreciation=depreciation if month < months else money(rou_asset - depreciation * (months - 1)), status="PENDING"))
        opening = closing
    db.add(lease); db.flush()
    write_audit(db, action="IFRS16_LEASE_CREATED", entity_type="LEASE_CONTRACT", entity_id=lease.id, user_id=user.id, company_id=data.company_id, after={"number":number,"liability":str(liability),"rou_asset":str(rou_asset),"months":months,"initial_journal":initial_journal.number})
    db.commit()
    return {"id":lease.id,"number":lease.number,"status":lease.status,"initial_liability":lease.initial_liability,"initial_rou_asset":lease.initial_rou_asset,"initial_journal":initial_journal.number,"schedule":[{"period":s.period_number,"date":s.payment_date,"opening":s.opening_liability,"interest":s.interest,"payment":s.payment,"principal":s.principal,"closing":s.closing_liability,"depreciation":s.depreciation,"status":s.status} for s in lease.schedules]}


@router.post("/post-schedules")
def post_schedules(data: LeaseRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "leases.post")
    rows = db.scalars(select(LeaseSchedule).join(LeaseContract).where(LeaseContract.company_id==data.company_id,LeaseContract.status=="ACTIVE",LeaseSchedule.status=="PENDING",LeaseSchedule.payment_date<=data.as_of_date).options(selectinload(LeaseSchedule.lease))).all()
    liability_account=get_account(db,data.company_id,"222010");interest_account=get_account(db,data.company_id,"711010");depreciation_account=get_account(db,data.company_id,"614010");accum_depr=get_account(db,data.company_id,"152020")
    posted=[]
    for row in rows:
        bank=db.get(BankAccount,row.lease.bank_account_id)
        lines=[{"account_id":interest_account.id,"debit":row.interest,"credit":0},{"account_id":liability_account.id,"debit":0,"credit":row.interest},{"account_id":depreciation_account.id,"debit":row.depreciation,"credit":0},{"account_id":accum_depr.id,"debit":0,"credit":row.depreciation}]
        if row.payment:
            lines.extend([{"account_id":liability_account.id,"debit":row.payment,"credit":0},{"account_id":bank.gl_account_id,"debit":0,"credit":row.payment}])
        journal=create_posted_journal(db,company_id=data.company_id,user_id=user.id,posting_date=row.payment_date,reference=row.lease.number,description=f"IFRS 16 lease schedule {row.lease.number} period {row.period_number}",lines=lines,cash_flow_activity="FINANCING" if row.payment else None,cash_flow_kind="LEASE_PAYMENTS" if row.payment else None)
        row.status="POSTED";row.journal_id=journal.id;posted.append({"schedule_id":row.id,"lease":row.lease.number,"period":row.period_number,"interest":row.interest,"payment":row.payment,"depreciation":row.depreciation,"journal":journal.number})
    write_audit(db,action="IFRS16_SCHEDULE_RUN",entity_type="LEASE_SCHEDULE",entity_id="BATCH",user_id=user.id,company_id=data.company_id,after={"as_of":str(data.as_of_date),"posted_count":len(posted)})
    db.commit();return {"company_id":data.company_id,"as_of":data.as_of_date,"posted_count":len(posted),"entries":posted}


@router.post("/{lease_id}/initialize-opening-value")
def initialize_lease_opening_value(
    lease_id: int,
    data: LeaseOpeningValueIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restore the opening IFRS 16 value and future schedule of a preserved contract."""
    ensure_permission(db, user, data.company_id, "leases.manage")
    lease = db.scalar(
        select(LeaseContract)
        .where(LeaseContract.id == lease_id, LeaseContract.company_id == data.company_id)
        .options(selectinload(LeaseContract.schedules))
    )
    if not lease:
        raise HTTPException(404, "Lease contract not found")
    if lease.status != "DRAFT_UNVALUED" or lease.initial_journal_id is not None:
        raise HTTPException(409, "Only an unvalued preserved lease can receive an opening value")
    if data.opening_date < lease.commencement_date or data.opening_date > lease.end_date:
        raise HTTPException(422, "Opening date must be within the lease term")
    if lease.schedules:
        raise HTTPException(409, "Unvalued lease unexpectedly has schedule rows")

    liability = money(data.lease_liability)
    rou_asset = money(data.rou_asset)
    rou = get_account(db, data.company_id, "152010")
    liability_account = get_account(db, data.company_id, "222010")
    equity = get_account(db, data.company_id, "312010")
    lines = [
        {"account_id": rou.id, "debit": rou_asset, "credit": 0},
        {"account_id": liability_account.id, "debit": 0, "credit": liability},
    ]
    difference = money(rou_asset - liability)
    if difference > 0:
        lines.append({"account_id": equity.id, "debit": 0, "credit": difference})
    elif difference < 0:
        lines.append({"account_id": equity.id, "debit": abs(difference), "credit": 0})
    journal = create_posted_journal(
        db,
        company_id=data.company_id,
        user_id=user.id,
        posting_date=data.opening_date,
        reference=f"OPEN-{lease.number}",
        description=f"Opening value for preserved lease {lease.number}",
        lines=lines,
        cash_flow_kind="OPENING_BALANCE",
    )

    remaining_months = months_between(data.opening_date, lease.end_date)
    monthly_rate = Decimal(str(lease.annual_discount_rate)) / Decimal("12")
    frequency = int(lease.payment_frequency_months)
    opening = liability
    monthly_depreciation = money(rou_asset / Decimal(remaining_months))
    for period in range(1, remaining_months + 1):
        interest = money(opening * monthly_rate)
        scheduled_payment = money(lease.payment_amount) if period % frequency == 0 else Decimal("0")
        payment = money(opening + interest) if period == remaining_months else scheduled_payment
        principal = money(payment - interest) if payment else Decimal("0")
        closing = Decimal("0") if period == remaining_months else money(opening + interest - payment)
        depreciation = (
            money(rou_asset - monthly_depreciation * (remaining_months - 1))
            if period == remaining_months else monthly_depreciation
        )
        lease.schedules.append(
            LeaseSchedule(
                period_number=period,
                payment_date=month_end(add_months(data.opening_date, period - 1)),
                opening_liability=opening,
                interest=interest,
                payment=payment,
                principal=principal,
                closing_liability=closing,
                depreciation=depreciation,
                status="PENDING",
            )
        )
        opening = closing
    lease.initial_liability = liability
    lease.initial_rou_asset = rou_asset
    lease.initial_journal_id = journal.id
    lease.status = "ACTIVE"
    write_audit(
        db,
        action="LEASE_OPENING_VALUE_INITIALIZED",
        entity_type="LEASE_CONTRACT",
        entity_id=lease.id,
        user_id=user.id,
        company_id=data.company_id,
        after={
            "number": lease.number,
            "liability": str(liability),
            "rou_asset": str(rou_asset),
            "remaining_periods": remaining_months,
            "journal": journal.number,
        },
    )
    db.commit()
    return {
        "id": lease.id,
        "number": lease.number,
        "status": lease.status,
        "initial_liability": lease.initial_liability,
        "initial_rou_asset": lease.initial_rou_asset,
        "remaining_periods": remaining_months,
        "journal": journal.number,
    }


@router.get("")
def list_leases(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"finance.read")
    rows=db.scalars(select(LeaseContract).where(LeaseContract.company_id==company_id).options(selectinload(LeaseContract.schedules)).order_by(LeaseContract.id.desc())).all()
    return [{"id":r.id,"number":r.number,"name_ar":r.name_ar,"name_en":r.name_en,"commencement_date":r.commencement_date,"end_date":r.end_date,"status":r.status,"initial_liability":r.initial_liability,"initial_rou_asset":r.initial_rou_asset,"posted_periods":sum(1 for s in r.schedules if s.status=="POSTED"),"remaining_liability":next((s.closing_liability for s in reversed(r.schedules) if s.status=="POSTED"),r.initial_liability),"schedule":[{"period":s.period_number,"date":s.payment_date,"opening":s.opening_liability,"interest":s.interest,"payment":s.payment,"principal":s.principal,"closing":s.closing_liability,"depreciation":s.depreciation,"status":s.status} for s in r.schedules]} for r in rows]


@router.get("/summary")
def lease_summary(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"finance.read")
    rows=db.scalars(select(LeaseContract).where(LeaseContract.company_id==company_id).options(selectinload(LeaseContract.schedules))).all()
    liability=Decimal("0");rou=Decimal("0");interest=Decimal("0");payments=Decimal("0");depreciation=Decimal("0")
    for lease in rows:
        rou+=lease.initial_rou_asset
        posted=[s for s in lease.schedules if s.status=="POSTED"]
        liability+=posted[-1].closing_liability if posted else lease.initial_liability
        interest+=sum((s.interest for s in posted),Decimal("0"));payments+=sum((s.payment for s in posted),Decimal("0"));depreciation+=sum((s.depreciation for s in posted),Decimal("0"))
    return {"active_leases":sum(1 for r in rows if r.status=="ACTIVE"),"lease_liability":money(liability),"gross_rou_asset":money(rou),"accumulated_depreciation":money(depreciation),"net_rou_asset":money(rou-depreciation),"interest_posted":money(interest),"payments_posted":money(payments)}
