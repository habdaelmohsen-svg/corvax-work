from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class LeaseVariablePayment(Base):
    __tablename__ = "lease_variable_payments"
    id = Column(Integer, primary_key=True)
    lease_id = Column(Integer, ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_date = Column(Date, nullable=False, index=True)
    payment_basis = Column(String(30), nullable=False)  # INDEX_RATE / PERFORMANCE_USAGE / RESIDUAL_GUARANTEE
    amount = Column(Numeric(18, 2), nullable=False)
    included_in_liability = Column(Boolean, nullable=False, default=False)
    remeasurement_amount = Column(Numeric(18, 2), nullable=False, default=0)
    pnl_expense_amount = Column(Numeric(18, 2), nullable=False, default=0)
    reason = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    lease = relationship("LeaseContract", lazy="joined")
    journal = relationship("JournalEntry")


class SaleLeasebackTransaction(Base):
    __tablename__ = "sale_leaseback_transactions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    lease_id = Column(Integer, ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    transfer_is_sale = Column(Boolean, nullable=False)
    carrying_amount = Column(Numeric(18, 2), nullable=False)
    fair_value = Column(Numeric(18, 2), nullable=False)
    sale_proceeds = Column(Numeric(18, 2), nullable=False)
    retained_right_percent = Column(Numeric(9, 6), nullable=False)
    initial_rou_asset = Column(Numeric(18, 2), nullable=False, default=0)
    lease_liability = Column(Numeric(18, 2), nullable=False, default=0)
    gain_on_rights_transferred = Column(Numeric(18, 2), nullable=False, default=0)
    financing_liability = Column(Numeric(18, 2), nullable=False, default=0)
    off_market_adjustment = Column(Numeric(18, 2), nullable=False, default=0)
    evidence_reference = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    lease = relationship("LeaseContract", lazy="joined")
    journal = relationship("JournalEntry")


class SubleaseArrangement(Base):
    __tablename__ = "sublease_arrangements"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    head_lease_id = Column(Integer, ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    commencement_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    remaining_head_lease_months = Column(Integer, nullable=False)
    sublease_months = Column(Integer, nullable=False)
    classification = Column(String(20), nullable=False)  # FINANCE / OPERATING
    payment_amount = Column(Numeric(18, 2), nullable=False)
    discount_rate = Column(Numeric(9, 6), nullable=False)
    net_investment = Column(Numeric(18, 2), nullable=False, default=0)
    derecognized_rou_asset = Column(Numeric(18, 2), nullable=False, default=0)
    gain_loss = Column(Numeric(18, 2), nullable=False, default=0)
    evidence_reference = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    head_lease = relationship("LeaseContract", lazy="joined")
    journal = relationship("JournalEntry")


__all__ = ["LeaseVariablePayment", "SaleLeasebackTransaction", "SubleaseArrangement"]
