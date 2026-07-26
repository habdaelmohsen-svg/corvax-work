from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, AssetLifecycleTransaction, BackupRecord, BankStatement, BankStatementLine, CloseOrchestrationCheck,
    CloseOrchestrationRun, CreditNote, DeferredTaxRun, ExciseTaxReturn, FiscalPeriod, FiscalYear,
    InternalCostRun, InternalCostVarianceLine, JournalEntry, JournalLine, LeadSchedule, PayrollRun,
    PlanningScenario, PlanningScenarioLine, ProductionOrder, ReadinessAssessment,
    ReadinessAssessmentCheck, StockMovement, User, VatReturnSnapshot, WithholdingTaxReturn,
    ZakatIncomeTaxReturn,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal, ensure_open_period

router = APIRouter(prefix="/internal-completion", tags=["final internal completion"])
ZERO = Decimal("0")
Q4 = Decimal("0.0001")
Q6 = Decimal("0.000001")
from app.core.migration_head import expected_migration_head

EXPECTED_HEAD = expected_migration_head()


def dec(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def qty(value: Any) -> Decimal:
    return dec(value).quantize(Q4, rounding=ROUND_HALF_UP)


def rate(value: Any) -> Decimal:
    return dec(value).quantize(Q6, rounding=ROUND_HALF_UP)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


def sha(value: Any) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def csv_response(filename: str, headers: list[str], rows: list[list[Any]]) -> Response:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    content = "\ufeff" + stream.getvalue()
    return Response(content=content.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------------------------------------------------------------------------
# Advanced manufacturing cost bridge
# ---------------------------------------------------------------------------


class MaterialVarianceIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name_ar: str = Field(min_length=1, max_length=250)
    name_en: str = Field(min_length=1, max_length=250)
    standard_quantity: Decimal = Field(gt=0)
    actual_quantity: Decimal = Field(ge=0)
    standard_price: Decimal = Field(ge=0)
    actual_price: Decimal = Field(ge=0)
    source_reference: str | None = Field(default=None, max_length=250)


class LaborVarianceIn(BaseModel):
    standard_hours: Decimal = Field(ge=0)
    actual_hours: Decimal = Field(ge=0)
    standard_rate: Decimal = Field(ge=0)
    actual_rate: Decimal = Field(ge=0)


class OverheadVarianceIn(BaseModel):
    standard_variable_rate: Decimal = Field(ge=0)
    actual_variable_rate: Decimal = Field(ge=0)
    standard_fixed_rate: Decimal = Field(ge=0)
    budgeted_fixed_overhead: Decimal = Field(ge=0)
    actual_fixed_overhead: Decimal = Field(ge=0)
    normal_capacity_hours: Decimal = Field(gt=0)
    productive_hours: Decimal = Field(ge=0)


class JointOutputIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0)
    selling_price: Decimal = Field(ge=0)
    separable_cost: Decimal = Field(default=0, ge=0)
    is_byproduct: bool = False


class ServiceAllocationIn(BaseModel):
    target_code: str = Field(min_length=1, max_length=80)
    percent: Decimal = Field(gt=0, le=1)


class ServicePoolIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name_ar: str = Field(min_length=1, max_length=250)
    name_en: str = Field(min_length=1, max_length=250)
    direct_cost: Decimal = Field(ge=0)
    allocations: list[ServiceAllocationIn] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_allocations(self):
        total = sum((dec(x.percent) for x in self.allocations), ZERO)
        if abs(total - Decimal("1")) > Decimal("0.000001"):
            raise ValueError("Service-pool allocation percentages must total 1.0")
        if len({x.target_code.upper() for x in self.allocations}) != len(self.allocations):
            raise ValueError("Duplicate service-pool allocation target")
        return self


class CostRunIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=60)
    period_start: date
    period_end: date
    posting_date: date
    standard_output_quantity: Decimal = Field(gt=0)
    actual_output_quantity: Decimal = Field(gt=0)
    materials: list[MaterialVarianceIn] = Field(min_length=1)
    labor: LaborVarianceIn
    overhead: OverheadVarianceIn
    joint_cost_total: Decimal = Field(default=0, ge=0)
    joint_outputs: list[JointOutputIn] = Field(default_factory=list)
    service_pools: list[ServicePoolIn] = Field(default_factory=list)
    rework_cost: Decimal = Field(default=0, ge=0)
    reference: str | None = Field(default=None, max_length=250)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot be before period_start")
        if not (self.period_start <= self.posting_date <= self.period_end):
            raise ValueError("posting_date must fall inside the cost period")
        if self.joint_cost_total and not self.joint_outputs:
            raise ValueError("joint_outputs are required when joint_cost_total is provided")
        return self


def _line(category: str, code: str, ar: str, en: str, amount: Decimal, account: str | None,
          *, sq: Decimal = ZERO, aq: Decimal = ZERO, sr: Decimal = ZERO, arate: Decimal = ZERO,
          posting: bool = True, reference: str | None = None) -> dict:
    signed = money(amount)
    return {
        "category": category, "component_code": code, "description_ar": ar, "description_en": en,
        "standard_quantity": qty(sq), "actual_quantity": qty(aq),
        "standard_rate": rate(sr), "actual_rate": rate(arate), "amount": signed,
        "favorable": signed < 0, "posting_effect": posting, "account_code": account,
        "source_reference": reference,
    }


