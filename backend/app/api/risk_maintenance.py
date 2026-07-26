from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import get_current_user, ensure_permission
from app.models.entities import (
    User, CreditRiskPortfolio, CreditRiskBucket, CreditExposure, EclRun, EclRunLine,
    MaintenanceAsset, MaintenanceWorkOrder, MaintenancePlan, MaintenanceSparePart,
    MaintenanceWorkOrderPart, CalibrationRecord,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/risk-maintenance", tags=["IFRS 9 & Maintenance"])
Q = Decimal("0.01")


class PortfolioIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    method: str = "SIMPLIFIED"
    business_model: str = "HOLD_TO_COLLECT"
    sicr_days_past_due: int = Field(default=30, ge=1)
    default_days_past_due: int = Field(default=90, ge=30)
    pd_sicr_multiplier: Decimal = Field(default=Decimal("2"), ge=1)
    forward_looking_overlay: Decimal = Field(default=Decimal("1"), gt=0)
    model_version: str = "1.0"
    buckets: list[dict] = []

    @model_validator(mode="after")
    def validate_method(self):
        self.method = self.method.upper()
        self.business_model = self.business_model.upper()
        if self.method not in {"SIMPLIFIED", "GENERAL"}:
            raise ValueError("method must be SIMPLIFIED or GENERAL")
        if self.method == "SIMPLIFIED" and not self.buckets:
            raise ValueError("At least one ageing bucket is required for the simplified approach")
        if self.default_days_past_due <= self.sicr_days_past_due:
            raise ValueError("default_days_past_due must exceed sicr_days_past_due")
        return self


class ExposureIn(BaseModel):
    company_id: int
    portfolio_id: int
    reference: str
    customer_name: str
    instrument_type: str = "TRADE_RECEIVABLE"
    origination_date: date | None = None
    due_date: date
    maturity_date: date | None = None
    gross_amount: Decimal = Field(gt=0)
    carrying_amount: Decimal = Field(gt=0)
    undrawn_commitment: Decimal = Field(default=Decimal("0"), ge=0)
    credit_conversion_factor: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    effective_interest_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    initial_12m_pd: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    current_12m_pd: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    lifetime_pd: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    lgd: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    collateral_value: Decimal = Field(default=Decimal("0"), ge=0)
    credit_rating: str | None = None
    business_model: str = "HOLD_TO_COLLECT"
    sppi_passed: bool = True
    significant_increase_in_credit_risk: bool = False
    default_flag: bool = False
    forbearance_flag: bool = False
    stage_override: int | None = Field(default=None, ge=1, le=3)
    stage_reason: str | None = None


class EclIn(BaseModel):
    company_id: int
    portfolio_id: int
    as_of_date: date
    expense_account_code: Optional[str] = None
    allowance_account_code: Optional[str] = None
    post_journal: bool = False  # legacy simplified-only compatibility


class AssetIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    production_line: str | None = None
    criticality: str = "MEDIUM"


class WorkOrderIn(BaseModel):
    company_id: int
    asset_id: int
    work_type: str
    priority: str = "MEDIUM"
    description: str


class CompleteWorkOrderIn(BaseModel):
    downtime_minutes: int = Field(ge=0)
    labor_cost: Decimal = Field(ge=0)
    parts_cost: Decimal = Field(ge=0)


class MaintenancePlanIn(BaseModel):
    company_id: int
    asset_id: int
    code: str
    description: str
    interval_days: int | None = Field(default=None, gt=0)
    meter_interval: Decimal | None = Field(default=None, gt=0)
    next_due_date: date | None = None
    next_due_meter: Decimal | None = None
    priority: str = "MEDIUM"


class SparePartIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    unit: str = "EA"
    quantity_on_hand: Decimal = Field(ge=0)
    reorder_level: Decimal = Field(ge=0)
    average_cost: Decimal = Field(ge=0)


class IssuePartIn(BaseModel):
    spare_part_id: int
    quantity: Decimal = Field(gt=0)


class CalibrationIn(BaseModel):
    company_id: int
    asset_id: int
    instrument_code: str
    calibration_date: date
    next_due_date: date
    result: str
    certificate_reference: str | None = None
    notes: str | None = None


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()).hexdigest()


