from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    BackgroundJob, BillOfMaterial, BillOfMaterialLine, Item, ManufacturingRouting, ManufacturingRoutingOperation,
    MRPDemandLine, MRPPlanRun, MRPRequirementLine, Party, ProductionCostClose, ProductionOperationLog,
    ProductionOrder, ProductionScrapRecord, StockMovement, SupplierItemPlanning, User, Warehouse, WorkCenter,
    WorkCenterCalendarDay,
)
from app.services.audit import write_audit
from app.services.operations import get_account, get_item, get_warehouse, money, quantity, stock_balance
from app.services.posting import create_posted_journal, ensure_open_period
from app.services.mrp import calculate_mrp, enqueue_mrp_job

router = APIRouter(prefix="/manufacturing/advanced", tags=["advanced manufacturing and costing"])
ZERO = Decimal("0")


class RoutingOperationIn(BaseModel):
    sequence: int = Field(ge=1)
    operation_code: str = Field(min_length=1, max_length=40)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    work_center_id: int
    setup_minutes: Decimal = Field(default=0, ge=0)
    run_minutes_per_unit: Decimal = Field(default=0, ge=0)
    queue_minutes: Decimal = Field(default=0, ge=0)
    move_minutes: Decimal = Field(default=0, ge=0)
    standard_labor_rate: Decimal | None = Field(default=None, ge=0)
    standard_overhead_rate: Decimal | None = Field(default=None, ge=0)
    outside_processing_cost: Decimal = Field(default=0, ge=0)
    quality_gate: bool = False


class RoutingIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=50)
    version: int = Field(default=1, ge=1)
    finished_item_id: int
    bom_id: int
    effective_from: date
    effective_to: date | None = None
    operations: list[RoutingOperationIn] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dates_and_operations(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        sequences = [row.sequence for row in self.operations]
        codes = [row.operation_code.strip().upper() for row in self.operations]
        if len(sequences) != len(set(sequences)):
            raise ValueError("routing operation sequences must be unique")
        if len(codes) != len(set(codes)):
            raise ValueError("routing operation codes must be unique")
        return self


class MRPDemandIn(BaseModel):
    item_id: int
    due_date: date
    quantity: Decimal = Field(gt=0)
    safety_stock: Decimal = Field(default=0, ge=0)
    source_type: str = Field(default="FORECAST", max_length=30)
    source_reference: str | None = Field(default=None, max_length=100)


class MRPRunIn(BaseModel):
    company_id: int
    warehouse_id: int
    planning_date: date
    horizon_end: date
    demands: list[MRPDemandIn] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_horizon(self):
        if self.horizon_end < self.planning_date:
            raise ValueError("horizon_end cannot be before planning_date")
        if any(line.due_date < self.planning_date or line.due_date > self.horizon_end for line in self.demands):
            raise ValueError("all demand dates must fall inside the planning horizon")
        return self


class SupplierPlanningIn(BaseModel):
    company_id: int
    supplier_id: int
    item_id: int
    lead_time_days: int = Field(default=0, ge=0, le=3650)
    lot_sizing_policy: str = Field(default="LFL", pattern="^(LFL|MIN_MAX|FOQ|EOQ|POQ)$")
    minimum_order_quantity: Decimal = Field(default=0, ge=0)
    order_multiple: Decimal = Field(default=1, gt=0)
    fixed_order_quantity: Decimal | None = Field(default=None, gt=0)
    eoq_annual_demand: Decimal | None = Field(default=None, gt=0)
    eoq_order_cost: Decimal | None = Field(default=None, gt=0)
    eoq_holding_cost: Decimal | None = Field(default=None, gt=0)
    preferred: bool = False


class WorkCenterCalendarIn(BaseModel):
    company_id: int
    work_center_id: int
    work_date: date
    shift_code: str = Field(default="DAY", min_length=1, max_length=30)
    available_minutes: Decimal = Field(default=480, gt=0, le=1440)


class OperationCompleteIn(BaseModel):
    actual_setup_minutes: Decimal = Field(default=0, ge=0)
    actual_run_minutes: Decimal = Field(gt=0)
    good_quantity: Decimal = Field(ge=0)
    rejected_quantity: Decimal = Field(default=0, ge=0)
    actual_labor_rate: Decimal | None = Field(default=None, ge=0)
    actual_overhead_rate: Decimal | None = Field(default=None, ge=0)


class ScrapIn(BaseModel):
    record_date: date
    item_id: int
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    reason_code: str = Field(min_length=1, max_length=50)
    classification: str = Field(default="NORMAL", pattern="^(NORMAL|ABNORMAL)$")
    disposition: str = Field(default="DISPOSE", pattern="^(DISPOSE|REWORK|RETURN_TO_STOCK)$")
    notes: str | None = None


class CostCloseIn(BaseModel):
    close_date: date
    cost_method: str = Field(default="STANDARD", pattern="^(STANDARD|ACTUAL)$")


def _routing_payload(row: ManufacturingRouting) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "code": row.code,
        "version": row.version,
        "finished_item_id": row.finished_item_id,
        "finished_item_code": row.finished_item.code,
        "bom_id": row.bom_id,
        "bom_code": row.bom.code,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "status": row.status,
        "prepared_by": row.prepared_by,
        "approved_by": row.approved_by,
        "operations": [
            {
                "id": op.id,
                "sequence": op.sequence,
                "operation_code": op.operation_code,
                "name_ar": op.name_ar,
                "name_en": op.name_en,
                "work_center_id": op.work_center_id,
                "work_center_code": op.work_center.code,
                "setup_minutes": op.setup_minutes,
                "run_minutes_per_unit": op.run_minutes_per_unit,
                "queue_minutes": op.queue_minutes,
                "move_minutes": op.move_minutes,
                "standard_labor_rate": op.standard_labor_rate,
                "standard_overhead_rate": op.standard_overhead_rate,
                "outside_processing_cost": op.outside_processing_cost,
                "quality_gate": op.quality_gate,
            }
            for op in sorted(row.operations, key=lambda item: item.sequence)
        ],
    }