def _calculate_cost(data: CostRunIn) -> tuple[list[dict], dict, dict]:
    output_factor = dec(data.actual_output_quantity) / dec(data.standard_output_quantity)
    allowed = {m.code.upper(): dec(m.standard_quantity) * output_factor for m in data.materials}
    allowed_total = sum(allowed.values(), ZERO)
    actual_total_qty = sum((dec(m.actual_quantity) for m in data.materials), ZERO)
    if allowed_total <= 0:
        raise HTTPException(422, "Standard material input must be positive")
    weighted_standard_price = sum((allowed[m.code.upper()] * dec(m.standard_price) for m in data.materials), ZERO) / allowed_total
    rows: list[dict] = []
    standard_material = ZERO
    actual_material = ZERO
    sequence = 1
    for material in data.materials:
        code = material.code.upper()
        std_allowed = allowed[code]
        standard_price = dec(material.standard_price)
        actual_quantity = dec(material.actual_quantity)
        actual_price = dec(material.actual_price)
        standard_material += std_allowed * standard_price
        actual_material += actual_quantity * actual_price
        revised_standard_qty = actual_total_qty * (std_allowed / allowed_total)
        price_variance = actual_quantity * (actual_price - standard_price)
        mix_variance = standard_price * (actual_quantity - revised_standard_qty)
        rows.append(_line("MATERIAL_PRICE", code, f"انحراف سعر المادة {material.name_ar}", f"Material price variance — {material.name_en}", price_variance, "624010", sq=std_allowed, aq=actual_quantity, sr=standard_price, arate=actual_price, reference=material.source_reference))
        rows.append(_line("MATERIAL_MIX", code, f"انحراف مزيج المادة {material.name_ar}", f"Material mix variance — {material.name_en}", mix_variance, "624120", sq=revised_standard_qty, aq=actual_quantity, sr=standard_price, arate=actual_price, reference=material.source_reference))
        sequence += 2
    yield_variance = weighted_standard_price * (actual_total_qty - allowed_total)
    rows.append(_line("MATERIAL_YIELD", "TOTAL_INPUT", "انحراف عائد المواد", "Material yield variance", yield_variance, "624130", sq=allowed_total, aq=actual_total_qty, sr=weighted_standard_price, arate=weighted_standard_price))

    standard_hours = dec(data.labor.standard_hours) * output_factor
    actual_hours = dec(data.labor.actual_hours)
    standard_labor_rate = dec(data.labor.standard_rate)
    actual_labor_rate = dec(data.labor.actual_rate)
    standard_labor = standard_hours * standard_labor_rate
    actual_labor = actual_hours * actual_labor_rate
    rows.append(_line("LABOR_RATE", "DIRECT_LABOR", "انحراف معدل الأجور", "Labor rate variance", actual_hours * (actual_labor_rate - standard_labor_rate), "624030", sq=standard_hours, aq=actual_hours, sr=standard_labor_rate, arate=actual_labor_rate))
    rows.append(_line("LABOR_EFFICIENCY", "DIRECT_LABOR", "انحراف كفاءة العمالة", "Labor efficiency variance", (actual_hours - standard_hours) * standard_labor_rate, "624040", sq=standard_hours, aq=actual_hours, sr=standard_labor_rate, arate=actual_labor_rate))

    std_var_rate = dec(data.overhead.standard_variable_rate)
    act_var_rate = dec(data.overhead.actual_variable_rate)
    std_fixed_rate = dec(data.overhead.standard_fixed_rate)
    budget_fixed = dec(data.overhead.budgeted_fixed_overhead)
    actual_fixed = dec(data.overhead.actual_fixed_overhead)
    normal_capacity = dec(data.overhead.normal_capacity_hours)
    productive_hours = dec(data.overhead.productive_hours)
    standard_variable_oh = standard_hours * std_var_rate
    actual_variable_oh = actual_hours * act_var_rate
    applied_fixed_oh = standard_hours * std_fixed_rate
    rows.append(_line("VARIABLE_OH_SPENDING", "VARIABLE_OH", "انحراف إنفاق التكاليف الصناعية المتغيرة", "Variable overhead spending variance", actual_hours * (act_var_rate - std_var_rate), "624050", sq=standard_hours, aq=actual_hours, sr=std_var_rate, arate=act_var_rate))
    rows.append(_line("VARIABLE_OH_EFFICIENCY", "VARIABLE_OH", "انحراف كفاءة التكاليف الصناعية المتغيرة", "Variable overhead efficiency variance", (actual_hours - standard_hours) * std_var_rate, "624140", sq=standard_hours, aq=actual_hours, sr=std_var_rate, arate=act_var_rate))
    rows.append(_line("FIXED_OH_BUDGET", "FIXED_OH", "انحراف موازنة التكاليف الصناعية الثابتة", "Fixed overhead budget variance", actual_fixed - budget_fixed, "624150", sq=normal_capacity, aq=productive_hours, sr=std_fixed_rate, arate=(actual_fixed / productive_hours if productive_hours else ZERO)))
    rows.append(_line("FIXED_OH_VOLUME", "FIXED_OH", "انحراف حجم الإنتاج والطاقة", "Fixed overhead volume variance", budget_fixed - applied_fixed_oh, "624060", sq=normal_capacity, aq=standard_hours, sr=std_fixed_rate, arate=std_fixed_rate))
    idle_capacity_cost = max(normal_capacity - productive_hours, ZERO) * std_fixed_rate
    rows.append(_line("IDLE_CAPACITY_MEMO", "IDLE_CAPACITY", "تكلفة الطاقة العاطلة — بند تحليلي", "Idle capacity cost — analytical memo", idle_capacity_cost, "624160", sq=normal_capacity, aq=productive_hours, sr=std_fixed_rate, arate=std_fixed_rate, posting=False))

    joint_allocations: list[dict] = []
    byproduct_credit = ZERO
    if data.joint_outputs:
        nrv_map = {x.code.upper(): max(dec(x.quantity) * dec(x.selling_price) - dec(x.separable_cost), ZERO) for x in data.joint_outputs}
        byproduct_credit = min(sum((nrv_map[x.code.upper()] for x in data.joint_outputs if x.is_byproduct), ZERO), dec(data.joint_cost_total))
        allocable = max(dec(data.joint_cost_total) - byproduct_credit, ZERO)
        main_total = sum((nrv_map[x.code.upper()] for x in data.joint_outputs if not x.is_byproduct), ZERO)
        if allocable and main_total <= 0:
            raise HTTPException(422, "Main joint products require positive NRV")
        for output in data.joint_outputs:
            code = output.code.upper()
            if output.is_byproduct:
                allocated = -nrv_map[code]
                method = "BYPRODUCT_NRV_CREDIT"
            else:
                allocated = allocable * nrv_map[code] / main_total if main_total else ZERO
                method = "NRV_ALLOCATION"
            joint_allocations.append({"code": code, "method": method, "nrv": str(money(nrv_map[code])), "allocated_cost": str(money(allocated))})
            rows.append(_line("JOINT_COST_ALLOCATION", code, f"توزيع التكلفة المشتركة على {code}", f"Joint-cost allocation to {code}", allocated, None, aq=dec(output.quantity), arate=(allocated / dec(output.quantity) if output.quantity else ZERO), posting=False))

    service_allocations: list[dict] = []
    pool_codes = [pool.code.upper() for pool in data.service_pools]
    accumulated = {code: ZERO for code in pool_codes}
    service_production_total = ZERO
    for index, pool in enumerate(data.service_pools):
        code = pool.code.upper()
        pool_total = dec(pool.direct_cost) + accumulated[code]
        allowed_later = set(pool_codes[index + 1:])
        for allocation in pool.allocations:
            target = allocation.target_code.upper()
            amount = pool_total * dec(allocation.percent)
            if target in allowed_later:
                accumulated[target] += amount
                target_type = "SERVICE_DEPARTMENT"
            elif target in set(pool_codes[:index + 1]):
                raise HTTPException(422, "Step-down allocation cannot allocate back to an already closed service department")
            else:
                service_production_total += amount
                target_type = "PRODUCTION_CENTER"
            service_allocations.append({"pool": code, "target": target, "target_type": target_type, "percent": str(rate(allocation.percent)), "amount": str(money(amount))})
            rows.append(_line("SERVICE_DEPARTMENT_ALLOCATION", f"{code}->{target}", f"توزيع قسم الخدمة {pool.name_ar} إلى {target}", f"Service department allocation {pool.name_en} to {target}", amount, None, posting=False))

    if dec(data.rework_cost):
        rows.append(_line("REWORK", "REWORK", "تكلفة إعادة التشغيل", "Rework cost", dec(data.rework_cost), "624170", posting=True, reference=data.reference))

    standard_total = standard_material + standard_labor + standard_variable_oh + applied_fixed_oh + max(dec(data.joint_cost_total) - byproduct_credit, ZERO) + service_production_total
    actual_total = actual_material + actual_labor + actual_variable_oh + actual_fixed + max(dec(data.joint_cost_total) - byproduct_credit, ZERO) + service_production_total + dec(data.rework_cost)
    posting_total = sum((dec(row["amount"]) for row in rows if row["posting_effect"]), ZERO)
    residual = money((actual_total - standard_total) - posting_total)
    if abs(residual) >= Decimal("0.01"):
        rows.append(_line("COST_BRIDGE_RESIDUAL", "RESIDUAL", "فرق ربط تكلفة الإنتاج", "Production cost bridge residual", residual, "624080", posting=True))
        posting_total += residual
    under_over_absorption = (actual_variable_oh + actual_fixed) - (standard_variable_oh + applied_fixed_oh)
    summary = {
        "standard_material": str(money(standard_material)), "actual_material": str(money(actual_material)),
        "standard_labor": str(money(standard_labor)), "actual_labor": str(money(actual_labor)),
        "standard_variable_overhead": str(money(standard_variable_oh)), "actual_variable_overhead": str(money(actual_variable_oh)),
        "applied_fixed_overhead": str(money(applied_fixed_oh)), "actual_fixed_overhead": str(money(actual_fixed)),
        "standard_total_cost": str(money(standard_total)), "actual_total_cost": str(money(actual_total)),
        "total_variance": str(money(posting_total)), "idle_capacity_cost": str(money(idle_capacity_cost)),
        "under_over_absorption": str(money(under_over_absorption)), "weighted_standard_material_price": str(rate(weighted_standard_price)),
    }
    allocations = {"joint_outputs": joint_allocations, "service_department_step_down": service_allocations}
    return rows, summary, allocations


def _cost_integrity_payload(row: InternalCostRun) -> dict:
    return {
        "company_id": row.company_id, "code": row.code, "version": row.version,
        "period_start": row.period_start, "period_end": row.period_end, "posting_date": row.posting_date,
        "standard_output_quantity": row.standard_output_quantity, "actual_output_quantity": row.actual_output_quantity,
        "summary": loads(row.summary_payload, {}), "allocations": loads(row.allocation_payload, {}),
        "lines": [
            {"sequence": x.sequence, "category": x.category, "component_code": x.component_code,
             "amount": x.amount, "posting_effect": x.posting_effect, "account_code": x.account_code}
            for x in sorted(row.lines, key=lambda item: item.sequence)
        ],
    }


