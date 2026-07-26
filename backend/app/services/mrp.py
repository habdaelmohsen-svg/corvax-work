from __future__ import annotations

import json
import math
import secrets
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.models import (
    BackgroundJob,
    BillOfMaterial,
    BillOfMaterialLine,
    ManufacturingRouting,
    ManufacturingRoutingOperation,
    MRPCapacityAllocation,
    MRPDemandLine,
    MRPPlanRun,
    MRPRequirementLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierItemPlanning,
    WorkCenterCalendarDay,
)
from app.services.audit import write_audit
from app.services.operations import get_item, get_warehouse, quantity, stock_balance

ZERO = Decimal("0")


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _as_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _active_bom(db: Session, company_id: int, item_id: int) -> BillOfMaterial | None:
    return db.scalar(
        select(BillOfMaterial)
        .where(
            BillOfMaterial.company_id == company_id,
            BillOfMaterial.finished_item_id == item_id,
            BillOfMaterial.status == "ACTIVE",
        )
        .options(selectinload(BillOfMaterial.lines).selectinload(BillOfMaterialLine.component_item))
        .order_by(BillOfMaterial.version.desc())
    )


def _approved_routing(db: Session, company_id: int, item_id: int, due_date: date) -> ManufacturingRouting | None:
    return db.scalar(
        select(ManufacturingRouting)
        .where(
            ManufacturingRouting.company_id == company_id,
            ManufacturingRouting.finished_item_id == item_id,
            ManufacturingRouting.status == "APPROVED",
            ManufacturingRouting.effective_from <= due_date,
            (ManufacturingRouting.effective_to.is_(None) | (ManufacturingRouting.effective_to >= due_date)),
        )
        .options(selectinload(ManufacturingRouting.operations))
        .order_by(ManufacturingRouting.version.desc())
    )


def _production_receipts(db: Session, company_id: int, warehouse_id: int, item_id: int, horizon_end: date) -> Decimal:
    from app.models import ProductionOrder

    value = db.scalar(
        select(func.coalesce(func.sum(ProductionOrder.planned_quantity - ProductionOrder.completed_quantity), 0))
        .join(BillOfMaterial, ProductionOrder.bom_id == BillOfMaterial.id)
        .where(
            ProductionOrder.company_id == company_id,
            ProductionOrder.warehouse_id == warehouse_id,
            BillOfMaterial.finished_item_id == item_id,
            ProductionOrder.order_date <= horizon_end,
            ProductionOrder.status.in_(["RELEASED", "IN_PROCESS"]),
        )
    )
    return quantity(value or 0)


def _purchase_receipts(db: Session, company_id: int, warehouse_id: int, item_id: int, horizon_end: date) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(PurchaseOrderLine.quantity - PurchaseOrderLine.received_quantity), 0))
        .join(PurchaseOrder, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .where(
            PurchaseOrder.company_id == company_id,
            PurchaseOrder.warehouse_id == warehouse_id,
            PurchaseOrderLine.item_id == item_id,
            PurchaseOrder.status.in_(["APPROVED", "PARTIALLY_RECEIVED"]),
            func.coalesce(PurchaseOrder.expected_receipt_date, PurchaseOrder.order_date) <= horizon_end,
        )
    )
    return quantity(value or 0)


def _supplier_plan(db: Session, company_id: int, item_id: int) -> SupplierItemPlanning | None:
    return db.scalar(
        select(SupplierItemPlanning)
        .where(
            SupplierItemPlanning.company_id == company_id,
            SupplierItemPlanning.item_id == item_id,
            SupplierItemPlanning.active.is_(True),
        )
        .order_by(SupplierItemPlanning.preferred.desc(), SupplierItemPlanning.lead_time_days.asc(), SupplierItemPlanning.id.asc())
    )


def _round_multiple(value: Decimal, multiple: Decimal) -> Decimal:
    if multiple <= 0:
        return quantity(value)
    units = (value / multiple).to_integral_value(rounding=ROUND_CEILING)
    return quantity(units * multiple)