def _cost_payload(row: ProductionCostClose) -> dict:
    return {
        "id": row.id,
        "production_order_id": row.production_order_id,
        "production_order_number": row.production_order.number,
        "close_date": row.close_date,
        "version": row.version,
        "cost_method": row.cost_method,
        "completed_quantity": row.completed_quantity,
        "standard_material_cost": row.standard_material_cost,
        "standard_labor_cost": row.standard_labor_cost,
        "standard_overhead_cost": row.standard_overhead_cost,
        "standard_total_cost": row.standard_total_cost,
        "actual_material_cost": row.actual_material_cost,
        "actual_labor_cost": row.actual_labor_cost,
        "actual_overhead_cost": row.actual_overhead_cost,
        "actual_total_cost": row.actual_total_cost,
        "material_price_variance": row.material_price_variance,
        "material_usage_variance": row.material_usage_variance,
        "labor_rate_variance": row.labor_rate_variance,
        "labor_efficiency_variance": row.labor_efficiency_variance,
        "overhead_spending_variance": row.overhead_spending_variance,
        "overhead_volume_variance": row.overhead_volume_variance,
        "abnormal_scrap_cost": row.abnormal_scrap_cost,
        "residual_variance": row.residual_variance,
        "total_variance": row.total_variance,
        "standard_unit_cost": row.standard_unit_cost,
        "actual_unit_cost": row.actual_unit_cost,
        "status": row.status,
        "analysis_hash": row.analysis_hash,
        "journal_id": row.journal_id,
        "prepared_by": row.prepared_by,
        "reviewed_by": row.reviewed_by,
        "approved_by": row.approved_by,
    }


def _mrp_payload(row: MRPPlanRun) -> dict:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "code": row.code,
        "warehouse_id": row.warehouse_id,
        "warehouse_code": row.warehouse.code,
        "planning_date": row.planning_date,
        "horizon_end": row.horizon_end,
        "gross_demand": row.gross_demand,
        "total_on_hand": row.total_on_hand,
        "total_scheduled_receipts": row.total_scheduled_receipts,
        "total_shortage": row.total_shortage,
        "total_planned_supply": row.total_planned_supply,
        "status": row.status,
        "execution_mode": row.execution_mode,
        "background_job_id": row.background_job_id,
        "progress_percent": row.progress_percent,
        "created_by": row.created_by,
        "approved_by": row.approved_by,
        "demands": [
            {
                "id": line.id,
                "item_id": line.item_id,
                "item_code": line.item.code,
                "due_date": line.due_date,
                "quantity": line.quantity,
                "safety_stock": line.safety_stock,
                "source_type": line.source_type,
                "source_reference": line.source_reference,
            }
            for line in row.demands
        ],
        "requirements": [
            {
                "id": line.id,
                "parent_item_id": line.parent_item_id,
                "parent_item_code": line.parent_item.code if line.parent_item else None,
                "item_id": line.item_id,
                "item_code": line.item.code,
                "item_name_ar": line.item.name_ar,
                "item_name_en": line.item.name_en,
                "level": line.level,
                "due_date": line.due_date,
                "gross_requirement": line.gross_requirement,
                "on_hand": line.on_hand,
                "scheduled_receipts": line.scheduled_receipts,
                "production_receipts": line.production_receipts,
                "purchase_receipts": line.purchase_receipts,
                "safety_stock": line.safety_stock,
                "net_requirement": line.net_requirement,
                "planned_order_quantity": line.planned_order_quantity,
                "planned_receipt_date": line.planned_receipt_date,
                "planned_release_date": line.planned_release_date,
                "supplier_id": line.supplier_id,
                "lead_time_days": line.lead_time_days,
                "lot_sizing_policy": line.lot_sizing_policy,
                "capacity_status": line.capacity_status,
                "supply_type": line.supply_type,
                "action_message": line.action_message,
                "bom_id": line.bom_id,
            }
            for line in sorted(row.requirements, key=lambda item: (item.level, item.due_date, item.item.code))
        ],
    }


