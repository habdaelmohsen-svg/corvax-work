from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class ZakatTaxpayerProfile(Base):
    __tablename__ = "zakat_taxpayer_profiles"
    __table_args__ = (UniqueConstraint("company_id", name="uq_zakat_taxpayer_profile_company"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    zakat_registration_number = Column(String(120))
    cit_registration_number = Column(String(120))
    return_basis = Column(String(30), nullable=False, default="MIXED")  # ZAKAT / CIT / MIXED
    saudi_gcc_ownership_percent = Column(Numeric(8, 4), nullable=False, default=100)
    non_saudi_ownership_percent = Column(Numeric(8, 4), nullable=False, default=0)
    zakat_rate_hijri = Column(Numeric(10, 6), nullable=False, default=2.5)
    hijri_year_days = Column(Integer, nullable=False, default=354)
    income_tax_rate = Column(Numeric(10, 6), nullable=False, default=20)
    tax_loss_utilization_cap_percent = Column(Numeric(10, 6), nullable=False, default=25)
    zakat_method = Column(String(50), nullable=False, default="FINANCING_SOURCES_LESS_DEDUCTIBLE_ASSETS")
    minimum_zakat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True, index=True)
    notes = Column(String(1000))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class TaxLossCarryforward(Base):
    __tablename__ = "tax_loss_carryforwards"
    __table_args__ = (UniqueConstraint("company_id", "origin_year", name="uq_tax_loss_company_year"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    origin_year = Column(Integer, nullable=False, index=True)
    original_amount = Column(Numeric(18, 2), nullable=False, default=0)
    utilized_amount = Column(Numeric(18, 2), nullable=False, default=0)
    expired_amount = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(30), nullable=False, default="AVAILABLE", index=True)
    evidence_reference = Column(String(250))
    notes = Column(String(1000))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class ZakatIncomeTaxReturn(Base):
    __tablename__ = "zakat_income_tax_returns"
    __table_args__ = (UniqueConstraint("company_id", "period_start", "period_end", name="uq_zakat_income_tax_return_period"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    calculation_status = Column(String(50), nullable=False, default="PREPARATION_REVIEW_REQUIRED")

    fiscal_days = Column(Integer, nullable=False, default=365)
    accounting_profit_before_zakat_tax = Column(Numeric(18, 2), nullable=False, default=0)
    cit_additions = Column(Numeric(18, 2), nullable=False, default=0)
    cit_deductions = Column(Numeric(18, 2), nullable=False, default=0)
    adjusted_taxable_profit = Column(Numeric(18, 2), nullable=False, default=0)
    non_saudi_ownership_percent = Column(Numeric(8, 4), nullable=False, default=0)
    cit_base_before_losses = Column(Numeric(18, 2), nullable=False, default=0)
    tax_losses_utilized = Column(Numeric(18, 2), nullable=False, default=0)
    income_tax_base = Column(Numeric(18, 2), nullable=False, default=0)
    income_tax_rate = Column(Numeric(10, 6), nullable=False, default=20)
    gross_income_tax = Column(Numeric(18, 2), nullable=False, default=0)
    cit_credits = Column(Numeric(18, 2), nullable=False, default=0)
    income_tax_payable = Column(Numeric(18, 2), nullable=False, default=0)

    gl_equity_balance = Column(Numeric(18, 2), nullable=False, default=0)
    gl_non_current_liabilities = Column(Numeric(18, 2), nullable=False, default=0)
    gl_deductible_non_current_assets = Column(Numeric(18, 2), nullable=False, default=0)
    zakat_additions = Column(Numeric(18, 2), nullable=False, default=0)
    zakat_deductions = Column(Numeric(18, 2), nullable=False, default=0)
    gross_zakat_base = Column(Numeric(18, 2), nullable=False, default=0)
    saudi_gcc_ownership_percent = Column(Numeric(8, 4), nullable=False, default=100)
    zakat_base = Column(Numeric(18, 2), nullable=False, default=0)
    zakat_rate = Column(Numeric(10, 6), nullable=False, default=0)
    gross_zakat = Column(Numeric(18, 2), nullable=False, default=0)
    zakat_credits = Column(Numeric(18, 2), nullable=False, default=0)
    zakat_payable = Column(Numeric(18, 2), nullable=False, default=0)

    total_gross_charge = Column(Numeric(18, 2), nullable=False, default=0)
    total_credits = Column(Numeric(18, 2), nullable=False, default=0)
    total_payable = Column(Numeric(18, 2), nullable=False, default=0)
    gl_payable = Column(Numeric(18, 2), nullable=False, default=0)
    reconciliation_difference = Column(Numeric(18, 2), nullable=False, default=0)

    accrual_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    payment_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    sadad_invoice_number = Column(String(120))
    payment_reference = Column(String(150))
    payment_date = Column(Date)
    notes = Column(String(1500))

    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    paid_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)
    paid_at = Column(DateTime)

    adjustments = relationship("ZakatTaxAdjustment", back_populates="tax_return", cascade="all, delete-orphan", lazy="selectin")
    loss_usages = relationship("TaxLossUtilization", back_populates="tax_return", cascade="all, delete-orphan", lazy="selectin")
    accrual_journal = relationship("JournalEntry", foreign_keys=[accrual_journal_id])
    payment_journal = relationship("JournalEntry", foreign_keys=[payment_journal_id])


class ZakatTaxAdjustment(Base):
    __tablename__ = "zakat_tax_adjustments"

    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("zakat_income_tax_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    regime = Column(String(20), nullable=False, index=True)  # CIT / ZAKAT
    direction = Column(String(20), nullable=False, index=True)  # ADD / DEDUCT
    code = Column(String(60), nullable=False, index=True)
    description_ar = Column(String(500), nullable=False)
    description_en = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    source_account_code = Column(String(30))
    evidence_reference = Column(String(250))
    recurring = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    tax_return = relationship("ZakatIncomeTaxReturn", back_populates="adjustments")


class TaxLossUtilization(Base):
    __tablename__ = "tax_loss_utilizations"
    __table_args__ = (UniqueConstraint("return_id", "loss_id", name="uq_tax_loss_utilization_return_loss"),)

    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("zakat_income_tax_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    loss_id = Column(Integer, ForeignKey("tax_loss_carryforwards.id"), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    tax_return = relationship("ZakatIncomeTaxReturn", back_populates="loss_usages")
    loss = relationship("TaxLossCarryforward", lazy="joined")


__all__ = [
    "ZakatTaxpayerProfile", "TaxLossCarryforward", "ZakatIncomeTaxReturn",
    "ZakatTaxAdjustment", "TaxLossUtilization",
]
