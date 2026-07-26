from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    AuditEngagement,
    AuditFinding,
    ControlledDocument,
    CorrectiveAction,
    GovernanceControl,
    GovernanceRisk,
    User,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/governance", tags=["governance, risk and assurance"])


class RiskIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=50)
    title_ar: str = Field(min_length=2, max_length=250)
    title_en: str = Field(min_length=2, max_length=250)
    category: str = "OPERATIONAL"
    likelihood: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    residual_score: int | None = Field(default=None, ge=1, le=25)
    owner_user_id: int | None = None
    mitigation_due_date: date | None = None
    description: str | None = None


class ControlIn(BaseModel):
    company_id: int
    risk_id: int | None = None
    code: str = Field(min_length=2, max_length=50)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    control_type: str = "PREVENTIVE"
    frequency: str = "MONTHLY"
    owner_user_id: int | None = None
    design_status: str = "EFFECTIVE"
    operating_status: str = "NOT_TESTED"
    last_test_date: date | None = None
    next_test_date: date | None = None
    description: str | None = None


class EngagementIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=50)
    title_ar: str = Field(min_length=2, max_length=250)
    title_en: str = Field(min_length=2, max_length=250)
    audit_type: str = "INTERNAL"
    scope: str | None = None
    risk_rating: str = "MEDIUM"
    planned_start: date | None = None
    planned_end: date | None = None
    lead_auditor_id: int | None = None


class FindingIn(BaseModel):
    company_id: int
    engagement_id: int
    code: str = Field(min_length=2, max_length=50)
    title_ar: str = Field(min_length=2, max_length=250)
    title_en: str = Field(min_length=2, max_length=250)
    severity: str = "MEDIUM"
    description: str = Field(min_length=2)
    root_cause: str | None = None
    recommendation: str | None = None
    owner_user_id: int | None = None
    due_date: date | None = None


class ActionIn(BaseModel):
    company_id: int
    description: str = Field(min_length=2)
    owner_user_id: int | None = None
    due_date: date | None = None


class ActionUpdate(BaseModel):
    status: str
    completion_percent: int = Field(ge=0, le=100)
    evidence_reference: str | None = None


class DocumentIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=60)
    title_ar: str = Field(min_length=2, max_length=250)
    title_en: str = Field(min_length=2, max_length=250)
    document_type: str = "POLICY"
    version: str = "1.0"
    effective_date: date | None = None
    review_date: date | None = None
    owner_user_id: int | None = None
    content_summary: str | None = None


def _risk_dict(row: GovernanceRisk) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "code": row.code,
        "title_ar": row.title_ar,
        "title_en": row.title_en,
        "category": row.category,
        "likelihood": row.likelihood,
        "impact": row.impact,
        "inherent_score": row.inherent_score,
        "residual_score": row.residual_score,
        "owner_user_id": row.owner_user_id,
        "status": row.status,
        "mitigation_due_date": row.mitigation_due_date,
        "description": row.description,
    }


def _finding_dict(row: AuditFinding) -> dict:
    return {
        "id": row.id,
        "engagement_id": row.engagement_id,
        "code": row.code,
        "title_ar": row.title_ar,
        "title_en": row.title_en,
        "severity": row.severity,
        "description": row.description,
        "root_cause": row.root_cause,
        "recommendation": row.recommendation,
        "owner_user_id": row.owner_user_id,
        "due_date": row.due_date,
        "status": row.status,
        "created_at": row.created_at,
        "closed_at": row.closed_at,
    }