@router.post("/routings", status_code=201)
def create_routing(data: RoutingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "manufacturing.routing")
    if db.scalar(select(ManufacturingRouting).where(
        ManufacturingRouting.company_id == data.company_id,
        ManufacturingRouting.code == data.code.strip().upper(),
        ManufacturingRouting.version == data.version,
    )):
        raise HTTPException(409, "Routing version already exists")
    finished = get_item(db, data.company_id, data.finished_item_id)
    bom = db.scalar(select(BillOfMaterial).where(
        BillOfMaterial.id == data.bom_id,
        BillOfMaterial.company_id == data.company_id,
        BillOfMaterial.finished_item_id == finished.id,
        BillOfMaterial.status == "ACTIVE",
    ))
    if not bom:
        raise HTTPException(422, "Active BOM must belong to the same finished item")
    centers = {row.id: row for row in db.scalars(select(WorkCenter).where(
        WorkCenter.company_id == data.company_id,
        WorkCenter.id.in_([line.work_center_id for line in data.operations]),
        WorkCenter.active.is_(True),
    )).all()}
    if len(centers) != len({line.work_center_id for line in data.operations}):
        raise HTTPException(422, "One or more work centers are missing or inactive")
    row = ManufacturingRouting(
        company_id=data.company_id,
        code=data.code.strip().upper(),
        version=data.version,
        finished_item_id=finished.id,
        bom_id=bom.id,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        status="DRAFT",
        prepared_by=user.id,
    )
    for source in sorted(data.operations, key=lambda item: item.sequence):
        center = centers[source.work_center_id]
        row.operations.append(ManufacturingRoutingOperation(
            sequence=source.sequence,
            operation_code=source.operation_code.strip().upper(),
            name_ar=source.name_ar.strip(),
            name_en=source.name_en.strip(),
            work_center_id=center.id,
            setup_minutes=quantity(source.setup_minutes),
            run_minutes_per_unit=Decimal(str(source.run_minutes_per_unit)),
            queue_minutes=quantity(source.queue_minutes),
            move_minutes=quantity(source.move_minutes),
            standard_labor_rate=money(source.standard_labor_rate if source.standard_labor_rate is not None else center.hourly_labor_rate),
            standard_overhead_rate=money(source.standard_overhead_rate if source.standard_overhead_rate is not None else center.hourly_overhead_rate),
            outside_processing_cost=money(source.outside_processing_cost),
            quality_gate=source.quality_gate,
        ))
    db.add(row)
    db.flush()
    write_audit(db, action="MANUFACTURING_ROUTING_CREATED", entity_type="MANUFACTURING_ROUTING", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"code": row.code, "version": row.version, "operations": len(row.operations)})
    db.commit()
    db.refresh(row)
    return _routing_payload(row)


@router.post("/routings/{routing_id}/approve")
def approve_routing(routing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(ManufacturingRouting).where(ManufacturingRouting.id == routing_id).options(selectinload(ManufacturingRouting.operations)))
    if not row:
        raise HTTPException(404, "Routing not found")
    ensure_permission(db, user, row.company_id, "manufacturing.routing.approve")
    if row.status != "DRAFT":
        raise HTTPException(409, "Only draft routings can be approved")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Routing preparer cannot approve the same routing")
    row.status = "APPROVED"
    row.approved_by = user.id
    row.approved_at = utc_now()
    write_audit(db, action="MANUFACTURING_ROUTING_APPROVED", entity_type="MANUFACTURING_ROUTING", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"code": row.code, "version": row.version})
    db.commit()
    db.refresh(row)
    return _routing_payload(row)


@router.get("/routings")
def list_routings(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "manufacturing.read")
    rows = db.scalars(select(ManufacturingRouting).where(ManufacturingRouting.company_id == company_id)
                      .options(selectinload(ManufacturingRouting.operations).selectinload(ManufacturingRoutingOperation.work_center))
                      .order_by(ManufacturingRouting.code, ManufacturingRouting.version.desc())).all()
    return [_routing_payload(row) for row in rows]


@router.post("/planning/supplier-items", status_code=201)
def upsert_supplier_item_planning(data: SupplierPlanningIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "manufacturing.plan")
    item = get_item(db, data.company_id, data.item_id)
    supplier = db.get(Party, data.supplier_id)
    if not supplier or supplier.company_id != data.company_id or supplier.party_type not in {"SUPPLIER", "BOTH"}:
        raise HTTPException(422, "Supplier must belong to the company")
    row = db.scalar(select(SupplierItemPlanning).where(
        SupplierItemPlanning.company_id == data.company_id,
        SupplierItemPlanning.supplier_id == data.supplier_id,
        SupplierItemPlanning.item_id == data.item_id,
    ))
    if row is None:
        row = SupplierItemPlanning(company_id=data.company_id, supplier_id=data.supplier_id, item_id=item.id)
        db.add(row)
    for key, value in data.model_dump(exclude={"company_id", "supplier_id", "item_id"}).items():
        setattr(row, key, value)
    row.active = True
    db.flush()
    write_audit(db, action="SUPPLIER_ITEM_PLANNING_UPSERTED", entity_type="SUPPLIER_ITEM_PLANNING", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"item_id": item.id, "lead_time_days": row.lead_time_days, "lot_sizing_policy": row.lot_sizing_policy})
    db.commit()
    return {"id": row.id, "supplier_id": row.supplier_id, "item_id": row.item_id, "lead_time_days": row.lead_time_days,
            "lot_sizing_policy": row.lot_sizing_policy, "minimum_order_quantity": row.minimum_order_quantity,
            "order_multiple": row.order_multiple, "preferred": row.preferred}


