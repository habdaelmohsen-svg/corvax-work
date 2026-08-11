from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BankAccount, CreditNote, CreditNoteApplication, CreditNoteLine, FinancialOpenItem, Item,
    JournalEntry, PartyCreditBalance, PurchaseInvoice, PurchaseInvoiceLine, SalesInvoice,
    SalesInvoiceLine, StockMovement, TaxCode, User, VatReturnSnapshot, Warehouse,
)
from app.services.ar_ap import open_amount, refresh_open_item_status
from app.services.audit import write_audit
from app.services.operations import stock_balance, stock_value
from app.services.posting import create_posted_journal, ensure_open_period
from app.services.tax import calculate_line, get_tax_code

router = APIRouter(prefix="/credit-notes", tags=["sales purchase returns and VAT adjustments"])
MONEY = Decimal("0.01")
QTY = Decimal("0.0001")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def quantity(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY, rounding=ROUND_HALF_UP)


def get_account(db: Session, company_id: int, code: str) -> Account:
    row = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code, Account.active.is_(True)))
    if not row or not row.is_postable:
        raise HTTPException(422, f"Account is missing or non-postable: {code}")
    return row


def note_number(db: Session, company_id: int, note_type: str, note_date: date) -> str:
    prefix = "SCN" if note_type == "SALES" else "PCN"
    count = db.scalar(select(func.count(CreditNote.id)).where(CreditNote.company_id == company_id, CreditNote.note_type == note_type)) or 0
    return f"{prefix}-{company_id}-{note_date.year}-{count + 1:06d}"


class CreditNoteLineIn(BaseModel):
    original_line_id: int
    quantity: Decimal = Field(gt=0)
    item_id: int | None = None
    warehouse_id: int | None = None
    inventory_disposition: str = "NONE"

    @model_validator(mode="after")
    def validate_inventory(self):
        self.inventory_disposition = self.inventory_disposition.upper()
        allowed = {"NONE", "RETURN_TO_STOCK", "QUARANTINE", "DAMAGED", "RETURN_TO_SUPPLIER"}
        if self.inventory_disposition not in allowed:
            raise ValueError("Invalid inventory disposition")
        if self.inventory_disposition != "NONE" and (not self.item_id or not self.warehouse_id):
            raise ValueError("item_id and warehouse_id are required for inventory processing")
        return self


class CreditNoteIn(BaseModel):
    company_id: int
    note_type: str = Field(pattern="^(SALES|PURCHASE)$")
    note_date: date
    original_invoice_id: int
    reason_code: str = Field(min_length=2, max_length=30)
    reason: str = Field(min_length=3, max_length=500)
    external_reference: str | None = Field(default=None, max_length=100)
    lines: list[CreditNoteLineIn] = Field(min_length=1)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CreditBalanceApplyIn(BaseModel):
    open_item_id: int
    amount: Decimal = Field(gt=0)
    application_date: date


class CreditBalanceCashIn(BaseModel):
    bank_account_id: int
    amount: Decimal = Field(gt=0)
    settlement_date: date
    reference: str = Field(min_length=2, max_length=100)


def serialize(row: CreditNote) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number, "note_date": row.note_date,
        "note_type": row.note_type, "original_invoice_id": row.original_sales_invoice_id or row.original_purchase_invoice_id,
        "original_document_number": row.original_document_number, "original_document_date": row.original_document_date,
        "party_id": row.party_id, "party_code": row.party.code if row.party else None,
        "party_name_ar": row.party.name_ar if row.party else None, "party_name_en": row.party.name_en if row.party else None,
        "reason_code": row.reason_code, "reason": row.reason, "external_reference": row.external_reference, "status": row.status,
        "subtotal": money(row.subtotal), "vat_amount": money(row.vat_amount), "total": money(row.total),
        "unapplied_credit": money(row.unapplied_credit), "journal_id": row.journal_id, "zatca_uuid": row.zatca_uuid,
        "created_by": row.created_by, "submitted_by": row.submitted_by, "approved_by": row.approved_by,
        "lines": [{
            "id": x.id, "original_line_id": x.original_sales_invoice_line_id or x.original_purchase_invoice_line_id,
            "description": x.description, "account_code": x.account.code if x.account else None,
            "tax_code": x.tax_code.code if x.tax_code else None, "quantity": x.quantity, "unit_price": x.unit_price,
            "subtotal": x.subtotal, "vat_amount": x.vat_amount, "total": x.total,
            "item_id": x.item_id, "warehouse_id": x.warehouse_id, "inventory_disposition": x.inventory_disposition,
            "unit_cost": x.unit_cost, "inventory_value": x.inventory_value,
        } for x in row.lines],
        "applications": [{"open_item_id": x.open_item_id, "application_date": x.application_date, "amount": x.amount} for x in row.applications],
    }


