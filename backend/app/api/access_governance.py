from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    AccessReviewCampaign, AccessReviewItem, Role, SoDConflict, SoDRule, User,
    UserCompanyRole,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/access-governance", tags=["access governance and segregation of duties"])


class SoDRuleIn(BaseModel):
    code: str = Field(min_length=3, max_length=60)
    name_ar: str = Field(min_length=3, max_length=250)
    name_en: str = Field(min_length=3, max_length=250)
    permission_a: str = Field(min_length=3, max_length=100)
    permission_b: str = Field(min_length=3, max_length=100)
    severity: str = "HIGH"
    rationale: str = Field(min_length=5)


class CampaignIn(BaseModel):
    company_id: int
    name: str = Field(min_length=3, max_length=250)
    period_start: date
    period_end: date
    scope: str = "ALL_USERS"


class ReviewDecisionIn(BaseModel):
    decision: str
    reviewer_notes: str = Field(min_length=3)


class ConflictMitigationIn(BaseModel):
    mitigating_control: str = Field(min_length=5)
    remediation_due_date: date


class ConflictResolveIn(BaseModel):
    resolution_notes: str = Field(min_length=5)


def _permissions_for_membership(membership: UserCompanyRole) -> set[str]:
    return {p.code for p in membership.role.permissions}


def _open_conflicts_for_user(db: Session, company_id: int, user_id: int) -> int:
    return db.scalar(select(func.count(SoDConflict.id)).where(SoDConflict.company_id == company_id, SoDConflict.user_id == user_id, SoDConflict.status.in_(["OPEN", "MITIGATED"]))) or 0


@router.post("/sod-rules", status_code=201)
def create_sod_rule(data: SoDRuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Global rule administration is anchored to any company where the user has access.manage.
    memberships = db.scalars(select(UserCompanyRole).where(UserCompanyRole.user_id == user.id)).all()
    if not memberships: raise HTTPException(403, "No company access")
    ensure_permission(db, user, memberships[0].company_id, "access.manage")
    if data.permission_a == data.permission_b: raise HTTPException(422, "SoD permissions must be different")
    if db.scalar(select(SoDRule.id).where(SoDRule.code == data.code)):
        raise HTTPException(409, "SoD rule code already exists")
    severity = data.severity.upper()
    if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}: raise HTTPException(422, "Invalid severity")
    row = SoDRule(**data.model_dump(exclude={"severity"}), severity=severity)
    db.add(row); db.flush()
    write_audit(db, action="SOD_RULE_CREATED", entity_type="SOD_RULE", entity_id=row.id, user_id=user.id, company_id=None, after={"code": row.code, "severity": severity})
    db.commit(); return {"id": row.id, "code": row.code, "severity": row.severity}


@router.get("/sod-rules")
def list_sod_rules(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "access.review")
    rows = db.scalars(select(SoDRule).where(SoDRule.active.is_(True)).order_by(SoDRule.severity.desc(), SoDRule.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "permission_a": r.permission_a, "permission_b": r.permission_b, "severity": r.severity, "rationale": r.rationale} for r in rows]


@router.post("/scan/{company_id}")
def scan_sod_conflicts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "access.review")
    memberships = db.scalars(select(UserCompanyRole).options(selectinload(UserCompanyRole.role).selectinload(Role.permissions)).where(UserCompanyRole.company_id == company_id)).all()
    by_user: dict[int, set[str]] = {}
    for membership in memberships:
        by_user.setdefault(membership.user_id, set()).update(_permissions_for_membership(membership))
    rules = db.scalars(select(SoDRule).where(SoDRule.active.is_(True))).all()
    detected = 0
    for user_id, permissions in by_user.items():
        for rule in rules:
            if rule.permission_a in permissions and rule.permission_b in permissions:
                exists = db.scalar(select(SoDConflict.id).where(SoDConflict.company_id == company_id, SoDConflict.user_id == user_id, SoDConflict.rule_id == rule.id, SoDConflict.status.in_(["OPEN", "MITIGATED"])))
                if not exists:
                    db.add(SoDConflict(company_id=company_id, user_id=user_id, rule_id=rule.id, status="OPEN")); detected += 1
    write_audit(db, action="SOD_SCAN_EXECUTED", entity_type="COMPANY", entity_id=company_id, user_id=user.id, company_id=company_id, after={"new_conflicts": detected, "users_scanned": len(by_user), "rules": len(rules)})
    db.commit()
    total = db.scalar(select(func.count(SoDConflict.id)).where(SoDConflict.company_id == company_id, SoDConflict.status.in_(["OPEN", "MITIGATED"]))) or 0
    return {"company_id": company_id, "new_conflicts": detected, "open_or_mitigated_conflicts": total}