def _stage_for(portfolio: CreditRiskPortfolio, exp: CreditExposure, dpd: int) -> tuple[int, str]:
    if exp.stage_override in {1, 2, 3}:
        return int(exp.stage_override), exp.stage_reason or "MANUAL_OVERRIDE"
    if exp.default_flag or dpd >= portfolio.default_days_past_due:
        return 3, "DEFAULT_OR_90_DPD_BACKSTOP"
    pd_deterioration = (
        Decimal(exp.initial_12m_pd or 0) > 0
        and Decimal(exp.current_12m_pd or 0) >= Decimal(exp.initial_12m_pd) * Decimal(portfolio.pd_sicr_multiplier or 2)
    )
    if exp.significant_increase_in_credit_risk or exp.forbearance_flag or dpd >= portfolio.sicr_days_past_due or pd_deterioration:
        return 2, "SICR_OR_30_DPD_BACKSTOP"
    return 1, "PERFORMING"


def _discount_factor(exp: CreditExposure, as_of_date: date) -> Decimal:
    maturity = exp.maturity_date or exp.due_date
    days = max((maturity - as_of_date).days, 0)
    years = Decimal(days) / Decimal("365")
    rate = Decimal(exp.effective_interest_rate or 0)
    if rate <= 0 or years <= 0:
        return Decimal("1")
    return Decimal(str(1 / ((1 + float(rate)) ** float(years))))


def _fixed(value, pattern: str) -> str:
    return format(Decimal(value or 0).quantize(Decimal(pattern)), "f")


def _run_hash(run: EclRun, lines: list[EclRunLine]) -> str:
    return _canonical_hash({
        "company_id": run.company_id, "portfolio_id": run.portfolio_id, "as_of_date": run.as_of_date,
        "approach": run.approach, "model_version": run.model_version,
        "lines": [{"exposure_id": x.exposure_id, "stage": x.stage, "dpd": x.days_past_due,
                   "pd": _fixed(x.pd_rate, "0.000001"), "lgd": _fixed(x.lgd_rate, "0.000001"),
                   "ead": _fixed(x.ead_amount, "0.01"), "discount": _fixed(x.discount_factor, "0.0000000001"),
                   "overlay": _fixed(x.forward_factor, "0.000001"), "ecl": _fixed(x.ecl_amount, "0.01")}
                  for x in sorted(lines, key=lambda row: row.exposure_id)],
    })


