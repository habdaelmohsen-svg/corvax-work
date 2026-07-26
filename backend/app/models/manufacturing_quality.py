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

class WorkCenter(Base):
    __tablename__ = "work_centers"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_work_center_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    hourly_labor_rate = Column(Numeric(18, 4), nullable=False, default=0)
    hourly_overhead_rate = Column(Numeric(18, 4), nullable=False, default=0)
    direct_expense_rate = Column(Numeric(18, 4), nullable=False, default=0)
    variable_overhead_rate = Column(Numeric(18, 4), nullable=False, default=0)
    fixed_overhead_rate = Column(Numeric(18, 4), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)

class BillOfMaterial(Base):
    __tablename__ = "bills_of_material"
    __table_args__ = (UniqueConstraint("company_id", "code", "version", name="uq_bom_company_code_version"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    finished_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    output_quantity = Column(Numeric(18, 4), nullable=False, default=1)
    work_center_id = Column(Integer, ForeignKey("work_centers.id"))
    standard_hours = Column(Numeric(18, 4), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    finished_item = relationship("Item", foreign_keys=[finished_item_id], lazy="joined")
    work_center = relationship("WorkCenter", lazy="joined")
    lines = relationship("BillOfMaterialLine", back_populates="bom", cascade="all, delete-orphan", lazy="selectin")

class BillOfMaterialLine(Base):
    __tablename__ = "bill_of_material_lines"
    id = Column(Integer, primary_key=True)
    bom_id = Column(Integer, ForeignKey("bills_of_material.id", ondelete="CASCADE"), nullable=False, index=True)
    component_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    scrap_percent = Column(Numeric(8, 4), nullable=False, default=0)
    bom = relationship("BillOfMaterial", back_populates="lines")
    component_item = relationship("Item", lazy="joined")

class ProductionOrder(Base):
    __tablename__ = "production_orders"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_production_order_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    order_date = Column(Date, nullable=False)
    bom_id = Column(Integer, ForeignKey("bills_of_material.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    planned_quantity = Column(Numeric(18, 4), nullable=False)
    completed_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    planned_hours = Column(Numeric(18, 4), nullable=False, default=0)
    actual_hours = Column(Numeric(18, 4), nullable=False, default=0)
    status = Column(String(25), nullable=False, default="RELEASED", index=True)
    material_cost = Column(Numeric(18, 2), nullable=False, default=0)
    labor_cost = Column(Numeric(18, 2), nullable=False, default=0)
    overhead_cost = Column(Numeric(18, 2), nullable=False, default=0)
    total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    issue_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    completion_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    bom = relationship("BillOfMaterial", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")

class ProductionRun(Base):
    __tablename__ = "production_runs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)
    planned_minutes = Column(Numeric(18, 2), nullable=False)
    downtime_minutes = Column(Numeric(18, 2), nullable=False, default=0)
    ideal_cycle_seconds = Column(Numeric(18, 4), nullable=False)
    total_units = Column(Numeric(18, 4), nullable=False)
    good_units = Column(Numeric(18, 4), nullable=False)
    availability = Column(Numeric(9, 4), nullable=False)
    performance = Column(Numeric(9, 4), nullable=False)
    quality = Column(Numeric(9, 4), nullable=False)
    oee = Column(Numeric(9, 4), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

class QualityInspection(Base):
    __tablename__ = "quality_inspections"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_quality_inspection_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    inspection_date = Column(Date, nullable=False)
    inspection_type = Column(String(30), nullable=False)
    reference_type = Column(String(50), nullable=False)
    reference_id = Column(Integer, nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"))
    lot_number = Column(String(80))
    inspected_quantity = Column(Numeric(18, 4), nullable=False)
    accepted_quantity = Column(Numeric(18, 4), nullable=False)
    rejected_quantity = Column(Numeric(18, 4), nullable=False)
    result = Column(String(20), nullable=False, index=True)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    item = relationship("Item", lazy="joined")

class NonConformance(Base):
    __tablename__ = "non_conformances"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_ncr_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    inspection_id = Column(Integer, ForeignKey("quality_inspections.id"))
    severity = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    root_cause = Column(Text)
    corrective_action = Column(Text)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(Date)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

# -------------------- IAS 16 fixed assets --------------------

__all__ = ['WorkCenter', 'BillOfMaterial', 'BillOfMaterialLine', 'ProductionOrder', 'ProductionRun', 'QualityInspection', 'NonConformance']
