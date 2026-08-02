from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BankAccount, JournalEntry, JournalLine, User,
    ZakatTaxpayerProfile, TaxLossCarryforward, ZakatIncomeTaxReturn,
    ZakatTaxAdjustment, TaxLossUtilization,
)
from app.services.audit import write_audit
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/zakat-income-tax", tags=["Saudi zakat and corporate income tax"])
MONEY = Decimal("0.01")
RATE = Decimal("0.000001")


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def rate(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(RATE, rounding=ROUND_HALF_UP)


def pct(v: Decimal) -> Decimal:
    return Decimal(str(v or 0)) / Decimal("100")


def _csv(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
    buf = io.StringIO(); writer = csv.writer(buf); writer.writerow(headers); writer.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(ZakatIncomeTaxReturn.id)).where(ZakatIncomeTaxReturn.company_id == company_id)) or 0
    return f"ZT-{company_id}-{year}-{int(count)+1:05d}"


def _account(db: Session, company_id: int, code: str) -> Account:
    row = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code, Account.active.is_(True)))
    if not row or not row.is_postable:
        raise HTTPException(422, f"Account is missing or non-postable: {code}")
    return row


def ensure_accounts(db: Session, company_id: int):
    specs = [
        ("218030", "زكاة مستحقة", "Zakat Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000"),
        ("218040", "ضريبة دخل مستحقة", "Corporate Income Tax Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000"),
        ("118020", "دفعات زكاة وضريبة مقدمة", "Zakat and Tax Prepayments", "ASSET", "OTHER_CURRENT_ASSETS", "110000"),
        ("811020", "مصروف ضريبة الدخل الحالية", "Current Income Tax Expense", "EXPENSE", "ZAKAT_TAX", "800000"),
    ]
    result = {}
    for code, ar, en, typ, group, parent_code in specs:
        row = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code))
        if not row:
            parent = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == parent_code))
            row = Account(company_id=company_id, code=code, name_ar=ar, name_en=en, account_type=typ,
                          statement_group=group, parent_id=parent.id if parent else None, level=3,
                          is_postable=True, is_cash=False, active=True)
            db.add(row); db.flush()
        result[code] = row
    result["811010"] = _account(db, company_id, "811010")
    return result


def _profile(db: Session, company_id: int) -> ZakatTaxpayerProfile:
    row = db.scalar(select(ZakatTaxpayerProfile).where(ZakatTaxpayerProfile.company_id == company_id))
    if not row:
        raise HTTPException(422, "Zakat and income tax taxpayer profile is required")
    return row


def _return(db: Session, return_id: int) -> ZakatIncomeTaxReturn:
    row = db.scalar(select(ZakatIncomeTaxReturn).where(ZakatIncomeTaxReturn.id == return_id).options(
        selectinload(ZakatIncomeTaxReturn.adjustments),
        selectinload(ZakatIncomeTaxReturn.loss_usages).selectinload(TaxLossUtilization.loss),
    ))
    if not row:
        raise HTTPException(404, "Zakat and income tax return not found")
    return row