@router.get("/conflicts")
def list_conflicts(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "access.review")
    query = select(SoDConflict).where(SoDConflict.company_id == company_id)
    if status: query = query.where(SoDConflict.status == status.upper())
    rows = db.scalars(query.order_by(SoDConflict.detected_at.desc())).all()
    return [{"id": r.id, "user_id": r.user_id, "user": r.user.email, "rule_code": r.rule.code, "severity": r.rule.severity, "permission_a": r.rule.permission_a, "permission_b": r.rule.permission_b, "status": r.status, "mitigating_control": r.mitigating_control, "remediation_due_date": r.remediation_due_date} for r in rows]


@router.post("/conflicts/{conflict_id}/mitigate")
def mitigate_conflict(conflict_id: int, data: ConflictMitigationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SoDConflict, conflict_id)
    if not row: raise HTTPException(404, "SoD conflict not found")
    ensure_permission(db, user, row.company_id, "access.manage")
    if data.remediation_due_date < date.today(): raise HTTPException(422, "Remediation date cannot be in the past")
    row.status = "MITIGATED"; row.mitigating_control = data.mitigating_control; row.remediation_due_date = data.remediation_due_date
    write_audit(db, action="SOD_CONFLICT_MITIGATED", entity_type="SOD_CONFLICT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"control": row.mitigating_control, "due": row.remediation_due_date})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: int, data: ConflictResolveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SoDConflict, conflict_id)
    if not row: raise HTTPException(404, "SoD conflict not found")
    ensure_permission(db, user, row.company_id, "access.manage")
    memberships = db.scalars(select(UserCompanyRole).options(selectinload(UserCompanyRole.role).selectinload(Role.permissions)).where(UserCompanyRole.company_id == row.company_id, UserCompanyRole.user_id == row.user_id)).all()
    permissions: set[str] = set()
    for membership in memberships: permissions.update(_permissions_for_membership(membership))
    if row.rule.permission_a in permissions and row.rule.permission_b in permissions:
        raise HTTPException(409, "Conflict remains in current role assignments")
    row.status = "RESOLVED"; row.resolved_by = user.id; row.resolved_at = utc_now()
    write_audit(db, action="SOD_CONFLICT_RESOLVED", entity_type="SOD_CONFLICT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"notes": data.resolution_notes})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/campaigns", status_code=201)
def create_campaign(data: CampaignIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "access.manage")
    if data.period_end < data.period_start: raise HTTPException(422, "Invalid campaign period")
    count = db.scalar(select(func.count(AccessReviewCampaign.id)).where(AccessReviewCampaign.company_id == data.company_id)) or 0
    row = AccessReviewCampaign(company_id=data.company_id, number=f"AR-{data.company_id}-{data.period_end.year}-{count + 1:04d}", name=data.name, period_start=data.period_start, period_end=data.period_end, scope=data.scope.upper(), status="IN_REVIEW", created_by=user.id)
    db.add(row); db.flush()
    memberships = db.scalars(select(UserCompanyRole).where(UserCompanyRole.company_id == data.company_id)).all()
    for membership in memberships:
        row.items.append(AccessReviewItem(membership_id=membership.id, user_id=membership.user_id, role_id=membership.role_id, conflict_count=_open_conflicts_for_user(db, data.company_id, membership.user_id), decision="PENDING"))
    write_audit(db, action="ACCESS_REVIEW_CAMPAIGN_CREATED", entity_type="ACCESS_REVIEW_CAMPAIGN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"number": row.number, "items": len(row.items)})
    db.commit(); return {"id": row.id, "number": row.number, "status": row.status, "items": len(row.items)}


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(AccessReviewCampaign, campaign_id)
    if not row: raise HTTPException(404, "Campaign not found")
    ensure_permission(db, user, row.company_id, "access.review")
    return {"id": row.id, "number": row.number, "name": row.name, "status": row.status, "period_start": row.period_start, "period_end": row.period_end, "items": [{"id": i.id, "user_id": i.user_id, "user": i.user.email, "role": i.role.code, "conflict_count": i.conflict_count, "decision": i.decision, "reviewer_notes": i.reviewer_notes} for i in row.items]}


@router.post("/review-items/{item_id}/decision")
def review_access_item(item_id: int, data: ReviewDecisionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(AccessReviewItem, item_id)
    if not item: raise HTTPException(404, "Access review item not found")
    campaign = db.get(AccessReviewCampaign, item.campaign_id)
    ensure_permission(db, user, campaign.company_id, "access.review")
    if item.user_id == user.id: raise HTTPException(409, "Users cannot certify their own access")
    decision = data.decision.upper()
    if decision not in {"RETAIN", "REVOKE"}: raise HTTPException(422, "Decision must be RETAIN or REVOKE")
    if decision == "RETAIN" and item.conflict_count > 0 and len(data.reviewer_notes.strip()) < 10:
        raise HTTPException(422, "Retaining conflicted access requires detailed justification")
    item.decision = decision; item.reviewer_notes = data.reviewer_notes; item.reviewed_by = user.id; item.reviewed_at = utc_now()
    write_audit(db, action="ACCESS_REVIEW_ITEM_DECIDED", entity_type="ACCESS_REVIEW_ITEM", entity_id=item.id, user_id=user.id, company_id=campaign.company_id, after={"decision": decision, "role_id": item.role_id})
    db.commit(); return {"id": item.id, "decision": item.decision}


@router.post("/campaigns/{campaign_id}/approve")
def approve_campaign(campaign_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    campaign = db.get(AccessReviewCampaign, campaign_id)
    if not campaign: raise HTTPException(404, "Campaign not found")
    ensure_permission(db, user, campaign.company_id, "access.approve")
    if campaign.created_by == user.id: raise HTTPException(409, "Maker-checker: campaign creator cannot approve")
    pending = [i for i in campaign.items if i.decision == "PENDING"]
    if pending: raise HTTPException(422, f"{len(pending)} access review items remain pending")
    revoked = 0
    for item in campaign.items:
        if item.decision == "REVOKE":
            db.execute(delete(UserCompanyRole).where(UserCompanyRole.id == item.membership_id)); revoked += 1
    campaign.status = "APPROVED"; campaign.approved_by = user.id; campaign.approved_at = utc_now()
    write_audit(db, action="ACCESS_REVIEW_CAMPAIGN_APPROVED", entity_type="ACCESS_REVIEW_CAMPAIGN", entity_id=campaign.id, user_id=user.id, company_id=campaign.company_id, after={"revoked_memberships": revoked, "items": len(campaign.items)})
    db.commit(); return {"id": campaign.id, "status": campaign.status, "revoked_memberships": revoked}


@router.get("/dashboard")
def access_dashboard(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "access.review")
    open_conflicts = db.scalar(select(func.count(SoDConflict.id)).where(SoDConflict.company_id == company_id, SoDConflict.status == "OPEN")) or 0
    mitigated = db.scalar(select(func.count(SoDConflict.id)).where(SoDConflict.company_id == company_id, SoDConflict.status == "MITIGATED")) or 0
    pending_items = db.scalar(select(func.count(AccessReviewItem.id)).join(AccessReviewCampaign).where(AccessReviewCampaign.company_id == company_id, AccessReviewItem.decision == "PENDING")) or 0
    active_campaigns = db.scalar(select(func.count(AccessReviewCampaign.id)).where(AccessReviewCampaign.company_id == company_id, AccessReviewCampaign.status == "IN_REVIEW")) or 0
    return {"open_sod_conflicts": open_conflicts, "mitigated_sod_conflicts": mitigated, "pending_access_certifications": pending_items, "active_campaigns": active_campaigns, "control_framework": {"periodic_access_review": True, "self_certification_blocked": True, "maker_checker_approval": True, "sod_detection": True, "revocation_on_approval": True}}
