from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    BankAccount, BankStatement, BankStatementLine, JournalEntry, JournalLine, User,
)
from app.services.audit import write_audit
from app.services.operations import money

router = APIRouter(prefix="/banking", tags=["bank reconciliation"])


class StatementLineIn(BaseModel):
    transaction_date: date
    reference: str | None = None
    description: str = Field(min_length=2, max_length=500)
    amount: Decimal = Field(gt=0)
    direction: str


class StatementIn(BaseModel):
    company_id: int
    bank_account_id: int
    statement_date: date
    opening_balance: Decimal
    closing_balance: Decimal
    lines: list[StatementLineIn] = Field(min_length=1)


def _statement_users(db: Session, rows: list[BankStatement]) -> dict[int, User]:
    user_ids = {
        user_id
        for row in rows
        for user_id in (row.created_by, row.matched_by, row.reconciled_by)
        if user_id is not None
    }
    if not user_ids:
        return {}
    return {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()}


def _user_out(row: User | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.id,
        "name_ar": row.name_ar,
        "name_en": row.name_en,
        "username": row.username,
    }


def _statement_number(row: BankStatement) -> str:
    return f"BANK-STMT-{row.company_id}-{row.id:06d}"


def _statement_out(row: BankStatement, users: dict[int, User]) -> dict:
    return {
        "id": row.id,
        "number": _statement_number(row),
        "company_id": row.company_id,
        "bank_account_id": row.bank_account_id,
        "bank_name": row.bank_account.bank_name_en,
        "statement_date": row.statement_date,
        "opening_balance": row.opening_balance,
        "closing_balance": row.closing_balance,
        "status": row.status,
        "created_by": row.created_by,
        "created_by_user": _user_out(users.get(row.created_by)),
        "matched_by": row.matched_by,
        "matched_by_user": _user_out(users.get(row.matched_by)) if row.matched_by else None,
        "matched_at": row.matched_at,
        "reconciled_by": row.reconciled_by,
        "reconciled_by_user": _user_out(users.get(row.reconciled_by)) if row.reconciled_by else None,
        "reconciled_at": row.reconciled_at,
        "lines": [
            {
                "id": line.id,
                "transaction_date": line.transaction_date,
                "reference": line.reference,
                "description": line.description,
                "amount": line.amount,
                "direction": line.direction,
                "status": line.status,
                "matched_journal_line_id": line.matched_journal_line_id,
            }
            for line in row.lines
        ],
    }


@router.get("/accounts")
def list_bank_accounts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(select(BankAccount).where(BankAccount.company_id == company_id, BankAccount.active.is_(True))).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name_ar": row.bank_name_ar,
            "name_en": row.bank_name_en,
            "iban": row.iban,
            "gl_account_code": row.gl_account.code,
        }
        for row in rows
    ]


@router.post("/statements", status_code=201)
def create_statement(data: StatementIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "bank.statement.prepare")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id))
    if not bank:
        raise HTTPException(404, "Bank account not found")
    if db.scalar(select(BankStatement).where(BankStatement.bank_account_id == bank.id, BankStatement.statement_date == data.statement_date)):
        raise HTTPException(409, "Statement already exists for this date")
    calculated = money(data.opening_balance)
    statement = BankStatement(
        company_id=data.company_id,
        bank_account_id=bank.id,
        statement_date=data.statement_date,
        opening_balance=money(data.opening_balance),
        closing_balance=money(data.closing_balance),
        status="DRAFT",
        created_by=user.id,
    )
    for source in data.lines:
        direction = source.direction.upper()
        if direction not in {"DEBIT", "CREDIT"}:
            raise HTTPException(422, "Direction must be DEBIT or CREDIT")
        amount = money(source.amount)
        calculated += amount if direction == "CREDIT" else -amount
        statement.lines.append(
            BankStatementLine(
                transaction_date=source.transaction_date,
                reference=source.reference,
                description=source.description,
                amount=amount,
                direction=direction,
                status="UNMATCHED",
            )
        )
    if money(calculated) != money(data.closing_balance):
        raise HTTPException(422, f"Statement does not add up. Calculated closing balance: {money(calculated)}")
    db.add(statement)
    db.flush()
    write_audit(
        db,
        action="BANK_STATEMENT_CREATED",
        entity_type="BANK_STATEMENT",
        entity_id=statement.id,
        user_id=user.id,
        company_id=data.company_id,
        after={"statement_date": str(data.statement_date), "closing_balance": str(statement.closing_balance)},
    )
    db.commit()
    db.refresh(statement)
    return _statement_out(statement, _statement_users(db, [statement]))


