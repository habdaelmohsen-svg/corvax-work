from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Item, Party, PurchaseOrder, PurchaseOrderLine, PurchaseRequisition,
    PurchaseRequisitionLine, RequestForQuotation, RFQLine, RFQSupplier,
    SupplierQuotation, SupplierQuotationLine, User, Warehouse,
)
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
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number,
        "request_date": row.request_date, "needed_by": row.needed_by,
        "warehouse_id": row.warehouse_id, "warehouse_code": row.warehouse.code,
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
    if len({line.item_id for line in data.lines}) != len(data.lines):
        raise HTTPException(422, "Duplicate item in purchase requisition")
    row = PurchaseRequisition(
        company_id=data.company_id,
        number=_number(db, PurchaseRequisition, data.company_id, "PR", data.request_date.year),
        request_date=data.request_date, needed_by=data.needed_by,
        warehouse_id=warehouse.id, department=data.department.strip(),
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
