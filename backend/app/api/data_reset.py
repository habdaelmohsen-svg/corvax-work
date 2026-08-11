"""Controlled removal of explicitly registered CORVAX demonstration records.

This endpoint never classifies a row as Demo from a name, reference, date,
creator, or environment.  A row is eligible only when a trusted seeding/demo
workflow recorded its exact table and primary key in ``demo_data_records``.
Unregistered rows are treated as real/manual data and cannot be deleted here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import MetaData, Table, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import Base, get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Company, DemoDataRecord, User
from app.services.audit import write_audit

router = APIRouter(prefix="/data-reset", tags=["data reset"])

# Explicit allow-list and child-before-parent order.  A compromised/erroneous
# registry row can never turn an arbitrary table into a deletion target.
DEMO_DELETE_ORDER = ("journal_lines", "stock_movements", "journal_entries")
AUTHORIZATION_TTL_SECONDS = 10 * 60


class ResetIn(BaseModel):
    company_id: int
    confirmation: str = Field(min_length=1, max_length=300)
    dry_run: bool = True
    # Issued only by a successful, fresh dry run and required for real deletion.
    authorization_token: str | None = Field(default=None, max_length=4000)


def _enabled() -> bool:
    return (
        settings.environment.strip().lower() != "production"
        and bool(settings.allow_data_reset)
    )


def _ensure_execution_enabled() -> None:
    if settings.environment.strip().lower() == "production":
        raise HTTPException(403, "Demo-data reset is permanently disabled in production")
    if not settings.allow_data_reset:
        raise HTTPException(
            403,
            "Demo-data reset is disabled. Enable ALLOW_DATA_RESET only in a non-production environment.",
        )


def _confirmation_phrase(company: Company) -> str:
    return f"حذف بيانات DEMO - {(company.name_ar or company.name_en).strip()}"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _sign_authorization(payload: dict[str, Any]) -> str:
    body = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{body}.{_b64encode(signature)}"


def _verify_authorization(
    token: str | None,
    *,
    user_id: int,
    company_id: int,
    snapshot_digest: str,
) -> None:
    if not token or "." not in token:
        raise HTTPException(428, "Run a successful dry run before deleting demo data")
    try:
        body, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.secret_key.encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64decode(supplied_signature), expected_signature):
            raise ValueError("signature")
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) < int(time.time()):
            raise HTTPException(428, "Dry-run authorization expired; run it again")
        if int(payload["uid"]) != user_id or int(payload["cid"]) != company_id:
            raise HTTPException(403, "Dry-run authorization belongs to another user or company")
        if not hmac.compare_digest(str(payload["digest"]), snapshot_digest):
            raise HTTPException(409, "Demo data changed after the dry run; run it again")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(428, "Invalid dry-run authorization; run it again") from exc


def _registered_rows(db: Session, company_id: int) -> dict[str, list[int]]:
    """Return only registered records that still exist in an allowed table."""
    existing_tables = set(Base.metadata.tables)
    result: dict[str, list[int]] = {}
    for table_name in DEMO_DELETE_ORDER:
        if table_name not in existing_tables:
            continue
        raw_ids = db.scalars(
            select(DemoDataRecord.record_id).where(
                DemoDataRecord.company_id == company_id,
                DemoDataRecord.table_name == table_name,
            )
        ).all()
        integer_ids = sorted({int(value) for value in raw_ids if str(value).isdigit()})
        if not integer_ids:
            continue
        table = Base.metadata.tables[table_name]
        actual = db.scalars(select(table.c.id).where(table.c.id.in_(integer_ids))).all()
        if actual:
            result[table_name] = sorted(int(value) for value in actual)
    return result


def _dependency_blockers(
    db: Session,
    registered: dict[str, list[int]],
) -> dict[str, int]:
    """Find unregistered rows that depend on a demo row.

    Such a dependency means that deleting the Demo row could either violate a
    foreign key or cascade into a real/manual row.  Both outcomes are blocked.
    """
    blockers: dict[str, set[str]] = defaultdict(set)
    registered_sets = {
        table_name: {str(value) for value in ids}
        for table_name, ids in registered.items()
    }
    for child_name, child in Base.metadata.tables.items():
        for foreign_key in child.foreign_keys:
            parent_name = foreign_key.column.table.name
            parent_ids = registered.get(parent_name)
            if not parent_ids:
                continue
            child_ids = db.execute(
                select(child.c.id).where(foreign_key.parent.in_(parent_ids))
                if "id" in child.c
                else select(foreign_key.parent).where(foreign_key.parent.in_(parent_ids))
            ).scalars().all()
            allowed_child_ids = registered_sets.get(child_name, set())
            for child_id in child_ids:
                if child_name not in DEMO_DELETE_ORDER or str(child_id) not in allowed_child_ids:
                    blockers[f"{child_name}.{foreign_key.parent.name}"].add(str(child_id))
    return {key: len(values) for key, values in sorted(blockers.items())}


def _preserved_unregistered_counts(
    db: Session,
    company_id: int,
    registered: dict[str, list[int]],
) -> dict[str, int]:
    """Counts shown to the operator as an explicit non-deletion guarantee."""
    entries = Base.metadata.tables["journal_entries"]
    lines = Base.metadata.tables["journal_lines"]
    company_entry_ids = select(entries.c.id).where(entries.c.company_id == company_id)
    total_entries = int(
        db.scalar(select(func.count()).select_from(entries).where(entries.c.company_id == company_id))
        or 0
    )
    total_lines = int(
        db.scalar(
            select(func.count()).select_from(lines).where(lines.c.journal_id.in_(company_entry_ids))
        )
        or 0
    )
    stock_movements = Base.metadata.tables["stock_movements"]
    total_stock_movements = int(
        db.scalar(
            select(func.count())
            .select_from(stock_movements)
            .where(stock_movements.c.company_id == company_id)
        )
        or 0
    )
    return {
        "journal_entries": max(
            0, total_entries - len(registered.get("journal_entries", []))
        ),
        "journal_lines": max(0, total_lines - len(registered.get("journal_lines", []))),
        "stock_movements": max(
            0,
            total_stock_movements - len(registered.get("stock_movements", [])),
        ),
    }


def _snapshot(db: Session, company_id: int) -> dict[str, Any]:
    registered = _registered_rows(db, company_id)
    registry_metadata = db.execute(
        select(
            DemoDataRecord.table_name,
            DemoDataRecord.record_id,
            DemoDataRecord.source,
            DemoDataRecord.created_at,
        )
        .where(
            DemoDataRecord.company_id == company_id,
            DemoDataRecord.table_name.in_(DEMO_DELETE_ORDER),
        )
        .order_by(DemoDataRecord.table_name, DemoDataRecord.record_id)
    ).all()
    # created_at/source prevent a previous token from authorizing a later demo
    # batch that happened to reuse the same integer primary keys.
    fingerprint = [
        [table_name, record_id, source, created_at.isoformat()]
        for table_name, record_id, source, created_at in registry_metadata
        if (
            table_name in registered
            and str(record_id).isdigit()
            and int(record_id) in registered[table_name]
        )
    ]
    digest = hashlib.sha256(
        json.dumps(fingerprint, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    blockers = _dependency_blockers(db, registered)
    preserved = _preserved_unregistered_counts(db, company_id, registered)
    return {
        "registered": registered,
        "tables": {name: len(ids) for name, ids in registered.items()},
        "total_rows": sum(len(ids) for ids in registered.values()),
        "preserved_unregistered": preserved,
        "preserved_unregistered_total": sum(preserved.values()),
        "blocking_dependencies": blockers,
        "digest": digest,
    }


def _company_or_404(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    return company


@router.get("/preview")
def preview_reset(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Show only explicitly registered Demo rows and real rows kept intact."""
    ensure_permission(db, user, company_id, "data.reset")
    company = _company_or_404(db, company_id)
    snapshot = _snapshot(db, company_id)
    return {
        "company_id": company_id,
        "company_name": company.name_ar,
        "confirmation_phrase": _confirmation_phrase(company),
        "total_rows": snapshot["total_rows"],
        "tables": snapshot["tables"],
        "preserved_unregistered": snapshot["preserved_unregistered"],
        "preserved_unregistered_total": snapshot["preserved_unregistered_total"],
        "blocking_dependencies": snapshot["blocking_dependencies"],
        "enabled": _enabled(),
        "production_blocked": settings.environment.strip().lower() == "production",
        "note_ar": (
            "سيُحذف فقط ما سجله النظام صراحةً كبيانات DEMO. "
            "كل صف يدوي أو حقيقي غير مسجل محفوظ ولا يدخل في عملية الحذف."
        ),
        "note_en": (
            "Only rows explicitly registered by CORVAX as Demo are eligible. "
            "Every unregistered manual or real row is preserved."
        ),
    }


