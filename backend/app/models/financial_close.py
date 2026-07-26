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

class BusinessCombination(Base):
    __tablename__ = "business_combinations"
    __table_args__ = (
        UniqueConstraint("group_id", "acquiree_company_id", "acquisition_date", name="uq_business_combination_group_acquiree_date"),
    )
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    acquirer_company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    acquiree_company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    acquisition_date = Column(Date, nullable=False, index=True)
    ownership_percent = Column(Numeric(9, 6), nullable=False)
    nci_measurement_method = Column(String(30), nullable=False, default="PROPORTIONATE_SHARE")
    consideration_cash = Column(Numeric(18, 2), nullable=False, default=0)
    consideration_shares = Column(Numeric(18, 2), nullable=False, default=0)
    contingent_consideration = Column(Numeric(18, 2), nullable=False, default=0)
    previously_held_interest_fv = Column(Numeric(18, 2), nullable=False, default=0)
    nci_fair_value = Column(Numeric(18, 2), nullable=False, default=0)
    identifiable_assets_fv = Column(Numeric(18, 2), nullable=False, default=0)
    identifiable_liabilities_fv = Column(Numeric(18, 2), nullable=False, default=0)
    deferred_tax_net_liability = Column(Numeric(18, 2), nullable=False, default=0)
    identifiable_net_assets_fv = Column(Numeric(18, 2), nullable=False, default=0)
    acquisition_value = Column(Numeric(18, 2), nullable=False, default=0)
    goodwill = Column(Numeric(18, 2), nullable=False, default=0)
    bargain_purchase_gain = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(40), nullable=False, default="DRAFT", index=True)
    rationale_payload = Column(Text, nullable=False, default="{}")
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    worksheet_id = Column(Integer, ForeignKey("consolidation_worksheets.id", use_alter=True, name="fk_business_combination_worksheet"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    items = relationship("PurchasePriceAllocationItem", back_populates="combination", cascade="all, delete-orphan", lazy="selectin")

class PurchasePriceAllocationItem(Base):
    __tablename__ = "purchase_price_allocation_items"
    __table_args__ = (UniqueConstraint("combination_id", "item_code", name="uq_ppa_item_combination_code"),)
    id = Column(Integer, primary_key=True)
    combination_id = Column(Integer, ForeignKey("business_combinations.id", ondelete="CASCADE"), nullable=False, index=True)
    item_code = Column(String(60), nullable=False)
    item_type = Column(String(30), nullable=False)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    book_value = Column(Numeric(18, 2), nullable=False, default=0)
    fair_value = Column(Numeric(18, 2), nullable=False, default=0)
    tax_base = Column(Numeric(18, 2), nullable=False, default=0)
    fair_value_adjustment = Column(Numeric(18, 2), nullable=False, default=0)
    deferred_tax_effect = Column(Numeric(18, 2), nullable=False, default=0)
    useful_life_months = Column(Integer)
    identifiable_intangible = Column(Boolean, nullable=False, default=False)
    evidence_reference = Column(String(500), nullable=False)
    combination = relationship("BusinessCombination", back_populates="items")

class ConsolidationWorksheet(Base):
    __tablename__ = "consolidation_worksheets"
    __table_args__ = (UniqueConstraint("group_id", "period_end", "version", name="uq_consolidation_worksheet_group_period_version"),)
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    worksheet_type = Column(String(40), nullable=False, default="MANUAL_ADJUSTMENT")
    reference = Column(String(120), nullable=False)
    description_ar = Column(String(500), nullable=False)
    description_en = Column(String(500), nullable=False)
    total_debit = Column(Numeric(18, 2), nullable=False, default=0)
    total_credit = Column(Numeric(18, 2), nullable=False, default=0)
    balance_difference = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(40), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    lines = relationship("ConsolidationWorksheetLine", back_populates="worksheet", cascade="all, delete-orphan", lazy="selectin")

class ConsolidationWorksheetLine(Base):
    __tablename__ = "consolidation_worksheet_lines"
    __table_args__ = (UniqueConstraint("worksheet_id", "line_number", name="uq_consolidation_worksheet_line_number"),)
    id = Column(Integer, primary_key=True)
    worksheet_id = Column(Integer, ForeignKey("consolidation_worksheets.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    adjustment_type = Column(String(40), nullable=False)
    account_code = Column(String(60), nullable=False)
    description_ar = Column(String(500), nullable=False)
    description_en = Column(String(500), nullable=False)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    source_reference = Column(String(500), nullable=False)
    worksheet = relationship("ConsolidationWorksheet", back_populates="lines")

class LeadSchedule(Base):
    __tablename__ = "lead_schedules"
    __table_args__ = (UniqueConstraint("company_id", "period_end", "code", "version", name="uq_lead_schedule_company_period_code_version"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    code = Column(String(60), nullable=False)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    account_code_from = Column(String(30), nullable=False)
    account_code_to = Column(String(30), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    ledger_balance = Column(Numeric(18, 2), nullable=False, default=0)
    schedule_total = Column(Numeric(18, 2), nullable=False, default=0)
    difference = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(40), nullable=False, default="DRAFT", index=True)
    conclusion_ar = Column(Text, nullable=False, default="")
    conclusion_en = Column(Text, nullable=False, default="")
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    items = relationship("LeadScheduleItem", back_populates="schedule", cascade="all, delete-orphan", lazy="selectin")
    evidence = relationship("FinancialEvidence", back_populates="schedule", cascade="all, delete-orphan", lazy="selectin")

class LeadScheduleItem(Base):
    __tablename__ = "lead_schedule_items"
    __table_args__ = (UniqueConstraint("schedule_id", "reference", name="uq_lead_schedule_item_reference"),)
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("lead_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    reference = Column(String(120), nullable=False)
    description_ar = Column(String(500), nullable=False)
    description_en = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    reconciling_item = Column(Boolean, nullable=False, default=False)
    ageing_days = Column(Integer)
    owner = Column(String(250))
    due_date = Column(Date)
    status = Column(String(30), nullable=False, default="OPEN")
    schedule = relationship("LeadSchedule", back_populates="items")

class FinancialEvidence(Base):
    __tablename__ = "financial_evidence"
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("lead_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("lead_schedule_items.id", ondelete="SET NULL"), index=True)
    file_name = Column(String(255), nullable=False)
    storage_path = Column(String(700), nullable=False)
    mime_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, default=utc_now)
    schedule = relationship("LeadSchedule", back_populates="evidence")

class LeasePartialTermination(Base):
    __tablename__ = "lease_partial_terminations"
    id = Column(Integer, primary_key=True)
    lease_id = Column(Integer, ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_date = Column(Date, nullable=False, index=True)
    reduction_percent = Column(Numeric(9, 6), nullable=False)
    reason = Column(String(500), nullable=False)
    carrying_liability = Column(Numeric(18, 2), nullable=False, default=0)
    carrying_rou_asset = Column(Numeric(18, 2), nullable=False, default=0)
    liability_reduction = Column(Numeric(18, 2), nullable=False, default=0)
    rou_reduction = Column(Numeric(18, 2), nullable=False, default=0)
    gain_loss = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(40), nullable=False, default="DRAFT", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    lease = relationship("LeaseContract", lazy="joined")
    journal = relationship("JournalEntry")


# -------------------- Final consolidation and finance completion RC9 --------------------

class ConsolidatedTrialBalanceRun(Base):
    __tablename__ = "consolidated_trial_balance_runs"
    __table_args__ = (UniqueConstraint("group_id", "period_end", "version", name="uq_consolidated_tb_group_period_version"),)
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("consolidation_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    member_count = Column(Integer, nullable=False, default=0)
    ledger_debit = Column(Numeric(18, 2), nullable=False, default=0)
    ledger_credit = Column(Numeric(18, 2), nullable=False, default=0)
    adjustment_debit = Column(Numeric(18, 2), nullable=False, default=0)
    adjustment_credit = Column(Numeric(18, 2), nullable=False, default=0)
    consolidated_debit = Column(Numeric(18, 2), nullable=False, default=0)
    consolidated_credit = Column(Numeric(18, 2), nullable=False, default=0)
    balance_difference = Column(Numeric(18, 2), nullable=False, default=0)
    pending_worksheet_count = Column(Integer, nullable=False, default=0)
    report_hash = Column(String(64), nullable=False)
    status = Column(String(40), nullable=False, default="READY_FOR_REVIEW", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    lines = relationship("ConsolidatedTrialBalanceLine", back_populates="run", cascade="all, delete-orphan", lazy="selectin")

class ConsolidatedTrialBalanceLine(Base):
    __tablename__ = "consolidated_trial_balance_lines"
    __table_args__ = (UniqueConstraint("run_id", "account_code", name="uq_consolidated_tb_line_account"),)
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("consolidated_trial_balance_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    account_code = Column(String(60), nullable=False, index=True)
    account_name_ar = Column(String(250), nullable=False)
    account_name_en = Column(String(250), nullable=False)
    account_type = Column(String(30), nullable=False)
    member_debit = Column(Numeric(18, 2), nullable=False, default=0)
    member_credit = Column(Numeric(18, 2), nullable=False, default=0)
    adjustment_debit = Column(Numeric(18, 2), nullable=False, default=0)
    adjustment_credit = Column(Numeric(18, 2), nullable=False, default=0)
    consolidated_debit = Column(Numeric(18, 2), nullable=False, default=0)
    consolidated_credit = Column(Numeric(18, 2), nullable=False, default=0)
    run = relationship("ConsolidatedTrialBalanceRun", back_populates="lines")

class ContingentConsiderationRemeasurement(Base):
    __tablename__ = "contingent_consideration_remeasurements"
    __table_args__ = (UniqueConstraint("combination_id", "measurement_date", "version", name="uq_contingent_consideration_measurement"),)
    id = Column(Integer, primary_key=True)
    combination_id = Column(Integer, ForeignKey("business_combinations.id", ondelete="CASCADE"), nullable=False, index=True)
    measurement_date = Column(Date, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    classification = Column(String(20), nullable=False, default="LIABILITY")
    measurement_type = Column(String(40), nullable=False, default="SUBSEQUENT_REMEASUREMENT")
    opening_fair_value = Column(Numeric(18, 2), nullable=False, default=0)
    closing_fair_value = Column(Numeric(18, 2), nullable=False, default=0)
    fair_value_change = Column(Numeric(18, 2), nullable=False, default=0)
    evidence_reference = Column(String(500), nullable=False)
    rationale = Column(Text, nullable=False)
    status = Column(String(40), nullable=False, default="READY_FOR_REVIEW", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    combination = relationship("BusinessCombination", lazy="joined")
    journal = relationship("JournalEntry")

class ForeignOperationDisposal(Base):
    __tablename__ = "foreign_operation_disposals"
    id = Column(Integer, primary_key=True)
    translation_run_id = Column(Integer, ForeignKey("foreign_operation_translation_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    disposal_date = Column(Date, nullable=False, index=True)
    disposal_type = Column(String(40), nullable=False)
    disposal_percent = Column(Numeric(9, 6), nullable=False)
    cta_before_disposal = Column(Numeric(18, 2), nullable=False, default=0)
    cta_recycled = Column(Numeric(18, 2), nullable=False, default=0)
    remaining_cta = Column(Numeric(18, 2), nullable=False, default=0)
    evidence_reference = Column(String(500), nullable=False)
    rationale = Column(Text, nullable=False)
    status = Column(String(40), nullable=False, default="READY_FOR_REVIEW", index=True)
    worksheet_id = Column(Integer, ForeignKey("consolidation_worksheets.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    translation = relationship("ForeignOperationTranslationRun", lazy="joined")
    worksheet = relationship("ConsolidationWorksheet")


# -------------------- Advanced manufacturing and costing RC10 --------------------

__all__ = ['BusinessCombination', 'PurchasePriceAllocationItem', 'ConsolidationWorksheet', 'ConsolidationWorksheetLine', 'LeadSchedule', 'LeadScheduleItem', 'FinancialEvidence', 'LeasePartialTermination', 'ConsolidatedTrialBalanceRun', 'ConsolidatedTrialBalanceLine', 'ContingentConsiderationRemeasurement', 'ForeignOperationDisposal']
