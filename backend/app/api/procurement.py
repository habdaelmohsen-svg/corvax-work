from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    GoodsReceipt, GoodsReceiptLine, Item, Party, PurchaseOrder, PurchaseOrderLine, PurchaseRequisition,
    PurchaseRequisitionLine, RequestForQuotation, RFQLine, RFQSupplier,
    SupplierQuotation, SupplierQuotationLine, User, Warehouse,
)
from app.models.ar_ap_allocation import FinancialOpenItem, FinancialSettlementAllocation
from app.models.finance import Payment, PurchaseInvoice, PurchaseInvoiceLine
from app.models.supply_chain import SupplierProcurementProfile
from app.services.audit import write_audit
from app.services.operations import get_item, get_warehouse, money, quantity


router = APIRouter(prefix="/procurement", tags=["controlled procurement R7"])


class RequisitionLineIn(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0)
    estimated_unit_price: Decimal = Field(default=Decimal("0"), ge=0)
    specifications: str | None = Field(default=None, max_length=500)


class RequisitionIn(BaseModel):
    company_id: int
    request_date: date
    needed_by: date
    warehouse_id: int
    suggested_supplier_id: int | None = None
    department: str = Field(min_length=2, max_length=120)
    justification: str = Field(min_length=5, max_length=500)
    lines: list[RequisitionLineIn] = Field(min_length=1)


class RejectionIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class RFQIn(BaseModel):
    company_id: int
    requisition_id: int
    issue_date: date
    closing_date: date
    supplier_ids: list[int] = Field(min_length=2)


class QuotationLineIn(BaseModel):
    rfq_line_id: int
    unit_price: Decimal = Field(gt=0)
    vat_rate: Decimal = Field(default=Decimal("15"), ge=0, le=100)


class QuotationIn(BaseModel):
    company_id: int
    rfq_id: int
    supplier_id: int
    supplier_reference: str = Field(min_length=2, max_length=100)
    quote_date: date
    valid_until: date
    lead_time_days: int = Field(default=0, ge=0, le=3650)
    payment_terms: str | None = Field(default=None, max_length=250)
    lines: list[QuotationLineIn] = Field(min_length=1)


class AwardIn(BaseModel):
    quotation_id: int
    award_reason: str = Field(min_length=5, max_length=500)


class SupplierProfileIn(BaseModel):
    commercial_registration: str | None = Field(default=None, max_length=80)
    contact_name: str | None = Field(default=None, max_length=160)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)
    payment_terms_days: int = Field(default=30, ge=0, le=730)
    delivery_score: Decimal = Field(default=0, ge=0, le=100)
    quality_score: Decimal = Field(default=0, ge=0, le=100)
    price_score: Decimal = Field(default=0, ge=0, le=100)
    rejection_rate: Decimal = Field(default=0, ge=0, le=100)


class IbanChangeIn(BaseModel):
    iban: str = Field(min_length=15, max_length=34, pattern=r"^[A-Za-z0-9 ]+$")
    reason: str = Field(min_length=10, max_length=500)


def _number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{count + 1:06d}"


def _supplier(db: Session, company_id: int, supplier_id: int) -> Party:
    row = db.scalar(select(Party).where(
        Party.id == supplier_id,
        Party.company_id == company_id,
        Party.party_type.in_(["SUPPLIER", "BOTH"]),
        Party.active.is_(True),
    ))
    if not row:
        raise HTTPException(422, "Active supplier not found in this company")
    return row


