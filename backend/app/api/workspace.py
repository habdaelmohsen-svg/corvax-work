from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import company_permissions, ensure_permission, get_current_user
from app.models import (
    CRMLead, Item, JournalEntry, Party, Payment, PurchaseInvoice, PurchaseOrder,
    PurchaseRequisition, RequestForQuotation, SupplierQuotation,
    Receipt, SalesInvoice, ServiceTicket, GymFacilityBooking,
    GymMembershipModification, PayrollRun, PlatformSettlementBatch,
    PosControlRequest, PosOrder, User,
)

router = APIRouter(prefix="/workspace", tags=["Operational workspace RC16"])

PENDING_STATUSES = {"SUBMITTED", "PENDING", "PENDING_APPROVAL", "AWAITING_APPROVAL", "REVIEWED", "CLOSED_PENDING_APPROVAL"}


def _guard(db: Session, user: User, company_id: int) -> None:
    ensure_permission(db, user, company_id, "company.read")


def _item(module: str, item_type: str, row: Any, number: str, status: str, title: str, amount: Any = None, view: str | None = None) -> dict[str, Any]:
    payload = {
        "module": module,
        "item_type": item_type,
        "id": row.id,
        "number": number,
        "status": status,
        "title": title,
        "amount": float(amount or 0),
        "created_at": getattr(row, "created_at", None),
    }
    if view:
        payload["view"] = view
    return payload


