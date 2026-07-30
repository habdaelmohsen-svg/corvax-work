from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, Company, ConsolidationGroup, ConsolidationLine, ConsolidationMember,
    ConsolidationRun, Currency, ExchangeRate, ForeignCurrencyBalance, FxRevaluationRun,
    JournalEntry, JournalLine, User, IntercompanyMatch, IntercompanyRecord, ConsolidationAdjustment,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/fx-consolidation", tags=["foreign currency and consolidation"])
Q = Decimal("0.01")


class RateIn(BaseModel):
    company_id: int
    currency_code: str = Field(min_length=3, max_length=3)
    rate_date: date
    rate: Decimal = Field(gt=0)
    source: str = "MANUAL"


class BalanceIn(BaseModel):
    company_id: int
    account_code: str
    currency_code: str = Field(min_length=3, max_length=3)
    foreign_amount: Decimal
    carrying_amount: Decimal
    last_rate: Decimal = Field(gt=0)


class RevaluationIn(BaseModel):
    company_id: int
    revaluation_date: date
    gain_account_code: str = "411010"
    loss_account_code: str = "613010"


class GroupIn(BaseModel):
    code: str
    name_ar: str
    name_en: str
    reporting_currency: str = "SAR"
    member_company_ids: list[int]


class ConsolidationIn(BaseModel):
    group_id: int
    period_end: date
    elimination_entries: list[dict] = []
    auto_eliminate_intercompany: bool = True


def _rate(db: Session, company_id: int, code: str, at: date) -> ExchangeRate:
    row = db.scalar(select(ExchangeRate).where(
        ExchangeRate.company_id == company_id,
        ExchangeRate.currency_code == code.upper(),
        ExchangeRate.rate_date <= at,
    ).order_by(ExchangeRate.rate_date.desc()))
    if not row:
        raise HTTPException(422, f"No exchange rate for {code} on or before {at}")
    return row


@router.get("/currencies")
def currencies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "active": r.active}
            for r in db.scalars(select(Currency).order_by(Currency.code)).all()]


@router.post("/rates", status_code=201)
def create_rate(data: RateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.manage_fx")
    code = data.currency_code.upper()
    if not db.get(Currency, code):
        db.add(Currency(code=code, name_ar=code, name_en=code))
        db.flush()
    row = db.scalar(select(ExchangeRate).where(
        ExchangeRate.company_id == data.company_id,
        ExchangeRate.currency_code == code,
        ExchangeRate.rate_date == data.rate_date,
    ))
    if row:
        row.rate, row.source, row.created_by = data.rate, data.source, user.id
    else:
        row = ExchangeRate(company_id=data.company_id, currency_code=code, rate_date=data.rate_date,
                           rate=data.rate, source=data.source, created_by=user.id)
        db.add(row)
    db.flush()
    write_audit(db, action="FX_RATE_SAVED", entity_type="EXCHANGE_RATE", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"currency": code, "rate": str(data.rate)})
    db.commit()
    return {"id": row.id, "currency_code": code, "rate": row.rate, "rate_date": row.rate_date}


