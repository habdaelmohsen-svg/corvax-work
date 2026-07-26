"""CORVAX RC27.4 H13 - central attachments API.

Any document anywhere in the platform can carry files: contracts, progress
certificates, sales/purchase invoices, receipts, payment vouchers, project costs.

Storage is hybrid:
  * DB       - bytes stored inline. Works immediately on Render (no object storage
               needed) and is right for scans and small PDFs.
  * EXTERNAL - the caller uploads to S3/R2 itself and registers the URL here.

A size guard keeps large files out of the database.
"""
from __future__ import annotations

import base64
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import User
from app.models.cip_projects import Attachment
from app.services.audit import write_audit

router = APIRouter(prefix="/attachments", tags=["attachments"])

# Keep inline database storage sane. Bigger files should go to object storage.
MAX_DB_BYTES = 2 * 1024 * 1024  # 2 MB

ALLOWED_ENTITY_TYPES = {
    "CIP_PROJECT", "CIP_CONTRACT", "CIP_CERTIFICATE", "CIP_COST", "CIP_PAYMENT",
    "SALES_INVOICE", "PURCHASE_INVOICE", "RECEIPT", "PAYMENT", "JOURNAL_ENTRY",
    "FIXED_ASSET", "LEGAL_CONTRACT", "MAINTENANCE_WORK_ORDER", "COMMISSION_ACCRUAL",
    "INBOUND_SHIPMENT", "EMPLOYEE", "OTHER",
}



# ---------------------------------------------------------------- upload guards
# AUDIT H-04: uploads had no MIME allowlist, no content sniffing, unrestricted
# external URLs and weak filename handling.
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/msword",
}

_MAGIC_PREFIXES = {
    "application/pdf": [b"%PDF-"],
    "image/jpeg": [bytes([0xFF, 0xD8, 0xFF])],
    "image/png": [bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])],
    "image/webp": [b"RIFF"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [b"PK"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [b"PK"],
    "application/vnd.ms-excel": [bytes([0xD0, 0xCF, 0x11, 0xE0]), b"PK"],
    "application/msword": [bytes([0xD0, 0xCF, 0x11, 0xE0])],
}

_DANGEROUS_PREFIXES = [
    b"MZ",
    bytes([0x7F]) + b"ELF",
    b"#!",
    bytes([0xCA, 0xFE, 0xBA, 0xBE]),
]


def _safe_file_name(raw: str) -> str:
    """Strip any path component and keep a conservative character set."""
    import re

    name = raw.replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._\- ]+", "_", name)
    name = name.lstrip(".") or "file"
    return name[:200]


def _guard_content(content_type: str, raw: bytes) -> None:
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Unsupported content type for upload")
    head = raw[:16]
    for bad in _DANGEROUS_PREFIXES:
        if head.startswith(bad):
            raise HTTPException(415, "Executable content is not accepted")
    expected = _MAGIC_PREFIXES.get(declared)
    if expected and not any(head.startswith(prefix) for prefix in expected):
        raise HTTPException(415, "File content does not match the declared type")


