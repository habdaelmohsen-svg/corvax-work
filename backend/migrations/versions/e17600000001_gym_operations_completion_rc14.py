"""Gym operations completion RC14

Revision ID: e17600000001
Revises: e17500000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e17600000001"
down_revision = "e17500000001"
branch_labels = None
depends_on = None

PERMISSIONS = {
    "gym.memberships.manage": ("إعداد تعديلات العضويات", "Prepare membership modifications"),
    "gym.memberships.approve": ("اعتماد تعديلات واستردادات العضويات", "Approve membership modifications and refunds"),
    "gym.classes.manage": ("إدارة الحصص والجداول", "Manage classes and schedules"),
    "gym.bookings.manage": ("إدارة حجوزات الحصص وقوائم الانتظار", "Manage class bookings and waitlists"),
    "gym.pt.manage": ("إدارة باقات وجلسات التدريب الشخصي", "Manage personal-training packages and sessions"),
    "gym.pt.complete": ("إتمام جلسات التدريب الشخصي", "Complete personal-training sessions"),
    "gym.commissions.review": ("إعداد ومراجعة عمولات المدربين", "Prepare and review trainer commissions"),
    "gym.commissions.approve": ("اعتماد وصرف عمولات المدربين", "Approve and pay trainer commissions"),
    "gym.access.capture": ("تسجيل دخول وخروج أعضاء النادي", "Capture gym member access"),
    "gym.lockers.manage": ("إدارة خزائن الأعضاء", "Manage member lockers"),
    "gym.transfers.manage": ("إعداد تحويل العضويات بين الفروع", "Prepare membership branch transfers"),
    "gym.transfers.approve": ("اعتماد تحويل العضويات بين الفروع", "Approve membership branch transfers"),
}

ROLE_PERMISSIONS = {
    "GYM_MANAGER": [
        "company.read", "masterdata.read", "gym.read", "gym.manage", "gym.memberships.manage",
        "gym.classes.manage", "gym.bookings.manage", "gym.pt.manage", "gym.pt.complete",
        "gym.commissions.review", "gym.access.capture", "gym.lockers.manage", "gym.transfers.manage", "audit.read",
    ],
    "GYM_TRAINER": ["company.read", "gym.read", "gym.bookings.manage", "gym.pt.complete", "gym.access.capture"],
    "FINANCIAL_CONTROLLER": ["gym.memberships.approve", "gym.commissions.review", "gym.transfers.approve"],
    "CFO": ["gym.memberships.approve", "gym.commissions.approve", "gym.transfers.approve"],
    "ACCOUNTANT": ["gym.commissions.review"],
    "AUDITOR": ["gym.commissions.review"],
}

ACCOUNT_SPECS = [
    ("213020", "أرصدة دائنة للأعضاء", "Member Credit Liability", "LIABILITY", "CONTRACT_LIABILITY", "210000"),
    ("217020", "عمولات مدربين مستحقة", "Trainer Commissions Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000"),
    ("412020", "إيراد التدريب الشخصي", "Personal Training Revenue", "REVENUE", "OPERATING_REVENUE", "400000"),
    ("625010", "عمولات المدربين", "Trainer Commission Expense", "EXPENSE", "OPERATING_EXPENSES", "600000"),
]


def _seed_access_and_accounts() -> None:
    bind = op.get_bind()
    for role_code, ar, en in [
        ("GYM_MANAGER", "مدير النادي", "Gym Manager"),
        ("GYM_TRAINER", "مدرب النادي", "Gym Trainer"),
    ]:
        if bind.execute(sa.text("SELECT id FROM roles WHERE code=:code"), {"code": role_code}).scalar() is None:
            bind.execute(sa.text("INSERT INTO roles(code,name_ar,name_en) VALUES (:code,:ar,:en)"), {"code": role_code, "ar": ar, "en": en})
    for code, (name_ar, name_en) in PERMISSIONS.items():
        if bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar() is None:
            bind.execute(sa.text("INSERT INTO permissions(code,name_ar,name_en) VALUES (:code,:ar,:en)"), {"code": code, "ar": name_ar, "en": name_en})
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE code=:code"), {"code": role_code}).scalar()
        if role_id is None:
            continue
        for permission_code in permission_codes:
            permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": permission_code}).scalar()
            if permission_id is None:
                continue
            exists = bind.execute(sa.text("SELECT 1 FROM role_permissions WHERE role_id=:r AND permission_id=:p"), {"r": role_id, "p": permission_id}).scalar()
            if exists is None:
                bind.execute(sa.text("INSERT INTO role_permissions(role_id,permission_id) VALUES (:r,:p)"), {"r": role_id, "p": permission_id})
    company_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM companies")).fetchall()]
    for company_id in company_ids:
        for code, ar, en, account_type, group, parent_code in ACCOUNT_SPECS:
            if bind.execute(sa.text("SELECT id FROM accounts WHERE company_id=:c AND code=:code"), {"c": company_id, "code": code}).scalar() is not None:
                continue
            parent_id = bind.execute(sa.text("SELECT id FROM accounts WHERE company_id=:c AND code=:code"), {"c": company_id, "code": parent_code}).scalar()
            bind.execute(sa.text(
                "INSERT INTO accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active) "
                "VALUES (:c,:code,:ar,:en,:type,:grp,:parent,3,:postable,:cash,:active)"
            ), {"c": company_id, "code": code, "ar": ar, "en": en, "type": account_type, "grp": group,
                "parent": parent_id, "postable": True, "cash": False, "active": True})


def upgrade():
    op.create_table(
        "gym_membership_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), index=True),
        sa.Column("original_end_date", sa.Date(), nullable=False),
        sa.Column("total_frozen_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("freeze_start", sa.Date()), sa.Column("freeze_end", sa.Date()),
        sa.Column("refunded_net", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refunded_vat", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("last_modification_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("contract_id", name="uq_gym_membership_state_contract"),
    )
    op.create_table(
        "gym_membership_modifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(60), nullable=False, index=True),
        sa.Column("modification_type", sa.String(30), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=False, index=True),
        sa.Column("freeze_start", sa.Date()), sa.Column("freeze_end", sa.Date()),
        sa.Column("extension_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_plan_id", sa.Integer(), sa.ForeignKey("membership_plans.id")),
        sa.Column("target_branch_id", sa.Integer(), sa.ForeignKey("branches.id")),
        sa.Column("adjustment_net", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_vat", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refund_net", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refund_vat", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refund_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refund_method", sa.String(20)), sa.Column("payment_method", sa.String(20)),
        sa.Column("credit_used", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id")),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="SUBMITTED", index=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("rejected_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("adjustment_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("refund_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("approved_at", sa.DateTime()),
        sa.Column("rejected_at", sa.DateTime()), sa.Column("rejection_reason", sa.String(500)),
        sa.UniqueConstraint("company_id", "number", name="uq_gym_membership_modification_number"),
    )
    op.create_table(
        "gym_member_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id", ondelete="SET NULL"), index=True),
        sa.Column("modification_id", sa.Integer(), sa.ForeignKey("gym_membership_modifications.id", ondelete="SET NULL"), index=True),
        sa.Column("transaction_date", sa.Date(), nullable=False, index=True),
        sa.Column("transaction_type", sa.String(30), nullable=False, index=True),
        sa.Column("reference", sa.String(100), nullable=False, index=True),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id")),
        sa.Column("notes", sa.String(500)), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "gym_trainers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), index=True),
        sa.Column("code", sa.String(30), nullable=False), sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("commission_rate", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_gym_trainer_company_code"),
    )
    op.create_table(
        "gym_class_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False), sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("default_capacity", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_id", "code", name="uq_gym_class_type_company_code"),
    )
    op.create_table(
        "gym_class_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("class_type_id", sa.Integer(), sa.ForeignKey("gym_class_types.id"), nullable=False, index=True),
        sa.Column("trainer_id", sa.Integer(), sa.ForeignKey("gym_trainers.id"), index=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False, index=True), sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("waitlist_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(25), nullable=False, server_default="SCHEDULED", index=True),
        sa.Column("notes", sa.String(500)), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "gym_class_bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("gym_class_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id"), nullable=False, index=True),
        sa.Column("status", sa.String(25), nullable=False, server_default="BOOKED", index=True),
        sa.Column("waitlist_position", sa.Integer()), sa.Column("booked_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("booked_at", sa.DateTime(), nullable=False), sa.Column("promoted_at", sa.DateTime()),
        sa.Column("checked_in_at", sa.DateTime()), sa.Column("cancelled_at", sa.DateTime()),
        sa.UniqueConstraint("session_id", "member_id", name="uq_gym_class_booking_session_member"),
    )
    op.create_table(
        "gym_pt_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False), sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False), sa.Column("sessions_count", sa.Integer(), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("net_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(8, 4), nullable=False, server_default="15"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_id", "code", name="uq_gym_pt_package_company_code"),
    )
    op.create_table(
        "gym_pt_sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False, index=True),
        sa.Column("membership_contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id"), index=True),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("gym_pt_packages.id"), nullable=False),
        sa.Column("trainer_id", sa.Integer(), sa.ForeignKey("gym_trainers.id"), nullable=False),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False, index=True),
        sa.Column("sale_date", sa.Date(), nullable=False, index=True), sa.Column("expiry_date", sa.Date(), nullable=False, index=True),
        sa.Column("sessions_total", sa.Integer(), nullable=False), sa.Column("sessions_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 2), nullable=False), sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False), sa.Column("deferred_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("sale_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "number", name="uq_gym_pt_sale_number"),
    )
    op.create_table(
        "gym_pt_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pt_sale_id", sa.Integer(), sa.ForeignKey("gym_pt_sales.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("trainer_id", sa.Integer(), sa.ForeignKey("gym_trainers.id"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("session_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("status", sa.String(25), nullable=False, server_default="BOOKED", index=True),
        sa.Column("revenue_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("commission_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("commission_status", sa.String(25), nullable=False, server_default="UNACCRUED", index=True),
        sa.Column("revenue_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("commission_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("booked_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("booked_at", sa.DateTime(), nullable=False), sa.Column("completed_at", sa.DateTime()),
        sa.Column("notes", sa.String(500)),
    )
    op.create_table(
        "gym_trainer_commission_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("trainer_id", sa.Integer(), sa.ForeignKey("gym_trainers.id"), nullable=False, index=True),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False, index=True),
        sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("payout_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("reviewed_at", sa.DateTime()), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_gym_trainer_commission_batch_number"),
    )
    op.create_table(
        "gym_trainer_commission_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("gym_trainer_commission_batches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pt_session_id", sa.Integer(), sa.ForeignKey("gym_pt_sessions.id"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("pt_session_id", name="uq_gym_commission_line_session"),
    )
    op.create_table(
        "gym_access_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id"), index=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("direction", sa.String(10), nullable=False), sa.Column("method", sa.String(20), nullable=False, server_default="MANUAL"),
        sa.Column("status", sa.String(20), nullable=False, index=True), sa.Column("reason", sa.String(500)),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "gym_lockers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="AVAILABLE", index=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_id", "branch_id", "code", name="uq_gym_locker_branch_code"),
    )
    op.create_table(
        "gym_locker_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("locker_id", sa.Integer(), sa.ForeignKey("gym_lockers.id"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id"), nullable=False, index=True),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date()),
        sa.Column("deposit_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("released_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("assigned_at", sa.DateTime(), nullable=False), sa.Column("released_at", sa.DateTime()),
    )
    op.create_table(
        "gym_branch_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id"), nullable=False, index=True),
        sa.Column("from_branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("to_branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False, index=True),
        sa.Column("transfer_date", sa.Date(), nullable=False, index=True), sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="SUBMITTED", index=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_gym_branch_transfer_number"),
    )
    bind = op.get_bind()
    bind.execute(sa.text(
        "INSERT INTO gym_membership_states(company_id,contract_id,branch_id,original_end_date,total_frozen_days,refunded_net,refunded_vat,credit_balance,updated_at) "
        "SELECT company_id,id,NULL,end_date,0,0,0,0,CURRENT_TIMESTAMP FROM membership_contracts "
        "WHERE id NOT IN (SELECT contract_id FROM gym_membership_states)"
    ))
    _seed_access_and_accounts()


def downgrade():
    for table in [
        "gym_branch_transfers", "gym_locker_assignments", "gym_lockers", "gym_access_records",
        "gym_trainer_commission_lines", "gym_trainer_commission_batches", "gym_pt_sessions", "gym_pt_sales",
        "gym_pt_packages", "gym_class_bookings", "gym_class_sessions", "gym_class_types", "gym_trainers",
        "gym_member_ledger", "gym_membership_modifications", "gym_membership_states",
    ]:
        op.drop_table(table)
