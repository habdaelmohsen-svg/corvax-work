from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class GymDepartment(Base):
    __tablename__ = "gym_departments"
    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", "code", name="uq_gym_department_branch_code"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    department_type = Column(String(30), nullable=False, index=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=False)
    revenue_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    capacity = Column(Integer, nullable=False, default=0)
    booking_required = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    branch = relationship("Branch", lazy="joined")
    cost_center = relationship("CostCenter", lazy="joined")
    revenue_account = relationship("Account", lazy="joined")


class GymDepartmentPlanAccess(Base):
    __tablename__ = "gym_department_plan_access"
    __table_args__ = (
        UniqueConstraint("plan_id", "department_id", name="uq_gym_plan_department_access"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("membership_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True)
    access_mode = Column(String(20), nullable=False, default="INCLUDED", index=True)
    monthly_visit_limit = Column(Integer)
    advance_booking_days = Column(Integer, nullable=False, default=7)
    guest_allowed = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    plan = relationship("MembershipPlan", lazy="joined")
    department = relationship("GymDepartment", lazy="joined")


class GymFacility(Base):
    __tablename__ = "gym_facilities"
    __table_args__ = (
        UniqueConstraint("department_id", "code", name="uq_gym_facility_department_code"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    facility_type = Column(String(30), nullable=False, index=True)
    capacity = Column(Integer, nullable=False, default=1)
    slot_minutes = Column(Integer, nullable=False, default=60)
    hourly_rate = Column(Numeric(18, 2), nullable=False, default=0)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    status = Column(String(20), nullable=False, default="AVAILABLE", index=True)
    active = Column(Boolean, nullable=False, default=True)
    notes = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    department = relationship("GymDepartment", lazy="joined")


class GymFacilityBooking(Base):
    __tablename__ = "gym_facility_bookings"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_gym_facility_booking_number"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    facility_id = Column(Integer, ForeignKey("gym_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="SET NULL"), index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id", ondelete="SET NULL"), index=True)
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=False, index=True)
    participants = Column(Integer, nullable=False, default=1)
    access_mode = Column(String(20), nullable=False, default="PAY_PER_USE")
    net_amount = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total_amount = Column(Numeric(18, 2), nullable=False, default=0)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"))
    status = Column(String(25), nullable=False, default="SUBMITTED", index=True)
    notes = Column(String(500))
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    cancelled_by = Column(Integer, ForeignKey("users.id"))
    sale_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    refund_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancellation_reason = Column(String(500))

    facility = relationship("GymFacility", lazy="joined")
    member = relationship("Member", lazy="joined")
    contract = relationship("MembershipContract", lazy="joined")
    bank_account = relationship("BankAccount", lazy="joined")


class GymDepartmentAccessRecord(Base):
    __tablename__ = "gym_department_access_records"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id", ondelete="SET NULL"), index=True)
    occurred_at = Column(DateTime, nullable=False, index=True)
    direction = Column(String(10), nullable=False, default="IN")
    method = Column(String(20), nullable=False, default="QR")
    status = Column(String(20), nullable=False, index=True)
    reason = Column(String(500))
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    department = relationship("GymDepartment", lazy="joined")
    member = relationship("Member", lazy="joined")
    contract = relationship("MembershipContract", lazy="joined")


class GymCafeProductProfile(Base):
    __tablename__ = "gym_cafe_product_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", "menu_item_id", name="uq_gym_cafe_branch_menu_item"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(30), nullable=False, index=True)
    product_type = Column(String(30), nullable=False, index=True)
    member_price = Column(Numeric(18, 2))
    calories = Column(Numeric(10, 2))
    protein_g = Column(Numeric(10, 2))
    carbs_g = Column(Numeric(10, 2))
    fat_g = Column(Numeric(10, 2))
    sugar_g = Column(Numeric(10, 2))
    caffeine_mg = Column(Numeric(10, 2))
    allergens = Column(Text)
    is_healthy = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    branch = relationship("Branch", lazy="joined")
    department = relationship("GymDepartment", lazy="joined")
    menu_item = relationship("MenuItem", lazy="joined")