def _cost_payload(row: InternalCostRun) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "code": row.code, "version": row.version,
        "period_start": row.period_start, "period_end": row.period_end, "posting_date": row.posting_date,
        "status": row.status, "standard_output_quantity": row.standard_output_quantity,
        "actual_output_quantity": row.actual_output_quantity, "total_standard_cost": row.total_standard_cost,
        "total_actual_cost": row.total_actual_cost, "total_variance": row.total_variance,
        "idle_capacity_cost": row.idle_capacity_cost, "under_over_absorption": row.under_over_absorption,
        "analysis_hash": row.analysis_hash, "journal_id": row.journal_id,
        "summary": loads(row.summary_payload, {}), "allocations": loads(row.allocation_payload, {}),
        "lines": [
            {"id": x.id, "sequence": x.sequence, "category": x.category, "component_code": x.component_code,
             "description_ar": x.description_ar, "description_en": x.description_en,
             "standard_quantity": x.standard_quantity, "actual_quantity": x.actual_quantity,
             "standard_rate": x.standard_rate, "actual_rate": x.actual_rate, "amount": x.amount,
             "favorable": x.favorable, "posting_effect": x.posting_effect, "account_code": x.account_code,
             "source_reference": x.source_reference}
            for x in sorted(row.lines, key=lambda item: item.sequence)
        ],
    }


@router.post("/costing/runs", status_code=201)
def create_cost_run(data: CostRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "manufacturing.cost.prepare")
    ensure_open_period(db, data.company_id, data.posting_date)
    version = int(db.scalar(select(func.max(InternalCostRun.version)).where(InternalCostRun.company_id == data.company_id, InternalCostRun.code == data.code.upper())) or 0) + 1
    rows, summary, allocations = _calculate_cost(data)
    row = InternalCostRun(
        company_id=data.company_id, code=data.code.upper(), version=version, period_start=data.period_start,
        period_end=data.period_end, posting_date=data.posting_date, status="READY_FOR_REVIEW",
        standard_output_quantity=qty(data.standard_output_quantity), actual_output_quantity=qty(data.actual_output_quantity),
        normal_capacity_hours=qty(data.overhead.normal_capacity_hours), productive_hours=qty(data.overhead.productive_hours),
        budgeted_fixed_overhead=money(data.overhead.budgeted_fixed_overhead), actual_fixed_overhead=money(data.overhead.actual_fixed_overhead),
        joint_cost_total=money(data.joint_cost_total), byproduct_credit_total=money(sum((-dec(x["amount"]) for x in rows if x["category"] == "JOINT_COST_ALLOCATION" and dec(x["amount"]) < 0), ZERO)),
        rework_cost=money(data.rework_cost), total_standard_cost=money(summary["standard_total_cost"]),
        total_actual_cost=money(summary["actual_total_cost"]), total_variance=money(summary["total_variance"]),
        idle_capacity_cost=money(summary["idle_capacity_cost"]), under_over_absorption=money(summary["under_over_absorption"]),
        allocation_payload=dumps(allocations), summary_payload=dumps(summary), analysis_hash="PENDING", prepared_by=user.id,
    )
    for index, source in enumerate(rows, start=1):
        row.lines.append(InternalCostVarianceLine(sequence=index, **source))
    db.add(row); db.flush()
    row.analysis_hash = sha(_cost_integrity_payload(row))
    write_audit(db, action="FINAL_COST_RUN_PREPARED", entity_type="INTERNAL_COST_RUN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"code": row.code, "total_variance": str(row.total_variance), "hash": row.analysis_hash})
    db.commit()
    loaded = db.scalar(select(InternalCostRun).where(InternalCostRun.id == row.id).options(selectinload(InternalCostRun.lines)))
    return _cost_payload(loaded)


@router.post("/costing/runs/{run_id}/review")
def review_cost_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(InternalCostRun).where(InternalCostRun.id == run_id).options(selectinload(InternalCostRun.lines)))
    if not row:
        raise HTTPException(404, "Cost run not found")
    ensure_permission(db, user, row.company_id, "manufacturing.cost.review")
    if row.status != "READY_FOR_REVIEW":
        raise HTTPException(409, "Cost run is not ready for review")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot review")
    if sha(_cost_integrity_payload(row)) != row.analysis_hash:
        raise HTTPException(409, "Cost analysis integrity hash failed")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now()
    write_audit(db, action="FINAL_COST_RUN_REVIEWED", entity_type="INTERNAL_COST_RUN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return _cost_payload(row)


@router.post("/costing/runs/{run_id}/approve-post")
def approve_cost_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(InternalCostRun).where(InternalCostRun.id == run_id).options(selectinload(InternalCostRun.lines)))
    if not row:
        raise HTTPException(404, "Cost run not found")
    ensure_permission(db, user, row.company_id, "manufacturing.cost.approve")
    if row.status != "REVIEWED":
        raise HTTPException(409, "Cost run must be reviewed")
    if user.id in {row.prepared_by, row.reviewed_by}:
        raise HTTPException(409, "Three-step control: approver must be independent")
    if sha(_cost_integrity_payload(row)) != row.analysis_hash:
        raise HTTPException(409, "Cost analysis integrity hash failed")
    ensure_open_period(db, row.company_id, row.posting_date)
    journal_lines: list[dict] = []
    for line in row.lines:
        if not line.posting_effect or not line.account_code or not dec(line.amount):
            continue
        account = get_account(db, row.company_id, line.account_code)
        amount = money(abs(dec(line.amount)))
        journal_lines.append({"account_id": account.id, "debit": amount if dec(line.amount) > 0 else ZERO, "credit": amount if dec(line.amount) < 0 else ZERO, "description": line.description_en})
    total = money(sum((dec(x.amount) for x in row.lines if x.posting_effect), ZERO))
    journal = None
    if total:
        offset = get_account(db, row.company_id, "115010")
        journal_lines.append({"account_id": offset.id, "debit": money(abs(total)) if total < 0 else ZERO, "credit": money(abs(total)) if total > 0 else ZERO, "description": f"Advanced manufacturing cost bridge {row.code}"})
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.posting_date, reference=f"FINAL-COST-{row.id}", description=f"Advanced manufacturing cost variance {row.code}", lines=journal_lines)
        row.journal_id = journal.id
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="FINAL_COST_RUN_APPROVED", entity_type="INTERNAL_COST_RUN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status, "journal_id": row.journal_id})
    db.commit()
    return _cost_payload(row)


@router.get("/costing/runs")
def list_cost_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "manufacturing.cost.read")
    rows = db.scalars(select(InternalCostRun).where(InternalCostRun.company_id == company_id).options(selectinload(InternalCostRun.lines)).order_by(InternalCostRun.id.desc())).all()
    return [_cost_payload(row) for row in rows]


@router.get("/costing/runs/export.csv")
def export_cost_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "manufacturing.cost.read")
    rows = db.scalars(select(InternalCostRun).where(InternalCostRun.company_id == company_id).options(selectinload(InternalCostRun.lines)).order_by(InternalCostRun.id)).all()
    output: list[list[Any]] = []
    for run in rows:
        for line in sorted(run.lines, key=lambda item: item.sequence):
            output.append([run.code, run.version, run.period_start, run.period_end, run.status, line.category, line.component_code, line.amount, "F" if line.favorable else "U", line.posting_effect, line.account_code or "", run.journal_id or ""])
    return csv_response("advanced_cost_variances.csv", ["run", "version", "period_start", "period_end", "status", "category", "component", "amount", "favorability", "posting_effect", "account", "journal_id"], output)


# ---------------------------------------------------------------------------
# Planning, forecasting and multi-dimensional variance analysis
# ---------------------------------------------------------------------------


class PlanningLineIn(BaseModel):
    account_code: str = Field(min_length=1, max_length=30)
    period_start: date
    period_end: date
    granularity: str = Field(default="MONTHLY", pattern="^(DAILY|MONTHLY|ANNUAL)$")
    branch_id: int | None = None
    cost_center_id: int | None = None
    department_code: str | None = Field(default=None, max_length=60)
    product_item_id: int | None = None
    amount: Decimal
    driver_name: str | None = Field(default=None, max_length=120)
    driver_value: Decimal | None = None
    source_type: str = Field(default="MANUAL", pattern="^(MANUAL|DRIVER|COPY|IMPORT)$")
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.period_end < self.period_start:
            raise ValueError("line period_end cannot be before period_start")
        return self


