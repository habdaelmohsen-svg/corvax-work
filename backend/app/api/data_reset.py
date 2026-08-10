"""Controlled data-reset workflows for CORVAX test environments.

The legacy company-scoped workflow removes only records explicitly registered
by a trusted seeder in ``demo_data_records``.  The separate UAT workflow is an
intentional, system-wide operational reset guarded by environment, role, exact
confirmation, dry run, signed authorization and audit controls.  Both workflows
are permanently unavailable in production.
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
from sqlalchemy import MetaData, Table, delete, func, literal, select, text, union_all
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import Base, get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Company, DemoDataRecord, Role, User, UserCompanyRole
from app.services.audit import write_audit

router = APIRouter(prefix="/data-reset", tags=["data reset"])

# Explicit allow-list and child-before-parent order.  A compromised/erroneous
# registry row can never turn an arbitrary table into a deletion target.
DEMO_DELETE_ORDER = ("journal_lines", "stock_movements", "journal_entries")
AUTHORIZATION_TTL_SECONDS = 10 * 60

# A full UAT reset is intentionally system-wide.  These are the only records
# retained because they are required to keep the installation reachable and
# structurally usable after operational/test data has been removed.  The set is
# FK-closed: no preserved table is allowed to depend on a reset table.
UAT_PRESERVED_TABLES = frozenset(
    {
        "companies",
        "branches",
        "accounts",
        "cost_centers",
        "fiscal_years",
        "fiscal_periods",
        "currencies",
        "permissions",
        "roles",
        "role_permissions",
        "users",
        "user_sessions",
        "user_company_roles",
        "user_company_role_branches",
        "password_history",
        "audit_logs",
        "backup_records",
        "legal_rule_versions",
        "sod_rules",
        "tax_codes",
    }
)
UAT_RESET_ENVIRONMENTS = frozenset({"development", "testing", "uat"})
UAT_CONFIRMATION_PHRASE = "تهيئة UAT كاملة - مسح جميع بيانات التشغيل"


class ResetIn(BaseModel):
    company_id: int
    confirmation: str = Field(min_length=1, max_length=300)
    dry_run: bool = True
    # Issued only by a successful, fresh dry run and required for real deletion.
    authorization_token: str | None = Field(default=None, max_length=4000)


class UATResetIn(BaseModel):
    confirmation: str = Field(min_length=1, max_length=300)
    dry_run: bool = True
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


def _uat_enabled() -> bool:
    return (
        settings.environment.strip().lower() in UAT_RESET_ENVIRONMENTS
        and bool(settings.allow_data_reset)
    )


def _ensure_uat_execution_enabled() -> None:
    environment = settings.environment.strip().lower()
    if environment == "production":
        raise HTTPException(403, "Full UAT reset is permanently disabled in production")
    if environment not in UAT_RESET_ENVIRONMENTS:
        raise HTTPException(403, "Full UAT reset requires ENVIRONMENT=uat")
    if not settings.allow_data_reset:
        raise HTTPException(403, "Full UAT reset is disabled; set ALLOW_DATA_RESET=true in UAT only")


def _ensure_super_admin(db: Session, user: User) -> None:
    role = db.scalar(
        select(Role.id)
        .join(UserCompanyRole, UserCompanyRole.role_id == Role.id)
        .where(UserCompanyRole.user_id == user.id, Role.code == "SUPER_ADMIN")
        .limit(1)
    )
    if role is None:
        raise HTTPException(403, "Only SUPER_ADMIN can execute a system-wide UAT reset")


def _uat_target_tables() -> list[Table]:
    existing = set(Base.metadata.tables)
    missing = UAT_PRESERVED_TABLES - existing
    if missing:
        raise RuntimeError(f"UAT preserved-table contract references missing tables: {sorted(missing)}")

    # TRUNCATE ... CASCADE must never discover a preserved child table.  Fail
    # closed if a future migration introduces such a dependency without first
    # updating the reset contract and its regression test.
    for table_name in UAT_PRESERVED_TABLES:
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            parent_name = foreign_key.column.table.name
            if parent_name not in UAT_PRESERVED_TABLES:
                raise RuntimeError(
                    f"Preserved table {table_name} depends on reset table {parent_name}"
                )

    return [
        Base.metadata.tables[name]
        for name in sorted(existing - UAT_PRESERVED_TABLES)
    ]


def _uat_snapshot(db: Session) -> dict[str, Any]:
    targets = _uat_target_tables()
    statements = [
        select(
            literal(table.name).label("table_name"),
            func.count().label("row_count"),
        ).select_from(table)
        for table in targets
    ]
    counts = {
        str(table_name): int(row_count or 0)
        for table_name, row_count in db.execute(union_all(*statements)).all()
    }
    nonempty = {name: count for name, count in counts.items() if count > 0}
    fingerprint = [[name, nonempty[name]] for name in sorted(nonempty)]
    digest = hashlib.sha256(
        json.dumps(fingerprint, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "tables": nonempty,
        "total_rows": sum(nonempty.values()),
        "tables_affected": len(nonempty),
        "target_table_count": len(targets),
        "digest": digest,
    }


def _execute_uat_truncate(db: Session, targets: list[Table]) -> None:
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        preparer = db.bind.dialect.identifier_preparer
        table_list = ", ".join(preparer.quote(table.name) for table in targets)
        db.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
        return

    if dialect == "sqlite":
        # SQLite cannot TRUNCATE, but it can defer every FK until the enclosing
        # transaction commits.  Because the preserved-table set is FK-closed,
        # the database is consistent again once all reset tables are empty.
        db.execute(text("PRAGMA defer_foreign_keys = ON"))
        for table in targets:
            db.execute(delete(table))
        return

    # Development fallback.  Production/UAT deployments use PostgreSQL and the
    # regression gate uses SQLite; other engines must prove their FK behaviour.
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in UAT_PRESERVED_TABLES:
            db.execute(delete(table))


@router.get("/uat-preview")
def preview_uat_reset(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview a system-wide operational-data purge for a controlled UAT environment."""
    _ensure_super_admin(db, user)
    snapshot = _uat_snapshot(db)
    company_count = int(db.scalar(select(func.count()).select_from(Company)) or 0)
    user_count = int(db.scalar(select(func.count()).select_from(User)) or 0)
    return {
        "scope": "SYSTEM_WIDE_UAT",
        "confirmation_phrase": UAT_CONFIRMATION_PHRASE,
        "total_rows": snapshot["total_rows"],
        "tables": snapshot["tables"],
        "tables_affected": snapshot["tables_affected"],
        "target_table_count": snapshot["target_table_count"],
        "enabled": _uat_enabled(),
        "environment": settings.environment,
        "production_blocked": settings.environment.strip().lower() == "production",
        "preserved": {
            "companies": company_count,
            "users": user_count,
            "table_count": len(UAT_PRESERVED_TABLES),
            "tables": sorted(UAT_PRESERVED_TABLES),
        },
        "note_ar": (
            "سيتم مسح جميع بيانات التشغيل والتجربة في كل الشركات، بما فيها الحركات "
            "والعملاء والموردون والأصناف والمخزون والموظفون. ستبقى بنية الدخول "
            "والشركات والفروع ودليل الحسابات والصلاحيات والفترات وسجل التدقيق."
        ),
        "note_en": (
            "All operational and test data across every company will be removed, including "
            "transactions, parties, items, inventory and employees. Access, company structure, "
            "the chart of accounts, permissions, fiscal periods and audit history are retained."
        ),
    }


