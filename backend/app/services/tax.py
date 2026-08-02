from __future__ import annotations

import json
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Account, CreditNote, CreditNoteLine, JournalEntry, JournalLine, MenuItem, PosControlLine, PosControlRequest,
    PosOrder, PosOrderLine, PurchaseInvoice, PurchaseInvoiceLine, SalesInvoice, SalesInvoiceLine, TaxCode,
    VatReturnLine, VatReturnSnapshot, VatReportingProfile, ImportDeclaration, ExportEvidence, AssetLifecycleTransaction,
)

MONEY = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


DEFAULT_TAX_CODES = [
    # code, ar, en, direction, category, rate, box, deductible, ZATCA category
    ("S15", "مبيعات محلية خاضعة 15%", "Standard-rated domestic sales 15%", "SALES", "STANDARD", "15", "SALES_STANDARD", "0", "S"),
    ("S0", "مبيعات محلية خاضعة بنسبة صفر", "Zero-rated domestic sales", "SALES", "ZERO_RATED", "0", "SALES_ZERO", "0", "Z"),
    ("SEX", "صادرات خاضعة بنسبة صفر", "Zero-rated exports", "SALES", "EXPORT", "0", "SALES_EXPORT", "0", "Z"),
    ("SE", "مبيعات معفاة", "Exempt sales", "SALES", "EXEMPT", "0", "SALES_EXEMPT", "0", "E"),
    ("SOOS", "مبيعات خارج نطاق الضريبة", "Out-of-scope sales", "SALES", "OUT_OF_SCOPE", "0", "SALES_OUT_OF_SCOPE", "0", "O"),
    ("P15", "مشتريات محلية خاضعة 15%", "Standard-rated domestic purchases 15%", "PURCHASE", "STANDARD", "15", "PURCHASE_STANDARD", "100", "S"),
    ("P0", "مشتريات خاضعة بنسبة صفر", "Zero-rated purchases", "PURCHASE", "ZERO_RATED", "0", "PURCHASE_ZERO", "0", "Z"),
    ("PE", "مشتريات معفاة", "Exempt purchases", "PURCHASE", "EXEMPT", "0", "PURCHASE_EXEMPT", "0", "E"),
    ("POOS", "مشتريات خارج نطاق الضريبة", "Out-of-scope purchases", "PURCHASE", "OUT_OF_SCOPE", "0", "PURCHASE_OUT_OF_SCOPE", "0", "O"),
    ("PIMP15", "واردات وضريبتها مسددة في الجمارك 15%", "Imports with VAT paid at customs 15%", "PURCHASE", "IMPORTS_CUSTOMS", "15", "PURCHASE_IMPORTS_CUSTOMS", "100", "S"),
    ("PRC15", "خدمات أو مشتريات خاضعة للاحتساب العكسي 15%", "Reverse-charge purchases 15%", "PURCHASE", "REVERSE_CHARGE", "15", "PURCHASE_REVERSE_CHARGE", "100", "S"),
    ("PND15", "مشتريات خاضعة بضريبة غير قابلة للخصم 15%", "Purchases with non-deductible VAT 15%", "PURCHASE", "NON_DEDUCTIBLE", "15", "PURCHASE_NON_DEDUCTIBLE", "0", "S"),
    ("PFOR0", "فاتورة مورد أجنبي بدون ضريبة سعودية", "Foreign supplier invoice without Saudi VAT", "PURCHASE", "FOREIGN_SUPPLIER", "0", "PURCHASE_FOREIGN_NO_SAUDI_VAT", "0", "O"),
    ("PIMPR15", "واردات تُحتسب ضريبتها عبر الإقرار", "Imports VAT accounted through the VAT return", "PURCHASE", "IMPORTS_RETURN", "15", "PURCHASE_IMPORTS_THROUGH_RETURN", "100", "S"),
    ("PIMPS0", "واردات معلقة جمركيًا", "Customs-suspended imports", "PURCHASE", "IMPORTS_SUSPENDED", "0", "PURCHASE_IMPORTS_SUSPENDED", "0", "O"),
    ("PIMPE", "واردات معفاة", "Exempt imports", "PURCHASE", "IMPORTS_EXEMPT", "0", "PURCHASE_IMPORTS_EXEMPT", "0", "E"),
]