def _latest_received_purchase(db: Session, company_id: int, item_id: int, supplier_id: int | None = None, before_date: date | None = None) -> dict | None:
    """Latest actual receipt price, never a draft or unreceived quotation.

    A purchase-order price is a commitment; the goods-receipt line is the
    auditable evidence that the company actually bought and received the item.
    """
    query = (
        select(
            GoodsReceiptLine.unit_cost,
            GoodsReceiptLine.quantity,
            GoodsReceipt.receipt_date,
            GoodsReceipt.number,
            PurchaseOrder.id,
            PurchaseOrder.number,
            Party.id,
            Party.code,
            Party.name_ar,
            Party.name_en,
            Party.vat_number,
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
        .join(Party, Party.id == PurchaseOrder.supplier_id)
        .where(
            GoodsReceipt.company_id == company_id,
            GoodsReceipt.status == "POSTED",
            GoodsReceiptLine.item_id == item_id,
        )
    )
    if supplier_id is not None:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    if before_date is not None:
        query = query.where(GoodsReceipt.receipt_date < before_date)
    result = db.execute(
        query.order_by(GoodsReceipt.receipt_date.desc(), GoodsReceiptLine.id.desc()).limit(1)
    ).first()
    if not result:
        return None
    return {
        "unit_price": result[0],
        "quantity": result[1],
        "purchase_date": result[2],
        "goods_receipt_number": result[3],
        "purchase_order_id": result[4],
        "purchase_order_number": result[5],
        "supplier_id": result[6],
        "supplier_code": result[7],
        "supplier_name_ar": result[8],
        "supplier_name_en": result[9],
        "supplier_vat_number": result[10],
        "source": "POSTED_GOODS_RECEIPT",
    }


def _req_query():
    return select(PurchaseRequisition).options(
        selectinload(PurchaseRequisition.lines).selectinload(PurchaseRequisitionLine.item)
    )


def _rfq_query():
    return select(RequestForQuotation).options(
        selectinload(RequestForQuotation.lines).selectinload(RFQLine.item),
        selectinload(RequestForQuotation.suppliers).selectinload(RFQSupplier.supplier),
        selectinload(RequestForQuotation.quotations).selectinload(SupplierQuotation.lines),
        selectinload(RequestForQuotation.quotations).selectinload(SupplierQuotation.supplier),
    )


def _req_dict(row: PurchaseRequisition) -> dict:
    supplier = row.suggested_supplier
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number,
        "request_date": row.request_date, "needed_by": row.needed_by,
        "warehouse_id": row.warehouse_id, "warehouse_code": row.warehouse.code,
        "suggested_supplier_id": row.suggested_supplier_id,
        "suggested_supplier_code": supplier.code if supplier else None,
        "suggested_supplier_name_ar": supplier.name_ar if supplier else None,
        "suggested_supplier_name_en": supplier.name_en if supplier else None,
        "suggested_supplier_vat_number": supplier.vat_number if supplier else None,
        "department": row.department, "justification": row.justification,
        "status": row.status, "estimated_total": row.estimated_total,
        "created_by": row.created_by, "approved_by": row.approved_by,
        "rejection_reason": row.rejection_reason, "created_at": row.created_at,
        "lines": [{
            "id": line.id, "item_id": line.item_id, "item_code": line.item.code,
            "item_name_ar": line.item.name_ar, "item_name_en": line.item.name_en,
            "quantity": line.quantity, "estimated_unit_price": line.estimated_unit_price,
            "specifications": line.specifications,
        } for line in row.lines],
    }


def _quote_dict(row: SupplierQuotation) -> dict:
    return {
        "id": row.id, "number": row.number, "rfq_id": row.rfq_id,
        "supplier_id": row.supplier_id, "supplier_code": row.supplier.code,
        "supplier_name_ar": row.supplier.name_ar, "supplier_name_en": row.supplier.name_en,
        "supplier_reference": row.supplier_reference, "quote_date": row.quote_date,
        "valid_until": row.valid_until, "lead_time_days": row.lead_time_days,
        "payment_terms": row.payment_terms, "status": row.status,
        "subtotal": row.subtotal, "vat_amount": row.vat_amount, "total": row.total,
        "created_by": row.created_by,
        "lines": [{
            "id": line.id, "rfq_line_id": line.rfq_line_id,
            "unit_price": line.unit_price, "vat_rate": line.vat_rate,
            "line_subtotal": line.line_subtotal, "vat_amount": line.vat_amount,
            "line_total": line.line_total,
        } for line in row.lines],
    }


def _mask_iban(value: str | None) -> str | None:
    compact = "".join(str(value or "").split()).upper()
    return f"{compact[:2]}••••••••{compact[-4:]}" if compact else None


def _profile_dict(row: SupplierProcurementProfile, db: Session) -> dict:
    supplier = row.supplier
    receipt_stats = db.execute(
        select(
            func.count(GoodsReceipt.id),
            func.max(GoodsReceipt.receipt_date),
            func.coalesce(func.sum(GoodsReceipt.total_cost), 0),
        )
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
        .where(PurchaseOrder.company_id == row.company_id, PurchaseOrder.supplier_id == row.supplier_id, GoodsReceipt.status == "POSTED")
    ).one()
    received_price_rows = db.execute(
        select(GoodsReceiptLine.item_id, Item.code, Item.name_ar, Item.name_en, GoodsReceiptLine.unit_cost, GoodsReceipt.receipt_date)
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
        .join(Item, Item.id == GoodsReceiptLine.item_id)
        .where(PurchaseOrder.company_id == row.company_id, PurchaseOrder.supplier_id == row.supplier_id, GoodsReceipt.status == "POSTED")
        .order_by(GoodsReceipt.receipt_date.desc(), GoodsReceiptLine.id.desc())
    ).all()
    grouped_prices: dict[int, dict] = {}
    for item_id, code, name_ar, name_en, unit_cost, receipt_date in received_price_rows:
        bucket = grouped_prices.setdefault(item_id, {"item_id": item_id, "item_code": code, "item_name_ar": name_ar, "item_name_en": name_en, "prices": [], "last_receipt_date": receipt_date})
        if len(bucket["prices"]) < 5: bucket["prices"].append(Decimal(unit_cost))
    item_price_indicators = []
    for bucket in grouped_prices.values():
        values = bucket.pop("prices")
        item_price_indicators.append(bucket | {"last_price": values[0],
            "average_last_3_prices": money(sum(values[:3], Decimal("0")) / len(values[:3])),
            "average_last_5_prices": money(sum(values, Decimal("0")) / len(values))})
    invoice_count = db.scalar(select(func.count(PurchaseInvoice.id)).where(
        PurchaseInvoice.company_id == row.company_id, PurchaseInvoice.supplier_id == row.supplier_id,
    )) or 0
    return {
        "id": row.id, "company_id": row.company_id, "supplier_id": row.supplier_id,
        "supplier_code": supplier.code, "supplier_name_ar": supplier.name_ar,
        "supplier_name_en": supplier.name_en, "vat_number": supplier.vat_number,
        "credit_limit": supplier.credit_limit, "active": bool(row.active and supplier.active),
        "commercial_registration": row.commercial_registration,
        "contact_name": row.contact_name, "contact_email": row.contact_email, "contact_phone": row.contact_phone,
        "payment_terms_days": row.payment_terms_days,
        "delivery_score": row.delivery_score, "quality_score": row.quality_score,
        "price_score": row.price_score, "rejection_rate": row.rejection_rate,
        "overall_score": money((Decimal(row.delivery_score) + Decimal(row.quality_score) + Decimal(row.price_score)) / Decimal("3")),
        "iban_status": row.iban_status, "iban_change_risk": row.iban_change_risk,
        "approved_iban_masked": _mask_iban(row.approved_iban), "pending_iban_masked": _mask_iban(row.pending_iban),
        "iban_change_requested_by": row.iban_change_requested_by,
        "iban_change_requested_at": row.iban_change_requested_at,
        "iban_approved_by": row.iban_approved_by, "iban_approved_at": row.iban_approved_at,
        "receipt_count": receipt_stats[0], "last_receipt_date": receipt_stats[1],
        "lifetime_received_value": money(receipt_stats[2]), "invoice_count": invoice_count,
        "item_price_indicators": item_price_indicators,
    }