@router.get("/planning/supplier-items")
def list_supplier_item_planning(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "manufacturing.read")
    rows = db.scalars(select(SupplierItemPlanning).where(SupplierItemPlanning.company_id == company_id, SupplierItemPlanning.active.is_(True))
                      .order_by(SupplierItemPlanning.item_id, SupplierItemPlanning.preferred.desc())).all()
    return [{"id": row.id, "supplier_id": row.supplier_id, "supplier": row.supplier.name_en, "item_id": row.item_id,
             "item": row.item.code, "lead_time_days": row.lead_time_days, "lot_sizing_policy": row.lot_sizing_policy,
             "minimum_order_quantity": row.minimum_order_quantity, "order_multiple": row.order_multiple,
             "fixed_order_quantity": row.fixed_order_quantity, "preferred": row.preferred} for row in rows]


@router.post("/planning/work-center-calendar", status_code=201)
def upsert_work_center_calendar(data: WorkCenterCalendarIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "manufacturing.plan")
    center = db.scalar(select(WorkCenter).where(WorkCenter.id == data.work_center_id, WorkCenter.company_id == data.company_id))
    if not center:
        raise HTTPException(422, "Work center must belong to the company")
    row = db.scalar(select(WorkCenterCalendarDay).where(WorkCenterCalendarDay.work_center_id == center.id, WorkCenterCalendarDay.work_date == data.work_date))
    if row is None:
        row = WorkCenterCalendarDay(company_id=data.company_id, work_center_id=center.id, work_date=data.work_date)
        db.add(row)
    row.shift_code = data.shift_code.strip().upper()
    row.available_minutes = quantity(data.available_minutes)
    row.active = True
    db.flush()
    write_audit(db, action="WORK_CENTER_CAPACITY_CONFIGURED", entity_type="WORK_CENTER_CALENDAR_DAY", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, after={"work_center": center.code, "date": str(row.work_date), "minutes": str(row.available_minutes)})
    db.commit()
    return {"id": row.id, "work_center_id": row.work_center_id, "work_date": row.work_date,
            "available_minutes": row.available_minutes, "reserved_minutes": row.reserved_minutes, "shift_code": row.shift_code}


@router.post("/mrp-runs", status_code=201)
def create_mrp_run(data: MRPRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "manufacturing.plan")
    payload = data.model_dump(mode="json")
    if not settings.mrp_inline_execution:
        job = enqueue_mrp_job(db, payload, user_id=user.id)
        db.commit()
        return JSONResponse(status_code=202, content={"job_id": job.id, "status": job.status, "progress_percent": job.progress_percent,
                                                     "poll_url": f"/api/v1/manufacturing/advanced/jobs/{job.id}"})
    run = calculate_mrp(db, payload, user_id=user.id)
    db.commit()
    row = db.scalar(select(MRPPlanRun).where(MRPPlanRun.id == run.id).options(
        selectinload(MRPPlanRun.demands).selectinload(MRPDemandLine.item),
        selectinload(MRPPlanRun.requirements).selectinload(MRPRequirementLine.item),
        selectinload(MRPPlanRun.requirements).selectinload(MRPRequirementLine.parent_item),
    ))
    return _mrp_payload(row)


@router.get("/jobs/{job_id}")
def get_background_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(BackgroundJob, job_id)
    if not job:
        raise HTTPException(404, "Background job not found")
    ensure_permission(db, user, job.company_id, "manufacturing.read")
    result_id = None
    if job.result_reference and job.result_reference.startswith("MRP_PLAN_RUN:"):
        result_id = int(job.result_reference.split(":", 1)[1])
    return {"id": job.id, "job_type": job.job_type, "status": job.status, "progress_percent": job.progress_percent,
            "attempts": job.attempts, "result_id": result_id, "error_message": job.error_message,
            "created_at": job.created_at, "started_at": job.started_at, "completed_at": job.completed_at}


@router.post("/mrp-runs/{run_id}/approve")
def approve_mrp_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(MRPPlanRun, run_id)
    if not row:
        raise HTTPException(404, "MRP run not found")
    ensure_permission(db, user, row.company_id, "manufacturing.plan.approve")
    if row.status != "CALCULATED":
        raise HTTPException(409, "Only calculated MRP runs can be approved")
    if row.created_by == user.id:
        raise HTTPException(409, "MRP preparer cannot approve the same run")
    row.status = "APPROVED"
    row.approved_by = user.id
    row.approved_at = utc_now()
    write_audit(db, action="MRP_PLAN_APPROVED", entity_type="MRP_PLAN_RUN", entity_id=row.id, user_id=user.id,
                company_id=row.company_id, after={"code": row.code, "planned_supply": str(row.total_planned_supply)})
    db.commit()
    return {"id": row.id, "code": row.code, "status": row.status, "approved_by": row.approved_by}


@router.get("/mrp-runs")
def list_mrp_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "manufacturing.read")
    rows = db.scalars(select(MRPPlanRun).where(MRPPlanRun.company_id == company_id)
                      .options(selectinload(MRPPlanRun.demands).selectinload(MRPDemandLine.item),
                               selectinload(MRPPlanRun.requirements).selectinload(MRPRequirementLine.item),
                               selectinload(MRPPlanRun.requirements).selectinload(MRPRequirementLine.parent_item))
                      .order_by(MRPPlanRun.id.desc())).all()
    return [_mrp_payload(row) for row in rows]