def apply_lot_sizing(net: Decimal, plan: SupplierItemPlanning | None) -> tuple[Decimal, str]:
    if net <= 0:
        return ZERO, (plan.lot_sizing_policy if plan else "LFL")
    if not plan:
        return quantity(net), "LFL"
    policy = (plan.lot_sizing_policy or "LFL").upper()
    minimum = _as_decimal(plan.minimum_order_quantity)
    multiple = _as_decimal(plan.order_multiple) or Decimal("1")
    target = max(net, minimum)
    if policy == "FOQ" and plan.fixed_order_quantity:
        target = max(target, _as_decimal(plan.fixed_order_quantity))
    elif policy == "EOQ":
        annual = _as_decimal(plan.eoq_annual_demand)
        order_cost = _as_decimal(plan.eoq_order_cost)
        holding = _as_decimal(plan.eoq_holding_cost)
        if annual > 0 and order_cost > 0 and holding > 0:
            eoq = Decimal(str(math.sqrt(float((Decimal("2") * annual * order_cost) / holding))))
            target = max(target, eoq)
    elif policy == "POQ" and plan.fixed_order_quantity:
        target = max(target, _as_decimal(plan.fixed_order_quantity))
    elif policy not in {"LFL", "MIN_MAX", "FOQ", "EOQ", "POQ"}:
        policy = "LFL"
    return _round_multiple(target, multiple), policy


def _allocate_finite_capacity(
    db: Session,
    *,
    run: MRPPlanRun,
    requirement: MRPRequirementLine,
    routing: ManufacturingRouting,
    quantity_needed: Decimal,
    planning_date: date,
    due_date: date,
) -> tuple[date, str]:
    cursor = due_date
    overall_status = "ALLOCATED"
    # Back-schedule the routing so the final operation finishes on the due date.
    for operation in sorted(routing.operations, key=lambda row: row.sequence, reverse=True):
        required = quantity(
            Decimal(operation.setup_minutes)
            + Decimal(operation.queue_minutes)
            + Decimal(operation.move_minutes)
            + Decimal(operation.run_minutes_per_unit) * quantity_needed
        )
        remaining = required
        calendars = db.scalars(
            select(WorkCenterCalendarDay)
            .where(
                WorkCenterCalendarDay.company_id == run.company_id,
                WorkCenterCalendarDay.work_center_id == operation.work_center_id,
                WorkCenterCalendarDay.work_date >= planning_date,
                WorkCenterCalendarDay.work_date <= cursor,
                WorkCenterCalendarDay.active.is_(True),
            )
            .order_by(WorkCenterCalendarDay.work_date.desc())
        ).all()
        if not calendars:
            overall_status = "NO_CALENDAR"
            # Conservative fallback for visibility only; it is explicitly marked unconfirmed.
            business_days = max(1, math.ceil(float(required / Decimal("480"))))
            cursor = max(planning_date, cursor - timedelta(days=business_days))
            continue
        for calendar in calendars:
            available = max(Decimal(calendar.available_minutes) - Decimal(calendar.reserved_minutes), ZERO)
            if available <= 0:
                continue
            allocated = min(available, remaining)
            calendar.reserved_minutes = quantity(Decimal(calendar.reserved_minutes) + allocated)
            db.add(
                MRPCapacityAllocation(
                    run_id=run.id,
                    requirement_line_id=requirement.id,
                    work_center_id=operation.work_center_id,
                    operation_sequence=operation.sequence,
                    work_date=calendar.work_date,
                    allocated_minutes=allocated,
                    capacity_status="ALLOCATED",
                )
            )
            remaining -= allocated
            cursor = min(cursor, calendar.work_date)
            if remaining <= 0:
                break
        if remaining > 0:
            overall_status = "INSUFFICIENT_CAPACITY"
            db.add(
                MRPCapacityAllocation(
                    run_id=run.id,
                    requirement_line_id=requirement.id,
                    work_center_id=operation.work_center_id,
                    operation_sequence=operation.sequence,
                    work_date=planning_date,
                    allocated_minutes=remaining,
                    capacity_status="UNALLOCATED",
                )
            )
            cursor = planning_date
    return cursor, overall_status