def get_note(db: Session, note_id: int) -> CreditNote:
    row = db.scalar(select(CreditNote).where(CreditNote.id == note_id).options(
        selectinload(CreditNote.lines).selectinload(CreditNoteLine.account),
        selectinload(CreditNote.lines).selectinload(CreditNoteLine.tax_code),
        selectinload(CreditNote.applications),
        selectinload(CreditNote.party),
    ))
    if not row:
        raise HTTPException(404, "Credit note not found")
    return row


def previously_credited_quantity(db: Session, note_type: str, original_line_id: int) -> Decimal:
    line_fk = CreditNoteLine.original_sales_invoice_line_id if note_type == "SALES" else CreditNoteLine.original_purchase_invoice_line_id
    total = db.scalar(select(func.coalesce(func.sum(CreditNoteLine.quantity), 0)).join(CreditNote).where(
        line_fk == original_line_id,
        CreditNote.status.notin_(["REJECTED"]),
    )) or 0
    return quantity(total)


@router.post("", status_code=201)
def create_credit_note(data: CreditNoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "journals.create")
    ensure_open_period(db, data.company_id, data.note_date)
    if data.note_type == "SALES":
        invoice = db.scalar(select(SalesInvoice).where(SalesInvoice.id == data.original_invoice_id, SalesInvoice.company_id == data.company_id).options(selectinload(SalesInvoice.lines)))
        if not invoice or invoice.status != "POSTED":
            raise HTTPException(422, "Original posted sales invoice not found")
        party_id, original_number, original_date = invoice.customer_id, invoice.number, invoice.invoice_date
        original_lines = {x.id: x for x in invoice.lines}
    else:
        invoice = db.scalar(select(PurchaseInvoice).where(PurchaseInvoice.id == data.original_invoice_id, PurchaseInvoice.company_id == data.company_id).options(selectinload(PurchaseInvoice.lines)))
        if not invoice or invoice.status != "POSTED":
            raise HTTPException(422, "Original posted purchase invoice not found")
        party_id, original_number, original_date = invoice.supplier_id, invoice.number, invoice.invoice_date
        original_lines = {x.id: x for x in invoice.lines}
    if data.note_date < original_date:
        raise HTTPException(422, "Credit note date cannot be before the original invoice date")

    note = CreditNote(
        company_id=data.company_id, number=note_number(db, data.company_id, data.note_type, data.note_date),
        note_date=data.note_date, note_type=data.note_type,
        original_sales_invoice_id=data.original_invoice_id if data.note_type == "SALES" else None,
        original_purchase_invoice_id=data.original_invoice_id if data.note_type == "PURCHASE" else None,
        party_id=party_id, reason_code=data.reason_code.upper(), reason=data.reason, external_reference=data.external_reference,
        status="DRAFT", zatca_uuid=str(uuid.uuid4()), original_document_number=original_number,
        original_document_date=original_date, created_by=user.id,
    )
    subtotal = vat = total = Decimal("0")
    seen: set[int] = set()
    for request_line in data.lines:
        if request_line.original_line_id in seen:
            raise HTTPException(422, "Duplicate original invoice line")
        seen.add(request_line.original_line_id)
        original = original_lines.get(request_line.original_line_id)
        if not original:
            raise HTTPException(422, "Original invoice line does not belong to the selected invoice")
        prior = previously_credited_quantity(db, data.note_type, original.id)
        available = quantity(Decimal(original.quantity) - prior)
        qty = quantity(request_line.quantity)
        if qty > available:
            raise HTTPException(409, f"Return quantity exceeds available quantity {available}")
        ratio = qty / Decimal(original.quantity)
        line_subtotal = money(Decimal(original.subtotal) * ratio)
        line_vat = money(Decimal(original.vat_amount) * ratio)
        line_total = money(Decimal(original.total) * ratio)
        tax_code = original.tax_code or get_tax_code(db, data.company_id, code=None, direction=data.note_type, vat_rate=Decimal(original.vat_rate), user_id=user.id)
        account_id = original.revenue_account_id if data.note_type == "SALES" else original.expense_account_id
        unit_cost = inventory_value = Decimal("0")
        if request_line.inventory_disposition != "NONE":
            item = db.scalar(select(Item).where(Item.id == request_line.item_id, Item.company_id == data.company_id, Item.active.is_(True)))
            warehouse = db.scalar(select(Warehouse).where(Warehouse.id == request_line.warehouse_id, Warehouse.company_id == data.company_id, Warehouse.active.is_(True)))
            if not item or not warehouse:
                raise HTTPException(422, "Inventory item or warehouse not found")
            if data.note_type == "SALES" and request_line.inventory_disposition == "RETURN_TO_SUPPLIER":
                raise HTTPException(422, "Sales return cannot use RETURN_TO_SUPPLIER")
            if data.note_type == "PURCHASE" and request_line.inventory_disposition not in {"RETURN_TO_SUPPLIER", "NONE"}:
                raise HTTPException(422, "Purchase return inventory disposition must be RETURN_TO_SUPPLIER")
            bal = Decimal(stock_balance(db, data.company_id, warehouse.id, item.id))
            val = Decimal(stock_value(db, data.company_id, warehouse.id, item.id))
            unit_cost = money(val / bal) if bal > 0 else money(item.standard_cost)
            if data.note_type == "PURCHASE" and qty > bal:
                raise HTTPException(409, f"Purchase return exceeds stock balance {bal}")
            inventory_value = money(qty * unit_cost)
        note.lines.append(CreditNoteLine(
            original_sales_invoice_line_id=original.id if data.note_type == "SALES" else None,
            original_purchase_invoice_line_id=original.id if data.note_type == "PURCHASE" else None,
            description=original.description, account_id=account_id, tax_code_id=tax_code.id,
            quantity=qty, unit_price=original.unit_price, subtotal=line_subtotal, vat_amount=line_vat, total=line_total,
            item_id=request_line.item_id, warehouse_id=request_line.warehouse_id,
            inventory_disposition=request_line.inventory_disposition, unit_cost=unit_cost, inventory_value=inventory_value,
        ))
        subtotal += line_subtotal; vat += line_vat; total += line_total
    note.subtotal, note.vat_amount, note.total = money(subtotal), money(vat), money(total)
    db.add(note); db.flush()
    write_audit(db, action="CREDIT_NOTE_CREATED", entity_type="CREDIT_NOTE", entity_id=note.id, user_id=user.id, company_id=note.company_id,
                after={"number": note.number, "type": note.note_type, "original": note.original_document_number, "total": str(note.total)})
    db.commit()
    return serialize(get_note(db, note.id))


