from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import BankAccount, Branch, GymMemberLedger, GymMembershipState, Member, MembershipContract, MembershipPlan, RevenueSchedule, User
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/revenue-recognition", tags=["IFRS 15 and gym revenue"])


class MemberIn(BaseModel):
    company_id: int
    member_number: str
    name_ar: str
    name_en: str
    mobile: str | None = None


class PlanIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    duration_months: int = Field(ge=1, le=120)
    net_price: Decimal = Field(gt=0)
    vat_rate: Decimal = Field(ge=0, le=100, default=15)


class ContractIn(BaseModel):
    company_id: int
    member_id: int
    plan_id: int
    start_date: date
    bank_account_id: int
    branch_id: int | None = None


class RecognitionRunIn(BaseModel):
    company_id: int
    recognition_date: date


def add_months(source: date, months: int) -> date:
    month_index = source.month - 1 + months
    year = source.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_end(source: date) -> date:
    return date(source.year, source.month, calendar.monthrange(source.year, source.month)[1])


def _number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(MembershipContract.id)).where(MembershipContract.company_id == company_id)) or 0
    return f"MEM-{company_id}-{year}-{count + 1:05d}"


@router.post("/members", status_code=201)
def create_member(data: MemberIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.manage")
    if db.scalar(select(Member).where(Member.company_id == data.company_id, Member.member_number == data.member_number)):
        raise HTTPException(409, "Member number already exists")
    member = Member(**data.model_dump(), active=True)
    db.add(member); db.flush()
    write_audit(db, action="MEMBER_CREATED", entity_type="MEMBER", entity_id=member.id, user_id=user.id, company_id=data.company_id, after={"member_number":member.member_number})
    db.commit()
    return {"id":member.id,"member_number":member.member_number,"name_ar":member.name_ar,"name_en":member.name_en}


@router.get("/members")
def list_members(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "gym.read")
    rows = db.scalars(select(Member).where(Member.company_id==company_id,Member.active.is_(True)).order_by(Member.member_number)).all()
    return [{"id":r.id,"member_number":r.member_number,"name_ar":r.name_ar,"name_en":r.name_en,"mobile":r.mobile} for r in rows]


@router.post("/plans", status_code=201)
def create_plan(data: PlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "gym.manage")
    if db.scalar(select(MembershipPlan).where(MembershipPlan.company_id==data.company_id,MembershipPlan.code==data.code)):
        raise HTTPException(409,"Plan code already exists")
    plan=MembershipPlan(**data.model_dump(),active=True);db.add(plan);db.flush()
    write_audit(db,action="MEMBERSHIP_PLAN_CREATED",entity_type="MEMBERSHIP_PLAN",entity_id=plan.id,user_id=user.id,company_id=data.company_id,after={"code":plan.code,"duration_months":plan.duration_months,"net_price":str(plan.net_price)})
    db.commit();return {"id":plan.id,"code":plan.code,"duration_months":plan.duration_months,"net_price":plan.net_price,"vat_rate":plan.vat_rate}


@router.get("/plans")
def list_plans(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"gym.read")
    rows=db.scalars(select(MembershipPlan).where(MembershipPlan.company_id==company_id,MembershipPlan.active.is_(True)).order_by(MembershipPlan.code)).all()
    return [{"id":r.id,"code":r.code,"name_ar":r.name_ar,"name_en":r.name_en,"duration_months":r.duration_months,"net_price":r.net_price,"vat_rate":r.vat_rate} for r in rows]


@router.post("/contracts",status_code=201)
def create_contract(data:ContractIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,data.company_id,"gym.manage")
    member=db.scalar(select(Member).where(Member.id==data.member_id,Member.company_id==data.company_id,Member.active.is_(True)))
    plan=db.scalar(select(MembershipPlan).where(MembershipPlan.id==data.plan_id,MembershipPlan.company_id==data.company_id,MembershipPlan.active.is_(True)))
    bank=db.scalar(select(BankAccount).where(BankAccount.id==data.bank_account_id,BankAccount.company_id==data.company_id,BankAccount.active.is_(True)))
    branch=db.scalar(select(Branch).where(Branch.id==data.branch_id,Branch.company_id==data.company_id,Branch.active.is_(True))) if data.branch_id else None
    if not member:raise HTTPException(404,"Member not found")
    if not plan:raise HTTPException(404,"Plan not found")
    if not bank:raise HTTPException(404,"Bank account not found")
    if data.branch_id and not branch:raise HTTPException(404,"Branch not found")
    net=money(plan.net_price);vat=money(net*plan.vat_rate/Decimal("100"));total=money(net+vat)
    deferred=get_account(db,data.company_id,"213010");output_vat=get_account(db,data.company_id,"212010")
    number=_number(db,data.company_id,data.start_date.year)
    sale_journal=create_posted_journal(db,company_id=data.company_id,user_id=user.id,posting_date=data.start_date,reference=number,description=f"Membership sale {number}",lines=[{"account_id":bank.gl_account_id,"debit":total,"credit":0},{"account_id":deferred.id,"debit":0,"credit":net},{"account_id":output_vat.id,"debit":0,"credit":vat}],cash_flow_activity="OPERATING",cash_flow_kind="CUSTOMER_RECEIPTS")
    end_date=add_months(data.start_date,plan.duration_months)-timedelta(days=1)
    contract=MembershipContract(company_id=data.company_id,number=number,member_id=member.id,plan_id=plan.id,start_date=data.start_date,end_date=end_date,net_amount=net,vat_amount=vat,total_amount=total,status="ACTIVE",bank_account_id=bank.id,sale_journal_id=sale_journal.id,created_by=user.id)
    base=money(net/plan.duration_months);allocated=Decimal("0")
    for i in range(plan.duration_months):
        amount=base if i<plan.duration_months-1 else money(net-allocated)
        allocated+=amount
        recognition_date=month_end(add_months(data.start_date,i))
        contract.schedules.append(RevenueSchedule(period_number=i+1,recognition_date=recognition_date,amount=amount,status="PENDING"))
    db.add(contract);db.flush()
    db.add(GymMembershipState(company_id=data.company_id,contract_id=contract.id,branch_id=data.branch_id,original_end_date=end_date,total_frozen_days=0,refunded_net=0,refunded_vat=0,credit_balance=0))
    db.add(GymMemberLedger(company_id=data.company_id,member_id=member.id,contract_id=contract.id,transaction_date=data.start_date,transaction_type="MEMBERSHIP_SALE",reference=number,debit=total,credit=0,journal_id=sale_journal.id,created_by=user.id))
    db.add(GymMemberLedger(company_id=data.company_id,member_id=member.id,contract_id=contract.id,transaction_date=data.start_date,transaction_type="PAYMENT",reference=number,debit=0,credit=total,journal_id=sale_journal.id,bank_account_id=bank.id,created_by=user.id))
    write_audit(db,action="MEMBERSHIP_CONTRACT_ACTIVATED",entity_type="MEMBERSHIP_CONTRACT",entity_id=contract.id,user_id=user.id,company_id=data.company_id,after={"number":number,"net":str(net),"vat":str(vat),"schedule_periods":plan.duration_months,"journal":sale_journal.number,"branch_id":data.branch_id})
    db.commit();return {"id":contract.id,"number":contract.number,"status":contract.status,"branch_id":data.branch_id,"start_date":contract.start_date,"end_date":contract.end_date,"net_amount":contract.net_amount,"vat_amount":contract.vat_amount,"total_amount":contract.total_amount,"sale_journal":sale_journal.number,"schedule":[{"period":s.period_number,"date":s.recognition_date,"amount":s.amount,"status":s.status} for s in contract.schedules]}


@router.post("/recognize")
def run_recognition(data:RecognitionRunIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,data.company_id,"revenue.recognize")
    schedules=db.scalars(select(RevenueSchedule).join(MembershipContract).where(MembershipContract.company_id==data.company_id,MembershipContract.status=="ACTIVE",RevenueSchedule.status=="PENDING",RevenueSchedule.recognition_date<=data.recognition_date).options(selectinload(RevenueSchedule.contract))).all()
    deferred=get_account(db,data.company_id,"213010");revenue=get_account(db,data.company_id,"412010")
    recognized=[]
    for schedule in schedules:
        journal=create_posted_journal(db,company_id=data.company_id,user_id=user.id,posting_date=schedule.recognition_date,reference=schedule.contract.number,description=f"IFRS 15 revenue recognition {schedule.contract.number} period {schedule.period_number}",lines=[{"account_id":deferred.id,"debit":schedule.amount,"credit":0},{"account_id":revenue.id,"debit":0,"credit":schedule.amount}])
        schedule.status="RECOGNIZED";schedule.journal_id=journal.id;schedule.recognized_at=utc_now();recognized.append({"schedule_id":schedule.id,"contract":schedule.contract.number,"amount":schedule.amount,"journal":journal.number})
    write_audit(db,action="REVENUE_RECOGNITION_RUN",entity_type="REVENUE_SCHEDULE",entity_id="BATCH",user_id=user.id,company_id=data.company_id,after={"as_of":str(data.recognition_date),"recognized_count":len(recognized),"recognized_amount":str(sum((r["amount"] for r in recognized),Decimal("0")))})
    db.commit();return {"company_id":data.company_id,"as_of":data.recognition_date,"recognized_count":len(recognized),"recognized_amount":sum((r["amount"] for r in recognized),Decimal("0")),"entries":recognized}


@router.get("/contracts")
def list_contracts(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"gym.read")
    rows=db.scalars(select(MembershipContract).where(MembershipContract.company_id==company_id).options(selectinload(MembershipContract.schedules)).order_by(MembershipContract.id.desc())).all()
    return [{"id":r.id,"number":r.number,"member":r.member.name_en,"plan":r.plan.name_en,"start_date":r.start_date,"end_date":r.end_date,"status":r.status,"net_amount":r.net_amount,"recognized":sum((s.amount for s in r.schedules if s.status=="RECOGNIZED"),Decimal("0")),"deferred":sum((s.amount for s in r.schedules if s.status=="PENDING"),Decimal("0")),"schedule":[{"period":s.period_number,"date":s.recognition_date,"amount":s.amount,"status":s.status} for s in r.schedules]} for r in rows]


@router.get("/summary")
def revenue_summary(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"finance.read")
    contracts=db.scalars(select(MembershipContract).where(MembershipContract.company_id==company_id).options(selectinload(MembershipContract.schedules))).all()
    billed=sum((c.net_amount for c in contracts),Decimal("0"))
    recognized=sum((s.amount for c in contracts for s in c.schedules if s.status=="RECOGNIZED"),Decimal("0"))
    deferred=sum((s.amount for c in contracts for s in c.schedules if s.status=="PENDING"),Decimal("0"))
    from app.models.entities import GymMembershipModification
    refunded=db.scalar(select(func.coalesce(func.sum(GymMembershipModification.refund_net),0)).where(
        GymMembershipModification.company_id==company_id,
        GymMembershipModification.status=="APPROVED_POSTED",
        GymMembershipModification.modification_type.in_(["CANCEL","REFUND"]),
    )) or Decimal("0")
    return {"contracts":len(contracts),"billed_net":money(billed),"recognized_revenue":money(recognized),"deferred_revenue":money(deferred),"refunded_net":money(refunded),"reconciliation_difference":money(billed-recognized-deferred-refunded)}