@router.get("/rates")
def list_rates(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(select(ExchangeRate).where(ExchangeRate.company_id == company_id)
                      .order_by(ExchangeRate.rate_date.desc(), ExchangeRate.currency_code)).all()
    return [{"id": r.id, "currency_code": r.currency_code, "rate_date": r.rate_date,
             "rate": r.rate, "source": r.source} for r in rows]


@router.post("/balances", status_code=201)
def save_balance(data: BalanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.manage_fx")
    account = db.scalar(select(Account).where(Account.company_id == data.company_id, Account.code == data.account_code))
    if not account:
        raise HTTPException(422, "Unknown account")
    code = data.currency_code.upper()
    row = db.scalar(select(ForeignCurrencyBalance).where(
        ForeignCurrencyBalance.company_id == data.company_id,
        ForeignCurrencyBalance.account_id == account.id,
        ForeignCurrencyBalance.currency_code == code,
    ))
    if row:
        before = {"foreign_amount": str(row.foreign_amount), "carrying_amount": str(row.carrying_amount)}
        row.foreign_amount, row.carrying_amount, row.last_rate = data.foreign_amount, data.carrying_amount, data.last_rate
        row.updated_at = utc_now()
    else:
        before = None
        row = ForeignCurrencyBalance(company_id=data.company_id, account_id=account.id,
                                     currency_code=code, foreign_amount=data.foreign_amount,
                                     carrying_amount=data.carrying_amount, last_rate=data.last_rate)
        db.add(row)
    db.flush()
    write_audit(db, action="FX_BALANCE_SAVED", entity_type="FX_BALANCE", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, before=before,
                after={"account": data.account_code, "currency": code, "foreign_amount": str(data.foreign_amount)})
    db.commit()
    return {"id": row.id, "account_code": account.code, "currency_code": code,
            "foreign_amount": row.foreign_amount, "carrying_amount": row.carrying_amount}


@router.post("/revaluations", status_code=201)
def revalue(data: RevaluationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.manage_fx")
    balances = db.scalars(select(ForeignCurrencyBalance).where(ForeignCurrencyBalance.company_id == data.company_id)).all()
    if not balances:
        raise HTTPException(422, "No foreign currency balances")
    gain_acc = db.scalar(select(Account).where(Account.company_id == data.company_id, Account.code == data.gain_account_code))
    loss_acc = db.scalar(select(Account).where(Account.company_id == data.company_id, Account.code == data.loss_account_code))
    if not gain_acc or not loss_acc:
        raise HTTPException(422, "FX gain/loss accounts are missing")
    lines: list[JournalLine] = []
    total_gain = Decimal("0"); total_loss = Decimal("0")
    details = []
    for bal in balances:
        rate = _rate(db, data.company_id, bal.currency_code, data.revaluation_date)
        translated = (Decimal(bal.foreign_amount) * Decimal(rate.rate)).quantize(Q, rounding=ROUND_HALF_UP)
        difference = (translated - Decimal(bal.carrying_amount)).quantize(Q)
        if difference == 0:
            continue
        if difference > 0:
            lines += [JournalLine(account_id=bal.account_id, debit=difference, credit=0, description="FX revaluation"),
                      JournalLine(account_id=gain_acc.id, debit=0, credit=difference, description="Unrealized FX gain")]
            total_gain += difference
        else:
            amount = abs(difference)
            lines += [JournalLine(account_id=loss_acc.id, debit=amount, credit=0, description="Unrealized FX loss"),
                      JournalLine(account_id=bal.account_id, debit=0, credit=amount, description="FX revaluation")]
            total_loss += amount
        details.append({"account": bal.account.code, "currency": bal.currency_code,
                        "old": str(bal.carrying_amount), "new": str(translated), "difference": str(difference)})
        bal.carrying_amount, bal.last_rate, bal.updated_at = translated, rate.rate, utc_now()
    if not lines:
        raise HTTPException(422, "No revaluation difference")
    total = total_gain + total_loss
    count = db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.company_id == data.company_id)) or 0
    journal = JournalEntry(company_id=data.company_id, number=f"FX-{data.company_id}-{data.revaluation_date.year}-{count+1:06d}",
                           entry_date=data.revaluation_date, reference="FX-REVALUATION",
                           description=f"Foreign currency revaluation {data.revaluation_date}", status="POSTED",
                           entry_origin="FX",
                           total_debit=total, total_credit=total, created_by=user.id, approved_by=user.id,
                           posted_by=user.id, approved_at=utc_now(), posted_at=utc_now(), lines=lines)
    db.add(journal); db.flush()
    run = FxRevaluationRun(company_id=data.company_id, revaluation_date=data.revaluation_date,
                           status="POSTED", total_gain=total_gain, total_loss=total_loss,
                           journal_id=journal.id, created_by=user.id)
    db.add(run); db.flush()
    write_audit(db, action="FX_REVALUATION_POSTED", entity_type="FX_REVALUATION", entity_id=run.id,
                user_id=user.id, company_id=data.company_id,
                after={"gain": str(total_gain), "loss": str(total_loss), "journal_id": journal.id, "details": details})
    db.commit()
    return {"id": run.id, "journal_id": journal.id, "total_gain": total_gain,
            "total_loss": total_loss, "details": details}


@router.post("/groups", status_code=201)
def create_group(data: GroupIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    companies = db.scalars(select(Company).where(Company.id.in_(data.member_company_ids))).all()
    if len(companies) != len(set(data.member_company_ids)):
        raise HTTPException(422, "One or more companies do not exist")
    for company in companies:
        ensure_permission(db, user, company.id, "consolidation.manage")
    group = ConsolidationGroup(code=data.code, name_ar=data.name_ar, name_en=data.name_en,
                               reporting_currency=data.reporting_currency.upper())
    db.add(group); db.flush()
    for company in companies:
        db.add(ConsolidationMember(group_id=group.id, company_id=company.id,
                                   ownership_percent=100, effective_date=date.today()))
    write_audit(db, action="CONSOLIDATION_GROUP_CREATED", entity_type="CONSOLIDATION_GROUP",
                entity_id=group.id, user_id=user.id, after={"code": data.code, "members": data.member_company_ids})
    db.commit()
    return {"id": group.id, "code": group.code, "member_company_ids": data.member_company_ids}


@router.post("/runs", status_code=201)
def run_consolidation(data: ConsolidationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.get(ConsolidationGroup, data.group_id)
    if not group:
        raise HTTPException(404, "Consolidation group not found")
    members = db.scalars(select(ConsolidationMember).where(ConsolidationMember.group_id == group.id)).all()
    if not members:
        raise HTTPException(422, "Consolidation group has no members")
    company_ids = [m.company_id for m in members]
    for cid in company_ids:
        ensure_permission(db, user, cid, "consolidation.manage")
    rows = db.execute(select(
        Account.code, func.max(Account.name_ar), func.max(Account.name_en),
        func.sum(JournalLine.debit), func.sum(JournalLine.credit),
    ).join(JournalLine, JournalLine.account_id == Account.id)
     .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
     .where(Account.company_id.in_(company_ids), JournalEntry.status.in_(("POSTED", "REVERSED")),
            JournalEntry.entry_date <= data.period_end)
     .group_by(Account.code).order_by(Account.code)).all()
    run = ConsolidationRun(group_id=group.id, period_end=data.period_end, created_by=user.id)
    db.add(run); db.flush()
    total_debit = Decimal("0"); total_credit = Decimal("0")
    for code, ar, en, debit, credit in rows:
        d, c = Decimal(debit or 0).quantize(Q), Decimal(credit or 0).quantize(Q)
        db.add(ConsolidationLine(run_id=run.id, account_code=code, account_name_ar=ar,
                                 account_name_en=en, debit=d, credit=c))
        total_debit += d; total_credit += c
    elimination_amount = Decimal("0")
    if data.auto_eliminate_intercompany:
        matches = db.scalars(select(IntercompanyMatch).where(IntercompanyMatch.status == "MATCHED")).all()
        for match in matches:
            a = db.get(IntercompanyRecord, match.record_a_id)
            b = db.get(IntercompanyRecord, match.record_b_id)
            if not a or not b or a.transaction_date > data.period_end or b.transaction_date > data.period_end:
                continue
            if a.company_id not in company_ids or b.company_id not in company_ids:
                continue
            pair = {a.direction, b.direction}
            amount = Decimal(match.matched_amount).quantize(Q)
            if pair == {"RECEIVABLE", "PAYABLE"}:
                debit_code = a.account_code if a.direction == "PAYABLE" else b.account_code
                credit_code = a.account_code if a.direction == "RECEIVABLE" else b.account_code
            elif pair == {"REVENUE", "EXPENSE"}:
                debit_code = a.account_code if a.direction == "REVENUE" else b.account_code
                credit_code = a.account_code if a.direction == "EXPENSE" else b.account_code
            else:
                continue
            db.add(ConsolidationLine(run_id=run.id, account_code=debit_code,
                                     account_name_ar="استبعاد معاملات بين الشركات",
                                     account_name_en="Intercompany elimination",
                                     debit=amount, credit=0, is_elimination=True))
            db.add(ConsolidationLine(run_id=run.id, account_code=credit_code,
                                     account_name_ar="استبعاد معاملات بين الشركات",
                                     account_name_en="Intercompany elimination",
                                     debit=0, credit=amount, is_elimination=True))
            db.add(ConsolidationAdjustment(run_id=run.id, adjustment_type="INTERCOMPANY",
                                           reference=f"IC-MATCH-{match.id}",
                                           debit_account_code=debit_code, credit_account_code=credit_code,
                                           amount=amount, source_match_id=match.id, created_by=user.id))
            total_debit += amount; total_credit += amount; elimination_amount += amount
    for item in data.elimination_entries:
        code = str(item.get("account_code", "ELIM")); debit = Decimal(str(item.get("debit", 0))).quantize(Q)
        credit = Decimal(str(item.get("credit", 0))).quantize(Q)
        db.add(ConsolidationLine(run_id=run.id, account_code=code,
                                 account_name_ar=str(item.get("name_ar", "قيد استبعاد")),
                                 account_name_en=str(item.get("name_en", "Elimination entry")),
                                 debit=debit, credit=credit, is_elimination=True))
        total_debit += debit; total_credit += credit; elimination_amount += max(debit, credit)
    if total_debit != total_credit:
        raise HTTPException(422, f"Consolidation is not balanced: {total_debit} != {total_credit}")
    run.total_debit, run.total_credit, run.elimination_amount = total_debit, total_credit, elimination_amount
    write_audit(db, action="CONSOLIDATION_RUN_COMPLETED", entity_type="CONSOLIDATION_RUN",
                entity_id=run.id, user_id=user.id,
                after={"group": group.code, "period_end": str(data.period_end), "total": str(total_debit)})
    db.commit()
    return {"id": run.id, "group": group.code, "period_end": run.period_end,
            "total_debit": run.total_debit, "total_credit": run.total_credit,
            "elimination_amount": run.elimination_amount, "line_count": len(rows)+len(data.elimination_entries), "auto_intercompany": data.auto_eliminate_intercompany}


@router.get("/runs/{run_id}")
def read_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(ConsolidationRun, run_id)
    if not run:
        raise HTTPException(404, "Consolidation run not found")
    members = db.scalars(select(ConsolidationMember).where(ConsolidationMember.group_id == run.group_id)).all()
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.read")
    lines = db.scalars(select(ConsolidationLine).where(ConsolidationLine.run_id == run.id)
                       .order_by(ConsolidationLine.account_code)).all()
    return {"id": run.id, "period_end": run.period_end, "status": run.status,
            "total_debit": run.total_debit, "total_credit": run.total_credit,
            "elimination_amount": run.elimination_amount,
            "lines": [{"account_code": x.account_code, "name_ar": x.account_name_ar,
                       "name_en": x.account_name_en, "debit": x.debit, "credit": x.credit,
                       "is_elimination": x.is_elimination} for x in lines]}