@router.get("")
def list_credit_notes(company_id: int, note_type: str | None = None, status: str | None = None,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    query = select(CreditNote).where(CreditNote.company_id == company_id).options(selectinload(CreditNote.lines), selectinload(CreditNote.applications)).order_by(CreditNote.note_date.desc(), CreditNote.id.desc())
    if note_type: query = query.where(CreditNote.note_type == note_type.upper())
    if status: query = query.where(CreditNote.status == status.upper())
    return [serialize(x) for x in db.scalars(query).all()]


@router.get("/eligible-invoices")
def eligible_invoices(company_id: int, note_type: str = Query(pattern="^(SALES|PURCHASE)$"),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    note_type = note_type.upper()
    if note_type == "SALES":
        invoices = db.scalars(
            select(SalesInvoice).where(
                SalesInvoice.company_id == company_id, SalesInvoice.status == "POSTED"
            ).options(selectinload(SalesInvoice.lines)).order_by(SalesInvoice.invoice_date.desc(), SalesInvoice.id.desc())
        ).all()
        rows = []
        for invoice in invoices:
            lines = []
            for line in invoice.lines:
                remaining = quantity(Decimal(line.quantity) - previously_credited_quantity(db, note_type, line.id))
                if remaining <= 0:
                    continue
                lines.append({
                    "id": line.id, "description": line.description, "quantity": line.quantity,
                    "remaining_quantity": remaining, "unit_price": line.unit_price,
                    "vat_rate": line.vat_rate, "tax_code": line.tax_code.code if line.tax_code else None,
                    "subtotal": line.subtotal, "vat_amount": line.vat_amount, "total": line.total,
                })
            if lines:
                rows.append({
                    "id": invoice.id, "number": invoice.number, "invoice_date": invoice.invoice_date,
                    "due_date": invoice.due_date, "party_id": invoice.customer_id,
                    "party_code": invoice.customer.code, "party_name_ar": invoice.customer.name_ar,
                    "party_name_en": invoice.customer.name_en, "total": invoice.total, "lines": lines,
                })
        return rows
    invoices = db.scalars(
        select(PurchaseInvoice).where(
            PurchaseInvoice.company_id == company_id, PurchaseInvoice.status == "POSTED"
        ).options(selectinload(PurchaseInvoice.lines)).order_by(PurchaseInvoice.invoice_date.desc(), PurchaseInvoice.id.desc())
    ).all()
    rows = []
    for invoice in invoices:
        lines = []
        for line in invoice.lines:
            remaining = quantity(Decimal(line.quantity) - previously_credited_quantity(db, note_type, line.id))
            if remaining <= 0:
                continue
            lines.append({
                "id": line.id, "description": line.description, "quantity": line.quantity,
                "remaining_quantity": remaining, "unit_price": line.unit_price,
                "vat_rate": line.vat_rate, "tax_code": line.tax_code.code if line.tax_code else None,
                "subtotal": line.subtotal, "vat_amount": line.vat_amount, "total": line.total,
            })
        if lines:
            rows.append({
                "id": invoice.id, "number": invoice.number, "invoice_date": invoice.invoice_date,
                "due_date": invoice.due_date, "party_id": invoice.supplier_id,
                "party_code": invoice.supplier.code, "party_name_ar": invoice.supplier.name_ar,
                "party_name_en": invoice.supplier.name_en, "supplier_invoice_number": invoice.supplier_invoice_number,
                "total": invoice.total, "lines": lines,
            })
    return rows


@router.get("/documents/{note_id}")
def read_credit_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_note(db, note_id); ensure_permission(db, user, row.company_id, "finance.read"); return serialize(row)


@router.post("/documents/{note_id}/submit")
def submit_credit_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_note(db, note_id); ensure_permission(db, user, row.company_id, "journals.create")
    if row.status != "DRAFT": raise HTTPException(409, "Credit note must be draft")
    row.status = "PENDING_APPROVAL"; row.submitted_by = user.id; row.submitted_at = utc_now()
    write_audit(db, action="CREDIT_NOTE_SUBMITTED", entity_type="CREDIT_NOTE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit(); return serialize(get_note(db, row.id))


def apply_credit_to_open_item(db: Session, row: CreditNote, user_id: int) -> None:
    ledger_type = "AR" if row.note_type == "SALES" else "AP"
    source_type = "SALES_INVOICE" if row.note_type == "SALES" else "PURCHASE_INVOICE"
    source_id = row.original_sales_invoice_id or row.original_purchase_invoice_id
    item = db.scalar(select(FinancialOpenItem).where(
        FinancialOpenItem.company_id == row.company_id, FinancialOpenItem.ledger_type == ledger_type,
        FinancialOpenItem.source_type == source_type, FinancialOpenItem.source_id == source_id,
    ))
    remaining_credit = money(row.total)
    if item:
        applied = min(remaining_credit, open_amount(db, item))
        if applied > 0:
            db.add(CreditNoteApplication(company_id=row.company_id, credit_note_id=row.id, open_item_id=item.id,
                                         application_date=row.note_date, amount=applied, created_by=user_id))
            db.flush(); refresh_open_item_status(db, item); remaining_credit = money(remaining_credit - applied)
    row.unapplied_credit = remaining_credit
    if remaining_credit > 0:
        db.add(PartyCreditBalance(company_id=row.company_id, ledger_type=ledger_type, party_id=row.party_id,
                                  source_id=row.id, document_number=row.number, balance_date=row.note_date,
                                  original_amount=remaining_credit, available_amount=remaining_credit, status="OPEN", created_by=user_id))


def post_inventory_effects(db: Session, row: CreditNote, user_id: int, journal: JournalEntry) -> list[dict]:
    extra_lines: list[dict] = []
    for line in row.lines:
        if not line.item_id or not line.warehouse_id or line.inventory_disposition == "NONE":
            continue
        item = db.get(Item, line.item_id)
        qty = quantity(line.quantity); value = money(line.inventory_value)
        if row.note_type == "SALES":
            if line.inventory_disposition in {"RETURN_TO_STOCK", "QUARANTINE"}:
                movement_type = "SALES_RETURN_RESTORE" if line.inventory_disposition == "RETURN_TO_STOCK" else "SALES_RETURN_QUARANTINE"
                db.add(StockMovement(company_id=row.company_id, warehouse_id=line.warehouse_id, item_id=line.item_id,
                    movement_date=row.note_date, movement_type=movement_type, quantity=qty, unit_cost=line.unit_cost,
                    total_cost=value, reference_type="CREDIT_NOTE", reference_id=row.id, journal_id=journal.id, created_by=user_id))
                extra_lines += [
                    {"account_id": item.inventory_account_id, "debit": value, "credit": 0, "description": f"Inventory restored {row.number}"},
                    {"account_id": item.cogs_account_id, "debit": 0, "credit": value, "description": f"COGS reversed {row.number}"},
                ]
        else:
            if line.inventory_disposition == "RETURN_TO_SUPPLIER":
                db.add(StockMovement(company_id=row.company_id, warehouse_id=line.warehouse_id, item_id=line.item_id,
                    movement_date=row.note_date, movement_type="PURCHASE_RETURN", quantity=-qty, unit_cost=line.unit_cost,
                    total_cost=-value, reference_type="CREDIT_NOTE", reference_id=row.id, journal_id=journal.id, created_by=user_id))
    return extra_lines


@router.post("/documents/{note_id}/approve-post")
def approve_post_credit_note(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_note(db, note_id); ensure_permission(db, user, row.company_id, "journals.approve"); ensure_permission(db, user, row.company_id, "journals.post")
    if row.status != "PENDING_APPROVAL": raise HTTPException(409, "Credit note must be pending approval")
    if user.id in {row.created_by, row.submitted_by}: raise HTTPException(409, "Maker-checker control: maker/submitter cannot approve the credit note")
    ensure_open_period(db, row.company_id, row.note_date)
    approved_vat = db.scalar(select(VatReturnSnapshot.id).where(
        VatReturnSnapshot.company_id == row.company_id, VatReturnSnapshot.status == "APPROVED",
        VatReturnSnapshot.period_start <= row.note_date, VatReturnSnapshot.period_end >= row.note_date,
    ))
    if approved_vat:
        raise HTTPException(409, "VAT return for the credit-note date is approved; issue the adjustment in the current open VAT period")
    ar = get_account(db, row.company_id, "112010"); ap = get_account(db, row.company_id, "211010")
    input_vat = get_account(db, row.company_id, "114010"); output_vat = get_account(db, row.company_id, "212010")
    journal_lines: list[dict] = []
    if row.note_type == "SALES":
        for line in row.lines:
            journal_lines.append({"account_id": line.account_id, "debit": line.subtotal, "credit": 0, "description": line.description})
        if row.vat_amount: journal_lines.append({"account_id": output_vat.id, "debit": row.vat_amount, "credit": 0, "description": "Output VAT credit-note adjustment"})
        journal_lines.append({"account_id": ar.id, "debit": 0, "credit": row.total, "description": row.number})
    else:
        journal_lines.append({"account_id": ap.id, "debit": row.total, "credit": 0, "description": row.number})
        deductible_total = Decimal("0"); reverse_output = Decimal("0")
        loss_account = get_account(db, row.company_id, "624110")
        gain_account = get_account(db, row.company_id, "424020")
        for line in row.lines:
            calc = calculate_line(Decimal(line.subtotal), line.tax_code)
            recoverable_base = money(Decimal(line.subtotal) + calc["non_deductible_tax"])
            if line.inventory_disposition == "RETURN_TO_SUPPLIER" and line.item_id:
                item = db.get(Item, line.item_id); carrying = money(line.inventory_value)
                journal_lines.append({"account_id": item.inventory_account_id, "debit": 0, "credit": carrying, "description": f"Inventory returned {line.description}"})
                difference = money(carrying - recoverable_base)
                if difference > 0:
                    journal_lines.append({"account_id": loss_account.id, "debit": difference, "credit": 0, "description": "Unrecovered landed/holding cost on purchase return"})
                elif difference < 0:
                    journal_lines.append({"account_id": gain_account.id, "debit": 0, "credit": -difference, "description": "Purchase return cost gain"})
            else:
                journal_lines.append({"account_id": line.account_id, "debit": 0, "credit": recoverable_base, "description": line.description})
            deductible_total += calc["deductible_tax"]
            if line.tax_code.category in {"REVERSE_CHARGE", "IMPORTS_RETURN"}: reverse_output += calc["tax"]
        if deductible_total: journal_lines.append({"account_id": input_vat.id, "debit": 0, "credit": money(deductible_total), "description": "Input VAT credit-note adjustment"})
        if reverse_output: journal_lines.append({"account_id": output_vat.id, "debit": money(reverse_output), "credit": 0, "description": "Reverse-charge output VAT adjustment"})
    # Inventory restoration for sales returns adds a second balanced pair to the same journal.
    inventory_lines = []
    for line in row.lines:
        if row.note_type == "SALES" and line.inventory_disposition in {"RETURN_TO_STOCK", "QUARANTINE"} and line.item_id:
            item = db.get(Item, line.item_id); value = money(line.inventory_value)
            inventory_lines += [{"account_id": item.inventory_account_id, "debit": value, "credit": 0, "description": f"Inventory restored {row.number}"},
                                {"account_id": item.cogs_account_id, "debit": 0, "credit": value, "description": f"COGS reversed {row.number}"}]
    journal_lines += inventory_lines
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.note_date,
                                    reference=row.number, description=f"{row.note_type.title()} credit note {row.number}", lines=journal_lines)
    # Stock movements use the posted journal id.
    for line in row.lines:
        if not line.item_id or not line.warehouse_id or line.inventory_disposition == "NONE": continue
        qty = quantity(line.quantity); value = money(line.inventory_value)
        if row.note_type == "SALES" and line.inventory_disposition in {"RETURN_TO_STOCK", "QUARANTINE"}:
            db.add(StockMovement(company_id=row.company_id, warehouse_id=line.warehouse_id, item_id=line.item_id,
                movement_date=row.note_date, movement_type="SALES_RETURN_RESTORE" if line.inventory_disposition == "RETURN_TO_STOCK" else "SALES_RETURN_QUARANTINE",
                quantity=qty, unit_cost=line.unit_cost, total_cost=value, reference_type="CREDIT_NOTE", reference_id=row.id, journal_id=journal.id, created_by=user.id))
        elif row.note_type == "PURCHASE" and line.inventory_disposition == "RETURN_TO_SUPPLIER":
            db.add(StockMovement(company_id=row.company_id, warehouse_id=line.warehouse_id, item_id=line.item_id,
                movement_date=row.note_date, movement_type="PURCHASE_RETURN", quantity=-qty, unit_cost=line.unit_cost,
                total_cost=-value, reference_type="CREDIT_NOTE", reference_id=row.id, journal_id=journal.id, created_by=user.id))
    apply_credit_to_open_item(db, row, user.id)
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.journal_id = journal.id
    write_audit(db, action="CREDIT_NOTE_APPROVED_POSTED", entity_type="CREDIT_NOTE", entity_id=row.id, user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "journal": journal.number, "unapplied_credit": str(row.unapplied_credit)})
    db.commit(); return serialize(get_note(db, row.id))


@router.post("/documents/{note_id}/reject")
def reject_credit_note(note_id: int, data: RejectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_note(db, note_id); ensure_permission(db, user, row.company_id, "journals.approve")
    if row.status != "PENDING_APPROVAL": raise HTTPException(409, "Credit note must be pending approval")
    if user.id in {row.created_by, row.submitted_by}: raise HTTPException(409, "Maker-checker control")
    row.status = "REJECTED"
    write_audit(db, action="CREDIT_NOTE_REJECTED", entity_type="CREDIT_NOTE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status, "reason": data.reason})
    db.commit(); return serialize(get_note(db, row.id))


@router.get("/documents/{note_id}/zatca-document")
def zatca_credit_note_document(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_note(db, note_id); ensure_permission(db, user, row.company_id, "finance.read")
    return {
        "production_status": "INTERNAL_STRUCTURED_DOCUMENT_REQUIRES_ZATCA_CSID",
        "document_type_code": "381" if row.note_type == "SALES" else "SUPPLIER_CREDIT_NOTE_INBOUND",
        "uuid": row.zatca_uuid, "number": row.number, "issue_date": row.note_date,
        "billing_reference": {"invoice_number": row.original_document_number, "invoice_date": row.original_document_date},
        "reason_code": row.reason_code, "reason": row.reason,
        "tax_total": money(row.vat_amount), "tax_exclusive_amount": money(row.subtotal), "tax_inclusive_amount": money(row.total),
        "lines": [{"id": x.id, "description": x.description, "quantity": x.quantity, "unit_price": x.unit_price,
                   "tax_code": x.tax_code.code, "tax_category": x.tax_code.tax_category_code,
                   "tax_rate": x.tax_code.rate, "line_extension": x.subtotal, "tax_amount": x.vat_amount, "total": x.total} for x in row.lines],
    }


@router.get("/credit-balances/open")
def list_open_credit_balances(company_id: int, ledger_type: str | None = None, party_id: int | None = None,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.arap.read")
    query = select(PartyCreditBalance).where(PartyCreditBalance.company_id == company_id, PartyCreditBalance.available_amount > 0).order_by(PartyCreditBalance.balance_date, PartyCreditBalance.id)
    if ledger_type: query = query.where(PartyCreditBalance.ledger_type == ledger_type.upper())
    if party_id: query = query.where(PartyCreditBalance.party_id == party_id)
    return [{"id": x.id, "ledger_type": x.ledger_type, "party_id": x.party_id, "party_code": x.party.code,
             "party_name_ar": x.party.name_ar, "party_name_en": x.party.name_en, "document_number": x.document_number,
             "balance_date": x.balance_date, "original_amount": money(x.original_amount), "available_amount": money(x.available_amount), "status": x.status} for x in db.scalars(query).all()]


@router.post("/credit-balances/{balance_id}/apply")
def apply_credit_balance(balance_id: int, data: CreditBalanceApplyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    balance = db.get(PartyCreditBalance, balance_id)
    if not balance: raise HTTPException(404, "Credit balance not found")
    ensure_permission(db, user, balance.company_id, "finance.arap.allocate")
    item = db.get(FinancialOpenItem, data.open_item_id)
    if not item or item.company_id != balance.company_id or item.ledger_type != balance.ledger_type or item.party_id != balance.party_id:
        raise HTTPException(422, "Open item does not belong to the credit-balance party and ledger")
    amount = money(data.amount)
    if amount > money(balance.available_amount): raise HTTPException(409, "Amount exceeds available credit balance")
    outstanding = open_amount(db, item)
    if amount > outstanding: raise HTTPException(409, f"Amount exceeds open item balance {outstanding}")
    if data.application_date < max(balance.balance_date, item.document_date): raise HTTPException(422, "Application date cannot precede the credit note or invoice")
    existing = db.scalar(select(CreditNoteApplication).where(CreditNoteApplication.credit_note_id == balance.source_id, CreditNoteApplication.open_item_id == item.id))
    if existing:
        existing.amount = money(existing.amount + amount); existing.application_date = data.application_date
    else:
        db.add(CreditNoteApplication(company_id=balance.company_id, credit_note_id=balance.source_id, open_item_id=item.id, application_date=data.application_date, amount=amount, created_by=user.id))
    balance.available_amount = money(balance.available_amount - amount); balance.status = "CLOSED" if balance.available_amount == 0 else "PARTIAL"
    db.flush(); refresh_open_item_status(db, item)
    write_audit(db, action="PARTY_CREDIT_APPLIED", entity_type="PARTY_CREDIT_BALANCE", entity_id=balance.id, user_id=user.id, company_id=balance.company_id, after={"open_item_id": item.id, "amount": str(amount), "available": str(balance.available_amount)})
    db.commit(); return {"balance_id": balance.id, "available_amount": money(balance.available_amount), "status": balance.status, "open_item_id": item.id, "open_amount": open_amount(db, item)}


@router.post("/credit-balances/{balance_id}/cash-settle")
def cash_settle_credit_balance(balance_id: int, data: CreditBalanceCashIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    balance = db.get(PartyCreditBalance, balance_id)
    if not balance: raise HTTPException(404, "Credit balance not found")
    ensure_permission(db, user, balance.company_id, "journals.post")
    ensure_open_period(db, balance.company_id, data.settlement_date)
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == balance.company_id, BankAccount.active.is_(True)))
    if not bank: raise HTTPException(422, "Bank account not found")
    amount = money(data.amount)
    if amount > money(balance.available_amount): raise HTTPException(409, "Amount exceeds available credit balance")
    control = get_account(db, balance.company_id, "112010" if balance.ledger_type == "AR" else "211010")
    if balance.ledger_type == "AR":
        lines = [{"account_id": control.id, "debit": amount, "credit": 0, "description": data.reference}, {"account_id": bank.gl_account_id, "debit": 0, "credit": amount, "description": data.reference}]
        kind = "CUSTOMER_REFUNDS"
    else:
        lines = [{"account_id": bank.gl_account_id, "debit": amount, "credit": 0, "description": data.reference}, {"account_id": control.id, "debit": 0, "credit": amount, "description": data.reference}]
        kind = "SUPPLIER_REFUNDS"
    journal = create_posted_journal(db, company_id=balance.company_id, user_id=user.id, posting_date=data.settlement_date, reference=data.reference, description=f"Cash settlement of credit {balance.document_number}", lines=lines, cash_flow_activity="OPERATING", cash_flow_kind=kind)
    balance.available_amount = money(balance.available_amount - amount); balance.status = "CLOSED" if balance.available_amount == 0 else "PARTIAL"
    write_audit(db, action="PARTY_CREDIT_CASH_SETTLED", entity_type="PARTY_CREDIT_BALANCE", entity_id=balance.id, user_id=user.id, company_id=balance.company_id, after={"amount": str(amount), "journal": journal.number, "available": str(balance.available_amount)})
    db.commit(); return {"balance_id": balance.id, "available_amount": money(balance.available_amount), "status": balance.status, "journal_number": journal.number}


@router.get("/export/csv")
def export_credit_notes(company_id: int, note_type: str | None = None,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    query = select(CreditNote).where(CreditNote.company_id == company_id).order_by(CreditNote.note_date, CreditNote.number)
    if note_type: query = query.where(CreditNote.note_type == note_type.upper())
    rows = db.scalars(query).all(); output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["number", "date", "type", "original_document", "party_id", "reason_code", "external_reference", "status", "subtotal", "vat", "total", "unapplied_credit", "zatca_uuid"])
    for row in rows: writer.writerow([row.number, row.note_date, row.note_type, row.original_document_number, row.party_id, row.reason_code, row.external_reference, row.status, row.subtotal, row.vat_amount, row.total, row.unapplied_credit, row.zatca_uuid])
    data = "\ufeff" + output.getvalue()
    return StreamingResponse(iter([data.encode("utf-8")]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=credit_notes.csv"})
