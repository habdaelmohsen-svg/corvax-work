from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import FiscalPeriod, FiscalYear, JournalEntry, JournalLine, JournalSequence


def ensure_open_period(db: Session, company_id: int, posting_date: date) -> None:
    period = db.scalar(
        select(FiscalPeriod)
        .join(FiscalYear)
        .where(
            FiscalYear.company_id == company_id,
            FiscalPeriod.start_date <= posting_date,
            FiscalPeriod.end_date >= posting_date,
        )
    )
    if not period or period.status != "OPEN":
        raise HTTPException(422, f"Posting period is not open: {period.status if period else 'NOT_FOUND'}")


def _existing_sequence_floor(db: Session, company_id: int, year: int) -> int:
    """Return a safe floor when upgrading a database that predates sequences."""
    numbers = db.scalars(
        select(JournalEntry.number).where(
            JournalEntry.company_id == company_id,
            func.extract("year", JournalEntry.entry_date) == year,
        )
    ).all()
    maximum = 0
    for number in numbers:
        try:
            maximum = max(maximum, int(str(number).rsplit("-", 1)[-1]))
        except (TypeError, ValueError):
            continue
    return maximum


def next_journal_number(db: Session, company_id: int, posting_date: date) -> str:
    """Allocate a race-safe journal number per company and fiscal year.

    PostgreSQL and SQLite use a single atomic UPSERT ... RETURNING statement. Other
    dialects use a row lock. This removes the count-then-insert race identified by the
    independent RC10 audit.
    """
    year = posting_date.year
    floor = _existing_sequence_floor(db, company_id, year)
    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        statement = (
            pg_insert(JournalSequence)
            .values(company_id=company_id, fiscal_year=year, last_number=floor + 1, updated_at=utc_now())
            .on_conflict_do_update(
                index_elements=[JournalSequence.company_id, JournalSequence.fiscal_year],
                set_={
                    # Self-healing (H16): never fall behind the numbers already used.
                    "last_number": func.greatest(JournalSequence.last_number + 1, floor + 1),
                    "updated_at": utc_now(),
                },
            )
            .returning(JournalSequence.last_number)
        )
        sequence = db.execute(statement).scalar_one()
    elif dialect == "sqlite":
        statement = (
            sqlite_insert(JournalSequence)
            .values(company_id=company_id, fiscal_year=year, last_number=floor + 1, updated_at=utc_now())
            .on_conflict_do_update(
                index_elements=[JournalSequence.company_id, JournalSequence.fiscal_year],
                set_={
                    # Self-healing (H16): SQLite max(a, b) is the scalar maximum.
                    "last_number": func.max(JournalSequence.last_number + 1, floor + 1),
                    "updated_at": utc_now(),
                },
            )
            .returning(JournalSequence.last_number)
        )
        sequence = db.execute(statement).scalar_one()
    else:  # pragma: no cover - supported production dialects are PostgreSQL/SQLite
        row = db.scalar(
            select(JournalSequence)
            .where(JournalSequence.company_id == company_id, JournalSequence.fiscal_year == year)
            .with_for_update()
        )
        if row is None:
            row = JournalSequence(company_id=company_id, fiscal_year=year, last_number=floor)
            db.add(row)
            db.flush()
        # Self-healing (H16): never fall behind numbers already present.
        row.last_number = max(int(row.last_number) + 1, floor + 1)
        row.updated_at = utc_now()
        sequence = row.last_number
    return f"JV-{company_id}-{year}-{int(sequence):06d}"


def create_posted_journal(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    posting_date: date,
    reference: str,
    description: str,
    lines: list[dict],
    cash_flow_activity: str | None = None,
    cash_flow_kind: str | None = None,
) -> JournalEntry:
    ensure_open_period(db, company_id, posting_date)
    total_debit = sum((Decimal(str(line.get("debit", 0))) for line in lines), Decimal("0"))
    total_credit = sum((Decimal(str(line.get("credit", 0))) for line in lines), Decimal("0"))
    if total_debit <= 0 or total_debit != total_credit:
        raise HTTPException(422, "System journal is not balanced")
    now = utc_now()
    entry = JournalEntry(
        company_id=company_id,
        number=next_journal_number(db, company_id, posting_date),
        entry_date=posting_date,
        reference=reference,
        description=description,
        status="POSTED",
        cash_flow_activity=cash_flow_activity,
        cash_flow_kind=cash_flow_kind,
        total_debit=total_debit,
        total_credit=total_credit,
        created_by=user_id,
        approved_by=user_id,
        posted_by=user_id,
        created_at=now,
        submitted_at=now,
        approved_at=now,
        posted_at=now,
    )
    for line in lines:
        entry.lines.append(
            JournalLine(
                account_id=line["account_id"],
                description=line.get("description") or description,
                debit=Decimal(str(line.get("debit", 0))),
                credit=Decimal(str(line.get("credit", 0))),
                cost_center_id=line.get("cost_center_id"),
                branch_id=line.get("branch_id"),
            )
        )
    db.add(entry)
    db.flush()
    return entry
