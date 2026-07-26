from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import ITAsset, ServiceTicket, User
from app.services.audit import write_audit

router = APIRouter(prefix="/itsm", tags=["digital administration and IT service management"])


class ITAssetIn(BaseModel):
    company_id: int
    asset_tag: str = Field(min_length=2, max_length=60)
    asset_type: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=250)
    serial_number: str | None = None
    branch_id: int | None = None
    assigned_user_id: int | None = None
    purchase_date: date | None = None
    warranty_end: date | None = None
    criticality: str = "MEDIUM"


class TicketIn(BaseModel):
    company_id: int
    category: str = "GENERAL"
    subject: str = Field(min_length=2, max_length=250)
    description: str | None = None
    priority: str = "MEDIUM"
    assignee_user_id: int | None = None
    due_hours: int = Field(default=24, ge=1, le=720)


class TicketAssign(BaseModel):
    assignee_user_id: int


class TicketResolve(BaseModel):
    resolution: str = Field(min_length=2)


def _ticket_dict(row: ServiceTicket) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "number": row.number,
        "category": row.category,
        "subject": row.subject,
        "description": row.description,
        "priority": row.priority,
        "status": row.status,
        "requester_user_id": row.requester_user_id,
        "assignee_user_id": row.assignee_user_id,
        "opened_at": row.opened_at,
        "due_at": row.due_at,
        "resolved_at": row.resolved_at,
        "resolution": row.resolution,
        "overdue": bool(row.status != "RESOLVED" and row.due_at and row.due_at < utc_now()),
    }


@router.get("/summary")
def summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "itsm.read")
    now = utc_now()
    assets = db.scalar(select(func.count(ITAsset.id)).where(ITAsset.company_id == company_id)) or 0
    active_assets = db.scalar(select(func.count(ITAsset.id)).where(ITAsset.company_id == company_id, ITAsset.status == "IN_SERVICE")) or 0
    tickets = db.scalar(select(func.count(ServiceTicket.id)).where(ServiceTicket.company_id == company_id)) or 0
    open_tickets = db.scalar(select(func.count(ServiceTicket.id)).where(ServiceTicket.company_id == company_id, ServiceTicket.status != "RESOLVED")) or 0
    high_priority = db.scalar(select(func.count(ServiceTicket.id)).where(ServiceTicket.company_id == company_id, ServiceTicket.status != "RESOLVED", ServiceTicket.priority.in_(["HIGH", "CRITICAL"]))) or 0
    overdue = db.scalar(select(func.count(ServiceTicket.id)).where(ServiceTicket.company_id == company_id, ServiceTicket.status != "RESOLVED", ServiceTicket.due_at < now)) or 0
    resolved = db.scalar(select(func.count(ServiceTicket.id)).where(ServiceTicket.company_id == company_id, ServiceTicket.status == "RESOLVED")) or 0
    return {
        "company_id": company_id,
        "it_assets": assets,
        "active_assets": active_assets,
        "tickets": tickets,
        "open_tickets": open_tickets,
        "high_priority_open": high_priority,
        "overdue_tickets": overdue,
        "resolved_tickets": resolved,
        "sla_compliance": round(((tickets - overdue) / tickets * 100), 1) if tickets else 100.0,
        "framework": "IT_ASSET_SERVICE_DESK_SLA",
    }


@router.post("/assets", status_code=201)
def create_asset(data: ITAssetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "itsm.manage")
    if db.scalar(select(ITAsset).where(ITAsset.company_id == data.company_id, ITAsset.asset_tag == data.asset_tag)):
        raise HTTPException(409, "IT asset tag already exists")
    row = ITAsset(
        company_id=data.company_id,
        asset_tag=data.asset_tag.upper(),
        asset_type=data.asset_type.upper(),
        name=data.name,
        serial_number=data.serial_number,
        branch_id=data.branch_id,
        assigned_user_id=data.assigned_user_id,
        purchase_date=data.purchase_date,
        warranty_end=data.warranty_end,
        criticality=data.criticality.upper(),
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="IT_ASSET_CREATED", entity_type="IT_ASSET", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"asset_tag": row.asset_tag, "asset_type": row.asset_type, "criticality": row.criticality})
    db.commit()
    return {"id": row.id, "asset_tag": row.asset_tag, "status": row.status, "criticality": row.criticality}


