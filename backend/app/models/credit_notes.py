from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class CreditNote(Base):
    __tablename__ = "credit_notes"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_credit_note_company_number"),
        CheckConstraint("note_type in ('SALES','PURCHASE')", name="ck_credit_note_type"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    note_date = Column(Date, nullable=False, index=True)
    note_type = Column(String(12), nullable=False, index=True)
    original_sales_invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), index=True)
    original_purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), index=True)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    reason_code = Column(String(30), nullable=False, index=True)
    reason = Column(String(500), nullable=False)
    external_reference = Column(String(100))
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    subtotal = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False, default=0)
    unapplied_credit = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    zatca_uuid = Column(String(80), nullable=False, unique=True, index=True)
    original_document_number = Column(String(100), nullable=False)
    original_document_date = Column(Date, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)

    party = relationship("Party", lazy="joined")
    original_sales_invoice = relationship("SalesInvoice", lazy="joined")
    original_purchase_invoice = relationship("PurchaseInvoice", lazy="joined")
    journal = relationship("JournalEntry")
    lines = relationship("CreditNoteLine", back_populates="credit_note", cascade="all, delete-orphan", lazy="selectin")
    applications = relationship("CreditNoteApplication", back_populates="credit_note", cascade="all, delete-orphan", lazy="selectin")


class CreditNoteLine(Base):
    __tablename__ = "credit_note_lines"
    id = Column(Integer, primary_key=True)
    credit_note_id = Column(Integer, ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    original_sales_invoice_line_id = Column(Integer, ForeignKey("sales_invoice_lines.id"), index=True)
    original_purchase_invoice_line_id = Column(Integer, ForeignKey("purchase_invoice_lines.id"), index=True)
    description = Column(String(500), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id"), nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    subtotal = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    total = Column(Numeric(18, 2), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), index=True)
    inventory_disposition = Column(String(25), nullable=False, default="NONE")
    unit_cost = Column(Numeric(18, 6), nullable=False, default=0)
    inventory_value = Column(Numeric(18, 2), nullable=False, default=0)

    credit_note = relationship("CreditNote", back_populates="lines")
    account = relationship("Account", lazy="joined")
    tax_code = relationship("TaxCode", lazy="joined")
    item = relationship("Item", lazy="joined")
    warehouse = relationship("Warehouse", lazy="joined")


class CreditNoteApplication(Base):
    __tablename__ = "credit_note_applications"
    __table_args__ = (UniqueConstraint("credit_note_id", "open_item_id", name="uq_credit_note_open_item"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    credit_note_id = Column(Integer, ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    open_item_id = Column(Integer, ForeignKey("financial_open_items.id", ondelete="CASCADE"), nullable=False, index=True)
    application_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    credit_note = relationship("CreditNote", back_populates="applications")
    open_item = relationship("FinancialOpenItem", lazy="joined")


class PartyCreditBalance(Base):
    __tablename__ = "party_credit_balances"
    __table_args__ = (CheckConstraint("ledger_type in ('AR','AP')", name="ck_party_credit_ledger_type"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    ledger_type = Column(String(2), nullable=False, index=True)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    source_type = Column(String(30), nullable=False, default="CREDIT_NOTE")
    source_id = Column(Integer, ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    document_number = Column(String(100), nullable=False, index=True)
    balance_date = Column(Date, nullable=False, index=True)
    original_amount = Column(Numeric(18, 2), nullable=False)
    available_amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    party = relationship("Party", lazy="joined")
    credit_note = relationship("CreditNote", lazy="joined")


__all__ = ["CreditNote", "CreditNoteLine", "CreditNoteApplication", "PartyCreditBalance"]