class PlanningScenarioIn(BaseModel):
    company_id: int
    fiscal_year_id: int
    name: str = Field(min_length=2, max_length=150)
    scenario_type: str = Field(default="BUDGET", pattern="^(BUDGET|FORECAST|ROLLING_FORECAST|STRESS|BASELINE)$")
    base_scenario_id: int | None = None
    horizon_start: date
    horizon_end: date
    assumptions: dict[str, Any] = Field(default_factory=dict)
    commentary_ar: str = ""
    commentary_en: str = ""
    lines: list[PlanningLineIn] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_horizon(self):
        if self.horizon_end < self.horizon_start:
            raise ValueError("horizon_end cannot be before horizon_start")
        if any(x.period_start < self.horizon_start or x.period_end > self.horizon_end for x in self.lines):
            raise ValueError("All planning lines must fall inside the scenario horizon")
        return self


def _planning_payload(row: PlanningScenario) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "fiscal_year_id": row.fiscal_year_id,
        "name": row.name, "scenario_type": row.scenario_type, "version": row.version,
        "base_scenario_id": row.base_scenario_id, "horizon_start": row.horizon_start,
        "horizon_end": row.horizon_end, "status": row.status, "assumptions": loads(row.assumptions_payload, {}),
        "commentary_ar": row.commentary_ar, "commentary_en": row.commentary_en,
        "prepared_by": row.prepared_by, "reviewed_by": row.reviewed_by, "approved_by": row.approved_by,
        "frozen_at": row.frozen_at,
        "total": money(sum((dec(x.amount) for x in row.lines), ZERO)),
        "lines": [
            {"id": x.id, "account_code": x.account.code, "account_name_ar": x.account.name_ar,
             "account_name_en": x.account.name_en, "account_type": x.account.account_type,
             "period_start": x.period_start, "period_end": x.period_end, "granularity": x.granularity,
             "branch_id": x.branch_id, "cost_center_id": x.cost_center_id, "department_code": x.department_code,
             "product_item_id": x.product_item_id, "amount": x.amount, "driver_name": x.driver_name,
             "driver_value": x.driver_value, "source_type": x.source_type, "note": x.note}
            for x in sorted(row.lines, key=lambda item: (item.period_start, item.account.code, item.id))
        ],
    }


@router.post("/planning/scenarios", status_code=201)
def create_planning_scenario(data: PlanningScenarioIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "budget.manage")
    year = db.scalar(select(FiscalYear).where(FiscalYear.id == data.fiscal_year_id, FiscalYear.company_id == data.company_id))
    if not year:
        raise HTTPException(404, "Fiscal year not found")
    if data.base_scenario_id:
        base = db.get(PlanningScenario, data.base_scenario_id)
        if not base or base.company_id != data.company_id:
            raise HTTPException(422, "Base scenario is invalid")
    version = int(db.scalar(select(func.max(PlanningScenario.version)).where(PlanningScenario.company_id == data.company_id, PlanningScenario.fiscal_year_id == data.fiscal_year_id, PlanningScenario.name == data.name)) or 0) + 1
    row = PlanningScenario(company_id=data.company_id, fiscal_year_id=data.fiscal_year_id, name=data.name, scenario_type=data.scenario_type,
                           version=version, base_scenario_id=data.base_scenario_id, horizon_start=data.horizon_start, horizon_end=data.horizon_end,
                           status="DRAFT", assumptions_payload=dumps(data.assumptions), commentary_ar=data.commentary_ar,
                           commentary_en=data.commentary_en, prepared_by=user.id)
    for source in data.lines:
        account = get_account(db, data.company_id, source.account_code)
        row.lines.append(PlanningScenarioLine(account_id=account.id, period_start=source.period_start, period_end=source.period_end,
                                              granularity=source.granularity, branch_id=source.branch_id, cost_center_id=source.cost_center_id,
                                              department_code=source.department_code, product_item_id=source.product_item_id,
                                              amount=money(source.amount), driver_name=source.driver_name,
                                              driver_value=qty(source.driver_value) if source.driver_value is not None else None,
                                              source_type=source.source_type, note=source.note))
    db.add(row); db.flush()
    write_audit(db, action="PLANNING_SCENARIO_CREATED", entity_type="PLANNING_SCENARIO", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"name": row.name, "type": row.scenario_type, "lines": len(row.lines)})
    db.commit()
    loaded = db.scalar(select(PlanningScenario).where(PlanningScenario.id == row.id).options(selectinload(PlanningScenario.lines).selectinload(PlanningScenarioLine.account)))
    return _planning_payload(loaded)


def _planning_row(db: Session, scenario_id: int) -> PlanningScenario:
    row = db.scalar(select(PlanningScenario).where(PlanningScenario.id == scenario_id).options(selectinload(PlanningScenario.lines).selectinload(PlanningScenarioLine.account)))
    if not row:
        raise HTTPException(404, "Planning scenario not found")
    return row