def _get_or_create_profile(db: Session, company_id: int, supplier: Party, user_id: int) -> SupplierProcurementProfile:
    row = db.scalar(select(SupplierProcurementProfile).where(
        SupplierProcurementProfile.company_id == company_id,
        SupplierProcurementProfile.supplier_id == supplier.id,
    ))
    if row is None:
        row = SupplierProcurementProfile(company_id=company_id, supplier_id=supplier.id, created_by=user_id, updated_by=user_id)
        db.add(row); db.flush()
    return row


def _age_days(moment: datetime | None) -> int:
    if not moment:
        return 0
    now = utc_now()
    if getattr(moment, "tzinfo", None) is None and getattr(now, "tzinfo", None) is not None:
        now = now.replace(tzinfo=None)
    return max(0, (now - moment).days)


def _rfq_dict(row: RequestForQuotation) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number,
        "requisition_id": row.requisition_id, "requisition_number": row.requisition.number,
        "issue_date": row.issue_date, "closing_date": row.closing_date,
        "status": row.status, "created_by": row.created_by,
        "awarded_quotation_id": row.awarded_quotation_id,
        "award_reason": row.award_reason, "awarded_by": row.awarded_by,
        "suppliers": [{
            "id": link.supplier_id, "code": link.supplier.code,
            "name_ar": link.supplier.name_ar, "name_en": link.supplier.name_en,
        } for link in row.suppliers],
        "lines": [{
            "id": line.id, "item_id": line.item_id, "item_code": line.item.code,
            "item_name_ar": line.item.name_ar, "item_name_en": line.item.name_en,
            "quantity": line.quantity, "specifications": line.specifications,
        } for line in row.lines],
        "quotations": [_quote_dict(quote) for quote in row.quotations],
        "created_at": row.created_at,
    }


@router.post("/requisitions", status_code=201)
def create_requisition(data: RequisitionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "procurement.manage")
    if data.needed_by < data.request_date:
        raise HTTPException(422, "Needed-by date cannot be before request date")
    warehouse = get_warehouse(db, data.company_id, data.warehouse_id)
    suggested_supplier = _supplier(db, data.company_id, data.suggested_supplier_id) if data.suggested_supplier_id else None
    if len({line.item_id for line in data.lines}) != len(data.lines):
        raise HTTPException(422, "Duplicate item in purchase requisition")
    row = PurchaseRequisition(
        company_id=data.company_id,
        number=_number(db, PurchaseRequisition, data.company_id, "PR", data.request_date.year),
        request_date=data.request_date, needed_by=data.needed_by,
        warehouse_id=warehouse.id, suggested_supplier_id=suggested_supplier.id if suggested_supplier else None,
        department=data.department.strip(),
        justification=data.justification.strip(), status="DRAFT", created_by=user.id,
    )
    total = Decimal("0")
    for source in data.lines:
        item = get_item(db, data.company_id, source.item_id)
        qty = quantity(source.quantity)
        price = Decimal(source.estimated_unit_price)
        total += qty * price
        row.lines.append(PurchaseRequisitionLine(
            item_id=item.id, quantity=qty, estimated_unit_price=price,
            specifications=source.specifications,
        ))
    row.estimated_total = money(total)
    db.add(row); db.flush()
    write_audit(db, action="PURCHASE_REQUISITION_CREATED", entity_type="PURCHASE_REQUISITION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": row.number, "estimated_total": str(row.estimated_total)})
    db.commit()
    return _req_dict(db.scalar(_req_query().where(PurchaseRequisition.id == row.id)))