def _guard_external_url(url: str) -> str:
    """Only allow https object-storage style URLs (audit H-04)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(422, "external_url must be an https URL")
    host = parsed.netloc.lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"} or host.endswith(".local"):
        raise HTTPException(422, "external_url may not point at an internal host")
    return url


class AttachmentIn(BaseModel):
    company_id: int
    entity_type: str
    entity_id: int
    file_name: str = Field(min_length=1, max_length=300)
    content_type: str = "application/octet-stream"
    content_base64: str | None = None   # for storage_kind=DB
    external_url: str | None = None     # for storage_kind=EXTERNAL
    description_ar: str | None = None
    description_en: str | None = None


@router.post("", status_code=201)
def upload_attachment(data: AttachmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "attachments.manage")
    entity_type = data.entity_type.upper()
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(422, f"Unsupported entity_type. Allowed: {sorted(ALLOWED_ENTITY_TYPES)}")
    if not data.content_base64 and not data.external_url:
        raise HTTPException(422, "Provide content_base64 (DB storage) or external_url (object storage)")

    if data.content_base64:
        try:
            raw = base64.b64decode(data.content_base64, validate=True)
        except Exception:
            raise HTTPException(422, "content_base64 is not valid base64")
        if len(raw) == 0:
            raise HTTPException(422, "Empty file")
        _guard_content(data.content_type, raw)
        if len(raw) > MAX_DB_BYTES:
            raise HTTPException(413, f"File too large for database storage ({len(raw)} bytes > {MAX_DB_BYTES}). Upload to object storage and register external_url instead.")
        att = Attachment(
            company_id=data.company_id, entity_type=entity_type, entity_id=data.entity_id,
            file_name=_safe_file_name(data.file_name), content_type=data.content_type, size_bytes=len(raw),
            storage_kind="DB", content=raw, checksum_sha256=hashlib.sha256(raw).hexdigest(),
            description_ar=data.description_ar, description_en=data.description_en,
            uploaded_by=user.id,
        )
    else:
        att = Attachment(
            company_id=data.company_id, entity_type=entity_type, entity_id=data.entity_id,
            file_name=_safe_file_name(data.file_name), content_type=data.content_type, size_bytes=0,
            storage_kind="EXTERNAL", external_url=_guard_external_url(data.external_url),
            description_ar=data.description_ar, description_en=data.description_en,
            uploaded_by=user.id,
        )
    db.add(att); db.flush()
    write_audit(db, action="ATTACHMENT_UPLOADED", entity_type="ATTACHMENT", entity_id=att.id, user_id=user.id, company_id=data.company_id, after={"file": att.file_name, "entity": f"{entity_type}:{data.entity_id}"})
    db.commit()
    return {"id": att.id, "file_name": att.file_name, "size_bytes": att.size_bytes,
            "storage_kind": att.storage_kind, "checksum_sha256": att.checksum_sha256}


@router.get("")
def list_attachments(company_id: int, entity_type: str = Query(...), entity_id: int = Query(...),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attachments.read")
    rows = db.scalars(select(Attachment).where(
        Attachment.company_id == company_id,
        Attachment.entity_type == entity_type.upper(),
        Attachment.entity_id == entity_id,
    ).order_by(Attachment.id.desc())).all()
    return [{"id": r.id, "file_name": r.file_name, "content_type": r.content_type,
             "size_bytes": r.size_bytes, "storage_kind": r.storage_kind,
             "external_url": r.external_url, "description_ar": r.description_ar,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attachments.read")
    att = db.scalar(select(Attachment).where(Attachment.id == attachment_id, Attachment.company_id == company_id))
    if not att:
        raise HTTPException(404, "Attachment not found")
    if att.storage_kind == "EXTERNAL":
        return {"redirect_url": att.external_url, "file_name": att.file_name}
    nosniff = {
        "Content-Disposition": f'attachment; filename="{att.file_name}"',
        # AUDIT H-04: never let a browser render or sniff an upload.
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    }
    return Response(
        content=att.content,
        media_type=att.content_type,
        headers=nosniff,
    )


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attachments.manage")
    att = db.scalar(select(Attachment).where(Attachment.id == attachment_id, Attachment.company_id == company_id))
    if not att:
        raise HTTPException(404, "Attachment not found")
    write_audit(db, action="ATTACHMENT_DELETED", entity_type="ATTACHMENT", entity_id=att.id, user_id=user.id, company_id=company_id, before={"file": att.file_name})
    db.delete(att); db.commit()
    return {"deleted": True, "id": attachment_id}


@router.get("/summary")
def attachments_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "attachments.read")
    total = db.scalar(select(func.count(Attachment.id)).where(Attachment.company_id == company_id)) or 0
    db_bytes = db.scalar(select(func.coalesce(func.sum(Attachment.size_bytes), 0)).where(
        Attachment.company_id == company_id, Attachment.storage_kind == "DB")) or 0
    external = db.scalar(select(func.count(Attachment.id)).where(
        Attachment.company_id == company_id, Attachment.storage_kind == "EXTERNAL")) or 0
    return {"total_attachments": total, "database_bytes": int(db_bytes),
            "database_mb": round(int(db_bytes) / (1024 * 1024), 2), "external_attachments": external,
            "max_db_file_bytes": MAX_DB_BYTES}