@router.get("/summary")
def summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.read")
    today = date.today()
    risks = db.scalar(select(func.count(GovernanceRisk.id)).where(GovernanceRisk.company_id == company_id)) or 0
    high_risks = db.scalar(
        select(func.count(GovernanceRisk.id)).where(
            GovernanceRisk.company_id == company_id,
            GovernanceRisk.status != "CLOSED",
            GovernanceRisk.residual_score >= 15,
        )
    ) or 0
    controls = db.scalar(select(func.count(GovernanceControl.id)).where(GovernanceControl.company_id == company_id)) or 0
    ineffective_controls = db.scalar(
        select(func.count(GovernanceControl.id)).where(
            GovernanceControl.company_id == company_id,
            GovernanceControl.operating_status.in_(["INEFFECTIVE", "DEFICIENT"]),
        )
    ) or 0
    engagements = db.scalar(select(func.count(AuditEngagement.id)).where(AuditEngagement.company_id == company_id)) or 0
    open_findings = db.scalar(
        select(func.count(AuditFinding.id)).where(AuditFinding.company_id == company_id, AuditFinding.status != "CLOSED")
    ) or 0
    overdue_findings = db.scalar(
        select(func.count(AuditFinding.id)).where(
            AuditFinding.company_id == company_id,
            AuditFinding.status != "CLOSED",
            AuditFinding.due_date.is_not(None),
            AuditFinding.due_date < today,
        )
    ) or 0
    documents_due = db.scalar(
        select(func.count(ControlledDocument.id)).where(
            ControlledDocument.company_id == company_id,
            ControlledDocument.review_date.is_not(None),
            ControlledDocument.review_date <= today,
            ControlledDocument.status == "APPROVED",
        )
    ) or 0
    return {
        "company_id": company_id,
        "risks": risks,
        "high_residual_risks": high_risks,
        "controls": controls,
        "ineffective_controls": ineffective_controls,
        "audit_engagements": engagements,
        "open_findings": open_findings,
        "overdue_findings": overdue_findings,
        "documents_due_for_review": documents_due,
        "framework": "RISK_CONTROL_AUDIT_CAPA_DOCUMENT_CONTROL",
    }


@router.post("/risks", status_code=201)
def create_risk(data: RiskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "grc.manage")
    if db.scalar(select(GovernanceRisk).where(GovernanceRisk.company_id == data.company_id, GovernanceRisk.code == data.code)):
        raise HTTPException(409, "Risk code already exists")
    score = data.likelihood * data.impact
    residual = data.residual_score if data.residual_score is not None else score
    row = GovernanceRisk(
        company_id=data.company_id,
        code=data.code.upper(),
        title_ar=data.title_ar,
        title_en=data.title_en,
        category=data.category.upper(),
        likelihood=data.likelihood,
        impact=data.impact,
        inherent_score=score,
        residual_score=residual,
        owner_user_id=data.owner_user_id,
        mitigation_due_date=data.mitigation_due_date,
        description=data.description,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="GRC_RISK_CREATED", entity_type="GOVERNANCE_RISK", entity_id=row.id, user_id=user.id, company_id=data.company_id, after=_risk_dict(row))
    db.commit()
    return _risk_dict(row)


@router.get("/risks")
def list_risks(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.read")
    query = select(GovernanceRisk).where(GovernanceRisk.company_id == company_id)
    if status:
        query = query.where(GovernanceRisk.status == status.upper())
    rows = db.scalars(query.order_by(GovernanceRisk.residual_score.desc(), GovernanceRisk.code)).all()
    return [_risk_dict(row) for row in rows]


@router.post("/controls", status_code=201)
def create_control(data: ControlIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "grc.manage")
    if data.risk_id:
        risk = db.get(GovernanceRisk, data.risk_id)
        if not risk or risk.company_id != data.company_id:
            raise HTTPException(404, "Risk not found")
    if db.scalar(select(GovernanceControl).where(GovernanceControl.company_id == data.company_id, GovernanceControl.code == data.code)):
        raise HTTPException(409, "Control code already exists")
    row = GovernanceControl(
        company_id=data.company_id,
        risk_id=data.risk_id,
        code=data.code.upper(),
        name_ar=data.name_ar,
        name_en=data.name_en,
        control_type=data.control_type.upper(),
        frequency=data.frequency.upper(),
        owner_user_id=data.owner_user_id,
        design_status=data.design_status.upper(),
        operating_status=data.operating_status.upper(),
        last_test_date=data.last_test_date,
        next_test_date=data.next_test_date,
        description=data.description,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="GRC_CONTROL_CREATED", entity_type="GOVERNANCE_CONTROL", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "risk_id": row.risk_id, "operating_status": row.operating_status})
    db.commit()
    return {"id": row.id, "code": row.code, "risk_id": row.risk_id, "design_status": row.design_status, "operating_status": row.operating_status}


