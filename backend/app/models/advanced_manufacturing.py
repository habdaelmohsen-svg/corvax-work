from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base
from app.models.types import EncryptedDecimal, EncryptedString

class ManufacturingRouting(Base):
    __tablename__ = "manufacturing_routings"
    __table_args__ = (UniqueConstraint("company_id", "code", "version", name="uq_mfg_routing_company_code_version"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    finished_item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    bom_id = Column(Integer, ForeignKey("bills_of_material.id"), nullable=False, index=True)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    finished_item = relationship("Item", lazy="joined")
    bom = relationship("BillOfMaterial", lazy="joined")
    operations = relationship("ManufacturingRoutingOperation", back_populates="routing", cascade="all, delete-orphan", lazy="selectin")

class ManufacturingRoutingOperation(Base):
    __tablename__ = "manufacturing_routing_operations"
    __table_args__ = (
        UniqueConstraint("routing_id", "sequence", name="uq_mfg_routing_operation_sequence"),
        UniqueConstraint("routing_id", "operation_code", name="uq_mfg_routing_operation_code"),
    )
    id = Column(Integer, primary_key=True)
    routing_id = Column(Integer, ForeignKey("manufacturing_routings.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    operation_code = Column(String(40), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    work_center_id = Column(Integer, ForeignKey("work_centers.id"), nullable=False)
    setup_minutes = Column(Numeric(18, 4), nullable=False, default=0)
    run_minutes_per_unit = Column(Numeric(18, 6), nullable=False, default=0)
    queue_minutes = Column(Numeric(18, 4), nullable=False, default=0)
    move_minutes = Column(Numeric(18, 4), nullable=False, default=0)
    standard_labor_rate = Column(Numeric(18, 4), nullable=False, default=0)
    standard_overhead_rate = Column(Numeric(18, 4), nullable=False, default=0)
    outside_processing_cost = Column(Numeric(18, 4), nullable=False, default=0)
    quality_gate = Column(Boolean, nullable=False, default=False)
    routing = relationship("ManufacturingRouting", back_populates="operations")
    work_center = relationship("WorkCenter", lazy="joined")

class MRPPlanRun(Base):
    __tablename__ = "mrp_plan_runs"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_mrp_run_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    planning_date = Column(Date, nullable=False, index=True)
    horizon_end = Column(Date, nullable=False)
    gross_demand = Column(Numeric(18, 4), nullable=False, default=0)
    total_on_hand = Column(Numeric(18, 4), nullable=False, default=0)
    total_scheduled_receipts = Column(Numeric(18, 4), nullable=False, default=0)
    total_shortage = Column(Numeric(18, 4), nullable=False, default=0)
    total_planned_supply = Column(Numeric(18, 4), nullable=False, default=0)
    status = Column(String(30), nullable=False, default="CALCULATED", index=True)
    execution_mode = Column(String(20), nullable=False, default="BACKGROUND")
    background_job_id = Column(String(64), ForeignKey("background_jobs.id"))
    progress_percent = Column(Integer, nullable=False, default=100)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    warehouse = relationship("Warehouse", lazy="joined")
    demands = relationship("MRPDemandLine", back_populates="run", cascade="all, delete-orphan", lazy="selectin")
    requirements = relationship("MRPRequirementLine", back_populates="run", cascade="all, delete-orphan", lazy="selectin")

class MRPDemandLine(Base):
    __tablename__ = "mrp_demand_lines"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("mrp_plan_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    safety_stock = Column(Numeric(18, 4), nullable=False, default=0)
    source_type = Column(String(30), nullable=False, default="FORECAST")
    source_reference = Column(String(100))
    run = relationship("MRPPlanRun", back_populates="demands")
    item = relationship("Item", lazy="joined")

class MRPRequirementLine(Base):
    __tablename__ = "mrp_requirement_lines"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("mrp_plan_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_item_id = Column(Integer, ForeignKey("items.id"))
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    bom_id = Column(Integer, ForeignKey("bills_of_material.id"))
    level = Column(Integer, nullable=False, default=0)
    due_date = Column(Date, nullable=False, index=True)
    gross_requirement = Column(Numeric(18, 4), nullable=False, default=0)
    on_hand = Column(Numeric(18, 4), nullable=False, default=0)
    scheduled_receipts = Column(Numeric(18, 4), nullable=False, default=0)
    production_receipts = Column(Numeric(18, 4), nullable=False, default=0)
    purchase_receipts = Column(Numeric(18, 4), nullable=False, default=0)
    safety_stock = Column(Numeric(18, 4), nullable=False, default=0)
    net_requirement = Column(Numeric(18, 4), nullable=False, default=0)
    planned_order_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    planned_receipt_date = Column(Date)
    planned_release_date = Column(Date)
    supplier_id = Column(Integer, ForeignKey("parties.id"))
    lead_time_days = Column(Integer, nullable=False, default=0)
    lot_sizing_policy = Column(String(20), nullable=False, default="LFL")
    capacity_status = Column(String(25), nullable=False, default="NOT_APPLICABLE")
    supply_type = Column(String(20), nullable=False, default="BUY")
    action_message = Column(String(80), nullable=False, default="NONE")
    run = relationship("MRPPlanRun", back_populates="requirements")
    item = relationship("Item", foreign_keys=[item_id], lazy="joined")
    parent_item = relationship("Item", foreign_keys=[parent_item_id], lazy="joined")
    bom = relationship("BillOfMaterial", lazy="joined")

class ProductionOperationLog(Base):
    __tablename__ = "production_operation_logs"
    __table_args__ = (UniqueConstraint("production_order_id", "routing_operation_id", name="uq_production_order_routing_operation"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    routing_operation_id = Column(Integer, ForeignKey("manufacturing_routing_operations.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    status = Column(String(25), nullable=False, default="PLANNED", index=True)
    planned_setup_minutes = Column(Numeric(18, 4), nullable=False, default=0)
    planned_run_minutes = Column(Numeric(18, 4), nullable=False, default=0)
    actual_setup_minutes = Column(Numeric(18, 4), nullable=False, default=0)
    actual_run_minutes = Column(Numeric(18, 4), nullable=False, default=0)
    good_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    rejected_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    actual_labor_rate = Column(Numeric(18, 4), nullable=False, default=0)
    actual_overhead_rate = Column(Numeric(18, 4), nullable=False, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    started_by = Column(Integer, ForeignKey("users.id"))
    completed_by = Column(Integer, ForeignKey("users.id"))
    production_order = relationship("ProductionOrder", lazy="joined")
    routing_operation = relationship("ManufacturingRoutingOperation", lazy="joined")

class ProductionScrapRecord(Base):
    __tablename__ = "production_scrap_records"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    record_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_cost = Column(Numeric(18, 4), nullable=False, default=0)
    total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    reason_code = Column(String(50), nullable=False)
    classification = Column(String(20), nullable=False, default="NORMAL")
    disposition = Column(String(30), nullable=False, default="DISPOSE")
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    production_order = relationship("ProductionOrder", lazy="joined")
    item = relationship("Item", lazy="joined")

class ProductionCostClose(Base):
    __tablename__ = "production_cost_closes"
    __table_args__ = (UniqueConstraint("production_order_id", "version", name="uq_production_cost_close_order_version"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    close_date = Column(Date, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    cost_method = Column(String(20), nullable=False, default="STANDARD")
    completed_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    standard_material_cost = Column(Numeric(18, 2), nullable=False, default=0)
    standard_labor_cost = Column(Numeric(18, 2), nullable=False, default=0)
    standard_overhead_cost = Column(Numeric(18, 2), nullable=False, default=0)
    standard_total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    actual_material_cost = Column(Numeric(18, 2), nullable=False, default=0)
    actual_labor_cost = Column(Numeric(18, 2), nullable=False, default=0)
    actual_overhead_cost = Column(Numeric(18, 2), nullable=False, default=0)
    actual_total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    material_price_variance = Column(Numeric(18, 2), nullable=False, default=0)
    material_usage_variance = Column(Numeric(18, 2), nullable=False, default=0)
    labor_rate_variance = Column(Numeric(18, 2), nullable=False, default=0)
    labor_efficiency_variance = Column(Numeric(18, 2), nullable=False, default=0)
    overhead_spending_variance = Column(Numeric(18, 2), nullable=False, default=0)
    overhead_volume_variance = Column(Numeric(18, 2), nullable=False, default=0)
    abnormal_scrap_cost = Column(Numeric(18, 2), nullable=False, default=0)
    residual_variance = Column(Numeric(18, 2), nullable=False, default=0)
    total_variance = Column(Numeric(18, 2), nullable=False, default=0)
    standard_unit_cost = Column(Numeric(18, 4), nullable=False, default=0)
    actual_unit_cost = Column(Numeric(18, 4), nullable=False, default=0)
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    analysis_hash = Column(String(64), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    production_order = relationship("ProductionOrder", lazy="joined")
    journal = relationship("JournalEntry")


# -------------------- Audit remediation, planning and durable jobs RC11 --------------------

class SupplierItemPlanning(Base):
    __tablename__ = "supplier_item_planning"
    __table_args__ = (UniqueConstraint("company_id", "supplier_id", "item_id", name="uq_supplier_item_planning"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_time_days = Column(Integer, nullable=False, default=0)
    lot_sizing_policy = Column(String(20), nullable=False, default="LFL")
    minimum_order_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    order_multiple = Column(Numeric(18, 4), nullable=False, default=1)
    fixed_order_quantity = Column(Numeric(18, 4))
    eoq_annual_demand = Column(Numeric(18, 4))
    eoq_order_cost = Column(Numeric(18, 4))
    eoq_holding_cost = Column(Numeric(18, 4))
    preferred = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    supplier = relationship("Party", lazy="joined")
    item = relationship("Item", lazy="joined")

class WorkCenterCalendarDay(Base):
    __tablename__ = "work_center_calendar_days"
    __table_args__ = (UniqueConstraint("work_center_id", "work_date", name="uq_work_center_calendar_day"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    work_center_id = Column(Integer, ForeignKey("work_centers.id", ondelete="CASCADE"), nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    shift_code = Column(String(30), nullable=False, default="DAY")
    available_minutes = Column(Numeric(18, 2), nullable=False, default=480)
    reserved_minutes = Column(Numeric(18, 2), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    work_center = relationship("WorkCenter", lazy="joined")

class MRPCapacityAllocation(Base):
    __tablename__ = "mrp_capacity_allocations"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("mrp_plan_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_line_id = Column(Integer, ForeignKey("mrp_requirement_lines.id", ondelete="CASCADE"), nullable=False, index=True)
    work_center_id = Column(Integer, ForeignKey("work_centers.id"), nullable=False, index=True)
    operation_sequence = Column(Integer, nullable=False)
    work_date = Column(Date, nullable=False, index=True)
    allocated_minutes = Column(Numeric(18, 2), nullable=False)
    capacity_status = Column(String(20), nullable=False, default="ALLOCATED")
    work_center = relationship("WorkCenter", lazy="joined")

class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (UniqueConstraint("company_id", "job_type", "idempotency_key", name="uq_background_job_idempotency"),)
    id = Column(String(64), primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(50), nullable=False, index=True)
    idempotency_key = Column(String(100), nullable=False)
    status = Column(String(25), nullable=False, default="QUEUED", index=True)
    payload_json = Column(Text, nullable=False)
    progress_percent = Column(Integer, nullable=False, default=0)
    result_reference = Column(String(100))
    error_message = Column(Text)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    locked_by = Column(String(100))
    locked_at = Column(DateTime)
    next_attempt_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

__all__ = ['ManufacturingRouting', 'ManufacturingRoutingOperation', 'MRPPlanRun', 'MRPDemandLine', 'MRPRequirementLine', 'ProductionOperationLog', 'ProductionScrapRecord', 'ProductionCostClose', 'SupplierItemPlanning', 'WorkCenterCalendarDay', 'MRPCapacityAllocation', 'BackgroundJob']
