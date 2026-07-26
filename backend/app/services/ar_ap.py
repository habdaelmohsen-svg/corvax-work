from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CreditNoteApplication, FinancialOpenItem, FinancialSettlementAllocation, JournalEntry, Party, Payment,
    PurchaseInvoice, Receipt, SalesInvoice,
)

MONEY = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def ensure_sales_invoice_open_item(db: Session, invoice: SalesInvoice) -> FinancialOpenItem:
    row = db.scalar(select(FinancialOpenItem).where(
        FinancialOpenItem.company_id == invoice.company_id,
        FinancialOpenItem.ledger_type == "AR",
        FinancialOpenItem.source_type == "SALES_INVOICE",
        FinancialOpenItem.source_id == invoice.id,
    ))
    if row:
        return row
    row = FinancialOpenItem(
        company_id=invoice.company_id, ledger_type="AR", party_id=invoice.customer_id,
        source_type="SALES_INVOICE", source_id=invoice.id, document_number=invoice.number,
        document_date=invoice.invoice_date, due_date=invoice.due_date, original_amount=money(invoice.total),
        status="OPEN", journal_id=invoice.journal_id, created_by=invoice.created_by,
    )
    db.add(row)
    db.flush()
    return row


def ensure_purchase_invoice_open_item(db: Session, invoice: PurchaseInvoice) -> FinancialOpenItem:
    row = db.scalar(select(FinancialOpenItem).where(
        FinancialOpenItem.company_id == invoice.company_id,
        FinancialOpenItem.ledger_type == "AP",
        FinancialOpenItem.source_type == "PURCHASE_INVOICE",
        FinancialOpenItem.source_id == invoice.id,
    ))
    if row:
        return row
    row = FinancialOpenItem(
        company_id=invoice.company_id, ledger_type="AP", party_id=invoice.supplier_id,
        source_type="PURCHASE_INVOICE", source_id=invoice.id, document_number=invoice.number,
        document_date=invoice.invoice_date, due_date=invoice.due_date, original_amount=money(invoice.total),
        status="OPEN", journal_id=invoice.journal_id, created_by=invoice.created_by,
    )
    db.add(row)
    db.flush()
    return row


def active_allocation_total(db: Session, open_item_id: int, as_of_date: date | None = None) -> Decimal:
    query = select(func.coalesce(func.sum(FinancialSettlementAllocation.amount), 0)).where(
        FinancialSettlementAllocation.open_item_id == open_item_id,
        FinancialSettlementAllocation.reversed_at.is_(None),
    )
    if as_of_date:
        query = query.where(FinancialSettlementAllocation.allocation_date <= as_of_date)
    return money(db.scalar(query) or 0)


def active_credit_note_total(db: Session, open_item_id: int, as_of_date: date | None = None) -> Decimal:
    query = select(func.coalesce(func.sum(CreditNoteApplication.amount), 0)).where(
        CreditNoteApplication.open_item_id == open_item_id,
    )
    if as_of_date:
        query = query.where(CreditNoteApplication.application_date <= as_of_date)
    return money(db.scalar(query) or 0)


def open_amount(db: Session, item: FinancialOpenItem, as_of_date: date | None = None) -> Decimal:
    settled = active_allocation_total(db, item.id, as_of_date) + active_credit_note_total(db, item.id, as_of_date)
    return money(max(Decimal("0"), money(item.original_amount) - settled))


def settlement_allocated_total(db: Session, *, receipt_id: int | None = None, payment_id: int | None = None, as_of_date: date | None = None) -> Decimal:
    query = select(func.coalesce(func.sum(FinancialSettlementAllocation.amount), 0)).where(
        FinancialSettlementAllocation.reversed_at.is_(None)
    )
    if receipt_id is not None:
        query = query.where(FinancialSettlementAllocation.receipt_id == receipt_id)
    elif payment_id is not None:
        query = query.where(FinancialSettlementAllocation.payment_id == payment_id)
    else:
        raise ValueError("receipt_id or payment_id is required")
    if as_of_date:
        query = query.where(FinancialSettlementAllocation.allocation_date <= as_of_date)
    return money(db.scalar(query) or 0)


def refresh_open_item_status(db: Session, item: FinancialOpenItem) -> None:
    remaining = open_amount(db, item)
    if remaining == 0:
        item.status = "CLOSED"
    elif remaining < money(item.original_amount):
        item.status = "PARTIAL"
    else:
        item.status = "OPEN"