@router.get("/controls")
def list_controls(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.read")
    rows = db.scalars(select(GovernanceControl).where(GovernanceControl.company_id == company_id).order_by(GovernanceControl.code)).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "risk_id": row.risk_id,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "control_type": row.control_type,
            "frequency": row.frequency,
            "design_status": row.design_status,
            "operating_status": row.operating_status,
            "last_test_date": row.last_test_date,
            "next_test_date": row.next_test_date,
        }
        for row in rows
    ]


@router.post("/audits", status_code=201)
def create_engagement(data: EngagementIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "audit.manage")
    if data.planned_start and data.planned_end and data.planned_end < data.planned_start:
        raise HTTPException(422, "Planned end date cannot precede start date")
    if db.scalar(select(AuditEngagement).where(AuditEngagement.company_id == data.company_id, AuditEngagement.code == data.code)):
        raise HTTPException(409, "Audit engagement code already exists")
    row = AuditEngagement(
        company_id=data.company_id,
        code=data.code.upper(),
        title_ar=data.title_ar,
        title_en=data.title_en,
        audit_type=data.audit_type.upper(),
        scope=data.scope,
        risk_rating=data.risk_rating.upper(),
        planned_start=data.planned_start,
        planned_end=data.planned_end,
        lead_auditor_id=data.lead_auditor_id,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="AUDIT_ENGAGEMENT_CREATED", entity_type="AUDIT_ENGAGEMENT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "type": row.audit_type, "risk_rating": row.risk_rating})
    db.commit()
    return {"id": row.id, "code": row.code, "status": row.status, "risk_rating": row.risk_rating}


@router.get("/audits")
def list_engagements(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.read")
    rows = db.scalars(select(AuditEngagement).where(AuditEngagement.company_id == company_id).order_by(AuditEngagement.created_at.desc())).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "title_ar": row.title_ar,
            "title_en": row.title_en,
            "audit_type": row.audit_type,
            "status": row.status,
            "risk_rating": row.risk_rating,
            "planned_start": row.planned_start,
            "planned_end": row.planned_end,
        }
        for row in rows
    ]


@router.post("/findings", status_code=201)
def create_finding(data: FindingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "audit.manage")
    engagement = db.get(AuditEngagement, data.engagement_id)
    if not engagement or engagement.company_id != data.company_id:
        raise HTTPException(404, "Audit engagement not found")
    if db.scalar(select(AuditFinding).where(AuditFinding.company_id == data.company_id, AuditFinding.code == data.code)):
        raise HTTPException(409, "Finding code already exists")
    row = AuditFinding(
        company_id=data.company_id,
        engagement_id=data.engagement_id,
        code=data.code.upper(),
        title_ar=data.title_ar,
        title_en=data.title_en,
        severity=data.severity.upper(),
        description=data.description,
        root_cause=data.root_cause,
        recommendation=data.recommendation,
        owner_user_id=data.owner_user_id,
        due_date=data.due_date,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="AUDIT_FINDING_CREATED", entity_type="AUDIT_FINDING", entity_id=row.id, user_id=user.id, company_id=data.company_id, after=_finding_dict(row))
    db.commit()
    return _finding_dict(row)


