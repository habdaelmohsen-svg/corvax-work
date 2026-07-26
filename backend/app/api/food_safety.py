from __future__ import annotations

import json
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
    CertificateOfAnalysis, HACCPHazard, HACCPMonitoringLog, HACCPPlan, Item,
    ProductRecall, ProductRecallLine, QualityAction, User,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/food-safety", tags=["food safety and HACCP"])


def _number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{count + 1:05d}"


def _item(db: Session, company_id: int, item_id: int) -> Item:
    row = db.get(Item, item_id)
    if not row or row.company_id != company_id:
        raise HTTPException(422, "Invalid company item")
    return row


class HACCPPlanIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=40)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    product_item_id: int | None = None
    process_scope: str = Field(min_length=5)
    intended_use: str | None = None
    target_consumer: str | None = None
    version: int = Field(default=1, ge=1)
    effective_from: date


class HazardIn(BaseModel):
    step_number: int = Field(ge=1)
    process_step: str = Field(min_length=2, max_length=250)
    hazard_type: str
    hazard_description: str = Field(min_length=5)
    likelihood: int = Field(ge=1, le=5)
    severity: int = Field(ge=1, le=5)
    preventive_controls: str = Field(min_length=3)
    is_ccp: bool = False
    critical_limit: str | None = None
    monitoring_method: str | None = None
    monitoring_frequency: str | None = None
    corrective_action: str | None = None
    verification_method: str | None = None
    records_required: str | None = None


class MonitoringIn(BaseModel):
    measured_value: str = Field(min_length=1, max_length=100)
    within_critical_limit: bool
    deviation_details: str | None = None
    immediate_correction: str | None = None


class MonitoringVerifyIn(BaseModel):
    accepted: bool
    notes: str | None = None


class COATestResult(BaseModel):
    test: str
    specification: str
    result: str
    status: str


class COAIn(BaseModel):
    company_id: int
    item_id: int
    lot_number: str = Field(min_length=1, max_length=80)
    issue_date: date
    expiry_date: date | None = None
    specification_version: str = Field(min_length=1, max_length=50)
    test_results: list[COATestResult] = Field(min_length=1)
    remarks: str | None = None


class RecallIn(BaseModel):
    company_id: int
    recall_date: date
    recall_class: str
    item_id: int
    lot_number: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=5)
    scope: str = Field(min_length=5)
    quantity_distributed: Decimal = Field(gt=0)


class RecallLineIn(BaseModel):
    party_id: int | None = None
    location: str = Field(min_length=2, max_length=250)
    quantity_distributed: Decimal = Field(ge=0)
    quantity_recovered: Decimal = Field(default=Decimal("0"), ge=0)
    contact_status: str = "PENDING"
    evidence_reference: str | None = None


class RecallRecoveryIn(BaseModel):
    quantity_recovered: Decimal = Field(ge=0)
    contact_status: str
    evidence_reference: str | None = None


class RecallCloseIn(BaseModel):
    quantity_disposed: Decimal = Field(default=Decimal("0"), ge=0)


