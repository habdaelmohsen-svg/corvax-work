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

class BackupRecord(Base):
    __tablename__ = "backup_records"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    backup_type = Column(String(30), nullable=False, default="FULL")
    storage_path = Column(String(500), nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="COMPLETED", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    verified_at = Column(DateTime)

class PeriodCloseRun(Base):
    __tablename__ = "period_close_runs"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_period_id", name="uq_close_company_period"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_period_id = Column(Integer, ForeignKey("fiscal_periods.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    closed_at = Column(DateTime)

class PeriodCloseCheck(Base):
    __tablename__ = "period_close_checks"
    __table_args__ = (UniqueConstraint("close_run_id", "code", name="uq_close_check_code"),)
    id = Column(Integer, primary_key=True)
    close_run_id = Column(Integer, ForeignKey("period_close_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    status = Column(String(20), nullable=False)
    blocking = Column(Boolean, nullable=False, default=True)
    details = Column(Text)
    checked_at = Column(DateTime, nullable=False, default=utc_now)

class EInvoice(Base):
    __tablename__ = "e_invoices"
    __table_args__ = (UniqueConstraint("company_id", "uuid", name="uq_einvoice_company_uuid"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(30), nullable=False, index=True)
    source_id = Column(Integer, nullable=False, index=True)
    uuid = Column(String(64), nullable=False)
    invoice_counter = Column(Integer, nullable=False)
    issue_datetime = Column(DateTime, nullable=False)
    invoice_type_code = Column(String(20), nullable=False)
    xml_content = Column(Text, nullable=False)
    invoice_hash = Column(String(128), nullable=False)
    previous_invoice_hash = Column(String(128), nullable=False)
    qr_tlv_base64 = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="GENERATED", index=True)
    validation_errors = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class VatReturnSnapshot(Base):
    __tablename__ = "vat_return_snapshots"
    __table_args__ = (UniqueConstraint("company_id", "period_start", "period_end", name="uq_vat_return_period"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    standard_rated_sales = Column(Numeric(18, 2), nullable=False, default=0)
    output_vat = Column(Numeric(18, 2), nullable=False, default=0)
    standard_rated_purchases = Column(Numeric(18, 2), nullable=False, default=0)
    input_vat = Column(Numeric(18, 2), nullable=False, default=0)
    net_vat_payable = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="DRAFT")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    submitted_at = Column(DateTime)
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    gl_output_vat = Column(Numeric(18, 2), nullable=False, default=0)
    gl_input_vat = Column(Numeric(18, 2), nullable=False, default=0)
    output_reconciliation_difference = Column(Numeric(18, 2), nullable=False, default=0)
    input_reconciliation_difference = Column(Numeric(18, 2), nullable=False, default=0)
    classification_complete = Column(Boolean, nullable=False, default=False)
    generated_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    lines = relationship("VatReturnLine", back_populates="vat_return", cascade="all, delete-orphan", lazy="selectin")

class Currency(Base):
    __tablename__ = "currencies"
    code = Column(String(3), primary_key=True)
    name_ar = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)
    decimal_places = Column(Integer, nullable=False, default=2)
    active = Column(Boolean, nullable=False, default=True)

class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("company_id", "currency_code", "rate_date", name="uq_fx_rate_company_currency_date"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    currency_code = Column(String(3), ForeignKey("currencies.code"), nullable=False, index=True)
    rate_date = Column(Date, nullable=False, index=True)
    rate = Column(Numeric(18, 8), nullable=False)
    source = Column(String(100), nullable=False, default="MANUAL")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class ForeignCurrencyBalance(Base):
    __tablename__ = "foreign_currency_balances"
    __table_args__ = (UniqueConstraint("company_id", "account_id", "currency_code", name="uq_fx_balance_account_currency"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    currency_code = Column(String(3), ForeignKey("currencies.code"), nullable=False)
    foreign_amount = Column(Numeric(18, 4), nullable=False, default=0)
    carrying_amount = Column(Numeric(18, 2), nullable=False, default=0)
    last_rate = Column(Numeric(18, 8), nullable=False, default=1)
    updated_at = Column(DateTime, nullable=False, default=utc_now)
    account = relationship("Account", lazy="joined")

class FxRevaluationRun(Base):
    __tablename__ = "fx_revaluation_runs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    revaluation_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="DRAFT")
    total_gain = Column(Numeric(18, 2), nullable=False, default=0)
    total_loss = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class CreditRiskPortfolio(Base):
    __tablename__ = "credit_risk_portfolios"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_credit_portfolio_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    method = Column(String(30), nullable=False, default="SIMPLIFIED")  # SIMPLIFIED / GENERAL
    business_model = Column(String(30), nullable=False, default="HOLD_TO_COLLECT")
    sicr_days_past_due = Column(Integer, nullable=False, default=30)
    default_days_past_due = Column(Integer, nullable=False, default=90)
    pd_sicr_multiplier = Column(Numeric(10, 4), nullable=False, default=2)
    forward_looking_overlay = Column(Numeric(10, 6), nullable=False, default=1)
    model_version = Column(String(40), nullable=False, default="1.0")
    active = Column(Boolean, nullable=False, default=True)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

class CreditRiskBucket(Base):
    __tablename__ = "credit_risk_buckets"
    __table_args__ = (UniqueConstraint("portfolio_id", "min_days", "max_days", name="uq_credit_bucket_range"),)
    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("credit_risk_portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    min_days = Column(Integer, nullable=False)
    max_days = Column(Integer)
    loss_rate = Column(Numeric(10, 6), nullable=False)
    forward_factor = Column(Numeric(10, 6), nullable=False, default=1)

class CreditExposure(Base):
    __tablename__ = "credit_exposures"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    portfolio_id = Column(Integer, ForeignKey("credit_risk_portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    reference = Column(String(80), nullable=False, index=True)
    customer_name = Column(String(250), nullable=False)
    instrument_type = Column(String(30), nullable=False, default="TRADE_RECEIVABLE")
    origination_date = Column(Date)
    due_date = Column(Date, nullable=False)
    maturity_date = Column(Date)
    gross_amount = Column(Numeric(18, 2), nullable=False)
    carrying_amount = Column(Numeric(18, 2), nullable=False)
    undrawn_commitment = Column(Numeric(18, 2), nullable=False, default=0)
    credit_conversion_factor = Column(Numeric(10, 6), nullable=False, default=1)
    effective_interest_rate = Column(Numeric(10, 6), nullable=False, default=0)
    initial_12m_pd = Column(Numeric(10, 6), nullable=False, default=0)
    current_12m_pd = Column(Numeric(10, 6), nullable=False, default=0)
    lifetime_pd = Column(Numeric(10, 6), nullable=False, default=0)
    lgd = Column(Numeric(10, 6), nullable=False, default=0)
    collateral_value = Column(Numeric(18, 2), nullable=False, default=0)
    credit_rating = Column(String(30))
    business_model = Column(String(30), nullable=False, default="HOLD_TO_COLLECT")
    sppi_passed = Column(Boolean, nullable=False, default=True)
    significant_increase_in_credit_risk = Column(Boolean, nullable=False, default=False)
    default_flag = Column(Boolean, nullable=False, default=False)
    forbearance_flag = Column(Boolean, nullable=False, default=False)
    stage_override = Column(Integer)
    stage_reason = Column(String(500))
    status = Column(String(25), nullable=False, default="OPEN")
    created_at = Column(DateTime, nullable=False, default=utc_now)

class EclRun(Base):
    __tablename__ = "ecl_runs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    portfolio_id = Column(Integer, ForeignKey("credit_risk_portfolios.id", ondelete="CASCADE"), nullable=False)
    as_of_date = Column(Date, nullable=False, index=True)
    approach = Column(String(30), nullable=False, default="SIMPLIFIED")
    model_version = Column(String(40), nullable=False, default="1.0")
    total_exposure = Column(Numeric(18, 2), nullable=False, default=0)
    expected_credit_loss = Column(Numeric(18, 2), nullable=False, default=0)
    stage_1_ecl = Column(Numeric(18, 2), nullable=False, default=0)
    stage_2_ecl = Column(Numeric(18, 2), nullable=False, default=0)
    stage_3_ecl = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    analysis_hash = Column(String(64), nullable=False, default="")
    expense_account_code = Column(String(30))
    allowance_account_code = Column(String(30))
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

class EclRunLine(Base):
    __tablename__ = "ecl_run_lines"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("ecl_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    exposure_id = Column(Integer, ForeignKey("credit_exposures.id", ondelete="CASCADE"), nullable=False)
    stage = Column(Integer, nullable=False, default=2)
    stage_reason = Column(String(500))
    days_past_due = Column(Integer, nullable=False)
    pd_rate = Column(Numeric(10, 6), nullable=False, default=0)
    lgd_rate = Column(Numeric(10, 6), nullable=False, default=0)
    ead_amount = Column(Numeric(18, 2), nullable=False, default=0)
    discount_factor = Column(Numeric(18, 10), nullable=False, default=1)
    loss_rate = Column(Numeric(10, 6), nullable=False)
    forward_factor = Column(Numeric(10, 6), nullable=False)
    base_ecl_amount = Column(Numeric(18, 2), nullable=False, default=0)
    ecl_amount = Column(Numeric(18, 2), nullable=False)

class MaintenanceAsset(Base):
    __tablename__ = "maintenance_assets"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_maintenance_asset_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    production_line = Column(String(120))
    meter_hours = Column(Numeric(18, 2), nullable=False, default=0)
    criticality = Column(String(20), nullable=False, default="MEDIUM")
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_at = Column(DateTime, nullable=False, default=utc_now)

class MaintenanceWorkOrder(Base):
    __tablename__ = "maintenance_work_orders"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_maintenance_wo_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("maintenance_assets.id", ondelete="CASCADE"), nullable=False)
    work_type = Column(String(30), nullable=False)
    priority = Column(String(20), nullable=False, default="MEDIUM")
    description = Column(String(500), nullable=False)
    status = Column(String(25), nullable=False, default="OPEN")
    requested_at = Column(DateTime, nullable=False, default=utc_now)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    downtime_minutes = Column(Integer, nullable=False, default=0)
    labor_cost = Column(Numeric(18, 2), nullable=False, default=0)
    parts_cost = Column(Numeric(18, 2), nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))

class MaintenancePlan(Base):
    __tablename__ = "maintenance_plans"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_maintenance_plan_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("maintenance_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    description = Column(String(500), nullable=False)
    interval_days = Column(Integer)
    meter_interval = Column(Numeric(18, 2))
    next_due_date = Column(Date)
    next_due_meter = Column(Numeric(18, 2))
    priority = Column(String(20), nullable=False, default="MEDIUM")
    active = Column(Boolean, nullable=False, default=True)
    last_generated_at = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class MaintenanceSparePart(Base):
    __tablename__ = "maintenance_spare_parts"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_maintenance_spare_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    unit = Column(String(30), nullable=False, default="EA")
    quantity_on_hand = Column(Numeric(18, 4), nullable=False, default=0)
    reorder_level = Column(Numeric(18, 4), nullable=False, default=0)
    average_cost = Column(Numeric(18, 4), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class MaintenanceWorkOrderPart(Base):
    __tablename__ = "maintenance_work_order_parts"
    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    spare_part_id = Column(Integer, ForeignKey("maintenance_spare_parts.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_cost = Column(Numeric(18, 4), nullable=False)
    total_cost = Column(Numeric(18, 2), nullable=False)
    issued_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    issued_at = Column(DateTime, nullable=False, default=utc_now)

class CalibrationRecord(Base):
    __tablename__ = "calibration_records"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("maintenance_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    instrument_code = Column(String(80), nullable=False)
    calibration_date = Column(Date, nullable=False)
    next_due_date = Column(Date, nullable=False, index=True)
    result = Column(String(20), nullable=False)
    certificate_reference = Column(String(120))
    notes = Column(String(500))
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

# -------------------- Intercompany reconciliation and advanced consolidation v0.28 --------------------

__all__ = ['BackupRecord', 'PeriodCloseRun', 'PeriodCloseCheck', 'EInvoice', 'VatReturnSnapshot', 'Currency', 'ExchangeRate', 'ForeignCurrencyBalance', 'FxRevaluationRun', 'CreditRiskPortfolio', 'CreditRiskBucket', 'CreditExposure', 'EclRun', 'EclRunLine', 'MaintenanceAsset', 'MaintenanceWorkOrder', 'MaintenancePlan', 'MaintenanceSparePart', 'MaintenanceWorkOrderPart', 'CalibrationRecord']
