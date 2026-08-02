from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BankAccount, FinancialOpenItem, FinancialSettlementAllocation, JournalEntry, JournalLine, Party, Payment, PurchaseInvoice,
    PartyCreditBalance, PurchaseInvoiceLine, Receipt, SalesInvoice, SalesInvoiceLine, TaxCode, User,
)
from app.services.audit import write_audit
from app.services.posting import create_posted_journal, ensure_open_period
from app.services.ar_ap import (
    active_allocation_total, allocate_payment, allocate_receipt, ensure_purchase_invoice_open_item,
    ensure_sales_invoice_open_item, money as arap_money, open_amount, refresh_open_item_status,
    serialize_open_item, settlement_allocated_total,
)
from app.core.time import utc_now
from app.services.tax import calculate_line, get_tax_code

router = APIRouter(prefix="/subledgers", tags=["AR AP and treasury"])
MONEY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def document_number(db: Session, model, company_id: int, prefix: str, doc_date: date) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{doc_date.year}-{count + 1:06d}"


def get_account(db: Session, company_id: int, code: str) -> Account:
    account = db.scalar(
        select(Account).where(Account.company_id == company_id, Account.code == code, Account.active.is_(True))
    )
    if not account or not account.is_postable:
        raise HTTPException(422, f"Account is missing or non-postable: {code}")
    return account


def get_party(db: Session, company_id: int, party_id: int, allowed: set[str]) -> Party:
    party = db.scalar(select(Party).where(Party.id == party_id, Party.company_id == company_id, Party.active.is_(True)))
    if not party or party.party_type not in allowed | {"BOTH"}:
        raise HTTPException(422, "Party is missing or has the wrong type")
    return party


class InvoiceLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    account_code: str
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(gt=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tax_code: str | None = Field(default=None, max_length=30)


class SalesInvoiceIn(BaseModel):
    company_id: int
    invoice_date: date
    due_date: date
    customer_id: int
    reference: str | None = None
    lines: list[InvoiceLineIn] = Field(min_length=1)


class PurchaseInvoiceIn(BaseModel):
    company_id: int
    invoice_date: date
    due_date: date
    supplier_id: int
    supplier_invoice_number: str = Field(min_length=1, max_length=100)
    lines: list[InvoiceLineIn] = Field(min_length=1)


class AllocationLineIn(BaseModel):
    open_item_id: int
    amount: Decimal = Field(gt=0)


class AllocationBatchIn(BaseModel):
    allocation_date: date | None = None
    allocations: list[AllocationLineIn] = Field(min_length=1)


class OpeningBalanceIn(BaseModel):
    company_id: int
    ledger_type: str = Field(pattern="^(AR|AP)$")
    party_id: int
    document_number: str = Field(min_length=1, max_length=100)
    document_date: date
    due_date: date
    amount: Decimal = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)
    post_to_gl: bool = False
    offset_account_code: str | None = None


class ReceiptIn(BaseModel):
    company_id: int
    receipt_date: date
    customer_id: int
    bank_account_id: int
    amount: Decimal = Field(gt=0)
    reference: str = Field(min_length=1, max_length=100)
    allocations: list[AllocationLineIn] = Field(default_factory=list)


class PaymentIn(BaseModel):
    company_id: int
    payment_date: date
    supplier_id: int
    bank_account_id: int
    amount: Decimal = Field(gt=0)
    reference: str = Field(min_length=1, max_length=100)
    allocations: list[AllocationLineIn] = Field(default_factory=list)


class PartyIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=30)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    party_type: str = Field(pattern="^(CUSTOMER|SUPPLIER|BOTH)$")
    vat_number: str | None = Field(default=None, max_length=30)
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)


@router.get("/parties")
def list_parties(
    company_id: int,
    party_type: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "masterdata.read")
    query = select(Party).where(Party.company_id == company_id, Party.active.is_(True)).order_by(Party.code)
    if party_type:
        query = query.where(Party.party_type.in_([party_type, "BOTH"]))
    return [
        {
            "id": row.id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "party_type": row.party_type,
            "vat_number": row.vat_number,
            "credit_limit": row.credit_limit,
        }
        for row in db.scalars(query).all()
    ]


@router.post("/parties", status_code=201)
def create_party(
    data: PartyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, data.company_id, "masterdata.manage")
    code = data.code.strip().upper()
    duplicate = db.scalar(
        select(Party.id).where(
            Party.company_id == data.company_id,
            func.lower(Party.code) == code.lower(),
        )
    )
    if duplicate:
        raise HTTPException(409, "Party code already exists")
    vat_number = data.vat_number.strip() if data.vat_number else None
    if vat_number and (not vat_number.isdigit() or len(vat_number) != 15):
        raise HTTPException(422, "VAT number must contain exactly 15 digits")
    row = Party(
        company_id=data.company_id,
        code=code,
        name_ar=data.name_ar.strip(),
        name_en=data.name_en.strip(),
        party_type=data.party_type,
        vat_number=vat_number,
        credit_limit=money(data.credit_limit),
        active=True,
    )
    db.add(row)
    db.flush()
    payload = {
        "id": row.id,
        "code": row.code,
        "name_ar": row.name_ar,
        "name_en": row.name_en,
        "party_type": row.party_type,
        "vat_number": row.vat_number,
        "credit_limit": row.credit_limit,
    }
    write_audit(
        db,
        action="PARTY_CREATED",
        entity_type="PARTY",
        entity_id=row.id,
        user_id=user.id,
        company_id=data.company_id,
        after={"code": row.code, "party_type": row.party_type, "credit_limit": str(row.credit_limit)},
    )
    db.commit()
    return payload


