import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Company, User, UserCompanyRole
from app.schemas.company import CompanyOut
from app.services.audit import write_audit

router = APIRouter(prefix="/companies", tags=["companies"])

MAX_COMPANY_LOGO_BYTES = 512 * 1024
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}


class CompanyLogoIn(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=50)
    content_base64: str = Field(min_length=1, max_length=750_000)


def _validate_logo(content_type: str, payload: bytes) -> None:
    if content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(422, "Company logo must be PNG, JPEG, or WEBP")
    if not payload or len(payload) > MAX_COMPANY_LOGO_BYTES:
        raise HTTPException(422, "Company logo must not exceed 512 KB")
    signatures = {
        "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": payload.startswith(b"\xff\xd8\xff"),
        "image/webp": payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
    }
    if not signatures[content_type]:
        raise HTTPException(422, "Company logo content does not match its file type")


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


@router.post("/{company_id}/logo", response_model=CompanyOut)
def upload_company_logo(
    company_id: int,
    data: CompanyLogoIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyOut:
    ensure_permission(db, user, company_id, "finance.reporting.manage")
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    content_type = data.content_type.lower().strip()
    try:
        payload = base64.b64decode(data.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Invalid base64 company logo")
    _validate_logo(content_type, payload)
    before = {"has_logo": bool(company.logo_url)}
    company.logo_url = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
    write_audit(
        db,
        action="COMPANY_LOGO_UPDATED",
        entity_type="COMPANY",
        entity_id=company.id,
        user_id=user.id,
        company_id=company.id,
        before=before,
        after={"has_logo": True, "file_name": data.file_name, "content_type": content_type, "bytes": len(payload)},
    )
    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company, from_attributes=True)
