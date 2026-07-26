from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    CustomerQualityComplaint, Item, Party, QualityAction, QualityInspectionPlan,
    QualityManagementReview, QualityObjective, SupplierQualityEvaluation, User,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/qms", tags=["enterprise quality management"])


def _number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{count + 1:05d}"


def _party(db: Session, company_id: int, party_id: int | None, party_type: str | None = None) -> Party | None:
    if party_id is None:
        return None
    row = db.get(Party, party_id)
    if not row or row.company_id != company_id or (party_type and row.party_type != party_type):
        raise HTTPException(422, "Invalid company party")
    return row


def _item(db: Session, company_id: int, item_id: int | None) -> Item | None:
    if item_id is None:
        return None
    row = db.get(Item, item_id)
    if not row or row.company_id != company_id:
        raise HTTPException(422, "Invalid company item")
    return row


class ObjectiveIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=40)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    metric_name: str = Field(min_length=2, max_length=200)
    unit: str = "PERCENT"
    baseline_value: Decimal = Decimal("0")
    target_value: Decimal
    current_value: Decimal = Decimal("0")
    frequency: str = "MONTHLY"
    owner_user_id: int | None = None
    effective_from: date
    effective_to: date | None = None


class ObjectiveMeasureIn(BaseModel):
    current_value: Decimal


class InspectionPlanIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=40)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    item_id: int | None = None
    inspection_stage: str
    sampling_method: str = "FIXED"
    sample_size: Decimal = Field(gt=0)
    acceptance_number: int = Field(ge=0)
    rejection_number: int = Field(ge=1)
    specification: str | None = None
    test_method: str | None = None


class ActionIn(BaseModel):
    company_id: int
    action_type: str = "CORRECTIVE"
    source_type: str
    source_id: int
    title: str = Field(min_length=2, max_length=250)
    description: str = Field(min_length=2)
    root_cause_method: str = "5_WHY"
    root_cause: str | None = None
    owner_user_id: int
    due_date: date


class ActionVerifyIn(BaseModel):
    effectiveness_result: str
    effectiveness_notes: str = Field(min_length=2)


class ComplaintIn(BaseModel):
    company_id: int
    received_date: date
    customer_id: int | None = None
    item_id: int | None = None
    lot_number: str | None = None
    channel: str = "DIRECT"
    severity: str = "MEDIUM"
    description: str = Field(min_length=2)
    immediate_containment: str | None = None
    owner_user_id: int | None = None
    due_date: date | None = None


class ComplaintCloseIn(BaseModel):
    root_cause: str = Field(min_length=2)
    resolution: str = Field(min_length=2)


class SupplierEvaluationIn(BaseModel):
    company_id: int
    supplier_id: int
    period_start: date
    period_end: date
    quality_score: Decimal = Field(ge=0, le=100)
    delivery_score: Decimal = Field(ge=0, le=100)
    documentation_score: Decimal = Field(ge=0, le=100)
    notes: str | None = None


class ManagementReviewIn(BaseModel):
    company_id: int
    review_date: date
    scope: str = Field(min_length=2, max_length=250)
    inputs_summary: str = Field(min_length=2)
    decisions: str | None = None
    improvement_opportunities: str | None = None
    resource_needs: str | None = None