@router.get("/bank-accounts")
def list_bank_accounts(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(
        select(BankAccount).where(BankAccount.company_id == company_id, BankAccount.active.is_(True)).order_by(BankAccount.code)
    ).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "bank_name_ar": row.bank_name_ar,
            "bank_name_en": row.bank_name_en,
            "iban": row.iban,
            "gl_account_code": row.gl_account.code,
        }
        for row in rows
    ]


@router.post("/sales-invoices", status_code=201)
def create_sales_invoice(
    data: SalesInvoiceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, data.company_id, "journals.create")
    if data.due_date < data.invoice_date:
        raise HTTPException(422, "Due date cannot be before invoice date")
    ensure_open_period(db, data.company_id, data.invoice_date)
    customer = get_party(db, data.company_id, data.customer_id, {"CUSTOMER"})
    accounts = {line.account_code: get_account(db, data.company_id, line.account_code) for line in data.lines}
    invoice = SalesInvoice(
        company_id=data.company_id,
        number=document_number(db, SalesInvoice, data.company_id, "SI", data.invoice_date),
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        customer_id=customer.id,
        reference=data.reference,
        status="DRAFT",
        created_by=user.id,
    )
    subtotal = vat_amount = Decimal("0")
    for line in data.lines:
        tax_code = get_tax_code(db, data.company_id, code=line.tax_code, direction="SALES", vat_rate=line.vat_rate, user_id=user.id)
        line_subtotal = money(line.quantity * line.unit_price)
        calc = calculate_line(line_subtotal, tax_code)
        invoice.lines.append(
            SalesInvoiceLine(
                description=line.description,
                revenue_account_id=accounts[line.account_code].id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                vat_rate=tax_code.rate,
                tax_code_id=tax_code.id,
                subtotal=line_subtotal,
                vat_amount=calc["tax"],
                total=calc["document_total"],
            )
        )
        subtotal += line_subtotal
        vat_amount += calc["tax"]
    invoice.subtotal = money(subtotal)
    invoice.vat_amount = money(vat_amount)
    invoice.total = money(sum((Decimal(line.total) for line in invoice.lines), Decimal("0")))
    db.add(invoice)
    db.flush()
    write_audit(db, action="SALES_INVOICE_CREATED", entity_type="SALES_INVOICE", entity_id=invoice.id, user_id=user.id, company_id=data.company_id, after={"number": invoice.number, "total": str(invoice.total), "status": invoice.status})
    db.commit()
    return {"id": invoice.id, "number": invoice.number, "status": invoice.status, "subtotal": invoice.subtotal, "vat_amount": invoice.vat_amount, "total": invoice.total}


