from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
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


def _schedule_out(row: LeaseSchedule) -> dict:
    return {
        "period": row.period_number,
        "date": row.period_end_date,
        "period_end_date": row.period_end_date,
        "cash_payment_date": row.cash_payment_date,
        "opening": row.opening_liability,
        "interest": row.interest,
        "payment": row.payment,
        "principal": row.principal,
        "closing": row.closing_liability,
        "depreciation": row.depreciation,
        "status": row.status,
        "accrual_status": row.accrual_status,
        "cash_status": row.cash_status,
    }


def _posted_liability(row: LeaseSchedule) -> Decimal:
    if row.payment and row.cash_status != "POSTED":
        return money(Decimal(row.opening_liability) + Decimal(row.interest))
    return money(row.closing_liability)


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
    monthly_rate = Decimal(data.annual_discount_rate) / Decimal("12")
    if timing == "ADVANCE":
        # The first instalment is paid at commencement (time zero) and belongs
        # in the ROU asset, not the lease liability.  Only later instalments
        # belong in the liability schedule.
        payment_months = list(range(frequency, months, frequency))
    else:
        payment_months = list(range(frequency, months + 1, frequency))
        if payment_months and payment_months[-1] < months:
            payment_months.append(months)
        elif not payment_months:
            payment_months = [months]
    advance_payment = money(data.payment_amount) if timing == "ADVANCE" else Decimal("0")
    cash_flows = [(month, money(data.payment_amount)) for month in payment_months]
    liability = money(sum((amount / ((Decimal("1") + monthly_rate) ** month) for month, amount in cash_flows), Decimal("0")))
    rou_asset = money(liability + advance_payment)

    rou = get_account(db, data.company_id, "152010")
    liability_account = get_account(db, data.company_id, "222010")
    initial_lines = [{"account_id": rou.id, "debit": rou_asset, "credit": 0}]
    if liability:
        initial_lines.append({"account_id": liability_account.id, "debit": 0, "credit": liability})
    if advance_payment:
        initial_lines.append({"account_id": bank.gl_account_id, "debit": 0, "credit": advance_payment})
    number = _number(db, data.company_id, data.commencement_date.year)
    initial_journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.commencement_date, reference=number, description=f"IFRS 16 initial recognition {number}", lines=initial_lines, cash_flow_activity="OPERATING" if advance_payment else None, cash_flow_kind="LEASE_PAYMENTS" if advance_payment else None)

    lease = LeaseContract(company_id=data.company_id, number=number, name_ar=data.name_ar, name_en=data.name_en, commencement_date=data.commencement_date, end_date=data.end_date, payment_amount=money(data.payment_amount), payment_frequency_months=frequency, payment_timing=timing, annual_discount_rate=data.annual_discount_rate, initial_liability=liability, initial_rou_asset=rou_asset, status="ACTIVE", bank_account_id=bank.id, initial_journal_id=initial_journal.id, created_by=user.id)
    opening = liability
    depreciation = money(rou_asset / months)
    for month in range(1, months + 1):
        interest = money(opening * monthly_rate)
        payment = money(data.payment_amount) if month in payment_months else Decimal("0")
        principal = money(payment - interest) if payment else Decimal("0")
        closing = money(opening + interest - payment)
        if payment and month == payment_months[-1] and abs(closing) <= Decimal("1.00"):
            # Keep contractual cash fixed and absorb the rounding residue into
            # the final interest/principal split.
            principal = money(opening)
            interest = money(payment - principal)
            closing = Decimal("0")
        period_end = month_end(add_months(data.commencement_date, month - 1))
        cash_payment_date = None
        if payment:
            cash_payment_date = period_end if timing == "ARREARS" else add_months(data.commencement_date, month)
        lease.schedules.append(
            LeaseSchedule(
                period_number=month,
                payment_date=period_end,
                period_end_date=period_end,
                cash_payment_date=cash_payment_date,
                opening_liability=opening,
                interest=interest,
                payment=payment,
                principal=principal,
                closing_liability=closing,
                depreciation=depreciation if month < months else money(rou_asset - depreciation * (months - 1)),
                status="PENDING",
                accrual_status="PENDING",
                cash_status="PENDING" if payment else "NOT_APPLICABLE",
            )
        )
        opening = closing
    db.add(lease); db.flush()
    write_audit(db, action="IFRS16_LEASE_CREATED", entity_type="LEASE_CONTRACT", entity_id=lease.id, user_id=user.id, company_id=data.company_id, after={"number":number,"liability":str(liability),"rou_asset":str(rou_asset),"months":months,"initial_journal":initial_journal.number})
    db.commit()
    return {"id":lease.id,"number":lease.number,"status":lease.status,"initial_liability":lease.initial_liability,"initial_rou_asset":lease.initial_rou_asset,"initial_journal":initial_journal.number,"schedule":[_schedule_out(s) for s in lease.schedules]}


