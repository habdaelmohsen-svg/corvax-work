from __future__ import annotations

import csv
import io
import json
import math
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BankAccount, FinancialOpenItem, JournalLine, Party, Payment, PurchaseInvoice, User,
    WithholdingBeneficiaryProfile, WithholdingTaxCategory, WithholdingTaxReturn,
    WithholdingTaxReturnLine, WithholdingTaxTransaction,
)
from app.services.ar_ap import allocate_payment, ensure_purchase_invoice_open_item, open_amount
from app.services.audit import write_audit
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/withholding-tax", tags=["Saudi withholding tax and monthly return"])
MONEY = Decimal("0.01")
RATE = Decimal("0.0001")

DEFAULT_WHT_CATEGORIES = [
    ("MANAGEMENT_FEES", "أتعاب الإدارة", "Management fees", "20", "MANAGEMENT_FEES"),
    ("ROYALTIES", "الإتاوات", "Royalties", "15", "ROYALTIES"),
    ("DIVIDENDS", "توزيعات الأرباح", "Dividends", "5", "DIVIDENDS"),
    ("RENT", "الإيجار", "Rent", "5", "RENT"),
    ("INSURANCE", "التأمين وإعادة التأمين", "Insurance and reinsurance", "5", "INSURANCE_REINSURANCE"),
    ("LOAN_RETURNS", "عوائد القروض", "Loan returns", "5", "LOAN_RETURNS"),
    ("TECHNICAL_CONSULTING", "خدمات فنية واستشارية", "Technical and consulting services", "5", "TECHNICAL_CONSULTING"),
    ("AIR_SEA_FREIGHT", "تذاكر طيران وشحن جوي أو بحري", "Air tickets and air or sea freight", "5", "AIR_SEA_FREIGHT"),
    ("INTERNATIONAL_TELECOM", "اتصالات دولية", "International telecommunication services", "5", "INTERNATIONAL_TELECOM"),
    ("OTHER_KSA_SOURCE_SERVICES", "خدمات أخرى من مصدر في المملكة", "Other services from KSA sources", "15", "OTHER_SERVICES"),
    ("GOODS_PURCHASE", "شراء بضائع دون خدمات", "Pure purchase of goods", "0", "OUT_OF_SCOPE"),
    ("INTERNATIONAL_ROAMING", "تجوال دولي منفذ بالكامل خارج المملكة", "International roaming performed outside KSA", "0", "OUT_OF_SCOPE"),
]

def ensure_categories(db: Session, company_id: int, user_id: int | None = None):
    existing={x.code:x for x in db.scalars(select(WithholdingTaxCategory).where(WithholdingTaxCategory.company_id==company_id)).all()}
    for code,ar,en,statutory,income_type in DEFAULT_WHT_CATEGORIES:
        if code in existing: continue
        row=WithholdingTaxCategory(company_id=company_id,code=code,name_ar=ar,name_en=en,statutory_rate=Decimal(statutory),income_type=income_type,source_rule="Article 68 / Article 63 classification; validate source and treaty facts per transaction",system_code=True,active=True,created_by=user_id)
        db.add(row);db.flush();existing[code]=row
    return existing


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def rate(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(RATE, rounding=ROUND_HALF_UP)


def account(db: Session, company_id: int, code: str) -> Account:
    row = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code, Account.active.is_(True)))
    if not row or not row.is_postable:
        raise HTTPException(422, f"Account is missing or non-postable: {code}")
    return row


def _number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{int(count)+1:06d}"


def _maker_checker(creator: int | None, user_id: int):
    if creator == user_id:
        raise HTTPException(409, "Maker-checker control: creator cannot approve the same document")


