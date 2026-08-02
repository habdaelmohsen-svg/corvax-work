from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_company_access, ensure_permission, get_current_user
from app.models import Account, AuditLog, Branch, CostCenter, FiscalPeriod, FiscalYear, User
from app.services.audit import write_audit

router = APIRouter(prefix="/enterprise", tags=["enterprise foundation"])


class BranchIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=30)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    city_ar: str | None = Field(default=None, max_length=100)
    city_en: str | None = Field(default=None, max_length=100)
    geofence_radius_m: int = Field(default=200, ge=10, le=10000)


class CostCenterIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=30)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    parent_id: int | None = None


@router.post("/branches", status_code=201)
def create_branch(data: BranchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attendance.manage")
    code = data.code.strip().upper()
    if db.scalar(select(Branch).where(Branch.company_id == data.company_id, Branch.code == code)):
        raise HTTPException(409, "Branch code already exists")
    row = Branch(
        company_id=data.company_id, code=code, name_ar=data.name_ar.strip(),
        name_en=(data.name_en or data.name_ar).strip(), city_ar=data.city_ar,
        city_en=data.city_en or data.city_ar, geofence_radius_m=data.geofence_radius_m,
        active=True,
    )
    db.add(row); db.flush()
    write_audit(db, action="HR_BRANCH_CREATED", entity_type="BRANCH", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "name_ar": row.name_ar})
    db.commit(); db.refresh(row)
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "active": row.active}


@router.post("/cost-centers", status_code=201)
def create_cost_center(data: CostCenterIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attendance.manage")
    code = data.code.strip().upper()
    if db.scalar(select(CostCenter).where(CostCenter.company_id == data.company_id, CostCenter.code == code)):
        raise HTTPException(409, "Cost-center code already exists")
    if data.parent_id and not db.scalar(select(CostCenter.id).where(
        CostCenter.id == data.parent_id, CostCenter.company_id == data.company_id,
    )):
        raise HTTPException(422, "Parent cost center does not belong to this company")
    row = CostCenter(
        company_id=data.company_id, code=code, name_ar=data.name_ar.strip(),
        name_en=(data.name_en or data.name_ar).strip(), parent_id=data.parent_id, active=True,
    )
    db.add(row); db.flush()
    write_audit(db, action="HR_COST_CENTER_CREATED", entity_type="COST_CENTER", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "name_ar": row.name_ar, "parent_id": row.parent_id})
    db.commit(); db.refresh(row)
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "active": row.active}


@router.get("/companies/{company_id}/branches")
def branches(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "masterdata.read")
    rows = db.scalars(select(Branch).where(Branch.company_id == company_id).order_by(Branch.code)).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "city_ar": row.city_ar,
            "city_en": row.city_en,
            "active": row.active,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "geofence_radius_m": row.geofence_radius_m,
        }
        for row in rows
    ]


@router.get("/companies/{company_id}/cost-centers")
def cost_centers(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "masterdata.read")
    rows = db.scalars(select(CostCenter).where(CostCenter.company_id == company_id).order_by(CostCenter.code)).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "parent_id": row.parent_id,
            "active": row.active,
        }
        for row in rows
    ]


@router.get("/companies/{company_id}/fiscal-years")
def fiscal_years(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_company_access(db, user, company_id)
    rows = db.scalars(select(FiscalYear).where(FiscalYear.company_id == company_id).order_by(FiscalYear.start_date.desc())).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/fiscal-years/{year_id}/periods")
def periods(year_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fiscal_year = db.get(FiscalYear, year_id)
    if not fiscal_year:
        return []
    ensure_company_access(db, user, fiscal_year.company_id)
    rows = db.scalars(select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == year_id).order_by(FiscalPeriod.number)).all()
    return [
        {
            "id": row.id,
            "number": row.number,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/companies/{company_id}/chart-of-accounts")
def chart_of_accounts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "masterdata.read")
    rows = db.scalars(select(Account).where(Account.company_id == company_id).order_by(Account.code)).all()
    parent_codes = {row.id: row.code for row in rows}
    return [
        {
            "id": row.id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "type": row.account_type,
            "statement_group": row.statement_group,
            "level": row.level,
            "parent": parent_codes.get(row.parent_id),
            "is_postable": row.is_postable,
            "is_cash": row.is_cash,
            "active": row.active,
        }
        for row in rows
    ]


@router.get("/companies/{company_id}/foundation-summary")
def foundation_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_company_access(db, user, company_id)
    fy = db.scalar(
        select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.status == "OPEN").order_by(FiscalYear.start_date.desc())
    )
    open_period = None
    if fy:
        open_period = db.scalar(
            select(FiscalPeriod.number)
            .where(FiscalPeriod.fiscal_year_id == fy.id, FiscalPeriod.status == "OPEN")
            .order_by(FiscalPeriod.number)
        )
    return {
        "company_id": company_id,
        "branches": db.scalar(select(func.count(Branch.id)).where(Branch.company_id == company_id)),
        "cost_centers": db.scalar(select(func.count(CostCenter.id)).where(CostCenter.company_id == company_id)),
        "fiscal_year": fy.name if fy else None,
        "open_period": open_period,
        "accounts": db.scalar(select(func.count(Account.id)).where(Account.company_id == company_id)),
        "audit_events": db.scalar(select(func.count(AuditLog.id)).where(AuditLog.company_id == company_id)),
        "persistence": "DATABASE",
    }