@router.get("/assets")
def list_assets(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "itsm.read")
    query = select(ITAsset).where(ITAsset.company_id == company_id)
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, ITAsset)
    if _scope is not None:
        query = query.where(_scope)
    if status:
        query = query.where(ITAsset.status == status.upper())
    rows = db.scalars(query.order_by(ITAsset.asset_tag)).all()
    return [
        {
            "id": row.id,
            "asset_tag": row.asset_tag,
            "asset_type": row.asset_type,
            "name": row.name,
            "serial_number": row.serial_number,
            "branch_id": row.branch_id,
            "assigned_user_id": row.assigned_user_id,
            "purchase_date": row.purchase_date,
            "warranty_end": row.warranty_end,
            "status": row.status,
            "criticality": row.criticality,
        }
        for row in rows
    ]


def _next_number(db: Session, company_id: int) -> str:
    count = db.scalar(select(func.count(ServiceTicket.id)).where(ServiceTicket.company_id == company_id)) or 0
    return f"IT-{utc_now():%y%m%d}-{int(count) + 1:05d}"


@router.post("/tickets", status_code=201)
def create_ticket(data: TicketIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "itsm.read")
    if data.assignee_user_id and not db.get(User, data.assignee_user_id):
        raise HTTPException(404, "Assignee user not found")
    row = ServiceTicket(
        company_id=data.company_id,
        number=_next_number(db, data.company_id),
        category=data.category.upper(),
        subject=data.subject,
        description=data.description,
        priority=data.priority.upper(),
        requester_user_id=user.id,
        assignee_user_id=data.assignee_user_id,
        status="ASSIGNED" if data.assignee_user_id else "OPEN",
        due_at=utc_now() + timedelta(hours=data.due_hours),
    )
    db.add(row)
    db.flush()
    write_audit(db, action="SERVICE_TICKET_CREATED", entity_type="SERVICE_TICKET", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": row.number, "priority": row.priority, "status": row.status, "due_at": row.due_at})
    db.commit()
    return _ticket_dict(row)


@router.get("/tickets")
def list_tickets(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "itsm.read")
    query = select(ServiceTicket).where(ServiceTicket.company_id == company_id)
    if status:
        query = query.where(ServiceTicket.status == status.upper())
    rows = db.scalars(query.order_by(ServiceTicket.opened_at.desc())).all()
    return [_ticket_dict(row) for row in rows]


@router.post("/tickets/{ticket_id}/assign")
def assign_ticket(ticket_id: int, data: TicketAssign, company_id: int = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "itsm.manage")
    row = db.get(ServiceTicket, ticket_id)
    if not row or row.company_id != company_id:
        raise HTTPException(404, "Service ticket not found")
    if not db.get(User, data.assignee_user_id):
        raise HTTPException(404, "Assignee user not found")
    before = {"assignee_user_id": row.assignee_user_id, "status": row.status}
    row.assignee_user_id = data.assignee_user_id
    row.status = "ASSIGNED"
    write_audit(db, action="SERVICE_TICKET_ASSIGNED", entity_type="SERVICE_TICKET", entity_id=row.id, user_id=user.id, company_id=company_id, before=before, after={"assignee_user_id": row.assignee_user_id, "status": row.status})
    db.commit()
    return _ticket_dict(row)


@router.post("/tickets/{ticket_id}/start")
def start_ticket(ticket_id: int, company_id: int = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "itsm.manage")
    row = db.get(ServiceTicket, ticket_id)
    if not row or row.company_id != company_id:
        raise HTTPException(404, "Service ticket not found")
    if row.status == "RESOLVED":
        raise HTTPException(409, "Resolved ticket cannot be restarted")
    row.status = "IN_PROGRESS"
    write_audit(db, action="SERVICE_TICKET_STARTED", entity_type="SERVICE_TICKET", entity_id=row.id, user_id=user.id, company_id=company_id, after={"status": row.status})
    db.commit()
    return _ticket_dict(row)


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int, data: TicketResolve, company_id: int = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "itsm.manage")
    row = db.get(ServiceTicket, ticket_id)
    if not row or row.company_id != company_id:
        raise HTTPException(404, "Service ticket not found")
    if row.status == "RESOLVED":
        raise HTTPException(409, "Ticket is already resolved")
    row.status = "RESOLVED"
    row.resolved_at = utc_now()
    row.resolution = data.resolution
    write_audit(db, action="SERVICE_TICKET_RESOLVED", entity_type="SERVICE_TICKET", entity_id=row.id, user_id=user.id, company_id=company_id, after={"status": row.status, "resolved_at": row.resolved_at, "resolution": row.resolution})
    db.commit()
    return _ticket_dict(row)
