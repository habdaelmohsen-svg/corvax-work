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

class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("company_id", "employee_number", name="uq_employee_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_number = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    nationality_group = Column(String(20), nullable=False, default="SAUDI")
    national_id = Column(EncryptedString(1024))
    birth_date = Column(Date)
    salary_bank_code = Column(String(20))
    job_title_ar = Column(String(200))
    job_title_en = Column(String(200))
    contract_type = Column(String(30), nullable=False, default="UNLIMITED")
    contract_end_date = Column(Date)
    probation_end_date = Column(Date)
    work_email = Column(String(320))
    mobile = Column(String(30))
    iban = Column(EncryptedString(1024))
    annual_leave_days = Column(Numeric(8, 2), nullable=False, default=30)
    hire_date = Column(Date, nullable=False)
    basic_salary = Column(EncryptedDecimal(), nullable=False)
    housing_allowance = Column(EncryptedDecimal(), nullable=False, default=0)
    other_allowance = Column(EncryptedDecimal(), nullable=False, default=0)
    employee_gosi_rate = Column(Numeric(8, 4), nullable=False, default=0)
    employer_gosi_rate = Column(Numeric(8, 4), nullable=False, default=0)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    active = Column(Boolean, nullable=False, default=True)
    employment_status = Column(String(20), nullable=False, default="ACTIVE")
    termination_date = Column(Date)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("company_id", "period_year", "period_month", name="uq_payroll_company_period"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)
    payment_date = Column(Date, nullable=False)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    total_gross = Column(Numeric(18, 2), nullable=False, default=0)
    total_employee_gosi = Column(Numeric(18, 2), nullable=False, default=0)
    total_employer_gosi = Column(Numeric(18, 2), nullable=False, default=0)
    total_deductions = Column(Numeric(18, 2), nullable=False, default=0)
    total_net = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    payment_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    posted_by = Column(Integer, ForeignKey("users.id"))
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    analysis_hash = Column(String(64))
    attendance_completeness_percent = Column(Numeric(8, 2), nullable=False, default=0)
    review_override_reason = Column(String(500))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    posted_at = Column(DateTime)
    lines = relationship("PayrollLine", back_populates="run", cascade="all, delete-orphan", lazy="selectin")

class PayrollLine(Base):
    __tablename__ = "payroll_lines"
    __table_args__ = (UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_line_employee"),)
    id = Column(Integer, primary_key=True)
    payroll_run_id = Column(Integer, ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    basic_salary = Column(EncryptedDecimal(), nullable=False)
    housing_allowance = Column(EncryptedDecimal(), nullable=False)
    other_allowance = Column(EncryptedDecimal(), nullable=False)
    gross_salary = Column(EncryptedDecimal(), nullable=False)
    employee_gosi = Column(Numeric(18, 2), nullable=False)
    employer_gosi = Column(Numeric(18, 2), nullable=False)
    other_deductions = Column(Numeric(18, 2), nullable=False, default=0)
    working_days = Column(Numeric(8, 2), nullable=False, default=0)
    paid_days = Column(Numeric(8, 2), nullable=False, default=0)
    absent_days = Column(Numeric(8, 2), nullable=False, default=0)
    unpaid_leave_days = Column(Numeric(8, 2), nullable=False, default=0)
    late_minutes = Column(Integer, nullable=False, default=0)
    overtime_minutes = Column(Integer, nullable=False, default=0)
    overtime_amount = Column(EncryptedDecimal(), nullable=True, default=0)
    absence_deduction = Column(EncryptedDecimal(), nullable=True, default=0)
    unpaid_leave_deduction = Column(EncryptedDecimal(), nullable=True, default=0)
    earning_adjustments = Column(EncryptedDecimal(), nullable=True, default=0)
    deduction_adjustments = Column(EncryptedDecimal(), nullable=True, default=0)
    net_salary = Column(EncryptedDecimal(), nullable=False)
    run = relationship("PayrollRun", back_populates="lines")
    employee = relationship("Employee", lazy="joined")


# -------------------- Restaurant POS and delivery platforms --------------------

class DeliveryPlatform(Base):
    __tablename__ = "delivery_platforms"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_delivery_platform_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(150), nullable=False)
    name_en = Column(String(150), nullable=False)
    commission_rate = Column(Numeric(8, 4), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)

class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_menu_item_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    recipe_bom_id = Column(Integer, ForeignKey("bills_of_material.id"), nullable=False)
    selling_price = Column(Numeric(18, 2), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id"), index=True)
    active = Column(Boolean, nullable=False, default=True)
    inventory_item = relationship("Item", lazy="joined")
    recipe = relationship("BillOfMaterial", lazy="joined")
    tax_code = relationship("TaxCode", lazy="joined")

class PosOrder(Base):
    __tablename__ = "pos_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_pos_order_company_number"),
        UniqueConstraint("company_id", "client_order_id", name="uq_pos_order_client_order"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    order_date = Column(Date, nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    business_unit = Column(String(20), nullable=False, default="RESTAURANT", index=True)
    gym_department_id = Column(Integer, ForeignKey("gym_departments.id"), index=True)
    gym_member_id = Column(Integer, ForeignKey("members.id"), index=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), index=True)
    order_type = Column(String(20), nullable=False, default="TAKEAWAY", index=True)
    table_id = Column(Integer, ForeignKey("restaurant_tables.id"))
    reservation_id = Column(Integer, ForeignKey("restaurant_reservations.id"))
    cashier_shift_id = Column(Integer, ForeignKey("cashier_shifts.id"), index=True)
    guest_count = Column(Integer, nullable=False, default=1)
    customer_name = Column(String(200))
    notes = Column(String(500))
    client_order_id = Column(String(120))
    source_device_id = Column(String(100))
    sync_status = Column(String(20), nullable=False, default="ONLINE", index=True)
    payment_channel = Column(String(20), nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"))
    platform_id = Column(Integer, ForeignKey("delivery_platforms.id"))
    subtotal = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    total = Column(Numeric(18, 2), nullable=False)
    food_cost = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="POSTED", index=True)
    sale_journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    cogs_journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    settlement_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    lines = relationship("PosOrderLine", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    platform = relationship("DeliveryPlatform", lazy="joined")

class PosOrderLine(Base):
    __tablename__ = "pos_order_lines"
    id = Column(Integer, primary_key=True)
    pos_order_id = Column(Integer, ForeignKey("pos_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 2), nullable=False)
    net_amount = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    tax_code_id = Column(Integer, ForeignKey("tax_codes.id"), index=True)
    total_amount = Column(Numeric(18, 2), nullable=False)
    food_cost = Column(Numeric(18, 2), nullable=False)
    order = relationship("PosOrder", back_populates="lines")
    menu_item = relationship("MenuItem", lazy="joined")
    tax_code = relationship("TaxCode", lazy="joined")


# -------------------- Security, compliance, HR operations and close v0.16 --------------------

class PasswordHistory(Base):
    __tablename__ = "password_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    password_hash = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)

class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_version = Column(Integer, nullable=False)
    issued_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=utc_now)
    refresh_token_hash = Column(String(64), unique=True, index=True)
    refresh_expires_at = Column(DateTime, index=True)
    rotated_at = Column(DateTime)
    revoked_at = Column(DateTime)
    revoke_reason = Column(String(100))
    parent_session_id = Column(String(64), ForeignKey("user_sessions.id"))
    ip_address = Column(String(64))
    user_agent = Column(String(500))

class LegalRuleVersion(Base):
    __tablename__ = "legal_rule_versions"
    __table_args__ = (UniqueConstraint("code", "effective_from", name="uq_legal_rule_effective"),)
    id = Column(Integer, primary_key=True)
    code = Column(String(100), nullable=False, index=True)
    jurisdiction = Column(String(10), nullable=False, default="SA")
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date)
    parameters_json = Column(Text, nullable=False)
    source_url = Column(String(1000), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_shift_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(150), nullable=False)
    name_en = Column(String(150), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    grace_minutes = Column(Integer, nullable=False, default=10)
    working_days = Column(String(30), nullable=False, default="0,1,2,3,4")
    active = Column(Boolean, nullable=False, default=True)

class EmployeeShiftAssignment(Base):
    __tablename__ = "employee_shift_assignments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_attendance_employee_date"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    work_date = Column(Date, nullable=False, index=True)
    clock_in = Column(DateTime)
    clock_out = Column(DateTime)
    status = Column(String(25), nullable=False, default="PENDING", index=True)
    late_minutes = Column(Integer, nullable=False, default=0)
    early_leave_minutes = Column(Integer, nullable=False, default=0)
    overtime_minutes = Column(Integer, nullable=False, default=0)
    source = Column(String(30), nullable=False, default="SYSTEM")
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    geofence_valid = Column(Boolean)
    manual_reason = Column(String(500))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)

class LeaveType(Base):
    __tablename__ = "leave_types"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_leave_type_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(150), nullable=False)
    name_en = Column(String(150), nullable=False)
    paid = Column(Boolean, nullable=False, default=True)
    affects_payroll = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)

class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_leave_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Numeric(8, 2), nullable=False)
    reason = Column(String(500))
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)

