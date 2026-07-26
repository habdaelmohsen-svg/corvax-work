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

class AssetCategory(Base):
    __tablename__ = "asset_categories"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_asset_category_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    asset_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    accumulated_depreciation_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    depreciation_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    useful_life_months = Column(Integer, nullable=False, default=60)
    residual_percent = Column(Numeric(8, 4), nullable=False, default=0)
    depreciation_convention = Column(String(30), nullable=False, default="FULL_MONTH_BY_15TH")
    active = Column(Boolean, nullable=False, default=True)

class FixedAsset(Base):
    __tablename__ = "fixed_assets"
    __table_args__ = (UniqueConstraint("company_id", "asset_number", name="uq_fixed_asset_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_number = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    category_id = Column(Integer, ForeignKey("asset_categories.id"), nullable=False)
    acquisition_date = Column(Date, nullable=False)
    in_service_date = Column(Date, nullable=False)
    cost = Column(Numeric(18, 2), nullable=False)
    residual_value = Column(Numeric(18, 2), nullable=False, default=0)
    useful_life_months = Column(Integer, nullable=False)
    depreciation_method = Column(String(30), nullable=False, default="STRAIGHT_LINE")
    accumulated_depreciation = Column(Numeric(18, 2), nullable=False, default=0)
    accumulated_impairment = Column(Numeric(18, 2), nullable=False, default=0)
    net_book_value = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    acquisition_journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    custodian_user_id = Column(Integer, ForeignKey("users.id"))
    held_for_sale_date = Column(Date)
    disposal_date = Column(Date)
    disposal_reference = Column(String(120))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    category = relationship("AssetCategory", lazy="joined")
    depreciation_runs = relationship("AssetDepreciation", back_populates="asset", cascade="all, delete-orphan", lazy="selectin")
    lifecycle_transactions = relationship("AssetLifecycleTransaction", back_populates="asset", cascade="all, delete-orphan", lazy="selectin")

class AssetDepreciation(Base):
    __tablename__ = "asset_depreciation"
    __table_args__ = (UniqueConstraint("asset_id", "period_date", name="uq_asset_depreciation_period"),)
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)
    opening_nbv = Column(Numeric(18, 2), nullable=False)
    depreciation = Column(Numeric(18, 2), nullable=False)
    closing_nbv = Column(Numeric(18, 2), nullable=False)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    posted_at = Column(DateTime, nullable=False, default=utc_now)
    asset = relationship("FixedAsset", back_populates="depreciation_runs")


class AssetLifecycleTransaction(Base):
    __tablename__ = "asset_lifecycle_transactions"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_asset_lifecycle_company_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    transaction_type = Column(String(35), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    reason = Column(String(1000), nullable=False)
    reference = Column(String(150))

    from_branch_id = Column(Integer, ForeignKey("branches.id"))
    to_branch_id = Column(Integer, ForeignKey("branches.id"))
    from_cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    to_cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    from_custodian_user_id = Column(Integer, ForeignKey("users.id"))
    to_custodian_user_id = Column(Integer, ForeignKey("users.id"))

    disposal_percent = Column(Numeric(8, 4), nullable=False, default=100)
    proceeds_net = Column(Numeric(18, 2), nullable=False, default=0)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=0)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id"))
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    proceeds_gross = Column(Numeric(18, 2), nullable=False, default=0)
    disposed_cost = Column(Numeric(18, 2), nullable=False, default=0)
    disposed_accumulated_depreciation = Column(Numeric(18, 2), nullable=False, default=0)
    disposed_accumulated_impairment = Column(Numeric(18, 2), nullable=False, default=0)
    disposed_net_book_value = Column(Numeric(18, 2), nullable=False, default=0)
    gain_amount = Column(Numeric(18, 2), nullable=False, default=0)
    loss_amount = Column(Numeric(18, 2), nullable=False, default=0)

    recoverable_amount = Column(Numeric(18, 2))
    fair_value_less_cost_to_sell = Column(Numeric(18, 2))
    impairment_amount = Column(Numeric(18, 2), nullable=False, default=0)
    reversal_amount = Column(Numeric(18, 2), nullable=False, default=0)

    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"))
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)

    asset = relationship("FixedAsset", back_populates="lifecycle_transactions")
    tax_code = relationship("TaxCode", lazy="joined")


