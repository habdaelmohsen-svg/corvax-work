from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Company, IntercompanyMatch, IntercompanyRecord, User
from app.services.audit import write_audit

router = APIRouter(prefix="/intercompany", tags=["intercompany reconciliation"])


class RecordIn(BaseModel):
    company_id: int
    counterparty_company_id: int
    document_number: str = Field(min_length=1, max_length=80)
    transaction_date: date
    direction: str
    account_code: str
    currency_code: str = Field(default="SAR", min_length=3, max_length=3)
    foreign_amount: Decimal = 0
    local_amount: Decimal = Field(gt=0)
    description: str | None = None
    journal_id: int | None = None


class MatchIn(BaseModel):
    record_a_id: int
    record_b_id: int
    tolerance: Decimal = Field(default=Decimal("0.01"), ge=0)
    notes: str | None = None


@router.post("/records", status_code=201)
def create_record(data: RecordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "consolidation.manage")
    ensure_permission(db, user, data.counterparty_company_id, "finance.read")
    if data.company_id == data.counterparty_company_id:
        raise HTTPException(422, "Company and counterparty must be different")
    if not db.get(Company, data.counterparty_company_id):
        raise HTTPException(422, "Counterparty company not found")
    direction = data.direction.upper()
    if direction not in {"RECEIVABLE", "PAYABLE", "REVENUE", "EXPENSE"}:
        raise HTTPException(422, "Unsupported intercompany direction")
    row = IntercompanyRecord(
        company_id=data.company_id,
        counterparty_company_id=data.counterparty_company_id,
        document_number=data.document_number,
        transaction_date=data.transaction_date,
        direction=direction,
        account_code=data.account_code,
        currency_code=data.currency_code.upper(),
        foreign_amount=data.foreign_amount,
        local_amount=data.local_amount,
        description=data.description,
        journal_id=data.journal_id,
        created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="INTERCOMPANY_RECORD_CREATED", entity_type="INTERCOMPANY_RECORD",
                entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"counterparty": data.counterparty_company_id, "document": data.document_number,
                       "direction": direction, "amount": str(data.local_amount)})
    db.commit()
    return {"id": row.id, "status": row.status, "document_number": row.document_number}


@router.get("/records")
def list_records(company_id: int, status: str | None = None,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    stmt = select(IntercompanyRecord).where(IntercompanyRecord.company_id == company_id)
    if status:
        stmt = stmt.where(IntercompanyRecord.status == status.upper())
    rows = db.scalars(stmt.order_by(IntercompanyRecord.transaction_date.desc(), IntercompanyRecord.id.desc())).all()
    return [{"id": r.id, "counterparty_company_id": r.counterparty_company_id,
             "document_number": r.document_number, "transaction_date": r.transaction_date,
             "direction": r.direction, "account_code": r.account_code,
             "currency_code": r.currency_code, "local_amount": r.local_amount,
             "status": r.status} for r in rows]


@router.post("/matches", status_code=201)
def match_records(data: MatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a, b = db.get(IntercompanyRecord, data.record_a_id), db.get(IntercompanyRecord, data.record_b_id)
    if not a or not b:
        raise HTTPException(404, "Intercompany record not found")
    ensure_permission(db, user, a.company_id, "consolidation.manage")
    ensure_permission(db, user, b.company_id, "consolidation.manage")
    if a.company_id != b.counterparty_company_id or b.company_id != a.counterparty_company_id:
        raise HTTPException(422, "Records are not reciprocal counterparties")
    complementary = {a.direction, b.direction} in ({"RECEIVABLE", "PAYABLE"}, {"REVENUE", "EXPENSE"})
    if not complementary:
        raise HTTPException(422, "Directions must be receivable/payable or revenue/expense")
    if a.status == "MATCHED" or b.status == "MATCHED":
        raise HTTPException(409, "One of the records is already matched")
    variance = abs(Decimal(a.local_amount) - Decimal(b.local_amount))
    if variance > data.tolerance:
        raise HTTPException(422, f"Variance {variance} exceeds tolerance {data.tolerance}")
    matched_amount = min(Decimal(a.local_amount), Decimal(b.local_amount))
    row = IntercompanyMatch(record_a_id=a.id, record_b_id=b.id, matched_amount=matched_amount,
                            variance_amount=variance, status="MATCHED", notes=data.notes, matched_by=user.id)
    a.status = b.status = "MATCHED"
    db.add(row); db.flush()
    write_audit(db, action="INTERCOMPANY_MATCH_CONFIRMED", entity_type="INTERCOMPANY_MATCH",
                entity_id=row.id, user_id=user.id,
                after={"record_a": a.id, "record_b": b.id, "amount": str(matched_amount),
                       "variance": str(variance)})
    db.commit()
    return {"id": row.id, "matched_amount": row.matched_amount, "variance_amount": row.variance_amount,
            "status": row.status}


@router.get("/reconciliation")
def reconciliation(company_id: int, period_end: date,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(select(IntercompanyRecord).where(
        or_(IntercompanyRecord.company_id == company_id, IntercompanyRecord.counterparty_company_id == company_id),
        IntercompanyRecord.transaction_date <= period_end,
    ).order_by(IntercompanyRecord.counterparty_company_id, IntercompanyRecord.document_number)).all()
    open_total = sum((Decimal(r.local_amount) for r in rows if r.company_id == company_id and r.status != "MATCHED"), Decimal("0"))
    matched_total = sum((Decimal(r.local_amount) for r in rows if r.company_id == company_id and r.status == "MATCHED"), Decimal("0"))
    return {"company_id": company_id, "period_end": period_end, "open_total": open_total,
            "matched_total": matched_total, "open_count": sum(1 for r in rows if r.company_id == company_id and r.status != "MATCHED"),
            "records": [{"id": r.id, "company_id": r.company_id,
                         "counterparty_company_id": r.counterparty_company_id,
                         "document_number": r.document_number, "direction": r.direction,
                         "local_amount": r.local_amount, "status": r.status} for r in rows]}