def calculate_mrp(db: Session, payload: dict, *, user_id: int, background_job_id: str | None = None) -> MRPPlanRun:
    company_id = int(payload["company_id"])
    warehouse_id = int(payload["warehouse_id"])
    planning_date = _as_date(payload["planning_date"])
    horizon_end = _as_date(payload["horizon_end"])
    warehouse = get_warehouse(db, company_id, warehouse_id)
    code = f"MRP-{company_id}-{planning_date.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
    run = MRPPlanRun(
        company_id=company_id,
        code=code,
        warehouse_id=warehouse.id,
        planning_date=planning_date,
        horizon_end=horizon_end,
        status="CALCULATING",
        execution_mode="BACKGROUND" if background_job_id else "INLINE_TEST",
        background_job_id=background_job_id,
        progress_percent=5,
        created_by=user_id,
    )
    db.add(run)
    db.flush()

    gross_total = ZERO
    on_hand_total = ZERO
    scheduled_total = ZERO
    shortage_total = ZERO
    planned_total = ZERO
    consumed_on_hand: dict[int, Decimal] = {}
    consumed_production: dict[int, Decimal] = {}
    consumed_purchase: dict[int, Decimal] = {}

    def explode(item_id: int, gross: Decimal, due: date, safety: Decimal, parent_item_id: int | None, level: int, path: tuple[int, ...]):
        nonlocal gross_total, on_hand_total, scheduled_total, shortage_total, planned_total
        if item_id in path:
            cycle = " -> ".join(str(x) for x in (*path, item_id))
            raise HTTPException(422, f"Circular BOM detected: {cycle}")
        item = get_item(db, company_id, item_id)
        available_raw = stock_balance(db, company_id, warehouse.id, item.id)
        available = max(available_raw - consumed_on_hand.get(item.id, ZERO), ZERO)
        prod_raw = _production_receipts(db, company_id, warehouse.id, item.id, horizon_end)
        prod_available = max(prod_raw - consumed_production.get(item.id, ZERO), ZERO)
        po_raw = _purchase_receipts(db, company_id, warehouse.id, item.id, horizon_end)
        po_available = max(po_raw - consumed_purchase.get(item.id, ZERO), ZERO)
        need = quantity(gross + safety)
        use_on_hand = min(available, need)
        remaining = need - use_on_hand
        use_production = min(prod_available, remaining)
        remaining -= use_production
        use_purchase = min(po_available, remaining)
        net = quantity(max(remaining - use_purchase, ZERO))
        consumed_on_hand[item.id] = consumed_on_hand.get(item.id, ZERO) + use_on_hand
        consumed_production[item.id] = consumed_production.get(item.id, ZERO) + use_production
        consumed_purchase[item.id] = consumed_purchase.get(item.id, ZERO) + use_purchase

        bom = _active_bom(db, company_id, item.id)
        supplier_plan = None if bom else _supplier_plan(db, company_id, item.id)
        planned_qty, lot_policy = apply_lot_sizing(net, supplier_plan)
        lead_time = int(supplier_plan.lead_time_days) if supplier_plan else 0
        receipt_date = due if planned_qty > 0 else None
        release_date = max(planning_date, due - timedelta(days=lead_time)) if planned_qty > 0 else None
        supply_type = "MAKE" if bom else "BUY"
        action = "CREATE_PRODUCTION_ORDER" if planned_qty > 0 and bom else "CREATE_PURCHASE_REQUISITION" if planned_qty > 0 else "NONE"
        requirement = MRPRequirementLine(
            run_id=run.id,
            parent_item_id=parent_item_id,
            item_id=item.id,
            bom_id=bom.id if bom else None,
            level=level,
            due_date=due,
            gross_requirement=quantity(gross),
            on_hand=quantity(use_on_hand),
            scheduled_receipts=quantity(use_production + use_purchase),
            production_receipts=quantity(use_production),
            purchase_receipts=quantity(use_purchase),
            safety_stock=quantity(safety),
            net_requirement=net,
            planned_order_quantity=planned_qty,
            planned_receipt_date=receipt_date,
            planned_release_date=release_date,
            supplier_id=supplier_plan.supplier_id if supplier_plan else None,
            lead_time_days=lead_time,
            lot_sizing_policy=lot_policy,
            capacity_status="PENDING" if bom and planned_qty > 0 else "NOT_APPLICABLE",
            supply_type=supply_type,
            action_message=action,
        )
        run.requirements.append(requirement)
        db.flush()

        if bom and planned_qty > 0:
            routing = _approved_routing(db, company_id, item.id, due)
            if routing:
                release_date, capacity_status = _allocate_finite_capacity(
                    db,
                    run=run,
                    requirement=requirement,
                    routing=routing,
                    quantity_needed=planned_qty,
                    planning_date=planning_date,
                    due_date=due,
                )
                requirement.planned_release_date = release_date
                requirement.capacity_status = capacity_status
            else:
                requirement.capacity_status = "NO_APPROVED_ROUTING"

        gross_total += quantity(gross)
        on_hand_total += quantity(use_on_hand)
        scheduled_total += quantity(use_production + use_purchase)
        shortage_total += net
        planned_total += planned_qty
        if bom and planned_qty > 0:
            factor = planned_qty / Decimal(bom.output_quantity)
            component_due = requirement.planned_release_date or due
            for component in bom.lines:
                component_gross = quantity(
                    factor * Decimal(component.quantity) * (Decimal("1") + Decimal(component.scrap_percent) / Decimal("100"))
                )
                explode(component.component_item_id, component_gross, component_due, ZERO, item.id, level + 1, (*path, item.id))

    demands = payload.get("demands") or []
    total_demands = max(1, len(demands))
    for idx, source in enumerate(demands, start=1):
        item = get_item(db, company_id, int(source["item_id"]))
        due = _as_date(source["due_date"])
        demand_qty = quantity(source["quantity"])
        safety = quantity(source.get("safety_stock", 0))
        run.demands.append(
            MRPDemandLine(
                item_id=item.id,
                due_date=due,
                quantity=demand_qty,
                safety_stock=safety,
                source_type=str(source.get("source_type", "FORECAST")).strip().upper(),
                source_reference=source.get("source_reference"),
            )
        )
        explode(item.id, demand_qty, due, safety, None, 0, tuple())
        run.progress_percent = min(95, 5 + int((idx / total_demands) * 90))

    run.gross_demand = quantity(gross_total)
    run.total_on_hand = quantity(on_hand_total)
    run.total_scheduled_receipts = quantity(scheduled_total)
    run.total_shortage = quantity(shortage_total)
    run.total_planned_supply = quantity(planned_total)
    run.status = "CALCULATED"
    run.progress_percent = 100
    write_audit(
        db,
        action="MRP_PLAN_CALCULATED",
        entity_type="MRP_PLAN_RUN",
        entity_id=run.id,
        user_id=user_id,
        company_id=company_id,
        after={
            "code": run.code,
            "requirements": len(run.requirements),
            "shortage": str(run.total_shortage),
            "po_receipts_included": True,
            "finite_capacity": True,
            "lot_sizing": True,
        },
    )
    db.flush()
    return run


