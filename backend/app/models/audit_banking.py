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

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(100), nullable=False)
    before_json = Column(Text)
    after_json = Column(Text)
    sequence_number = Column(Integer, index=True)
    previous_hash = Column(String(64))
    record_hash = Column(String(64), unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)

class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_bank_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    bank_name_ar = Column(String(200), nullable=False)
    bank_name_en = Column(String(200), nullable=False)
    iban = Column(EncryptedString(1024))
    gl_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    gl_account = relationship("Account", lazy="joined")

class BankStatement(Base):
    __tablename__ = "bank_statements"
    __table_args__ = (UniqueConstraint("bank_account_id", "statement_date", name="uq_bank_statement_date"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    statement_date = Column(Date, nullable=False, index=True)
    opening_balance = Column(Numeric(18, 2), nullable=False, default=0)
    closing_balance = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    matched_by = Column(Integer, ForeignKey("users.id"))
    matched_at = Column(DateTime)
    reconciled_by = Column(Integer, ForeignKey("users.id"))
    reconciled_at = Column(DateTime)
    bank_account = relationship("BankAccount", lazy="joined")
    lines = relationship("BankStatementLine", back_populates="statement", cascade="all, delete-orphan", lazy="selectin")

class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    id = Column(Integer, primary_key=True)
    statement_id = Column(Integer, ForeignKey("bank_statements.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    reference = Column(String(120))
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    direction = Column(String(10), nullable=False)  # DEBIT / CREDIT from bank perspective
    status = Column(String(20), nullable=False, default="UNMATCHED", index=True)
    matched_journal_line_id = Column(Integer, ForeignKey("journal_lines.id"))
    statement = relationship("BankStatement", back_populates="lines")
    matched_journal_line = relationship("JournalLine", lazy="joined")


# -------------------- Budget control --------------------

class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("company_id", "name", "fiscal_year_id", name="uq_budget_company_name_year"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = Column(Integer, ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    lines = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan", lazy="selectin")

class BudgetLine(Base):
    __tablename__ = "budget_lines"
    __table_args__ = (UniqueConstraint("budget_id", "account_id", "cost_center_id", "period_number", name="uq_budget_line_dimension"),)
    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    period_number = Column(Integer, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    committed_amount = Column(Numeric(18, 2), nullable=False, default=0)
    reserved_amount = Column(Numeric(18, 2), nullable=False, default=0)
    budget = relationship("Budget", back_populates="lines")
    account = relationship("Account", lazy="joined")
    cost_center = relationship("CostCenter", lazy="joined")


# -------------------- Inventory and procurement --------------------

__all__ = ['AuditLog', 'BankAccount', 'BankStatement', 'BankStatementLine', 'Budget', 'BudgetLine']