@router.get("/items/{item_id}/last-purchase")
def last_purchase_price(
    item_id: int,
    company_id: int,
    supplier_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return supplier-specific and company-wide actual last receipt prices."""
    ensure_permission(db, user, company_id, "inventory.read")
    item = get_item(db, company_id, item_id)
    supplier = _supplier(db, company_id, supplier_id) if supplier_id else None
    supplier_last = _latest_received_purchase(db, company_id, item.id, supplier.id) if supplier else None
    company_last = _latest_received_purchase(db, company_id, item.id)
    return {
        "item_id": item.id,
        "item_code": item.code,
        "selected_supplier": {
            "id": supplier.id,
            "code": supplier.code,
            "name_ar": supplier.name_ar,
            "name_en": supplier.name_en,
            "vat_number": supplier.vat_number,
        } if supplier else None,
        "supplier_last_purchase": supplier_last,
        "company_last_purchase": company_last,
    }


@router.get("/requisitions")
def list_requisitions(company_id: int, status: str | None = None, q: str | None = Query(default=None, max_length=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    query = _req_query().where(PurchaseRequisition.company_id == company_id)
    if status:
        query = query.where(PurchaseRequisition.status == status.upper())
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(PurchaseRequisition.number).like(term), func.lower(PurchaseRequisition.department).like(term), func.lower(PurchaseRequisition.justification).like(term)))
    rows = db.scalars(query.order_by(PurchaseRequisition.created_at.desc(), PurchaseRequisition.id.desc())).all()
    return [_req_dict(row) for row in rows]


@router.get("/workflow-center")
def procurement_workflow_center(
    company_id: int,
    q: str | None = Query(default=None, max_length=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Auditor-friendly PR-to-payment control tower with document drill-through."""
    ensure_permission(db, user, company_id, "inventory.read")
    query = _req_query().where(PurchaseRequisition.company_id == company_id)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(PurchaseRequisition.number).like(term), func.lower(PurchaseRequisition.department).like(term)))
    requisitions = db.scalars(query.order_by(PurchaseRequisition.created_at.desc())).unique().all()
    rows = []
    for req in requisitions:
        rfq = db.scalar(_rfq_query().where(RequestForQuotation.requisition_id == req.id))
        po = db.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.source_requisition_id == req.id))
        receipts = db.scalars(select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == po.id).order_by(GoodsReceipt.receipt_date) if po else select(GoodsReceipt).where(False)).all()
        receipt_ids = [x.id for x in receipts]
        invoices = []
        if receipt_ids:
            invoices = db.scalars(
                select(PurchaseInvoice).distinct()
                .outerjoin(GoodsReceipt, GoodsReceipt.purchase_invoice_id == PurchaseInvoice.id)
                .outerjoin(PurchaseInvoiceLine, PurchaseInvoiceLine.invoice_id == PurchaseInvoice.id)
                .outerjoin(GoodsReceiptLine, GoodsReceiptLine.id == PurchaseInvoiceLine.goods_receipt_line_id)
                .where(or_(GoodsReceipt.id.in_(receipt_ids), GoodsReceiptLine.goods_receipt_id.in_(receipt_ids)))
                .order_by(PurchaseInvoice.invoice_date)
            ).all()
        open_items = db.scalars(select(FinancialOpenItem).where(
            FinancialOpenItem.company_id == company_id,
            FinancialOpenItem.ledger_type == "AP",
            FinancialOpenItem.source_type == "PURCHASE_INVOICE",
            FinancialOpenItem.source_id.in_([x.id for x in invoices]) if invoices else False,
        )).all()
        allocations = db.scalars(select(FinancialSettlementAllocation).where(
            FinancialSettlementAllocation.open_item_id.in_([x.id for x in open_items]) if open_items else False,
            FinancialSettlementAllocation.reversed_at.is_(None),
        )).all()
        payments = db.scalars(select(Payment).where(Payment.id.in_({x.payment_id for x in allocations if x.payment_id}))).all() if allocations else []
        received_qty = sum((Decimal(line.quantity) for rec in receipts for line in rec.lines), Decimal("0"))
        ordered_qty = sum((Decimal(line.quantity) for line in po.lines), Decimal("0")) if po else Decimal("0")
        allocated = sum((Decimal(x.amount) for x in allocations), Decimal("0"))
        invoiced = sum((Decimal(x.total) for x in invoices), Decimal("0"))
        outstanding = max(Decimal("0"), invoiced - allocated)
        stage, owner, since = "REQUISITION", "REQUESTER", req.created_at
        if req.status == "SUBMITTED": stage, owner, since = "REQUISITION_APPROVAL", "PROCUREMENT_APPROVER", req.submitted_at
        elif req.status == "APPROVED" and not rfq: stage, owner, since = "SOURCING", "BUYER", req.approved_at
        elif rfq and rfq.status in {"DRAFT", "ISSUED"}: stage, owner, since = "RFQ", "BUYER" if rfq.status == "DRAFT" else "SUPPLIERS", rfq.created_at if rfq.status == "DRAFT" else rfq.issued_at
        elif rfq and rfq.status == "AWARDED" and po and po.status == "DRAFT": stage, owner, since = "PO_APPROVAL", "PROCUREMENT_APPROVER", po.created_at
        elif po and received_qty < ordered_qty: stage, owner, since = "RECEIPT", "WAREHOUSE", max((x.created_at for x in receipts), default=po.created_at)
        elif receipts and not invoices: stage, owner, since = "INVOICE", "ACCOUNTS_PAYABLE", max(x.created_at for x in receipts)
        elif invoices and outstanding > 0: stage, owner, since = "PAYMENT", "TREASURY", max(x.created_at for x in invoices)
        elif invoices and outstanding == 0: stage, owner, since = "COMPLETE", "CLOSED", max((x.created_at for x in payments), default=max(x.created_at for x in invoices))
        supplier = po.supplier if po else (rfq.quotations[0].supplier if rfq and rfq.quotations else req.suggested_supplier)
        price_indicators = []
        for line in po.lines if po else []:
            historical = _latest_received_purchase(db, company_id, line.item_id, po.supplier_id, before_date=po.order_date)
            variance = None
            if historical and Decimal(historical["unit_price"]):
                variance = money((Decimal(line.unit_price) - Decimal(historical["unit_price"])) / Decimal(historical["unit_price"]) * 100)
            price_indicators.append({"item_id": line.item_id, "current_unit_price": line.unit_price,
                                     "last_received_unit_price": historical["unit_price"] if historical else None,
                                     "last_receipt_number": historical["goods_receipt_number"] if historical else None,
                                     "variance_percent": variance})
        positive_variances = [Decimal(x["variance_percent"]) for x in price_indicators if x["variance_percent"] is not None]
        variance = max(positive_variances) if positive_variances else None
        rows.append({
            "requisition": {"id": req.id, "number": req.number, "status": req.status, "path": f"/purchases?pr={req.id}"},
            "rfq": {"id": rfq.id, "number": rfq.number, "status": rfq.status, "path": f"/purchases?rfq={rfq.id}"} if rfq else None,
            "purchase_order": {"id": po.id, "number": po.number, "status": po.status, "path": f"/inventory?po={po.id}"} if po else None,
            "receipts": [{"id": x.id, "number": x.number, "status": x.status, "path": f"/inventory?grn={x.id}"} for x in receipts],
            "invoices": [{"id": x.id, "number": x.number, "status": x.status, "supplier_invoice_number": x.supplier_invoice_number, "path": f"/purchases?invoice={x.id}"} for x in invoices],
            "payments": [{"id": x.id, "number": x.number, "path": f"/purchases?payment={x.id}"} for x in payments],
            "department": req.department, "needed_by": req.needed_by,
            "supplier_id": supplier.id if supplier else None,
            "supplier_code": supplier.code if supplier else None,
            "supplier_name_ar": supplier.name_ar if supplier else None,
            "supplier_name_en": supplier.name_en if supplier else None,
            "supplier_vat_number": supplier.vat_number if supplier else None,
            "stage": stage, "current_owner": owner, "stalled_days": _age_days(since), "stage_since": since,
            "ordered_quantity": ordered_qty, "received_quantity": received_qty,
            "po_total": po.total if po else None, "invoiced_total": money(invoiced),
            "paid_total": money(allocated), "outstanding_total": money(outstanding),
            "price_indicators": price_indicators,
            "price_variance_percent": variance,
            "control_flags": [
                *(["OVERDUE_NEEDED_DATE"] if req.needed_by < date.today() and stage != "COMPLETE" else []),
                *(["PRICE_INCREASE"] if variance is not None and Decimal(variance) > 5 else []),
                *(["RECEIPT_SHORTFALL"] if po and received_qty < ordered_qty else []),
                *(["UNPAID_INVOICE"] if invoices and outstanding > 0 else []),
            ],
        })
    return {"company_id": company_id, "generated_at": utc_now(), "rows": rows,
            "summary": {"total": len(rows), "complete": sum(x["stage"] == "COMPLETE" for x in rows),
                        "stalled": sum(x["stalled_days"] >= 3 and x["stage"] != "COMPLETE" for x in rows),
                        "at_risk": sum(bool(x["control_flags"]) for x in rows)}}