@router.post("/haccp-plans", status_code=201)
def create_haccp_plan(data: HACCPPlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "food_safety.manage")
    if data.product_item_id:
        _item(db, data.company_id, data.product_item_id)
    if db.scalar(select(HACCPPlan.id).where(HACCPPlan.company_id == data.company_id, HACCPPlan.code == data.code)):
        raise HTTPException(409, "HACCP plan code already exists")
    row = HACCPPlan(**data.model_dump(), status="DRAFT", prepared_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="HACCP_PLAN_CREATED", entity_type="HACCP_PLAN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"code": row.code, "version": row.version})
    db.commit()
    return {"id": row.id, "code": row.code, "status": row.status}


@router.post("/haccp-plans/{plan_id}/hazards", status_code=201)
def add_haccp_hazard(plan_id: int, data: HazardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.get(HACCPPlan, plan_id)
    if not plan: raise HTTPException(404, "HACCP plan not found")
    ensure_permission(db, user, plan.company_id, "food_safety.manage")
    if plan.status != "DRAFT": raise HTTPException(409, "Only draft HACCP plans can be edited")
    hazard_type = data.hazard_type.upper()
    if hazard_type not in {"BIOLOGICAL", "CHEMICAL", "PHYSICAL", "ALLERGEN", "RADIOLOGICAL"}:
        raise HTTPException(422, "Invalid hazard type")
    if data.is_ccp and not all([data.critical_limit, data.monitoring_method, data.monitoring_frequency, data.corrective_action, data.verification_method]):
        raise HTTPException(422, "CCP requires critical limit, monitoring, correction and verification")
    risk_score = data.likelihood * data.severity
    row = HACCPHazard(**data.model_dump(exclude={"hazard_type", "likelihood", "severity"}), plan_id=plan.id, hazard_type=hazard_type, likelihood=data.likelihood, severity=data.severity, risk_score=risk_score, significant=risk_score >= 12 or data.is_ccp)
    db.add(row); db.flush()
    write_audit(db, action="HACCP_HAZARD_ADDED", entity_type="HACCP_HAZARD", entity_id=row.id, user_id=user.id, company_id=plan.company_id, after={"risk_score": risk_score, "ccp": row.is_ccp})
    db.commit()
    return {"id": row.id, "risk_score": row.risk_score, "significant": row.significant, "is_ccp": row.is_ccp}


@router.post("/haccp-plans/{plan_id}/approve")
def approve_haccp_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.get(HACCPPlan, plan_id)
    if not plan: raise HTTPException(404, "HACCP plan not found")
    ensure_permission(db, user, plan.company_id, "food_safety.approve")
    if plan.prepared_by == user.id: raise HTTPException(409, "Maker-checker: plan preparer cannot approve")
    hazards = db.scalars(select(HACCPHazard).where(HACCPHazard.plan_id == plan.id, HACCPHazard.active.is_(True))).all()
    if not hazards: raise HTTPException(422, "HACCP plan requires at least one hazard analysis")
    if not any(h.is_ccp for h in hazards): raise HTTPException(422, "HACCP plan requires at least one documented CCP")
    plan.status = "APPROVED"; plan.approved_by = user.id; plan.approved_at = utc_now()
    write_audit(db, action="HACCP_PLAN_APPROVED", entity_type="HACCP_PLAN", entity_id=plan.id, user_id=user.id, company_id=plan.company_id)
    db.commit(); return {"id": plan.id, "status": plan.status}


@router.get("/haccp-plans")
def list_haccp_plans(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "food_safety.read")
    rows = db.scalars(select(HACCPPlan).where(HACCPPlan.company_id == company_id).order_by(HACCPPlan.created_at.desc())).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "item": r.product_item.code if r.product_item else None, "version": r.version, "status": r.status, "hazards": len(r.hazards), "ccps": sum(1 for h in r.hazards if h.is_ccp)} for r in rows]