BOX_NAMES = {
    "SALES_STANDARD": ("المبيعات المحلية الخاضعة للنسبة الأساسية", "Standard-rated domestic sales"),
    "SALES_ZERO": ("المبيعات المحلية الخاضعة بنسبة صفر", "Zero-rated domestic sales"),
    "SALES_EXPORT": ("الصادرات الخاضعة بنسبة صفر", "Zero-rated exports"),
    "SALES_EXPORT_PENDING_EVIDENCE": ("صادرات معلقة لحين اكتمال مستندات الإثبات", "Exports pending supporting evidence"),
    "SALES_EXEMPT": ("المبيعات المعفاة", "Exempt sales"),
    "SALES_OUT_OF_SCOPE": ("المبيعات خارج النطاق – معلومات رقابية", "Out-of-scope sales – control information"),
    "PURCHASE_STANDARD": ("المشتريات المحلية الخاضعة للنسبة الأساسية", "Standard-rated domestic purchases"),
    "PURCHASE_IMPORTS_CUSTOMS": ("الواردات المسددة ضريبتها في الجمارك", "Imports with VAT paid at customs"),
    "PURCHASE_REVERSE_CHARGE": ("المشتريات الخاضعة للاحتساب العكسي", "Reverse-charge purchases"),
    "PURCHASE_ZERO": ("المشتريات الخاضعة بنسبة صفر", "Zero-rated purchases"),
    "PURCHASE_EXEMPT": ("المشتريات المعفاة", "Exempt purchases"),
    "PURCHASE_OUT_OF_SCOPE": ("المشتريات خارج النطاق – معلومات رقابية", "Out-of-scope purchases – control information"),
    "PURCHASE_NON_DEDUCTIBLE": ("المشتريات ذات الضريبة غير القابلة للخصم", "Purchases with non-deductible VAT"),
    "PURCHASE_FOREIGN_NO_SAUDI_VAT": ("فواتير الموردين الأجانب بدون ضريبة سعودية – معلومات رقابية", "Foreign supplier invoices without Saudi VAT – control information"),
    "PURCHASE_IMPORTS_THROUGH_RETURN": ("واردات تُحتسب ضريبتها عبر الإقرار", "Imports VAT accounted through the return"),
    "PURCHASE_IMPORTS_SUSPENDED": ("واردات معلقة جمركيًا – معلومات رقابية", "Customs-suspended imports – control information"),
    "PURCHASE_IMPORTS_EXEMPT": ("واردات معفاة – معلومات رقابية", "Exempt imports – control information"),
}


def ensure_default_tax_codes(db: Session, company_id: int, user_id: int | None = None) -> dict[str, TaxCode]:
    existing = {row.code: row for row in db.scalars(select(TaxCode).where(TaxCode.company_id == company_id)).all()}
    for code, ar, en, direction, category, rate, box, deductible, zatca_category in DEFAULT_TAX_CODES:
        if code in existing:
            continue
        row = TaxCode(
            company_id=company_id, code=code, name_ar=ar, name_en=en, direction=direction,
            category=category, rate=Decimal(rate), return_box=box,
            deductible_percent=Decimal(deductible), tax_category_code=zatca_category,
            effective_from=date(2020, 7, 1), system_code=True, active=True, created_by=user_id,
        )
        db.add(row)
        db.flush()
        existing[code] = row
    return existing


def get_tax_code(db: Session, company_id: int, *, code: str | None, direction: str, vat_rate: Decimal | None = None, user_id: int | None = None) -> TaxCode:
    codes = ensure_default_tax_codes(db, company_id, user_id)
    direction = direction.upper()
    if code:
        row = codes.get(code.upper()) or db.scalar(select(TaxCode).where(TaxCode.company_id == company_id, TaxCode.code == code.upper(), TaxCode.active.is_(True)))
        if not row:
            raise HTTPException(422, f"Unknown tax code: {code}")
    else:
        rate = money(Decimal("15") if vat_rate is None else vat_rate)
        if rate != Decimal("15.00"):
            raise HTTPException(422, "Non-standard, zero-rated, exempt and out-of-scope transactions require an explicit tax code")
        row = codes["S15" if direction == "SALES" else "P15"]
    if row.direction not in {direction, "BOTH"}:
        raise HTTPException(422, f"Tax code {row.code} cannot be used for {direction.lower()} transactions")
    if vat_rate is not None and money(vat_rate) != money(row.rate):
        raise HTTPException(422, f"Tax code {row.code} requires VAT rate {money(row.rate)}")
    return row