class EndOfServiceSettlement(Base):
    __tablename__ = "end_of_service_settlements"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_eos_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    termination_date = Column(Date, nullable=False)
    termination_reason = Column(String(40), nullable=False)
    service_days = Column(Integer, nullable=False)
    last_wage = Column(Numeric(18, 2), nullable=False)
    gross_award = Column(Numeric(18, 2), nullable=False)
    entitlement_percent = Column(Numeric(8, 4), nullable=False)
    award_amount = Column(Numeric(18, 2), nullable=False)
    leave_encashment = Column(Numeric(18, 2), nullable=False, default=0)
    deductions = Column(Numeric(18, 2), nullable=False, default=0)
    net_settlement = Column(Numeric(18, 2), nullable=False)
    rule_version_id = Column(Integer, ForeignKey("legal_rule_versions.id"), nullable=False)
    status = Column(String(20), nullable=False, default="CALCULATED", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)

__all__ = ['Employee', 'PayrollRun', 'PayrollLine', 'DeliveryPlatform', 'MenuItem', 'PosOrder', 'PosOrderLine', 'PasswordHistory', 'UserSession', 'LegalRuleVersion', 'Shift', 'EmployeeShiftAssignment', 'AttendanceRecord', 'LeaveType', 'LeaveRequest', 'EndOfServiceSettlement']