def _csv(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
    buf = io.StringIO(); writer = csv.writer(buf); writer.writerow(headers); writer.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class BeneficiaryProfileIn(BaseModel):
    company_id: int
    party_id: int
    country_code: str = Field(min_length=2, max_length=3)
    tax_residency_country: str = Field(min_length=2, max_length=3)
    foreign_tax_id: str | None = Field(default=None, max_length=120)
    non_resident: bool = True
    permanent_establishment_in_ksa: bool = False
    related_party: bool = False
    beneficial_owner_confirmed: bool = False
    treaty_country_code: str | None = Field(default=None, max_length=3)
    residency_certificate_number: str | None = Field(default=None, max_length=150)
    residency_certificate_expiry: date | None = None
    treaty_relief_approval_reference: str | None = Field(default=None, max_length=150)
    treaty_relief_approval_expiry: date | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_profile(self):
        self.country_code = self.country_code.upper()
        self.tax_residency_country = self.tax_residency_country.upper()
        self.treaty_country_code = self.treaty_country_code.upper() if self.treaty_country_code else None
        if self.permanent_establishment_in_ksa and self.non_resident:
            # The legal person can be non-resident, but payments attributable to its KSA PE should not use WHT.
            pass
        if self.treaty_relief_approval_reference and not self.treaty_country_code:
            raise ValueError("Treaty country is required for an approved DTA relief reference")
        return self


class WhtTransactionIn(BaseModel):
    company_id: int
    payment_date: date
    beneficiary_profile_id: int
    category_id: int
    amount: Decimal = Field(gt=0, description="Tax base, or beneficiary net amount when gross_up=true")
    bank_account_id: int
    purchase_invoice_id: int | None = None
    debit_account_code: str | None = None
    gross_up: bool = False
    source_in_ksa: bool = True
    dta_relief_method: str = "STATUTORY"
    treaty_rate: Decimal | None = Field(default=None, ge=0, le=100)
    dta_reference: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=3, max_length=500)
    reference: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def validate_method(self):
        self.dta_relief_method = self.dta_relief_method.upper()
        if self.dta_relief_method not in {"STATUTORY", "REFUND_CLAIM", "DIRECT_RELIEF"}:
            raise ValueError("Invalid DTA relief method")
        if self.purchase_invoice_id and self.debit_account_code:
            raise ValueError("Use either purchase_invoice_id or debit_account_code, not both")
        if not self.purchase_invoice_id and not self.debit_account_code:
            raise ValueError("purchase_invoice_id or debit_account_code is required")
        if self.gross_up and self.purchase_invoice_id:
            raise ValueError("Gross-up transactions must use a direct debit account, not an existing purchase invoice")
        return self


class ReturnIn(BaseModel):
    company_id: int
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("Period end cannot precede period start")
        if self.period_start.day != 1 or self.period_end.day != monthrange(self.period_end.year, self.period_end.month)[1] or self.period_start.year != self.period_end.year or self.period_start.month != self.period_end.month:
            raise ValueError("Withholding return must cover one complete calendar month")
        return self


class ReturnPaymentIn(BaseModel):
    bank_account_id: int
    payment_date: date
    sadad_invoice_number: str = Field(min_length=2, max_length=120)
    payment_reference: str = Field(min_length=2, max_length=150)


def serialize_profile(row: WithholdingBeneficiaryProfile) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "party_id": row.party_id,
        "party_code": row.party.code, "party_name_ar": row.party.name_ar, "party_name_en": row.party.name_en,
        "country_code": row.country_code, "tax_residency_country": row.tax_residency_country,
        "foreign_tax_id": row.foreign_tax_id, "non_resident": row.non_resident,
        "permanent_establishment_in_ksa": row.permanent_establishment_in_ksa, "related_party": row.related_party,
        "beneficial_owner_confirmed": row.beneficial_owner_confirmed, "treaty_country_code": row.treaty_country_code,
        "residency_certificate_number": row.residency_certificate_number,
        "residency_certificate_expiry": row.residency_certificate_expiry,
        "treaty_relief_approval_reference": row.treaty_relief_approval_reference,
        "treaty_relief_approval_expiry": row.treaty_relief_approval_expiry, "notes": row.notes, "active": row.active,
    }


