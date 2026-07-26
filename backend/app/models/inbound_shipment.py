"""CORVAX RC27.4 H9 - inbound shipment models with landed-cost traceability."""
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


# Strict allowed values (validated in the API layer as well).
ITEM_TYPES = {
    "RAW_MATERIAL",       # مواد خام
    "WORK_IN_PROGRESS",   # تحت التصنيع
    "FINISHED_GOOD",      # منتج نهائي
    "PACKAGING",          # تعبئة وتغليف
    "CLEANING_MATERIAL",  # مواد نظافة
    "OPERATING_SUPPLY",   # مواد تشغيلية
    "SPARE_PART",         # قطع غيار
    "SERVICE",            # خدمة (غير مخزنية)
}

# Suggested raw-material subtypes for a food-manufacturing (poultry/meat) operation.
RAW_MATERIAL_SUBTYPES = {
    "CORE_MATERIAL",      # مواد خام أساسية (لحوم/دواجن)
    "SPICE",              # بهارات
    "CHEMICAL_BINDER",    # مواد ربط كيميائية
    "AUXILIARY_MATERIAL", # مواد مساعدة (زيوت/شحوم)
}

VALUATION_METHODS = {"WEIGHTED_AVERAGE", "FIFO"}   # IAS 2 - LIFO is intentionally excluded
PHYSICAL_ISSUE_METHODS = {"FEFO", "FIFO"}
ALLOCATION_METHODS = {"VALUE", "WEIGHT", "QUANTITY"}


class InboundShipment(Base):
    __tablename__ = "inbound_shipments"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_inbound_shipment_company_number"),
        UniqueConstraint("company_id", "container_number", name="uq_inbound_shipment_container"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    container_number = Column(String(60), nullable=False)
    packing_list_number = Column(String(60), nullable=False)
    commercial_invoice_number = Column(String(60), nullable=False)
    customs_clearance_number = Column(String(60))
    customs_declaration_number = Column(String(60))
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"))
    arrival_date = Column(Date, nullable=False)
    port_of_entry = Column(String(120))
    carrier = Column(String(120))
    goods_value = Column(Numeric(18, 2), nullable=False, default=0)
    freight_cost = Column(Numeric(18, 2), nullable=False, default=0)
    customs_duty = Column(Numeric(18, 2), nullable=False, default=0)
    clearance_fees = Column(Numeric(18, 2), nullable=False, default=0)
    other_costs = Column(Numeric(18, 2), nullable=False, default=0)
    landed_cost_total = Column(Numeric(18, 2), nullable=False, default=0)
    allocation_method = Column(String(20), nullable=False, default="VALUE")
    status = Column(String(20), nullable=False, default="DRAFT")  # DRAFT -> COSTED -> RECEIVED
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    received_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    supplier = relationship("Party", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")
    journal = relationship("JournalEntry")
    lines = relationship("InboundShipmentLine", back_populates="shipment", cascade="all, delete-orphan", lazy="selectin")


class InboundShipmentLine(Base):
    __tablename__ = "inbound_shipment_lines"
    id = Column(Integer, primary_key=True)
    inbound_shipment_id = Column(Integer, ForeignKey("inbound_shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    supplier_unit_cost = Column(Numeric(18, 4), nullable=False)
    line_goods_value = Column(Numeric(18, 2), nullable=False, default=0)
    allocated_landed_cost = Column(Numeric(18, 2), nullable=False, default=0)
    landed_unit_cost = Column(Numeric(18, 4), nullable=False, default=0)
    lot_number = Column(String(80))
    expiry_date = Column(Date)
    shipment = relationship("InboundShipment", back_populates="lines")
    item = relationship("Item", lazy="joined")


# Note: stock_movements.inbound_shipment_id is added by migration e19000000001 as a plain
# integer column (no DB-level FK) to avoid a SQLite batch rebuild. The link to the shipment
# is populated and enforced by the H9 API layer.


__all__ = [
    "InboundShipment", "InboundShipmentLine",
    "ITEM_TYPES", "RAW_MATERIAL_SUBTYPES", "VALUATION_METHODS",
    "PHYSICAL_ISSUE_METHODS", "ALLOCATION_METHODS",
]
