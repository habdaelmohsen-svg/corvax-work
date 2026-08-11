from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_company_access, ensure_permission, get_current_user
from app.models import Account, AuditLog, Branch, CostCenter, FiscalPeriod, FiscalYear, User

router = APIRouter(prefix="/enterprise", tags=["enterprise foundation"])


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
