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

class ConsolidationGroup(Base):
    __tablename__ = "consolidation_groups"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    reporting_currency = Column(String(3), nullable=False, default="SAR")
    active = Column(Boolean, nullable=False, default=True)

class ConsolidationMember(Base):
    __tablename__ = "consolidation_members"
    __table_args__ = (UniqueConstraint("group_id", "company_id", name="uq_consolidation_group_company"),)
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    ownership_percent = Column(Numeric(8, 4), nullable=False, default=100)
    effective_date = Column(Date, nullable=False)

class ConsolidationRun(Base):
    __tablename__ = "consolidation_runs"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="COMPLETED")
    total_debit = Column(Numeric(18, 2), nullable=False, default=0)
    total_credit = Column(Numeric(18, 2), nullable=False, default=0)
    elimination_amount = Column(Numeric(18, 2), nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class ConsolidationLine(Base):
    __tablename__ = "consolidation_lines"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("consolidation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    account_code = Column(String(30), nullable=False, index=True)
    account_name_ar = Column(String(250), nullable=False)
    account_name_en = Column(String(250), nullable=False)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    is_elimination = Column(Boolean, nullable=False, default=False)

class IntercompanyRecord(Base):
    __tablename__ = "intercompany_records"
    __table_args__ = (
        UniqueConstraint("company_id", "document_number", "direction", name="uq_ic_record_company_doc_direction"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    counterparty_company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    document_number = Column(String(80), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    direction = Column(String(20), nullable=False)  # RECEIVABLE / PAYABLE / REVENUE / EXPENSE
    account_code = Column(String(30), nullable=False)
    currency_code = Column(String(3), nullable=False, default="SAR")
    foreign_amount = Column(Numeric(18, 4), nullable=False, default=0)
    local_amount = Column(Numeric(18, 2), nullable=False)
    description = Column(String(500))
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class IntercompanyMatch(Base):
    __tablename__ = "intercompany_matches"
    __table_args__ = (
        UniqueConstraint("record_a_id", "record_b_id", name="uq_ic_match_pair"),
    )
    id = Column(Integer, primary_key=True)
    record_a_id = Column(Integer, ForeignKey("intercompany_records.id", ondelete="CASCADE"), nullable=False, index=True)
    record_b_id = Column(Integer, ForeignKey("intercompany_records.id", ondelete="CASCADE"), nullable=False, index=True)
    matched_amount = Column(Numeric(18, 2), nullable=False)
    variance_amount = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="MATCHED", index=True)
    notes = Column(String(500))
    matched_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    matched_at = Column(DateTime, nullable=False, default=utc_now)

class ConsolidationAdjustment(Base):
    __tablename__ = "consolidation_adjustments"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("consolidation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    adjustment_type = Column(String(30), nullable=False, default="INTERCOMPANY")
    reference = Column(String(120), nullable=False)
    debit_account_code = Column(String(30), nullable=False)
    credit_account_code = Column(String(30), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    source_match_id = Column(Integer, ForeignKey("intercompany_matches.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

# -------------------- Year-end close and retained earnings v0.32 --------------------

class YearEndCloseRun(Base):
    __tablename__ = "year_end_close_runs"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year_id", name="uq_year_end_company_year"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = Column(Integer, ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    retained_earnings_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    current_year_result = Column(Numeric(18, 2), nullable=False, default=0)
    closing_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    closed_at = Column(DateTime)

class YearEndCloseCheck(Base):
    __tablename__ = "year_end_close_checks"
    __table_args__ = (UniqueConstraint("year_end_run_id", "code", name="uq_year_end_check_code"),)
    id = Column(Integer, primary_key=True)
    year_end_run_id = Column(Integer, ForeignKey("year_end_close_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    status = Column(String(20), nullable=False)
    blocking = Column(Boolean, nullable=False, default=True)
    details = Column(Text)
    checked_at = Column(DateTime, nullable=False, default=utc_now)

# -------------------- Governance, assurance, controlled documents and ITSM v1.0 --------------------

__all__ = ['ConsolidationGroup', 'ConsolidationMember', 'ConsolidationRun', 'ConsolidationLine', 'IntercompanyRecord', 'IntercompanyMatch', 'ConsolidationAdjustment', 'YearEndCloseRun', 'YearEndCloseCheck']