# -------------------- Prepaid expenses --------------------

class PrepaidExpense(Base):
    __tablename__ = "prepaid_expenses"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_prepaid_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    supplier_name = Column(String(250))
    payment_date = Column(Date, nullable=False)
    service_start_date = Column(Date, nullable=False)
    service_end_date = Column(Date, nullable=False)
    allocation_method = Column(String(30), nullable=False, default="MONTHLY_STRAIGHT_LINE")
    net_amount = Column(Numeric(18, 2), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    gross_amount = Column(Numeric(18, 2), nullable=False)
    amortized_amount = Column(Numeric(18, 2), nullable=False, default=0)
    remaining_amount = Column(Numeric(18, 2), nullable=False)
    prepaid_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    initial_journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    schedules = relationship("PrepaidExpenseSchedule", back_populates="prepaid", cascade="all, delete-orphan", lazy="selectin")

class PrepaidExpenseSchedule(Base):
    __tablename__ = "prepaid_expense_schedules"
    __table_args__ = (UniqueConstraint("prepaid_expense_id", "period_date", name="uq_prepaid_schedule_period"),)
    id = Column(Integer, primary_key=True)
    prepaid_expense_id = Column(Integer, ForeignKey("prepaid_expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    posted_by = Column(Integer, ForeignKey("users.id"))
    posted_at = Column(DateTime)
    prepaid = relationship("PrepaidExpense", back_populates="schedules")


# -------------------- Accruals and recurring journals --------------------

class AccrualEntry(Base):
    __tablename__ = "accrual_entries"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_accrual_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    accrual_type = Column(String(30), nullable=False, index=True)  # EXPENSE_ACCRUAL / REVENUE_ACCRUAL
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    reference = Column(String(120))
    accrual_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    debit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    credit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    auto_reverse = Column(Boolean, nullable=False, default=True)
    reversal_date = Column(Date, index=True)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    reversal_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    posted_by = Column(Integer, ForeignKey("users.id"))
    reversed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    posted_at = Column(DateTime)
    reversed_at = Column(DateTime)

class RecurringJournalTemplate(Base):
    __tablename__ = "recurring_journal_templates"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_recurring_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    reference_prefix = Column(String(80), nullable=False, default="REC")
    frequency = Column(String(20), nullable=False, default="MONTHLY")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    next_run_date = Column(Date, nullable=False, index=True)
    auto_post = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    lines = relationship("RecurringJournalLine", back_populates="template", cascade="all, delete-orphan", lazy="selectin")
    runs = relationship("RecurringJournalRun", back_populates="template", cascade="all, delete-orphan", lazy="selectin")

class RecurringJournalLine(Base):
    __tablename__ = "recurring_journal_lines"
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("recurring_journal_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    description = Column(String(500))
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    template = relationship("RecurringJournalTemplate", back_populates="lines")
    account = relationship("Account", lazy="joined")

class RecurringJournalRun(Base):
    __tablename__ = "recurring_journal_runs"
    __table_args__ = (UniqueConstraint("template_id", "run_date", name="uq_recurring_template_run_date"),)
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("recurring_journal_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="POSTED")
    journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    executed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    executed_at = Column(DateTime, nullable=False, default=utc_now)
    template = relationship("RecurringJournalTemplate", back_populates="runs")


# -------------------- HR and payroll --------------------

__all__ = ['AssetCategory', 'FixedAsset', 'AssetDepreciation', 'AssetLifecycleTransaction', 'PrepaidExpense', 'PrepaidExpenseSchedule', 'AccrualEntry', 'RecurringJournalTemplate', 'RecurringJournalLine', 'RecurringJournalRun']