@router.post("/sales-invoices/{invoice_id}/post")
def post_sales_invoice(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = db.scalar(select(SalesInvoice).options(selectinload(SalesInvoice.lines)).where(SalesInvoice.id == invoice_id))
    if not invoice:
        raise HTTPException(404, "Sales invoice not found")
    ensure_permission(db, user, invoice.company_id, "journals.post")
    if invoice.status != "DRAFT":
        raise HTTPException(409, "Sales invoice is not a draft")
    ar = get_account(db, invoice.company_id, "112010")
    vat = get_account(db, invoice.company_id, "212010")
    lines = [{"account_id": ar.id, "debit": invoice.total, "credit": 0, "description": invoice.number}]
    lines.extend({"account_id": line.revenue_account_id, "debit": 0, "credit": line.subtotal, "description": line.description} for line in invoice.lines)
    if invoice.vat_amount:
        lines.append({"account_id": vat.id, "debit": 0, "credit": invoice.vat_amount, "description": "Output VAT"})
    journal = create_posted_journal(db, company_id=invoice.company_id, user_id=user.id, posting_date=invoice.invoice_date, reference=invoice.number, description=f"Sales invoice {invoice.number}", lines=lines)
    invoice.status = "POSTED"
    invoice.journal_id = journal.id
    ensure_sales_invoice_open_item(db, invoice)
    write_audit(db, action="SALES_INVOICE_POSTED", entity_type="SALES_INVOICE", entity_id=invoice.id, user_id=user.id, company_id=invoice.company_id, before={"status": "DRAFT"}, after={"status": "POSTED", "journal": journal.number})
    db.commit()
    return {"id": invoice.id, "number": invoice.number, "status": invoice.status, "journal_number": journal.number}


@router.post("/purchase-invoices", status_code=201)
def create_purchase_invoice(
    data: PurchaseInvoiceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, data.company_id, "journals.create")
    if data.due_date < data.invoice_date:
        raise HTTPException(422, "Due date cannot be before invoice date")
    ensure_open_period(db, data.company_id, data.invoice_date)
    supplier = get_party(db, data.company_id, data.supplier_id, {"SUPPLIER"})
    accounts = {line.account_code: get_account(db, data.company_id, line.account_code) for line in data.lines}
    invoice = PurchaseInvoice(
        company_id=data.company_id,
        number=document_number(db, PurchaseInvoice, data.company_id, "PI", data.invoice_date),
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        supplier_id=supplier.id,
        supplier_invoice_number=data.supplier_invoice_number,
        status="DRAFT",
        created_by=user.id,
    )
    subtotal = vat_amount = Decimal("0")
    for line in data.lines:
        tax_code = get_tax_code(db, data.company_id, code=line.tax_code, direction="PURCHASE", vat_rate=line.vat_rate, user_id=user.id)
        line_subtotal = money(line.quantity * line.unit_price)
        calc = calculate_line(line_subtotal, tax_code)
        invoice.lines.append(PurchaseInvoiceLine(
            description=line.description, expense_account_id=accounts[line.account_code].id,
            quantity=line.quantity, unit_price=line.unit_price, vat_rate=tax_code.rate,
            tax_code_id=tax_code.id, subtotal=line_subtotal, vat_amount=calc["tax"], total=calc["document_total"],
        ))
        subtotal += line_subtotal
        vat_amount += calc["tax"]
    invoice.subtotal = money(subtotal)
    invoice.vat_amount = money(vat_amount)
    invoice.total = money(sum((Decimal(line.total) for line in invoice.lines), Decimal("0")))
    db.add(invoice)
    db.flush()
    write_audit(db, action="PURCHASE_INVOICE_CREATED", entity_type="PURCHASE_INVOICE", entity_id=invoice.id, user_id=user.id, company_id=data.company_id, after={"number": invoice.number, "total": str(invoice.total), "status": invoice.status})
    db.commit()
    return {"id": invoice.id, "number": invoice.number, "status": invoice.status, "subtotal": invoice.subtotal, "vat_amount": invoice.vat_amount, "total": invoice.total}



# ------------------------------------------------------- purchase posting guard
# ACCOUNTING RISK THIS CLOSES
#   The platform has a correct three-way flow:
#       purchase order -> goods receipt (moves stock, credits 214010
#       "Goods Received Not Invoiced") -> supplier invoice (clears 214010, credits AP)
#   The supplier invoice, however, had no knowledge of receipts. Posting an
#   invoice line straight onto an inventory account (113010) instead of clearing
#   214010 debits inventory a SECOND time while the warehouse holds one physical
#   quantity. The ledger and the stock ledger then drift apart permanently, and
#   the gap is only found at a stock count months later.
#
#   Inventory accounts are therefore refused on a supplier invoice. Goods reach
#   inventory through the receipt; the invoice settles the money.

def _inventory_account_ids(db: Session, company_id: int) -> set[int]:
    """Accounts that represent stock on hand and must not be touched by an invoice."""
    from app.models.supply_chain import Item

    ids: set[int] = set()
    for (account_id,) in db.execute(
        select(Item.inventory_account_id).where(
            Item.company_id == company_id, Item.inventory_account_id.is_not(None)
        )
    ):
        if account_id:
            ids.add(int(account_id))
    # 113010 is the seeded stock account and may exist before any item is defined.
    stock = db.scalar(
        select(Account).where(Account.company_id == company_id, Account.code == "113010")
    )
    if stock:
        ids.add(stock.id)
    return ids


def guard_purchase_line_accounts(db: Session, company_id: int, lines) -> None:
    """Refuse a supplier invoice that would debit stock outside the receipt flow."""
    blocked = _inventory_account_ids(db, company_id)
    if not blocked:
        return
    for line in lines:
        account_id = getattr(line, "expense_account_id", None)
        if account_id and int(account_id) in blocked:
            account = db.get(Account, int(account_id))
            code = account.code if account else account_id
            raise HTTPException(
                422,
                {
                    "message_ar": (
                        f"لا يمكن ترحيل فاتورة شراء على حساب المخزون {code}. "
                        "المخزون يزيد عند إثبات الاستلام لا عند الفاتورة. "
                        "الطريق الصحيح: أمر شراء ← إثبات استلام (يزيد المخزون ويسجّل "
                        "استلامات غير مفوترة 214010) ← ثم فاتورة على 214010 لتصفيته. "
                        "أما الشراء الخدمي فيُرحَّل على حساب مصروف."
                    ),
                    "message_en": (
                        f"A supplier invoice may not debit inventory account {code}. "
                        "Stock increases at goods receipt, not at invoicing. Correct path: "
                        "purchase order -> goods receipt (raises stock and credits 214010 "
                        "Goods Received Not Invoiced) -> invoice against 214010 to clear it. "
                        "Service purchases post to an expense account."
                    ),
                    "inventory_account": str(code),
                    "use_instead": "214010",
                },
            )


@router.post("/purchase-invoices/{invoice_id}/post")
def post_purchase_invoice(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = db.scalar(select(PurchaseInvoice).options(selectinload(PurchaseInvoice.lines)).where(PurchaseInvoice.id == invoice_id))
    if not invoice:
        raise HTTPException(404, "Purchase invoice not found")
    ensure_permission(db, user, invoice.company_id, "journals.post")
    if invoice.status != "DRAFT":
        raise HTTPException(409, "Purchase invoice is not a draft")
    ap = get_account(db, invoice.company_id, "211010")
    # Refuse inventory accounts: stock is raised by the receipt, not the invoice.
    guard_purchase_line_accounts(db, invoice.company_id, invoice.lines)
    input_vat = get_account(db, invoice.company_id, "114010")
    output_vat = get_account(db, invoice.company_id, "212010")
    lines = []
    deductible_total = Decimal("0")
    reverse_charge_output = Decimal("0")
    for line in invoice.lines:
        tax_code = line.tax_code or get_tax_code(db, invoice.company_id, code=None, direction="PURCHASE", vat_rate=Decimal(line.vat_rate), user_id=user.id)
        calc = calculate_line(Decimal(line.subtotal), tax_code)
        expense_debit = money(Decimal(line.subtotal) + calc["non_deductible_tax"])
        lines.append({"account_id": line.expense_account_id, "debit": expense_debit, "credit": 0, "description": line.description})
        deductible_total += calc["deductible_tax"]
        if tax_code.category == "REVERSE_CHARGE":
            reverse_charge_output += calc["tax"]
    if deductible_total:
        lines.append({"account_id": input_vat.id, "debit": money(deductible_total), "credit": 0, "description": "Recoverable input VAT"})
    if reverse_charge_output:
        lines.append({"account_id": output_vat.id, "debit": 0, "credit": money(reverse_charge_output), "description": "Reverse-charge output VAT"})
    lines.append({"account_id": ap.id, "debit": 0, "credit": invoice.total, "description": invoice.number})
    journal = create_posted_journal(db, company_id=invoice.company_id, user_id=user.id, posting_date=invoice.invoice_date, reference=invoice.number, description=f"Purchase invoice {invoice.number}", lines=lines)
    invoice.status = "POSTED"
    invoice.journal_id = journal.id
    ensure_purchase_invoice_open_item(db, invoice)
    write_audit(db, action="PURCHASE_INVOICE_POSTED", entity_type="PURCHASE_INVOICE", entity_id=invoice.id, user_id=user.id, company_id=invoice.company_id, before={"status": "DRAFT"}, after={"status": "POSTED", "journal": journal.number})
    db.commit()
    return {"id": invoice.id, "number": invoice.number, "status": invoice.status, "journal_number": journal.number}


@router.post("/receipts", status_code=201)
def create_receipt(data: ReceiptIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "journals.post")
    customer = get_party(db, data.company_id, data.customer_id, {"CUSTOMER"})
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not bank:
        raise HTTPException(422, "Bank account not found")
    ar = get_account(db, data.company_id, "112010")
    amount = money(data.amount)
    number = document_number(db, Receipt, data.company_id, "RC", data.receipt_date)
    journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.receipt_date, reference=number, description=f"Receipt from {customer.name_en}", lines=[{"account_id": bank.gl_account_id, "debit": amount, "credit": 0}, {"account_id": ar.id, "debit": 0, "credit": amount}], cash_flow_activity="OPERATING", cash_flow_kind="CUSTOMER_RECEIPTS")
    receipt = Receipt(company_id=data.company_id, number=number, receipt_date=data.receipt_date, customer_id=customer.id, bank_account_id=bank.id, amount=amount, reference=data.reference, journal_id=journal.id, created_by=user.id)
    db.add(receipt)
    db.flush()
    allocated_rows = allocate_receipt(db, receipt, [line.model_dump() for line in data.allocations], user_id=user.id) if data.allocations else []
    write_audit(db, action="RECEIPT_POSTED", entity_type="RECEIPT", entity_id=receipt.id, user_id=user.id, company_id=data.company_id, after={"number": number, "amount": str(amount), "journal": journal.number})
    db.commit()
    return {"id": receipt.id, "number": number, "amount": amount, "allocated_amount": arap_money(sum((row.amount for row in allocated_rows), Decimal("0"))), "unapplied_amount": amount - arap_money(sum((row.amount for row in allocated_rows), Decimal("0"))), "journal_number": journal.number}


@router.post("/payments", status_code=201)
def create_payment(data: PaymentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "journals.post")
    supplier = get_party(db, data.company_id, data.supplier_id, {"SUPPLIER"})
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not bank:
        raise HTTPException(422, "Bank account not found")
    ap = get_account(db, data.company_id, "211010")
    amount = money(data.amount)
    number = document_number(db, Payment, data.company_id, "PY", data.payment_date)
    journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.payment_date, reference=number, description=f"Payment to {supplier.name_en}", lines=[{"account_id": ap.id, "debit": amount, "credit": 0}, {"account_id": bank.gl_account_id, "debit": 0, "credit": amount}], cash_flow_activity="OPERATING", cash_flow_kind="SUPPLIER_PAYMENTS")
    payment = Payment(company_id=data.company_id, number=number, payment_date=data.payment_date, supplier_id=supplier.id, bank_account_id=bank.id, amount=amount, net_cash_amount=amount, withholding_tax_amount=0, reference=data.reference, journal_id=journal.id, created_by=user.id)
    db.add(payment)
    db.flush()
    allocated_rows = allocate_payment(db, payment, [line.model_dump() for line in data.allocations], user_id=user.id) if data.allocations else []
    write_audit(db, action="PAYMENT_POSTED", entity_type="PAYMENT", entity_id=payment.id, user_id=user.id, company_id=data.company_id, after={"number": number, "amount": str(amount), "journal": journal.number})
    db.commit()
    return {"id": payment.id, "number": number, "amount": amount, "allocated_amount": arap_money(sum((row.amount for row in allocated_rows), Decimal("0"))), "unapplied_amount": amount - arap_money(sum((row.amount for row in allocated_rows), Decimal("0"))), "journal_number": journal.number}



