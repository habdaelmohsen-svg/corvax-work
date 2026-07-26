from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Company, User, UserCompanyRole
from app.schemas.company import CompanyOut

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyOut])
def list_companies(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[CompanyOut]:
    company_ids = select(UserCompanyRole.company_id).where(UserCompanyRole.user_id == user.id)
    rows = db.scalars(select(Company).where(Company.id.in_(company_ids), Company.active.is_(True)).order_by(Company.id)).all()
    return [
        CompanyOut(
            id=row.id,
            code=row.code,
            name_ar=row.name_ar,
            name_en=row.name_en,
            currency=row.currency,
            logo_url=row.logo_url,
            primary_color=row.primary_color,
        )
        for row in rows
    ]