@router.get("/findings")
def list_findings(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.read")
    query = select(AuditFinding).where(AuditFinding.company_id == company_id)
    if status:
        query = query.where(AuditFinding.status == status.upper())
    rows = db.scalars(query.order_by(AuditFinding.due_date, AuditFinding.severity.desc())).all()
    return [_finding_dict(row) for row in rows]


@router.post("/findings/{finding_id}/actions", status_code=201)
def create_action(finding_id: int, data: ActionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "grc.manage")
    finding = db.get(AuditFinding, finding_id)
    if not finding or finding.company_id != data.company_id:
        raise HTTPException(404, "Finding not found")
    row = CorrectiveAction(
        company_id=data.company_id,
        finding_id=finding_id,
        description=data.description,
        owner_user_id=data.owner_user_id,
        due_date=data.due_date,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="CORRECTIVE_ACTION_CREATED", entity_type="CORRECTIVE_ACTION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"finding_id": finding_id, "due_date": data.due_date})
    db.commit()
    return {"id": row.id, "finding_id": row.finding_id, "status": row.status, "completion_percent": row.completion_percent}


@router.patch("/actions/{action_id}")
def update_action(action_id: int, data: ActionUpdate, company_id: int = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.manage")
    row = db.get(CorrectiveAction, action_id)
    if not row or row.company_id != company_id:
        raise HTTPException(404, "Corrective action not found")
    before = {"status": row.status, "completion_percent": row.completion_percent, "evidence_reference": row.evidence_reference}
    row.status = data.status.upper()
    row.completion_percent = data.completion_percent
    row.evidence_reference = data.evidence_reference
    if row.status == "COMPLETED" or row.completion_percent == 100:
        row.status = "COMPLETED"
        row.completion_percent = 100
        row.completed_at = utc_now()
    write_audit(db, action="CORRECTIVE_ACTION_UPDATED", entity_type="CORRECTIVE_ACTION", entity_id=row.id, user_id=user.id, company_id=company_id, before=before, after={"status": row.status, "completion_percent": row.completion_percent, "evidence_reference": row.evidence_reference})
    db.commit()
    return {"id": row.id, "status": row.status, "completion_percent": row.completion_percent, "completed_at": row.completed_at}


@router.get("/actions")
def list_actions(company_id: int, finding_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.read")
    query = select(CorrectiveAction).where(CorrectiveAction.company_id == company_id)
    if finding_id:
        query = query.where(CorrectiveAction.finding_id == finding_id)
    rows = db.scalars(query.order_by(CorrectiveAction.due_date, CorrectiveAction.id)).all()
    return [
        {
            "id": row.id,
            "finding_id": row.finding_id,
            "description": row.description,
            "owner_user_id": row.owner_user_id,
            "due_date": row.due_date,
            "status": row.status,
            "completion_percent": row.completion_percent,
            "evidence_reference": row.evidence_reference,
        }
        for row in rows
    ]


@router.post("/documents", status_code=201)
def create_document(data: DocumentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "documents.manage")
    if db.scalar(select(ControlledDocument).where(ControlledDocument.company_id == data.company_id, ControlledDocument.code == data.code, ControlledDocument.version == data.version)):
        raise HTTPException(409, "Document version already exists")
    row = ControlledDocument(
        company_id=data.company_id,
        code=data.code.upper(),
        title_ar=data.title_ar,
        title_en=data.title_en,
        document_type=data.document_type.upper(),
        version=data.version,
        effective_date=data.effective_date,
        review_date=data.review_date,
        owner_user_id=data.owner_user_id,
        content_summary=data.content_summary,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="CONTROLLED_DOCUMENT_CREATED", entity_type="CONTROLLED_DOCUMENT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "version": row.version, "status": row.status})
    db.commit()
    return {"id": row.id, "code": row.code, "version": row.version, "status": row.status}


@router.post("/documents/{document_id}/approve")
def approve_document(document_id: int, company_id: int = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "documents.manage")
    row = db.get(ControlledDocument, document_id)
    if not row or row.company_id != company_id:
        raise HTTPException(404, "Document not found")
    if row.created_by == user.id:
        raise HTTPException(409, "Document creator cannot approve the same document")
    row.status = "APPROVED"
    row.approved_by = user.id
    write_audit(db, action="CONTROLLED_DOCUMENT_APPROVED", entity_type="CONTROLLED_DOCUMENT", entity_id=row.id, user_id=user.id, company_id=company_id, after={"status": row.status, "approved_by": user.id})
    db.commit()
    return {"id": row.id, "status": row.status, "approved_by": row.approved_by}


@router.get("/documents")
def list_documents(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "grc.read")
    rows = db.scalars(select(ControlledDocument).where(ControlledDocument.company_id == company_id).order_by(ControlledDocument.code, ControlledDocument.version.desc())).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "title_ar": row.title_ar,
            "title_en": row.title_en,
            "document_type": row.document_type,
            "version": row.version,
            "status": row.status,
            "effective_date": row.effective_date,
            "review_date": row.review_date,
        }
        for row in rows
    ]
