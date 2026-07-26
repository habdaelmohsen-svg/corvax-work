from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base
from app.models.types import EncryptedDecimal, EncryptedString


class PayrollPolicy(Base):
    __tablename__ = "payroll_policies"
    __table_args__ = (UniqueConstraint("company_id", name="uq_payroll_policy_company"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    salary_day_basis = Column(Numeric(8, 2), nullable=False, default=30)
    standard_daily_hours = Column(Numeric(8, 2), nullable=False, default=8)
    gosi_basis = Column(String(30), nullable=False, default="BASIC_HOUSING")
    late_deduction_enabled = Column(Boolean, nullable=False, default=True)
    absence_deduction_enabled = Column(Boolean, nullable=False, default=True)
    overtime_basis = Column(String(30), nullable=False, default="BASIC")
    attendance_completeness_threshold = Column(Numeric(8, 2), nullable=False, default=95)
    require_three_user_approval = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)


class EmployeeContract(Base):
    __tablename__ = "employee_contracts"
    __table_args__ = (
        UniqueConstraint("company_id", "contract_number", name="uq_employee_contract_number"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_number = Column(String(60), nullable=False, index=True)
    contract_type = Column(String(30), nullable=False, default="UNLIMITED")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    probation_end_date = Column(Date)
    basic_salary = Column(EncryptedDecimal(), nullable=False)
    housing_allowance = Column(EncryptedDecimal(), nullable=False, default=0)
    other_allowance = Column(EncryptedDecimal(), nullable=False, default=0)
    working_hours_per_week = Column(Numeric(8, 2), nullable=False, default=48)
    notice_days = Column(Integer, nullable=False, default=60)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    employee = relationship("Employee", lazy="joined")


class OvertimeRequest(Base):
    __tablename__ = "overtime_requests"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_overtime_request_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    requested_minutes = Column(Integer, nullable=False)
    approved_minutes = Column(Integer, nullable=False, default=0)
    rate_multiplier = Column(Numeric(8, 4), nullable=False, default=1.5)
    reason = Column(String(500), nullable=False)
    status = Column(String(25), nullable=False, default="SUBMITTED", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    payroll_run_id = Column(Integer, ForeignKey("payroll_runs.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    employee = relationship("Employee", lazy="joined")


class PayrollAdjustment(Base):
    __tablename__ = "payroll_adjustments"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_payroll_adjustment_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    period_year = Column(Integer, nullable=False, index=True)
    period_month = Column(Integer, nullable=False, index=True)
    adjustment_type = Column(String(30), nullable=False)
    amount = Column(EncryptedDecimal(), nullable=False)
    earning = Column(Boolean, nullable=False, default=False)
    gosi_applicable = Column(Boolean, nullable=False, default=False)
    reason = Column(String(500), nullable=False)
    status = Column(String(25), nullable=False, default="SUBMITTED", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    applied_payroll_run_id = Column(Integer, ForeignKey("payroll_runs.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    employee = relationship("Employee", lazy="joined")


class WpsBatch(Base):
    __tablename__ = "wps_batches"
    __table_args__ = (
        UniqueConstraint("payroll_run_id", name="uq_wps_batch_payroll_run"),
        UniqueConstraint("company_id", "batch_number", name="uq_wps_batch_number"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    payroll_run_id = Column(Integer, ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_number = Column(String(60), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    execution_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="GENERATED", index=True)
    total_amount = Column(EncryptedDecimal(), nullable=False)
    line_count = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False)
    response_reference = Column(String(150))
    response_message = Column(Text)
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    generated_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    accepted_at = Column(DateTime)
    lines = relationship("WpsBatchLine", back_populates="batch", cascade="all, delete-orphan", lazy="selectin")


class WpsBatchLine(Base):
    __tablename__ = "wps_batch_lines"
    __table_args__ = (UniqueConstraint("wps_batch_id", "employee_id", name="uq_wps_line_employee"),)
    id = Column(Integer, primary_key=True)
    wps_batch_id = Column(Integer, ForeignKey("wps_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    employee_iban = Column(EncryptedString(1024), nullable=False)
    bank_code = Column(String(20), nullable=False)
    amount = Column(EncryptedDecimal(), nullable=False)
    status = Column(String(30), nullable=False, default="PENDING", index=True)
    rejection_code = Column(String(50))
    rejection_reason = Column(String(500))
    batch = relationship("WpsBatch", back_populates="lines")
    employee = relationship("Employee", lazy="joined")


class EmployeeBenefitAssumption(Base):
    __tablename__ = "employee_benefit_assumptions"
    __table_args__ = (UniqueConstraint("company_id", "valuation_date", name="uq_benefit_assumption_date"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    valuation_date = Column(Date, nullable=False, index=True)
    discount_rate = Column(Numeric(10, 6), nullable=False)
    salary_growth_rate = Column(Numeric(10, 6), nullable=False)
    annual_turnover_rate = Column(Numeric(10, 6), nullable=False)
    retirement_age = Column(Integer, nullable=False, default=60)
    mortality_survival_factor = Column(Numeric(10, 6), nullable=False, default=0.995)
    method = Column(String(40), nullable=False, default="PROJECTED_UNIT_CREDIT_SUPPORT")
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)


class EmployeeBenefitValuation(Base):
    __tablename__ = "employee_benefit_valuations"
    __table_args__ = (UniqueConstraint("company_id", "valuation_date", "version", name="uq_benefit_valuation_version"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    assumption_id = Column(Integer, ForeignKey("employee_benefit_assumptions.id"), nullable=False)
    valuation_date = Column(Date, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    total_dbo = Column(EncryptedDecimal(), nullable=False, default=0)
    current_service_cost = Column(EncryptedDecimal(), nullable=False, default=0)
    interest_cost = Column(EncryptedDecimal(), nullable=False, default=0)
    actuarial_gain_loss = Column(EncryptedDecimal(), nullable=False, default=0)
    employee_count = Column(Integer, nullable=False, default=0)
    analysis_hash = Column(String(64), nullable=False)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    lines = relationship("EmployeeBenefitValuationLine", back_populates="valuation", cascade="all, delete-orphan", lazy="selectin")


class EmployeeBenefitValuationLine(Base):
    __tablename__ = "employee_benefit_valuation_lines"
    __table_args__ = (UniqueConstraint("valuation_id", "employee_id", name="uq_benefit_valuation_employee"),)
    id = Column(Integer, primary_key=True)
    valuation_id = Column(Integer, ForeignKey("employee_benefit_valuations.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    current_wage = Column(EncryptedDecimal(), nullable=False)
    projected_final_wage = Column(EncryptedDecimal(), nullable=False)
    service_years = Column(Numeric(12, 6), nullable=False)
    future_service_years = Column(Numeric(12, 6), nullable=False)
    survival_probability = Column(Numeric(12, 8), nullable=False)
    present_value_obligation = Column(EncryptedDecimal(), nullable=False)
    valuation = relationship("EmployeeBenefitValuation", back_populates="lines")
    employee = relationship("Employee", lazy="joined")


__all__ = [
    "PayrollPolicy", "EmployeeContract", "OvertimeRequest", "PayrollAdjustment",
    "WpsBatch", "WpsBatchLine", "EmployeeBenefitAssumption",
    "EmployeeBenefitValuation", "EmployeeBenefitValuationLine",
]