@router.post("/haccp-hazards/{hazard_id}/monitor", status_code=201)
def record_ccp_monitoring(hazard_id: int, data: MonitoringIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hazard = db.get(HACCPHazard, hazard_id)
    if not hazard: raise HTTPException(404, "HACCP hazard not found")
    plan = db.get(HACCPPlan, hazard.plan_id)
    ensure_permission(db, user, plan.company_id, "food_safety.manage")
    if plan.status != "APPROVED" or not hazard.is_ccp: raise HTTPException(409, "Monitoring is allowed only for approved CCPs")
    if not data.within_critical_limit and not data.immediate_correction:
        raise HTTPException(422, "CCP deviation requires immediate correction")
    row = HACCPMonitoringLog(company_id=plan.company_id, hazard_id=hazard.id, measured_value=data.measured_value, within_critical_limit=data.within_critical_limit, deviation_details=data.deviation_details, immediate_correction=data.immediate_correction, status="RECORDED" if data.within_critical_limit else "DEVIATION_OPEN", recorded_by=user.id)
    db.add(row); db.flush()
    if not data.within_critical_limit:
        count = db.scalar(select(func.count(QualityAction.id)).where(QualityAction.company_id == plan.company_id)) or 0
        action = QualityAction(company_id=plan.company_id, number=f"CAPA-{plan.company_id}-{date.today().year}-{count + 1:05d}", action_type="CORRECTIVE", source_type="HACCP_DEVIATION", source_id=row.id, title=f"CCP deviation at {hazard.process_step}", description=data.deviation_details or "Critical limit deviation", root_cause_method="5_WHY", owner_user_id=user.id, due_date=date.today(), status="OPEN", created_by=user.id)
        db.add(action); db.flush(); row.corrective_action_id = action.id
    write_audit(db, action="HACCP_CCP_MONITORED", entity_type="HACCP_MONITORING", entity_id=row.id, user_id=user.id, company_id=plan.company_id, after={"within_limit": row.within_critical_limit, "status": row.status, "capa_id": row.corrective_action_id})
    db.commit(); return {"id": row.id, "status": row.status, "corrective_action_id": row.corrective_action_id}


@router.post("/haccp-monitoring/{log_id}/verify")
def verify_monitoring(log_id: int, data: MonitoringVerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(HACCPMonitoringLog, log_id)
    if not row: raise HTTPException(404, "Monitoring log not found")
    ensure_permission(db, user, row.company_id, "food_safety.approve")
    if row.recorded_by == user.id: raise HTTPException(409, "Maker-checker: recorder cannot verify")
    if not data.accepted: row.status = "REJECTED"
    elif row.within_critical_limit: row.status = "VERIFIED"
    else: row.status = "DEVIATION_VERIFIED"
    row.verified_by = user.id; row.verified_at = utc_now()
    write_audit(db, action="HACCP_MONITORING_VERIFIED", entity_type="HACCP_MONITORING", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status, "notes": data.notes})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/coa", status_code=201)
def create_coa(data: COAIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "food_safety.manage")
    _item(db, data.company_id, data.item_id)
    if data.expiry_date and data.expiry_date < data.issue_date: raise HTTPException(422, "Expiry date cannot precede issue date")
    results = [r.model_dump() for r in data.test_results]
    conclusion = "PASS" if all(str(r["status"]).upper() == "PASS" for r in results) else "FAIL"
    row = CertificateOfAnalysis(company_id=data.company_id, number=_number(db, CertificateOfAnalysis, data.company_id, "COA", data.issue_date.year), item_id=data.item_id, lot_number=data.lot_number, issue_date=data.issue_date, expiry_date=data.expiry_date, specification_version=data.specification_version, test_results_json=json.dumps(results, ensure_ascii=False), conclusion=conclusion, remarks=data.remarks, status="DRAFT", prepared_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="COA_CREATED", entity_type="CERTIFICATE_OF_ANALYSIS", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"number": row.number, "conclusion": row.conclusion})
    db.commit(); return {"id": row.id, "number": row.number, "conclusion": row.conclusion, "status": row.status}


@router.post("/coa/{coa_id}/approve")
def approve_coa(coa_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CertificateOfAnalysis, coa_id)
    if not row: raise HTTPException(404, "COA not found")
    ensure_permission(db, user, row.company_id, "food_safety.approve")
    if row.prepared_by == user.id: raise HTTPException(409, "Maker-checker: COA preparer cannot approve")
    row.status = "RELEASED" if row.conclusion == "PASS" else "REJECTED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="COA_APPROVED", entity_type="CERTIFICATE_OF_ANALYSIS", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit(); return {"id": row.id, "status": row.status, "conclusion": row.conclusion}


@router.get("/coa")
def list_coa(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "food_safety.read")
    rows = db.scalars(select(CertificateOfAnalysis).where(CertificateOfAnalysis.company_id == company_id).order_by(CertificateOfAnalysis.issue_date.desc())).all()
    return [{"id": r.id, "number": r.number, "item": r.item.code, "lot_number": r.lot_number, "issue_date": r.issue_date, "specification_version": r.specification_version, "conclusion": r.conclusion, "status": r.status} for r in rows]


