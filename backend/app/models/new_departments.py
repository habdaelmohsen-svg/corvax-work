"""CORVAX RC27.4 H10 - new departments: Fleet/Logistics and Legal Affairs.

NOTE: Maintenance already exists in the platform (models in operations_compliance.py,
API under /risk-maintenance/maintenance/...). H10 does NOT redefine it; the H10
maintenance UI binds to that existing API. H10 adds only the genuinely missing
departments: Fleet/Logistics and Legal Affairs.

All models are company-scoped and bilingual (Arabic + English fields).
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


# ============================================================ FLEET / LOGISTICS
class Vehicle(Base):
    __tablename__ = "fleet_vehicles"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    plate_number = Column(String(30), nullable=False)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    vehicle_type = Column(String(30), nullable=False, default="REFRIGERATED_TRUCK")  # REFRIGERATED_TRUCK / TRUCK / VAN / CAR / FORKLIFT
    make = Column(String(80))
    model = Column(String(80))
    year = Column(Integer)
    is_refrigerated = Column(Boolean, nullable=False, default=True)
    odometer_km = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="AVAILABLE")  # AVAILABLE / ON_TRIP / MAINTENANCE / OUT_OF_SERVICE
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class Driver(Base):
    __tablename__ = "fleet_drivers"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    license_number = Column(String(60), nullable=False)
    license_expiry = Column(Date)
    phone = Column(String(30))
    status = Column(String(20), nullable=False, default="AVAILABLE")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class Trip(Base):
    __tablename__ = "fleet_trips"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("fleet_vehicles.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("fleet_drivers.id"), nullable=False)
    trip_date = Column(Date, nullable=False)
    origin_ar = Column(String(200))
    origin_en = Column(String(200))
    destination_ar = Column(String(200))
    destination_en = Column(String(200))
    purpose = Column(String(30), nullable=False, default="DELIVERY")  # DELIVERY / PICKUP / TRANSFER / OTHER
    distance_km = Column(Numeric(18, 2), nullable=False, default=0)
    fuel_cost = Column(Numeric(18, 2), nullable=False, default=0)
    cargo_description_ar = Column(String(300))
    cargo_description_en = Column(String(300))
    cargo_temperature = Column(Numeric(6, 2))  # for refrigerated food loads
    status = Column(String(20), nullable=False, default="PLANNED")  # PLANNED / IN_TRANSIT / DELIVERED / CANCELLED
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    vehicle = relationship("Vehicle", lazy="joined")
    driver = relationship("Driver", lazy="joined")


# ============================================================ LEGAL AFFAIRS
class LegalContract(Base):
    __tablename__ = "legal_contracts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    contract_type = Column(String(30), nullable=False, default="SUPPLIER")  # SUPPLIER / CUSTOMER / LEASE / EMPLOYMENT / SERVICE / NDA / OTHER
    counterparty_ar = Column(String(200))
    counterparty_en = Column(String(200))
    start_date = Column(Date)
    end_date = Column(Date)
    value = Column(Numeric(18, 2), nullable=False, default=0)
    auto_renew = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="ACTIVE")  # DRAFT / ACTIVE / EXPIRED / TERMINATED
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class LegalCase(Base):
    __tablename__ = "legal_cases"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    case_type = Column(String(30), nullable=False, default="COMMERCIAL")  # COMMERCIAL / LABOR / REGULATORY / TAX / OTHER
    counterparty_ar = Column(String(200))
    counterparty_en = Column(String(200))
    court_ar = Column(String(200))
    court_en = Column(String(200))
    filing_date = Column(Date)
    hearing_date = Column(Date)
    claim_amount = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="OPEN")  # OPEN / IN_PROGRESS / WON / LOST / SETTLED / CLOSED
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class LegalLicense(Base):
    """Commercial registrations, municipal licenses, food-safety permits, etc."""
    __tablename__ = "legal_licenses"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    license_type = Column(String(40), nullable=False, default="COMMERCIAL_REGISTRATION")
    license_number = Column(String(80), nullable=False)
    issuer_ar = Column(String(200))
    issuer_en = Column(String(200))
    issue_date = Column(Date)
    expiry_date = Column(Date, index=True)
    status = Column(String(20), nullable=False, default="VALID")  # VALID / EXPIRING_SOON / EXPIRED
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utc_now)


__all__ = [
    "Vehicle", "Driver", "Trip",
    "LegalContract", "LegalCase", "LegalLicense",
]