def serialize_transaction(row: WithholdingTaxTransaction) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number, "payment_date": row.payment_date,
        "beneficiary_profile_id": row.beneficiary_profile_id, "party_id": row.beneficiary.party_id,
        "beneficiary_code": row.beneficiary.party.code, "beneficiary_name_ar": row.beneficiary.party.name_ar,
        "beneficiary_name_en": row.beneficiary.party.name_en, "country_code": row.beneficiary.country_code,
        "category_id": row.category_id, "category_code": row.category.code, "category_name_ar": row.category.name_ar,
        "category_name_en": row.category.name_en, "purchase_invoice_id": row.purchase_invoice_id,
        "purchase_invoice_number": row.purchase_invoice.number if row.purchase_invoice else None,
        "debit_account_code": row.debit_account.code if row.debit_account else None,
        "gross_amount": money(row.gross_amount), "statutory_rate": rate(row.statutory_rate),
        "treaty_rate": rate(row.treaty_rate) if row.treaty_rate is not None else None,
        "applied_rate": rate(row.applied_rate), "withholding_amount": money(row.withholding_amount),
        "net_cash_amount": money(row.net_cash_amount), "gross_up": row.gross_up,
        "dta_relief_method": row.dta_relief_method, "dta_reference": row.dta_reference,
        "source_in_ksa": row.source_in_ksa, "description": row.description, "reference": row.reference,
        "status": row.status, "payment_id": row.payment_id, "journal_id": row.journal_id,
        "created_by": row.created_by, "submitted_by": row.submitted_by, "approved_by": row.approved_by,
    }


def serialize_return(row: WithholdingTaxReturn, *, as_of: date | None = None) -> dict:
    effective = as_of or date.today()
    late_days = max(0, (effective - row.due_date).days) if row.status != "PAID" else 0
    periods = math.ceil(late_days / 30) if late_days else 0
    estimated_penalty = money(row.tax_withheld * Decimal(periods) / Decimal(100))
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number,
        "period_start": row.period_start, "period_end": row.period_end, "due_date": row.due_date,
        "status": row.status, "gross_payments": money(row.gross_payments), "tax_withheld": money(row.tax_withheld),
        "gl_withheld": money(row.gl_withheld), "reconciliation_difference": money(row.reconciliation_difference),
        "late_days": late_days, "estimated_late_penalty": estimated_penalty,
        "sadad_invoice_number": row.sadad_invoice_number, "payment_reference": row.payment_reference,
        "payment_date": row.payment_date, "payment_journal_id": row.payment_journal_id,
        "prepared_by": row.prepared_by, "submitted_by": row.submitted_by, "approved_by": row.approved_by,
        "lines": [{
            "category_id": line.category_id, "category_code": line.category.code,
            "name_ar": line.category.name_ar, "name_en": line.category.name_en,
            "statutory_rate": rate(line.category.statutory_rate), "gross_amount": money(line.gross_amount),
            "tax_amount": money(line.tax_amount), "transaction_count": line.transaction_count,
            "details": json.loads(line.details_json or "[]"),
        } for line in row.lines],
    }


