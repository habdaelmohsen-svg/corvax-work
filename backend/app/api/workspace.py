from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    GymFacilityBooking, GymMembershipModification, PayrollRun, PlatformSettlementBatch,
    PosControlRequest, PosOrder, User,
)

router = APIRouter(prefix="/workspace", tags=["Operational workspace RC16"])

PENDING_STATUSES = {"SUBMITTED", "PENDING", "PENDING_APPROVAL", "AWAITING_APPROVAL", "REVIEWED", "CLOSED_PENDING_APPROVAL"}


def _guard(db: Session, user: User, company_id: int) -> None:
    ensure_permission(db, user, company_id, "company.read")


def _item(module: str, item_type: str, row: Any, number: str, status: str, title: str, amount: Any = None) -> dict[str, Any]:
    return {
        "module": module,
        "item_type": item_type,
        "id": row.id,
        "number": number,
        "status": status,
        "title": title,
        "amount": float(amount or 0),
        "created_at": getattr(row, "created_at", None),
    }


@router.get("/work-queue")
def work_queue(
    company_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _guard(db, user, company_id)
    items: list[dict[str, Any]] = []

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

    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return {
        "items": items[:limit],
        "total": len(items),
        "by_module": {m: sum(1 for i in items if i["module"] == m) for m in {"GYM", "POS", "HR"}},
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

    mods = db.scalars(select(GymMembershipModification).where(
        GymMembershipModification.company_id == company_id,
        or_(func.lower(GymMembershipModification.number).like(term), func.lower(GymMembershipModification.reason).like(term), func.lower(GymMembershipModification.modification_type).like(term)),
    ).limit(limit)).all()
    results += [_item("GYM", "MEMBERSHIP_MODIFICATION", r, r.number, r.status, r.reason, r.adjustment_net or r.refund_total) for r in mods]

    orders = db.scalars(select(PosOrder).where(
        PosOrder.company_id == company_id,
        or_(func.lower(PosOrder.number).like(term), func.lower(func.coalesce(PosOrder.customer_name, "")).like(term), func.lower(PosOrder.business_unit).like(term)),
    ).limit(limit)).all()
    results += [_item("POS", "POS_ORDER", r, r.number, r.status, r.customer_name or r.business_unit, r.total) for r in orders]

    payrolls = db.scalars(select(PayrollRun).where(
        PayrollRun.company_id == company_id,
        or_(cast(PayrollRun.period_year, String).like(f"%{q}%"), PayrollRun.status.ilike(term)),
    ).limit(limit)).all()
    results += [_item("HR", "PAYROLL_RUN", r, f"PAY-{r.period_year}-{r.period_month:02d}", r.status, "PAYROLL_RUN", r.total_net) for r in payrolls]

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
