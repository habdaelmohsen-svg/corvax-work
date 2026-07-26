from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class ImportDeclaration(Base):
    __tablename__ = "import_declarations"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_import_declaration_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    declaration_date = Column(Date, nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id"), index=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), index=True)
    goods_receipt_id = Column(Integer, ForeignKey("goods_receipts.id"), index=True)
    origin_country = Column(String(3), nullable=False, index=True)
    customs_port = Column(String(120))
    customs_reference = Column(String(120))
    treatment = Column(String(30), nullable=False, index=True)  # AT_CUSTOMS / THROUGH_RETURN / SUSPENDED / EXEMPT
    customs_value = Column(Numeric(18, 2), nullable=False, default=0)
    freight_insurance_value = Column(Numeric(18, 2), nullable=False, default=0)
    customs_duty = Column(Numeric(18, 2), nullable=False, default=0)
    excise_tax = Column(Numeric(18, 2), nullable=False, default=0)
    other_customs_charges = Column(Numeric(18, 2), nullable=False, default=0)
    vat_base = Column(Numeric(18, 2), nullable=False, default=0)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    vat_due = Column(Numeric(18, 2), nullable=False, default=0)
    vat_collected_on_declaration = Column(Numeric(18, 2), nullable=False, default=0)
    vat_accounted_in_return = Column(Numeric(18, 2), nullable=False, default=0)
    release_date = Column(Date)
    evidence_json = Column(Text, nullable=False, default="{}")
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    posted_by = Column(Integer, ForeignKey("users.id"))
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)
    posted_at = Column(DateTime)

    supplier = relationship("Party", lazy="joined")
    purchase_invoice = relationship("PurchaseInvoice", lazy="joined")
    goods_receipt = relationship("GoodsReceipt", lazy="joined")
    journal = relationship("JournalEntry", lazy="joined")
    lines = relationship("ImportDeclarationLine", back_populates="declaration", cascade="all, delete-orphan", lazy="selectin")