@router.post("/objectives", status_code=201)
def create_objective(data: ObjectiveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "quality.objectives")
    if data.effective_to and data.effective_to < data.effective_from:
        raise HTTPException(422, "Effective-to date precedes effective-from date")
    if db.scalar(select(QualityObjective.id).where(QualityObjective.company_id == data.company_id, QualityObjective.code == data.code.upper())):
        raise HTTPException(409, "Objective code already exists")
    row = QualityObjective(**data.model_dump(exclude={"code", "unit", "frequency"}), code=data.code.upper(), unit=data.unit.upper(), frequency=data.frequency.upper(), created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="QUALITY_OBJECTIVE_CREATED", entity_type="QUALITY_OBJECTIVE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "target": str(row.target_value)})
    db.commit(); return {"id": row.id, "code": row.code, "status": row.status}


@router.get("/objectives")
def list_objectives(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "quality.read")
    rows = db.scalars(select(QualityObjective).where(QualityObjective.company_id == company_id).order_by(QualityObjective.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "metric_name": r.metric_name, "unit": r.unit, "baseline_value": r.baseline_value, "target_value": r.target_value, "current_value": r.current_value, "frequency": r.frequency, "status": r.status, "approved": r.approved_by is not None} for r in rows]


@router.patch("/objectives/{objective_id}/measure")
def measure_objective(objective_id: int, data: ObjectiveMeasureIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(QualityObjective, objective_id)
    if not row: raise HTTPException(404, "Quality objective not found")
    ensure_permission(db, user, row.company_id, "quality.objectives")
    before = str(row.current_value); row.current_value = data.current_value
    write_audit(db, action="QUALITY_OBJECTIVE_MEASURED", entity_type="QUALITY_OBJECTIVE", entity_id=row.id, user_id=user.id, company_id=row.company_id, before={"current": before}, after={"current": str(row.current_value)})
    db.commit(); return {"id": row.id, "current_value": row.current_value}


@router.post("/objectives/{objective_id}/approve")
def approve_objective(objective_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(QualityObjective, objective_id)
    if not row: raise HTTPException(404, "Quality objective not found")
    ensure_permission(db, user, row.company_id, "quality.review")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker: creator cannot approve objective")
    row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="QUALITY_OBJECTIVE_APPROVED", entity_type="QUALITY_OBJECTIVE", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return {"id": row.id, "approved": True}


@router.post("/inspection-plans", status_code=201)
def create_plan(data: InspectionPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "quality.plans")
    _item(db, data.company_id, data.item_id)
    if data.rejection_number <= data.acceptance_number:
        raise HTTPException(422, "Rejection number must exceed acceptance number")
    row = QualityInspectionPlan(**data.model_dump(exclude={"code", "inspection_stage", "sampling_method"}), code=data.code.upper(), inspection_stage=data.inspection_stage.upper(), sampling_method=data.sampling_method.upper(), created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="INSPECTION_PLAN_CREATED", entity_type="QUALITY_INSPECTION_PLAN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"code": row.code, "stage": row.inspection_stage})
    db.commit(); return {"id": row.id, "code": row.code}


@router.get("/inspection-plans")
def list_plans(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "quality.read")
    rows = db.scalars(select(QualityInspectionPlan).where(QualityInspectionPlan.company_id == company_id).order_by(QualityInspectionPlan.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "item_code": r.item.code if r.item else None, "inspection_stage": r.inspection_stage, "sampling_method": r.sampling_method, "sample_size": r.sample_size, "acceptance_number": r.acceptance_number, "rejection_number": r.rejection_number, "approved": r.approved_by is not None, "active": r.active} for r in rows]


@router.post("/inspection-plans/{plan_id}/approve")
def approve_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(QualityInspectionPlan, plan_id)
    if not row: raise HTTPException(404, "Inspection plan not found")
    ensure_permission(db, user, row.company_id, "quality.review")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker: creator cannot approve plan")
    row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="INSPECTION_PLAN_APPROVED", entity_type="QUALITY_INSPECTION_PLAN", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return {"id": row.id, "approved": True}


@router.post("/actions", status_code=201)
def create_action(data: ActionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "quality.capa")
    if data.due_date < date.today(): raise HTTPException(422, "CAPA due date cannot be in the past")
    row = QualityAction(**data.model_dump(exclude={"action_type", "source_type", "root_cause_method"}), action_type=data.action_type.upper(), source_type=data.source_type.upper(), root_cause_method=data.root_cause_method.upper(), number=_number(db, QualityAction, data.company_id, "CAPA", date.today().year), created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="QUALITY_ACTION_CREATED", entity_type="QUALITY_ACTION", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"number": row.number, "due_date": str(row.due_date)})
    db.commit(); return {"id": row.id, "number": row.number, "status": row.status}


@router.get("/actions")
def list_actions(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "quality.read")
    rows = db.scalars(select(QualityAction).where(QualityAction.company_id == company_id).order_by(QualityAction.id.desc())).all()
    return [{"id": r.id, "number": r.number, "action_type": r.action_type, "source_type": r.source_type, "source_id": r.source_id, "title": r.title, "root_cause": r.root_cause, "due_date": r.due_date, "status": r.status, "effectiveness_result": r.effectiveness_result} for r in rows]


@router.post("/actions/{action_id}/verify")
def verify_action(action_id: int, data: ActionVerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(QualityAction, action_id)
    if not row: raise HTTPException(404, "Quality action not found")
    ensure_permission(db, user, row.company_id, "quality.review")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker: action creator cannot verify effectiveness")
    result = data.effectiveness_result.upper()
    if result not in {"EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE"}: raise HTTPException(422, "Invalid effectiveness result")
    row.effectiveness_result = result; row.effectiveness_notes = data.effectiveness_notes; row.verified_by = user.id; row.verified_at = utc_now(); row.status = "CLOSED" if result == "EFFECTIVE" else "REOPENED"
    write_audit(db, action="QUALITY_ACTION_EFFECTIVENESS_VERIFIED", entity_type="QUALITY_ACTION", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"result": result, "status": row.status})
    db.commit(); return {"id": row.id, "status": row.status, "effectiveness_result": result}


@router.post("/complaints", status_code=201)
def create_complaint(data: ComplaintIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "quality.complaints")
    _party(db, data.company_id, data.customer_id, "CUSTOMER")
    _item(db, data.company_id, data.item_id)
    row = CustomerQualityComplaint(**data.model_dump(exclude={"channel", "severity"}), channel=data.channel.upper(), severity=data.severity.upper(), number=_number(db, CustomerQualityComplaint, data.company_id, "QCOM", data.received_date.year), created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="QUALITY_COMPLAINT_CREATED", entity_type="QUALITY_COMPLAINT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"number": row.number, "severity": row.severity})
    db.commit(); return {"id": row.id, "number": row.number, "status": row.status}


@router.get("/complaints")
def list_complaints(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "quality.read")
    rows = db.scalars(select(CustomerQualityComplaint).where(CustomerQualityComplaint.company_id == company_id).order_by(CustomerQualityComplaint.received_date.desc())).all()
    return [{"id": r.id, "number": r.number, "received_date": r.received_date, "customer": r.customer.name_en if r.customer else None, "item": r.item.code if r.item else None, "lot_number": r.lot_number, "severity": r.severity, "description": r.description, "status": r.status, "due_date": r.due_date} for r in rows]


@router.post("/complaints/{complaint_id}/close")
def close_complaint(complaint_id: int, data: ComplaintCloseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CustomerQualityComplaint, complaint_id)
    if not row: raise HTTPException(404, "Complaint not found")
    ensure_permission(db, user, row.company_id, "quality.review")
    if row.created_by == user.id: raise HTTPException(409, "Maker-checker: complaint creator cannot close complaint")
    row.root_cause = data.root_cause; row.resolution = data.resolution; row.status = "CLOSED"; row.closed_by = user.id; row.closed_at = utc_now()
    write_audit(db, action="QUALITY_COMPLAINT_CLOSED", entity_type="QUALITY_COMPLAINT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/supplier-evaluations", status_code=201)
def evaluate_supplier(data: SupplierEvaluationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "quality.suppliers")
    _party(db, data.company_id, data.supplier_id, "SUPPLIER")
    if data.period_end < data.period_start: raise HTTPException(422, "Invalid evaluation period")
    overall = (data.quality_score * Decimal("0.50") + data.delivery_score * Decimal("0.30") + data.documentation_score * Decimal("0.20")).quantize(Decimal("0.01"))
    classification = "A" if overall >= 90 else "B" if overall >= 75 else "C" if overall >= 60 else "D"
    approved = classification != "D"
    row = SupplierQualityEvaluation(**data.model_dump(exclude={"quality_score", "delivery_score", "documentation_score"}), quality_score=data.quality_score, delivery_score=data.delivery_score, documentation_score=data.documentation_score, overall_score=overall, classification=classification, approved=approved, evaluated_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="SUPPLIER_QUALITY_EVALUATED", entity_type="SUPPLIER_QUALITY_EVALUATION", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"overall": str(overall), "classification": classification, "approved": approved})
    db.commit(); return {"id": row.id, "overall_score": overall, "classification": classification, "approved": approved}


@router.get("/supplier-evaluations")
def list_supplier_evaluations(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "quality.read")
    rows = db.scalars(select(SupplierQualityEvaluation).where(SupplierQualityEvaluation.company_id == company_id).order_by(SupplierQualityEvaluation.period_end.desc())).all()
    return [{"id": r.id, "supplier": r.supplier.name_en, "period_start": r.period_start, "period_end": r.period_end, "quality_score": r.quality_score, "delivery_score": r.delivery_score, "documentation_score": r.documentation_score, "overall_score": r.overall_score, "classification": r.classification, "approved": r.approved} for r in rows]


@router.post("/management-reviews", status_code=201)
def create_management_review(data: ManagementReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "quality.review")
    row = QualityManagementReview(**data.model_dump(), number=_number(db, QualityManagementReview, data.company_id, "QMR", data.review_date.year), prepared_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="QUALITY_MANAGEMENT_REVIEW_CREATED", entity_type="QUALITY_MANAGEMENT_REVIEW", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"number": row.number, "scope": row.scope})
    db.commit(); return {"id": row.id, "number": row.number, "status": row.status}


@router.get("/management-reviews")
def list_management_reviews(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "quality.read")
    rows = db.scalars(select(QualityManagementReview).where(QualityManagementReview.company_id == company_id).order_by(QualityManagementReview.review_date.desc())).all()
    return [{"id": r.id, "number": r.number, "review_date": r.review_date, "scope": r.scope, "status": r.status, "approved": r.approved_by is not None} for r in rows]


@router.post("/management-reviews/{review_id}/approve")
def approve_management_review(review_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(QualityManagementReview, review_id)
    if not row: raise HTTPException(404, "Management review not found")
    ensure_permission(db, user, row.company_id, "quality.review")
    if row.prepared_by == user.id: raise HTTPException(409, "Maker-checker: preparer cannot approve management review")
    if not row.decisions: raise HTTPException(422, "Management decisions must be documented before approval")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="QUALITY_MANAGEMENT_REVIEW_APPROVED", entity_type="QUALITY_MANAGEMENT_REVIEW", entity_id=row.id, user_id=user.id, company_id=row.company_id)
    db.commit(); return {"id": row.id, "status": row.status}


@router.get("/dashboard")
def qms_dashboard(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "quality.read")
    objectives = db.scalars(select(QualityObjective).where(QualityObjective.company_id == company_id, QualityObjective.status == "ACTIVE")).all()
    actions = db.scalars(select(QualityAction).where(QualityAction.company_id == company_id)).all()
    complaints = db.scalars(select(CustomerQualityComplaint).where(CustomerQualityComplaint.company_id == company_id)).all()
    supplier_evals = db.scalars(select(SupplierQualityEvaluation).where(SupplierQualityEvaluation.company_id == company_id)).all()
    today = date.today()
    achieved = sum(1 for r in objectives if Decimal(r.current_value) >= Decimal(r.target_value))
    overdue_actions = sum(1 for r in actions if r.status not in {"CLOSED", "CANCELLED"} and r.due_date < today)
    open_complaints = sum(1 for r in complaints if r.status != "CLOSED")
    avg_supplier = (sum((Decimal(r.overall_score) for r in supplier_evals), Decimal("0")) / len(supplier_evals)).quantize(Decimal("0.01")) if supplier_evals else Decimal("0")
    return {
        "active_objectives": len(objectives),
        "objectives_achieved": achieved,
        "objective_achievement_rate": (Decimal(achieved) / Decimal(len(objectives)) * 100).quantize(Decimal("0.01")) if objectives else Decimal("0"),
        "open_actions": sum(1 for r in actions if r.status not in {"CLOSED", "CANCELLED"}),
        "overdue_actions": overdue_actions,
        "open_complaints": open_complaints,
        "supplier_quality_average": avg_supplier,
        "management_reviews": db.scalar(select(func.count(QualityManagementReview.id)).where(QualityManagementReview.company_id == company_id)) or 0,
        "iso9001_core_controls": {
            "objectives": True,
            "inspection_plans": True,
            "nonconformity_capa": True,
            "customer_complaints": True,
            "supplier_evaluation": True,
            "management_review": True,
            "controlled_documents": True,
            "internal_audit": True,
        },
    }
