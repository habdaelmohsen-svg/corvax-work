from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class GymMembershipState(Base):
    __tablename__ = "gym_membership_states"
    __table_args__ = (UniqueConstraint("contract_id", name="uq_gym_membership_state_contract"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), index=True)
    original_end_date = Column(Date, nullable=False)
    total_frozen_days = Column(Integer, nullable=False, default=0)
    freeze_start = Column(Date)
    freeze_end = Column(Date)
    refunded_net = Column(Numeric(18, 2), nullable=False, default=0)
    refunded_vat = Column(Numeric(18, 2), nullable=False, default=0)
    credit_balance = Column(Numeric(18, 2), nullable=False, default=0)
    last_modification_at = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, default=utc_now)

    contract = relationship("MembershipContract", lazy="joined")
    branch = relationship("Branch", lazy="joined")


class GymMembershipModification(Base):
    __tablename__ = "gym_membership_modifications"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_gym_membership_modification_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    modification_type = Column(String(30), nullable=False, index=True)
    effective_date = Column(Date, nullable=False, index=True)
    freeze_start = Column(Date)
    freeze_end = Column(Date)
    extension_days = Column(Integer, nullable=False, default=0)
    new_plan_id = Column(Integer, ForeignKey("membership_plans.id"))
    target_branch_id = Column(Integer, ForeignKey("branches.id"))
    adjustment_net = Column(Numeric(18, 2), nullable=False, default=0)
    adjustment_vat = Column(Numeric(18, 2), nullable=False, default=0)
    refund_net = Column(Numeric(18, 2), nullable=False, default=0)
    refund_vat = Column(Numeric(18, 2), nullable=False, default=0)
    refund_total = Column(Numeric(18, 2), nullable=False, default=0)
    refund_method = Column(String(20))
    payment_method = Column(String(20))
    credit_used = Column(Numeric(18, 2), nullable=False, default=0)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"))
    reason = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="SUBMITTED", index=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    rejected_by = Column(Integer, ForeignKey("users.id"))
    adjustment_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    refund_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    rejected_at = Column(DateTime)
    rejection_reason = Column(String(500))

    contract = relationship("MembershipContract", lazy="joined")
    new_plan = relationship("MembershipPlan", lazy="joined")
    target_branch = relationship("Branch", lazy="joined")


class GymMemberLedger(Base):
    __tablename__ = "gym_member_ledger"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id", ondelete="SET NULL"), index=True)
    modification_id = Column(Integer, ForeignKey("gym_membership_modifications.id", ondelete="SET NULL"), index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    transaction_type = Column(String(30), nullable=False, index=True)
    reference = Column(String(100), nullable=False, index=True)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"))
    notes = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class GymTrainer(Base):
    __tablename__ = "gym_trainers"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_gym_trainer_company_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("gym_departments.id"), index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    commission_rate = Column(Numeric(8, 4), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class GymClassType(Base):
    __tablename__ = "gym_class_types"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_gym_class_type_company_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("gym_departments.id"), index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)
    default_capacity = Column(Integer, nullable=False, default=20)
    active = Column(Boolean, nullable=False, default=True)


class GymClassSession(Base):
    __tablename__ = "gym_class_sessions"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    class_type_id = Column(Integer, ForeignKey("gym_class_types.id"), nullable=False, index=True)
    facility_id = Column(Integer, ForeignKey("gym_facilities.id"), index=True)
    trainer_id = Column(Integer, ForeignKey("gym_trainers.id"), index=True)
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=False)
    capacity = Column(Integer, nullable=False)
    waitlist_enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String(25), nullable=False, default="SCHEDULED", index=True)
    notes = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    class_type = relationship("GymClassType", lazy="joined")
    trainer = relationship("GymTrainer", lazy="joined")


class GymClassBooking(Base):
    __tablename__ = "gym_class_bookings"
    __table_args__ = (UniqueConstraint("session_id", "member_id", name="uq_gym_class_booking_session_member"),)

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("gym_class_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id"), nullable=False, index=True)
    status = Column(String(25), nullable=False, default="BOOKED", index=True)
    waitlist_position = Column(Integer)
    booked_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    booked_at = Column(DateTime, nullable=False, default=utc_now)
    promoted_at = Column(DateTime)
    checked_in_at = Column(DateTime)
    cancelled_at = Column(DateTime)

    session = relationship("GymClassSession", lazy="joined")
    member = relationship("Member", lazy="joined")


