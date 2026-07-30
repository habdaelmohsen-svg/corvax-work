from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class ItemCategory(Base):
    __tablename__ = "item_categories"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_item_category_company_code"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    parent_id = Column(Integer, ForeignKey("item_categories.id"))
    default_item_type = Column(String(30), nullable=False, default="INVENTORY")
    inventory_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    cogs_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    revenue_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    valuation_method = Column(String(30), nullable=False, default="WEIGHTED_AVERAGE")
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    parent = relationship("ItemCategory", remote_side=[id], lazy="joined")
    inventory_account = relationship("Account", foreign_keys=[inventory_account_id], lazy="joined")
    cogs_account = relationship("Account", foreign_keys=[cogs_account_id], lazy="joined")
    revenue_account = relationship("Account", foreign_keys=[revenue_account_id], lazy="joined")


class OpeningBalanceBatch(Base):
    __tablename__ = "opening_balance_batches"
    __table_args__ = (
        UniqueConstraint("company_id", "opening_date", "version", name="uq_opening_balance_batch_version"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    opening_date = Column(Date, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    source_system = Column(String(120), nullable=False)
    source_filename = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    total_debit = Column(Numeric(18, 2), nullable=False, default=0)
    total_credit = Column(Numeric(18, 2), nullable=False, default=0)
    validation_hash = Column(String(64), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    posted_at = Column(DateTime)

    journal = relationship("JournalEntry", lazy="joined")
    lines = relationship(
        "OpeningBalanceLine",
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OpeningBalanceLine.line_number",
    )


class OpeningBalanceLine(Base):
    __tablename__ = "opening_balance_lines"
    __table_args__ = (
        UniqueConstraint("batch_id", "line_number", name="uq_opening_balance_batch_line"),
    )

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("opening_balance_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    line_type = Column(String(20), nullable=False, default="GL", index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    party_id = Column(Integer, ForeignKey("parties.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"))
    reference_code = Column(String(100))
    document_date = Column(Date)
    due_date = Column(Date)
    quantity = Column(Numeric(18, 4))
    unit_cost = Column(Numeric(18, 4))
    lot_number = Column(String(80))
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    description = Column(String(500))

    batch = relationship("OpeningBalanceBatch", back_populates="lines")
    account = relationship("Account", lazy="joined")
    party = relationship("Party", lazy="joined")
    item = relationship("Item", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")


__all__ = ["ItemCategory", "OpeningBalanceBatch", "OpeningBalanceLine"]
