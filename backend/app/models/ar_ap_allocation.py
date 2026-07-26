from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class FinancialOpenItem(Base):
    __tablename__ = "financial_open_items"
    __table_args__ = (
        UniqueConstraint("company_id", "ledger_type", "source_type", "source_id", name="uq_open_item_source"),
        UniqueConstraint("company_id", "ledger_type", "document_number", name="uq_open_item_document"),
        CheckConstraint("ledger_type in ('AR','AP')", name="ck_open_item_ledger_type"),
        CheckConstraint("original_amount > 0", name="ck_open_item_positive_amount"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    ledger_type = Column(String(2), nullable=False, index=True)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    source_type = Column(String(30), nullable=False, index=True)
    source_id = Column(Integer)
    document_number = Column(String(100), nullable=False, index=True)
    document_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False, index=True)
    original_amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(15), nullable=False, default="OPEN", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    notes = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    party = relationship("Party", lazy="joined")
    journal = relationship("JournalEntry")
    allocations = relationship("FinancialSettlementAllocation", back_populates="open_item", cascade="all, delete-orphan", lazy="selectin")


class FinancialSettlementAllocation(Base):
    __tablename__ = "financial_settlement_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlement_allocation_positive"),
        CheckConstraint(
            "(receipt_id is not null and payment_id is null) or (receipt_id is null and payment_id is not null)",
            name="ck_settlement_allocation_one_source",
        ),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    open_item_id = Column(Integer, ForeignKey("financial_open_items.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    allocation_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reversed_by = Column(Integer, ForeignKey("users.id"))
    reversed_at = Column(DateTime)
    reversal_reason = Column(String(500))

    open_item = relationship("FinancialOpenItem", back_populates="allocations")
    receipt = relationship("Receipt")
    payment = relationship("Payment")


__all__ = ["FinancialOpenItem", "FinancialSettlementAllocation"]
