"""CORVAX RC27.4 H10 - API for Fleet/Logistics and Legal Affairs.

Maintenance already exists at /risk-maintenance/maintenance/... - this router does
not duplicate it. All endpoints are company-scoped and permission-checked. Numbering
uses func.extract('year', ...) which is portable across SQLite and PostgreSQL (Render).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import User
from app.models.new_departments import (
    Driver, LegalCase, LegalContract, LegalLicense, Trip, Vehicle,
)
from app.models.operations_compliance import MaintenanceAsset, MaintenanceWorkOrder
from app.services.audit import write_audit

router = APIRouter(prefix="/departments", tags=["new departments"])


def _next_number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(
        select(func.count(model.id)).where(
            model.company_id == company_id,
            func.extract("year", model.created_at) == year,
        )
    ) or 0
    return f"{prefix}-{company_id}-{year}-{count + 1:05d}"


# ============================================= MAINTENANCE list endpoints (read-only)
# Maintenance create/complete already exist under /risk-maintenance. The platform was
# missing GET list endpoints, which is why maintenance had no usable UI. H10 adds them
# here (reading the existing operations_compliance tables) and provides the UI.
@router.get("/maintenance/assets")
def list_maintenance_assets(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "maintenance.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, MaintenanceAsset)
    query = select(MaintenanceAsset).where(MaintenanceAsset.company_id == company_id)
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.order_by(MaintenanceAsset.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en,
             "production_line": r.production_line, "meter_hours": r.meter_hours,
             "criticality": r.criticality, "status": r.status} for r in rows]


@router.get("/maintenance/work-orders")
def list_maintenance_work_orders(company_id: int, status: str | None = Query(default=None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "maintenance.read")
    query = select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.company_id == company_id)
    if status:
        query = query.where(MaintenanceWorkOrder.status == status)
    rows = db.scalars(query.order_by(MaintenanceWorkOrder.id.desc())).all()
    result = []
    for r in rows:
        asset = db.get(MaintenanceAsset, r.asset_id)
        result.append({"id": r.id, "number": r.number, "asset_id": r.asset_id,
                       "asset_name_ar": asset.name_ar if asset else None,
                       "work_type": r.work_type, "priority": r.priority, "description": r.description,
                       "labor_cost": r.labor_cost, "parts_cost": r.parts_cost,
                       "total_cost": float(r.labor_cost or 0) + float(r.parts_cost or 0),
                       "downtime_minutes": r.downtime_minutes, "status": r.status})
    return result


# ==================================================================== FLEET / LOGISTICS
class VehicleIn(BaseModel):
    company_id: int
    plate_number: str = Field(min_length=1, max_length=30)
    name_ar: str
    name_en: str
    vehicle_type: str = "REFRIGERATED_TRUCK"
    make: str | None = None
    model: str | None = None
    year: int | None = None
    is_refrigerated: bool = True
    odometer_km: float = 0


class DriverIn(BaseModel):
    company_id: int
    name_ar: str
    name_en: str
    license_number: str
    license_expiry: date | None = None
    phone: str | None = None


class TripIn(BaseModel):
    company_id: int
    vehicle_id: int
    driver_id: int
    trip_date: date
    origin_ar: str | None = None
    origin_en: str | None = None
    destination_ar: str | None = None
    destination_en: str | None = None
    purpose: str = "DELIVERY"
    distance_km: float = 0
    fuel_cost: float = 0
    cargo_description_ar: str | None = None
    cargo_description_en: str | None = None
    cargo_temperature: float | None = None


@router.post("/fleet/vehicles", status_code=201)
def create_vehicle(data: VehicleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "fleet.manage")
    v = Vehicle(**data.model_dump())
    db.add(v); db.flush()
    write_audit(db, action="VEHICLE_CREATED", entity_type="VEHICLE", entity_id=v.id, user_id=user.id, company_id=data.company_id, after={"plate": v.plate_number})
    db.commit()
    return {"id": v.id, "plate_number": v.plate_number, "name_ar": v.name_ar, "status": v.status}


@router.get("/fleet/vehicles")
def list_vehicles(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "fleet.read")
    rows = db.scalars(select(Vehicle).where(Vehicle.company_id == company_id).order_by(Vehicle.plate_number)).all()
    return [{"id": r.id, "plate_number": r.plate_number, "name_ar": r.name_ar, "name_en": r.name_en,
             "vehicle_type": r.vehicle_type, "is_refrigerated": r.is_refrigerated, "odometer_km": r.odometer_km, "status": r.status} for r in rows]


@router.post("/fleet/drivers", status_code=201)
def create_driver(data: DriverIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "fleet.manage")
    d = Driver(**data.model_dump())
    db.add(d); db.flush()
    db.commit()
    return {"id": d.id, "name_ar": d.name_ar, "license_number": d.license_number, "status": d.status}


@router.get("/fleet/drivers")
def list_drivers(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "fleet.read")
    rows = db.scalars(select(Driver).where(Driver.company_id == company_id).order_by(Driver.name_ar)).all()
    return [{"id": r.id, "name_ar": r.name_ar, "name_en": r.name_en, "license_number": r.license_number,
             "license_expiry": r.license_expiry.isoformat() if r.license_expiry else None, "phone": r.phone, "status": r.status} for r in rows]


@router.post("/fleet/trips", status_code=201)
def create_trip(data: TripIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "fleet.manage")
    vehicle = db.get(Vehicle, data.vehicle_id)
    driver = db.get(Driver, data.driver_id)
    if not vehicle or vehicle.company_id != data.company_id:
        raise HTTPException(422, "Vehicle does not belong to company")
    if not driver or driver.company_id != data.company_id:
        raise HTTPException(422, "Driver does not belong to company")
    trip = Trip(
        company_id=data.company_id,
        number=_next_number(db, Trip, data.company_id, "TRIP", data.trip_date.year),
        vehicle_id=data.vehicle_id, driver_id=data.driver_id, trip_date=data.trip_date,
        origin_ar=data.origin_ar, origin_en=data.origin_en, destination_ar=data.destination_ar, destination_en=data.destination_en,
        purpose=data.purpose, distance_km=data.distance_km, fuel_cost=data.fuel_cost,
        cargo_description_ar=data.cargo_description_ar, cargo_description_en=data.cargo_description_en,
        cargo_temperature=data.cargo_temperature, status="PLANNED", created_by=user.id,
    )
    db.add(trip); db.flush()
    write_audit(db, action="TRIP_CREATED", entity_type="TRIP", entity_id=trip.id, user_id=user.id, company_id=data.company_id, after={"number": trip.number})
    db.commit()
    return {"id": trip.id, "number": trip.number, "status": trip.status}


@router.get("/fleet/trips")
def list_trips(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "fleet.read")
    rows = db.scalars(select(Trip).where(Trip.company_id == company_id).order_by(Trip.id.desc())).all()
    return [{"id": r.id, "number": r.number, "vehicle_plate": r.vehicle.plate_number if r.vehicle else None,
             "driver_name_ar": r.driver.name_ar if r.driver else None, "trip_date": r.trip_date.isoformat(),
             "origin_ar": r.origin_ar, "destination_ar": r.destination_ar, "purpose": r.purpose,
             "distance_km": r.distance_km, "fuel_cost": r.fuel_cost, "cargo_temperature": r.cargo_temperature, "status": r.status} for r in rows]


# ==================================================================== LEGAL AFFAIRS
class ContractIn(BaseModel):
    company_id: int
    title_ar: str
    title_en: str
    contract_type: str = "SUPPLIER"
    counterparty_ar: str | None = None
    counterparty_en: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    value: float = 0
    auto_renew: bool = False
    notes: str | None = None


class LegalCaseIn(BaseModel):
    company_id: int
    title_ar: str
    title_en: str
    case_type: str = "COMMERCIAL"
    counterparty_ar: str | None = None
    counterparty_en: str | None = None
    court_ar: str | None = None
    court_en: str | None = None
    filing_date: date | None = None
    hearing_date: date | None = None
    claim_amount: float = 0
    notes: str | None = None


class LicenseIn(BaseModel):
    company_id: int
    name_ar: str
    name_en: str
    license_type: str = "COMMERCIAL_REGISTRATION"
    license_number: str
    issuer_ar: str | None = None
    issuer_en: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    notes: str | None = None


@router.post("/legal/contracts", status_code=201)
def create_contract(data: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "legal.manage")
    c = LegalContract(
        company_id=data.company_id,
        number=_next_number(db, LegalContract, data.company_id, "CTR", (data.start_date or date.today()).year),
        **{k: v for k, v in data.model_dump().items() if k != "company_id"}, created_by=user.id,
    )
    db.add(c); db.flush()
    write_audit(db, action="CONTRACT_CREATED", entity_type="LEGAL_CONTRACT", entity_id=c.id, user_id=user.id, company_id=data.company_id, after={"number": c.number})
    db.commit()
    return {"id": c.id, "number": c.number, "status": c.status}


@router.get("/legal/contracts")
def list_contracts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "legal.read")
    rows = db.scalars(select(LegalContract).where(LegalContract.company_id == company_id).order_by(LegalContract.id.desc())).all()
    return [{"id": r.id, "number": r.number, "title_ar": r.title_ar, "title_en": r.title_en, "contract_type": r.contract_type,
             "counterparty_ar": r.counterparty_ar, "start_date": r.start_date.isoformat() if r.start_date else None,
             "end_date": r.end_date.isoformat() if r.end_date else None, "value": r.value, "auto_renew": r.auto_renew, "status": r.status} for r in rows]


@router.post("/legal/cases", status_code=201)
def create_case(data: LegalCaseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "legal.manage")
    c = LegalCase(
        company_id=data.company_id,
        number=_next_number(db, LegalCase, data.company_id, "CASE", (data.filing_date or date.today()).year),
        **{k: v for k, v in data.model_dump().items() if k != "company_id"}, created_by=user.id,
    )
    db.add(c); db.flush()
    write_audit(db, action="LEGAL_CASE_CREATED", entity_type="LEGAL_CASE", entity_id=c.id, user_id=user.id, company_id=data.company_id, after={"number": c.number})
    db.commit()
    return {"id": c.id, "number": c.number, "status": c.status}


@router.get("/legal/cases")
def list_cases(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "legal.read")
    rows = db.scalars(select(LegalCase).where(LegalCase.company_id == company_id).order_by(LegalCase.id.desc())).all()
    return [{"id": r.id, "number": r.number, "title_ar": r.title_ar, "title_en": r.title_en, "case_type": r.case_type,
             "counterparty_ar": r.counterparty_ar, "court_ar": r.court_ar,
             "filing_date": r.filing_date.isoformat() if r.filing_date else None,
             "hearing_date": r.hearing_date.isoformat() if r.hearing_date else None,
             "claim_amount": r.claim_amount, "status": r.status} for r in rows]


@router.post("/legal/licenses", status_code=201)
def create_license(data: LicenseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "legal.manage")
    lic = LegalLicense(**data.model_dump())
    # Compute status from expiry.
    if lic.expiry_date:
        days = (lic.expiry_date - date.today()).days
        lic.status = "EXPIRED" if days < 0 else ("EXPIRING_SOON" if days <= 30 else "VALID")
    db.add(lic); db.flush()
    db.commit()
    return {"id": lic.id, "name_ar": lic.name_ar, "license_number": lic.license_number, "status": lic.status}


@router.get("/legal/licenses")
def list_licenses(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "legal.read")
    rows = db.scalars(select(LegalLicense).where(LegalLicense.company_id == company_id).order_by(LegalLicense.expiry_date)).all()
    result = []
    for r in rows:
        status = r.status
        if r.expiry_date:
            days = (r.expiry_date - date.today()).days
            status = "EXPIRED" if days < 0 else ("EXPIRING_SOON" if days <= 30 else "VALID")
        result.append({"id": r.id, "name_ar": r.name_ar, "name_en": r.name_en, "license_type": r.license_type,
                       "license_number": r.license_number, "issuer_ar": r.issuer_ar,
                       "issue_date": r.issue_date.isoformat() if r.issue_date else None,
                       "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None, "status": status})
    return result
