"""UAT-only clean-slate reset for CORVAX business data.

This is intentionally separate from the narrow Demo registry purge.  It removes
all business/master/transaction rows so the owner can start a fresh UAT cycle,
while preserving the platform foundation needed to sign in and keep working.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import Base, get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Role, User, UserCompanyRole
from app.services.audit import write_audit

router = APIRouter(prefix="/uat-reset", tags=["UAT reset"])

CONFIRMATION_PHRASE = "تهيئة UAT كاملة - مسح جميع بيانات التشغيل"
AUTHORIZATION_TTL_SECONDS = 10 * 60

# These rows are the minimum viable platform foundation.  Everything else in
# SQLAlchemy metadata is business/UAT data and is removed.  The runtime check in
# _classified_tables refuses execution if a protected table points to a target;
# that prevents TRUNCATE from cascading back into the foundation.
PROTECTED_FOUNDATION_TABLES = frozenset(
    {
        "companies",
        "branches",
        "cost_centers",
        "accounts",
        "fiscal_years",
        "fiscal_periods",
        "permissions",
        "roles",
        "role_permissions",
        "users",
        "user_company_roles",
        "user_company_role_branches",
        "password_history",
        "user_sessions",
        "audit_logs",
        "backup_records",
        "currencies",
        "tax_codes",
        "legal_rule_versions",
        "journal_sequences",
        "financial_statement_mappings",
        "corporate_finance_configs",
        "sod_rules",
    }
)


class UatResetIn(BaseModel):
    company_id: int
    confirmation: str = Field(min_length=1, max_length=300)
    backup_acknowledged: bool = False
    dry_run: bool = True
    authorization_token: str | None = Field(default=None, max_length=4000)


def _enabled() -> bool:
    return settings.environment.strip().lower() in {"uat", "testing"} and bool(
        settings.allow_data_reset
    )


def _ensure_enabled() -> None:
    environment = settings.environment.strip().lower()
    if environment not in {"uat", "testing"}:
        raise HTTPException(403, "Full data reset is available only in UAT")
    if not settings.allow_data_reset:
        raise HTTPException(403, "Set ALLOW_DATA_RESET=true temporarily in UAT")


def _ensure_system_admin(db: Session, user: User, company_id: int) -> None:
    ensure_permission(db, user, company_id, "data.reset")
    membership = db.scalar(
        select(UserCompanyRole.id)
        .join(Role, Role.id == UserCompanyRole.role_id)
        .where(
            UserCompanyRole.user_id == user.id,
            UserCompanyRole.company_id == company_id,
            Role.code == "SUPER_ADMIN",
        )
    )
    if membership is None:
        raise HTTPException(403, "Only a System Administrator can reset UAT data")


def _classified_tables() -> tuple[list[str], list[str]]:
    existing = set(Base.metadata.tables)
    missing = PROTECTED_FOUNDATION_TABLES - existing
    if missing:
        raise HTTPException(
            503,
            f"UAT reset policy does not match the schema; missing: {sorted(missing)}",
        )
    targets = existing - PROTECTED_FOUNDATION_TABLES
    # A protected table must never depend on a target.  PostgreSQL TRUNCATE is
    # deliberately RESTRICT (not CASCADE), and this preflight makes the boundary
    # visible before any destructive statement is attempted.
    unsafe: list[str] = []
    for table_name in sorted(PROTECTED_FOUNDATION_TABLES):
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            parent_name = foreign_key.column.table.name
            if parent_name in targets:
                unsafe.append(f"{table_name}.{foreign_key.parent.name}->{parent_name}")
    if unsafe:
        raise HTTPException(503, {"message": "Unsafe UAT reset classification", "links": unsafe})
    return sorted(targets), sorted(PROTECTED_FOUNDATION_TABLES)


def _table_snapshot(db: Session) -> dict[str, Any]:
    targets, protected = _classified_tables()
    counts: dict[str, int] = {}
    fingerprint: list[list[Any]] = []
    for table_name in targets:
        table = Base.metadata.tables[table_name]
        count = int(db.scalar(select(func.count()).select_from(table)) or 0)
        if count:
            counts[table_name] = count
        max_id: Any = None
        if "id" in table.c and count:
            max_id = db.scalar(select(func.max(table.c.id)))
        fingerprint.append([table_name, count, str(max_id) if max_id is not None else None])
    digest = hashlib.sha256(
        json.dumps(fingerprint, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "tables": counts,
        "total_rows": sum(counts.values()),
        "target_table_count": len(targets),
        "protected": protected,
        "digest": digest,
    }


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _sign(payload: dict[str, Any]) -> str:
    body = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def _verify(token: str | None, *, user_id: int, company_id: int, digest: str) -> None:
    if not token or "." not in token:
        raise HTTPException(428, "Run the safe preview before deleting")
    try:
        body, supplied = token.split(".", 1)
        expected = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(supplied), expected):
            raise ValueError("signature")
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) < int(time.time()):
            raise HTTPException(428, "Preview authorization expired; run it again")
        if int(payload["uid"]) != user_id or int(payload["cid"]) != company_id:
            raise HTTPException(403, "Preview authorization belongs to another user or company")
        if not hmac.compare_digest(str(payload["digest"]), digest):
            raise HTTPException(409, "UAT data changed after preview; run it again")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(428, "Invalid preview authorization; run it again") from exc


def _delete_business_rows(db: Session, targets: list[str]) -> None:
    dialect = db.bind.dialect.name
    quote = db.bind.dialect.identifier_preparer.quote
    if dialect == "postgresql":
        names = ", ".join(quote(name) for name in targets)
        db.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY RESTRICT"))
        return
    if dialect == "sqlite":
        db.execute(text("PRAGMA defer_foreign_keys = ON"))
    target_set = set(targets)
    ordered = [table.name for table in reversed(Base.metadata.sorted_tables) if table.name in target_set]
    for table_name in ordered:
        db.execute(delete(Base.metadata.tables[table_name]))


@router.get("/preview")
def preview_uat_reset(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_system_admin(db, user, company_id)
    snapshot = _table_snapshot(db)
    return {
        "scope": "ALL_COMPANIES_BUSINESS_DATA",
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "enabled": _enabled(),
        "production_blocked": settings.environment.strip().lower() not in {"uat", "testing"},
        "total_rows": snapshot["total_rows"],
        "target_table_count": snapshot["target_table_count"],
        "tables": snapshot["tables"],
        "protected": snapshot["protected"],
        "note_ar": "سيتم حذف جميع بيانات الأعمال المضافة في كل الشركات. ستبقى الشركات والفروع وشجرة الحسابات والفترات والمستخدمون والصلاحيات والجلسة الحالية وسجل التدقيق.",
        "note_en": "All added business data across every company will be removed. Platform foundation and access remain.",
    }


@router.post("/execute")
def execute_uat_reset(
    data: UatResetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_system_admin(db, user, data.company_id)
    _ensure_enabled()
    if data.confirmation != CONFIRMATION_PHRASE:
        raise HTTPException(422, {"message_ar": f"اكتب العبارة حرفيًا: {CONFIRMATION_PHRASE}"})
    if not data.backup_acknowledged:
        raise HTTPException(422, {"message_ar": "يجب تأكيد أخذ نسخة احتياطية أو قبول عدم إمكانية الاسترجاع."})
    snapshot = _table_snapshot(db)
    if data.dry_run:
        now = int(time.time())
        token = _sign(
            {
                "uid": user.id,
                "cid": data.company_id,
                "digest": snapshot["digest"],
                "iat": now,
                "exp": now + AUTHORIZATION_TTL_SECONDS,
            }
        )
        write_audit(
            db,
            action="UAT_FULL_RESET_DRY_RUN",
            entity_type="SYSTEM",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            after={"rows": snapshot["total_rows"], "tables": len(snapshot["tables"]), "digest": snapshot["digest"]},
        )
        db.commit()
        return {
            "dry_run": True,
            "rows_that_would_be_deleted": snapshot["total_rows"],
            "tables_affected": len(snapshot["tables"]),
            "authorization_token": token,
            "authorization_expires_in_seconds": AUTHORIZATION_TTL_SECONDS,
            "message_ar": f"المعاينة ناجحة: سيتم حذف {snapshot['total_rows']} صفًا من {len(snapshot['tables'])} جدولًا.",
            "message_en": f"Preview passed: {snapshot['total_rows']} rows across {len(snapshot['tables'])} tables will be removed.",
        }
    _verify(
        data.authorization_token,
        user_id=user.id,
        company_id=data.company_id,
        digest=snapshot["digest"],
    )
    if snapshot["total_rows"] == 0:
        return {
            "dry_run": False,
            "rows_deleted": 0,
            "tables_affected": 0,
            "message_ar": "لا توجد بيانات أعمال مضافة؛ النظام جاهز للإدخال.",
            "message_en": "No added business data remains; the system is ready.",
        }
    targets, _ = _classified_tables()
    try:
        write_audit(
            db,
            action="UAT_FULL_RESET_STARTED",
            entity_type="SYSTEM",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            before={"rows": snapshot["total_rows"], "tables": len(snapshot["tables"]), "digest": snapshot["digest"]},
        )
        db.flush()
        _delete_business_rows(db, targets)
        write_audit(
            db,
            action="UAT_FULL_RESET_COMPLETED",
            entity_type="SYSTEM",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            after={"rows_deleted": snapshot["total_rows"], "tables_cleared": len(snapshot["tables"])},
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(409, "UAT reset failed atomically; no partial deletion was committed") from exc
    remaining = _table_snapshot(db)
    if remaining["total_rows"]:
        raise HTTPException(500, "Post-reset verification failed")
    return {
        "dry_run": False,
        "rows_deleted": snapshot["total_rows"],
        "tables_affected": len(snapshot["tables"]),
        "message_ar": "تم حذف جميع بيانات الأعمال المضافة بنجاح. يمكنك الآن إدخال البيانات شبه الحقيقية.",
        "message_en": "All added business data was removed. The system is ready for semi-real UAT data.",
    }