@router.post("/orders/{order_id}/operations/initialize")
def initialize_order_operations(order_id: int, routing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.scalar(select(ProductionOrder).where(ProductionOrder.id == order_id).options(selectinload(ProductionOrder.bom)))
    if not order:
        raise HTTPException(404, "Production order not found")
    ensure_permission(db, user, order.company_id, "manufacturing.manage")
    routing = db.scalar(select(ManufacturingRouting).where(
        ManufacturingRouting.id == routing_id,
        ManufacturingRouting.company_id == order.company_id,
        ManufacturingRouting.finished_item_id == order.bom.finished_item_id,
        ManufacturingRouting.status == "APPROVED",
    ).options(selectinload(ManufacturingRouting.operations)))
    if not routing:
        raise HTTPException(422, "Approved routing for the production order item was not found")
    if db.scalar(select(func.count(ProductionOperationLog.id)).where(ProductionOperationLog.production_order_id == order.id)):
        raise HTTPException(409, "Production operations are already initialized")
    for operation in sorted(routing.operations, key=lambda item: item.sequence):
        db.add(ProductionOperationLog(
            company_id=order.company_id, production_order_id=order.id, routing_operation_id=operation.id,
            sequence=operation.sequence, status="PLANNED", planned_setup_minutes=operation.setup_minutes,
            planned_run_minutes=quantity(Decimal(operation.run_minutes_per_unit) * Decimal(order.planned_quantity)),
            actual_labor_rate=operation.standard_labor_rate, actual_overhead_rate=operation.standard_overhead_rate,
        ))
    db.flush()
    write_audit(db, action="PRODUCTION_ROUTING_INITIALIZED", entity_type="PRODUCTION_ORDER", entity_id=order.id,
                user_id=user.id, company_id=order.company_id, after={"routing": routing.code, "operations": len(routing.operations)})
    db.commit()
    return {"order_id": order.id, "routing_id": routing.id, "operations_created": len(routing.operations)}


@router.post("/operations/{operation_log_id}/start")
def start_operation(operation_log_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ProductionOperationLog, operation_log_id)
    if not row:
        raise HTTPException(404, "Production operation not found")
    ensure_permission(db, user, row.company_id, "manufacturing.manage")
    if row.status != "PLANNED":
        raise HTTPException(409, "Only planned operations can be started")
    previous_open = db.scalar(select(ProductionOperationLog).where(
        ProductionOperationLog.production_order_id == row.production_order_id,
        ProductionOperationLog.sequence < row.sequence,
        ProductionOperationLog.status != "COMPLETED",
    ).order_by(ProductionOperationLog.sequence))
    if previous_open:
        raise HTTPException(409, f"Previous operation sequence {previous_open.sequence} must be completed first")
    row.status = "IN_PROCESS"
    row.started_at = utc_now()
    row.started_by = user.id
    write_audit(db, action="PRODUCTION_OPERATION_STARTED", entity_type="PRODUCTION_OPERATION", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"order_id": row.production_order_id, "sequence": row.sequence})
    db.commit()
    return {"id": row.id, "status": row.status, "started_at": row.started_at}


@router.post("/operations/{operation_log_id}/complete")
def complete_operation(operation_log_id: int, data: OperationCompleteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(ProductionOperationLog).where(ProductionOperationLog.id == operation_log_id)
                    .options(selectinload(ProductionOperationLog.routing_operation).selectinload(ManufacturingRoutingOperation.work_center)))
    if not row:
        raise HTTPException(404, "Production operation not found")
    ensure_permission(db, user, row.company_id, "manufacturing.manage")
    if row.status != "IN_PROCESS":
        raise HTTPException(409, "Operation must be in process")
    if quantity(data.good_quantity + data.rejected_quantity) <= 0:
        raise HTTPException(422, "Good plus rejected quantity must be greater than zero")
    operation = row.routing_operation
    row.actual_setup_minutes = quantity(data.actual_setup_minutes)
    row.actual_run_minutes = quantity(data.actual_run_minutes)
    row.good_quantity = quantity(data.good_quantity)
    row.rejected_quantity = quantity(data.rejected_quantity)
    row.actual_labor_rate = money(data.actual_labor_rate if data.actual_labor_rate is not None else operation.standard_labor_rate)
    row.actual_overhead_rate = money(data.actual_overhead_rate if data.actual_overhead_rate is not None else operation.standard_overhead_rate)
    row.status = "COMPLETED"
    row.completed_at = utc_now()
    row.completed_by = user.id
    write_audit(db, action="PRODUCTION_OPERATION_COMPLETED", entity_type="PRODUCTION_OPERATION", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"sequence": row.sequence, "good": str(row.good_quantity), "rejected": str(row.rejected_quantity)})
    db.commit()
    return {"id": row.id, "status": row.status, "good_quantity": row.good_quantity, "rejected_quantity": row.rejected_quantity}


