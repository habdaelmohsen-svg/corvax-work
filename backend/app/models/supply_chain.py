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
    category_id = Column(Integer, ForeignKey("item_categories.id"))
    item_subtype = Column(String(40))  # H9-item-columns
    nrv_per_unit = Column(Numeric(18, 4))  # H9-item-columns
    physical_issue_method = Column(String(10), nullable=False, default="FEFO")  # H9-item-columns
    inventory_account = relationship("Account", foreign_keys=[inventory_account_id], lazy="joined")
    cogs_account = relationship("Account", foreign_keys=[cogs_account_id], lazy="joined")
    revenue_account = relationship("Account", foreign_keys=[revenue_account_id], lazy="joined")
    category = relationship("ItemCategory", foreign_keys=[category_id], lazy="joined")

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
    source_requisition_id = Column(Integer, ForeignKey("purchase_requisitions.id"), index=True)
    source_quotation_id = Column(Integer, ForeignKey("supplier_quotations.id"), index=True)
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
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_grn_company_number"),
        UniqueConstraint("purchase_invoice_id", name="uq_grn_purchase_invoice"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    receipt_date = Column(Date, nullable=False)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    status = Column(String(20), nullable=False, default="POSTED")
    total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    purchase_order = relationship("PurchaseOrder", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")
    journal = relationship("JournalEntry")
    purchase_invoice = relationship("PurchaseInvoice", foreign_keys=[purchase_invoice_id])
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


# -------------------- Controlled procurement: PR -> RFQ -> quotations -> PO

class PurchaseRequisition(Base):
    __tablename__ = "purchase_requisitions"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_pr_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    request_date = Column(Date, nullable=False, index=True)
    needed_by = Column(Date, nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    # A requisition may carry a requester suggestion for benchmarking and
    # continuity, but procurement remains free to invite and award other
    # suppliers through the controlled RFQ comparison.
    suggested_supplier_id = Column(Integer, ForeignKey("parties.id"), index=True)
    department = Column(String(120), nullable=False)
    justification = Column(String(500), nullable=False)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    estimated_total = Column(Numeric(18, 2), nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime)
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    rejected_by = Column(Integer, ForeignKey("users.id"))
    rejected_at = Column(DateTime)
    rejection_reason = Column(String(500))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    warehouse = relationship("Warehouse", lazy="joined")
    suggested_supplier = relationship("Party", foreign_keys=[suggested_supplier_id], lazy="joined")
    lines = relationship("PurchaseRequisitionLine", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")


class PurchaseRequisitionLine(Base):
    __tablename__ = "purchase_requisition_lines"
    id = Column(Integer, primary_key=True)
    requisition_id = Column(Integer, ForeignKey("purchase_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    estimated_unit_price = Column(Numeric(18, 4), nullable=False, default=0)
    specifications = Column(String(500))
    requisition = relationship("PurchaseRequisition", back_populates="lines")
    item = relationship("Item", lazy="joined")


class RequestForQuotation(Base):
    __tablename__ = "requests_for_quotation"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_rfq_company_number"),
        UniqueConstraint("requisition_id", name="uq_rfq_requisition"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    requisition_id = Column(Integer, ForeignKey("purchase_requisitions.id"), nullable=False, index=True)
    issue_date = Column(Date, nullable=False)
    closing_date = Column(Date, nullable=False)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    issued_at = Column(DateTime)
    awarded_quotation_id = Column(Integer, ForeignKey("supplier_quotations.id"))
    award_reason = Column(String(500))
    awarded_by = Column(Integer, ForeignKey("users.id"))
    awarded_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    requisition = relationship("PurchaseRequisition", lazy="joined")
    suppliers = relationship("RFQSupplier", back_populates="rfq", cascade="all, delete-orphan", lazy="selectin")
    lines = relationship("RFQLine", back_populates="rfq", cascade="all, delete-orphan", lazy="selectin")
    quotations = relationship("SupplierQuotation", back_populates="rfq", foreign_keys="SupplierQuotation.rfq_id", lazy="selectin")


class RFQSupplier(Base):
    __tablename__ = "rfq_suppliers"
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id", name="uq_rfq_supplier"),)
    id = Column(Integer, primary_key=True)
    rfq_id = Column(Integer, ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    rfq = relationship("RequestForQuotation", back_populates="suppliers")
    supplier = relationship("Party", lazy="joined")


class RFQLine(Base):
    __tablename__ = "rfq_lines"
    __table_args__ = (UniqueConstraint("rfq_id", "requisition_line_id", name="uq_rfq_requisition_line"),)
    id = Column(Integer, primary_key=True)
    rfq_id = Column(Integer, ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False, index=True)
    requisition_line_id = Column(Integer, ForeignKey("purchase_requisition_lines.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    specifications = Column(String(500))
    rfq = relationship("RequestForQuotation", back_populates="lines")
    item = relationship("Item", lazy="joined")


class SupplierQuotation(Base):
    __tablename__ = "supplier_quotations"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_supplier_quote_company_number"),
        UniqueConstraint("rfq_id", "supplier_id", name="uq_supplier_quote_rfq_supplier"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    supplier_reference = Column(String(100), nullable=False)
    quote_date = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)
    lead_time_days = Column(Integer, nullable=False, default=0)
    payment_terms = Column(String(250))
    status = Column(String(25), nullable=False, default="SUBMITTED", index=True)
    subtotal = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    rfq = relationship("RequestForQuotation", back_populates="quotations", foreign_keys=[rfq_id])
    supplier = relationship("Party", lazy="joined")
    lines = relationship("SupplierQuotationLine", back_populates="quotation", cascade="all, delete-orphan", lazy="selectin")


class SupplierQuotationLine(Base):
    __tablename__ = "supplier_quotation_lines"
    __table_args__ = (UniqueConstraint("quotation_id", "rfq_line_id", name="uq_supplier_quote_rfq_line"),)
    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("supplier_quotations.id", ondelete="CASCADE"), nullable=False, index=True)
    rfq_line_id = Column(Integer, ForeignKey("rfq_lines.id"), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    line_subtotal = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    line_total = Column(Numeric(18, 2), nullable=False)
    quotation = relationship("SupplierQuotation", back_populates="lines")
    rfq_line = relationship("RFQLine", lazy="joined")


class SupplierProcurementProfile(Base):
    """Controlled supplier attributes that do not belong in the AP party card.

    Banking changes deliberately use a pending/approved pair so the maker can
    never silently replace the payment destination used by treasury.
    """
    __tablename__ = "supplier_procurement_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", "supplier_id", name="uq_supplier_procurement_profile"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True)
    commercial_registration = Column(String(80))
    contact_name = Column(String(160))
    contact_email = Column(String(254))
    contact_phone = Column(String(40))
    payment_terms_days = Column(Integer, nullable=False, default=30)
    delivery_score = Column(Numeric(5, 2), nullable=False, default=0)
    quality_score = Column(Numeric(5, 2), nullable=False, default=0)
    price_score = Column(Numeric(5, 2), nullable=False, default=0)
    rejection_rate = Column(Numeric(7, 4), nullable=False, default=0)
    approved_iban = Column(EncryptedString(1024))
    pending_iban = Column(EncryptedString(1024))
    iban_status = Column(String(25), nullable=False, default="NOT_PROVIDED", index=True)
    iban_change_risk = Column(String(20), nullable=False, default="NONE", index=True)
    iban_change_requested_by = Column(Integer, ForeignKey("users.id"))
    iban_change_requested_at = Column(DateTime)
    iban_approved_by = Column(Integer, ForeignKey("users.id"))
    iban_approved_at = Column(DateTime)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    supplier = relationship("Party", lazy="joined")


# -------------------- IFRS 15 / gym contracts --------------------

__all__ = ['Warehouse', 'Item', 'StockMovement', 'PurchaseOrder', 'PurchaseOrderLine', 'GoodsReceipt', 'GoodsReceiptLine',
           'PurchaseRequisition', 'PurchaseRequisitionLine', 'RequestForQuotation', 'RFQSupplier', 'RFQLine',
           'SupplierQuotation', 'SupplierQuotationLine', 'SupplierProcurementProfile']