@router.post("/planning/scenarios/{scenario_id}/submit")
def submit_planning_scenario(scenario_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _planning_row(db, scenario_id); ensure_permission(db, user, row.company_id, "budget.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft scenarios can be submitted")
    row.status = "READY_FOR_REVIEW"; row.submitted_at = utc_now(); db.commit(); return _planning_payload(row)


@router.post("/planning/scenarios/{scenario_id}/review")
def review_planning_scenario(scenario_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _planning_row(db, scenario_id); ensure_permission(db, user, row.company_id, "budget.approve")
    if row.status != "READY_FOR_REVIEW": raise HTTPException(409, "Scenario is not ready for review")
    if row.prepared_by == user.id: raise HTTPException(409, "Maker-checker: preparer cannot review")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit(); return _planning_payload(row)


@router.post("/planning/scenarios/{scenario_id}/approve")
def approve_planning_scenario(scenario_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _planning_row(db, scenario_id); ensure_permission(db, user, row.company_id, "budget.approve")
    if row.status != "REVIEWED": raise HTTPException(409, "Scenario must be reviewed")
    if user.id in {row.prepared_by, row.reviewed_by}: raise HTTPException(409, "Three-step control: approver must be independent")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); db.commit(); return _planning_payload(row)


@router.post("/planning/scenarios/{scenario_id}/freeze")
def freeze_planning_scenario(scenario_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _planning_row(db, scenario_id); ensure_permission(db, user, row.company_id, "budget.approve")
    if row.status != "APPROVED": raise HTTPException(409, "Only approved scenarios can be frozen")
    row.status = "FROZEN"; row.frozen_at = utc_now(); db.commit(); return _planning_payload(row)


def _previous_year(value: date) -> date:
    year = value.year - 1
    return date(year, value.month, min(value.day, calendar.monthrange(year, value.month)[1]))


def _actual_for_planning_line(db: Session, company_id: int, line: PlanningScenarioLine, start: date, end: date) -> Decimal:
    query = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(JournalEntry, JournalEntry.id == JournalLine.journal_id).where(
        JournalEntry.company_id == company_id, JournalEntry.status.in_(("POSTED", "REVERSED")),
        JournalEntry.entry_date.between(start, end), JournalLine.account_id == line.account_id,
    )
    if line.branch_id: query = query.where(JournalLine.branch_id == line.branch_id)
    if line.cost_center_id: query = query.where(JournalLine.cost_center_id == line.cost_center_id)
    value = dec(db.scalar(query) or 0)
    if line.account.account_type in {"REVENUE", "LIABILITY", "EQUITY"}: value = -value
    return money(value)


def _planning_key(line: PlanningScenarioLine) -> tuple:
    return (line.account_id, line.period_start, line.period_end, line.branch_id, line.cost_center_id, line.department_code, line.product_item_id)


@router.get("/planning/scenarios/{scenario_id}/variance")
def planning_variance(scenario_id: int, comparison_scenario_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _planning_row(db, scenario_id); ensure_permission(db, user, row.company_id, "budget.read")
    comparison_map: dict[tuple, Decimal] = {}
    comparison_name = None
    if comparison_scenario_id:
        comparison = _planning_row(db, comparison_scenario_id)
        if comparison.company_id != row.company_id: raise HTTPException(422, "Comparison scenario belongs to another company")
        comparison_map = {_planning_key(x): dec(x.amount) for x in comparison.lines}; comparison_name = comparison.name
    output = []
    totals = {"plan": ZERO, "actual": ZERO, "prior_year": ZERO, "comparison": ZERO, "variance": ZERO}
    for line in row.lines:
        actual = _actual_for_planning_line(db, row.company_id, line, line.period_start, line.period_end)
        prior = _actual_for_planning_line(db, row.company_id, line, _previous_year(line.period_start), _previous_year(line.period_end))
        planned = money(line.amount); comparison_amount = money(comparison_map.get(_planning_key(line), ZERO))
        variance = money(actual - planned)
        revenue = line.account.account_type == "REVENUE"
        favorable = variance >= 0 if revenue else variance <= 0
        pct_value = money(abs(variance) / abs(planned) * 100) if planned else ZERO
        significance = "SIGNIFICANT" if pct_value >= 10 else "NORMAL"
        ar = f"الفعلي {'أعلى' if variance > 0 else 'أقل' if variance < 0 else 'مساوٍ'} من الخطة بمبلغ {abs(variance):,.2f}؛ الانحراف {'إيجابي' if favorable else 'سلبي'} و{('جوهري' if significance == 'SIGNIFICANT' else 'ضمن النطاق')}"
        en = f"Actual is {'above' if variance > 0 else 'below' if variance < 0 else 'equal to'} plan by {abs(variance):,.2f}; the variance is {'favorable' if favorable else 'unfavorable'} and {'significant' if significance == 'SIGNIFICANT' else 'within range'}"
        output.append({"line_id": line.id, "account_code": line.account.code, "period_start": line.period_start, "period_end": line.period_end,
                       "branch_id": line.branch_id, "cost_center_id": line.cost_center_id, "department_code": line.department_code,
                       "product_item_id": line.product_item_id, "plan": planned, "actual": actual, "prior_year": prior,
                       "comparison": comparison_amount, "comparison_name": comparison_name, "variance": variance,
                       "variance_percent": pct_value, "favorable": favorable, "significance": significance,
                       "commentary_ar": ar, "commentary_en": en})
        for key, value in (("plan", planned), ("actual", actual), ("prior_year", prior), ("comparison", comparison_amount), ("variance", variance)): totals[key] += dec(value)
    return {"scenario": _planning_payload(row), "comparison_name": comparison_name, "totals": {k: money(v) for k, v in totals.items()}, "rows": output}


@router.get("/planning/scenarios")
def list_planning_scenarios(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "budget.read")
    rows = db.scalars(select(PlanningScenario).where(PlanningScenario.company_id == company_id).options(selectinload(PlanningScenario.lines).selectinload(PlanningScenarioLine.account)).order_by(PlanningScenario.id.desc())).all()
    return [_planning_payload(row) for row in rows]


@router.get("/planning/scenarios/{scenario_id}/export.csv")
def export_planning_scenario(scenario_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = planning_variance(scenario_id, None, user, db)
    rows = [[x["account_code"], x["period_start"], x["period_end"], x["branch_id"] or "", x["cost_center_id"] or "", x["department_code"] or "", x["product_item_id"] or "", x["plan"], x["actual"], x["prior_year"], x["variance"], x["variance_percent"], "F" if x["favorable"] else "U", x["commentary_ar"], x["commentary_en"]] for x in data["rows"]]
    return csv_response("planning_variance.csv", ["account", "period_start", "period_end", "branch", "cost_center", "department", "product", "plan", "actual", "prior_year", "variance", "variance_percent", "favorability", "commentary_ar", "commentary_en"], rows)


# ---------------------------------------------------------------------------
# Unified close orchestration and drill-down
# ---------------------------------------------------------------------------


class CloseRunIn(BaseModel):
    company_id: int
    fiscal_period_id: int


def _check(category: str, code: str, ar: str, en: str, status: str, *, blocking: bool = False,
           severity: str = "MEDIUM", expected: Any = None, actual: Any = None, variance: Decimal = ZERO,
           owner: str | None = None, evidence: str | None = None, details: str | None = None) -> dict:
    return {"category": category, "code": code, "title_ar": ar, "title_en": en, "severity": severity,
            "blocking": blocking, "status": status, "expected_value": None if expected is None else str(expected),
            "actual_value": None if actual is None else str(actual), "variance": money(variance), "owner": owner,
            "evidence_reference": evidence, "details": details}


def _count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def _build_close_checks(db: Session, company_id: int, period: FiscalPeriod) -> list[dict]:
    start, end = period.start_date, period.end_date
    checks: list[dict] = []
    unbalanced = _count(db, select(func.count(JournalEntry.id)).where(JournalEntry.company_id == company_id, JournalEntry.entry_date.between(start, end), JournalEntry.total_debit != JournalEntry.total_credit))
    checks.append(_check("GL", "GL_BALANCED", "توازن القيود", "Balanced journals", "PASS" if unbalanced == 0 else "FAIL", blocking=True, severity="CRITICAL", expected=0, actual=unbalanced, owner="Finance"))
    pending_journals = _count(db, select(func.count(JournalEntry.id)).where(JournalEntry.company_id == company_id, JournalEntry.entry_date.between(start, end), JournalEntry.status.in_(("DRAFT", "SUBMITTED"))))
    checks.append(_check("GL", "NO_PENDING_JOURNALS", "عدم وجود قيود غير مرحلة", "No pending journals", "PASS" if pending_journals == 0 else "FAIL", blocking=True, severity="HIGH", expected=0, actual=pending_journals, owner="Finance"))
    unmatched_bank = _count(db, select(func.count(BankStatementLine.id)).join(BankStatement, BankStatement.id == BankStatementLine.statement_id).where(BankStatement.company_id == company_id, BankStatementLine.status == "UNMATCHED", BankStatementLine.transaction_date <= end))
    checks.append(_check("TREASURY", "BANK_RECONCILIATION", "تسوية الحركات البنكية", "Bank reconciliation", "PASS" if unmatched_bank == 0 else "WARN", expected=0, actual=unmatched_bank, owner="Treasury"))
    negative_inventory = len(db.execute(select(StockMovement.item_id, StockMovement.warehouse_id, func.sum(StockMovement.quantity)).where(StockMovement.company_id == company_id, StockMovement.movement_date <= end).group_by(StockMovement.item_id, StockMovement.warehouse_id).having(func.sum(StockMovement.quantity) < 0)).all())
    checks.append(_check("INVENTORY", "NO_NEGATIVE_STOCK", "عدم وجود مخزون سالب", "No negative inventory", "PASS" if negative_inventory == 0 else "FAIL", blocking=True, severity="CRITICAL", expected=0, actual=negative_inventory, owner="Supply Chain"))
    pending_production = _count(db, select(func.count(ProductionOrder.id)).where(ProductionOrder.company_id == company_id, ProductionOrder.order_date <= end, ProductionOrder.status.notin_(("COMPLETED", "CANCELLED", "CLOSED"))))
    checks.append(_check("MANUFACTURING", "PRODUCTION_CUTOFF", "إقفال أوامر الإنتاج المستحقة", "Production order cut-off", "PASS" if pending_production == 0 else "WARN", expected=0, actual=pending_production, owner="Production"))
    pending_payroll = _count(db, select(func.count(PayrollRun.id)).where(PayrollRun.company_id == company_id, PayrollRun.period_year == end.year, PayrollRun.period_month == end.month, PayrollRun.status.notin_(("POSTED", "PAID", "APPROVED"))))
    checks.append(_check("PAYROLL", "PAYROLL_POSTING", "ترحيل رواتب الفترة", "Payroll posting", "PASS" if pending_payroll == 0 else "FAIL", blocking=True, severity="HIGH", expected=0, actual=pending_payroll, owner="HR & Finance"))
    pending_credit_notes = _count(db, select(func.count(CreditNote.id)).where(CreditNote.company_id == company_id, CreditNote.note_date <= end, CreditNote.status.notin_(("APPROVED_POSTED", "REJECTED", "CANCELLED"))))
    checks.append(_check("AR_AP", "CREDIT_NOTES", "اعتماد الإشعارات الدائنة", "Credit-note approval", "PASS" if pending_credit_notes == 0 else "WARN", expected=0, actual=pending_credit_notes, owner="AR/AP"))
    pending_asset_actions = _count(db, select(func.count(AssetLifecycleTransaction.id)).where(AssetLifecycleTransaction.company_id == company_id, AssetLifecycleTransaction.transaction_date <= end, AssetLifecycleTransaction.status.notin_(("APPROVED_POSTED", "REJECTED"))))
    checks.append(_check("ASSETS", "ASSET_LIFECYCLE", "اعتماد حركات الأصول", "Asset lifecycle approval", "PASS" if pending_asset_actions == 0 else "WARN", expected=0, actual=pending_asset_actions, owner="Fixed Assets"))
    lead_diff = dec(db.scalar(select(func.coalesce(func.sum(func.abs(LeadSchedule.difference)), 0)).where(LeadSchedule.company_id == company_id, LeadSchedule.period_end == end)) or 0)
    pending_leads = _count(db, select(func.count(LeadSchedule.id)).where(LeadSchedule.company_id == company_id, LeadSchedule.period_end == end, LeadSchedule.status != "APPROVED"))
    lead_ok = lead_diff == 0 and pending_leads == 0
    checks.append(_check("RECONCILIATION", "LEAD_SCHEDULES", "مطابقة جداول الحسابات", "Lead schedule reconciliation", "PASS" if lead_ok else "FAIL", blocking=True, severity="HIGH", expected="0 difference / approved", actual=f"difference={money(lead_diff)}, pending={pending_leads}", variance=lead_diff, owner="Financial Control"))
    pending_vat = _count(db, select(func.count(VatReturnSnapshot.id)).where(VatReturnSnapshot.company_id == company_id, VatReturnSnapshot.period_end <= end, VatReturnSnapshot.status.in_(("DRAFT", "SUBMITTED"))))
    pending_wht = _count(db, select(func.count(WithholdingTaxReturn.id)).where(WithholdingTaxReturn.company_id == company_id, WithholdingTaxReturn.period_end <= end, WithholdingTaxReturn.status.in_(("DRAFT", "SUBMITTED"))))
    pending_excise = _count(db, select(func.count(ExciseTaxReturn.id)).where(ExciseTaxReturn.company_id == company_id, ExciseTaxReturn.period_end <= end, ExciseTaxReturn.status.in_(("DRAFT", "SUBMITTED"))))
    pending_zakat = _count(db, select(func.count(ZakatIncomeTaxReturn.id)).where(ZakatIncomeTaxReturn.company_id == company_id, ZakatIncomeTaxReturn.period_end <= end, ZakatIncomeTaxReturn.status.in_(("DRAFT", "SUBMITTED"))))
    tax_pending = pending_vat + pending_wht + pending_excise + pending_zakat
    checks.append(_check("TAX", "TAX_RETURNS", "الإقرارات الضريبية المستحقة", "Due tax returns", "PASS" if tax_pending == 0 else "WARN", expected=0, actual=tax_pending, owner="Tax"))
    if end.month == 12:
        deferred = _count(db, select(func.count(DeferredTaxRun.id)).where(DeferredTaxRun.company_id == company_id, DeferredTaxRun.period_end == end, DeferredTaxRun.status.in_(("APPROVED", "APPROVED_POSTED"))))
        checks.append(_check("REPORTING", "DEFERRED_TAX", "اعتماد الضريبة المؤجلة", "Approved deferred tax", "PASS" if deferred else "FAIL", blocking=True, severity="HIGH", expected=1, actual=deferred, owner="Reporting"))
    else:
        checks.append(_check("REPORTING", "DEFERRED_TAX", "الضريبة المؤجلة عند الإقفال السنوي", "Deferred tax at year-end", "N/A", expected="Year-end only", actual=end.month, owner="Reporting"))
    verified_backup = _count(db, select(func.count(BackupRecord.id)).where(BackupRecord.company_id == company_id, BackupRecord.status == "VERIFIED"))
    checks.append(_check("RESILIENCE", "VERIFIED_BACKUP", "نسخة احتياطية تم التحقق منها", "Verified backup", "PASS" if verified_backup else "FAIL", blocking=True, severity="CRITICAL", expected=">=1", actual=verified_backup, owner="IT"))
    frozen_plan = _count(db, select(func.count(PlanningScenario.id)).where(PlanningScenario.company_id == company_id, PlanningScenario.horizon_start <= end, PlanningScenario.horizon_end >= start, PlanningScenario.status == "FROZEN"))
    checks.append(_check("PLANNING", "FROZEN_PLAN", "سيناريو تخطيط معتمد ومجمد", "Approved frozen planning scenario", "PASS" if frozen_plan else "WARN", expected=">=1", actual=frozen_plan, owner="FP&A"))
    return checks


def _close_summary(checks: list[dict]) -> dict:
    blockers = sum(1 for x in checks if x["blocking"] and x["status"] == "FAIL")
    warnings = sum(1 for x in checks if x["status"] == "WARN")
    passes = sum(1 for x in checks if x["status"] == "PASS")
    applicable = sum(1 for x in checks if x["status"] != "N/A")
    score = max(Decimal("0"), Decimal("100") - Decimal(blockers * 15) - Decimal(warnings * 5))
    return {"blocker_count": blockers, "warning_count": warnings, "pass_count": passes, "applicable_checks": applicable, "score": money(score)}


def _close_payload(row: CloseOrchestrationRun) -> dict:
    return {"id": row.id, "company_id": row.company_id, "fiscal_period_id": row.fiscal_period_id, "version": row.version,
            "status": row.status, "score": row.score, "blocker_count": row.blocker_count, "warning_count": row.warning_count,
            "checklist_hash": row.checklist_hash, "summary": loads(row.summary_payload, {}), "prepared_by": row.prepared_by,
            "reviewed_by": row.reviewed_by, "approved_by": row.approved_by, "closed_at": row.closed_at,
            "checks": [{"id": x.id, "category": x.category, "code": x.code, "title_ar": x.title_ar, "title_en": x.title_en,
                        "severity": x.severity, "blocking": x.blocking, "status": x.status, "expected_value": x.expected_value,
                        "actual_value": x.actual_value, "variance": x.variance, "owner": x.owner,
                        "evidence_reference": x.evidence_reference, "details": x.details} for x in row.checks]}


def _load_close(db: Session, run_id: int) -> CloseOrchestrationRun:
    row = db.scalar(select(CloseOrchestrationRun).where(CloseOrchestrationRun.id == run_id).options(selectinload(CloseOrchestrationRun.checks)))
    if not row: raise HTTPException(404, "Close orchestration run not found")
    return row


@router.post("/close/runs", status_code=201)
def create_close_run(data: CloseRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "period.close")
    period = db.get(FiscalPeriod, data.fiscal_period_id)
    if not period or period.fiscal_year.company_id != data.company_id:
        raise HTTPException(404, "Fiscal period not found")
    checks = _build_close_checks(db, data.company_id, period); summary = _close_summary(checks)
    version = int(db.scalar(select(func.max(CloseOrchestrationRun.version)).where(CloseOrchestrationRun.company_id == data.company_id, CloseOrchestrationRun.fiscal_period_id == data.fiscal_period_id)) or 0) + 1
    hash_value = sha(checks)
    row = CloseOrchestrationRun(company_id=data.company_id, fiscal_period_id=data.fiscal_period_id, version=version,
                                status="READY_FOR_REVIEW" if summary["blocker_count"] == 0 else "BLOCKED",
                                score=summary["score"], blocker_count=summary["blocker_count"], warning_count=summary["warning_count"],
                                checklist_hash=hash_value, summary_payload=dumps(summary), prepared_by=user.id)
    for source in checks: row.checks.append(CloseOrchestrationCheck(**source))
    db.add(row); db.flush()
    write_audit(db, action="UNIFIED_CLOSE_CHECKLIST_CREATED", entity_type="CLOSE_ORCHESTRATION_RUN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"score": str(row.score), "blockers": row.blocker_count, "warnings": row.warning_count})
    db.commit(); return _close_payload(_load_close(db, row.id))


@router.post("/close/runs/{run_id}/review")
def review_close_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _load_close(db, run_id); ensure_permission(db, user, row.company_id, "period.close")
    if row.prepared_by == user.id: raise HTTPException(409, "Maker-checker: preparer cannot review")
    period = db.get(FiscalPeriod, row.fiscal_period_id); current = _build_close_checks(db, row.company_id, period); summary = _close_summary(current)
    if summary["blocker_count"]: raise HTTPException(409, f"Close remains blocked by {summary['blocker_count']} checks")
    if sha(current) != row.checklist_hash: raise HTTPException(409, "Close conditions changed; prepare a new checklist version")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit(); return _close_payload(row)


@router.post("/close/runs/{run_id}/approve-close")
def approve_close_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _load_close(db, run_id); ensure_permission(db, user, row.company_id, "period.close")
    if row.status != "REVIEWED": raise HTTPException(409, "Close run must be reviewed")
    if user.id in {row.prepared_by, row.reviewed_by}: raise HTTPException(409, "Three-step control: approver must be independent")
    period = db.get(FiscalPeriod, row.fiscal_period_id); current = _build_close_checks(db, row.company_id, period); summary = _close_summary(current)
    if summary["blocker_count"] or sha(current) != row.checklist_hash: raise HTTPException(409, "Close conditions changed or blockers reappeared")
    period.status = "CLOSED"; row.status = "CLOSED"; row.approved_by = user.id; row.approved_at = utc_now(); row.closed_at = utc_now()
    write_audit(db, action="UNIFIED_PERIOD_CLOSED", entity_type="CLOSE_ORCHESTRATION_RUN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"period_id": period.id, "score": str(row.score)})
    db.commit(); return _close_payload(row)


@router.get("/close/runs")
def list_close_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "period.close")
    rows = db.scalars(select(CloseOrchestrationRun).where(CloseOrchestrationRun.company_id == company_id).options(selectinload(CloseOrchestrationRun.checks)).order_by(CloseOrchestrationRun.id.desc())).all()
    return [_close_payload(row) for row in rows]


@router.get("/drilldown")
def financial_drilldown(company_id: int, account_code: str, start_date: date, end_date: date,
                        branch_id: int | None = None, cost_center_id: int | None = None,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    account = get_account(db, company_id, account_code)
    query = select(JournalLine, JournalEntry).join(JournalEntry, JournalEntry.id == JournalLine.journal_id).where(
        JournalEntry.company_id == company_id, JournalEntry.status.in_(("POSTED", "REVERSED")),
        JournalEntry.entry_date.between(start_date, end_date), JournalLine.account_id == account.id,
    ).order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id)
    if branch_id: query = query.where(JournalLine.branch_id == branch_id)
    if cost_center_id: query = query.where(JournalLine.cost_center_id == cost_center_id)
    rows = db.execute(query).all(); running = ZERO; output = []
    natural_credit = account.account_type in {"REVENUE", "LIABILITY", "EQUITY"}
    for line, journal in rows:
        movement = dec(line.credit) - dec(line.debit) if natural_credit else dec(line.debit) - dec(line.credit)
        running += movement
        source_hint = "JOURNAL"
        reference = journal.reference or ""
        for prefix, source in (("FINAL-COST", "COST_VARIANCE"), ("VAT", "VAT"), ("WHT", "WITHHOLDING_TAX"), ("EXCISE", "EXCISE_TAX"), ("ASSET", "FIXED_ASSET"), ("PAY", "PAYROLL")):
            if reference.upper().startswith(prefix): source_hint = source; break
        output.append({"journal_id": journal.id, "journal_number": journal.number, "entry_date": journal.entry_date,
                       "reference": journal.reference, "journal_description": journal.description, "line_id": line.id,
                       "line_description": line.description, "debit": line.debit, "credit": line.credit,
                       "movement": money(movement), "running_balance": money(running), "branch_id": line.branch_id,
                       "cost_center_id": line.cost_center_id, "source_hint": source_hint})
    return {"account": {"id": account.id, "code": account.code, "name_ar": account.name_ar, "name_en": account.name_en, "account_type": account.account_type},
            "filters": {"start_date": start_date, "end_date": end_date, "branch_id": branch_id, "cost_center_id": cost_center_id},
            "total_debit": money(sum((dec(x[0].debit) for x in rows), ZERO)), "total_credit": money(sum((dec(x[0].credit) for x in rows), ZERO)),
            "natural_balance": money(running), "rows": output}


# ---------------------------------------------------------------------------
# Production-readiness assessment and evidence gate
# ---------------------------------------------------------------------------


class ReadinessIn(BaseModel):
    company_id: int
    environment_name: str = Field(default="INTERNAL", min_length=2, max_length=50)
    target_stage: str = Field(default="INTERNAL_RELEASE", pattern="^(INTERNAL_RELEASE|PRODUCTION)$")
    evidence: dict[str, Any] = Field(default_factory=dict)


def _readiness_check(category: str, code: str, ar: str, en: str, status: str, *, mandatory: bool,
                     evidence: str | None = None, details: str | None = None) -> dict:
    return {"category": category, "code": code, "title_ar": ar, "title_en": en, "mandatory": mandatory,
            "status": status, "evidence_reference": evidence, "details": details}


def _alembic_head(db: Session) -> str:
    try:
        return str(db.execute(text("select version_num from alembic_version")).scalar_one())
    except Exception:
        db.rollback()
        return "AUTO_CREATE_SCHEMA_OR_UNVERSIONED"


def _build_readiness_checks(db: Session, company_id: int, target: str, evidence: dict[str, Any]) -> tuple[list[dict], str]:
    production = target == "PRODUCTION"
    dialect = db.get_bind().dialect.name
    actual_head = _alembic_head(db)
    checks = [
        _readiness_check("DATABASE", "MIGRATION_HEAD", "رأس الترحيل النهائي", "Final migration head", "PASS" if actual_head == EXPECTED_HEAD else ("WARN" if not production and actual_head == "AUTO_CREATE_SCHEMA_OR_UNVERSIONED" else "FAIL"), mandatory=True, evidence=actual_head, details=f"Expected {EXPECTED_HEAD}"),
        _readiness_check("DATABASE", "POSTGRESQL", "قاعدة PostgreSQL", "PostgreSQL database", "PASS" if dialect == "postgresql" else ("WARN" if not production else "FAIL"), mandatory=production, evidence=dialect),
        _readiness_check("SECURITY", "PRODUCTION_ENV", "إعداد بيئة الإنتاج", "Production environment configuration", "PASS" if settings.environment.lower() == "production" else ("WARN" if not production else "FAIL"), mandatory=production, evidence=settings.environment),
        _readiness_check("SECURITY", "SECRET_KEY", "مفتاح سري قوي", "Strong secret key", "PASS" if settings.secret_key != "dev-only-change-me" and len(settings.secret_key) >= 32 else ("WARN" if not production else "FAIL"), mandatory=production),
        _readiness_check("SECURITY", "JWT_KEYS", "مفاتيح JWT غير متماثلة", "Asymmetric JWT keys", "PASS" if (settings.jwt_private_key_path or settings.jwt_private_key_pem) and settings.jwt_active_kid in settings.jwt_public_keys else ("WARN" if not production else "FAIL"), mandatory=production),
        _readiness_check("SECURITY", "FIELD_ENCRYPTION", "حلقة مفاتيح تشفير الحقول", "Field-encryption key ring", "PASS" if settings.field_encryption_active_kid in settings.field_encryption_keys else ("WARN" if not production else "FAIL"), mandatory=production),
        _readiness_check("SECURITY", "SENSITIVE_MFA", "MFA للأدوار الحساسة", "MFA for sensitive roles", "PASS" if settings.enforce_sensitive_role_mfa else ("WARN" if not production else "FAIL"), mandatory=production),
        _readiness_check("OPERATIONS", "MIGRATION_ONLY", "منع إنشاء الجداول تلقائيًا", "Migration-only schema management", "PASS" if not settings.auto_create_schema else ("WARN" if not production else "FAIL"), mandatory=production),
        _readiness_check("OPERATIONS", "NO_DEMO_SEED", "تعطيل البيانات التجريبية", "Demo seed disabled", "PASS" if not settings.seed_demo_data else ("WARN" if not production else "FAIL"), mandatory=production),
        _readiness_check("OPERATIONS", "DURABLE_MRP", "عامل MRP دائم", "Durable MRP worker", "PASS" if not settings.mrp_inline_execution else ("WARN" if not production else "FAIL"), mandatory=production),
        _readiness_check("PAYROLL", "STRICT_WORKFLOW", "مسار رواتب صارم", "Strict payroll workflow", "PASS" if settings.payroll_strict_workflow else ("WARN" if not production else "FAIL"), mandatory=production),
    ]
    verified_backup = _count(db, select(func.count(BackupRecord.id)).where(BackupRecord.company_id == company_id, BackupRecord.status == "VERIFIED"))
    checks.append(_readiness_check("RESILIENCE", "VERIFIED_BACKUP", "نسخة احتياطية متحققة", "Verified backup", "PASS" if verified_backup else "FAIL", mandatory=True, evidence=str(verified_backup)))
    unbalanced = _count(db, select(func.count(JournalEntry.id)).where(JournalEntry.company_id == company_id, JournalEntry.total_debit != JournalEntry.total_credit))
    checks.append(_readiness_check("FINANCE", "BALANCED_LEDGER", "الأستاذ العام متوازن", "Balanced general ledger", "PASS" if unbalanced == 0 else "FAIL", mandatory=True, evidence=str(unbalanced)))
    completed_close = _count(db, select(func.count(CloseOrchestrationRun.id)).where(CloseOrchestrationRun.company_id == company_id, CloseOrchestrationRun.status == "CLOSED"))
    checks.append(_readiness_check("FINANCE", "CLOSE_DRILL", "تجربة إقفال موحدة", "Unified close drill", "PASS" if completed_close else ("WARN" if not production else "FAIL"), mandatory=production, evidence=str(completed_close)))
    evidence_rules = [
        ("postgres_smoke_passed", "DATABASE", "POSTGRES_SMOKE", "اختبار PostgreSQL", "PostgreSQL smoke test"),
        ("load_test_passed", "PERFORMANCE", "LOAD_TEST", "اختبار الحمل والتزامن", "Load and concurrency test"),
        ("restore_drill_passed", "RESILIENCE", "RESTORE_DRILL", "تجربة الاستعادة", "Restore drill"),
        ("opening_balances_reconciled", "DATA", "OPENING_BALANCES", "مطابقة الأرصدة الافتتاحية", "Opening balances reconciled"),
        ("uat_signed", "GOVERNANCE", "UAT_SIGNOFF", "اعتماد UAT", "Signed UAT"),
        ("parallel_run_passed", "GOVERNANCE", "PARALLEL_RUN", "تشغيل موازٍ ناجح", "Successful parallel run"),
        ("penetration_test_passed", "SECURITY", "PEN_TEST", "اختبار اختراق مستقل", "Independent penetration test"),
    ]
    for key, category, code, ar, en in evidence_rules:
        passed = bool(evidence.get(key))
        checks.append(_readiness_check(category, code, ar, en, "PASS" if passed else ("WARN" if not production else "FAIL"), mandatory=production, evidence=str(evidence.get(f"{key}_reference") or ""), details=str(evidence.get(f"{key}_details") or "")))
    for code, ar, en in (
        ("ZATCA", "بيانات اعتماد ZATCA", "ZATCA credentials"), ("BANKS", "بيانات ربط البنوك", "Bank integration credentials"),
        ("WPS", "اعتماد WPS/مدد", "WPS/Mudad credentials"), ("GOV_PLATFORMS", "قوى ومقيم والتأمينات", "Qiwa, Muqeem and GOSI access"),
    ):
        checks.append(_readiness_check("EXTERNAL", code, ar, en, "EXTERNAL", mandatory=False, details="Prepared interface; official credentials and certification are outside the internal build"))
    return checks, dialect


def _readiness_summary(checks: list[dict]) -> dict:
    blockers = sum(1 for x in checks if x["mandatory"] and x["status"] == "FAIL")
    warnings = sum(1 for x in checks if x["status"] == "WARN")
    passes = sum(1 for x in checks if x["status"] == "PASS")
    scored = [x for x in checks if x["status"] != "EXTERNAL"]
    score = Decimal("100") * Decimal(passes) / Decimal(len(scored)) if scored else ZERO
    return {"blocker_count": blockers, "warning_count": warnings, "pass_count": passes, "scored_checks": len(scored), "score": money(score)}


def _readiness_payload(row: ReadinessAssessment) -> dict:
    return {"id": row.id, "company_id": row.company_id, "environment_name": row.environment_name, "target_stage": row.target_stage,
            "status": row.status, "score": row.score, "blocker_count": row.blocker_count, "warning_count": row.warning_count,
            "expected_migration_head": row.expected_migration_head, "database_dialect": row.database_dialect,
            "evidence": loads(row.evidence_payload, {}), "summary": loads(row.summary_payload, {}),
            "prepared_by": row.prepared_by, "reviewed_by": row.reviewed_by, "approved_by": row.approved_by,
            "checks": [{"id": x.id, "category": x.category, "code": x.code, "title_ar": x.title_ar, "title_en": x.title_en,
                        "mandatory": x.mandatory, "status": x.status, "evidence_reference": x.evidence_reference,
                        "details": x.details} for x in row.checks]}


def _load_readiness(db: Session, assessment_id: int) -> ReadinessAssessment:
    row = db.scalar(select(ReadinessAssessment).where(ReadinessAssessment.id == assessment_id).options(selectinload(ReadinessAssessment.checks)))
    if not row: raise HTTPException(404, "Readiness assessment not found")
    return row


@router.post("/readiness/assessments", status_code=201)
def create_readiness_assessment(data: ReadinessIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "governance.read")
    checks, dialect = _build_readiness_checks(db, data.company_id, data.target_stage, data.evidence); summary = _readiness_summary(checks)
    row = ReadinessAssessment(company_id=data.company_id, environment_name=data.environment_name, target_stage=data.target_stage,
                              status="READY_FOR_REVIEW" if summary["blocker_count"] == 0 else "BLOCKED", score=summary["score"],
                              blocker_count=summary["blocker_count"], warning_count=summary["warning_count"],
                              expected_migration_head=EXPECTED_HEAD, database_dialect=dialect, evidence_payload=dumps(data.evidence),
                              summary_payload=dumps(summary), prepared_by=user.id)
    for source in checks: row.checks.append(ReadinessAssessmentCheck(**source))
    db.add(row); db.flush()
    write_audit(db, action="READINESS_ASSESSMENT_CREATED", entity_type="READINESS_ASSESSMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"target": row.target_stage, "score": str(row.score), "blockers": row.blocker_count})
    db.commit(); return _readiness_payload(_load_readiness(db, row.id))


@router.post("/readiness/assessments/{assessment_id}/review")
def review_readiness(assessment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _load_readiness(db, assessment_id); ensure_permission(db, user, row.company_id, "governance.manage")
    if row.status != "READY_FOR_REVIEW": raise HTTPException(409, "Readiness assessment is blocked or already processed")
    if row.prepared_by == user.id: raise HTTPException(409, "Maker-checker: preparer cannot review")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit(); return _readiness_payload(row)


@router.post("/readiness/assessments/{assessment_id}/approve")
def approve_readiness(assessment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _load_readiness(db, assessment_id); ensure_permission(db, user, row.company_id, "governance.manage")
    if row.status != "REVIEWED": raise HTTPException(409, "Readiness assessment must be reviewed")
    if user.id in {row.prepared_by, row.reviewed_by}: raise HTTPException(409, "Three-step control: approver must be independent")
    if row.blocker_count: raise HTTPException(409, "Readiness assessment contains mandatory blockers")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); db.commit(); return _readiness_payload(row)


@router.get("/readiness/assessments")
def list_readiness(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "governance.read")
    rows = db.scalars(select(ReadinessAssessment).where(ReadinessAssessment.company_id == company_id).options(selectinload(ReadinessAssessment.checks)).order_by(ReadinessAssessment.id.desc())).all()
    return [_readiness_payload(row) for row in rows]


@router.get("/readiness/assessments/{assessment_id}/export.csv")
def export_readiness(assessment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _load_readiness(db, assessment_id); ensure_permission(db, user, row.company_id, "governance.read")
    rows = [[x.category, x.code, x.title_ar, x.title_en, x.mandatory, x.status, x.evidence_reference or "", x.details or ""] for x in row.checks]
    return csv_response("readiness_assessment.csv", ["category", "code", "title_ar", "title_en", "mandatory", "status", "evidence", "details"], rows)