def _gl_balances(db: Session, company_id: int, start: date, end: date) -> dict:
    rows = db.execute(
        select(Account.account_type, Account.statement_group,
               func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(Account.company_id == company_id, JournalEntry.status == "POSTED", JournalEntry.entry_date <= end)
        .group_by(Account.account_type, Account.statement_group)
    ).all()
    period_rows = db.execute(
        select(Account.account_type, Account.statement_group,
               func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(Account.company_id == company_id, JournalEntry.status == "POSTED",
               JournalEntry.entry_date >= start, JournalEntry.entry_date <= end)
        .group_by(Account.account_type, Account.statement_group)
    ).all()
    pbt = Decimal("0")
    for typ, group, debit, credit in period_rows:
        if typ == "REVENUE": pbt += Decimal(credit) - Decimal(debit)
        elif typ == "EXPENSE" and group != "ZAKAT_TAX": pbt -= Decimal(debit) - Decimal(credit)
    equity = noncurrent_liabilities = noncurrent_assets = Decimal("0")
    for typ, group, debit, credit in rows:
        debit, credit = Decimal(debit), Decimal(credit)
        if typ == "EQUITY": equity += credit - debit
        if group == "NON_CURRENT_LIABILITIES": noncurrent_liabilities += credit - debit
        if group in {"NON_CURRENT_ASSETS", "PPE", "ACCUMULATED_DEPRECIATION"}:
            noncurrent_assets += debit - credit
    return {"pbt": money(pbt), "equity": money(equity), "noncurrent_liabilities": money(noncurrent_liabilities), "noncurrent_assets": money(noncurrent_assets)}


def _liability_balance(db: Session, company_id: int, end: date) -> Decimal:
    ids = db.scalars(select(Account.id).where(Account.company_id == company_id, Account.code.in_(["218030", "218040"]))).all()
    if not ids: return Decimal("0")
    debit, credit = db.execute(select(func.coalesce(func.sum(JournalLine.debit),0), func.coalesce(func.sum(JournalLine.credit),0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalLine.account_id.in_(ids), JournalEntry.status == "POSTED", JournalEntry.entry_date <= end)).one()
    return money(Decimal(credit)-Decimal(debit))


class ProfileIn(BaseModel):
    company_id: int
    zakat_registration_number: str | None = None
    cit_registration_number: str | None = None
    return_basis: str = "MIXED"
    saudi_gcc_ownership_percent: Decimal = Field(ge=0, le=100)
    non_saudi_ownership_percent: Decimal = Field(ge=0, le=100)
    zakat_rate_hijri: Decimal = Field(default=Decimal("2.5"), gt=0, le=100)
    hijri_year_days: int = Field(default=354, ge=353, le=355)
    income_tax_rate: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    tax_loss_utilization_cap_percent: Decimal = Field(default=Decimal("25"), ge=0, le=100)
    zakat_method: str = "FINANCING_SOURCES_LESS_DEDUCTIBLE_ASSETS"
    minimum_zakat_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_profile(self):
        self.return_basis = self.return_basis.upper()
        if self.return_basis not in {"ZAKAT", "CIT", "MIXED"}: raise ValueError("Invalid return basis")
        if money(self.saudi_gcc_ownership_percent + self.non_saudi_ownership_percent) != Decimal("100.00"):
            raise ValueError("Saudi/GCC and non-Saudi ownership percentages must total 100%")
        return self


class ReturnIn(BaseModel):
    company_id: int
    period_start: date
    period_end: date
    zakat_credits: Decimal = Field(default=0, ge=0)
    cit_credits: Decimal = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=1500)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start: raise ValueError("Period end cannot precede period start")
        if self.period_start.month != 1 or self.period_start.day != 1 or self.period_end.month != 12 or self.period_end.day != 31 or self.period_start.year != self.period_end.year:
            raise ValueError("RC24 annual return must cover a complete Gregorian fiscal year")
        return self


class AdjustmentIn(BaseModel):
    regime: str
    direction: str
    code: str = Field(min_length=2, max_length=60)
    description_ar: str = Field(min_length=2, max_length=500)
    description_en: str = Field(min_length=2, max_length=500)
    amount: Decimal = Field(gt=0)
    source_account_code: str | None = Field(default=None, max_length=30)
    evidence_reference: str | None = Field(default=None, max_length=250)
    recurring: bool = False

    @model_validator(mode="after")
    def validate_codes(self):
        self.regime = self.regime.upper(); self.direction = self.direction.upper(); self.code = self.code.upper()
        if self.regime not in {"CIT", "ZAKAT"}: raise ValueError("Invalid regime")
        if self.direction not in {"ADD", "DEDUCT"}: raise ValueError("Invalid direction")
        return self


class LossIn(BaseModel):
    company_id: int
    origin_year: int = Field(ge=1900, le=2200)
    original_amount: Decimal = Field(gt=0)
    evidence_reference: str | None = Field(default=None, max_length=250)
    notes: str | None = Field(default=None, max_length=1000)


class PaymentIn(BaseModel):
    bank_account_id: int
    payment_date: date
    sadad_invoice_number: str = Field(min_length=2, max_length=120)
    payment_reference: str = Field(min_length=2, max_length=150)


def serialize_profile(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in {"created_at", "updated_at"}}


def serialize_loss(row):
    available = money(row.original_amount - row.utilized_amount - row.expired_amount)
    return {"id": row.id, "company_id": row.company_id, "origin_year": row.origin_year, "original_amount": money(row.original_amount),
            "utilized_amount": money(row.utilized_amount), "expired_amount": money(row.expired_amount), "available_amount": available,
            "status": row.status, "evidence_reference": row.evidence_reference, "notes": row.notes}


def serialize_return(row):
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number, "period_start": row.period_start,
        "period_end": row.period_end, "due_date": row.due_date, "status": row.status,
        "calculation_status": row.calculation_status, "fiscal_days": row.fiscal_days,
        "accounting_profit_before_zakat_tax": money(row.accounting_profit_before_zakat_tax),
        "cit_additions": money(row.cit_additions), "cit_deductions": money(row.cit_deductions),
        "adjusted_taxable_profit": money(row.adjusted_taxable_profit), "non_saudi_ownership_percent": rate(row.non_saudi_ownership_percent),
        "cit_base_before_losses": money(row.cit_base_before_losses), "tax_losses_utilized": money(row.tax_losses_utilized),
        "income_tax_base": money(row.income_tax_base), "income_tax_rate": rate(row.income_tax_rate),
        "gross_income_tax": money(row.gross_income_tax), "cit_credits": money(row.cit_credits), "income_tax_payable": money(row.income_tax_payable),
        "gl_equity_balance": money(row.gl_equity_balance), "gl_non_current_liabilities": money(row.gl_non_current_liabilities),
        "gl_deductible_non_current_assets": money(row.gl_deductible_non_current_assets), "zakat_additions": money(row.zakat_additions),
        "zakat_deductions": money(row.zakat_deductions), "gross_zakat_base": money(row.gross_zakat_base),
        "saudi_gcc_ownership_percent": rate(row.saudi_gcc_ownership_percent), "zakat_base": money(row.zakat_base),
        "zakat_rate": rate(row.zakat_rate), "gross_zakat": money(row.gross_zakat), "zakat_credits": money(row.zakat_credits),
        "zakat_payable": money(row.zakat_payable), "total_gross_charge": money(row.total_gross_charge),
        "total_credits": money(row.total_credits), "total_payable": money(row.total_payable), "gl_payable": money(row.gl_payable),
        "reconciliation_difference": money(row.reconciliation_difference), "accrual_journal_id": row.accrual_journal_id,
        "payment_journal_id": row.payment_journal_id, "sadad_invoice_number": row.sadad_invoice_number,
        "payment_reference": row.payment_reference, "payment_date": row.payment_date, "notes": row.notes,
        "prepared_by": row.prepared_by, "submitted_by": row.submitted_by, "approved_by": row.approved_by,
        "adjustments": [{"id": a.id, "regime": a.regime, "direction": a.direction, "code": a.code,
                         "description_ar": a.description_ar, "description_en": a.description_en, "amount": money(a.amount),
                         "source_account_code": a.source_account_code, "evidence_reference": a.evidence_reference, "recurring": a.recurring}
                        for a in row.adjustments],
        "loss_usages": [{"loss_id": u.loss_id, "origin_year": u.loss.origin_year, "amount": money(u.amount)} for u in row.loss_usages],
    }


def recalculate(db: Session, row: ZakatIncomeTaxReturn) -> None:
    profile = _profile(db, row.company_id)
    gl = _gl_balances(db, row.company_id, row.period_start, row.period_end)
    row.accounting_profit_before_zakat_tax = gl["pbt"]
    row.gl_equity_balance = gl["equity"]
    row.gl_non_current_liabilities = gl["noncurrent_liabilities"]
    row.gl_deductible_non_current_assets = gl["noncurrent_assets"]
    cit_add = sum((money(a.amount) for a in row.adjustments if a.regime == "CIT" and a.direction == "ADD"), Decimal("0"))
    cit_ded = sum((money(a.amount) for a in row.adjustments if a.regime == "CIT" and a.direction == "DEDUCT"), Decimal("0"))
    zak_add = sum((money(a.amount) for a in row.adjustments if a.regime == "ZAKAT" and a.direction == "ADD"), Decimal("0"))
    zak_ded = sum((money(a.amount) for a in row.adjustments if a.regime == "ZAKAT" and a.direction == "DEDUCT"), Decimal("0"))
    row.cit_additions, row.cit_deductions = money(cit_add), money(cit_ded)
    row.zakat_additions, row.zakat_deductions = money(zak_add), money(zak_ded)
    adjusted = max(Decimal("0"), money(row.accounting_profit_before_zakat_tax + cit_add - cit_ded))
    row.adjusted_taxable_profit = adjusted
    row.non_saudi_ownership_percent = profile.non_saudi_ownership_percent
    base_before_losses = money(adjusted * pct(profile.non_saudi_ownership_percent))
    row.cit_base_before_losses = base_before_losses

    for usage in list(row.loss_usages): db.delete(usage)
    db.flush()
    available_losses = db.scalars(select(TaxLossCarryforward).where(
        TaxLossCarryforward.company_id == row.company_id,
        TaxLossCarryforward.origin_year < row.period_end.year,
        TaxLossCarryforward.status == "AVAILABLE",
    ).order_by(TaxLossCarryforward.origin_year)).all()
    cap = money(base_before_losses * pct(profile.tax_loss_utilization_cap_percent))
    remaining_cap = cap; used = Decimal("0")
    for loss in available_losses:
        available = money(loss.original_amount - loss.utilized_amount - loss.expired_amount)
        take = min(available, remaining_cap)
        if take <= 0: continue
        row.loss_usages.append(TaxLossUtilization(loss_id=loss.id, amount=take)); used += take; remaining_cap -= take
        if remaining_cap <= 0: break
    row.tax_losses_utilized = money(used)
    row.income_tax_base = money(max(Decimal("0"), base_before_losses - used))
    row.income_tax_rate = profile.income_tax_rate
    row.gross_income_tax = money(row.income_tax_base * pct(profile.income_tax_rate)) if profile.return_basis in {"CIT", "MIXED"} else Decimal("0")
    row.income_tax_payable = money(max(Decimal("0"), row.gross_income_tax - row.cit_credits))

    gross_zakat_base = money(gl["equity"] + gl["noncurrent_liabilities"] + zak_add - gl["noncurrent_assets"] - zak_ded)
    row.gross_zakat_base = max(Decimal("0"), gross_zakat_base)
    row.saudi_gcc_ownership_percent = profile.saudi_gcc_ownership_percent
    row.zakat_base = money(row.gross_zakat_base * pct(profile.saudi_gcc_ownership_percent))
    row.fiscal_days = (row.period_end - row.period_start).days + 1
    row.zakat_rate = rate(profile.zakat_rate_hijri * Decimal(row.fiscal_days) / Decimal(profile.hijri_year_days))
    calculated_zakat = money(row.zakat_base * pct(row.zakat_rate)) if profile.return_basis in {"ZAKAT", "MIXED"} else Decimal("0")
    if calculated_zakat > 0 and profile.minimum_zakat_amount > 0: calculated_zakat = max(calculated_zakat, money(profile.minimum_zakat_amount))
    row.gross_zakat = calculated_zakat
    row.zakat_payable = money(max(Decimal("0"), row.gross_zakat - row.zakat_credits))
    row.total_gross_charge = money(row.gross_zakat + row.gross_income_tax)
    row.total_credits = money(row.zakat_credits + row.cit_credits)
    row.total_payable = money(row.zakat_payable + row.income_tax_payable)
    row.gl_payable = _liability_balance(db, row.company_id, row.period_end if row.status not in {"APPROVED", "PAID"} else (row.payment_date or row.period_end))
    row.reconciliation_difference = money(row.gl_payable - (Decimal("0") if row.status == "PAID" else row.total_payable))


@router.post("/profiles", status_code=201)
def save_profile(data: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    row = db.scalar(select(ZakatTaxpayerProfile).where(ZakatTaxpayerProfile.company_id == data.company_id))
    if not row:
        row = ZakatTaxpayerProfile(company_id=data.company_id, created_by=user.id); db.add(row)
    for k, v in data.model_dump(exclude={"company_id"}).items(): setattr(row, k, v)
    row.updated_by = user.id; db.flush(); write_audit(db, action="ZAKAT_TAX_PROFILE_SAVED", entity_type="ZAKAT_TAX_PROFILE", entity_id=row.id, user_id=user.id, company_id=data.company_id)
    db.commit(); return serialize_profile(row)


@router.get("/profiles/{company_id}")
def read_profile(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read"); return serialize_profile(_profile(db, company_id))


@router.post("/losses", status_code=201)
def create_loss(data: LossIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    if db.scalar(select(TaxLossCarryforward).where(TaxLossCarryforward.company_id == data.company_id, TaxLossCarryforward.origin_year == data.origin_year)):
        raise HTTPException(409, "Tax loss already exists for this year")
    row = TaxLossCarryforward(**data.model_dump(), created_by=user.id); db.add(row); db.flush()
    write_audit(db, action="TAX_LOSS_CREATED", entity_type="TAX_LOSS", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"year": data.origin_year, "amount": str(data.original_amount)})
    db.commit(); return serialize_loss(row)


@router.get("/losses")
def list_losses(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    return [serialize_loss(x) for x in db.scalars(select(TaxLossCarryforward).where(TaxLossCarryforward.company_id == company_id).order_by(TaxLossCarryforward.origin_year)).all()]


@router.post("/returns", status_code=201)
def create_return(data: ReturnIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage"); _profile(db, data.company_id); ensure_accounts(db, data.company_id)
    if db.scalar(select(ZakatIncomeTaxReturn).where(ZakatIncomeTaxReturn.company_id == data.company_id, ZakatIncomeTaxReturn.period_start == data.period_start, ZakatIncomeTaxReturn.period_end == data.period_end)):
        raise HTTPException(409, "Return already exists for this period")
    row = ZakatIncomeTaxReturn(company_id=data.company_id, number=_number(db, data.company_id, data.period_end.year), period_start=data.period_start,
        period_end=data.period_end, due_date=data.period_end + timedelta(days=120), zakat_credits=money(data.zakat_credits), cit_credits=money(data.cit_credits), notes=data.notes, prepared_by=user.id)
    db.add(row); db.flush(); recalculate(db, row); write_audit(db, action="ZAKAT_CIT_RETURN_CREATED", entity_type="ZAKAT_CIT_RETURN", entity_id=row.id, user_id=user.id, company_id=data.company_id)
    db.commit(); return serialize_return(_return(db, row.id))


@router.post("/returns/{return_id}/adjustments", status_code=201)
def add_adjustment(return_id: int, data: AdjustmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _return(db, return_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Adjustments can only be changed while the return is draft")
    if data.source_account_code and not db.scalar(select(Account.id).where(Account.company_id == row.company_id, Account.code == data.source_account_code)):
        raise HTTPException(422, "Source account code not found")
    adj = ZakatTaxAdjustment(created_by=user.id, **data.model_dump())
    # Attach through the loaded relationship so the current adjustment is included
    # in this same request's recalculation. Assigning return_id alone leaves a
    # selectin-loaded collection stale until the next request.
    row.adjustments.append(adj)
    db.flush()
    recalculate(db, row)
    write_audit(db, action="ZAKAT_CIT_ADJUSTMENT_ADDED", entity_type="ZAKAT_CIT_RETURN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"code": adj.code, "amount": str(adj.amount)})
    db.commit(); return serialize_return(_return(db, row.id))


@router.delete("/returns/{return_id}/adjustments/{adjustment_id}")
def delete_adjustment(return_id: int, adjustment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _return(db, return_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Adjustments can only be changed while the return is draft")
    adj = db.scalar(select(ZakatTaxAdjustment).where(ZakatTaxAdjustment.id == adjustment_id, ZakatTaxAdjustment.return_id == row.id))
    if not adj: raise HTTPException(404, "Adjustment not found")
    # Keep the already-loaded relationship consistent in this request.  Merely
    # marking ``adj`` deleted leaves it in ``row.adjustments`` until the session
    # expires, so recalculation and the immediate response can still include it.
    row.adjustments.remove(adj)
    db.delete(adj); db.flush(); recalculate(db, row); db.commit(); return serialize_return(_return(db, row.id))


@router.post("/returns/{return_id}/recalculate")
def recalc_return(return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _return(db, return_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft returns can be recalculated")
    recalculate(db, row); db.commit(); return serialize_return(_return(db, row.id))


@router.post("/returns/{return_id}/submit")
def submit_return(return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _return(db, return_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft returns can be submitted")
    recalculate(db, row)
    missing = [a.code for a in row.adjustments if not a.evidence_reference]
    if missing: raise HTTPException(422, f"Evidence reference is required for adjustments: {', '.join(missing)}")
    row.status = "SUBMITTED"; row.submitted_by = user.id; row.submitted_at = utc_now()
    write_audit(db, action="ZAKAT_CIT_RETURN_SUBMITTED", entity_type="ZAKAT_CIT_RETURN", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return serialize_return(_return(db, row.id))


@router.post("/returns/{return_id}/approve-post")
def approve_return(return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _return(db, return_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "SUBMITTED": raise HTTPException(409, "Only submitted returns can be approved")
    if row.prepared_by == user.id or row.submitted_by == user.id: raise HTTPException(409, "Maker-checker control: preparer or submitter cannot approve")
    accounts = ensure_accounts(db, row.company_id); lines = []
    if money(row.gross_zakat) > 0:
        lines += [{"account_id": accounts["811010"].id, "debit": money(row.gross_zakat), "credit": 0}, {"account_id": accounts["218030"].id, "debit": 0, "credit": money(row.gross_zakat)}]
    if money(row.gross_income_tax) > 0:
        lines += [{"account_id": accounts["811020"].id, "debit": money(row.gross_income_tax), "credit": 0}, {"account_id": accounts["218040"].id, "debit": 0, "credit": money(row.gross_income_tax)}]
    if money(row.zakat_credits) > 0:
        lines += [{"account_id": accounts["218030"].id, "debit": money(row.zakat_credits), "credit": 0}, {"account_id": accounts["118020"].id, "debit": 0, "credit": money(row.zakat_credits)}]
    if money(row.cit_credits) > 0:
        lines += [{"account_id": accounts["218040"].id, "debit": money(row.cit_credits), "credit": 0}, {"account_id": accounts["118020"].id, "debit": 0, "credit": money(row.cit_credits)}]
    if lines:
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.period_end,
            reference=row.number, description=f"Zakat and corporate income tax accrual {row.number}", lines=lines)
        row.accrual_journal_id = journal.id
    for usage in row.loss_usages:
        usage.loss.utilized_amount = money(usage.loss.utilized_amount + usage.amount)
        if money(usage.loss.original_amount - usage.loss.utilized_amount - usage.loss.expired_amount) <= 0: usage.loss.status = "UTILIZED"
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); row.calculation_status = "APPROVED_INTERNAL_RETURN"
    row.gl_payable = money(row.total_payable); row.reconciliation_difference = Decimal("0")
    write_audit(db, action="ZAKAT_CIT_RETURN_APPROVED_POSTED", entity_type="ZAKAT_CIT_RETURN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"total_payable": str(row.total_payable), "journal_id": row.accrual_journal_id})
    db.commit(); return serialize_return(_return(db, row.id))


@router.post("/returns/{return_id}/pay")
def pay_return(return_id: int, data: PaymentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _return(db, return_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "APPROVED": raise HTTPException(409, "Only approved returns can be paid")
    if row.total_payable <= 0: raise HTTPException(409, "Return has no payable amount")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == row.company_id, BankAccount.active.is_(True)))
    if not bank: raise HTTPException(422, "Bank account not found")
    accounts = ensure_accounts(db, row.company_id); lines=[]
    if row.zakat_payable > 0: lines.append({"account_id": accounts["218030"].id, "debit": money(row.zakat_payable), "credit": 0})
    if row.income_tax_payable > 0: lines.append({"account_id": accounts["218040"].id, "debit": money(row.income_tax_payable), "credit": 0})
    lines.append({"account_id": bank.gl_account_id, "debit": 0, "credit": money(row.total_payable)})
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=data.payment_date,
        reference=data.sadad_invoice_number, description=f"Payment of zakat and income tax return {row.number}", lines=lines,
        cash_flow_activity="OPERATING", cash_flow_kind="ZAKAT_AND_INCOME_TAX_PAYMENTS")
    row.status = "PAID"; row.payment_journal_id = journal.id; row.sadad_invoice_number = data.sadad_invoice_number
    row.payment_reference = data.payment_reference; row.payment_date = data.payment_date; row.paid_by = user.id; row.paid_at = utc_now()
    row.gl_payable = Decimal("0"); row.reconciliation_difference = Decimal("0")
    write_audit(db, action="ZAKAT_CIT_RETURN_PAID", entity_type="ZAKAT_CIT_RETURN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"amount": str(row.total_payable), "journal_id": journal.id})
    db.commit(); return serialize_return(_return(db, row.id))


@router.get("/returns")
def list_returns(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(ZakatIncomeTaxReturn).where(ZakatIncomeTaxReturn.company_id == company_id).options(
        selectinload(ZakatIncomeTaxReturn.adjustments), selectinload(ZakatIncomeTaxReturn.loss_usages).selectinload(TaxLossUtilization.loss)
    ).order_by(ZakatIncomeTaxReturn.period_end.desc())).all()
    return [serialize_return(x) for x in rows]


@router.get("/returns/{return_id}")
def read_return(return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _return(db, return_id); ensure_permission(db, user, row.company_id, "compliance.read"); return serialize_return(row)


@router.get("/export/returns.csv")
def export_returns(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = list_returns(company_id, user=user, db=db)
    return _csv("zakat_income_tax_returns.csv", ["Number","Period start","Period end","Due date","Accounting PBT","CIT additions","CIT deductions","CIT base","CIT rate","Gross CIT","CIT credits","CIT payable","Zakat gross base","Zakat ownership base","Zakat rate","Gross zakat","Zakat credits","Zakat payable","Total payable","GL payable","Difference","Status"],
        [[x["number"],x["period_start"],x["period_end"],x["due_date"],x["accounting_profit_before_zakat_tax"],x["cit_additions"],x["cit_deductions"],x["income_tax_base"],x["income_tax_rate"],x["gross_income_tax"],x["cit_credits"],x["income_tax_payable"],x["gross_zakat_base"],x["zakat_base"],x["zakat_rate"],x["gross_zakat"],x["zakat_credits"],x["zakat_payable"],x["total_payable"],x["gl_payable"],x["reconciliation_difference"],x["status"]] for x in rows])


@router.get("/export/adjustments.csv")
def export_adjustments(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.execute(select(ZakatIncomeTaxReturn.number, ZakatIncomeTaxReturn.period_end, ZakatTaxAdjustment)
        .join(ZakatTaxAdjustment, ZakatTaxAdjustment.return_id == ZakatIncomeTaxReturn.id)
        .where(ZakatIncomeTaxReturn.company_id == company_id).order_by(ZakatIncomeTaxReturn.period_end, ZakatTaxAdjustment.id)).all()
    return _csv("zakat_income_tax_adjustments.csv", ["Return","Year end","Regime","Direction","Code","Arabic description","English description","Amount","Source account","Evidence","Recurring"],
        [[number, period_end, a.regime, a.direction, a.code, a.description_ar, a.description_en, a.amount, a.source_account_code, a.evidence_reference, a.recurring] for number, period_end, a in rows])