@router.get("/suppliers/{supplier_id}/profile")
def get_supplier_profile(supplier_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    supplier = _supplier(db, company_id, supplier_id)
    row = db.scalar(select(SupplierProcurementProfile).where(SupplierProcurementProfile.company_id == company_id, SupplierProcurementProfile.supplier_id == supplier.id))
    if row is None:
        row = SupplierProcurementProfile(company_id=company_id, supplier_id=supplier.id, created_by=user.id, updated_by=user.id)
        row.supplier = supplier
    return _profile_dict(row, db)


@router.put("/suppliers/{supplier_id}/profile")
def update_supplier_profile(supplier_id: int, company_id: int, data: SupplierProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "procurement.manage")
    supplier = _supplier(db, company_id, supplier_id)
    row = _get_or_create_profile(db, company_id, supplier, user.id)
    before = {key: str(getattr(row, key, None)) for key in data.model_fields}
    for key, value in data.model_dump().items(): setattr(row, key, value.strip() if isinstance(value, str) else value)
    row.updated_by = user.id
    write_audit(db, action="SUPPLIER_PROFILE_UPDATED", entity_type="SUPPLIER_PROCUREMENT_PROFILE", entity_id=row.id, user_id=user.id, company_id=company_id, before=before, after={k: str(v) for k, v in data.model_dump().items()})
    db.commit(); return _profile_dict(row, db)


@router.post("/suppliers/{supplier_id}/iban-change")
def request_supplier_iban_change(supplier_id: int, company_id: int, data: IbanChangeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "procurement.manage")
    supplier = _supplier(db, company_id, supplier_id); row = _get_or_create_profile(db, company_id, supplier, user.id)
    iban = "".join(data.iban.split()).upper()
    if row.approved_iban and iban == row.approved_iban: raise HTTPException(409, "IBAN is already approved")
    row.pending_iban = iban; row.iban_status = "PENDING_APPROVAL"
    row.iban_change_risk = "HIGH" if row.approved_iban else "MEDIUM"
    row.iban_change_requested_by = user.id; row.iban_change_requested_at = utc_now(); row.updated_by = user.id
    write_audit(db, action="SUPPLIER_IBAN_CHANGE_REQUESTED", entity_type="SUPPLIER_PROCUREMENT_PROFILE", entity_id=row.id, user_id=user.id, company_id=company_id, after={"supplier": supplier.code, "iban_masked": _mask_iban(iban), "risk": row.iban_change_risk, "reason": data.reason})
    db.commit(); return _profile_dict(row, db)


@router.post("/suppliers/{supplier_id}/iban-change/approve")
def approve_supplier_iban_change(supplier_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "procurement.approve")
    supplier = _supplier(db, company_id, supplier_id)
    row = db.scalar(select(SupplierProcurementProfile).where(SupplierProcurementProfile.company_id == company_id, SupplierProcurementProfile.supplier_id == supplier.id))
    if not row or row.iban_status != "PENDING_APPROVAL" or not row.pending_iban: raise HTTPException(409, "No pending IBAN change")
    if row.iban_change_requested_by == user.id: raise HTTPException(409, "Maker-checker: IBAN requester cannot approve")
    row.approved_iban = row.pending_iban; row.pending_iban = None; row.iban_status = "APPROVED"; row.iban_change_risk = "NONE"
    row.iban_approved_by = user.id; row.iban_approved_at = utc_now(); row.updated_by = user.id
    write_audit(db, action="SUPPLIER_IBAN_CHANGE_APPROVED", entity_type="SUPPLIER_PROCUREMENT_PROFILE", entity_id=row.id, user_id=user.id, company_id=company_id, after={"supplier": supplier.code, "iban_masked": _mask_iban(row.approved_iban)})
    db.commit(); return _profile_dict(row, db)


@router.get("/suppliers/{supplier_id}/invoice-risk")
def supplier_invoice_duplicate_risk(supplier_id: int, company_id: int, invoice_number: str, amount: Decimal | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read"); _supplier(db, company_id, supplier_id)
    normalized = invoice_number.strip().lower()
    matches = db.scalars(select(PurchaseInvoice).where(
        PurchaseInvoice.company_id == company_id, PurchaseInvoice.supplier_id == supplier_id,
        func.lower(func.trim(PurchaseInvoice.supplier_invoice_number)) == normalized,
    ).order_by(PurchaseInvoice.invoice_date.desc())).all()
    exact_amount = [x for x in matches if amount is not None and money(x.total) == money(amount)]
    return {"duplicate": bool(matches), "blocking": bool(exact_amount or matches), "match_count": len(matches),
            "matches": [{"id": x.id, "number": x.number, "supplier_invoice_number": x.supplier_invoice_number, "invoice_date": x.invoice_date, "total": x.total, "status": x.status} for x in matches]}


@router.post("/requisitions/{row_id}/submit")
def submit_requisition(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(_req_query().where(PurchaseRequisition.id == row_id))
    if not row: raise HTTPException(404, "Purchase requisition not found")
    ensure_permission(db, user, row.company_id, "procurement.manage")
    if row.created_by != user.id: raise HTTPException(403, "Only the requisition creator can submit it")
    if row.status != "DRAFT": raise HTTPException(409, "Only a draft requisition can be submitted")
    row.status = "SUBMITTED"; row.submitted_at = utc_now()
    write_audit(db, action="PURCHASE_REQUISITION_SUBMITTED", entity_type="PURCHASE_REQUISITION", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return _req_dict(row)


@router.post("/requisitions/{row_id}/approve")
def approve_requisition(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(_req_query().where(PurchaseRequisition.id == row_id))
    if not row: raise HTTPException(404, "Purchase requisition not found")
    ensure_permission(db, user, row.company_id, "procurement.approve")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker: requisition creator cannot approve")
    if row.status != "SUBMITTED": raise HTTPException(409, "Only a submitted requisition can be approved")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="PURCHASE_REQUISITION_APPROVED", entity_type="PURCHASE_REQUISITION", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return _req_dict(row)


@router.post("/requisitions/{row_id}/reject")
def reject_requisition(row_id: int, data: RejectionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(_req_query().where(PurchaseRequisition.id == row_id))
    if not row: raise HTTPException(404, "Purchase requisition not found")
    ensure_permission(db, user, row.company_id, "procurement.approve")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker: requisition creator cannot reject")
    if row.status != "SUBMITTED": raise HTTPException(409, "Only a submitted requisition can be rejected")
    row.status = "REJECTED"; row.rejected_by = user.id; row.rejected_at = utc_now(); row.rejection_reason = data.reason
    write_audit(db, action="PURCHASE_REQUISITION_REJECTED", entity_type="PURCHASE_REQUISITION", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"reason": data.reason})
    db.commit(); return _req_dict(row)


@router.post("/rfqs", status_code=201)
def create_rfq(data: RFQIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "procurement.manage")
    if data.closing_date < data.issue_date:
        raise HTTPException(422, "RFQ closing date cannot be before issue date")
    requisition = db.scalar(_req_query().where(PurchaseRequisition.id == data.requisition_id, PurchaseRequisition.company_id == data.company_id))
    if not requisition: raise HTTPException(404, "Purchase requisition not found")
    if requisition.status != "APPROVED": raise HTTPException(409, "RFQ requires an approved purchase requisition")
    if db.scalar(select(RequestForQuotation.id).where(RequestForQuotation.requisition_id == requisition.id)):
        raise HTTPException(409, "An RFQ already exists for this requisition")
    supplier_ids = list(dict.fromkeys(data.supplier_ids))
    if len(supplier_ids) < 2: raise HTTPException(422, "At least two distinct suppliers are required for comparison")
    suppliers = [_supplier(db, data.company_id, supplier_id) for supplier_id in supplier_ids]
    row = RequestForQuotation(
        company_id=data.company_id,
        number=_number(db, RequestForQuotation, data.company_id, "RFQ", data.issue_date.year),
        requisition_id=requisition.id, issue_date=data.issue_date,
        closing_date=data.closing_date, status="DRAFT", created_by=user.id,
    )
    row.suppliers = [RFQSupplier(supplier_id=supplier.id) for supplier in suppliers]
    row.lines = [RFQLine(
        requisition_line_id=line.id, item_id=line.item_id,
        quantity=line.quantity, specifications=line.specifications,
    ) for line in requisition.lines]
    db.add(row); db.flush()
    write_audit(db, action="RFQ_CREATED", entity_type="REQUEST_FOR_QUOTATION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": row.number, "suppliers": supplier_ids})
    db.commit(); return _rfq_dict(db.scalar(_rfq_query().where(RequestForQuotation.id == row.id)))


@router.get("/rfqs")
def list_rfqs(company_id: int, status: str | None = None, q: str | None = Query(default=None, max_length=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    query = _rfq_query().where(RequestForQuotation.company_id == company_id)
    if status: query = query.where(RequestForQuotation.status == status.upper())
    if q and q.strip(): query = query.where(func.lower(RequestForQuotation.number).like(f"%{q.strip().lower()}%"))
    return [_rfq_dict(row) for row in db.scalars(query.order_by(RequestForQuotation.created_at.desc())).unique().all()]


@router.post("/rfqs/{row_id}/issue")
def issue_rfq(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(_rfq_query().where(RequestForQuotation.id == row_id))
    if not row: raise HTTPException(404, "RFQ not found")
    ensure_permission(db, user, row.company_id, "procurement.manage")
    if row.created_by != user.id: raise HTTPException(403, "Only the RFQ creator can issue it")
    if row.status != "DRAFT": raise HTTPException(409, "Only a draft RFQ can be issued")
    if len(row.suppliers) < 2: raise HTTPException(422, "At least two suppliers are required")
    row.status = "ISSUED"; row.issued_at = utc_now()
    write_audit(db, action="RFQ_ISSUED", entity_type="REQUEST_FOR_QUOTATION", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return _rfq_dict(row)


@router.post("/quotations", status_code=201)
def record_quotation(data: QuotationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "procurement.manage")
    rfq = db.scalar(_rfq_query().where(RequestForQuotation.id == data.rfq_id, RequestForQuotation.company_id == data.company_id))
    if not rfq: raise HTTPException(404, "RFQ not found")
    if rfq.status != "ISSUED": raise HTTPException(409, "Supplier quotations require an issued RFQ")
    if not (rfq.issue_date <= data.quote_date <= rfq.closing_date):
        raise HTTPException(422, "Quotation date must be within the RFQ window")
    if data.valid_until < data.quote_date: raise HTTPException(422, "Quotation validity cannot end before quote date")
    supplier = _supplier(db, data.company_id, data.supplier_id)
    if supplier.id not in {link.supplier_id for link in rfq.suppliers}:
        raise HTTPException(422, "Supplier was not invited to this RFQ")
    if db.scalar(select(SupplierQuotation.id).where(SupplierQuotation.rfq_id == rfq.id, SupplierQuotation.supplier_id == supplier.id)):
        raise HTTPException(409, "A quotation from this supplier is already recorded")
    source_lines = {line.id: line for line in rfq.lines}
    if set(source_lines) != {line.rfq_line_id for line in data.lines} or len(data.lines) != len(source_lines):
        raise HTTPException(422, "Quotation must price every RFQ line exactly once")
    row = SupplierQuotation(
        company_id=data.company_id,
        number=_number(db, SupplierQuotation, data.company_id, "SQ", data.quote_date.year),
        rfq_id=rfq.id, supplier_id=supplier.id,
        supplier_reference=data.supplier_reference.strip(), quote_date=data.quote_date,
        valid_until=data.valid_until, lead_time_days=data.lead_time_days,
        payment_terms=data.payment_terms, status="SUBMITTED", created_by=user.id,
    )
    subtotal = vat_total = Decimal("0")
    for source in data.lines:
        rfq_line = source_lines[source.rfq_line_id]
        line_subtotal = money(Decimal(rfq_line.quantity) * Decimal(source.unit_price))
        line_vat = money(line_subtotal * Decimal(source.vat_rate) / Decimal("100"))
        subtotal += line_subtotal; vat_total += line_vat
        row.lines.append(SupplierQuotationLine(
            rfq_line_id=rfq_line.id, unit_price=source.unit_price,
            vat_rate=source.vat_rate, line_subtotal=line_subtotal,
            vat_amount=line_vat, line_total=money(line_subtotal + line_vat),
        ))
    row.subtotal = money(subtotal); row.vat_amount = money(vat_total); row.total = money(subtotal + vat_total)
    db.add(row); db.flush()
    write_audit(db, action="SUPPLIER_QUOTATION_RECORDED", entity_type="SUPPLIER_QUOTATION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"rfq": rfq.number, "supplier": supplier.code, "total": str(row.total)})
    db.commit(); return _quote_dict(db.scalar(select(SupplierQuotation).options(selectinload(SupplierQuotation.lines), selectinload(SupplierQuotation.supplier)).where(SupplierQuotation.id == row.id)))


@router.get("/rfqs/{row_id}/comparison")
def quotation_comparison(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rfq = db.scalar(_rfq_query().where(RequestForQuotation.id == row_id))
    if not rfq: raise HTTPException(404, "RFQ not found")
    ensure_permission(db, user, rfq.company_id, "inventory.read")
    quotes = sorted(rfq.quotations, key=lambda quote: (Decimal(quote.total), quote.lead_time_days, quote.id))
    return {
        "rfq_id": rfq.id, "rfq_number": rfq.number, "status": rfq.status,
        "minimum_quote_total": quotes[0].total if quotes else None,
        "comparison_complete": len(quotes) >= 2,
        "quotations": [_quote_dict(quote) | {"rank": rank} for rank, quote in enumerate(quotes, 1)],
    }


@router.post("/rfqs/{row_id}/award")
def award_rfq(row_id: int, data: AwardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rfq = db.scalar(_rfq_query().where(RequestForQuotation.id == row_id))
    if not rfq: raise HTTPException(404, "RFQ not found")
    ensure_permission(db, user, rfq.company_id, "procurement.approve")
    if rfq.status != "ISSUED": raise HTTPException(409, "Only an issued RFQ can be awarded")
    selected = next((quote for quote in rfq.quotations if quote.id == data.quotation_id), None)
    if not selected: raise HTTPException(422, "Quotation does not belong to this RFQ")
    if rfq.created_by == user.id or selected.created_by == user.id:
        raise HTTPException(409, "Maker-checker: RFQ/quotation preparer cannot award")
    if len(rfq.quotations) < 2: raise HTTPException(409, "At least two quotations are required before award")
    lowest = min(Decimal(quote.total) for quote in rfq.quotations)
    if Decimal(selected.total) > lowest and len(data.award_reason.strip()) < 15:
        raise HTTPException(422, "A detailed reason is required when the lowest quotation is not selected")

    requisition = rfq.requisition
    quote_lines = {line.rfq_line_id: line for line in selected.lines}
    po = PurchaseOrder(
        company_id=rfq.company_id,
        number=_number(db, PurchaseOrder, rfq.company_id, "PO", date.today().year),
        order_date=date.today(), expected_receipt_date=date.today() + timedelta(days=selected.lead_time_days),
        supplier_id=selected.supplier_id, warehouse_id=requisition.warehouse_id,
        status="DRAFT", subtotal=selected.subtotal, vat_amount=selected.vat_amount,
        total=selected.total, created_by=user.id,
        source_requisition_id=requisition.id, source_quotation_id=selected.id,
    )
    for rfq_line in rfq.lines:
        quote_line = quote_lines[rfq_line.id]
        po.lines.append(PurchaseOrderLine(
            item_id=rfq_line.item_id, quantity=rfq_line.quantity,
            unit_price=quote_line.unit_price, vat_rate=quote_line.vat_rate,
            received_quantity=0, invoiced_quantity=0,
        ))
    db.add(po); db.flush()
    rfq.status = "AWARDED"; rfq.awarded_quotation_id = selected.id
    rfq.award_reason = data.award_reason.strip(); rfq.awarded_by = user.id; rfq.awarded_at = utc_now()
    for quote in rfq.quotations: quote.status = "ACCEPTED" if quote.id == selected.id else "REJECTED"
    write_audit(db, action="RFQ_AWARDED", entity_type="REQUEST_FOR_QUOTATION", entity_id=rfq.id, user_id=user.id, company_id=rfq.company_id, after={"quotation": selected.number, "supplier": selected.supplier.code, "po": po.number, "reason": rfq.award_reason})
    db.commit()
    return {"rfq_id": rfq.id, "status": rfq.status, "quotation_id": selected.id, "purchase_order": {"id": po.id, "number": po.number, "status": po.status, "total": po.total}}
