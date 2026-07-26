from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import AuditLog


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))


def _hash_payload(*, company_id: int | None, sequence: int, previous_hash: str | None, user_id: int | None,
                  action: str, entity_type: str, entity_id: str, before_json: str | None,
                  after_json: str | None, created_at: datetime) -> str:
    payload = {
        "company_id": company_id,
        "sequence_number": sequence,
        "previous_hash": previous_hash or "GENESIS",
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_json": before_json,
        "after_json": after_json,
        "created_at": created_at.isoformat(timespec="microseconds"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | int,
    user_id: int | None,
    company_id: int | None = None,
    before: Any = None,
    after: Any = None,
) -> AuditLog:
    """Append a tamper-evident audit event.

    The database user used by CORVAX should be denied UPDATE/DELETE on audit_logs in
    production. The hash chain detects any row mutation, deletion or reordering.
    """
    scope = AuditLog.company_id.is_(None) if company_id is None else AuditLog.company_id == company_id

    # AUDIT H-05: two concurrent writers used to read the same tail and allocate the
    # same sequence number with the same previous_hash, forking the chain. On
    # PostgreSQL a transaction-scoped advisory lock now serialises allocation per
    # tenant, so the chain stays linear under load.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key1, :key2)"),
            {"key1": 918_273, "key2": int(company_id or 0)},
        )

    last = db.scalar(select(AuditLog).where(scope).order_by(AuditLog.sequence_number.desc().nullslast(), AuditLog.id.desc()).limit(1))
    max_seq = db.scalar(select(func.max(AuditLog.sequence_number)).where(scope)) or 0
    sequence = int(max_seq) + 1
    previous_hash = last.record_hash if last and last.record_hash else None
    created_at = utc_now()
    before_json = _json(before)
    after_json = _json(after)
    entity_id_text = str(entity_id)
    record_hash = _hash_payload(
        company_id=company_id,
        sequence=sequence,
        previous_hash=previous_hash,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id_text,
        before_json=before_json,
        after_json=after_json,
        created_at=created_at,
    )
    row = AuditLog(
        company_id=company_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id_text,
        before_json=before_json,
        after_json=after_json,
        sequence_number=sequence,
        previous_hash=previous_hash,
        record_hash=record_hash,
        created_at=created_at,
    )
    db.add(row)
    return row


def verify_audit_chain(db: Session, company_id: int | None) -> dict[str, Any]:
    scope = AuditLog.company_id.is_(None) if company_id is None else AuditLog.company_id == company_id
    rows = db.scalars(select(AuditLog).where(scope).order_by(AuditLog.sequence_number.asc().nullsfirst(), AuditLog.id.asc())).all()
    legacy = [r for r in rows if not r.record_hash or r.sequence_number is None]
    chained = [r for r in rows if r.record_hash and r.sequence_number is not None]
    previous_hash: str | None = None
    expected_sequence = 1
    failures: list[dict[str, Any]] = []
    for row in chained:
        if row.sequence_number != expected_sequence:
            failures.append({"id": row.id, "type": "SEQUENCE_GAP", "expected": expected_sequence, "actual": row.sequence_number})
            expected_sequence = row.sequence_number
        if row.previous_hash != previous_hash:
            failures.append({"id": row.id, "type": "PREVIOUS_HASH_MISMATCH"})
        expected_hash = _hash_payload(
            company_id=row.company_id,
            sequence=row.sequence_number,
            previous_hash=row.previous_hash,
            user_id=row.user_id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            before_json=row.before_json,
            after_json=row.after_json,
            created_at=row.created_at,
        )
        if expected_hash != row.record_hash:
            failures.append({"id": row.id, "type": "RECORD_HASH_MISMATCH"})
        previous_hash = row.record_hash
        expected_sequence += 1
    return {
        "company_id": company_id,
        "status": "VALID" if not failures else "INVALID",
        "verified_records": len(chained),
        "legacy_unhashed_records": len(legacy),
        "last_hash": previous_hash,
        "failures": failures,
    }