def allocate_receipt(db: Session, receipt: Receipt, allocations: list[dict], *, user_id: int, allocation_date: date | None = None) -> list[FinancialSettlementAllocation]:
    effective_date = allocation_date or receipt.receipt_date
    if effective_date < receipt.receipt_date:
        raise HTTPException(422, "Allocation date cannot be before receipt date")
    requested = money(sum((money(line["amount"]) for line in allocations), Decimal("0")))
    available = money(receipt.amount) - settlement_allocated_total(db, receipt_id=receipt.id)
    if requested <= 0 or requested > available:
        raise HTTPException(409, f"Receipt allocation exceeds unapplied amount {available}")
    rows = []
    seen: set[int] = set()
    for line in allocations:
        item_id = int(line["open_item_id"])
        if item_id in seen:
            raise HTTPException(422, "Duplicate open item in allocation request")
        seen.add(item_id)
        item = db.get(FinancialOpenItem, item_id)
        amount = money(line["amount"])
        if not item or item.company_id != receipt.company_id or item.ledger_type != "AR" or item.party_id != receipt.customer_id:
            raise HTTPException(422, "AR open item does not belong to the receipt customer/company")
        if item.document_date > effective_date:
            raise HTTPException(422, "Cannot allocate a receipt before the invoice date")
        remaining = open_amount(db, item)
        if amount <= 0 or amount > remaining:
            raise HTTPException(409, f"Allocation exceeds open amount {remaining} for {item.document_number}")
        row = FinancialSettlementAllocation(
            company_id=receipt.company_id, open_item_id=item.id, receipt_id=receipt.id,
            allocation_date=effective_date, amount=amount, created_by=user_id,
        )
        db.add(row); db.flush(); rows.append(row)
        refresh_open_item_status(db, item)
    return rows


def allocate_payment(db: Session, payment: Payment, allocations: list[dict], *, user_id: int, allocation_date: date | None = None) -> list[FinancialSettlementAllocation]:
    effective_date = allocation_date or payment.payment_date
    if effective_date < payment.payment_date:
        raise HTTPException(422, "Allocation date cannot be before payment date")
    requested = money(sum((money(line["amount"]) for line in allocations), Decimal("0")))
    available = money(payment.amount) - settlement_allocated_total(db, payment_id=payment.id)
    if requested <= 0 or requested > available:
        raise HTTPException(409, f"Payment allocation exceeds unapplied amount {available}")
    rows = []
    seen: set[int] = set()
    for line in allocations:
        item_id = int(line["open_item_id"])
        if item_id in seen:
            raise HTTPException(422, "Duplicate open item in allocation request")
        seen.add(item_id)
        item = db.get(FinancialOpenItem, item_id)
        amount = money(line["amount"])
        if not item or item.company_id != payment.company_id or item.ledger_type != "AP" or item.party_id != payment.supplier_id:
            raise HTTPException(422, "AP open item does not belong to the payment supplier/company")
        if item.document_date > effective_date:
            raise HTTPException(422, "Cannot allocate a payment before the invoice date")
        remaining = open_amount(db, item)
        if amount <= 0 or amount > remaining:
            raise HTTPException(409, f"Allocation exceeds open amount {remaining} for {item.document_number}")
        row = FinancialSettlementAllocation(
            company_id=payment.company_id, open_item_id=item.id, payment_id=payment.id,
            allocation_date=effective_date, amount=amount, created_by=user_id,
        )
        db.add(row); db.flush(); rows.append(row)
        refresh_open_item_status(db, item)
    return rows


def serialize_open_item(db: Session, item: FinancialOpenItem, as_of_date: date | None = None) -> dict:
    cash_allocated = active_allocation_total(db, item.id, as_of_date)
    credit_applied = active_credit_note_total(db, item.id, as_of_date)
    allocated = money(cash_allocated + credit_applied)
    outstanding = money(max(Decimal("0"), money(item.original_amount) - allocated))
    return {
        "id": item.id, "company_id": item.company_id, "ledger_type": item.ledger_type,
        "party_id": item.party_id, "party_code": item.party.code, "party_name_ar": item.party.name_ar,
        "party_name_en": item.party.name_en, "source_type": item.source_type, "source_id": item.source_id,
        "document_number": item.document_number, "document_date": item.document_date, "due_date": item.due_date,
        "original_amount": money(item.original_amount), "allocated_amount": allocated,
        "cash_allocated_amount": cash_allocated, "credit_note_applied_amount": credit_applied,
        "outstanding_amount": outstanding,
        "status": "CLOSED" if outstanding == 0 else ("PARTIAL" if allocated > 0 else "OPEN"),
        "journal_id": item.journal_id, "notes": item.notes,
    }