class GymPTPackage(Base):
    __tablename__ = "gym_pt_packages"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_gym_pt_package_company_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    sessions_count = Column(Integer, nullable=False)
    validity_days = Column(Integer, nullable=False, default=90)
    net_price = Column(Numeric(18, 2), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    active = Column(Boolean, nullable=False, default=True)


class GymPTSale(Base):
    __tablename__ = "gym_pt_sales"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_gym_pt_sale_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)
    membership_contract_id = Column(Integer, ForeignKey("membership_contracts.id"), index=True)
    package_id = Column(Integer, ForeignKey("gym_pt_packages.id"), nullable=False)
    trainer_id = Column(Integer, ForeignKey("gym_trainers.id"), nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    number = Column(String(60), nullable=False, index=True)
    sale_date = Column(Date, nullable=False, index=True)
    expiry_date = Column(Date, nullable=False, index=True)
    sessions_total = Column(Integer, nullable=False)
    sessions_used = Column(Integer, nullable=False, default=0)
    net_amount = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    total_amount = Column(Numeric(18, 2), nullable=False)
    deferred_balance = Column(Numeric(18, 2), nullable=False)
    status = Column(String(25), nullable=False, default="ACTIVE", index=True)
    sale_journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    package = relationship("GymPTPackage", lazy="joined")
    trainer = relationship("GymTrainer", lazy="joined")
    member = relationship("Member", lazy="joined")


class GymPTSession(Base):
    __tablename__ = "gym_pt_sessions"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    pt_sale_id = Column(Integer, ForeignKey("gym_pt_sales.id", ondelete="CASCADE"), nullable=False, index=True)
    trainer_id = Column(Integer, ForeignKey("gym_trainers.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    session_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(25), nullable=False, default="BOOKED", index=True)
    revenue_amount = Column(Numeric(18, 2), nullable=False, default=0)
    commission_amount = Column(Numeric(18, 2), nullable=False, default=0)
    commission_status = Column(String(25), nullable=False, default="UNACCRUED", index=True)
    revenue_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    commission_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    booked_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    completed_by = Column(Integer, ForeignKey("users.id"))
    booked_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime)
    notes = Column(String(500))

    sale = relationship("GymPTSale", lazy="joined")
    trainer = relationship("GymTrainer", lazy="joined")


class GymTrainerCommissionBatch(Base):
    __tablename__ = "gym_trainer_commission_batches"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_gym_trainer_commission_batch_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    trainer_id = Column(Integer, ForeignKey("gym_trainers.id"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    number = Column(String(60), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    total_amount = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    payout_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

    trainer = relationship("GymTrainer", lazy="joined")
    lines = relationship("GymTrainerCommissionLine", back_populates="batch", cascade="all, delete-orphan", lazy="selectin")


class GymTrainerCommissionLine(Base):
    __tablename__ = "gym_trainer_commission_lines"
    __table_args__ = (UniqueConstraint("pt_session_id", name="uq_gym_commission_line_session"),)

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("gym_trainer_commission_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    pt_session_id = Column(Integer, ForeignKey("gym_pt_sessions.id"), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)

    batch = relationship("GymTrainerCommissionBatch", back_populates="lines")
    session = relationship("GymPTSession", lazy="joined")


class GymAccessRecord(Base):
    __tablename__ = "gym_access_records"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id"), index=True)
    occurred_at = Column(DateTime, nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    method = Column(String(20), nullable=False, default="MANUAL")
    status = Column(String(20), nullable=False, index=True)
    reason = Column(String(500))
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class GymLocker(Base):
    __tablename__ = "gym_lockers"
    __table_args__ = (UniqueConstraint("company_id", "branch_id", "code", name="uq_gym_locker_branch_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    status = Column(String(25), nullable=False, default="AVAILABLE", index=True)
    active = Column(Boolean, nullable=False, default=True)


class GymLockerAssignment(Base):
    __tablename__ = "gym_locker_assignments"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    locker_id = Column(Integer, ForeignKey("gym_lockers.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    deposit_amount = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    released_by = Column(Integer, ForeignKey("users.id"))
    assigned_at = Column(DateTime, nullable=False, default=utc_now)
    released_at = Column(DateTime)

    locker = relationship("GymLocker", lazy="joined")


class GymBranchTransfer(Base):
    __tablename__ = "gym_branch_transfers"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_gym_branch_transfer_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id"), nullable=False, index=True)
    from_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    to_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    number = Column(String(60), nullable=False, index=True)
    transfer_date = Column(Date, nullable=False, index=True)
    reason = Column(String(500), nullable=False)
    status = Column(String(25), nullable=False, default="SUBMITTED", index=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)


__all__ = [
    "GymMembershipState", "GymMembershipModification", "GymMemberLedger", "GymTrainer",
    "GymClassType", "GymClassSession", "GymClassBooking", "GymPTPackage", "GymPTSale",
    "GymPTSession", "GymTrainerCommissionBatch", "GymTrainerCommissionLine", "GymAccessRecord",
    "GymLocker", "GymLockerAssignment", "GymBranchTransfer",
]