def calculate_line(base: Decimal, tax_code: TaxCode) -> dict[str, Decimal]:
    base = money(base)
    tax = money(base * Decimal(tax_code.rate) / Decimal("100"))
    category = tax_code.category.upper()
    if category in {"ZERO_RATED", "EXPORT", "EXEMPT", "OUT_OF_SCOPE", "FOREIGN_SUPPLIER", "IMPORTS_SUSPENDED", "IMPORTS_EXEMPT"}:
        tax = Decimal("0.00")
    deductible = money(tax * Decimal(tax_code.deductible_percent) / Decimal("100"))
    non_deductible = money(tax - deductible)
    payable_tax = Decimal("0.00") if category in {"REVERSE_CHARGE", "IMPORTS_RETURN"} else tax
    return {
        "base": base,
        "tax": tax,
        "deductible_tax": deductible,
        "non_deductible_tax": non_deductible,
        "document_total": money(base + payable_tax),
    }


def serialize_tax_code(row: TaxCode) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "code": row.code,
        "name_ar": row.name_ar, "name_en": row.name_en, "direction": row.direction,
        "category": row.category, "rate": money(row.rate), "return_box": row.return_box,
        "deductible_percent": money(row.deductible_percent), "tax_category_code": row.tax_category_code,
        "exemption_reason_code": row.exemption_reason_code, "exemption_reason": row.exemption_reason,
        "effective_from": row.effective_from, "effective_to": row.effective_to,
        "system_code": row.system_code, "active": row.active,
    }


def _account_movement(db: Session, company_id: int, code: str, start: date, end: date, *, natural: str) -> Decimal:
    account_id = db.scalar(select(Account.id).where(Account.company_id == company_id, Account.code == code))
    if not account_id:
        return Decimal("0.00")
    debit, credit = db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalEntry.company_id == company_id, JournalEntry.status.in_(["POSTED", "REVERSED"]),
               JournalEntry.entry_date.between(start, end), JournalLine.account_id == account_id)
    ).one()
    return money(Decimal(credit) - Decimal(debit) if natural == "CREDIT" else Decimal(debit) - Decimal(credit))


def _aggregate_line(boxes: dict, code: TaxCode, *, base: Decimal, tax: Decimal, source: str, source_id: int, deductible_tax: Decimal | None = None):
    box = boxes[code.return_box]
    box["base"] += money(base)
    box["tax"] += money(tax if deductible_tax is None else deductible_tax)
    box["count"] += 1
    box["sources"][source] += 1
    if len(box["sample_ids"]) < 20:
        box["sample_ids"].append(source_id)


def _validate_vat_period(db: Session, company_id: int, period_start: date, period_end: date) -> None:
    if period_end < period_start:
        raise HTTPException(422, "Invalid VAT period")
    month_end = date(period_start.year, period_start.month, monthrange(period_start.year, period_start.month)[1])
    valid_month = period_start.day == 1 and period_end == month_end
    quarter_end_month = period_start.month + 2
    valid_quarter = (
        period_start.day == 1
        and period_start.month in {1, 4, 7, 10}
        and period_end == date(period_start.year, quarter_end_month, monthrange(period_start.year, quarter_end_month)[1])
    )
    profile = db.scalar(select(VatReportingProfile).where(VatReportingProfile.company_id == company_id))
    frequency = profile.filing_frequency if profile else None
    if frequency == "MONTHLY" and not valid_month:
        raise HTTPException(422, "VAT period must be one complete calendar month for the configured MONTHLY filing frequency")
    if frequency == "QUARTERLY" and not valid_quarter:
        raise HTTPException(422, "VAT period must be one complete calendar quarter for the configured QUARTERLY filing frequency")
    if frequency is None and not (valid_month or valid_quarter):
        raise HTTPException(422, "VAT period must be a complete calendar month or calendar quarter")
    overlaps = db.scalars(select(VatReturnSnapshot).where(
        VatReturnSnapshot.company_id == company_id,
        VatReturnSnapshot.period_start <= period_end,
        VatReturnSnapshot.period_end >= period_start,
    )).all()
    if any(row.period_start != period_start or row.period_end != period_end for row in overlaps):
        raise HTTPException(409, "VAT return period overlaps an existing VAT return")