def enqueue_mrp_job(db: Session, payload: dict, *, user_id: int) -> BackgroundJob:
    company_id = int(payload["company_id"])
    idempotency_source = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    import hashlib

    idempotency_key = hashlib.sha256(idempotency_source.encode()).hexdigest()[:64]
    existing = db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.company_id == company_id,
            BackgroundJob.job_type == "MRP_RUN",
            BackgroundJob.idempotency_key == idempotency_key,
            BackgroundJob.status.in_(["QUEUED", "RUNNING", "COMPLETED"]),
        )
    )
    if existing:
        return existing
    job = BackgroundJob(
        id=secrets.token_urlsafe(32),
        company_id=company_id,
        job_type="MRP_RUN",
        idempotency_key=idempotency_key,
        status="QUEUED",
        payload_json=idempotency_source,
        progress_percent=0,
        max_attempts=3,
        next_attempt_at=utc_now(),
        created_by=user_id,
    )
    db.add(job)
    db.flush()
    write_audit(
        db,
        action="MRP_JOB_QUEUED",
        entity_type="BACKGROUND_JOB",
        entity_id=job.id,
        user_id=user_id,
        company_id=company_id,
        after={"job_type": job.job_type, "idempotency_key": idempotency_key},
    )
    return job


def process_mrp_job(db: Session, job: BackgroundJob, *, worker_id: str) -> MRPPlanRun:
    if job.status not in {"QUEUED", "RETRY"}:
        raise ValueError(f"Job {job.id} is not executable from status {job.status}")
    job.status = "RUNNING"
    job.locked_by = worker_id
    job.locked_at = utc_now()
    job.started_at = utc_now()
    job.attempts += 1
    job.progress_percent = 1
    db.flush()
    try:
        run = calculate_mrp(db, json.loads(job.payload_json), user_id=job.created_by, background_job_id=job.id)
        job.status = "COMPLETED"
        job.progress_percent = 100
        job.result_reference = f"MRP_PLAN_RUN:{run.id}"
        job.completed_at = utc_now()
        return run
    except Exception as exc:
        job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        job.status = "RETRY" if job.attempts < job.max_attempts else "FAILED"
        job.next_attempt_at = utc_now() + timedelta(minutes=min(30, 2 ** job.attempts))
        raise