@router.get("/categories")
def list_categories(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    ensure_categories(db, company_id, user.id)
    rows = db.scalars(select(WithholdingTaxCategory).where(WithholdingTaxCategory.company_id == company_id, WithholdingTaxCategory.active.is_(True)).order_by(WithholdingTaxCategory.statutory_rate, WithholdingTaxCategory.code)).all()
    return [{"id": x.id, "code": x.code, "name_ar": x.name_ar, "name_en": x.name_en, "statutory_rate": rate(x.statutory_rate), "income_type": x.income_type, "source_rule": x.source_rule} for x in rows]


@router.post("/beneficiaries", status_code=201)
def save_beneficiary(data: BeneficiaryProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    party = db.scalar(select(Party).where(Party.id == data.party_id, Party.company_id == data.company_id, Party.active.is_(True)))
    if not party or party.party_type not in {"SUPPLIER", "BOTH"}:
        raise HTTPException(422, "Beneficiary must be an active supplier in the same company")
    row = db.scalar(select(WithholdingBeneficiaryProfile).where(WithholdingBeneficiaryProfile.company_id == data.company_id, WithholdingBeneficiaryProfile.party_id == data.party_id))
    payload = data.model_dump(exclude={"company_id", "party_id"})
    if row:
        for key, value in payload.items(): setattr(row, key, value)
        row.updated_by = user.id; row.updated_at = utc_now(); action = "WHT_BENEFICIARY_UPDATED"
    else:
        row = WithholdingBeneficiaryProfile(company_id=data.company_id, party_id=data.party_id, **payload, created_by=user.id, updated_by=user.id)
        db.add(row); db.flush(); action = "WHT_BENEFICIARY_CREATED"
    write_audit(db, action=action, entity_type="WHT_BENEFICIARY", entity_id=row.id, user_id=user.id, company_id=data.company_id, after=serialize_profile(row))
    db.commit(); db.refresh(row)
    return serialize_profile(row)


@router.get("/beneficiaries")
def list_beneficiaries(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(WithholdingBeneficiaryProfile).where(WithholdingBeneficiaryProfile.company_id == company_id, WithholdingBeneficiaryProfile.active.is_(True)).options(selectinload(WithholdingBeneficiaryProfile.party)).order_by(WithholdingBeneficiaryProfile.id)).all()
    return [serialize_profile(x) for x in rows]


@router.post("/transactions", status_code=201)
def create_transaction(data: WhtTransactionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    ensure_categories(db, data.company_id, user.id)
    profile = db.scalar(select(WithholdingBeneficiaryProfile).where(WithholdingBeneficiaryProfile.id == data.beneficiary_profile_id, WithholdingBeneficiaryProfile.company_id == data.company_id, WithholdingBeneficiaryProfile.active.is_(True)).options(selectinload(WithholdingBeneficiaryProfile.party)))
    category = db.scalar(select(WithholdingTaxCategory).where(WithholdingTaxCategory.id == data.category_id, WithholdingTaxCategory.company_id == data.company_id, WithholdingTaxCategory.active.is_(True)))
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not profile or not category or not bank:
        raise HTTPException(422, "Beneficiary, category or bank account is invalid")
    if not profile.non_resident:
        raise HTTPException(422, "Saudi WHT applies to qualifying payments to non-residents")
    if profile.permanent_establishment_in_ksa:
        raise HTTPException(422, "Payments attributable to a KSA permanent establishment must not use this WHT workflow")
    if category.code == "TECHNICAL_CONSULTING":
        source_in_ksa = True  # statutory treatment applies regardless of place of performance
    else:
        source_in_ksa = data.source_in_ksa
    statutory = rate(category.statutory_rate)
    applied = statutory
    treaty = rate(data.treaty_rate) if data.treaty_rate is not None else None
    if data.dta_relief_method == "DIRECT_RELIEF":
        if treaty is None or treaty > statutory:
            raise HTTPException(422, "A valid treaty rate not exceeding the statutory rate is required")
        if not profile.treaty_relief_approval_reference or not profile.treaty_relief_approval_expiry or profile.treaty_relief_approval_expiry < data.payment_date:
            raise HTTPException(422, "Direct treaty relief requires a valid ZATCA/treaty approval reference")
        if data.dta_reference != profile.treaty_relief_approval_reference:
            raise HTTPException(422, "DTA reference does not match the approved beneficiary profile")
        applied = treaty
    elif data.dta_relief_method == "REFUND_CLAIM":
        if treaty is None or treaty > statutory or not profile.residency_certificate_number or not profile.beneficial_owner_confirmed:
            raise HTTPException(422, "Refund-claim tracking requires treaty rate, residency certificate and beneficial-owner confirmation")
        applied = statutory
    elif treaty is not None:
        raise HTTPException(422, "Treaty rate is only accepted with REFUND_CLAIM or DIRECT_RELIEF")
    if not source_in_ksa and statutory > 0:
        raise HTTPException(422, "Use an out-of-scope category when the payment is not from a KSA source")
    input_amount = money(data.amount)
    if data.gross_up:
        fraction = applied / Decimal(100)
        if fraction >= 1:
            raise HTTPException(422, "Gross-up rate must be below 100%")
        net_cash = input_amount
        gross = money(net_cash / (Decimal(1) - fraction))
        withheld = money(gross - net_cash)
    else:
        gross = input_amount
        withheld = money(gross * applied / Decimal(100))
        net_cash = money(gross - withheld)
    invoice = None; debit = None
    if data.purchase_invoice_id:
        invoice = db.scalar(select(PurchaseInvoice).where(PurchaseInvoice.id == data.purchase_invoice_id, PurchaseInvoice.company_id == data.company_id, PurchaseInvoice.supplier_id == profile.party_id))
        if not invoice or invoice.status != "POSTED":
            raise HTTPException(422, "Purchase invoice must be posted and belong to the beneficiary")
        item = ensure_purchase_invoice_open_item(db, invoice)
        if gross > open_amount(db, item):
            raise HTTPException(409, f"Gross settlement exceeds invoice open amount {open_amount(db, item)}")
    else:
        debit = account(db, data.company_id, str(data.debit_account_code))
    number = _number(db, WithholdingTaxTransaction, data.company_id, "WHT", data.payment_date.year)
    row = WithholdingTaxTransaction(
        company_id=data.company_id, number=number, payment_date=data.payment_date,
        beneficiary_profile_id=profile.id, category_id=category.id, purchase_invoice_id=invoice.id if invoice else None,
        debit_account_id=debit.id if debit else None, bank_account_id=bank.id, gross_amount=gross,
        statutory_rate=statutory, treaty_rate=treaty, applied_rate=applied, withholding_amount=withheld,
        net_cash_amount=net_cash, gross_up=data.gross_up, dta_relief_method=data.dta_relief_method,
        dta_reference=data.dta_reference, source_in_ksa=source_in_ksa, description=data.description,
        reference=data.reference, status="DRAFT", created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="WHT_TRANSACTION_CREATED", entity_type="WHT_TRANSACTION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": number, "gross": str(gross), "rate": str(applied), "tax": str(withheld), "net": str(net_cash)})
    db.commit(); db.refresh(row)
    return serialize_transaction(row)


@router.get("/transactions")
def list_transactions(company_id: int, period_start: date | None = None, period_end: date | None = None, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    q = select(WithholdingTaxTransaction).where(WithholdingTaxTransaction.company_id == company_id).options(
        selectinload(WithholdingTaxTransaction.beneficiary).selectinload(WithholdingBeneficiaryProfile.party),
        selectinload(WithholdingTaxTransaction.category), selectinload(WithholdingTaxTransaction.purchase_invoice),
        selectinload(WithholdingTaxTransaction.debit_account),
    ).order_by(WithholdingTaxTransaction.payment_date.desc(), WithholdingTaxTransaction.id.desc())
    if period_start: q=q.where(WithholdingTaxTransaction.payment_date >= period_start)
    if period_end: q=q.where(WithholdingTaxTransaction.payment_date <= period_end)
    if status: q=q.where(WithholdingTaxTransaction.status == status.upper())
    return [serialize_transaction(x) for x in db.scalars(q).all()]


@router.post("/transactions/{transaction_id}/submit")
def submit_transaction(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(WithholdingTaxTransaction, transaction_id)
    if not row: raise HTTPException(404, "WHT transaction not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft transactions can be submitted")
    row.status="PENDING_APPROVAL"; row.submitted_by=user.id; row.submitted_at=utc_now()
    write_audit(db, action="WHT_TRANSACTION_SUBMITTED", entity_type="WHT_TRANSACTION", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return serialize_transaction(row)


@router.post("/transactions/{transaction_id}/approve-post")
def approve_transaction(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(WithholdingTaxTransaction).where(WithholdingTaxTransaction.id == transaction_id).options(
        selectinload(WithholdingTaxTransaction.beneficiary).selectinload(WithholdingBeneficiaryProfile.party),
        selectinload(WithholdingTaxTransaction.category), selectinload(WithholdingTaxTransaction.purchase_invoice),
        selectinload(WithholdingTaxTransaction.debit_account), selectinload(WithholdingTaxTransaction.bank_account),
    ))
    if not row: raise HTTPException(404, "WHT transaction not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "PENDING_APPROVAL": raise HTTPException(409, "Transaction is not pending approval")
    _maker_checker(row.created_by, user.id)
    wht = account(db, row.company_id, "218010")
    lines=[]
    if row.purchase_invoice_id:
        ap=account(db,row.company_id,"211010")
        lines.append({"account_id":ap.id,"debit":money(row.gross_amount),"credit":0})
    else:
        lines.append({"account_id":row.debit_account_id,"debit":money(row.gross_amount),"credit":0})
    if money(row.net_cash_amount)>0: lines.append({"account_id":row.bank_account.gl_account_id,"debit":0,"credit":money(row.net_cash_amount)})
    if money(row.withholding_amount)>0: lines.append({"account_id":wht.id,"debit":0,"credit":money(row.withholding_amount)})
    journal=create_posted_journal(db,company_id=row.company_id,user_id=user.id,posting_date=row.payment_date,reference=row.number,description=f"WHT payment to {row.beneficiary.party.name_en}: {row.description}",lines=lines,cash_flow_activity="OPERATING",cash_flow_kind="SUPPLIER_PAYMENTS")
    payment=None
    if row.purchase_invoice_id:
        item=ensure_purchase_invoice_open_item(db,row.purchase_invoice)
        payment=Payment(company_id=row.company_id,number=f"WHTPY-{row.number}",payment_date=row.payment_date,supplier_id=row.beneficiary.party_id,bank_account_id=row.bank_account_id,amount=money(row.gross_amount),net_cash_amount=money(row.net_cash_amount),withholding_tax_amount=money(row.withholding_amount),reference=row.reference or row.number,journal_id=journal.id,created_by=user.id)
        db.add(payment);db.flush()
        allocate_payment(db,payment,[{"open_item_id":item.id,"amount":money(row.gross_amount)}],user_id=user.id,allocation_date=row.payment_date)
    row.status="APPROVED_POSTED";row.approved_by=user.id;row.approved_at=utc_now();row.journal_id=journal.id;row.payment_id=payment.id if payment else None
    write_audit(db,action="WHT_TRANSACTION_APPROVED_POSTED",entity_type="WHT_TRANSACTION",entity_id=row.id,user_id=user.id,company_id=row.company_id,after={"journal":journal.number,"withholding":str(row.withholding_amount),"net_cash":str(row.net_cash_amount)})
    db.commit();return serialize_transaction(row)


def _return_row(db: Session, return_id: int) -> WithholdingTaxReturn:
    row=db.scalar(select(WithholdingTaxReturn).where(WithholdingTaxReturn.id==return_id).options(selectinload(WithholdingTaxReturn.lines).selectinload(WithholdingTaxReturnLine.category)))
    if not row: raise HTTPException(404,"WHT return not found")
    return row


@router.post("/returns", status_code=201)
def create_return(data: ReturnIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db,user,data.company_id,"compliance.manage")
    existing=db.scalar(select(WithholdingTaxReturn).where(WithholdingTaxReturn.company_id==data.company_id,WithholdingTaxReturn.period_start==data.period_start,WithholdingTaxReturn.period_end==data.period_end).options(selectinload(WithholdingTaxReturn.lines)))
    if existing and existing.status!="DRAFT": raise HTTPException(409,"Approved/submitted return cannot be regenerated")
    transactions=db.scalars(select(WithholdingTaxTransaction).where(WithholdingTaxTransaction.company_id==data.company_id,WithholdingTaxTransaction.payment_date>=data.period_start,WithholdingTaxTransaction.payment_date<=data.period_end,WithholdingTaxTransaction.status=="APPROVED_POSTED").options(selectinload(WithholdingTaxTransaction.category),selectinload(WithholdingTaxTransaction.beneficiary).selectinload(WithholdingBeneficiaryProfile.party)).order_by(WithholdingTaxTransaction.id)).all()
    if not transactions: raise HTTPException(422,"No approved WHT transactions in the selected month")
    if existing:
        existing.lines.clear();row=existing
    else:
        next_month=date(data.period_end.year+1,1,1) if data.period_end.month==12 else date(data.period_end.year,data.period_end.month+1,1)
        row=WithholdingTaxReturn(company_id=data.company_id,number=_number(db,WithholdingTaxReturn,data.company_id,"WHTR",data.period_end.year),period_start=data.period_start,period_end=data.period_end,due_date=next_month.replace(day=10),status="DRAFT",prepared_by=user.id)
        db.add(row);db.flush()
    grouped={}
    for t in transactions:
        bucket=grouped.setdefault(t.category_id,{"category":t.category,"gross":Decimal(0),"tax":Decimal(0),"details":[]})
        bucket["gross"]+=money(t.gross_amount);bucket["tax"]+=money(t.withholding_amount);bucket["details"].append({"transaction_id":t.id,"number":t.number,"beneficiary":t.beneficiary.party.name_en,"gross":str(money(t.gross_amount)),"rate":str(rate(t.applied_rate)),"tax":str(money(t.withholding_amount)),"dta_method":t.dta_relief_method})
    total_gross=sum((x["gross"] for x in grouped.values()),Decimal(0));total_tax=sum((x["tax"] for x in grouped.values()),Decimal(0))
    for category_id,b in grouped.items(): row.lines.append(WithholdingTaxReturnLine(category_id=category_id,gross_amount=money(b["gross"]),tax_amount=money(b["tax"]),transaction_count=len(b["details"]),details_json=json.dumps(b["details"],ensure_ascii=False)))
    journal_ids=[t.journal_id for t in transactions if t.journal_id]
    wht_account=account(db,data.company_id,"218010")
    gl=Decimal(0)
    if journal_ids:
        debit,credit=db.execute(select(func.coalesce(func.sum(JournalLine.debit),0),func.coalesce(func.sum(JournalLine.credit),0)).where(JournalLine.journal_id.in_(journal_ids),JournalLine.account_id==wht_account.id)).one();gl=money(Decimal(credit)-Decimal(debit))
    row.gross_payments=money(total_gross);row.tax_withheld=money(total_tax);row.gl_withheld=gl;row.reconciliation_difference=money(total_tax-gl);row.prepared_by=user.id
    db.flush();write_audit(db,action="WHT_RETURN_GENERATED",entity_type="WHT_RETURN",entity_id=row.id,user_id=user.id,company_id=data.company_id,after={"period":str(data.period_start),"gross":str(row.gross_payments),"tax":str(row.tax_withheld),"difference":str(row.reconciliation_difference)})
    db.commit();return serialize_return(_return_row(db,row.id))


@router.get("/returns")
def list_returns(company_id:int,as_of:date|None=None,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"compliance.read")
    rows=db.scalars(select(WithholdingTaxReturn).where(WithholdingTaxReturn.company_id==company_id).options(selectinload(WithholdingTaxReturn.lines).selectinload(WithholdingTaxReturnLine.category)).order_by(WithholdingTaxReturn.period_end.desc())).all()
    return [serialize_return(x,as_of=as_of) for x in rows]


@router.post("/returns/{return_id}/submit")
def submit_return(return_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=_return_row(db,return_id);ensure_permission(db,user,row.company_id,"compliance.manage")
    if row.status!="DRAFT":raise HTTPException(409,"Only draft returns can be submitted")
    if money(row.reconciliation_difference)!=0:raise HTTPException(409,"WHT return does not reconcile to the general ledger")
    row.status="PENDING_APPROVAL";row.submitted_by=user.id;row.submitted_at=utc_now();write_audit(db,action="WHT_RETURN_SUBMITTED",entity_type="WHT_RETURN",entity_id=row.id,user_id=user.id,company_id=row.company_id);db.commit();return serialize_return(row)


@router.post("/returns/{return_id}/approve")
def approve_return(return_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=_return_row(db,return_id);ensure_permission(db,user,row.company_id,"compliance.manage")
    if row.status!="PENDING_APPROVAL":raise HTTPException(409,"Return is not pending approval")
    _maker_checker(row.prepared_by,user.id);row.status="APPROVED";row.approved_by=user.id;row.approved_at=utc_now();write_audit(db,action="WHT_RETURN_APPROVED",entity_type="WHT_RETURN",entity_id=row.id,user_id=user.id,company_id=row.company_id);db.commit();return serialize_return(row)


@router.post("/returns/{return_id}/pay")
def pay_return(return_id:int,data:ReturnPaymentIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=_return_row(db,return_id);ensure_permission(db,user,row.company_id,"compliance.manage")
    if row.status!="APPROVED":raise HTTPException(409,"Only approved returns can be paid")
    if data.payment_date<row.period_end:raise HTTPException(422,"Payment date cannot precede the return period end")
    bank=db.scalar(select(BankAccount).where(BankAccount.id==data.bank_account_id,BankAccount.company_id==row.company_id,BankAccount.active.is_(True)))
    if not bank:raise HTTPException(422,"Bank account not found")
    liability=account(db,row.company_id,"218010")
    journal=create_posted_journal(db,company_id=row.company_id,user_id=user.id,posting_date=data.payment_date,reference=data.sadad_invoice_number,description=f"Payment of WHT return {row.number}",lines=[{"account_id":liability.id,"debit":money(row.tax_withheld),"credit":0},{"account_id":bank.gl_account_id,"debit":0,"credit":money(row.tax_withheld)}],cash_flow_activity="OPERATING",cash_flow_kind="TAX_PAYMENTS")
    row.status="PAID";row.sadad_invoice_number=data.sadad_invoice_number;row.payment_reference=data.payment_reference;row.payment_date=data.payment_date;row.payment_journal_id=journal.id;row.paid_by=user.id;row.paid_at=utc_now();write_audit(db,action="WHT_RETURN_PAID",entity_type="WHT_RETURN",entity_id=row.id,user_id=user.id,company_id=row.company_id,after={"journal":journal.number,"sadad":data.sadad_invoice_number,"amount":str(row.tax_withheld)});db.commit();return serialize_return(row)


@router.get("/transactions/{transaction_id}/certificate")
def certificate(transaction_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=db.scalar(select(WithholdingTaxTransaction).where(WithholdingTaxTransaction.id==transaction_id).options(selectinload(WithholdingTaxTransaction.beneficiary).selectinload(WithholdingBeneficiaryProfile.party),selectinload(WithholdingTaxTransaction.category)))
    if not row:raise HTTPException(404,"WHT transaction not found")
    ensure_permission(db,user,row.company_id,"compliance.read")
    tax_return=db.scalar(select(WithholdingTaxReturn).where(WithholdingTaxReturn.company_id==row.company_id,WithholdingTaxReturn.period_start<=row.payment_date,WithholdingTaxReturn.period_end>=row.payment_date,WithholdingTaxReturn.status=="PAID"))
    eligible=bool(row.status=="APPROVED_POSTED" and tax_return)
    return {"eligible":eligible,"status":"ISSUABLE" if eligible else "PENDING_RETURN_PAYMENT","certificate_number":f"WHTC-{row.company_id}-{row.payment_date.year}-{row.id:08d}" if eligible else None,"transaction_number":row.number,"beneficiary":{"code":row.beneficiary.party.code,"name_ar":row.beneficiary.party.name_ar,"name_en":row.beneficiary.party.name_en,"country":row.beneficiary.country_code,"foreign_tax_id":row.beneficiary.foreign_tax_id},"payment_date":row.payment_date,"income_type":row.category.income_type,"gross_amount":money(row.gross_amount),"applied_rate":rate(row.applied_rate),"tax_withheld":money(row.withholding_amount),"return_number":tax_return.number if tax_return else None,"sadad_invoice_number":tax_return.sadad_invoice_number if tax_return else None,"note":"Internal certificate evidence; official ZATCA certificate remains subject to portal issuance and verification."}


@router.get("/export/transactions.csv")
def export_transactions(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=list_transactions(company_id,user=user,db=db)
    return _csv("withholding_tax_transactions.csv",["Number","Payment date","Beneficiary","Country","Category","Gross amount","Statutory rate","Applied rate","Tax withheld","Net cash","DTA method","Status","Journal ID"],[[x["number"],x["payment_date"],x["beneficiary_name_en"],x["country_code"],x["category_code"],x["gross_amount"],x["statutory_rate"],x["applied_rate"],x["withholding_amount"],x["net_cash_amount"],x["dta_relief_method"],x["status"],x["journal_id"]] for x in rows])


@router.get("/export/returns.csv")
def export_returns(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=list_returns(company_id,user=user,db=db)
    return _csv("withholding_tax_returns.csv",["Number","Period start","Period end","Due date","Gross payments","Tax withheld","GL withheld","Difference","Status","SADAD invoice","Payment date"],[[x["number"],x["period_start"],x["period_end"],x["due_date"],x["gross_payments"],x["tax_withheld"],x["gl_withheld"],x["reconciliation_difference"],x["status"],x["sadad_invoice_number"],x["payment_date"]] for x in rows])
