"""CORVAX RC27.4 H11 - Sales commission API (inside the Sales department).

Endpoints (prefix /sales-commissions):
  Beneficiaries:  POST/GET  /beneficiaries
  Accruals:       POST      /accruals                 (accrue commission on a posted sales invoice)
                  GET       /accruals                 (list, with live collected ratio)
                  POST      /accruals/{id}/refresh     (recompute payable from current collections)
                  POST      /accruals/{id}/approve     (manager approval, required before pay)
                  POST      /accruals/{id}/pay         (pay approved commission via bank)
  Summary:        GET       /summary

Accounting:
  On accrual (invoice posted):
      Dr 627010 Sales Commission Expense
      Cr 217030 Sales Commissions Payable         (full earned amount, PENDING)
  Payable amount unlocks in proportion to how much of the invoice has been collected.
  On payment (after approval):
      Dr 217030 Sales Commissions Payable
      Cr bank GL account
Numbering uses func.extract('year', ...) (portable across SQLite and PostgreSQL).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BankAccount, FinancialOpenItem, FinancialSettlementAllocation, SalesInvoice, User,
)
from app.models.sales_commissions import CommissionAccrual, CommissionBeneficiary
from app.services.audit import write_audit
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/sales-commissions", tags=["sales commissions"])

EXPENSE_CODE = "627010"
PAYABLE_CODE = "217030"


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _account(db: Session, company_id: int, code: str) -> Account:
    acc = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code, Account.active.is_(True)))
    if not acc or not acc.is_postable:
        raise HTTPException(422, f"Postable account not found: {code}")
    return acc


# Definitions for the two commission accounts, so the API can self-heal if a
# company's chart predates H11 (e.g. migration ran before the company was seeded).
_COMMISSION_ACCOUNTS = {
    "627010": ("مصروف عمولات المبيعات", "Sales Commission Expense", "EXPENSE", "OPERATING_EXPENSES", "600000"),
    "217030": ("عمولات مبيعات مستحقة", "Sales Commissions Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000"),
}


def _ensure_commission_account(db: Session, company_id: int, code: str) -> Account:
    acc = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code))
    if acc and acc.is_postable and acc.active:
        return acc
    if acc:
        return acc  # exists but perhaps not postable; let _account surface the error
    name_ar, name_en, acc_type, group, parent_code = _COMMISSION_ACCOUNTS[code]
    parent = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == parent_code))
    acc = Account(
        company_id=company_id, code=code, name_ar=name_ar, name_en=name_en,
        account_type=acc_type, statement_group=group, parent_id=parent.id if parent else None,
        level=3, is_postable=True, is_cash=False, active=True,
    )
    db.add(acc); db.flush()
    return acc


def _next_number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(
        select(func.count(CommissionAccrual.id)).where(
            CommissionAccrual.company_id == company_id,
            func.extract("year", CommissionAccrual.created_at) == year,
        )
    ) or 0
    return f"COM-{company_id}-{year}-{count + 1:05d}"


def _collected_ratio(db: Session, invoice: SalesInvoice) -> Decimal:
    """Portion (0..1) of the invoice that has been collected, via settlement allocations."""
    open_item = db.scalar(
        select(FinancialOpenItem).where(
            FinancialOpenItem.company_id == invoice.company_id,
            FinancialOpenItem.source_type == "SALES_INVOICE",
            FinancialOpenItem.source_id == invoice.id,
        )
    )
    if not open_item or not open_item.original_amount:
        return Decimal("0")
    allocated = db.scalar(
        select(func.coalesce(func.sum(FinancialSettlementAllocation.amount), 0)).where(
            FinancialSettlementAllocation.open_item_id == open_item.id,
            FinancialSettlementAllocation.receipt_id.is_not(None),
            FinancialSettlementAllocation.reversed_at.is_(None),
        )
    ) or 0
    ratio = Decimal(str(allocated)) / Decimal(str(open_item.original_amount))
    if ratio < 0:
        ratio = Decimal("0")
    if ratio > 1:
        ratio = Decimal("1")
    return ratio.quantize(Decimal("0.0001"))


def _refresh(db: Session, accrual: CommissionAccrual) -> None:
    """Recompute collected ratio and unlock payable amount. Does not change PAID/CANCELLED."""
    if accrual.status in ("PAID", "CANCELLED"):
        return
    ratio = _collected_ratio(db, accrual.invoice)
    accrual.collected_ratio = ratio
    accrual.payable_amount = _money(Decimal(str(accrual.amount)) * ratio)
    if accrual.status == "APPROVED":
        return  # keep approval; payable may have grown but approval stands
    if ratio >= 1:
        accrual.status = "PAYABLE"
    elif ratio > 0:
        accrual.status = "PARTIAL"
    else:
        accrual.status = "PENDING"


# ============================================================ BENEFICIARIES
class BeneficiaryIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=40)
    name_ar: str
    name_en: str
    beneficiary_type: str = "SALES_REP"  # SALES_REP / BROKER
    default_basis: str = "PERCENTAGE"     # PERCENTAGE / FIXED
    default_rate: float = 0
    phone: str | None = None


@router.post("/beneficiaries", status_code=201)
def create_beneficiary(data: BeneficiaryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "sales.commissions.manage")
    if data.beneficiary_type not in ("SALES_REP", "BROKER"):
        raise HTTPException(422, "beneficiary_type must be SALES_REP or BROKER")
    if data.default_basis not in ("PERCENTAGE", "FIXED"):
        raise HTTPException(422, "default_basis must be PERCENTAGE or FIXED")
    dup = db.scalar(select(CommissionBeneficiary).where(CommissionBeneficiary.company_id == data.company_id, CommissionBeneficiary.code == data.code))
    if dup:
        raise HTTPException(409, "Beneficiary code already exists")
    b = CommissionBeneficiary(**data.model_dump())
    db.add(b); db.flush()
    write_audit(db, action="COMMISSION_BENEFICIARY_CREATED", entity_type="COMMISSION_BENEFICIARY", entity_id=b.id, user_id=user.id, company_id=data.company_id, after={"code": b.code, "type": b.beneficiary_type})
    db.commit()
    return {"id": b.id, "code": b.code, "name_ar": b.name_ar, "beneficiary_type": b.beneficiary_type}


@router.get("/beneficiaries")
def list_beneficiaries(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "sales.commissions.read")
    rows = db.scalars(select(CommissionBeneficiary).where(CommissionBeneficiary.company_id == company_id).order_by(CommissionBeneficiary.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "beneficiary_type": r.beneficiary_type,
             "default_basis": r.default_basis, "default_rate": r.default_rate, "phone": r.phone, "active": r.active} for r in rows]


# ============================================================ ACCRUALS
class AccrualIn(BaseModel):
    company_id: int
    beneficiary_id: int
    sales_invoice_id: int
    # Optional overrides; if omitted, the beneficiary's default rule is used.
    basis: str | None = None       # PERCENTAGE / FIXED
    rate: float | None = None
    notes: str | None = None


@router.post("/accruals", status_code=201)
def create_accrual(data: AccrualIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "sales.commissions.manage")
    beneficiary = db.scalar(select(CommissionBeneficiary).where(CommissionBeneficiary.id == data.beneficiary_id, CommissionBeneficiary.company_id == data.company_id))
    if not beneficiary:
        raise HTTPException(404, "Beneficiary not found")
    invoice = db.scalar(select(SalesInvoice).where(SalesInvoice.id == data.sales_invoice_id, SalesInvoice.company_id == data.company_id))
    if not invoice:
        raise HTTPException(404, "Sales invoice not found")
    if invoice.status != "POSTED":
        raise HTTPException(409, "Commission can only be accrued on a posted sales invoice")
    dup = db.scalar(select(CommissionAccrual).where(
        CommissionAccrual.company_id == data.company_id,
        CommissionAccrual.beneficiary_id == data.beneficiary_id,
        CommissionAccrual.sales_invoice_id == data.sales_invoice_id,
        CommissionAccrual.status != "CANCELLED",
    ))
    if dup:
        raise HTTPException(409, "Commission already accrued for this beneficiary and invoice")

    basis = (data.basis or beneficiary.default_basis).upper()
    rate = Decimal(str(data.rate if data.rate is not None else beneficiary.default_rate))
    if basis not in ("PERCENTAGE", "FIXED"):
        raise HTTPException(422, "basis must be PERCENTAGE or FIXED")
    base_amount = Decimal(str(invoice.subtotal))  # commission on net sale, excluding VAT
    if basis == "PERCENTAGE":
        amount = _money(base_amount * rate / Decimal("100"))
    else:
        amount = _money(rate)
    if amount <= 0:
        raise HTTPException(422, "Computed commission amount must be positive")

    expense = _ensure_commission_account(db, data.company_id, EXPENSE_CODE)
    payable = _ensure_commission_account(db, data.company_id, PAYABLE_CODE)
    accrual = CommissionAccrual(
        company_id=data.company_id,
        number=_next_number(db, data.company_id, date.today().year),
        beneficiary_id=beneficiary.id, sales_invoice_id=invoice.id,
        basis=basis, rate=rate, invoice_base_amount=base_amount, amount=amount,
        collected_ratio=Decimal("0"), payable_amount=Decimal("0"), paid_amount=Decimal("0"),
        status="PENDING", notes=data.notes, created_by=user.id,
    )
    # Accrual journal: Dr expense / Cr payable (full earned amount).
    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=invoice.invoice_date,
        reference=accrual.number, description=f"Commission accrual {accrual.number} on {invoice.number}",
        lines=[
            {"account_id": expense.id, "debit": amount, "credit": 0, "description": f"Commission {beneficiary.code}"},
            {"account_id": payable.id, "debit": 0, "credit": amount, "description": f"Commission payable {beneficiary.code}"},
        ],
    )
    accrual.accrual_journal_id = journal.id
    db.add(accrual); db.flush()
    # Immediately reflect any collection that already happened on the invoice.
    _refresh(db, accrual)
    write_audit(db, action="COMMISSION_ACCRUED", entity_type="COMMISSION_ACCRUAL", entity_id=accrual.id, user_id=user.id, company_id=data.company_id, after={"number": accrual.number, "amount": str(amount), "journal": journal.number})
    db.commit()
    return {"id": accrual.id, "number": accrual.number, "amount": accrual.amount,
            "collected_ratio": accrual.collected_ratio, "payable_amount": accrual.payable_amount,
            "status": accrual.status, "journal_number": journal.number}


@router.get("/accruals")
def list_accruals(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "sales.commissions.read")
    rows = db.scalars(select(CommissionAccrual).where(CommissionAccrual.company_id == company_id).order_by(CommissionAccrual.id.desc())).all()
    result = []
    for r in rows:
        # live ratio for display without persisting
        live_ratio = _collected_ratio(db, r.invoice) if r.status not in ("PAID", "CANCELLED") else r.collected_ratio
        result.append({
            "id": r.id, "number": r.number,
            "beneficiary_name_ar": r.beneficiary.name_ar if r.beneficiary else None,
            "beneficiary_type": r.beneficiary.beneficiary_type if r.beneficiary else None,
            "invoice_number": r.invoice.number if r.invoice else None,
            "basis": r.basis, "rate": r.rate, "amount": r.amount,
            "collected_ratio": live_ratio, "payable_amount": r.payable_amount,
            "paid_amount": r.paid_amount, "status": r.status,
        })
    return result


@router.post("/accruals/{accrual_id}/refresh")
def refresh_accrual(accrual_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "sales.commissions.manage")
    accrual = db.scalar(select(CommissionAccrual).where(CommissionAccrual.id == accrual_id, CommissionAccrual.company_id == company_id))
    if not accrual:
        raise HTTPException(404, "Accrual not found")
    _refresh(db, accrual)
    db.commit()
    return {"id": accrual.id, "collected_ratio": accrual.collected_ratio, "payable_amount": accrual.payable_amount, "status": accrual.status}


@router.post("/accruals/{accrual_id}/approve")
def approve_accrual(accrual_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "sales.commissions.approve")
    accrual = db.scalar(select(CommissionAccrual).where(CommissionAccrual.id == accrual_id, CommissionAccrual.company_id == company_id))
    if not accrual:
        raise HTTPException(404, "Accrual not found")
    _refresh(db, accrual)
    if accrual.payable_amount <= 0:
        raise HTTPException(409, "Nothing payable yet - invoice not collected")
    # Segregation of duties: approver cannot be the person who created the accrual.
    if accrual.created_by == user.id:
        raise HTTPException(403, "Approver must be different from the preparer")
    accrual.status = "APPROVED"
    accrual.approved_by = user.id
    from app.core.time import utc_now
    accrual.approved_at = utc_now()
    write_audit(db, action="COMMISSION_APPROVED", entity_type="COMMISSION_ACCRUAL", entity_id=accrual.id, user_id=user.id, company_id=company_id, after={"payable": str(accrual.payable_amount)})
    db.commit()
    return {"id": accrual.id, "status": accrual.status, "payable_amount": accrual.payable_amount}


class PayIn(BaseModel):
    company_id: int
    bank_account_id: int


@router.post("/accruals/{accrual_id}/pay")
def pay_accrual(accrual_id: int, data: PayIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "sales.commissions.approve")
    accrual = db.scalar(select(CommissionAccrual).where(CommissionAccrual.id == accrual_id, CommissionAccrual.company_id == data.company_id))
    if not accrual:
        raise HTTPException(404, "Accrual not found")
    if accrual.status != "APPROVED":
        raise HTTPException(409, "Commission must be APPROVED before payment")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id))
    if not bank:
        raise HTTPException(404, "Bank account not found")
    pay_amount = _money(Decimal(str(accrual.payable_amount)) - Decimal(str(accrual.paid_amount)))
    if pay_amount <= 0:
        raise HTTPException(409, "Nothing left to pay")
    payable = _ensure_commission_account(db, data.company_id, PAYABLE_CODE)
    if not bank.gl_account_id:
        raise HTTPException(422, "Bank account has no linked GL account")
    journal_bank_id = bank.gl_account_id
    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=date.today(),
        reference=accrual.number, description=f"Commission payment {accrual.number}",
        lines=[
            {"account_id": payable.id, "debit": pay_amount, "credit": 0, "description": "Commission payable settled"},
            {"account_id": journal_bank_id, "debit": 0, "credit": pay_amount, "description": "Commission paid"},
        ],
    )
    accrual.paid_amount = _money(Decimal(str(accrual.paid_amount)) + pay_amount)
    accrual.paid_journal_id = journal.id
    accrual.status = "PAID"
    write_audit(db, action="COMMISSION_PAID", entity_type="COMMISSION_ACCRUAL", entity_id=accrual.id, user_id=user.id, company_id=data.company_id, after={"paid": str(pay_amount), "journal": journal.number})
    db.commit()
    return {"id": accrual.id, "status": accrual.status, "paid_amount": accrual.paid_amount, "journal_number": journal.number}


@router.get("/summary")
def commission_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "sales.commissions.read")
    rows = db.scalars(select(CommissionAccrual).where(CommissionAccrual.company_id == company_id)).all()
    total_accrued = sum((Decimal(str(r.amount)) for r in rows), Decimal("0"))
    total_payable = sum((Decimal(str(r.payable_amount)) for r in rows if r.status in ("PARTIAL", "PAYABLE", "APPROVED")), Decimal("0"))
    total_paid = sum((Decimal(str(r.paid_amount)) for r in rows), Decimal("0"))
    return {
        "beneficiaries": db.scalar(select(func.count(CommissionBeneficiary.id)).where(CommissionBeneficiary.company_id == company_id)) or 0,
        "accruals": len(rows),
        "total_accrued": _money(total_accrued),
        "total_payable": _money(total_payable),
        "total_paid": _money(total_paid),
        "pending_approval": sum(1 for r in rows if r.status in ("PARTIAL", "PAYABLE")),
    }