def claim_next_mrp_job(db: Session, *, worker_id: str) -> BackgroundJob | None:
    """Atomically claim the next due MRP job.

    PostgreSQL uses SKIP LOCKED so multiple workers can operate safely. SQLite is
    supported for local development and tests, where a single worker is expected.
    """
    now = utc_now()
    statement = (
        select(BackgroundJob)
        .where(
            BackgroundJob.job_type == "MRP_RUN",
            BackgroundJob.status.in_(["QUEUED", "RETRY"]),
            BackgroundJob.next_attempt_at <= now,
        )
        .order_by(BackgroundJob.created_at, BackgroundJob.id)
        .limit(1)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    job = db.scalar(statement)
    if job is None:
        return None
    job.status = "RUNNING"
    job.locked_by = worker_id
    job.locked_at = now
    job.started_at = job.started_at or now
    job.attempts += 1
    job.progress_percent = max(job.progress_percent, 1)
    db.flush()
    return job


def execute_claimed_mrp_job(db: Session, job: BackgroundJob, *, worker_id: str) -> MRPPlanRun:
    if job.status != "RUNNING" or job.locked_by != worker_id:
        raise ValueError("Background job must be claimed by this worker before execution")
    try:
        run = calculate_mrp(db, json.loads(job.payload_json), user_id=job.created_by, background_job_id=job.id)
        job.status = "COMPLETED"
        job.progress_percent = 100
        job.result_reference = f"MRP_PLAN_RUN:{run.id}"
        job.completed_at = utc_now()
        job.error_message = None
        db.commit()
        return run
    except Exception as exc:
        db.rollback()
        # Re-load the row after rollback so the failure state is durable.
        failed = db.get(BackgroundJob, job.id)
        if failed is not None:
            failed.attempts = max(failed.attempts, job.attempts)
            failed.locked_by = None
            failed.locked_at = None
            failed.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            failed.status = "RETRY" if failed.attempts < failed.max_attempts else "FAILED"
            failed.next_attempt_at = utc_now() + timedelta(minutes=min(30, 2 ** failed.attempts))
            db.commit()
        raise