@router.post("/execute")
def execute_reset(
    data: ResetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dry-run or atomically delete the registered Demo snapshot."""
    ensure_permission(db, user, data.company_id, "data.reset")
    _ensure_execution_enabled()
    company = _company_or_404(db, data.company_id)
    expected_confirmation = _confirmation_phrase(company)
    if data.confirmation != expected_confirmation:
        raise HTTPException(
            422,
            {
                "message_ar": f"عبارة التأكيد غير مطابقة. اكتب بالضبط: {expected_confirmation}",
                "message_en": f"Confirmation does not match. Type exactly: {expected_confirmation}",
            },
        )

    snapshot = _snapshot(db, data.company_id)
    if snapshot["blocking_dependencies"]:
        raise HTTPException(
            409,
            {
                "message_ar": "تعذر الحذف لأن بيانات غير تجريبية تعتمد على سجل Demo.",
                "message_en": "Deletion is blocked because unregistered data depends on a Demo record.",
                "dependencies": snapshot["blocking_dependencies"],
            },
        )

    if data.dry_run:
        authorization_token = None
        if snapshot["total_rows"]:
            now = int(time.time())
            authorization_token = _sign_authorization(
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
            action="DEMO_DATA_RESET_DRY_RUN",
            entity_type="COMPANY",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            after={
                "registered_demo_rows": snapshot["total_rows"],
                "manual_rows_preserved": snapshot["preserved_unregistered_total"],
                "snapshot_digest": snapshot["digest"],
            },
        )
        db.commit()
        return {
            "dry_run": True,
            "company_id": data.company_id,
            "company_name": company.name_ar,
            "tables_affected": len(snapshot["tables"]),
            "rows_deleted": 0,
            "rows_that_would_be_deleted": snapshot["total_rows"],
            "manual_rows_preserved": snapshot["preserved_unregistered_total"],
            "detail": snapshot["tables"],
            "authorization_token": authorization_token,
            "authorization_expires_in_seconds": (
                AUTHORIZATION_TTL_SECONDS if authorization_token else 0
            ),
            "message_ar": (
                f"فحص آمن: سيُحذف {snapshot['total_rows']} صف Demo مسجل فقط، "
                f"وسيُحفظ {snapshot['preserved_unregistered_total']} صف غير تجريبي."
            ),
            "message_en": (
                f"Safe dry run: {snapshot['total_rows']} registered Demo rows would be removed; "
                f"{snapshot['preserved_unregistered_total']} unregistered rows are preserved."
            ),
        }

    _verify_authorization(
        data.authorization_token,
        user_id=user.id,
        company_id=data.company_id,
        snapshot_digest=snapshot["digest"],
    )
    if not snapshot["total_rows"]:
        raise HTTPException(409, "No registered Demo data remains to delete")

    deleted: dict[str, int] = {}
    try:
        for table_name in DEMO_DELETE_ORDER:
            record_ids = snapshot["registered"].get(table_name, [])
            if not record_ids:
                continue
            table = Base.metadata.tables[table_name]
            result = db.execute(delete(table).where(table.c.id.in_(record_ids)))
            deleted_count = int(result.rowcount or 0)
            if deleted_count != len(record_ids):
                raise RuntimeError(
                    f"Demo snapshot changed while deleting {table_name}; transaction cancelled"
                )
            deleted[table_name] = deleted_count
        db.execute(
            delete(DemoDataRecord).where(
                DemoDataRecord.company_id == data.company_id,
                DemoDataRecord.table_name.in_(DEMO_DELETE_ORDER),
            )
        )
        write_audit(
            db,
            action="DEMO_DATA_RESET_COMPLETED",
            entity_type="COMPANY",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            after={
                "rows_deleted": sum(deleted.values()),
                "detail": deleted,
                "manual_rows_preserved": snapshot["preserved_unregistered_total"],
                "snapshot_digest": snapshot["digest"],
            },
        )
        db.commit()
    except (IntegrityError, RuntimeError) as exc:
        db.rollback()
        raise HTTPException(
            409,
            "Demo data changed or is referenced by preserved data; nothing was deleted",
        ) from exc

    total_deleted = sum(deleted.values())
    return {
        "dry_run": False,
        "company_id": data.company_id,
        "company_name": company.name_ar,
        "tables_affected": len(deleted),
        "rows_deleted": total_deleted,
        "rows_that_would_be_deleted": 0,
        "manual_rows_preserved": snapshot["preserved_unregistered_total"],
        "detail": deleted,
        "message_ar": (
            f"تم حذف {total_deleted} صف Demo مسجل فقط. "
            f"تم الحفاظ على {snapshot['preserved_unregistered_total']} صف غير تجريبي دون تغيير."
        ),
        "message_en": (
            f"Removed {total_deleted} registered Demo rows only. "
            f"{snapshot['preserved_unregistered_total']} unregistered rows were preserved unchanged."
        ),
    }