@router.post("/uat-execute")
def execute_uat_reset(
    data: UATResetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dry-run or execute an all-company operational reset in an explicit UAT environment."""
    _ensure_super_admin(db, user)
    _ensure_uat_execution_enabled()
    if data.confirmation != UAT_CONFIRMATION_PHRASE:
        raise HTTPException(
            422,
            {
                "message_ar": f"عبارة التأكيد غير مطابقة. اكتب بالضبط: {UAT_CONFIRMATION_PHRASE}",
                "message_en": f"Confirmation does not match. Type exactly: {UAT_CONFIRMATION_PHRASE}",
            },
        )

    snapshot = _uat_snapshot(db)
    if data.dry_run:
        authorization_token = None
        if snapshot["total_rows"]:
            now = int(time.time())
            authorization_token = _sign_authorization(
                {
                    "uid": user.id,
                    "cid": 0,
                    "mode": "SYSTEM_WIDE_UAT",
                    "digest": snapshot["digest"],
                    "iat": now,
                    "exp": now + AUTHORIZATION_TTL_SECONDS,
                }
            )
        write_audit(
            db,
            action="UAT_OPERATIONAL_RESET_DRY_RUN",
            entity_type="SYSTEM",
            entity_id="ALL_COMPANIES",
            user_id=user.id,
            after={
                "rows_to_delete": snapshot["total_rows"],
                "tables_affected": snapshot["tables_affected"],
                "snapshot_digest": snapshot["digest"],
            },
        )
        db.commit()
        return {
            "dry_run": True,
            "scope": "SYSTEM_WIDE_UAT",
            "rows_deleted": 0,
            "rows_that_would_be_deleted": snapshot["total_rows"],
            "tables_affected": snapshot["tables_affected"],
            "detail": snapshot["tables"],
            "authorization_token": authorization_token,
            "authorization_expires_in_seconds": (
                AUTHORIZATION_TTL_SECONDS if authorization_token else 0
            ),
            "message_ar": (
                f"فحص آمن ناجح: سيُحذف {snapshot['total_rows']} صف تشغيل وتجربة "
                f"من {snapshot['tables_affected']} جدولًا في جميع الشركات."
            ),
            "message_en": (
                f"Safe dry run passed: {snapshot['total_rows']} operational/test rows "
                f"would be removed from {snapshot['tables_affected']} tables across all companies."
            ),
        }

    _verify_authorization(
        data.authorization_token,
        user_id=user.id,
        company_id=0,
        snapshot_digest=snapshot["digest"],
    )
    if not snapshot["total_rows"]:
        raise HTTPException(409, "No operational UAT data remains to delete")

    try:
        targets = _uat_target_tables()
        _execute_uat_truncate(db, targets)
        write_audit(
            db,
            action="UAT_OPERATIONAL_RESET_COMPLETED",
            entity_type="SYSTEM",
            entity_id="ALL_COMPANIES",
            user_id=user.id,
            after={
                "rows_deleted": snapshot["total_rows"],
                "tables_affected": snapshot["tables_affected"],
                "snapshot_digest": snapshot["digest"],
                "preserved_tables": sorted(UAT_PRESERVED_TABLES),
            },
        )
        db.commit()
    except (IntegrityError, SQLAlchemyError, RuntimeError) as exc:
        db.rollback()
        raise HTTPException(
            409,
            "UAT data changed or the preserved-table contract failed; nothing was deleted",
        ) from exc

    return {
        "dry_run": False,
        "scope": "SYSTEM_WIDE_UAT",
        "rows_deleted": snapshot["total_rows"],
        "tables_affected": snapshot["tables_affected"],
        "detail": snapshot["tables"],
        "message_ar": (
            f"تمت تهيئة UAT: حُذف {snapshot['total_rows']} صف من بيانات التشغيل والتجربة "
            "في جميع الشركات، مع الحفاظ على الدخول والشركات ودليل الحسابات والصلاحيات وسجل التدقيق."
        ),
        "message_en": (
            f"UAT reset completed: {snapshot['total_rows']} operational/test rows were removed "
            "across all companies while access, company structure, the chart of accounts, "
            "permissions and audit history were retained."
        ),
    }