def build_vat_return(db: Session, *, company_id: int, period_start: date, period_end: date, user_id: int) -> VatReturnSnapshot:
    _validate_vat_period(db, company_id, period_start, period_end)
    ensure_default_tax_codes(db, company_id, user_id)
    row = db.scalar(select(VatReturnSnapshot).where(
        VatReturnSnapshot.company_id == company_id,
        VatReturnSnapshot.period_start == period_start,
        VatReturnSnapshot.period_end == period_end,
    ).options(selectinload(VatReturnSnapshot.lines)))
    if row and row.status == "APPROVED":
        raise HTTPException(409, "Approved VAT return snapshot cannot be regenerated")
    preserved_adjustments: dict[str, tuple[Decimal, Decimal]] = {}
    if row:
        preserved_adjustments = {
            line.box_code: (money(line.adjustment_base), money(line.adjustment_tax))
            for line in row.lines
        }
    if not row:
        row = VatReturnSnapshot(company_id=company_id, period_start=period_start, period_end=period_end, created_by=user_id)
        db.add(row); db.flush()
    else:
        db.execute(delete(VatReturnLine).where(VatReturnLine.vat_return_id == row.id))
        row.status = "DRAFT"; row.submitted_by = None; row.submitted_at = None; row.approved_by = None; row.approved_at = None

    boxes = {box: {"base": Decimal("0"), "tax": Decimal("0"), "count": 0, "sources": defaultdict(int), "sample_ids": []} for box in BOX_NAMES}
    unclassified = []

    sales_lines = db.scalars(
        select(SalesInvoiceLine).join(SalesInvoice).where(
            SalesInvoice.company_id == company_id, SalesInvoice.status == "POSTED",
            SalesInvoice.invoice_date.between(period_start, period_end),
        ).options(selectinload(SalesInvoiceLine.tax_code), selectinload(SalesInvoiceLine.invoice))
    ).all()
    for line in sales_lines:
        code = line.tax_code
        if not code and money(line.vat_rate) == Decimal("15.00"):
            code = ensure_default_tax_codes(db, company_id, user_id)["S15"]
        if not code or not code.return_box:
            unclassified.append({"source": "SALES_INVOICE_LINE", "id": line.id, "vat_rate": str(line.vat_rate)}); continue
        if code.category == "EXPORT":
            evidence = db.scalar(select(ExportEvidence).where(
                ExportEvidence.company_id == company_id, ExportEvidence.sales_invoice_id == line.invoice_id,
                ExportEvidence.status == "APPROVED",
            ))
            if not evidence:
                pending = boxes["SALES_EXPORT_PENDING_EVIDENCE"]
                pending["base"] += money(line.subtotal); pending["count"] += 1
                pending["sources"]["SALES_INVOICE"] += 1
                if len(pending["sample_ids"]) < 20: pending["sample_ids"].append(line.invoice_id)
                unclassified.append({"source": "EXPORT_EVIDENCE", "id": line.invoice_id, "reason": "Approved export evidence is missing"})
                continue
        _aggregate_line(boxes, code, base=Decimal(line.subtotal), tax=Decimal(line.vat_amount), source="SALES_INVOICE", source_id=line.invoice_id)

    pos_lines = db.scalars(
        select(PosOrderLine).join(PosOrder).where(
            PosOrder.company_id == company_id, PosOrder.sale_journal_id.is_not(None),
            PosOrder.order_date.between(period_start, period_end),
        ).options(selectinload(PosOrderLine.tax_code), selectinload(PosOrderLine.menu_item), selectinload(PosOrderLine.order))
    ).all()
    for line in pos_lines:
        code = line.tax_code or (line.menu_item.tax_code if line.menu_item else None)
        if not code and line.menu_item and money(line.menu_item.vat_rate) == Decimal("15.00"):
            code = ensure_default_tax_codes(db, company_id, user_id)["S15"]
        if not code:
            unclassified.append({"source": "POS_ORDER_LINE", "id": line.id, "vat_rate": str(line.menu_item.vat_rate if line.menu_item else 0)}); continue
        _aggregate_line(boxes, code, base=Decimal(line.net_amount), tax=Decimal(line.vat_amount), source="POS_ORDER", source_id=line.pos_order_id)

    # Approved POS returns/voids are separate tax adjustments in the approval period.
    pos_return_lines = db.scalars(
        select(PosControlLine).join(PosControlRequest).where(
            PosControlRequest.company_id == company_id, PosControlRequest.status == "APPROVED_POSTED",
            func.date(PosControlRequest.approved_at).between(period_start, period_end),
        ).options(selectinload(PosControlLine.order_line).selectinload(PosOrderLine.tax_code),
                  selectinload(PosControlLine.order_line).selectinload(PosOrderLine.menu_item))
    ).all()
    for return_line in pos_return_lines:
        original = return_line.order_line
        code = original.tax_code or (original.menu_item.tax_code if original.menu_item else None)
        if not code and original.menu_item and money(original.menu_item.vat_rate) == Decimal("15.00"):
            code = ensure_default_tax_codes(db, company_id, user_id)["S15"]
        if not code:
            unclassified.append({"source": "POS_CONTROL_LINE", "id": return_line.id, "reason": "Original POS tax code is unavailable"}); continue
        _aggregate_line(boxes, code, base=-Decimal(return_line.refund_net), tax=-Decimal(return_line.refund_vat),
                        source="POS_CREDIT_NOTE", source_id=return_line.control_request_id)

    # General sales credit notes reduce the original VAT return box in the note period.
    sales_credit_lines = db.scalars(
        select(CreditNoteLine).join(CreditNote).where(
            CreditNote.company_id == company_id, CreditNote.note_type == "SALES",
            CreditNote.status == "APPROVED_POSTED", CreditNote.note_date.between(period_start, period_end),
        ).options(selectinload(CreditNoteLine.tax_code), selectinload(CreditNoteLine.credit_note))
    ).all()
    for credit_line in sales_credit_lines:
        code = credit_line.tax_code
        if code.category == "EXPORT":
            original_invoice_id = credit_line.credit_note.original_sales_invoice_id
            evidence = db.scalar(select(ExportEvidence).where(
                ExportEvidence.company_id == company_id, ExportEvidence.sales_invoice_id == original_invoice_id,
                ExportEvidence.status == "APPROVED",
            ))
            if not evidence:
                pending = boxes["SALES_EXPORT_PENDING_EVIDENCE"]
                pending["base"] -= money(credit_line.subtotal); pending["count"] += 1
                pending["sources"]["SALES_CREDIT_NOTE"] += 1
                if len(pending["sample_ids"]) < 20: pending["sample_ids"].append(credit_line.credit_note_id)
                continue
        _aggregate_line(boxes, code, base=-Decimal(credit_line.subtotal), tax=-Decimal(credit_line.vat_amount),
                        source="SALES_CREDIT_NOTE", source_id=credit_line.credit_note_id)

    # Disposals of fixed assets are taxable supplies when a sales tax code is selected.
    asset_sales = db.scalars(
        select(AssetLifecycleTransaction).where(
            AssetLifecycleTransaction.company_id == company_id,
            AssetLifecycleTransaction.transaction_type == "SALE",
            AssetLifecycleTransaction.status == "APPROVED_POSTED",
            AssetLifecycleTransaction.transaction_date.between(period_start, period_end),
        ).options(selectinload(AssetLifecycleTransaction.tax_code))
    ).all()
    for asset_sale in asset_sales:
        code = asset_sale.tax_code
        if not code:
            unclassified.append({"source": "ASSET_SALE", "id": asset_sale.id, "reason": "Missing sales tax code"})
            continue
        _aggregate_line(boxes, code, base=Decimal(asset_sale.proceeds_net), tax=Decimal(asset_sale.vat_amount),
                        source="ASSET_SALE", source_id=asset_sale.id)

    purchase_lines = db.scalars(
        select(PurchaseInvoiceLine).join(PurchaseInvoice).where(
            PurchaseInvoice.company_id == company_id, PurchaseInvoice.status == "POSTED",
            PurchaseInvoice.invoice_date.between(period_start, period_end),
        ).options(selectinload(PurchaseInvoiceLine.tax_code), selectinload(PurchaseInvoiceLine.invoice))
    ).all()
    reverse_charge_output = Decimal("0")
    non_deductible_tax = Decimal("0")
    for line in purchase_lines:
        code = line.tax_code
        if not code and money(line.vat_rate) == Decimal("15.00"):
            code = ensure_default_tax_codes(db, company_id, user_id)["P15"]
        if not code:
            unclassified.append({"source": "PURCHASE_INVOICE_LINE", "id": line.id, "vat_rate": str(line.vat_rate)}); continue
        calc = calculate_line(Decimal(line.subtotal), code)
        if code.category == "REVERSE_CHARGE":
            reverse_charge_output += calc["tax"]
        if code.category == "NON_DEDUCTIBLE":
            non_deductible_tax += calc["tax"]
        _aggregate_line(boxes, code, base=Decimal(line.subtotal), tax=Decimal(line.vat_amount), deductible_tax=(None if code.category == "NON_DEDUCTIBLE" else calc["deductible_tax"]), source="PURCHASE_INVOICE", source_id=line.invoice_id)

    # Supplier credit notes reduce deductible input VAT and reverse-charge output VAT in the note period.
    purchase_credit_lines = db.scalars(
        select(CreditNoteLine).join(CreditNote).where(
            CreditNote.company_id == company_id, CreditNote.note_type == "PURCHASE",
            CreditNote.status == "APPROVED_POSTED", CreditNote.note_date.between(period_start, period_end),
        ).options(selectinload(CreditNoteLine.tax_code))
    ).all()
    for credit_line in purchase_credit_lines:
        code = credit_line.tax_code
        calc = calculate_line(Decimal(credit_line.subtotal), code)
        if code.category in {"REVERSE_CHARGE", "IMPORTS_RETURN"}:
            reverse_charge_output -= calc["tax"]
        if code.category == "NON_DEDUCTIBLE":
            non_deductible_tax -= calc["tax"]
        _aggregate_line(boxes, code, base=-Decimal(credit_line.subtotal), tax=-Decimal(credit_line.vat_amount),
                        deductible_tax=(None if code.category == "NON_DEDUCTIBLE" else -calc["deductible_tax"]),
                        source="PURCHASE_CREDIT_NOTE", source_id=credit_line.credit_note_id)

    import_rows = db.scalars(select(ImportDeclaration).where(
        ImportDeclaration.company_id == company_id, ImportDeclaration.status == "POSTED",
        ImportDeclaration.declaration_date.between(period_start, period_end),
    )).all()
    import_return_output = Decimal("0")
    for declaration in import_rows:
        treatment = declaration.treatment.upper()
        if treatment == "AT_CUSTOMS":
            box = boxes["PURCHASE_IMPORTS_CUSTOMS"]
            box["base"] += money(declaration.vat_base); box["tax"] += money(declaration.vat_collected_on_declaration)
        elif treatment == "THROUGH_RETURN":
            box = boxes["PURCHASE_IMPORTS_THROUGH_RETURN"]
            tax = money(declaration.vat_accounted_in_return or declaration.vat_due)
            box["base"] += money(declaration.vat_base); box["tax"] += tax; import_return_output += tax
        elif treatment == "SUSPENDED":
            box = boxes["PURCHASE_IMPORTS_SUSPENDED"]; box["base"] += money(declaration.vat_base)
        elif treatment == "EXEMPT":
            box = boxes["PURCHASE_IMPORTS_EXEMPT"]; box["base"] += money(declaration.vat_base)
        else:
            unclassified.append({"source": "IMPORT_DECLARATION", "id": declaration.id, "reason": "Unknown import VAT treatment"}); continue
        box["count"] += 1; box["sources"]["IMPORT_DECLARATION"] += 1
        if len(box["sample_ids"]) < 20: box["sample_ids"].append(declaration.id)

    for box_code, values in boxes.items():
        ar, en = BOX_NAMES[box_code]
        adjustment_base, adjustment_tax = preserved_adjustments.get(
            box_code, (Decimal("0.00"), Decimal("0.00"))
        )
        row.lines.append(VatReturnLine(
            box_code=box_code, name_ar=ar, name_en=en,
            base_amount=money(values["base"]), tax_amount=money(values["tax"]),
            adjustment_base=adjustment_base, adjustment_tax=adjustment_tax,
            transaction_count=values["count"],
            details_json=json.dumps({"sources": dict(values["sources"]), "sample_source_ids": values["sample_ids"]}),
        ))

    standard_sales = money(boxes["SALES_STANDARD"]["base"])
    standard_purchases = money(boxes["PURCHASE_STANDARD"]["base"])
    output_boxes = {"SALES_STANDARD", "PURCHASE_REVERSE_CHARGE", "PURCHASE_IMPORTS_THROUGH_RETURN"}
    input_boxes = {"PURCHASE_STANDARD", "PURCHASE_IMPORTS_CUSTOMS", "PURCHASE_REVERSE_CHARGE", "PURCHASE_IMPORTS_THROUGH_RETURN"}
    line_by_box = {line.box_code: line for line in row.lines}
    output_vat = money(sum((
        Decimal(line_by_box[code].tax_amount) - Decimal(line_by_box[code].adjustment_tax)
        for code in output_boxes if code in line_by_box
    ), Decimal("0")))
    input_vat = money(sum((
        Decimal(line_by_box[code].tax_amount) - Decimal(line_by_box[code].adjustment_tax)
        for code in input_boxes if code in line_by_box
    ), Decimal("0")))
    net = money(
        output_vat - input_vat
        + Decimal(str(row.prior_period_correction or 0))
        - Decimal(str(row.carried_forward_vat or 0))
    )
    gl_output = _account_movement(db, company_id, "212010", period_start, period_end, natural="CREDIT")
    gl_input = _account_movement(db, company_id, "114010", period_start, period_end, natural="DEBIT")

    row.standard_rated_sales = standard_sales
    row.standard_rated_purchases = standard_purchases
    row.output_vat = output_vat
    row.input_vat = input_vat
    row.net_vat_payable = net
    row.gl_output_vat = gl_output
    row.gl_input_vat = gl_input
    row.output_reconciliation_difference = money(output_vat - gl_output)
    row.input_reconciliation_difference = money(input_vat - gl_input)
    row.classification_complete = len(unclassified) == 0
    row.status = "DRAFT"
    db.flush()
    return row


