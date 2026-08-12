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

class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("company_id", "member_number", name="uq_member_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    member_number = Column(String(40), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    mobile = Column(String(30))
    active = Column(Boolean, nullable=False, default=True)

class MembershipPlan(Base):
    __tablename__ = "membership_plans"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_plan_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    duration_months = Column(Integer, nullable=False)
    net_price = Column(Numeric(18, 2), nullable=False)
    vat_rate = Column(Numeric(8, 4), nullable=False, default=15)
    active = Column(Boolean, nullable=False, default=True)

class MembershipContract(Base):
    __tablename__ = "membership_contracts"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_membership_contract_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("membership_plans.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    net_amount = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    total_amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(25), nullable=False, default="ACTIVE", index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    sale_journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    member = relationship("Member", lazy="joined")
    plan = relationship("MembershipPlan", lazy="joined")
    schedules = relationship("RevenueSchedule", back_populates="contract", cascade="all, delete-orphan", lazy="selectin")

class RevenueSchedule(Base):
    __tablename__ = "revenue_schedules"
    __table_args__ = (UniqueConstraint("contract_id", "period_number", name="uq_contract_revenue_period"),)
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("membership_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    period_number = Column(Integer, nullable=False)
    recognition_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    recognized_at = Column(DateTime)
    contract = relationship("MembershipContract", back_populates="schedules")
    journal = relationship("JournalEntry")


# -------------------- IFRS 16 leases --------------------

class LeaseContract(Base):
    __tablename__ = "lease_contracts"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_lease_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    commencement_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    payment_amount = Column(Numeric(18, 2), nullable=False)
    payment_frequency_months = Column(Integer, nullable=False, default=1)
    payment_timing = Column(String(20), nullable=False, default="ARREARS")
    annual_discount_rate = Column(Numeric(9, 6), nullable=False)
    initial_liability = Column(Numeric(18, 2), nullable=False)
    initial_rou_asset = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    # Nullable while the retained contract is awaiting IFRS 16 re-initialization.
    initial_journal_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    schedules = relationship("LeaseSchedule", back_populates="lease", cascade="all, delete-orphan", lazy="selectin")

class LeaseSchedule(Base):
    __tablename__ = "lease_schedules"
    __table_args__ = (UniqueConstraint("lease_id", "period_number", name="uq_lease_schedule_period"),)
    id = Column(Integer, primary_key=True)
    lease_id = Column(Integer, ForeignKey("lease_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    period_number = Column(Integer, nullable=False)
    payment_date = Column(Date, nullable=False, index=True)
    opening_liability = Column(Numeric(18, 2), nullable=False)
    interest = Column(Numeric(18, 2), nullable=False)
    payment = Column(Numeric(18, 2), nullable=False)
    principal = Column(Numeric(18, 2), nullable=False)
    closing_liability = Column(Numeric(18, 2), nullable=False)
    depreciation = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    lease = relationship("LeaseContract", back_populates="schedules")
    journal = relationship("JournalEntry")


# -------------------- Manufacturing and quality --------------------

__all__ = ['Member', 'MembershipPlan', 'MembershipContract', 'RevenueSchedule', 'LeaseContract', 'LeaseSchedule']
