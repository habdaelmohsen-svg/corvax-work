"""HR and payroll completion RC12

Revision ID: e17400000001
Revises: e17300000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e17400000001"
down_revision = "e17300000001"
branch_labels = None
depends_on = None

PERMISSIONS = {
    "hr.contracts.manage": ("إدارة عقود الموظفين", "Manage employee contracts"),
    "hr.overtime.manage": ("إدارة طلبات العمل الإضافي", "Manage overtime requests"),
    "hr.overtime.approve": ("اعتماد العمل الإضافي", "Approve overtime"),
    "payroll.adjustments.manage": ("إعداد تعديلات الرواتب", "Prepare payroll adjustments"),
    "payroll.adjustments.review": ("مراجعة تعديلات الرواتب", "Review payroll adjustments"),
    "payroll.adjustments.approve": ("اعتماد تعديلات الرواتب", "Approve payroll adjustments"),
    "payroll.review": ("مراجعة مسير الرواتب", "Review payroll run"),
    "payroll.approve": ("اعتماد وترحيل مسير الرواتب", "Approve and post payroll run"),
    "payroll.wps": ("إدارة دفعات حماية الأجور", "Manage WPS batches"),
    "benefits.manage": ("إعداد تقييم منافع الموظفين", "Prepare employee-benefit valuation"),
    "benefits.review": ("مراجعة تقييم منافع الموظفين", "Review employee-benefit valuation"),
    "benefits.approve": ("اعتماد تقييم منافع الموظفين", "Approve employee-benefit valuation"),
}

ROLE_PERMISSIONS = {
    "HR_MANAGER": [
        "company.read", "masterdata.read", "payroll.read", "payroll.manage", "payroll.review",
        "attendance.read", "attendance.manage", "attendance.capture", "attendance.override",
        "leave.read", "leave.manage", "leave.approve", "eos.manage",
        "hr.contracts.manage", "hr.overtime.manage", "hr.overtime.approve",
        "payroll.adjustments.manage", "payroll.adjustments.review",
        "benefits.manage", "benefits.review", "audit.read",
    ],
    "FINANCIAL_CONTROLLER": ["payroll.review", "payroll.adjustments.review", "benefits.review"],
    "CFO": ["payroll.approve", "payroll.wps", "payroll.adjustments.approve", "benefits.approve"],
    "AUDITOR": ["benefits.review"],
}


def _seed_access() -> None:
    bind = op.get_bind()
    role_id = bind.execute(sa.text("SELECT id FROM roles WHERE code='HR_MANAGER'")).scalar()
    if role_id is None:
        bind.execute(sa.text("INSERT INTO roles(code,name_ar,name_en) VALUES ('HR_MANAGER','مدير الموارد البشرية','HR Manager')"))
    for code, (name_ar, name_en) in PERMISSIONS.items():
        if bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar() is None:
            bind.execute(sa.text("INSERT INTO permissions(code,name_ar,name_en) VALUES (:code,:ar,:en)"), {"code": code, "ar": name_ar, "en": name_en})
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        rid = bind.execute(sa.text("SELECT id FROM roles WHERE code=:code"), {"code": role_code}).scalar()
        if rid is None:
            continue
        for permission_code in permission_codes:
            pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": permission_code}).scalar()
            if pid is None:
                continue
            exists = bind.execute(sa.text("SELECT 1 FROM role_permissions WHERE role_id=:r AND permission_id=:p"), {"r": rid, "p": pid}).scalar()
            if exists is None:
                bind.execute(sa.text("INSERT INTO role_permissions(role_id,permission_id) VALUES (:r,:p)"), {"r": rid, "p": pid})


def upgrade():
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("national_id", sa.Text()))
        batch.add_column(sa.Column("birth_date", sa.Date()))
        batch.add_column(sa.Column("salary_bank_code", sa.String(20)))
    with op.batch_alter_table("payroll_runs") as batch:
        batch.add_column(sa.Column("reviewed_by", sa.Integer()))
        batch.add_column(sa.Column("approved_by", sa.Integer()))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime()))
        batch.add_column(sa.Column("approved_at", sa.DateTime()))
        batch.add_column(sa.Column("analysis_hash", sa.String(64)))
        batch.add_column(sa.Column("attendance_completeness_percent", sa.Numeric(8, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("review_override_reason", sa.String(500)))
        batch.create_foreign_key("fk_payroll_run_reviewer", "users", ["reviewed_by"], ["id"])
        batch.create_foreign_key("fk_payroll_run_approver", "users", ["approved_by"], ["id"])
    with op.batch_alter_table("payroll_lines") as batch:
        batch.add_column(sa.Column("working_days", sa.Numeric(8, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("paid_days", sa.Numeric(8, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("absent_days", sa.Numeric(8, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("unpaid_leave_days", sa.Numeric(8, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("overtime_minutes", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("overtime_amount", sa.Text(), nullable=True))
        batch.add_column(sa.Column("absence_deduction", sa.Text(), nullable=True))
        batch.add_column(sa.Column("unpaid_leave_deduction", sa.Text(), nullable=True))
        batch.add_column(sa.Column("earning_adjustments", sa.Text(), nullable=True))
        batch.add_column(sa.Column("deduction_adjustments", sa.Text(), nullable=True))

    op.create_table(
        "payroll_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("salary_day_basis", sa.Numeric(8, 2), nullable=False, server_default="30"),
        sa.Column("standard_daily_hours", sa.Numeric(8, 2), nullable=False, server_default="8"),
        sa.Column("gosi_basis", sa.String(30), nullable=False, server_default="BASIC_HOUSING"),
        sa.Column("late_deduction_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("absence_deduction_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("overtime_basis", sa.String(30), nullable=False, server_default="BASIC"),
        sa.Column("attendance_completeness_threshold", sa.Numeric(8, 2), nullable=False, server_default="95"),
        sa.Column("require_three_user_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", name="uq_payroll_policy_company"),
    )
    op.create_table(
        "employee_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_number", sa.String(60), nullable=False, index=True),
        sa.Column("contract_type", sa.String(30), nullable=False, server_default="UNLIMITED"),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date()), sa.Column("probation_end_date", sa.Date()),
        sa.Column("basic_salary", sa.Text(), nullable=False), sa.Column("housing_allowance", sa.Text(), nullable=False), sa.Column("other_allowance", sa.Text(), nullable=False),
        sa.Column("working_hours_per_week", sa.Numeric(8, 2), nullable=False, server_default="48"),
        sa.Column("notice_days", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "contract_number", name="uq_employee_contract_number"),
    )
    op.create_table(
        "overtime_requests",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True), sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("work_date", sa.Date(), nullable=False, index=True), sa.Column("requested_minutes", sa.Integer(), nullable=False),
        sa.Column("approved_minutes", sa.Integer(), nullable=False, server_default="0"), sa.Column("rate_multiplier", sa.Numeric(8, 4), nullable=False, server_default="1.5"),
        sa.Column("reason", sa.String(500), nullable=False), sa.Column("status", sa.String(25), nullable=False, server_default="SUBMITTED", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("payroll_run_id", sa.Integer(), sa.ForeignKey("payroll_runs.id")), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_overtime_request_number"),
    )
    op.create_table(
        "payroll_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True), sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_year", sa.Integer(), nullable=False, index=True), sa.Column("period_month", sa.Integer(), nullable=False, index=True),
        sa.Column("adjustment_type", sa.String(30), nullable=False), sa.Column("amount", sa.Text(), nullable=False),
        sa.Column("earning", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("gosi_applicable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(500), nullable=False), sa.Column("status", sa.String(25), nullable=False, server_default="SUBMITTED", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("applied_payroll_run_id", sa.Integer(), sa.ForeignKey("payroll_runs.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("reviewed_at", sa.DateTime()), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_payroll_adjustment_number"),
    )
    op.create_table(
        "wps_batches",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("payroll_run_id", sa.Integer(), sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("batch_number", sa.String(60), nullable=False, index=True), sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id"), nullable=False),
        sa.Column("execution_date", sa.Date(), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="GENERATED", index=True),
        sa.Column("total_amount", sa.Text(), nullable=False), sa.Column("line_count", sa.Integer(), nullable=False), sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("response_reference", sa.String(150)), sa.Column("response_message", sa.Text()),
        sa.Column("generated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()), sa.Column("accepted_at", sa.DateTime()),
        sa.UniqueConstraint("payroll_run_id", name="uq_wps_batch_payroll_run"), sa.UniqueConstraint("company_id", "batch_number", name="uq_wps_batch_number"),
    )
    op.create_table(
        "wps_batch_lines",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("wps_batch_id", sa.Integer(), sa.ForeignKey("wps_batches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False, index=True), sa.Column("employee_iban", sa.Text(), nullable=False),
        sa.Column("bank_code", sa.String(20), nullable=False), sa.Column("amount", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING", index=True), sa.Column("rejection_code", sa.String(50)), sa.Column("rejection_reason", sa.String(500)),
        sa.UniqueConstraint("wps_batch_id", "employee_id", name="uq_wps_line_employee"),
    )
    op.create_table(
        "employee_benefit_assumptions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("valuation_date", sa.Date(), nullable=False, index=True), sa.Column("discount_rate", sa.Numeric(10, 6), nullable=False),
        sa.Column("salary_growth_rate", sa.Numeric(10, 6), nullable=False), sa.Column("annual_turnover_rate", sa.Numeric(10, 6), nullable=False),
        sa.Column("retirement_age", sa.Integer(), nullable=False, server_default="60"), sa.Column("mortality_survival_factor", sa.Numeric(10, 6), nullable=False, server_default="0.995"),
        sa.Column("method", sa.String(40), nullable=False, server_default="PROJECTED_UNIT_CREDIT_SUPPORT"), sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("reviewed_at", sa.DateTime()), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "valuation_date", name="uq_benefit_assumption_date"),
    )
    op.create_table(
        "employee_benefit_valuations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("assumption_id", sa.Integer(), sa.ForeignKey("employee_benefit_assumptions.id"), nullable=False), sa.Column("valuation_date", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("total_dbo", sa.Text(), nullable=False), sa.Column("current_service_cost", sa.Text(), nullable=False), sa.Column("interest_cost", sa.Text(), nullable=False), sa.Column("actuarial_gain_loss", sa.Text(), nullable=False),
        sa.Column("employee_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("analysis_hash", sa.String(64), nullable=False),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("reviewed_at", sa.DateTime()), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "valuation_date", "version", name="uq_benefit_valuation_version"),
    )
    op.create_table(
        "employee_benefit_valuation_lines",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("valuation_id", sa.Integer(), sa.ForeignKey("employee_benefit_valuations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False, index=True), sa.Column("current_wage", sa.Text(), nullable=False), sa.Column("projected_final_wage", sa.Text(), nullable=False),
        sa.Column("service_years", sa.Numeric(12, 6), nullable=False), sa.Column("future_service_years", sa.Numeric(12, 6), nullable=False), sa.Column("survival_probability", sa.Numeric(12, 8), nullable=False),
        sa.Column("present_value_obligation", sa.Text(), nullable=False), sa.UniqueConstraint("valuation_id", "employee_id", name="uq_benefit_valuation_employee"),
    )
    _seed_access()


def downgrade():
    for table in [
        "employee_benefit_valuation_lines", "employee_benefit_valuations", "employee_benefit_assumptions",
        "wps_batch_lines", "wps_batches", "payroll_adjustments", "overtime_requests", "employee_contracts", "payroll_policies",
    ]:
        op.drop_table(table)
    with op.batch_alter_table("payroll_lines") as batch:
        for name in ["deduction_adjustments", "earning_adjustments", "unpaid_leave_deduction", "absence_deduction", "overtime_amount", "overtime_minutes", "late_minutes", "unpaid_leave_days", "absent_days", "paid_days", "working_days"]:
            batch.drop_column(name)
    with op.batch_alter_table("payroll_runs") as batch:
        batch.drop_constraint("fk_payroll_run_approver", type_="foreignkey")
        batch.drop_constraint("fk_payroll_run_reviewer", type_="foreignkey")
        for name in ["review_override_reason", "attendance_completeness_percent", "analysis_hash", "approved_at", "reviewed_at", "approved_by", "reviewed_by"]:
            batch.drop_column(name)
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("salary_bank_code"); batch.drop_column("birth_date"); batch.drop_column("national_id")
