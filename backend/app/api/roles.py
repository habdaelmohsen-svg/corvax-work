from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Role, User, UserCompanyRole

router = APIRouter(prefix="/roles", tags=["roles & permissions"])


@router.get("")
def list_roles(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    memberships = db.scalars(select(UserCompanyRole).options(selectinload(UserCompanyRole.role)).where(UserCompanyRole.user_id == current.id)).all()
    is_super_admin = any(m.role and m.role.code == "SUPER_ADMIN" for m in memberships)
    query = select(Role).options(selectinload(Role.permissions)).order_by(Role.code)
    if not is_super_admin:
        query = query.where(Role.code != "SUPER_ADMIN")
    roles = db.scalars(query).all()
    return [
        {
            "code": role.code,
            "name_ar": role.name_ar,
            "name_en": role.name_en,
            "permissions": sorted(permission.code for permission in role.permissions),
        }
        for role in roles
    ]