@router.post("/post-schedules")
def post_schedules(data: LeaseRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "leases.post")
    rows = db.scalars(
        select(LeaseSchedule)
        .join(LeaseContract)
        .where(
            LeaseContract.company_id == data.company_id,
            LeaseContract.status == "ACTIVE",
            or_(
                and_(LeaseSchedule.accrual_status == "PENDING", LeaseSchedule.period_end_date <= data.as_of_date),
                and_(
                    LeaseSchedule.cash_status == "PENDING",
                    LeaseSchedule.cash_payment_date.is_not(None),
                    LeaseSchedule.cash_payment_date <= data.as_of_date,
                ),
            ),
        )
        .options(selectinload(LeaseSchedule.lease))
        .order_by(LeaseSchedule.period_end_date, LeaseSchedule.period_number)
    ).all()
    liability_account=get_account(db,data.company_id,"222010");interest_account=get_account(db,data.company_id,"711010");depreciation_account=get_account(db,data.company_id,"614010");accum_depr=get_account(db,data.company_id,"152020")
    posted=[]; journal_count=0
    for row in rows:
        bank=db.get(BankAccount,row.lease.bank_account_id)
        accrual_journal=None; cash_journal=None
        if row.accrual_status == "PENDING" and row.period_end_date <= data.as_of_date:
            accrual_journal=create_posted_journal(
                db,company_id=data.company_id,user_id=user.id,posting_date=row.period_end_date,
                reference=row.lease.number,
                description=f"IFRS 16 accrual {row.lease.number} period {row.period_number}",
                lines=[
                    {"account_id":interest_account.id,"debit":row.interest,"credit":0},
                    {"account_id":liability_account.id,"debit":0,"credit":row.interest},
                    {"account_id":depreciation_account.id,"debit":row.depreciation,"credit":0},
                    {"account_id":accum_depr.id,"debit":0,"credit":row.depreciation},
                ],
            )
            row.accrual_status="POSTED";row.accrual_journal_id=accrual_journal.id
            row.status="POSTED";row.journal_id=accrual_journal.id;journal_count+=1
        if row.cash_status == "PENDING" and row.cash_payment_date and row.cash_payment_date <= data.as_of_date:
            cash_journal=create_posted_journal(
                db,company_id=data.company_id,user_id=user.id,posting_date=row.cash_payment_date,
                reference=row.lease.number,
                description=f"IFRS 16 cash payment {row.lease.number} period {row.period_number}",
                lines=[
                    {"account_id":liability_account.id,"debit":row.payment,"credit":0},
                    {"account_id":bank.gl_account_id,"debit":0,"credit":row.payment},
                ],
                cash_flow_activity="FINANCING",cash_flow_kind="LEASE_PAYMENTS",
            )
            row.cash_status="POSTED";row.cash_journal_id=cash_journal.id;journal_count+=1
        posted.append({
            "schedule_id":row.id,"lease":row.lease.number,"period":row.period_number,
            "interest":row.interest,"payment":row.payment,"depreciation":row.depreciation,
            "period_end_date":row.period_end_date,"cash_payment_date":row.cash_payment_date,
            "accrual_journal":accrual_journal.number if accrual_journal else None,
            "cash_journal":cash_journal.number if cash_journal else None,
        })
    write_audit(db,action="IFRS16_SCHEDULE_RUN",entity_type="LEASE_SCHEDULE",entity_id="BATCH",user_id=user.id,company_id=data.company_id,after={"as_of":str(data.as_of_date),"posted_count":len(posted),"journal_count":journal_count})
    db.commit();return {"company_id":data.company_id,"as_of":data.as_of_date,"posted_count":len(posted),"journal_count":journal_count,"entries":posted}


@router.get("")
def list_leases(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"finance.read")
    rows=db.scalars(select(LeaseContract).where(LeaseContract.company_id==company_id).options(selectinload(LeaseContract.schedules)).order_by(LeaseContract.id.desc())).all()
    return [{"id":r.id,"number":r.number,"name_ar":r.name_ar,"name_en":r.name_en,"commencement_date":r.commencement_date,"end_date":r.end_date,"status":r.status,"initial_liability":r.initial_liability,"initial_rou_asset":r.initial_rou_asset,"posted_periods":sum(1 for s in r.schedules if s.accrual_status=="POSTED"),"remaining_liability":next((_posted_liability(s) for s in reversed(r.schedules) if s.accrual_status=="POSTED"),r.initial_liability),"schedule":[_schedule_out(s) for s in r.schedules]} for r in rows]


@router.get("/summary")
def lease_summary(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"finance.read")
    rows=db.scalars(select(LeaseContract).where(LeaseContract.company_id==company_id).options(selectinload(LeaseContract.schedules))).all()
    liability=Decimal("0");rou=Decimal("0");interest=Decimal("0");payments=Decimal("0");depreciation=Decimal("0")
    for lease in rows:
        rou+=lease.initial_rou_asset
        accrued=[s for s in lease.schedules if s.accrual_status=="POSTED"]
        liability+=_posted_liability(accrued[-1]) if accrued else lease.initial_liability
        interest+=sum((s.interest for s in accrued),Decimal("0"))
        payments+=sum((s.payment for s in lease.schedules if s.cash_status=="POSTED"),Decimal("0"))
        depreciation+=sum((s.depreciation for s in accrued),Decimal("0"))
    return {"active_leases":sum(1 for r in rows if r.status=="ACTIVE"),"lease_liability":money(liability),"gross_rou_asset":money(rou),"accumulated_depreciation":money(depreciation),"net_rou_asset":money(rou-depreciation),"interest_posted":money(interest),"payments_posted":money(payments)}