class ImportDeclarationLine(Base):
    __tablename__ = "import_declaration_lines"

    id = Column(Integer, primary_key=True)
    declaration_id = Column(Integer, ForeignKey("import_declarations.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), index=True)
    hs_code = Column(String(30))
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False, default=0)
    uom = Column(String(20), nullable=False, default="EA")
    customs_value = Column(Numeric(18, 2), nullable=False, default=0)
    customs_duty = Column(Numeric(18, 2), nullable=False, default=0)
    excise_tax = Column(Numeric(18, 2), nullable=False, default=0)
    other_charges = Column(Numeric(18, 2), nullable=False, default=0)
    vat_base = Column(Numeric(18, 2), nullable=False, default=0)
    vat_due = Column(Numeric(18, 2), nullable=False, default=0)

    declaration = relationship("ImportDeclaration", back_populates="lines")
    item = relationship("Item", lazy="joined")


class ExportEvidence(Base):
    __tablename__ = "export_evidence"
    __table_args__ = (UniqueConstraint("company_id", "sales_invoice_id", name="uq_export_evidence_invoice"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    sales_invoice_id = Column(Integer, ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    export_declaration_number = Column(String(100), nullable=False)
    export_date = Column(Date, nullable=False, index=True)
    destination_country = Column(String(3), nullable=False)
    exit_port = Column(String(120))
    transport_document = Column(String(120), nullable=False)
    evidence_json = Column(Text, nullable=False, default="{}")
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)

    sales_invoice = relationship("SalesInvoice", lazy="joined")


class LandedCostDocument(Base):
    __tablename__ = "landed_cost_documents"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_landed_cost_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    document_date = Column(Date, nullable=False, index=True)
    goods_receipt_id = Column(Integer, ForeignKey("goods_receipts.id"), nullable=False, index=True)
    import_declaration_id = Column(Integer, ForeignKey("import_declarations.id"), index=True)
    allocation_method = Column(String(20), nullable=False, default="VALUE")  # VALUE / QUANTITY / EQUAL
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    total_capitalizable_cost = Column(Numeric(18, 2), nullable=False, default=0)
    total_noncapitalizable_cost = Column(Numeric(18, 2), nullable=False, default=0)
    clearing_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    posted_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)
    posted_at = Column(DateTime)

    goods_receipt = relationship("GoodsReceipt", lazy="joined")
    import_declaration = relationship("ImportDeclaration", lazy="joined")
    clearing_account = relationship("Account", foreign_keys=[clearing_account_id], lazy="joined")
    journal = relationship("JournalEntry", lazy="joined")
    charges = relationship("LandedCostCharge", back_populates="document", cascade="all, delete-orphan", lazy="selectin")
    allocations = relationship("LandedCostAllocation", back_populates="document", cascade="all, delete-orphan", lazy="selectin")


class LandedCostCharge(Base):
    __tablename__ = "landed_cost_charges"

    id = Column(Integer, primary_key=True)
    landed_cost_id = Column(Integer, ForeignKey("landed_cost_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    supplier_invoice_number = Column(String(100), nullable=False)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    charge_type = Column(String(30), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    capitalizable = Column(Boolean, nullable=False, default=True)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id"), nullable=False)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"))

    document = relationship("LandedCostDocument", back_populates="charges")
    supplier = relationship("Party", lazy="joined")
    tax_code = relationship("TaxCode", lazy="joined")
    purchase_invoice = relationship("PurchaseInvoice", lazy="joined")


class LandedCostAllocation(Base):
    __tablename__ = "landed_cost_allocations"

    id = Column(Integer, primary_key=True)
    landed_cost_id = Column(Integer, ForeignKey("landed_cost_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    goods_receipt_line_id = Column(Integer, ForeignKey("goods_receipt_lines.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    allocation_basis = Column(Numeric(18, 6), nullable=False, default=0)
    allocated_amount = Column(Numeric(18, 2), nullable=False, default=0)
    unit_cost_increment = Column(Numeric(18, 6), nullable=False, default=0)
    stock_movement_id = Column(Integer, ForeignKey("stock_movements.id"))

    document = relationship("LandedCostDocument", back_populates="allocations")
    goods_receipt_line = relationship("GoodsReceiptLine", lazy="joined")
    item = relationship("Item", lazy="joined")
    stock_movement = relationship("StockMovement", lazy="joined")


class CostRollupSnapshot(Base):
    __tablename__ = "cost_rollup_snapshots"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_cost_rollup_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    bom_id = Column(Integer, ForeignKey("bills_of_material.id"), nullable=False)
    as_of_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    cost_basis = Column(String(20), nullable=False, default="STANDARD")
    status = Column(String(25), nullable=False, default="READY_FOR_REVIEW", index=True)
    direct_material_cost = Column(Numeric(18, 2), nullable=False, default=0)
    packaging_cost = Column(Numeric(18, 2), nullable=False, default=0)
    direct_labor_cost = Column(Numeric(18, 2), nullable=False, default=0)
    direct_expense_cost = Column(Numeric(18, 2), nullable=False, default=0)
    variable_overhead_cost = Column(Numeric(18, 2), nullable=False, default=0)
    fixed_overhead_cost = Column(Numeric(18, 2), nullable=False, default=0)
    total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    unit_cost = Column(Numeric(18, 6), nullable=False, default=0)
    current_standard_cost = Column(Numeric(18, 6), nullable=False, default=0)
    standard_cost_variance = Column(Numeric(18, 2), nullable=False, default=0)
    analysis_hash = Column(String(64), nullable=False)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

    item = relationship("Item", lazy="joined")
    bom = relationship("BillOfMaterial", lazy="joined")
    lines = relationship("CostRollupLine", back_populates="snapshot", cascade="all, delete-orphan", lazy="selectin")


class CostRollupLine(Base):
    __tablename__ = "cost_rollup_lines"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("cost_rollup_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    level = Column(Integer, nullable=False, default=0)
    path = Column(String(500), nullable=False)
    parent_item_id = Column(Integer, ForeignKey("items.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    line_type = Column(String(30), nullable=False, index=True)
    description_ar = Column(String(500), nullable=False)
    description_en = Column(String(500), nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False, default=0)
    unit_cost = Column(Numeric(18, 6), nullable=False, default=0)
    total_cost = Column(Numeric(18, 2), nullable=False, default=0)
    source_reference = Column(String(120))

    snapshot = relationship("CostRollupSnapshot", back_populates="lines")
    parent_item = relationship("Item", foreign_keys=[parent_item_id], lazy="joined")
    item = relationship("Item", foreign_keys=[item_id], lazy="joined")


class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_inventory_count_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    count_date = Column(Date, nullable=False, index=True)
    count_type = Column(String(20), nullable=False, default="FULL")
    status = Column(String(25), nullable=False, default="FROZEN", index=True)
    loss_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    gain_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    frozen_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)

    warehouse = relationship("Warehouse", lazy="joined")
    journal = relationship("JournalEntry", lazy="joined")
    lines = relationship("InventoryCountLine", back_populates="count", cascade="all, delete-orphan", lazy="selectin")


class InventoryCountLine(Base):
    __tablename__ = "inventory_count_lines"
    __table_args__ = (UniqueConstraint("inventory_count_id", "item_id", "lot_number", name="uq_inventory_count_item_lot"),)

    id = Column(Integer, primary_key=True)
    inventory_count_id = Column(Integer, ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    lot_number = Column(String(80), nullable=False, default="")
    book_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    book_value = Column(Numeric(18, 2), nullable=False, default=0)
    counted_quantity = Column(Numeric(18, 4))
    variance_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    unit_cost = Column(Numeric(18, 6), nullable=False, default=0)
    variance_value = Column(Numeric(18, 2), nullable=False, default=0)
    reason = Column(String(500))

    count = relationship("InventoryCount", back_populates="lines")
    item = relationship("Item", lazy="joined")


class InventoryWriteDown(Base):
    __tablename__ = "inventory_write_downs"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_inventory_write_down_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    write_down_date = Column(Date, nullable=False, index=True)
    reason_type = Column(String(20), nullable=False, index=True)  # NRV / OBSOLETE / DAMAGE / EXPIRED
    quantity = Column(Numeric(18, 4), nullable=False)
    carrying_unit_cost = Column(Numeric(18, 6), nullable=False)
    nrv_unit_cost = Column(Numeric(18, 6), nullable=False, default=0)
    write_down_amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(25), nullable=False, default="PENDING_APPROVAL", index=True)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    provision_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)

    warehouse = relationship("Warehouse", lazy="joined")
    item = relationship("Item", lazy="joined")
    journal = relationship("JournalEntry", lazy="joined")


class ItemUomConversion(Base):
    __tablename__ = "item_uom_conversions"
    __table_args__ = (UniqueConstraint("item_id", "from_uom", "to_uom", name="uq_item_uom_conversion"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    from_uom = Column(String(20), nullable=False)
    to_uom = Column(String(20), nullable=False)
    factor = Column(Numeric(18, 8), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    item = relationship("Item", lazy="joined")


__all__ = [
    "ImportDeclaration", "ImportDeclarationLine", "ExportEvidence",
    "LandedCostDocument", "LandedCostCharge", "LandedCostAllocation",
    "CostRollupSnapshot", "CostRollupLine", "InventoryCount", "InventoryCountLine",
    "InventoryWriteDown", "ItemUomConversion",
]