def _allocation_dict(row: FinancialSettlementAllocation) -> dict:
    return {
        "id": row.id, "open_item_id": row.open_item_id, "receipt_id": row.receipt_id,
        "payment_id": row.payment_id, "allocation_date": row.allocation_date, "amount": arap_money(row.amount),
        "reversed": row.reversed_at is not None, "reversed_at": row.reversed_at,
        "reversal_reason": row.reversal_reason,
    }


def _account_balance_as_of(db: Session, company_id: int, code: str, as_of_date: date) -> Decimal:
    debit, credit = db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(
            Account.company_id == company_id, Account.code == code,
            JournalEntry.entry_date <= as_of_date,
            JournalEntry.status.in_(["POSTED", "REVERSED"]),
        )
    ).one()
    net = Decimal(debit) - Decimal(credit)
    return arap_money(net if code == "112010" else -net)


@router.get("/open-items")
def list_open_items(
    company_id: int, ledger_type: str, as_of_date: date | None = None, party_id: int | None = None,
    include_closed: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.arap.read")
    ledger = ledger_type.upper()
    if ledger not in {"AR", "AP"}:
        raise HTTPException(422, "ledger_type must be AR or AP")
    effective = as_of_date or date.today()
    query = select(FinancialOpenItem).where(
        FinancialOpenItem.company_id == company_id,
        FinancialOpenItem.ledger_type == ledger,
        FinancialOpenItem.document_date <= effective,
    ).order_by(FinancialOpenItem.due_date, FinancialOpenItem.document_date, FinancialOpenItem.id)
    if party_id:
        query = query.where(FinancialOpenItem.party_id == party_id)
    rows = [serialize_open_item(db, row, effective) for row in db.scalars(query).all()]
    return rows if include_closed else [row for row in rows if Decimal(str(row["outstanding_amount"])) > 0]


def _settlement_allocations(db: Session, *, receipt_id: int | None = None, payment_id: int | None = None):
    query = select(FinancialSettlementAllocation).options(selectinload(FinancialSettlementAllocation.open_item)).where(
        FinancialSettlementAllocation.receipt_id == receipt_id if receipt_id is not None else FinancialSettlementAllocation.payment_id == payment_id
    ).order_by(FinancialSettlementAllocation.id)
    return [_allocation_dict(row) | {
        "document_number": row.open_item.document_number,
        "ledger_type": row.open_item.ledger_type,
        "party_id": row.open_item.party_id,
    } for row in db.scalars(query).all()]


@router.get("/receipts")
def list_receipts(
    company_id: int, customer_id: int | None = None, include_fully_applied: bool = True,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.arap.read")
    query = select(Receipt).where(Receipt.company_id == company_id).order_by(Receipt.receipt_date.desc(), Receipt.id.desc())
    if customer_id:
        query = query.where(Receipt.customer_id == customer_id)
    result = []
    for row in db.scalars(query).all():
        allocated = settlement_allocated_total(db, receipt_id=row.id)
        unapplied = arap_money(row.amount) - allocated
        if not include_fully_applied and unapplied <= 0:
            continue
        result.append({
            "id": row.id, "number": row.number, "receipt_date": row.receipt_date,
            "customer_id": row.customer_id, "party_code": row.customer.code,
            "party_name_ar": row.customer.name_ar, "party_name_en": row.customer.name_en,
            "amount": arap_money(row.amount), "allocated_amount": allocated, "unapplied_amount": unapplied,
            "reference": row.reference, "journal_id": row.journal_id,
        })
    return result


@router.get("/payments")
def list_payments(
    company_id: int, supplier_id: int | None = None, include_fully_applied: bool = True,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.arap.read")
    query = select(Payment).where(Payment.company_id == company_id).order_by(Payment.payment_date.desc(), Payment.id.desc())
    if supplier_id:
        query = query.where(Payment.supplier_id == supplier_id)
    result = []
    for row in db.scalars(query).all():
        allocated = settlement_allocated_total(db, payment_id=row.id)
        unapplied = arap_money(row.amount) - allocated
        if not include_fully_applied and unapplied <= 0:
            continue
        result.append({
            "id": row.id, "number": row.number, "payment_date": row.payment_date,
            "supplier_id": row.supplier_id, "party_code": row.supplier.code,
            "party_name_ar": row.supplier.name_ar, "party_name_en": row.supplier.name_en,
            "amount": arap_money(row.amount), "allocated_amount": allocated, "unapplied_amount": unapplied,
            "reference": row.reference, "journal_id": row.journal_id,
        })
    return result


@router.get("/receipts/{receipt_id}/allocations")
def receipt_allocations(receipt_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    ensure_permission(db, user, receipt.company_id, "finance.arap.read")
    return _settlement_allocations(db, receipt_id=receipt.id)


@router.get("/payments/{payment_id}/allocations")
def payment_allocations(payment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    ensure_permission(db, user, payment.company_id, "finance.arap.read")
    return _settlement_allocations(db, payment_id=payment.id)


@router.post("/receipts/{receipt_id}/allocations")
def allocate_receipt_endpoint(receipt_id: int, data: AllocationBatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    ensure_permission(db, user, receipt.company_id, "finance.arap.allocate")
    rows = allocate_receipt(db, receipt, [line.model_dump() for line in data.allocations], user_id=user.id, allocation_date=data.allocation_date)
    write_audit(db, action="AR_RECEIPT_ALLOCATED", entity_type="RECEIPT", entity_id=receipt.id, user_id=user.id, company_id=receipt.company_id, after={"allocations": [{"open_item_id": r.open_item_id, "amount": str(r.amount)} for r in rows]})
    db.commit()
    allocated = settlement_allocated_total(db, receipt_id=receipt.id)
    return {"receipt_id": receipt.id, "amount": receipt.amount, "allocated_amount": allocated, "unapplied_amount": arap_money(receipt.amount) - allocated, "allocations": [_allocation_dict(r) for r in rows]}


@router.post("/payments/{payment_id}/allocations")
def allocate_payment_endpoint(payment_id: int, data: AllocationBatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    ensure_permission(db, user, payment.company_id, "finance.arap.allocate")
    rows = allocate_payment(db, payment, [line.model_dump() for line in data.allocations], user_id=user.id, allocation_date=data.allocation_date)
    write_audit(db, action="AP_PAYMENT_ALLOCATED", entity_type="PAYMENT", entity_id=payment.id, user_id=user.id, company_id=payment.company_id, after={"allocations": [{"open_item_id": r.open_item_id, "amount": str(r.amount)} for r in rows]})
    db.commit()
    allocated = settlement_allocated_total(db, payment_id=payment.id)
    return {"payment_id": payment.id, "amount": payment.amount, "allocated_amount": allocated, "unapplied_amount": arap_money(payment.amount) - allocated, "allocations": [_allocation_dict(r) for r in rows]}


@router.post("/receipts/{receipt_id}/auto-allocate")
def auto_allocate_receipt(receipt_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    ensure_permission(db, user, receipt.company_id, "finance.arap.allocate")
    available = arap_money(receipt.amount) - settlement_allocated_total(db, receipt_id=receipt.id)
    lines = []
    for item in db.scalars(select(FinancialOpenItem).where(
        FinancialOpenItem.company_id == receipt.company_id, FinancialOpenItem.ledger_type == "AR",
        FinancialOpenItem.party_id == receipt.customer_id, FinancialOpenItem.document_date <= receipt.receipt_date,
    ).order_by(FinancialOpenItem.due_date, FinancialOpenItem.document_date, FinancialOpenItem.id)).all():
        remaining = open_amount(db, item)
        if remaining <= 0 or available <= 0:
            continue
        applied = min(remaining, available)
        lines.append({"open_item_id": item.id, "amount": applied}); available -= applied
    if not lines:
        return {"receipt_id": receipt.id, "allocated_amount": settlement_allocated_total(db, receipt_id=receipt.id), "unapplied_amount": available, "allocations": []}
    rows = allocate_receipt(db, receipt, lines, user_id=user.id)
    write_audit(db, action="AR_RECEIPT_AUTO_ALLOCATED", entity_type="RECEIPT", entity_id=receipt.id, user_id=user.id, company_id=receipt.company_id, after={"allocation_count": len(rows)})
    db.commit()
    return {"receipt_id": receipt.id, "allocated_amount": settlement_allocated_total(db, receipt_id=receipt.id), "unapplied_amount": available, "allocations": [_allocation_dict(r) for r in rows]}


@router.post("/payments/{payment_id}/auto-allocate")
def auto_allocate_payment(payment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    ensure_permission(db, user, payment.company_id, "finance.arap.allocate")
    available = arap_money(payment.amount) - settlement_allocated_total(db, payment_id=payment.id)
    lines = []
    for item in db.scalars(select(FinancialOpenItem).where(
        FinancialOpenItem.company_id == payment.company_id, FinancialOpenItem.ledger_type == "AP",
        FinancialOpenItem.party_id == payment.supplier_id, FinancialOpenItem.document_date <= payment.payment_date,
    ).order_by(FinancialOpenItem.due_date, FinancialOpenItem.document_date, FinancialOpenItem.id)).all():
        remaining = open_amount(db, item)
        if remaining <= 0 or available <= 0:
            continue
        applied = min(remaining, available)
        lines.append({"open_item_id": item.id, "amount": applied}); available -= applied
    if not lines:
        return {"payment_id": payment.id, "allocated_amount": settlement_allocated_total(db, payment_id=payment.id), "unapplied_amount": available, "allocations": []}
    rows = allocate_payment(db, payment, lines, user_id=user.id)
    write_audit(db, action="AP_PAYMENT_AUTO_ALLOCATED", entity_type="PAYMENT", entity_id=payment.id, user_id=user.id, company_id=payment.company_id, after={"allocation_count": len(rows)})
    db.commit()
    return {"payment_id": payment.id, "allocated_amount": settlement_allocated_total(db, payment_id=payment.id), "unapplied_amount": available, "allocations": [_allocation_dict(r) for r in rows]}


@router.post("/allocations/{allocation_id}/reverse")
def reverse_allocation(allocation_id: int, reason: str = Query(min_length=3, max_length=500), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FinancialSettlementAllocation, allocation_id)
    if not row:
        raise HTTPException(404, "Allocation not found")
    ensure_permission(db, user, row.company_id, "finance.arap.allocate")
    if row.reversed_at is not None:
        raise HTTPException(409, "Allocation is already reversed")
    row.reversed_by = user.id; row.reversed_at = utc_now(); row.reversal_reason = reason
    refresh_open_item_status(db, row.open_item)
    write_audit(db, action="ARAP_ALLOCATION_REVERSED", entity_type="FINANCIAL_ALLOCATION", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"reason": reason, "amount": str(row.amount)})
    db.commit()
    return _allocation_dict(row)


@router.post("/open-items/opening-balances", status_code=201)
def create_opening_balance(data: OpeningBalanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.arap.opening")
    ledger = data.ledger_type.upper()
    party = get_party(db, data.company_id, data.party_id, {"CUSTOMER" if ledger == "AR" else "SUPPLIER"})
    if data.due_date < data.document_date:
        raise HTTPException(422, "Due date cannot be before document date")
    duplicate = db.scalar(select(FinancialOpenItem.id).where(FinancialOpenItem.company_id == data.company_id, FinancialOpenItem.ledger_type == ledger, FinancialOpenItem.document_number == data.document_number))
    if duplicate:
        raise HTTPException(409, "Opening document number already exists")
    journal = None
    if data.post_to_gl:
        ensure_open_period(db, data.company_id, data.document_date)
        if not data.offset_account_code:
            raise HTTPException(422, "offset_account_code is required when post_to_gl is true")
        control = get_account(db, data.company_id, "112010" if ledger == "AR" else "211010")
        offset = get_account(db, data.company_id, data.offset_account_code)
        amount = arap_money(data.amount)
        lines = ([{"account_id": control.id, "debit": amount, "credit": 0}, {"account_id": offset.id, "debit": 0, "credit": amount}]
                 if ledger == "AR" else
                 [{"account_id": offset.id, "debit": amount, "credit": 0}, {"account_id": control.id, "debit": 0, "credit": amount}])
        journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.document_date, reference=data.document_number, description=f"{ledger} opening item {data.document_number}", lines=lines)
    item = FinancialOpenItem(
        company_id=data.company_id, ledger_type=ledger, party_id=party.id, source_type="OPENING_BALANCE",
        source_id=None, document_number=data.document_number, document_date=data.document_date, due_date=data.due_date,
        original_amount=arap_money(data.amount), status="OPEN", journal_id=journal.id if journal else None,
        notes=data.notes, created_by=user.id,
    )
    db.add(item); db.flush()
    write_audit(db, action="ARAP_OPENING_ITEM_CREATED", entity_type="FINANCIAL_OPEN_ITEM", entity_id=item.id, user_id=user.id, company_id=data.company_id, after={"ledger_type": ledger, "document_number": item.document_number, "amount": str(item.original_amount), "posted_to_gl": bool(journal)})
    db.commit()
    return serialize_open_item(db, item)


@router.get("/aging")
def aging_report(
    company_id: int, ledger_type: str, as_of_date: date | None = None, party_id: int | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.arap.read")
    ledger = ledger_type.upper()
    if ledger not in {"AR", "AP"}:
        raise HTTPException(422, "ledger_type must be AR or AP")
    effective = as_of_date or date.today()
    query = select(FinancialOpenItem).where(
        FinancialOpenItem.company_id == company_id, FinancialOpenItem.ledger_type == ledger,
        FinancialOpenItem.document_date <= effective,
    ).order_by(FinancialOpenItem.party_id, FinancialOpenItem.due_date, FinancialOpenItem.id)
    if party_id:
        query = query.where(FinancialOpenItem.party_id == party_id)
    bucket_names = ["CURRENT", "1_30", "31_60", "61_90", "91_120", "OVER_120"]
    totals = {name: Decimal("0") for name in bucket_names}
    party_map: dict[int, dict] = {}
    details = []
    gross_open = Decimal("0")
    for item in db.scalars(query).all():
        row = serialize_open_item(db, item, effective)
        outstanding = arap_money(row["outstanding_amount"])
        if outstanding <= 0:
            continue
        overdue_days = max(0, (effective - item.due_date).days)
        bucket = "CURRENT" if overdue_days == 0 else "1_30" if overdue_days <= 30 else "31_60" if overdue_days <= 60 else "61_90" if overdue_days <= 90 else "91_120" if overdue_days <= 120 else "OVER_120"
        row.update({"overdue_days": overdue_days, "bucket": bucket})
        details.append(row); totals[bucket] += outstanding; gross_open += outstanding
        summary = party_map.setdefault(item.party_id, {"party_id": item.party_id, "party_code": item.party.code, "party_name_ar": item.party.name_ar, "party_name_en": item.party.name_en, **{name: Decimal("0") for name in bucket_names}, "total": Decimal("0")})
        summary[bucket] += outstanding; summary["total"] += outstanding

    if ledger == "AR":
        settlements = db.scalars(select(Receipt).where(Receipt.company_id == company_id, Receipt.receipt_date <= effective, *( [Receipt.customer_id == party_id] if party_id else [] ))).all()
        unapplied = sum((arap_money(row.amount) - settlement_allocated_total(db, receipt_id=row.id, as_of_date=effective) for row in settlements), Decimal("0"))
        gl_balance = _account_balance_as_of(db, company_id, "112010", effective)
    else:
        settlements = db.scalars(select(Payment).where(Payment.company_id == company_id, Payment.payment_date <= effective, *( [Payment.supplier_id == party_id] if party_id else [] ))).all()
        unapplied = sum((arap_money(row.amount) - settlement_allocated_total(db, payment_id=row.id, as_of_date=effective) for row in settlements), Decimal("0"))
        gl_balance = _account_balance_as_of(db, company_id, "211010", effective)
    unapplied = arap_money(unapplied)
    credit_query = select(func.coalesce(func.sum(PartyCreditBalance.available_amount), 0)).where(
        PartyCreditBalance.company_id == company_id, PartyCreditBalance.ledger_type == ledger,
        PartyCreditBalance.balance_date <= effective, PartyCreditBalance.status == "OPEN",
    )
    if party_id:
        credit_query = credit_query.where(PartyCreditBalance.party_id == party_id)
    unapplied_credit_notes = arap_money(db.scalar(credit_query) or 0)
    net_subledger = arap_money(gross_open - unapplied - unapplied_credit_notes)
    if party_id:
        gl_value = None
        difference = None
        reconciled = None
    else:
        gl_value = gl_balance
        difference = arap_money(net_subledger - gl_balance)
        reconciled = difference == 0
    return {
        "company_id": company_id, "ledger_type": ledger, "as_of_date": effective,
        "buckets": {key: arap_money(value) for key, value in totals.items()},
        "gross_open_items": arap_money(gross_open), "unapplied_settlements": unapplied,
        "unapplied_credit_notes": unapplied_credit_notes,
        "net_subledger_balance": net_subledger, "gl_control_balance": gl_value,
        "reconciliation_difference": difference, "reconciled": reconciled,
        "party_summaries": [{**row, **{key: arap_money(row[key]) for key in bucket_names}, "total": arap_money(row["total"])} for row in party_map.values()],
        "details": details,
    }

def account_net(db: Session, company_id: int, code: str) -> Decimal:
    debit, credit = db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(Account.company_id == company_id, Account.code == code, JournalEntry.status.in_(["POSTED", "REVERSED"]))
    ).one()
    return Decimal(debit) - Decimal(credit)


@router.get("/summary")
def subledger_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    return {
        "company_id": company_id,
        "cash_balance": account_net(db, company_id, "111010"),
        "accounts_receivable": account_net(db, company_id, "112010"),
        "accounts_payable": -account_net(db, company_id, "211010"),
        "sales_invoices": db.scalar(select(func.count(SalesInvoice.id)).where(SalesInvoice.company_id == company_id)),
        "purchase_invoices": db.scalar(select(func.count(PurchaseInvoice.id)).where(PurchaseInvoice.company_id == company_id)),
        "receipts": db.scalar(select(func.count(Receipt.id)).where(Receipt.company_id == company_id)),
        "payments": db.scalar(select(func.count(Payment.id)).where(Payment.company_id == company_id)),
        "ar_open_items": db.scalar(select(func.count(FinancialOpenItem.id)).where(FinancialOpenItem.company_id == company_id, FinancialOpenItem.ledger_type == "AR")) or 0,
        "ap_open_items": db.scalar(select(func.count(FinancialOpenItem.id)).where(FinancialOpenItem.company_id == company_id, FinancialOpenItem.ledger_type == "AP")) or 0,
        "reconciliation": "NATIVE_OPEN_ITEM_ALLOCATION",
    }


# --- H8-INVOICE-READ-ENDPOINTS ---------------------------------------------
def _serialize_sales_invoice(invoice: SalesInvoice, *, with_lines: bool) -> dict:
    data = {
        "id": invoice.id,
        "company_id": invoice.company_id,
        "number": invoice.number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "customer_id": invoice.customer_id,
        "customer_name_ar": getattr(invoice.customer, "name_ar", None),
        "customer_name_en": getattr(invoice.customer, "name_en", None),
        "reference": invoice.reference,
        "status": invoice.status,
        "subtotal": invoice.subtotal,
        "vat_amount": invoice.vat_amount,
        "total": invoice.total,
        "journal_id": invoice.journal_id,
    }
    if with_lines:
        data["lines"] = [
            {
                "id": line.id,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "vat_rate": line.vat_rate,
                "subtotal": line.subtotal,
                "vat_amount": line.vat_amount,
                "total": line.total,
            }
            for line in invoice.lines
        ]
    return data


def _serialize_purchase_invoice(invoice: PurchaseInvoice, *, with_lines: bool) -> dict:
    data = {
        "id": invoice.id,
        "company_id": invoice.company_id,
        "number": invoice.number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "supplier_id": invoice.supplier_id,
        "supplier_name_ar": getattr(invoice.supplier, "name_ar", None),
        "supplier_name_en": getattr(invoice.supplier, "name_en", None),
        "supplier_invoice_number": invoice.supplier_invoice_number,
        "status": invoice.status,
        "subtotal": invoice.subtotal,
        "vat_amount": invoice.vat_amount,
        "total": invoice.total,
        "journal_id": invoice.journal_id,
    }
    if with_lines:
        data["lines"] = [
            {
                "id": line.id,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "vat_rate": line.vat_rate,
                "subtotal": line.subtotal,
                "vat_amount": line.vat_amount,
                "total": line.total,
            }
            for line in invoice.lines
        ]
    return data


@router.get("/sales-invoices")
def list_sales_invoices(
    company_id: int,
    status: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.read")
    query = select(SalesInvoice).where(SalesInvoice.company_id == company_id)
    if status:
        query = query.where(SalesInvoice.status == status)
    query = query.order_by(SalesInvoice.invoice_date.desc(), SalesInvoice.id.desc())
    rows = db.scalars(query).all()
    return [_serialize_sales_invoice(invoice, with_lines=False) for invoice in rows]


@router.get("/sales-invoices/{invoice_id}")
def get_sales_invoice(
    invoice_id: int,
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.read")
    invoice = db.scalar(
        select(SalesInvoice)
        .options(selectinload(SalesInvoice.lines))
        .where(SalesInvoice.id == invoice_id, SalesInvoice.company_id == company_id)
    )
    if not invoice:
        raise HTTPException(404, "Sales invoice not found")
    return _serialize_sales_invoice(invoice, with_lines=True)


@router.get("/purchase-invoices")
def list_purchase_invoices(
    company_id: int,
    status: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.read")
    query = select(PurchaseInvoice).where(PurchaseInvoice.company_id == company_id)
    if status:
        query = query.where(PurchaseInvoice.status == status)
    query = query.order_by(PurchaseInvoice.invoice_date.desc(), PurchaseInvoice.id.desc())
    rows = db.scalars(query).all()
    return [_serialize_purchase_invoice(invoice, with_lines=False) for invoice in rows]


@router.get("/purchase-invoices/{invoice_id}")
def get_purchase_invoice(
    invoice_id: int,
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.read")
    invoice = db.scalar(
        select(PurchaseInvoice)
        .options(selectinload(PurchaseInvoice.lines))
        .where(PurchaseInvoice.id == invoice_id, PurchaseInvoice.company_id == company_id)
    )
    if not invoice:
        raise HTTPException(404, "Purchase invoice not found")
    return _serialize_purchase_invoice(invoice, with_lines=True)
# --- end H8-INVOICE-READ-ENDPOINTS -----------------------------------------
