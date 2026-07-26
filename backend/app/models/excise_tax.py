from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class ExciseTaxCategory(Base):
    __tablename__ = "excise_tax_categories"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_excise_category_company_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    statutory_rate = Column(Numeric(8, 4), nullable=False)
    tariff_reference = Column(String(120))
    system_code = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)


class ExciseWarehouseProfile(Base):
    __tablename__ = "excise_warehouse_profiles"
    __table_args__ = (UniqueConstraint("company_id", "warehouse_id", name="uq_excise_warehouse_company_warehouse"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)
    license_number = Column(String(150), nullable=False)
    license_start_date = Column(Date, nullable=False)
    license_expiry_date = Column(Date, nullable=False)
    permitted_activities = Column(String(250), nullable=False, default="STORE")
    bank_guarantee_amount = Column(Numeric(18, 2), nullable=False, default=0)
    estimated_monthly_excise_value = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(30), nullable=False, default="ACTIVE", index=True)
    notes = Column(String(1000))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    warehouse = relationship("Warehouse", lazy="joined")


class ExciseProduct(Base):
    __tablename__ = "excise_products"
    __table_args__ = (UniqueConstraint("company_id", "item_id", name="uq_excise_product_company_item"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("excise_tax_categories.id"), nullable=False, index=True)
    hs_code = Column(String(30))
    zatca_registration_reference = Column(String(150))
    registered_retail_price = Column(Numeric(18, 4), nullable=False, default=0)
    indicative_price = Column(Numeric(18, 4), nullable=False, default=0)
    package_quantity = Column(Numeric(18, 4), nullable=False, default=1)
    package_uom = Column(String(20), nullable=False, default="EA")
    tax_stamp_required = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    item = relationship("Item", lazy="joined")
    category = relationship("ExciseTaxCategory", lazy="joined")


class ExciseMovement(Base):
    __tablename__ = "excise_movements"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_excise_movement_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    movement_date = Column(Date, nullable=False, index=True)
    event_type = Column(String(40), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("excise_products.id"), nullable=False, index=True)
    warehouse_profile_id = Column(Integer, ForeignKey("excise_warehouse_profiles.id"), index=True)
    destination_warehouse_profile_id = Column(Integer, ForeignKey("excise_warehouse_profiles.id"), index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    taxable_unit_value = Column(Numeric(18, 4), nullable=False, default=0)
    taxable_value = Column(Numeric(18, 2), nullable=False, default=0)
    excise_rate = Column(Numeric(8, 4), nullable=False, default=0)
    excise_amount = Column(Numeric(18, 2), nullable=False, default=0)
    customs_declaration_number = Column(String(150))
    customs_excise_paid = Column(Numeric(18, 2), nullable=False, default=0)
    tax_settlement_method = Column(String(30), nullable=False, default="SUSPENDED")
    debit_account_id = Column(Integer, ForeignKey("accounts.id"))
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"))
    reference = Column(String(150))
    description = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)

    product = relationship("ExciseProduct", lazy="joined")
    warehouse_profile = relationship("ExciseWarehouseProfile", foreign_keys=[warehouse_profile_id], lazy="joined")
    destination_warehouse_profile = relationship("ExciseWarehouseProfile", foreign_keys=[destination_warehouse_profile_id], lazy="joined")
    debit_account = relationship("Account", foreign_keys=[debit_account_id], lazy="joined")
    bank_account = relationship("BankAccount", foreign_keys=[bank_account_id], lazy="joined")
    journal = relationship("JournalEntry")


class ExciseTaxReturn(Base):
    __tablename__ = "excise_tax_returns"
    __table_args__ = (UniqueConstraint("company_id", "period_start", "period_end", name="uq_excise_return_company_period"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    taxable_value = Column(Numeric(18, 2), nullable=False, default=0)
    gross_excise = Column(Numeric(18, 2), nullable=False, default=0)
    customs_paid = Column(Numeric(18, 2), nullable=False, default=0)
    tax_payable = Column(Numeric(18, 2), nullable=False, default=0)
    gl_payable = Column(Numeric(18, 2), nullable=False, default=0)
    reconciliation_difference = Column(Numeric(18, 2), nullable=False, default=0)
    estimated_late_penalty = Column(Numeric(18, 2), nullable=False, default=0)
    sadad_invoice_number = Column(String(120))
    payment_reference = Column(String(150))
    payment_date = Column(Date)
    payment_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    paid_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)
    paid_at = Column(DateTime)

    lines = relationship("ExciseTaxReturnLine", back_populates="tax_return", cascade="all, delete-orphan", lazy="selectin")
    payment_journal = relationship("JournalEntry")


class ExciseTaxReturnLine(Base):
    __tablename__ = "excise_tax_return_lines"
    __table_args__ = (UniqueConstraint("return_id", "category_id", name="uq_excise_return_line_category"),)

    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("excise_tax_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("excise_tax_categories.id"), nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False, default=0)
    taxable_value = Column(Numeric(18, 2), nullable=False, default=0)
    gross_excise = Column(Numeric(18, 2), nullable=False, default=0)
    customs_paid = Column(Numeric(18, 2), nullable=False, default=0)
    tax_payable = Column(Numeric(18, 2), nullable=False, default=0)
    movement_count = Column(Integer, nullable=False, default=0)
    details_json = Column(Text, nullable=False, default="[]")

    tax_return = relationship("ExciseTaxReturn", back_populates="lines")
    category = relationship("ExciseTaxCategory", lazy="joined")


__all__ = [
    "ExciseTaxCategory", "ExciseWarehouseProfile", "ExciseProduct", "ExciseMovement",
    "ExciseTaxReturn", "ExciseTaxReturnLine",
]