@router.get("/orders/{order_id}/operations")
def list_order_operations(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Production order not found")
    ensure_permission(db, user, order.company_id, "manufacturing.read")
    rows = db.scalars(select(ProductionOperationLog).where(ProductionOperationLog.production_order_id == order.id)
                      .options(selectinload(ProductionOperationLog.routing_operation).selectinload(ManufacturingRoutingOperation.work_center))
                      .order_by(ProductionOperationLog.sequence)).all()
    return [{
        "id": row.id, "sequence": row.sequence, "operation_code": row.routing_operation.operation_code,
        "name_ar": row.routing_operation.name_ar, "name_en": row.routing_operation.name_en,
        "work_center": row.routing_operation.work_center.code, "status": row.status,
        "planned_setup_minutes": row.planned_setup_minutes, "planned_run_minutes": row.planned_run_minutes,
        "actual_setup_minutes": row.actual_setup_minutes, "actual_run_minutes": row.actual_run_minutes,
        "good_quantity": row.good_quantity, "rejected_quantity": row.rejected_quantity,
        "actual_labor_rate": row.actual_labor_rate, "actual_overhead_rate": row.actual_overhead_rate,
    } for row in rows]


@router.post("/orders/{order_id}/scrap", status_code=201)
def record_scrap(order_id: int, data: ScrapIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Production order not found")
    ensure_permission(db, user, order.company_id, "manufacturing.scrap")
    if order.status not in {"IN_PROCESS", "COMPLETED"}:
        raise HTTPException(409, "Scrap can only be recorded for in-process or completed orders")
    item = get_item(db, order.company_id, data.item_id)
    unit_cost = money(data.unit_cost if data.unit_cost is not None else item.standard_cost)
    row = ProductionScrapRecord(
        company_id=order.company_id, production_order_id=order.id, item_id=item.id, record_date=data.record_date,
        quantity=quantity(data.quantity), unit_cost=unit_cost, total_cost=money(quantity(data.quantity) * unit_cost),
        reason_code=data.reason_code.strip().upper(), classification=data.classification, disposition=data.disposition,
        notes=data.notes, created_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="PRODUCTION_SCRAP_RECORDED", entity_type="PRODUCTION_SCRAP", entity_id=row.id,
                user_id=user.id, company_id=order.company_id, after={"order": order.number, "item": item.code, "quantity": str(row.quantity), "classification": row.classification})
    db.commit()
    return {"id": row.id, "order_id": order.id, "item_code": item.code, "quantity": row.quantity,
            "total_cost": row.total_cost, "classification": row.classification, "disposition": row.disposition}


def _hash_cost_analysis(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _calculate_cost_close(db: Session, order: ProductionOrder, close_date: date) -> dict[str, Decimal]:
    qty = Decimal(order.completed_quantity)
    if qty <= 0:
        raise HTTPException(422, "Completed quantity must be greater than zero")
    factor = qty / Decimal(order.bom.output_quantity)
    material_price = ZERO
    material_usage = ZERO
    standard_material = ZERO
    issue_rows = db.scalars(select(StockMovement).where(
        StockMovement.company_id == order.company_id,
        StockMovement.reference_type == "PRODUCTION_ORDER",
        StockMovement.reference_id == order.id,
        StockMovement.movement_type == "PRODUCTION_ISSUE",
    )).all()
    actual_by_item: dict[int, tuple[Decimal, Decimal]] = {}
    for movement in issue_rows:
        current_qty, current_cost = actual_by_item.get(movement.item_id, (ZERO, ZERO))
        actual_by_item[movement.item_id] = (current_qty + abs(Decimal(movement.quantity)), current_cost + abs(Decimal(movement.total_cost)))
    for line in order.bom.lines:
        standard_qty = factor * Decimal(line.quantity) * (Decimal("1") + Decimal(line.scrap_percent) / Decimal("100"))
        standard_unit = Decimal(line.component_item.standard_cost)
        standard_material += standard_qty * standard_unit
        actual_qty, actual_cost = actual_by_item.get(line.component_item_id, (ZERO, ZERO))
        actual_unit = actual_cost / actual_qty if actual_qty else standard_unit
        material_price += actual_qty * (actual_unit - standard_unit)
        material_usage += standard_unit * (actual_qty - standard_qty)
    operation_logs = db.scalars(select(ProductionOperationLog).where(
        ProductionOperationLog.production_order_id == order.id,
        ProductionOperationLog.status == "COMPLETED",
    ).options(selectinload(ProductionOperationLog.routing_operation))).all()
    standard_labor = ZERO
    standard_overhead = ZERO
    labor_rate = ZERO
    labor_efficiency = ZERO
    overhead_spending = ZERO
    overhead_volume = ZERO
    if operation_logs:
        for log in operation_logs:
            op = log.routing_operation
            standard_hours = (Decimal(op.setup_minutes) + Decimal(op.run_minutes_per_unit) * qty) / Decimal("60")
            actual_hours = (Decimal(log.actual_setup_minutes) + Decimal(log.actual_run_minutes)) / Decimal("60")
            std_labor_rate = Decimal(op.standard_labor_rate)
            std_overhead_rate = Decimal(op.standard_overhead_rate)
            actual_labor_rate = Decimal(log.actual_labor_rate)
            actual_overhead_rate = Decimal(log.actual_overhead_rate)
            standard_labor += standard_hours * std_labor_rate + Decimal(op.outside_processing_cost) * qty
            standard_overhead += standard_hours * std_overhead_rate
            labor_rate += actual_hours * (actual_labor_rate - std_labor_rate)
            labor_efficiency += (actual_hours - standard_hours) * std_labor_rate
            overhead_spending += actual_hours * (actual_overhead_rate - std_overhead_rate)
            overhead_volume += (actual_hours - standard_hours) * std_overhead_rate
    else:
        center = order.bom.work_center
        standard_hours = Decimal(order.planned_hours)
        actual_hours = Decimal(order.actual_hours)
        labor_rate_value = Decimal(center.hourly_labor_rate) if center else ZERO
        overhead_rate_value = Decimal(center.hourly_overhead_rate) if center else ZERO
        standard_labor = standard_hours * labor_rate_value
        standard_overhead = standard_hours * overhead_rate_value
        labor_efficiency = (actual_hours - standard_hours) * labor_rate_value
        overhead_volume = (actual_hours - standard_hours) * overhead_rate_value
    standard_material = money(standard_material)
    standard_labor = money(standard_labor)
    standard_overhead = money(standard_overhead)
    material_price = money(material_price)
    material_usage = money(material_usage)
    labor_rate = money(labor_rate)
    labor_efficiency = money(labor_efficiency)
    overhead_spending = money(overhead_spending)
    overhead_volume = money(overhead_volume)
    actual_material = money(order.material_cost)
    actual_labor = money(order.labor_cost)
    actual_overhead = money(order.overhead_cost)
    standard_total = money(standard_material + standard_labor + standard_overhead)
    actual_total = money(actual_material + actual_labor + actual_overhead)
    total_variance = money(actual_total - standard_total)
    abnormal_scrap = money(db.scalar(select(func.coalesce(func.sum(ProductionScrapRecord.total_cost), 0)).where(
        ProductionScrapRecord.production_order_id == order.id,
        ProductionScrapRecord.classification == "ABNORMAL",
        ProductionScrapRecord.record_date <= close_date,
    )) or 0)
    calculated_components = money(material_price + material_usage + labor_rate + labor_efficiency + overhead_spending + overhead_volume)
    residual = money(total_variance - calculated_components)
    return {
        "completed_quantity": quantity(qty),
        "standard_material_cost": standard_material,
        "standard_labor_cost": standard_labor,
        "standard_overhead_cost": standard_overhead,
        "standard_total_cost": standard_total,
        "actual_material_cost": actual_material,
        "actual_labor_cost": actual_labor,
        "actual_overhead_cost": actual_overhead,
        "actual_total_cost": actual_total,
        "material_price_variance": material_price,
        "material_usage_variance": material_usage,
        "labor_rate_variance": labor_rate,
        "labor_efficiency_variance": labor_efficiency,
        "overhead_spending_variance": overhead_spending,
        "overhead_volume_variance": overhead_volume,
        "abnormal_scrap_cost": abnormal_scrap,
        "residual_variance": residual,
        "total_variance": total_variance,
        "standard_unit_cost": quantity(standard_total / qty),
        "actual_unit_cost": quantity(actual_total / qty),
    }


@router.post("/orders/{order_id}/cost-close", status_code=201)
def prepare_cost_close(order_id: int, data: CostCloseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.scalar(select(ProductionOrder).where(ProductionOrder.id == order_id)
                      .options(selectinload(ProductionOrder.bom).selectinload(BillOfMaterial.lines).selectinload(BillOfMaterialLine.component_item)))
    if not order:
        raise HTTPException(404, "Production order not found")
    ensure_permission(db, user, order.company_id, "manufacturing.cost.prepare")
    if order.status != "COMPLETED":
        raise HTTPException(409, "Only completed production orders can be cost-closed")
    ensure_open_period(db, order.company_id, data.close_date)
    version = (db.scalar(select(func.max(ProductionCostClose.version)).where(ProductionCostClose.production_order_id == order.id)) or 0) + 1
    values = _calculate_cost_close(db, order, data.close_date)
    analysis_hash = _hash_cost_analysis({"order_id": order.id, "close_date": data.close_date, "version": version, **values})
    row = ProductionCostClose(company_id=order.company_id, production_order_id=order.id, close_date=data.close_date,
                              version=version, cost_method=data.cost_method, status="READY_FOR_REVIEW",
                              analysis_hash=analysis_hash, prepared_by=user.id, **values)
    db.add(row)
    db.flush()
    write_audit(db, action="PRODUCTION_COST_CLOSE_PREPARED", entity_type="PRODUCTION_COST_CLOSE", entity_id=row.id,
                user_id=user.id, company_id=order.company_id, after={"order": order.number, "total_variance": str(row.total_variance), "hash": row.analysis_hash})
    db.commit()
    db.refresh(row)
    return _cost_payload(row)


@router.post("/cost-closes/{close_id}/review")
def review_cost_close(close_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ProductionCostClose, close_id)
    if not row:
        raise HTTPException(404, "Production cost close not found")
    ensure_permission(db, user, row.company_id, "manufacturing.cost.review")
    if row.status != "READY_FOR_REVIEW":
        raise HTTPException(409, "Cost close is not ready for review")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Cost close preparer cannot review the same close")
    current_values = _calculate_cost_close(db, row.production_order, row.close_date)
    expected_hash = _hash_cost_analysis({"order_id": row.production_order_id, "close_date": row.close_date, "version": row.version, **current_values})
    if expected_hash != row.analysis_hash:
        raise HTTPException(409, "Underlying production cost data changed; prepare a new version")
    row.status = "REVIEWED"
    row.reviewed_by = user.id
    row.reviewed_at = utc_now()
    write_audit(db, action="PRODUCTION_COST_CLOSE_REVIEWED", entity_type="PRODUCTION_COST_CLOSE", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"status": row.status, "hash_verified": True})
    db.commit()
    return _cost_payload(row)


def _variance_journal_lines(db: Session, row: ProductionCostClose) -> list[dict]:
    variance_map = [
        ("624010", Decimal(row.material_price_variance), "Material price variance"),
        ("624020", Decimal(row.material_usage_variance), "Material usage variance"),
        ("624030", Decimal(row.labor_rate_variance), "Labor rate variance"),
        ("624040", Decimal(row.labor_efficiency_variance), "Labor efficiency variance"),
        ("624050", Decimal(row.overhead_spending_variance), "Overhead spending variance"),
        ("624060", Decimal(row.overhead_volume_variance), "Overhead volume variance"),
        ("624080", Decimal(row.residual_variance), "Production cost close residual"),
    ]
    lines: list[dict] = []
    for code, signed_amount, description in variance_map:
        amount = money(abs(signed_amount))
        if not amount:
            continue
        account = get_account(db, row.company_id, code)
        lines.append({"account_id": account.id, "debit": amount if signed_amount > 0 else ZERO,
                      "credit": amount if signed_amount < 0 else ZERO, "description": description})
    total = money(row.total_variance)
    if total:
        inventory = row.production_order.bom.finished_item.inventory_account_id
        lines.append({"account_id": inventory, "debit": money(abs(total)) if total < 0 else ZERO,
                      "credit": money(abs(total)) if total > 0 else ZERO,
                      "description": f"Standard cost adjustment {row.production_order.number}"})
    return lines


@router.post("/cost-closes/{close_id}/approve")
def approve_cost_close(close_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(ProductionCostClose).where(ProductionCostClose.id == close_id)
                    .options(selectinload(ProductionCostClose.production_order).selectinload(ProductionOrder.bom)))
    if not row:
        raise HTTPException(404, "Production cost close not found")
    ensure_permission(db, user, row.company_id, "manufacturing.cost.approve")
    if row.status != "REVIEWED":
        raise HTTPException(409, "Cost close must be reviewed before approval")
    if user.id in {row.prepared_by, row.reviewed_by}:
        raise HTTPException(409, "Cost close approver must be independent from preparer and reviewer")
    ensure_open_period(db, row.company_id, row.close_date)
    lines = _variance_journal_lines(db, row) if row.cost_method == "STANDARD" else []
    journal = None
    if lines:
        debit = money(sum((Decimal(line["debit"]) for line in lines), ZERO))
        credit = money(sum((Decimal(line["credit"]) for line in lines), ZERO))
        if debit != credit:
            raise HTTPException(500, f"Variance journal is not balanced: {debit} != {credit}")
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.close_date,
                                        reference=f"COST-{row.production_order.number}-V{row.version}",
                                        description=f"Production cost close {row.production_order.number}", lines=lines)
        row.journal_id = journal.id
    row.status = "POSTED"
    row.approved_by = user.id
    row.approved_at = utc_now()
    write_audit(db, action="PRODUCTION_COST_CLOSE_APPROVED", entity_type="PRODUCTION_COST_CLOSE", entity_id=row.id,
                user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "journal": journal.number if journal else None, "total_variance": str(row.total_variance)})
    db.commit()
    return _cost_payload(row)


@router.get("/cost-closes")
def list_cost_closes(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "manufacturing.read")
    rows = db.scalars(select(ProductionCostClose).where(ProductionCostClose.company_id == company_id)
                      .options(selectinload(ProductionCostClose.production_order))
                      .order_by(ProductionCostClose.id.desc())).all()
    return [_cost_payload(row) for row in rows]


@router.get("/dashboard")
def advanced_manufacturing_dashboard(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "manufacturing.read")
    routing_count = db.scalar(select(func.count(ManufacturingRouting.id)).where(ManufacturingRouting.company_id == company_id, ManufacturingRouting.status == "APPROVED")) or 0
    mrp_runs = db.scalar(select(func.count(MRPPlanRun.id)).where(MRPPlanRun.company_id == company_id)) or 0
    mrp_shortage = db.scalar(select(func.coalesce(func.sum(MRPPlanRun.total_shortage), 0)).where(MRPPlanRun.company_id == company_id, MRPPlanRun.status.in_(["CALCULATED", "APPROVED"]))) or 0
    operation_total = db.scalar(select(func.count(ProductionOperationLog.id)).where(ProductionOperationLog.company_id == company_id)) or 0
    operation_open = db.scalar(select(func.count(ProductionOperationLog.id)).where(ProductionOperationLog.company_id == company_id, ProductionOperationLog.status != "COMPLETED")) or 0
    scrap_qty = db.scalar(select(func.coalesce(func.sum(ProductionScrapRecord.quantity), 0)).where(ProductionScrapRecord.company_id == company_id)) or 0
    abnormal_scrap = db.scalar(select(func.coalesce(func.sum(ProductionScrapRecord.total_cost), 0)).where(ProductionScrapRecord.company_id == company_id, ProductionScrapRecord.classification == "ABNORMAL")) or 0
    closed_orders = db.scalar(select(func.count(ProductionCostClose.id)).where(ProductionCostClose.company_id == company_id, ProductionCostClose.status == "POSTED")) or 0
    total_variance = db.scalar(select(func.coalesce(func.sum(ProductionCostClose.total_variance), 0)).where(ProductionCostClose.company_id == company_id, ProductionCostClose.status == "POSTED")) or 0
    return {
        "approved_routings": routing_count,
        "mrp_runs": mrp_runs,
        "mrp_shortage": money(mrp_shortage),
        "operations": operation_total,
        "open_operations": operation_open,
        "scrap_quantity": quantity(scrap_qty),
        "abnormal_scrap_cost": money(abnormal_scrap),
        "posted_cost_closes": closed_orders,
        "total_cost_variance": money(total_variance),
    }