@router.post("/ifrs9/portfolios", status_code=201)
def create_portfolio(data: PortfolioIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.manage_ifrs9")
    p = CreditRiskPortfolio(
        company_id=data.company_id, code=data.code, name_ar=data.name_ar, name_en=data.name_en,
        method=data.method, business_model=data.business_model, sicr_days_past_due=data.sicr_days_past_due,
        default_days_past_due=data.default_days_past_due, pd_sicr_multiplier=data.pd_sicr_multiplier,
        forward_looking_overlay=data.forward_looking_overlay, model_version=data.model_version,
        status="APPROVED" if data.method == "SIMPLIFIED" else "READY_FOR_REVIEW", created_by=user.id,
        approved_by=user.id if data.method == "SIMPLIFIED" else None,
        approved_at=utc_now() if data.method == "SIMPLIFIED" else None,
    )
    db.add(p); db.flush()
    for b in data.buckets:
        db.add(CreditRiskBucket(portfolio_id=p.id, min_days=int(b["min_days"]), max_days=b.get("max_days"),
                                loss_rate=Decimal(str(b["loss_rate"])),
                                forward_factor=Decimal(str(b.get("forward_factor", 1)))))
    write_audit(db, action="IFRS9_PORTFOLIO_CREATED", entity_type="CREDIT_RISK_PORTFOLIO",
                entity_id=p.id, user_id=user.id, company_id=data.company_id,
                after={"code": data.code, "method": data.method, "status": p.status})
    db.commit()
    return {"id": p.id, "code": p.code, "method": p.method, "status": p.status}


@router.post("/ifrs9/portfolios/{portfolio_id}/review")
def review_portfolio(portfolio_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(CreditRiskPortfolio, portfolio_id)
    if not p: raise HTTPException(404, "Portfolio not found")
    ensure_permission(db, user, p.company_id, "finance.manage_ifrs9")
    if p.status != "READY_FOR_REVIEW": raise HTTPException(422, "Portfolio is not ready for review")
    if p.created_by == user.id: raise HTTPException(409, "Preparer cannot review the model")
    p.status = "REVIEWED"; p.reviewed_by = user.id; p.reviewed_at = utc_now()
    write_audit(db, action="IFRS9_PORTFOLIO_REVIEWED", entity_type="CREDIT_RISK_PORTFOLIO", entity_id=p.id,
                user_id=user.id, company_id=p.company_id, after={"status": p.status})
    db.commit(); return {"id": p.id, "status": p.status}


@router.post("/ifrs9/portfolios/{portfolio_id}/approve")
def approve_portfolio(portfolio_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(CreditRiskPortfolio, portfolio_id)
    if not p: raise HTTPException(404, "Portfolio not found")
    ensure_permission(db, user, p.company_id, "finance.manage_ifrs9")
    if p.status != "REVIEWED": raise HTTPException(422, "Portfolio must be reviewed first")
    if user.id in {p.created_by, p.reviewed_by}: raise HTTPException(409, "Final approver must be independent")
    p.status = "APPROVED"; p.approved_by = user.id; p.approved_at = utc_now()
    write_audit(db, action="IFRS9_PORTFOLIO_APPROVED", entity_type="CREDIT_RISK_PORTFOLIO", entity_id=p.id,
                user_id=user.id, company_id=p.company_id, after={"status": p.status})
    db.commit(); return {"id": p.id, "status": p.status}


@router.post("/ifrs9/exposures", status_code=201)
def create_exposure(data: ExposureIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.manage_ifrs9")
    p = db.get(CreditRiskPortfolio, data.portfolio_id)
    if not p or p.company_id != data.company_id:
        raise HTTPException(404, "Portfolio not found")
    if p.method == "GENERAL" and not data.sppi_passed:
        raise HTTPException(422, "Instrument fails SPPI and is outside amortised-cost ECL processing")
    row = CreditExposure(**data.model_dump())
    row.instrument_type = row.instrument_type.upper(); row.business_model = row.business_model.upper()
    db.add(row); db.flush()
    write_audit(db, action="IFRS9_EXPOSURE_CREATED", entity_type="CREDIT_EXPOSURE", entity_id=row.id,
                user_id=user.id, company_id=data.company_id,
                after={"reference": data.reference, "instrument_type": row.instrument_type, "sppi_passed": row.sppi_passed})
    db.commit()
    return {"id": row.id, "reference": row.reference}


@router.post("/ifrs9/runs", status_code=201)
def calculate_ecl(data: EclIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.manage_ifrs9")
    portfolio = db.get(CreditRiskPortfolio, data.portfolio_id)
    if not portfolio or portfolio.company_id != data.company_id:
        raise HTTPException(404, "Portfolio not found")
    if portfolio.status != "APPROVED":
        raise HTTPException(422, "Credit risk model must be independently approved")
    buckets = db.scalars(select(CreditRiskBucket).where(CreditRiskBucket.portfolio_id == data.portfolio_id)
                         .order_by(CreditRiskBucket.min_days)).all()
    exposures = db.scalars(select(CreditExposure).where(
        CreditExposure.company_id == data.company_id,
        CreditExposure.portfolio_id == data.portfolio_id,
        CreditExposure.status == "OPEN")).all()
    if not exposures or (portfolio.method == "SIMPLIFIED" and not buckets):
        raise HTTPException(422, "Portfolio exposures or buckets are missing")
    run = EclRun(company_id=data.company_id, portfolio_id=data.portfolio_id, as_of_date=data.as_of_date,
                 approach=portfolio.method, model_version=portfolio.model_version,
                 expense_account_code=data.expense_account_code, allowance_account_code=data.allowance_account_code,
                 created_by=user.id, status="READY_FOR_REVIEW")
    db.add(run); db.flush()
    total_exp = Decimal("0"); total_ecl = Decimal("0")
    stage_totals = {1: Decimal("0"), 2: Decimal("0"), 3: Decimal("0")}
    lines: list[EclRunLine] = []
    for exp in exposures:
        dpd = max((data.as_of_date - exp.due_date).days, 0)
        exposure = Decimal(exp.carrying_amount)
        if portfolio.method == "SIMPLIFIED":
            bucket = next((b for b in buckets if dpd >= b.min_days and (b.max_days is None or dpd <= b.max_days)), None)
            if not bucket: raise HTTPException(422, f"No ageing bucket for {dpd} days")
            stage, reason = 2, "SIMPLIFIED_LIFETIME_ECL"
            rate = Decimal(bucket.loss_rate); overlay = Decimal(bucket.forward_factor)
            ead = exposure; discount = Decimal("1"); pd_rate = rate; lgd_rate = Decimal("1")
            base_ecl = money(ead * rate); ecl = money(base_ecl * overlay)
        else:
            if not exp.sppi_passed or exp.business_model not in {"HOLD_TO_COLLECT", "HOLD_TO_COLLECT_AND_SELL"}:
                raise HTTPException(422, f"Exposure {exp.reference} is outside amortised-cost/FVOCI ECL scope")
            stage, reason = _stage_for(portfolio, exp, dpd)
            pd_rate = Decimal(exp.current_12m_pd or 0) if stage == 1 else Decimal(exp.lifetime_pd or 0)
            if stage == 3 and pd_rate == 0: pd_rate = Decimal("1")
            if pd_rate <= 0 or Decimal(exp.lgd or 0) <= 0:
                raise HTTPException(422, f"PD/LGD inputs are missing for {exp.reference}")
            lgd_rate = Decimal(exp.lgd)
            ead = money(exposure + Decimal(exp.undrawn_commitment or 0) * Decimal(exp.credit_conversion_factor or 0))
            discount = _discount_factor(exp, data.as_of_date)
            overlay = Decimal(portfolio.forward_looking_overlay or 1)
            base_ecl = money(ead * pd_rate * lgd_rate * discount)
            ecl = money(base_ecl * overlay)
            rate = pd_rate * lgd_rate
        line = EclRunLine(run_id=run.id, exposure_id=exp.id, stage=stage, stage_reason=reason,
                          days_past_due=dpd, pd_rate=pd_rate, lgd_rate=lgd_rate, ead_amount=ead,
                          discount_factor=discount, loss_rate=rate, forward_factor=overlay,
                          base_ecl_amount=base_ecl, ecl_amount=ecl)
        db.add(line); lines.append(line)
        total_exp += ead; total_ecl += ecl; stage_totals[stage] += ecl
    run.total_exposure = money(total_exp); run.expected_credit_loss = money(total_ecl)
    run.stage_1_ecl = money(stage_totals[1]); run.stage_2_ecl = money(stage_totals[2]); run.stage_3_ecl = money(stage_totals[3])
    run.analysis_hash = _run_hash(run, lines)
    # Backward-compatible posting is allowed only for the legacy simplified method.
    if data.post_journal and portfolio.method == "SIMPLIFIED":
        if not data.expense_account_code or not data.allowance_account_code:
            raise HTTPException(422, "Posting accounts are required")
        expense = get_account(db, data.company_id, data.expense_account_code)
        allowance = get_account(db, data.company_id, data.allowance_account_code)
        je = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.as_of_date,
                                   reference="IFRS9-ECL", description=f"Expected credit loss at {data.as_of_date}",
                                   lines=[{"account_id": expense.id, "debit": run.expected_credit_loss, "credit": 0},
                                          {"account_id": allowance.id, "debit": 0, "credit": run.expected_credit_loss}])
        run.journal_id = je.id; run.status = "POSTED_LEGACY"
    write_audit(db, action="IFRS9_ECL_CALCULATED", entity_type="ECL_RUN", entity_id=run.id,
                user_id=user.id, company_id=data.company_id,
                after={"approach": run.approach, "exposure": str(run.total_exposure), "ecl": str(run.expected_credit_loss),
                       "stage_1": str(run.stage_1_ecl), "stage_2": str(run.stage_2_ecl), "stage_3": str(run.stage_3_ecl),
                       "status": run.status, "analysis_hash": run.analysis_hash})
    db.commit()
    return {"id": run.id, "approach": run.approach, "total_exposure": run.total_exposure,
            "expected_credit_loss": run.expected_credit_loss, "stage_1_ecl": run.stage_1_ecl,
            "stage_2_ecl": run.stage_2_ecl, "stage_3_ecl": run.stage_3_ecl,
            "status": run.status, "journal_id": run.journal_id, "analysis_hash": run.analysis_hash}


@router.post("/ifrs9/runs/{run_id}/review")
def review_ecl_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(EclRun, run_id)
    if not run: raise HTTPException(404, "ECL run not found")
    ensure_permission(db, user, run.company_id, "finance.manage_ifrs9")
    if run.status != "READY_FOR_REVIEW": raise HTTPException(422, "Run is not ready for review")
    if run.created_by == user.id: raise HTTPException(409, "Preparer cannot review the ECL run")
    lines = db.scalars(select(EclRunLine).where(EclRunLine.run_id == run.id)).all()
    if _run_hash(run, list(lines)) != run.analysis_hash:
        raise HTTPException(409, "ECL analysis changed after preparation")
    run.status = "REVIEWED"; run.reviewed_by = user.id; run.reviewed_at = utc_now()
    write_audit(db, action="IFRS9_ECL_REVIEWED", entity_type="ECL_RUN", entity_id=run.id,
                user_id=user.id, company_id=run.company_id, after={"status": run.status})
    db.commit(); return {"id": run.id, "status": run.status}


@router.post("/ifrs9/runs/{run_id}/approve")
def approve_ecl_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(EclRun, run_id)
    if not run: raise HTTPException(404, "ECL run not found")
    ensure_permission(db, user, run.company_id, "finance.manage_ifrs9")
    if run.status != "REVIEWED": raise HTTPException(422, "Run must be reviewed first")
    if user.id in {run.created_by, run.reviewed_by}: raise HTTPException(409, "Approver must be independent")
    if not run.expense_account_code or not run.allowance_account_code:
        raise HTTPException(422, "Posting accounts were not configured on the run")
    lines = db.scalars(select(EclRunLine).where(EclRunLine.run_id == run.id)).all()
    if _run_hash(run, list(lines)) != run.analysis_hash:
        raise HTTPException(409, "ECL analysis changed after review")
    expense = get_account(db, run.company_id, run.expense_account_code)
    allowance = get_account(db, run.company_id, run.allowance_account_code)
    je = create_posted_journal(db, company_id=run.company_id, user_id=user.id, posting_date=run.as_of_date,
                               reference="IFRS9-ECL", description=f"Approved expected credit loss at {run.as_of_date}",
                               lines=[{"account_id": expense.id, "debit": run.expected_credit_loss, "credit": 0},
                                      {"account_id": allowance.id, "debit": 0, "credit": run.expected_credit_loss}])
    run.journal_id = je.id; run.status = "APPROVED_POSTED"; run.approved_by = user.id; run.approved_at = utc_now()
    write_audit(db, action="IFRS9_ECL_APPROVED_POSTED", entity_type="ECL_RUN", entity_id=run.id,
                user_id=user.id, company_id=run.company_id, after={"status": run.status, "journal": je.number})
    db.commit(); return {"id": run.id, "status": run.status, "journal_id": run.journal_id, "journal_number": je.number}


@router.get("/ifrs9/runs")
def list_ecl_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(select(EclRun).where(EclRun.company_id == company_id).order_by(EclRun.id.desc())).all()
    return [{"id": r.id, "as_of_date": r.as_of_date, "approach": r.approach,
             "total_exposure": r.total_exposure, "expected_credit_loss": r.expected_credit_loss,
             "stage_1_ecl": r.stage_1_ecl, "stage_2_ecl": r.stage_2_ecl, "stage_3_ecl": r.stage_3_ecl,
             "status": r.status, "analysis_hash": r.analysis_hash} for r in rows]


@router.post("/maintenance/assets", status_code=201)
def create_maintenance_asset(data: AssetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "maintenance.manage")
    row = MaintenanceAsset(**data.model_dump())
    db.add(row); db.flush()
    write_audit(db, action="MAINTENANCE_ASSET_CREATED", entity_type="MAINTENANCE_ASSET", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"code": data.code})
    db.commit(); return {"id": row.id, "code": row.code}

@router.post("/maintenance/work-orders", status_code=201)
def create_work_order(data: WorkOrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "maintenance.manage")
    asset = db.get(MaintenanceAsset, data.asset_id)
    if not asset or asset.company_id != data.company_id:
        raise HTTPException(404, "Maintenance asset not found")
    count = db.scalar(select(func.count(MaintenanceWorkOrder.id)).where(MaintenanceWorkOrder.company_id == data.company_id)) or 0
    row = MaintenanceWorkOrder(company_id=data.company_id, number=f"MWO-{data.company_id}-{count+1:06d}",
                               asset_id=data.asset_id, work_type=data.work_type, priority=data.priority,
                               description=data.description, created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="MAINTENANCE_WO_CREATED", entity_type="MAINTENANCE_WORK_ORDER", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"number": row.number})
    db.commit(); return {"id": row.id, "number": row.number, "status": row.status}

@router.post("/maintenance/work-orders/{work_order_id}/start")
def start_work_order(work_order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(MaintenanceWorkOrder, work_order_id)
    if not row: raise HTTPException(404, "Work order not found")
    ensure_permission(db, user, row.company_id, "maintenance.manage")
    if row.status != "OPEN": raise HTTPException(422, "Only open work orders can be started")
    row.status = "IN_PROGRESS"; row.started_at = utc_now()
    db.commit(); return {"id": row.id, "status": row.status}

@router.post("/maintenance/work-orders/{work_order_id}/complete")
def complete_work_order(work_order_id: int, data: CompleteWorkOrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(MaintenanceWorkOrder, work_order_id)
    if not row: raise HTTPException(404, "Work order not found")
    ensure_permission(db, user, row.company_id, "maintenance.manage")
    if row.status not in ("OPEN", "IN_PROGRESS"): raise HTTPException(422, "Work order cannot be completed")
    row.status = "COMPLETED"; row.completed_at = utc_now(); row.approved_by = user.id
    row.downtime_minutes = data.downtime_minutes; row.labor_cost = data.labor_cost; row.parts_cost = Decimal(row.parts_cost or 0) + Decimal(data.parts_cost)
    write_audit(db, action="MAINTENANCE_WO_COMPLETED", entity_type="MAINTENANCE_WORK_ORDER", entity_id=row.id,
                user_id=user.id, company_id=row.company_id,
                after={"downtime_minutes": data.downtime_minutes, "cost": str(Decimal(data.labor_cost) + Decimal(row.parts_cost or 0))})
    db.commit(); return {"id": row.id, "status": row.status, "total_cost": Decimal(row.labor_cost or 0) + Decimal(row.parts_cost or 0)}

@router.get("/maintenance/dashboard")
def maintenance_dashboard(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "maintenance.read")
    assets = db.scalar(select(func.count(MaintenanceAsset.id)).where(MaintenanceAsset.company_id == company_id)) or 0
    open_orders = db.scalar(select(func.count(MaintenanceWorkOrder.id)).where(
        MaintenanceWorkOrder.company_id == company_id, MaintenanceWorkOrder.status != "COMPLETED")) or 0
    completed = db.scalars(select(MaintenanceWorkOrder).where(
        MaintenanceWorkOrder.company_id == company_id, MaintenanceWorkOrder.status == "COMPLETED")).all()
    total_down = sum((x.downtime_minutes or 0) for x in completed)
    total_cost = sum((Decimal(x.labor_cost or 0) + Decimal(x.parts_cost or 0) for x in completed), Decimal("0"))
    mttr = round(total_down / len(completed), 2) if completed else 0
    return {"assets": assets, "open_work_orders": open_orders, "completed_work_orders": len(completed),
            "downtime_minutes": total_down, "maintenance_cost": total_cost, "mttr_minutes": mttr}


@router.post("/maintenance/plans", status_code=201)
def create_maintenance_plan(data: MaintenancePlanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "maintenance.manage")
    asset = db.get(MaintenanceAsset, data.asset_id)
    if not asset or asset.company_id != data.company_id:
        raise HTTPException(404, "Maintenance asset not found")
    if not data.interval_days and not data.meter_interval:
        raise HTTPException(422, "A calendar or meter interval is required")
    row = MaintenancePlan(**data.model_dump(), created_by=user.id)
    if row.interval_days and not row.next_due_date:
        row.next_due_date = date.today() + timedelta(days=row.interval_days)
    if row.meter_interval and row.next_due_meter is None:
        row.next_due_meter = Decimal(asset.meter_hours or 0) + Decimal(row.meter_interval)
    db.add(row); db.flush()
    write_audit(db, action="MAINTENANCE_PLAN_CREATED", entity_type="MAINTENANCE_PLAN", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"code": row.code})
    db.commit()
    return {"id": row.id, "code": row.code, "next_due_date": row.next_due_date, "next_due_meter": row.next_due_meter}

@router.post("/maintenance/plans/generate-due")
def generate_due_maintenance(company_id: int, as_of_date: date = date.today(), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "maintenance.manage")
    plans = db.scalars(select(MaintenancePlan).where(MaintenancePlan.company_id == company_id, MaintenancePlan.active == True)).all()
    generated=[]
    for p in plans:
        asset=db.get(MaintenanceAsset,p.asset_id)
        due_date=bool(p.next_due_date and p.next_due_date <= as_of_date)
        due_meter=bool(p.next_due_meter is not None and Decimal(asset.meter_hours or 0) >= Decimal(p.next_due_meter))
        if not (due_date or due_meter):
            continue
        existing=db.scalar(select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.company_id==company_id, MaintenanceWorkOrder.asset_id==p.asset_id, MaintenanceWorkOrder.work_type=="PREVENTIVE", MaintenanceWorkOrder.description==p.description, MaintenanceWorkOrder.status.in_(["OPEN","IN_PROGRESS"])))
        if existing:
            continue
        count=db.scalar(select(func.count(MaintenanceWorkOrder.id)).where(MaintenanceWorkOrder.company_id==company_id)) or 0
        wo=MaintenanceWorkOrder(company_id=company_id, number=f"MWO-{company_id}-{count+1:06d}", asset_id=p.asset_id, work_type="PREVENTIVE", priority=p.priority, description=p.description, created_by=user.id)
        db.add(wo); db.flush(); generated.append({"id":wo.id,"number":wo.number,"plan_id":p.id})
        p.last_generated_at=utc_now()
        if p.interval_days: p.next_due_date=as_of_date+timedelta(days=p.interval_days)
        if p.meter_interval: p.next_due_meter=Decimal(asset.meter_hours or 0)+Decimal(p.meter_interval)
    write_audit(db, action="PREVENTIVE_WO_GENERATED", entity_type="MAINTENANCE_PLAN", entity_id=None, user_id=user.id, company_id=company_id, after={"count":len(generated)})
    db.commit(); return {"generated_count":len(generated),"work_orders":generated}

@router.post("/maintenance/spare-parts", status_code=201)
def create_spare_part(data: SparePartIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "maintenance.manage")
    row=MaintenanceSparePart(**data.model_dump()); db.add(row); db.flush()
    write_audit(db, action="SPARE_PART_CREATED", entity_type="MAINTENANCE_SPARE_PART", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code":row.code})
    db.commit(); return {"id":row.id,"code":row.code,"quantity_on_hand":row.quantity_on_hand}

@router.post("/maintenance/work-orders/{work_order_id}/issue-part")
def issue_part(work_order_id: int, data: IssuePartIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wo=db.get(MaintenanceWorkOrder,work_order_id)
    if not wo: raise HTTPException(404,"Work order not found")
    ensure_permission(db,user,wo.company_id,"maintenance.manage")
    part=db.get(MaintenanceSparePart,data.spare_part_id)
    if not part or part.company_id != wo.company_id: raise HTTPException(404,"Spare part not found")
    if Decimal(part.quantity_on_hand) < Decimal(data.quantity): raise HTTPException(422,"Insufficient spare part stock")
    total=(Decimal(data.quantity)*Decimal(part.average_cost)).quantize(Q,ROUND_HALF_UP)
    part.quantity_on_hand=Decimal(part.quantity_on_hand)-Decimal(data.quantity)
    wo.parts_cost=Decimal(wo.parts_cost or 0)+total
    line=MaintenanceWorkOrderPart(work_order_id=wo.id,spare_part_id=part.id,quantity=data.quantity,unit_cost=part.average_cost,total_cost=total,issued_by=user.id)
    db.add(line); db.flush()
    write_audit(db, action="SPARE_PART_ISSUED", entity_type="MAINTENANCE_WORK_ORDER", entity_id=wo.id, user_id=user.id, company_id=wo.company_id, after={"part":part.code,"quantity":str(data.quantity),"cost":str(total)})
    db.commit(); return {"work_order_id":wo.id,"part_code":part.code,"remaining_quantity":part.quantity_on_hand,"issued_cost":total}

@router.post("/maintenance/calibrations", status_code=201)
def record_calibration(data: CalibrationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db,user,data.company_id,"maintenance.manage")
    asset=db.get(MaintenanceAsset,data.asset_id)
    if not asset or asset.company_id != data.company_id: raise HTTPException(404,"Maintenance asset not found")
    if data.next_due_date <= data.calibration_date: raise HTTPException(422,"Next calibration date must be later")
    result=data.result.upper()
    if result not in {"PASS","FAIL","CONDITIONAL"}: raise HTTPException(422,"Invalid calibration result")
    row=CalibrationRecord(**data.model_dump(exclude={"result"}),result=result,performed_by=user.id); db.add(row); db.flush()
    write_audit(db,action="CALIBRATION_RECORDED",entity_type="CALIBRATION_RECORD",entity_id=row.id,user_id=user.id,company_id=data.company_id,after={"instrument":row.instrument_code,"result":row.result})
    db.commit(); return {"id":row.id,"result":row.result,"next_due_date":row.next_due_date}

@router.get("/maintenance/alerts")
def maintenance_alerts(company_id: int, as_of_date: date = date.today(), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db,user,company_id,"maintenance.read")
    low=db.scalars(select(MaintenanceSparePart).where(MaintenanceSparePart.company_id==company_id, MaintenanceSparePart.quantity_on_hand <= MaintenanceSparePart.reorder_level)).all()
    due=db.scalars(select(CalibrationRecord).where(CalibrationRecord.company_id==company_id, CalibrationRecord.next_due_date <= as_of_date).order_by(CalibrationRecord.next_due_date)).all()
    plans=db.scalars(select(MaintenancePlan).where(MaintenancePlan.company_id==company_id, MaintenancePlan.active==True, MaintenancePlan.next_due_date <= as_of_date)).all()
    return {"low_stock_parts":[{"code":x.code,"quantity":x.quantity_on_hand,"reorder_level":x.reorder_level} for x in low],"due_calibrations":[{"instrument_code":x.instrument_code,"next_due_date":x.next_due_date,"result":x.result} for x in due],"due_plans":[{"code":x.code,"next_due_date":x.next_due_date} for x in plans]}
