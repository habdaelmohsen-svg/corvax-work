"""CORVAX RC27.4 H11 - Sales commissions (inside the Sales department).

Design agreed with the owner:
  * Beneficiaries: internal sales reps AND external brokers (beneficiary_type).
  * Rate: flexible per rule - percentage of invoice, fixed amount, or per beneficiary.
  * Accrual in two stages tied to sale AND collection:
      1. On sales-invoice post -> commission accrues as expense + PENDING liability
         (not yet payable).
      2. As the invoice is collected -> the payable portion opens up in proportion to
         the collected ratio.
  * Approval required before payment (segregation of duties).

Bilingual (Arabic + English) and company-scoped. Base from app.db, matching H9/H10.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class CommissionBeneficiary(Base):
    """A sales rep (employee) or an external broker who earns commissions."""
    __tablename__ = "commission_beneficiaries"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_commission_beneficiary_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    beneficiary_type = Column(String(20), nullable=False, default="SALES_REP")  # SALES_REP / BROKER
    # Default rule for this beneficiary; can be overridden per assignment.
    default_basis = Column(String(20), nullable=False, default="PERCENTAGE")  # PERCENTAGE / FIXED
    default_rate = Column(Numeric(10, 4), nullable=False, default=0)  # percent when PERCENTAGE, amount when FIXED
    phone = Column(String(30))
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class CommissionAccrual(Base):
    """A commission earned on one sales invoice by one beneficiary.

    Lifecycle of `status`:
      PENDING     -> accrued on invoice post, not payable yet (nothing collected)
      PARTIAL     -> some of the invoice collected; payable_amount > 0 but < amount
      PAYABLE     -> invoice fully collected; whole commission payable
      APPROVED    -> approved by a manager, ready to pay
      PAID        -> paid out
      CANCELLED   -> reversed
    """
    __tablename__ = "commission_accruals"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    beneficiary_id = Column(Integer, ForeignKey("commission_beneficiaries.id"), nullable=False, index=True)
    sales_invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=False, index=True)
    basis = Column(String(20), nullable=False, default="PERCENTAGE")  # PERCENTAGE / FIXED
    rate = Column(Numeric(10, 4), nullable=False, default=0)  # percent or fixed amount used
    invoice_base_amount = Column(Numeric(18, 2), nullable=False, default=0)  # subtotal the % applies to
    amount = Column(Numeric(18, 2), nullable=False, default=0)  # full earned commission
    collected_ratio = Column(Numeric(8, 4), nullable=False, default=0)  # 0..1 portion of invoice collected
    payable_amount = Column(Numeric(18, 2), nullable=False, default=0)  # amount * collected_ratio, unlocked to pay
    paid_amount = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    accrual_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    paid_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    beneficiary = relationship("CommissionBeneficiary", lazy="joined")
    invoice = relationship("SalesInvoice", lazy="joined")


__all__ = ["CommissionBeneficiary", "CommissionAccrual"]