def serialize_vat_return(row: VatReturnSnapshot) -> dict:
    lines = sorted(row.lines, key=lambda x: x.box_code)
    total_sales = money(sum((
        Decimal(line.base_amount) - Decimal(line.adjustment_base)
        for line in lines
        if line.box_code.startswith("SALES_")
        and line.box_code not in {"SALES_OUT_OF_SCOPE", "SALES_EXPORT_PENDING_EVIDENCE"}
    ), Decimal("0")))
    purchase_control_boxes = {"PURCHASE_OUT_OF_SCOPE", "PURCHASE_FOREIGN_NO_SAUDI_VAT", "PURCHASE_IMPORTS_SUSPENDED", "PURCHASE_IMPORTS_EXEMPT"}
    total_purchases = money(sum((
        Decimal(line.base_amount) - Decimal(line.adjustment_base)
        for line in lines
        if line.box_code.startswith("PURCHASE_") and line.box_code not in purchase_control_boxes
    ), Decimal("0")))
    return {
        "id": row.id, "company_id": row.company_id, "period_start": row.period_start, "period_end": row.period_end,
        "status": row.status, "standard_rated_sales": money(row.standard_rated_sales),
        "standard_rated_purchases": money(row.standard_rated_purchases), "total_sales": total_sales,
        "total_purchases": total_purchases, "output_vat": money(row.output_vat), "input_vat": money(row.input_vat),
        "prior_period_correction": money(row.prior_period_correction),
        "carried_forward_vat": money(row.carried_forward_vat),
        "adjustment_reason": row.adjustment_reason,
        "adjustments_updated_by": row.adjustments_updated_by,
        "adjustments_updated_at": row.adjustments_updated_at,
        "net_vat_payable": money(row.net_vat_payable), "gl_output_vat": money(row.gl_output_vat),
        "gl_input_vat": money(row.gl_input_vat), "output_reconciliation_difference": money(row.output_reconciliation_difference),
        "input_reconciliation_difference": money(row.input_reconciliation_difference),
        "output_reconciled": money(row.output_reconciliation_difference) == 0,
        "input_reconciled": money(row.input_reconciliation_difference) == 0,
        "classification_complete": bool(row.classification_complete),
        "classification_note": "All source lines have explicit or safe standard-rate tax codes" if row.classification_complete else "One or more legacy non-standard lines require explicit tax-code classification",
        "submission_status": "NOT_SUBMITTED_TO_ZATCA", "production_claim": "INTERNAL_SNAPSHOT_ONLY",
        "lines": [{
            "box_code": line.box_code, "name_ar": line.name_ar, "name_en": line.name_en,
            "base_amount": money(line.base_amount), "tax_amount": money(line.tax_amount),
            "adjustment_base": money(line.adjustment_base), "adjustment_tax": money(line.adjustment_tax),
            "reported_base_amount": money(Decimal(line.base_amount) - Decimal(line.adjustment_base)),
            "reported_tax_amount": money(Decimal(line.tax_amount) - Decimal(line.adjustment_tax)),
            "transaction_count": line.transaction_count, "details": json.loads(line.details_json or "{}"),
        } for line in lines],
    }