@router.post("/recalls", status_code=201)
def create_recall(data: RecallIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "food_safety.manage")
    _item(db, data.company_id, data.item_id)
    recall_class = data.recall_class.upper()
    if recall_class not in {"CLASS_I", "CLASS_II", "CLASS_III", "MARKET_WITHDRAWAL"}: raise HTTPException(422, "Invalid recall class")
    row = ProductRecall(**data.model_dump(exclude={"recall_class"}), recall_class=recall_class, number=_number(db, ProductRecall, data.company_id, "RCL", data.recall_date.year), status="DRAFT", initiated_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="PRODUCT_RECALL_CREATED", entity_type="PRODUCT_RECALL", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"number": row.number, "class": row.recall_class, "lot": row.lot_number})
    db.commit(); return {"id": row.id, "number": row.number, "status": row.status}


@router.post("/recalls/{recall_id}/lines", status_code=201)
def add_recall_line(recall_id: int, data: RecallLineIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recall = db.get(ProductRecall, recall_id)
    if not recall: raise HTTPException(404, "Recall not found")
    ensure_permission(db, user, recall.company_id, "food_safety.manage")
    if recall.status not in {"DRAFT", "ACTIVE"}: raise HTTPException(409, "Recall cannot be updated")
    if data.quantity_recovered > data.quantity_distributed: raise HTTPException(422, "Recovered quantity cannot exceed distributed quantity")
    row = ProductRecallLine(recall_id=recall.id, **data.model_dump(exclude={"contact_status"}), contact_status=data.contact_status.upper(), updated_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="PRODUCT_RECALL_LINE_ADDED", entity_type="PRODUCT_RECALL_LINE", entity_id=row.id, user_id=user.id, company_id=recall.company_id, after={"location": row.location, "distributed": str(row.quantity_distributed)})
    db.commit(); return {"id": row.id, "contact_status": row.contact_status}


@router.post("/recalls/{recall_id}/approve")
def approve_recall(recall_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recall = db.get(ProductRecall, recall_id)
    if not recall: raise HTTPException(404, "Recall not found")
    ensure_permission(db, user, recall.company_id, "food_safety.approve")
    if recall.initiated_by == user.id: raise HTTPException(409, "Maker-checker: recall initiator cannot approve")
    lines = db.scalars(select(ProductRecallLine).where(ProductRecallLine.recall_id == recall.id)).all()
    if not lines: raise HTTPException(422, "Recall distribution list is required")
    distributed = sum((Decimal(r.quantity_distributed) for r in lines), Decimal("0"))
    if distributed <= 0: raise HTTPException(422, "Recall distribution quantity must be positive")
    recall.quantity_distributed = distributed; recall.status = "ACTIVE"; recall.approved_by = user.id; recall.approved_at = utc_now()
    write_audit(db, action="PRODUCT_RECALL_APPROVED", entity_type="PRODUCT_RECALL", entity_id=recall.id, user_id=user.id, company_id=recall.company_id, after={"status": recall.status, "distributed": str(distributed)})
    db.commit(); return {"id": recall.id, "status": recall.status, "quantity_distributed": recall.quantity_distributed}


@router.post("/recall-lines/{line_id}/recovery")
def update_recovery(line_id: int, data: RecallRecoveryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    line = db.get(ProductRecallLine, line_id)
    if not line: raise HTTPException(404, "Recall line not found")
    recall = db.get(ProductRecall, line.recall_id)
    ensure_permission(db, user, recall.company_id, "food_safety.manage")
    if recall.status != "ACTIVE": raise HTTPException(409, "Recall is not active")
    if data.quantity_recovered > Decimal(line.quantity_distributed): raise HTTPException(422, "Recovered quantity cannot exceed distributed quantity")
    line.quantity_recovered = data.quantity_recovered; line.contact_status = data.contact_status.upper(); line.evidence_reference = data.evidence_reference; line.updated_by = user.id; line.updated_at = utc_now()
    lines = db.scalars(select(ProductRecallLine).where(ProductRecallLine.recall_id == recall.id)).all()
    recall.quantity_recovered = sum((Decimal(r.quantity_recovered) for r in lines), Decimal("0"))
    recall.effectiveness_percent = (recall.quantity_recovered / recall.quantity_distributed * 100).quantize(Decimal("0.01")) if recall.quantity_distributed else Decimal("0")
    write_audit(db, action="PRODUCT_RECALL_RECOVERY_UPDATED", entity_type="PRODUCT_RECALL_LINE", entity_id=line.id, user_id=user.id, company_id=recall.company_id, after={"recovered": str(line.quantity_recovered), "effectiveness": str(recall.effectiveness_percent)})
    db.commit(); return {"line_id": line.id, "quantity_recovered": line.quantity_recovered, "recall_effectiveness_percent": recall.effectiveness_percent}


@router.post("/recalls/{recall_id}/close")
def close_recall(recall_id: int, data: RecallCloseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recall = db.get(ProductRecall, recall_id)
    if not recall: raise HTTPException(404, "Recall not found")
    ensure_permission(db, user, recall.company_id, "food_safety.approve")
    if recall.status != "ACTIVE": raise HTTPException(409, "Only active recall can be closed")
    lines = db.scalars(select(ProductRecallLine).where(ProductRecallLine.recall_id == recall.id)).all()
    if any(r.contact_status == "PENDING" for r in lines): raise HTTPException(422, "All recall locations must be contacted")
    if Decimal(recall.effectiveness_percent) < Decimal("95"):
        raise HTTPException(422, "Recall effectiveness must reach at least 95% before closure")
    if data.quantity_disposed > Decimal(recall.quantity_recovered): raise HTTPException(422, "Disposed quantity cannot exceed recovered quantity")
    recall.quantity_disposed = data.quantity_disposed; recall.status = "CLOSED"; recall.closed_by = user.id; recall.closed_at = utc_now()
    write_audit(db, action="PRODUCT_RECALL_CLOSED", entity_type="PRODUCT_RECALL", entity_id=recall.id, user_id=user.id, company_id=recall.company_id, after={"effectiveness": str(recall.effectiveness_percent), "disposed": str(recall.quantity_disposed)})
    db.commit(); return {"id": recall.id, "status": recall.status, "effectiveness_percent": recall.effectiveness_percent}


@router.get("/recalls")
def list_recalls(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "food_safety.read")
    rows = db.scalars(select(ProductRecall).where(ProductRecall.company_id == company_id).order_by(ProductRecall.recall_date.desc())).all()
    return [{"id": r.id, "number": r.number, "recall_date": r.recall_date, "class": r.recall_class, "item": r.item.code, "lot_number": r.lot_number, "distributed": r.quantity_distributed, "recovered": r.quantity_recovered, "effectiveness_percent": r.effectiveness_percent, "status": r.status} for r in rows]


@router.get("/dashboard")
def food_safety_dashboard(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "food_safety.read")
    approved_plans = db.scalar(select(func.count(HACCPPlan.id)).where(HACCPPlan.company_id == company_id, HACCPPlan.status == "APPROVED")) or 0
    open_deviations = db.scalar(select(func.count(HACCPMonitoringLog.id)).where(HACCPMonitoringLog.company_id == company_id, HACCPMonitoringLog.status.in_(["DEVIATION_OPEN", "DEVIATION_VERIFIED"]))) or 0
    active_recalls = db.scalar(select(func.count(ProductRecall.id)).where(ProductRecall.company_id == company_id, ProductRecall.status == "ACTIVE")) or 0
    released_coa = db.scalar(select(func.count(CertificateOfAnalysis.id)).where(CertificateOfAnalysis.company_id == company_id, CertificateOfAnalysis.status == "RELEASED")) or 0
    return {"approved_haccp_plans": approved_plans, "open_ccp_deviations": open_deviations, "active_recalls": active_recalls, "released_coa": released_coa, "iso22000_haccp_core": {"hazard_analysis": True, "ccp_monitoring": True, "deviation_capa": True, "coa_release": True, "traceability_recall": True}}
