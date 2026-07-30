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

class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_account_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    account_type = Column(String(30), nullable=False, index=True)
    statement_group = Column(String(50), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts.id"))
    level = Column(Integer, nullable=False, default=1)
    is_postable = Column(Boolean, nullable=False, default=True)
    is_cash = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    company = relationship("Company", back_populates="accounts")

class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_journal_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    reference = Column(String(100), nullable=False)
    description = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    cash_flow_activity = Column(String(20))
    cash_flow_kind = Column(String(60))
    entry_origin = Column(String(20), nullable=False, default="SYSTEM", index=True)
    total_debit = Column(Numeric(18, 2), nullable=False, default=0)
    total_credit = Column(Numeric(18, 2), nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    posted_by = Column(Integer, ForeignKey("users.id"))
    reversed_entry_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)
    posted_at = Column(DateTime)
    lines = relationship("JournalLine", back_populates="journal", cascade="all, delete-orphan", lazy="selectin")

class JournalSequence(Base):
    __tablename__ = "journal_sequences"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", name="uq_journal_sequence_company_year"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=False, index=True)
    last_number = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

class JournalLine(Base):
    __tablename__ = "journal_lines"
    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    description = Column(String(500))
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    journal = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", lazy="joined")
    cost_center = relationship("CostCenter", lazy="joined")
    branch = relationship("Branch", lazy="joined")

class Party(Base):
    __tablename__ = "parties"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_party_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    party_type = Column(String(20), nullable=False, index=True)
    vat_number = Column(EncryptedString(512))
    credit_limit = Column(Numeric(18, 2), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)

class SalesInvoice(Base):
    __tablename__ = "sales_invoices"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_sales_invoice_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    invoice_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False)
    customer_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    reference = Column(String(100))
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    subtotal = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    customer = relationship("Party", lazy="joined")
    journal = relationship("JournalEntry")
    lines = relationship("SalesInvoiceLine", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")

class SalesInvoiceLine(Base):
    __tablename__ = "sales_invoice_lines"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    revenue_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False, default=1)
    unit_price = Column(Numeric(18, 4), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id"), index=True)
    subtotal = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    total = Column(Numeric(18, 2), nullable=False)
    invoice = relationship("SalesInvoice", back_populates="lines")
    revenue_account = relationship("Account", lazy="joined")
    tax_code = relationship("TaxCode", lazy="joined")

class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoices"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_purchase_invoice_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    invoice_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False)
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    supplier_invoice_number = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    subtotal = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    supplier = relationship("Party", lazy="joined")
    journal = relationship("JournalEntry")
    lines = relationship("PurchaseInvoiceLine", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")

class PurchaseInvoiceLine(Base):
    __tablename__ = "purchase_invoice_lines"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("purchase_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False, default=1)
    unit_price = Column(Numeric(18, 4), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id"), index=True)
    subtotal = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    total = Column(Numeric(18, 2), nullable=False)
    invoice = relationship("PurchaseInvoice", back_populates="lines")
    expense_account = relationship("Account", lazy="joined")
    tax_code = relationship("TaxCode", lazy="joined")

class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_receipt_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    receipt_date = Column(Date, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    reference = Column(String(100), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    customer = relationship("Party", lazy="joined")
    bank_account = relationship("BankAccount", lazy="joined")
    journal = relationship("JournalEntry")

class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_payment_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    payment_date = Column(Date, nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)  # gross AP settlement amount
    net_cash_amount = Column(Numeric(18, 2), nullable=False, default=0)
    withholding_tax_amount = Column(Numeric(18, 2), nullable=False, default=0)
    reference = Column(String(100), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    supplier = relationship("Party", lazy="joined")
    bank_account = relationship("BankAccount", lazy="joined")
    journal = relationship("JournalEntry")

# -------------------- Banking and reconciliation --------------------

__all__ = ['Account', 'JournalEntry', 'JournalSequence', 'JournalLine', 'Party', 'SalesInvoice', 'SalesInvoiceLine', 'PurchaseInvoice', 'PurchaseInvoiceLine', 'Receipt', 'Payment']