@router.get("/work-queue")
def work_queue(
    company_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _guard(db, user, company_id)
    items: list[dict[str, Any]] = []
    queue_permissions = company_permissions(db, user, company_id)

    mods = db.scalars(select(GymMembershipModification).where(
        GymMembershipModification.company_id == company_id,
        GymMembershipModification.status.in_(PENDING_STATUSES),
    ).order_by(GymMembershipModification.created_at.desc()).limit(limit)).all()
    items += [_item("GYM", "MEMBERSHIP_MODIFICATION", r, r.number, r.status, r.modification_type, r.adjustment_net or r.refund_total) for r in mods]

    bookings = db.scalars(select(GymFacilityBooking).where(
        GymFacilityBooking.company_id == company_id,
        GymFacilityBooking.status.in_(PENDING_STATUSES),
    ).order_by(GymFacilityBooking.created_at.desc()).limit(limit)).all()
    items += [_item("GYM", "FACILITY_BOOKING", r, r.number, r.status, "FACILITY_BOOKING", r.net_amount) for r in bookings]

    controls = db.scalars(select(PosControlRequest).where(
        PosControlRequest.company_id == company_id,
        PosControlRequest.status.in_(PENDING_STATUSES),
    ).order_by(PosControlRequest.created_at.desc()).limit(limit)).all()
    items += [_item("POS", "CONTROL_REQUEST", r, r.number, r.status, r.request_type, r.refund_total) for r in controls]

    settlements = db.scalars(select(PlatformSettlementBatch).where(
        PlatformSettlementBatch.company_id == company_id,
        PlatformSettlementBatch.status.in_(PENDING_STATUSES),
    ).order_by(PlatformSettlementBatch.created_at.desc()).limit(limit)).all()
    items += [_item("POS", "PLATFORM_SETTLEMENT", r, r.number, r.status, "PLATFORM_SETTLEMENT", r.received_net) for r in settlements]

    payrolls = db.scalars(select(PayrollRun).where(
        PayrollRun.company_id == company_id,
        PayrollRun.status.in_(PENDING_STATUSES | {"DRAFT", "REVIEWED"}),
    ).order_by(PayrollRun.created_at.desc()).limit(limit)).all()
    items += [_item("HR", "PAYROLL_RUN", r, f"PAY-{r.period_year}-{r.period_month:02d}", r.status, "PAYROLL_RUN", r.total_net) for r in payrolls]

    if "*" in queue_permissions or "procurement.approve" in queue_permissions:
        requisitions = db.scalars(select(PurchaseRequisition).where(
            PurchaseRequisition.company_id == company_id,
            PurchaseRequisition.status == "SUBMITTED",
        ).order_by(PurchaseRequisition.created_at.desc()).limit(limit)).all()
        items += [_item("PROCUREMENT", "PURCHASE_REQUISITION", r, r.number, r.status, r.department, r.estimated_total, "purchases") for r in requisitions]

    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return {
        "items": items[:limit],
        "total": len(items),
        "by_module": {m: sum(1 for i in items if i["module"] == m) for m in {"GYM", "POS", "HR", "PROCUREMENT"}},
        "control": {"maker_checker": True, "self_approval_blocked": True, "source": "LIVE_DATABASE"},
    }


@router.get("/search")
def global_search(
    company_id: int,
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _guard(db, user, company_id)
    term = f"%{q.strip().lower()}%"
    results: list[dict[str, Any]] = []
    permissions = company_permissions(db, user, company_id)
    allowed = lambda *codes: "*" in permissions or any(code in permissions for code in codes)
    per_type = min(limit, 25)

    mods = db.scalars(select(GymMembershipModification).where(
        GymMembershipModification.company_id == company_id,
        or_(func.lower(GymMembershipModification.number).like(term), func.lower(GymMembershipModification.reason).like(term), func.lower(GymMembershipModification.modification_type).like(term)),
    ).limit(per_type)).all()
    results += [_item("GYM", "MEMBERSHIP_MODIFICATION", r, r.number, r.status, r.reason, r.adjustment_net or r.refund_total, "gym") for r in mods]

    orders = db.scalars(select(PosOrder).where(
        PosOrder.company_id == company_id,
        or_(func.lower(PosOrder.number).like(term), func.lower(func.coalesce(PosOrder.customer_name, "")).like(term), func.lower(PosOrder.business_unit).like(term)),
    ).limit(per_type)).all()
    results += [_item("POS", "POS_ORDER", r, r.number, r.status, r.customer_name or r.business_unit, r.total, "restaurant") for r in orders]

    payrolls = db.scalars(select(PayrollRun).where(
        PayrollRun.company_id == company_id,
        or_(cast(PayrollRun.period_year, String).like(f"%{q}%"), PayrollRun.status.ilike(term)),
    ).limit(per_type)).all()
    results += [_item("HR", "PAYROLL_RUN", r, f"PAY-{r.period_year}-{r.period_month:02d}", r.status, "PAYROLL_RUN", r.total_net, "hr") for r in payrolls]

    if allowed("masterdata.read", "inventory.read"):
        parties = db.scalars(select(Party).where(
            Party.company_id == company_id,
            or_(func.lower(Party.code).like(term), func.lower(Party.name_ar).like(term), func.lower(Party.name_en).like(term)),
        ).limit(per_type)).all()
        results += [_item("MASTER_DATA", "PARTY", r, r.code, "ACTIVE" if r.active else "INACTIVE", r.name_ar or r.name_en, r.credit_limit, "sales" if r.party_type in {"CUSTOMER", "BOTH"} else "purchases") for r in parties]

        inventory_items = db.scalars(select(Item).where(
            Item.company_id == company_id,
            or_(func.lower(Item.code).like(term), func.lower(Item.name_ar).like(term), func.lower(Item.name_en).like(term), func.lower(Item.item_type).like(term)),
        ).limit(per_type)).all()
        results += [_item("INVENTORY", "ITEM", r, r.code, "ACTIVE" if r.active else "INACTIVE", r.name_ar or r.name_en, r.standard_cost, "items") for r in inventory_items]

    if allowed("finance.read", "finance.arap.read"):
        sales = db.scalars(select(SalesInvoice).where(
            SalesInvoice.company_id == company_id,
            or_(func.lower(SalesInvoice.number).like(term), func.lower(func.coalesce(SalesInvoice.reference, "")).like(term), func.lower(SalesInvoice.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("SALES", "SALES_INVOICE", r, r.number, r.status, r.customer.name_ar or r.customer.name_en, r.total, "sales") for r in sales]

        purchases = db.scalars(select(PurchaseInvoice).where(
            PurchaseInvoice.company_id == company_id,
            or_(func.lower(PurchaseInvoice.number).like(term), func.lower(PurchaseInvoice.supplier_invoice_number).like(term), func.lower(PurchaseInvoice.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("PURCHASES", "PURCHASE_INVOICE", r, r.number, r.status, r.supplier.name_ar or r.supplier.name_en, r.total, "purchases") for r in purchases]

        receipts = db.scalars(select(Receipt).where(
            Receipt.company_id == company_id,
            or_(func.lower(Receipt.number).like(term), func.lower(Receipt.reference).like(term)),
        ).limit(per_type)).all()
        results += [_item("SALES", "RECEIPT", r, r.number, "POSTED", r.customer.name_ar or r.customer.name_en, r.amount, "sales") for r in receipts]

        payments = db.scalars(select(Payment).where(
            Payment.company_id == company_id,
            or_(func.lower(Payment.number).like(term), func.lower(Payment.reference).like(term)),
        ).limit(per_type)).all()
        results += [_item("PURCHASES", "PAYMENT", r, r.number, "POSTED", r.supplier.name_ar or r.supplier.name_en, r.amount, "purchases") for r in payments]

        journals = db.scalars(select(JournalEntry).where(
            JournalEntry.company_id == company_id,
            or_(func.lower(JournalEntry.number).like(term), func.lower(JournalEntry.reference).like(term), func.lower(JournalEntry.description).like(term), func.lower(JournalEntry.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("FINANCE", "JOURNAL_ENTRY", r, r.number, r.status, r.description, r.total_debit, "manualJournals") for r in journals]

    if allowed("procurement.manage", "procurement.approve", "inventory.read"):
        purchase_orders = db.scalars(select(PurchaseOrder).where(
            PurchaseOrder.company_id == company_id,
            or_(func.lower(PurchaseOrder.number).like(term), func.lower(PurchaseOrder.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("PROCUREMENT", "PURCHASE_ORDER", r, r.number, r.status, r.supplier.name_ar or r.supplier.name_en, r.total, "inventory") for r in purchase_orders]

        requisitions = db.scalars(select(PurchaseRequisition).where(
            PurchaseRequisition.company_id == company_id,
            or_(func.lower(PurchaseRequisition.number).like(term), func.lower(PurchaseRequisition.department).like(term), func.lower(PurchaseRequisition.justification).like(term), func.lower(PurchaseRequisition.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("PROCUREMENT", "PURCHASE_REQUISITION", r, r.number, r.status, r.department, r.estimated_total, "purchases") for r in requisitions]

        rfqs = db.scalars(select(RequestForQuotation).where(
            RequestForQuotation.company_id == company_id,
            or_(func.lower(RequestForQuotation.number).like(term), func.lower(RequestForQuotation.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("PROCUREMENT", "RFQ", r, r.number, r.status, f"PR #{r.requisition_id}", None, "purchases") for r in rfqs]

        quotations = db.scalars(select(SupplierQuotation).where(
            SupplierQuotation.company_id == company_id,
            or_(func.lower(SupplierQuotation.number).like(term), func.lower(SupplierQuotation.supplier_reference).like(term), func.lower(SupplierQuotation.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("PROCUREMENT", "SUPPLIER_QUOTATION", r, r.number, r.status, r.supplier.name_ar or r.supplier.name_en, r.total, "purchases") for r in quotations]

    if allowed("crm.read"):
        leads = db.scalars(select(CRMLead).where(
            CRMLead.company_id == company_id,
            or_(func.lower(CRMLead.number).like(term), func.lower(CRMLead.name).like(term), func.lower(func.coalesce(CRMLead.email, "")).like(term), func.lower(func.coalesce(CRMLead.phone, "")).like(term), func.lower(CRMLead.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("CRM", "LEAD", r, r.number, r.status, r.name, r.estimated_value, "crm") for r in leads]

    if allowed("itsm.read"):
        tickets = db.scalars(select(ServiceTicket).where(
            ServiceTicket.company_id == company_id,
            or_(func.lower(ServiceTicket.number).like(term), func.lower(ServiceTicket.subject).like(term), func.lower(func.coalesce(ServiceTicket.description, "")).like(term), func.lower(ServiceTicket.status).like(term)),
        ).limit(per_type)).all()
        results += [_item("ITSM", "SERVICE_TICKET", r, r.number, r.status, r.subject, None, "it") for r in tickets]

    results.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return {"query": q, "results": results[:limit], "count": min(len(results), limit)}


@router.get("/work-queue.csv")
def export_work_queue_csv(
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = work_queue(company_id=company_id, limit=500, db=db, user=user)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["module", "item_type", "id", "number", "status", "title", "amount", "created_at"])
    writer.writeheader()
    for row in payload["items"]:
        writer.writerow(row)
    data = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    headers = {"Content-Disposition": f'attachment; filename="corvax-work-queue-{company_id}.csv"'}
    return StreamingResponse(data, media_type="text/csv; charset=utf-8", headers=headers)