@router.get("/statements")
def list_statements(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(
        select(BankStatement)
        .where(BankStatement.company_id == company_id)
        .options(selectinload(BankStatement.lines))
        .order_by(BankStatement.statement_date.desc(), BankStatement.id.desc())
    ).all()
    users = _statement_users(db, rows)
    return [_statement_out(row, users) for row in rows]


@router.get("/statements/export.csv")
def export_statements(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(
        select(BankStatement)
        .where(BankStatement.company_id == company_id)
        .options(selectinload(BankStatement.lines))
        .order_by(BankStatement.statement_date, BankStatement.id)
    ).all()
    users = _statement_users(db, rows)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Statement number", "Bank code", "Bank name AR", "Bank name EN",
        "Statement date", "Opening balance", "Closing balance", "Line count", "Matched line count", "Status",
        "Created at", "Created by ID", "Created by name AR", "Created by name EN", "Created by username",
        "Matched at", "Matched by ID", "Matched by name AR", "Matched by name EN", "Matched by username",
        "Reconciled at", "Reconciled by ID", "Reconciled by name AR", "Reconciled by name EN", "Reconciled by username",
    ])
    for row in rows:
        creator = users.get(row.created_by)
        matcher = users.get(row.matched_by) if row.matched_by else None
        reconciler = users.get(row.reconciled_by) if row.reconciled_by else None
        writer.writerow([
            _statement_number(row), row.bank_account.code, row.bank_account.bank_name_ar, row.bank_account.bank_name_en,
            row.statement_date, row.opening_balance, row.closing_balance, len(row.lines),
            sum(1 for line in row.lines if line.status == "MATCHED"), row.status,
            row.created_at, row.created_by, creator.name_ar if creator else "", creator.name_en if creator else "", creator.username if creator else "",
            row.matched_at or "", row.matched_by or "", matcher.name_ar if matcher else "", matcher.name_en if matcher else "", matcher.username if matcher else "",
            row.reconciled_at or "", row.reconciled_by or "", reconciler.name_ar if reconciler else "", reconciler.name_en if reconciler else "", reconciler.username if reconciler else "",
        ])
    content = "\ufeff" + output.getvalue()
    filename = f"bank_statements_{company_id}.csv"
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/statements/{statement_id}/auto-match")
def auto_match(statement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    statement = db.scalar(
        select(BankStatement)
        .where(BankStatement.id == statement_id)
        .options(selectinload(BankStatement.lines))
    )
    if not statement:
        raise HTTPException(404, "Statement not found")
    permissions = ensure_permission(db, user, statement.company_id, "bank.statement.prepare")
    if statement.created_by == user.id and "*" not in permissions:
        raise HTTPException(409, "Maker-checker control: statement creator cannot complete reconciliation")
    if statement.status == "RECONCILED":
        raise HTTPException(409, "Statement is already reconciled")
    matched_ids = set(
        db.scalars(
            select(BankStatementLine.matched_journal_line_id).where(BankStatementLine.matched_journal_line_id.is_not(None))
        ).all()
    )
    matched = 0
    for line in statement.lines:
        if line.status == "MATCHED":
            continue
        start = line.transaction_date - timedelta(days=3)
        end = line.transaction_date + timedelta(days=3)
        debit_value = line.amount if line.direction == "CREDIT" else Decimal("0")
        credit_value = line.amount if line.direction == "DEBIT" else Decimal("0")
        candidates = db.scalars(
            select(JournalLine)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
            .where(
                JournalLine.account_id == statement.bank_account.gl_account_id,
                JournalEntry.company_id == statement.company_id,
                JournalEntry.status.in_(["POSTED", "REVERSED"]),
                JournalEntry.entry_date.between(start, end),
                JournalLine.debit == debit_value,
                JournalLine.credit == credit_value,
            )
            .order_by(JournalEntry.entry_date, JournalLine.id)
        ).all()
        candidate = next((row for row in candidates if row.id not in matched_ids), None)
        if candidate:
            line.matched_journal_line_id = candidate.id
            line.status = "MATCHED"
            matched_ids.add(candidate.id)
            matched += 1
    statement.status = "MATCHED" if all(line.status == "MATCHED" for line in statement.lines) else "PARTIAL"
    if matched:
        statement.matched_by = user.id
        statement.matched_at = utc_now()
    write_audit(
        db,
        action="BANK_STATEMENT_AUTO_MATCHED",
        entity_type="BANK_STATEMENT",
        entity_id=statement.id,
        user_id=user.id,
        company_id=statement.company_id,
        after={"matched_now": matched, "status": statement.status},
    )
    db.commit()
    return {"statement_id": statement.id, "matched_now": matched, "status": statement.status, "unmatched": sum(1 for line in statement.lines if line.status != "MATCHED")}


@router.post("/statements/{statement_id}/reconcile")
def reconcile(statement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    statement = db.scalar(
        select(BankStatement)
        .where(BankStatement.id == statement_id)
        .options(selectinload(BankStatement.lines))
    )
    if not statement:
        raise HTTPException(404, "Statement not found")
    permissions = ensure_permission(db, user, statement.company_id, "bank.reconcile")
    if statement.created_by == user.id and "*" not in permissions:
        raise HTTPException(409, "Maker-checker control: statement creator cannot complete reconciliation")
    if statement.matched_by == user.id and "*" not in permissions:
        raise HTTPException(409, "Maker-checker control: statement matcher cannot complete reconciliation")
    if statement.status == "RECONCILED":
        raise HTTPException(409, "Statement is already reconciled")
    if any(line.status != "MATCHED" for line in statement.lines):
        raise HTTPException(409, "All statement lines must be matched before reconciliation")
    debit, credit = db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(
            JournalLine.account_id == statement.bank_account.gl_account_id,
            JournalEntry.company_id == statement.company_id,
            JournalEntry.status.in_(["POSTED", "REVERSED"]),
            JournalEntry.entry_date <= statement.statement_date,
        )
    ).one()
    gl_balance = money(Decimal(debit) - Decimal(credit))
    difference = money(statement.closing_balance - gl_balance)
    if difference != 0:
        raise HTTPException(409, f"GL and statement do not agree. Difference: {difference}")
    statement.status = "RECONCILED"
    statement.reconciled_by = user.id
    statement.reconciled_at = utc_now()
    write_audit(
        db,
        action="BANK_STATEMENT_RECONCILED",
        entity_type="BANK_STATEMENT",
        entity_id=statement.id,
        user_id=user.id,
        company_id=statement.company_id,
        after={"gl_balance": str(gl_balance), "statement_balance": str(statement.closing_balance)},
    )
    db.commit()
    return {"statement_id": statement.id, "status": statement.status, "gl_balance": gl_balance, "statement_balance": statement.closing_balance, "difference": difference}
