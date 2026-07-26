from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import AuditLog, User
from app.services.audit import verify_audit_chain

router = APIRouter(prefix="/audit-log", tags=["audit trail"])


@router.get("")
def list_audit_events(
    company_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "audit.read")
    rows = db.scalars(
        select(AuditLog)
        .where((AuditLog.company_id == company_id) | (AuditLog.company_id.is_(None)))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "user_id": row.user_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "before": row.before_json,
            "after": row.after_json,
            "sequence_number": row.sequence_number,
            "previous_hash": row.previous_hash,
            "record_hash": row.record_hash,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/integrity")
def audit_integrity(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "audit.verify_integrity")
    return verify_audit_chain(db, company_id)
