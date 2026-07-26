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

class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_warehouse_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    warehouse_type = Column(String(30), nullable=False, default="GENERAL")
    active = Column(Boolean, nullable=False, default=True)
    branch = relationship("Branch", lazy="joined")

class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_item_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    item_type = Column(String(30), nullable=False, default="INVENTORY", index=True)
    uom = Column(String(20), nullable=False, default="EA")
    valuation_method = Column(String(30), nullable=False, default="WEIGHTED_AVERAGE")
    standard_cost = Column(Numeric(18, 4), nullable=False, default=0)
    reorder_level = Column(Numeric(18, 4), nullable=False, default=0)
    inventory_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    cogs_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    revenue_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    item_subtype = Column(String(40))  # H9-item-columns
    nrv_per_unit = Column(Numeric(18, 4))  # H9-item-columns
    physical_issue_method = Column(String(10), nullable=False, default="FEFO")  # H9-item-columns
    inventory_account = relationship("Account", foreign_keys=[inventory_account_id], lazy="joined")
    cogs_account = relationship("Account", foreign_keys=[cogs_account_id], lazy="joined")
    revenue_account = relationship("Account", foreign_keys=[revenue_account_id], lazy="joined")

class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    movement_date = Column(Date, nullable=False, index=True)
    movement_type = Column(String(30), nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_cost = Column(Numeric(18, 4), nullable=False, default=0)
    total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    lot_number = Column(String(80))
    expiry_date = Column(Date)
    reference_type = Column(String(50), nullable=False)
    reference_id = Column(Integer)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    inbound_shipment_id = Column(Integer)  # H9-movement-column
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    warehouse = relationship("Warehouse", lazy="joined")
    item = relationship("Item", lazy="joined")
    journal = relationship("JournalEntry")

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_po_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    order_date = Column(Date, nullable=False)
    expected_receipt_date = Column(Date, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    subtotal = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    supplier = relationship("Party", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")
    lines = relationship("PurchaseOrderLine", back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin")

class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    received_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    invoiced_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    purchase_order = relationship("PurchaseOrder", back_populates="lines")
    item = relationship("Item", lazy="joined")

class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_grn_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    receipt_date = Column(Date, nullable=False)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    status = Column(String(20), nullable=False, default="POSTED")
    total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    purchase_order = relationship("PurchaseOrder", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")
    journal = relationship("JournalEntry")
    lines = relationship("GoodsReceiptLine", back_populates="goods_receipt", cascade="all, delete-orphan", lazy="selectin")

class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    id = Column(Integer, primary_key=True)
    goods_receipt_id = Column(Integer, ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False, index=True)
    purchase_order_line_id = Column(Integer, ForeignKey("purchase_order_lines.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_cost = Column(Numeric(18, 4), nullable=False)
    lot_number = Column(String(80))
    expiry_date = Column(Date)
    goods_receipt = relationship("GoodsReceipt", back_populates="lines")
    item = relationship("Item", lazy="joined")


# -------------------- IFRS 15 / gym contracts --------------------

__all__ = ['Warehouse', 'Item', 'StockMovement', 'PurchaseOrder', 'PurchaseOrderLine', 'GoodsReceipt', 'GoodsReceiptLine']
