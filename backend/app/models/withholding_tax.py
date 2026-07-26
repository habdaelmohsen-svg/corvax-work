from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class WithholdingTaxCategory(Base):
    __tablename__ = "withholding_tax_categories"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_wht_category_company_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    statutory_rate = Column(Numeric(8, 4), nullable=False, default=0)
    income_type = Column(String(60), nullable=False, index=True)
    source_rule = Column(String(500))
    system_code = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)


class WithholdingBeneficiaryProfile(Base):
    __tablename__ = "withholding_beneficiary_profiles"
    __table_args__ = (UniqueConstraint("company_id", "party_id", name="uq_wht_beneficiary_company_party"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True)
    country_code = Column(String(3), nullable=False)
    tax_residency_country = Column(String(3), nullable=False)
    foreign_tax_id = Column(String(120))
    non_resident = Column(Boolean, nullable=False, default=True)
    permanent_establishment_in_ksa = Column(Boolean, nullable=False, default=False)
    related_party = Column(Boolean, nullable=False, default=False)
    beneficial_owner_confirmed = Column(Boolean, nullable=False, default=False)
    treaty_country_code = Column(String(3))
    residency_certificate_number = Column(String(150))
    residency_certificate_expiry = Column(Date)
    treaty_relief_approval_reference = Column(String(150))
    treaty_relief_approval_expiry = Column(Date)
    notes = Column(String(1000))
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    party = relationship("Party", lazy="joined")


class WithholdingTaxTransaction(Base):
    __tablename__ = "withholding_tax_transactions"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_wht_transaction_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    payment_date = Column(Date, nullable=False, index=True)
    beneficiary_profile_id = Column(Integer, ForeignKey("withholding_beneficiary_profiles.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("withholding_tax_categories.id"), nullable=False, index=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), index=True)
    debit_account_id = Column(Integer, ForeignKey("accounts.id"))
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    gross_amount = Column(Numeric(18, 2), nullable=False)
    statutory_rate = Column(Numeric(8, 4), nullable=False)
    treaty_rate = Column(Numeric(8, 4))
    applied_rate = Column(Numeric(8, 4), nullable=False)
    withholding_amount = Column(Numeric(18, 2), nullable=False)
    net_cash_amount = Column(Numeric(18, 2), nullable=False)
    gross_up = Column(Boolean, nullable=False, default=False)
    dta_relief_method = Column(String(30), nullable=False, default="STATUTORY")
    dta_reference = Column(String(200))
    source_in_ksa = Column(Boolean, nullable=False, default=True)
    description = Column(String(500), nullable=False)
    reference = Column(String(150))
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), unique=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)

    beneficiary = relationship("WithholdingBeneficiaryProfile", lazy="joined")
    category = relationship("WithholdingTaxCategory", lazy="joined")
    purchase_invoice = relationship("PurchaseInvoice", lazy="joined")
    debit_account = relationship("Account", lazy="joined")
    bank_account = relationship("BankAccount", lazy="joined")
    payment = relationship("Payment")
    journal = relationship("JournalEntry")


class WithholdingTaxReturn(Base):
    __tablename__ = "withholding_tax_returns"
    __table_args__ = (UniqueConstraint("company_id", "period_start", "period_end", name="uq_wht_return_company_period"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    gross_payments = Column(Numeric(18, 2), nullable=False, default=0)
    tax_withheld = Column(Numeric(18, 2), nullable=False, default=0)
    gl_withheld = Column(Numeric(18, 2), nullable=False, default=0)
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

    lines = relationship("WithholdingTaxReturnLine", back_populates="tax_return", cascade="all, delete-orphan", lazy="selectin")
    payment_journal = relationship("JournalEntry")


class WithholdingTaxReturnLine(Base):
    __tablename__ = "withholding_tax_return_lines"
    __table_args__ = (UniqueConstraint("return_id", "category_id", name="uq_wht_return_line_category"),)

    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("withholding_tax_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("withholding_tax_categories.id"), nullable=False, index=True)
    gross_amount = Column(Numeric(18, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(18, 2), nullable=False, default=0)
    transaction_count = Column(Integer, nullable=False, default=0)
    details_json = Column(Text, nullable=False, default="[]")

    tax_return = relationship("WithholdingTaxReturn", back_populates="lines")
    category = relationship("WithholdingTaxCategory", lazy="joined")


__all__ = [
    "WithholdingTaxCategory", "WithholdingBeneficiaryProfile", "WithholdingTaxTransaction",
    "WithholdingTaxReturn", "WithholdingTaxReturnLine",
]
