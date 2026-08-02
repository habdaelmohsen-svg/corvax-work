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

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_company_role_branches = Table(
    "user_company_role_branches",
    Base.metadata,
    Column("membership_id", ForeignKey("user_company_roles.id", ondelete="CASCADE"), primary_key=True),
    Column("branch_id", ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("membership_id", "branch_id", name="uq_membership_branch"),
)

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False, unique=True, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    legal_name_ar = Column(String(250))
    legal_name_en = Column(String(250))
    currency = Column(String(3), nullable=False, default="SAR")
    country_code = Column(String(2), nullable=False, default="SA")
    vat_number = Column(EncryptedString(512))
    commercial_registration = Column(EncryptedString(512))
    zatca_distinguished_number = Column(EncryptedString(512))
    tax_account_number = Column(EncryptedString(512))
    taxpayer_identity_number = Column(EncryptedString(512))
    registered_address = Column(EncryptedString(2048))
    logo_url = Column(String(500))
    primary_color = Column(String(20), nullable=False, default="#3157D5")
    company_type = Column(String(30), nullable=False, default="TRADING")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    branches = relationship("Branch", back_populates="company", cascade="all, delete-orphan")
    cost_centers = relationship("CostCenter", back_populates="company", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="company", cascade="all, delete-orphan")

class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_branch_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    city_ar = Column(String(100))
    city_en = Column(String(100))
    active = Column(Boolean, nullable=False, default=True)
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    geofence_radius_m = Column(Integer, nullable=False, default=200)
    company = relationship("Company", back_populates="branches")

class CostCenter(Base):
    __tablename__ = "cost_centers"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_cc_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    parent_id = Column(Integer, ForeignKey("cost_centers.id"))
    active = Column(Boolean, nullable=False, default=True)
    company = relationship("Company", back_populates="cost_centers")

class FiscalYear(Base):
    __tablename__ = "fiscal_years"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_fy_company_name"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")
    periods = relationship("FiscalPeriod", back_populates="fiscal_year", cascade="all, delete-orphan")

class FiscalPeriod(Base):
    __tablename__ = "fiscal_periods"
    __table_args__ = (UniqueConstraint("fiscal_year_id", "number", name="uq_period_year_number"),)
    id = Column(Integer, primary_key=True)
    fiscal_year_id = Column(Integer, ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    name_ar = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="FUTURE")
    fiscal_year = relationship("FiscalYear", back_populates="periods")

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    code = Column(String(100), nullable=False, unique=True, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    permissions = relationship("Permission", secondary=role_permissions, lazy="selectin")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    email = Column(String(320), nullable=False, unique=True, index=True)
    # H17: short login name (e.g. "admin"). Employees can sign in with this
    # instead of a full email address. Unique per platform, lower-cased.
    username = Column(String(60), unique=True, index=True)
    password_hash = Column(String(500), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime)
    last_login_at = Column(DateTime)
    password_changed_at = Column(DateTime, nullable=False, default=utc_now)
    require_password_change = Column(Boolean, nullable=False, default=False)
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    # AUDIT H-08: stored encrypted at rest. EncryptedString was already used
    # for other sensitive columns but not for this one.
    mfa_secret = Column(EncryptedString(400))
    token_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    memberships = relationship("UserCompanyRole", back_populates="user", cascade="all, delete-orphan")

class UserCompanyRole(Base):
    __tablename__ = "user_company_roles"
    __table_args__ = (UniqueConstraint("user_id", "company_id", "role_id", name="uq_user_company_role"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    branch_scope = Column(String(20), nullable=False, default="ALL")
    user = relationship("User", back_populates="memberships")
    company = relationship("Company")
    role = relationship("Role", lazy="joined")
    branches = relationship("Branch", secondary=user_company_role_branches, lazy="selectin")

__all__ = ['role_permissions', 'user_company_role_branches', 'Company', 'Branch', 'CostCenter', 'FiscalYear', 'FiscalPeriod', 'Permission', 'Role', 'User', 'UserCompanyRole']
