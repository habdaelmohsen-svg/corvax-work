from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BusinessCombination, Company, ConsolidatedTrialBalanceLine,
    ConsolidatedTrialBalanceRun, ConsolidationGroup, ConsolidationMember,
    ConsolidationWorksheet, ConsolidationWorksheetLine,
    ContingentConsiderationRemeasurement, ForeignOperationDisposal,
    ForeignOperationTranslationRun, JournalEntry, JournalLine, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/finance-completion", tags=["final consolidation and finance completion"])
Q = Decimal("0.01")
R6 = Decimal("0.000001")


def _rate(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(R6, rounding=ROUND_HALF_UP)


def _version(db: Session, model, *conditions) -> int:
    return int(db.scalar(select(func.max(model.version)).where(*conditions)) or 0) + 1


def _review(row, user: User) -> None:
    if row.status != "READY_FOR_REVIEW":
        raise HTTPException(409, "Record is not ready for review")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot review this record")
    row.status = "REVIEWED"
    row.reviewed_by = user.id
    row.reviewed_at = utc_now()


def _approve(row, user: User) -> None:
    if row.status != "REVIEWED":
        raise HTTPException(409, "Record must be reviewed before approval")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot approve this record")
    if row.reviewed_by == user.id:
        raise HTTPException(409, "Three-step control: reviewer cannot be final approver")
    row.approved_by = user.id
    row.approved_at = utc_now()


def _group_members(db: Session, group_id: int) -> tuple[ConsolidationGroup, list[ConsolidationMember]]:
    group = db.get(ConsolidationGroup, group_id)
    if not group:
        raise HTTPException(404, "Consolidation group not found")
    members = db.scalars(
        select(ConsolidationMember).where(ConsolidationMember.group_id == group_id).order_by(ConsolidationMember.company_id)
    ).all()
    if not members:
        raise HTTPException(422, "Consolidation group has no members")
    return group, members


def _line_payload(run: ConsolidatedTrialBalanceRun) -> list[dict]:
    return [
        {
            "account_code": line.account_code,
            "account_name_ar": line.account_name_ar,
            "account_name_en": line.account_name_en,
            "account_type": line.account_type,
            "member_debit": str(money(line.member_debit)),
            "member_credit": str(money(line.member_credit)),
            "adjustment_debit": str(money(line.adjustment_debit)),
            "adjustment_credit": str(money(line.adjustment_credit)),
            "consolidated_debit": str(money(line.consolidated_debit)),
            "consolidated_credit": str(money(line.consolidated_credit)),
        }
        for line in sorted(run.lines, key=lambda item: item.account_code)
    ]


def _report_hash(group_id: int, period_end: date, version: int, lines: list[dict]) -> str:
    payload = {
        "group_id": group_id,
        "period_end": str(period_end),
        "version": version,
        "lines": lines,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _translation_rate(db: Session, group: ConsolidationGroup, company: Company, period_end: date, account_type: str) -> Decimal:
    if company.currency.upper() == group.reporting_currency.upper():
        return Decimal("1")
    translation = db.scalar(
        select(ForeignOperationTranslationRun).where(
            ForeignOperationTranslationRun.group_id == group.id,
            ForeignOperationTranslationRun.member_company_id == company.id,
            ForeignOperationTranslationRun.period_end == period_end,
            ForeignOperationTranslationRun.status == "APPROVED_FOR_CONSOLIDATION",
        )
    )
    if not translation:
        raise HTTPException(
            422,
            f"Approved foreign-operation translation is required for company {company.code} at {period_end}",
        )
    if account_type in {"ASSET", "LIABILITY"}:
        return Decimal(translation.closing_rate)
    if account_type == "EQUITY":
        return Decimal(translation.historical_equity_rate)
    return Decimal(translation.average_rate)


class ConsolidatedTrialBalanceIn(BaseModel):
    group_id: int
    period_end: date


class ContingentConsiderationIn(BaseModel):
    combination_id: int
    measurement_date: date
    classification: str = "LIABILITY"
    measurement_type: str = "SUBSEQUENT_REMEASUREMENT"
    opening_fair_value: Decimal = Field(ge=0)
    closing_fair_value: Decimal = Field(ge=0)
    evidence_reference: str = Field(min_length=3, max_length=500)
    rationale: str = Field(min_length=10, max_length=2000)


class ForeignOperationDisposalIn(BaseModel):
    translation_run_id: int
    disposal_date: date
    disposal_type: str
    disposal_percent: Decimal = Field(gt=0, le=1)
    evidence_reference: str = Field(min_length=3, max_length=500)
    rationale: str = Field(min_length=10, max_length=2000)


@router.post("/consolidated-trial-balances", status_code=201)
def create_consolidated_trial_balance(
    data: ConsolidatedTrialBalanceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group, members = _group_members(db, data.group_id)
    companies = {company.id: company for company in db.scalars(select(Company).where(Company.id.in_([m.company_id for m in members]))).all()}
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.corporate.manage")

    buckets: dict[str, dict] = defaultdict(lambda: {
        "name_ar": "", "name_en": "", "account_type": "ADJUSTMENT",
        "member_debit": Decimal("0"), "member_credit": Decimal("0"),
        "adjustment_debit": Decimal("0"), "adjustment_credit": Decimal("0"),
    })

    for member in members:
        company = companies[member.company_id]
        member_translated_debit = Decimal("0")
        member_translated_credit = Decimal("0")
        rows = db.execute(
            select(
                Account.code, func.max(Account.name_ar), func.max(Account.name_en), func.max(Account.account_type),
                func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
            .where(
                Account.company_id == member.company_id,
                JournalEntry.status.in_(("POSTED", "REVERSED")),
                JournalEntry.entry_date <= data.period_end,
            )
            .group_by(Account.code)
            .order_by(Account.code)
        ).all()
        for code, name_ar, name_en, account_type, debit, credit in rows:
            rate = _translation_rate(db, group, company, data.period_end, account_type)
            bucket = buckets[code]
            bucket["name_ar"] = name_ar
            bucket["name_en"] = name_en
            bucket["account_type"] = account_type
            translated_debit = money(Decimal(debit or 0) * rate)
            translated_credit = money(Decimal(credit or 0) * rate)
            bucket["member_debit"] += translated_debit
            bucket["member_credit"] += translated_credit
            member_translated_debit += translated_debit
            member_translated_credit += translated_credit
        translation_difference = money(member_translated_debit - member_translated_credit)
        if translation_difference != 0:
            cta_bucket = buckets["313010"]
            cta_bucket["name_ar"] = "احتياطي فروق ترجمة العملات"
            cta_bucket["name_en"] = "Foreign Currency Translation Reserve"
            cta_bucket["account_type"] = "EQUITY"
            if translation_difference > 0:
                cta_bucket["adjustment_credit"] += translation_difference
            else:
                cta_bucket["adjustment_debit"] += abs(translation_difference)

    approved_worksheets = db.scalars(
        select(ConsolidationWorksheet)
        .options(selectinload(ConsolidationWorksheet.lines))
        .where(
            ConsolidationWorksheet.group_id == group.id,
            ConsolidationWorksheet.period_end == data.period_end,
            ConsolidationWorksheet.status == "APPROVED_FOR_CONSOLIDATION",
        )
    ).all()
    pending_count = int(db.scalar(
        select(func.count(ConsolidationWorksheet.id)).where(
            ConsolidationWorksheet.group_id == group.id,
            ConsolidationWorksheet.period_end == data.period_end,
            ConsolidationWorksheet.status != "APPROVED_FOR_CONSOLIDATION",
        )
    ) or 0)

    member_ids = [m.company_id for m in members]
    account_lookup = {
        row.code: row for row in db.scalars(select(Account).where(Account.company_id.in_(member_ids))).all()
    }
    for worksheet in approved_worksheets:
        for line in worksheet.lines:
            bucket = buckets[line.account_code]
            account = account_lookup.get(line.account_code)
            if account:
                bucket["name_ar"] = account.name_ar
                bucket["name_en"] = account.name_en
                bucket["account_type"] = account.account_type
            else:
                bucket["name_ar"] = bucket["name_ar"] or line.description_ar
                bucket["name_en"] = bucket["name_en"] or line.description_en
            bucket["adjustment_debit"] += money(line.debit)
            bucket["adjustment_credit"] += money(line.credit)

    version = _version(
        db, ConsolidatedTrialBalanceRun,
        ConsolidatedTrialBalanceRun.group_id == group.id,
        ConsolidatedTrialBalanceRun.period_end == data.period_end,
    )
    prepared_lines: list[dict] = []
    ledger_debit = ledger_credit = adjustment_debit = adjustment_credit = Decimal("0")
    for code in sorted(buckets):
        item = buckets[code]
        consolidated_debit = money(item["member_debit"] + item["adjustment_debit"])
        consolidated_credit = money(item["member_credit"] + item["adjustment_credit"])
        prepared = {
            "account_code": code,
            "account_name_ar": item["name_ar"] or code,
            "account_name_en": item["name_en"] or code,
            "account_type": item["account_type"],
            "member_debit": money(item["member_debit"]),
            "member_credit": money(item["member_credit"]),
            "adjustment_debit": money(item["adjustment_debit"]),
            "adjustment_credit": money(item["adjustment_credit"]),
            "consolidated_debit": consolidated_debit,
            "consolidated_credit": consolidated_credit,
        }
        prepared_lines.append(prepared)
        ledger_debit += prepared["member_debit"]
        ledger_credit += prepared["member_credit"]
        adjustment_debit += prepared["adjustment_debit"]
        adjustment_credit += prepared["adjustment_credit"]

    ledger_debit, ledger_credit = money(ledger_debit), money(ledger_credit)
    adjustment_debit, adjustment_credit = money(adjustment_debit), money(adjustment_credit)
    consolidated_debit = money(ledger_debit + adjustment_debit)
    consolidated_credit = money(ledger_credit + adjustment_credit)
    difference = money(consolidated_debit - consolidated_credit)
    if difference != 0:
        raise HTTPException(422, f"Consolidated trial balance is not balanced: {difference}")
    serializable = [{key: str(value) if isinstance(value, Decimal) else value for key, value in item.items()} for item in prepared_lines]
    digest = _report_hash(group.id, data.period_end, version, serializable)
    run = ConsolidatedTrialBalanceRun(
        group_id=group.id, period_end=data.period_end, version=version, member_count=len(members),
        ledger_debit=ledger_debit, ledger_credit=ledger_credit,
        adjustment_debit=adjustment_debit, adjustment_credit=adjustment_credit,
        consolidated_debit=consolidated_debit, consolidated_credit=consolidated_credit,
        balance_difference=difference, pending_worksheet_count=pending_count,
        report_hash=digest, prepared_by=user.id,
    )
    for item in prepared_lines:
        run.lines.append(ConsolidatedTrialBalanceLine(**item))
    db.add(run)
    db.flush()
    write_audit(
        db, action="CONSOLIDATED_TRIAL_BALANCE_CREATED", entity_type="CONSOLIDATED_TRIAL_BALANCE",
        entity_id=run.id, user_id=user.id,
        after={"group_id": group.id, "period_end": str(data.period_end), "version": version,
               "members": len(members), "approved_worksheets": len(approved_worksheets),
               "pending_worksheets": pending_count, "report_hash": digest},
    )
    db.commit()
    return {
        "id": run.id, "version": version, "status": run.status, "member_count": run.member_count,
        "ledger_debit": run.ledger_debit, "ledger_credit": run.ledger_credit,
        "adjustment_debit": run.adjustment_debit, "adjustment_credit": run.adjustment_credit,
        "consolidated_debit": run.consolidated_debit, "consolidated_credit": run.consolidated_credit,
        "balance_difference": run.balance_difference, "pending_worksheet_count": pending_count,
        "report_hash": run.report_hash, "line_count": len(run.lines),
    }


@router.post("/consolidated-trial-balances/{run_id}/review")
def review_consolidated_trial_balance(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(ConsolidatedTrialBalanceRun).options(selectinload(ConsolidatedTrialBalanceRun.lines)).where(ConsolidatedTrialBalanceRun.id == run_id))
    if not run:
        raise HTTPException(404, "Consolidated trial balance not found")
    _, members = _group_members(db, run.group_id)
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.corporate.review")
    if money(run.balance_difference) != 0:
        raise HTTPException(409, "Unbalanced consolidated trial balance cannot be reviewed")
    if run.pending_worksheet_count:
        raise HTTPException(409, "Pending consolidation worksheets must be resolved before review")
    expected = _report_hash(run.group_id, run.period_end, run.version, _line_payload(run))
    if expected != run.report_hash:
        raise HTTPException(409, "Consolidated trial balance integrity check failed")
    _review(run, user)
    write_audit(db, action="CONSOLIDATED_TRIAL_BALANCE_REVIEWED", entity_type="CONSOLIDATED_TRIAL_BALANCE", entity_id=run.id, user_id=user.id, after={"status": run.status, "report_hash": run.report_hash})
    db.commit()
    return {"id": run.id, "status": run.status, "report_hash": run.report_hash}


@router.post("/consolidated-trial-balances/{run_id}/approve")
def approve_consolidated_trial_balance(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(ConsolidatedTrialBalanceRun).options(selectinload(ConsolidatedTrialBalanceRun.lines)).where(ConsolidatedTrialBalanceRun.id == run_id))
    if not run:
        raise HTTPException(404, "Consolidated trial balance not found")
    _, members = _group_members(db, run.group_id)
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.corporate.approve")
    current_pending = int(db.scalar(select(func.count(ConsolidationWorksheet.id)).where(
        ConsolidationWorksheet.group_id == run.group_id,
        ConsolidationWorksheet.period_end == run.period_end,
        ConsolidationWorksheet.status != "APPROVED_FOR_CONSOLIDATION",
    )) or 0)
    if current_pending:
        raise HTTPException(409, "New or pending consolidation worksheets exist; regenerate the trial balance")
    expected = _report_hash(run.group_id, run.period_end, run.version, _line_payload(run))
    if expected != run.report_hash:
        raise HTTPException(409, "Consolidated trial balance integrity check failed")
    _approve(run, user)
    run.status = "APPROVED_LOCKED"
    write_audit(db, action="CONSOLIDATED_TRIAL_BALANCE_APPROVED", entity_type="CONSOLIDATED_TRIAL_BALANCE", entity_id=run.id, user_id=user.id, after={"status": run.status, "total": str(run.consolidated_debit), "report_hash": run.report_hash})
    db.commit()
    return {"id": run.id, "status": run.status, "consolidated_debit": run.consolidated_debit, "consolidated_credit": run.consolidated_credit, "report_hash": run.report_hash}


@router.get("/consolidated-trial-balances/{run_id}")
def get_consolidated_trial_balance(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.scalar(select(ConsolidatedTrialBalanceRun).options(selectinload(ConsolidatedTrialBalanceRun.lines)).where(ConsolidatedTrialBalanceRun.id == run_id))
    if not run:
        raise HTTPException(404, "Consolidated trial balance not found")
    _, members = _group_members(db, run.group_id)
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.corporate.read")
    expected = _report_hash(run.group_id, run.period_end, run.version, _line_payload(run))
    return {
        "id": run.id, "group_id": run.group_id, "period_end": run.period_end, "version": run.version,
        "status": run.status, "member_count": run.member_count, "ledger_debit": run.ledger_debit,
        "ledger_credit": run.ledger_credit, "adjustment_debit": run.adjustment_debit,
        "adjustment_credit": run.adjustment_credit, "consolidated_debit": run.consolidated_debit,
        "consolidated_credit": run.consolidated_credit, "balance_difference": run.balance_difference,
        "pending_worksheet_count": run.pending_worksheet_count, "report_hash": run.report_hash,
        "integrity_valid": expected == run.report_hash, "lines": _line_payload(run),
    }


@router.get("/consolidated-trial-balances")
def list_consolidated_trial_balances(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, members = _group_members(db, group_id)
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.corporate.read")
    rows = db.scalars(select(ConsolidatedTrialBalanceRun).where(ConsolidatedTrialBalanceRun.group_id == group_id).order_by(ConsolidatedTrialBalanceRun.period_end.desc(), ConsolidatedTrialBalanceRun.version.desc())).all()
    return [{"id": row.id, "period_end": row.period_end, "version": row.version, "status": row.status, "member_count": row.member_count, "consolidated_debit": row.consolidated_debit, "consolidated_credit": row.consolidated_credit, "report_hash": row.report_hash} for row in rows]


@router.post("/contingent-consideration", status_code=201)
def create_contingent_consideration(data: ContingentConsiderationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    combination = db.get(BusinessCombination, data.combination_id)
    if not combination or combination.status != "APPROVED_FOR_CONSOLIDATION":
        raise HTTPException(422, "An approved business combination is required")
    ensure_permission(db, user, combination.acquirer_company_id, "finance.corporate.manage")
    classification = data.classification.upper()
    measurement_type = data.measurement_type.upper()
    if classification not in {"LIABILITY", "EQUITY"}:
        raise HTTPException(422, "Classification must be LIABILITY or EQUITY")
    if measurement_type not in {"MEASUREMENT_PERIOD_ADJUSTMENT", "SUBSEQUENT_REMEASUREMENT"}:
        raise HTTPException(422, "Invalid measurement type")
    if data.measurement_date < combination.acquisition_date:
        raise HTTPException(422, "Measurement date cannot precede acquisition date")
    if measurement_type == "MEASUREMENT_PERIOD_ADJUSTMENT" and data.measurement_date > combination.acquisition_date + timedelta(days=365):
        raise HTTPException(422, "Measurement-period adjustment must be within one year of acquisition")
    if classification == "EQUITY" and money(data.closing_fair_value - data.opening_fair_value) != 0:
        raise HTTPException(422, "Equity-classified contingent consideration is not subsequently remeasured")
    latest = db.scalar(select(ContingentConsiderationRemeasurement).where(
        ContingentConsiderationRemeasurement.combination_id == combination.id,
        ContingentConsiderationRemeasurement.status == "APPROVED_POSTED",
    ).order_by(ContingentConsiderationRemeasurement.measurement_date.desc(), ContingentConsiderationRemeasurement.version.desc()))
    expected_opening = money(latest.closing_fair_value if latest else combination.contingent_consideration)
    if abs(money(data.opening_fair_value) - expected_opening) > Q:
        raise HTTPException(422, f"Opening fair value must equal the latest approved balance: {expected_opening}")
    version = _version(db, ContingentConsiderationRemeasurement,
                       ContingentConsiderationRemeasurement.combination_id == combination.id,
                       ContingentConsiderationRemeasurement.measurement_date == data.measurement_date)
    change = money(data.closing_fair_value - data.opening_fair_value)
    row = ContingentConsiderationRemeasurement(
        combination_id=combination.id, measurement_date=data.measurement_date, version=version,
        classification=classification, measurement_type=measurement_type,
        opening_fair_value=money(data.opening_fair_value), closing_fair_value=money(data.closing_fair_value),
        fair_value_change=change, evidence_reference=data.evidence_reference, rationale=data.rationale,
        prepared_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="CONTINGENT_CONSIDERATION_REMEASUREMENT_CREATED", entity_type="CONTINGENT_CONSIDERATION", entity_id=row.id, user_id=user.id, company_id=combination.acquirer_company_id, after={"combination_id": combination.id, "measurement_type": measurement_type, "classification": classification, "opening": str(row.opening_fair_value), "closing": str(row.closing_fair_value), "change": str(change)})
    db.commit()
    return {"id": row.id, "version": row.version, "status": row.status, "classification": row.classification, "measurement_type": row.measurement_type, "opening_fair_value": row.opening_fair_value, "closing_fair_value": row.closing_fair_value, "fair_value_change": row.fair_value_change}


@router.post("/contingent-consideration/{measurement_id}/review")
def review_contingent_consideration(measurement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ContingentConsiderationRemeasurement, measurement_id)
    if not row:
        raise HTTPException(404, "Contingent consideration measurement not found")
    ensure_permission(db, user, row.combination.acquirer_company_id, "finance.corporate.review")
    _review(row, user)
    write_audit(db, action="CONTINGENT_CONSIDERATION_REMEASUREMENT_REVIEWED", entity_type="CONTINGENT_CONSIDERATION", entity_id=row.id, user_id=user.id, company_id=row.combination.acquirer_company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/contingent-consideration/{measurement_id}/approve")
def approve_contingent_consideration(measurement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ContingentConsiderationRemeasurement, measurement_id)
    if not row:
        raise HTTPException(404, "Contingent consideration measurement not found")
    company_id = row.combination.acquirer_company_id
    ensure_permission(db, user, company_id, "finance.corporate.approve")
    _approve(row, user)
    change = money(row.fair_value_change)
    if row.classification == "LIABILITY" and change != 0:
        liability = get_account(db, company_id, "224010")
        if row.measurement_type == "MEASUREMENT_PERIOD_ADJUSTMENT":
            counterpart = get_account(db, company_id, "154020")
        else:
            counterpart = get_account(db, company_id, "622010" if change > 0 else "422010")
        amount = abs(change)
        if change > 0:
            lines = [
                {"account_id": counterpart.id, "debit": amount, "credit": 0},
                {"account_id": liability.id, "debit": 0, "credit": amount},
            ]
        else:
            lines = [
                {"account_id": liability.id, "debit": amount, "credit": 0},
                {"account_id": counterpart.id, "debit": 0, "credit": amount},
            ]
        journal = create_posted_journal(
            db, company_id=company_id, user_id=user.id, posting_date=row.measurement_date,
            reference=f"CC-{row.combination_id}-{row.id}",
            description=f"Contingent consideration {row.measurement_type.lower()} for acquisition {row.combination_id}",
            lines=lines,
        )
        row.journal_id = journal.id
    row.status = "APPROVED_POSTED" if row.journal_id else "APPROVED_NO_REMEASUREMENT"
    write_audit(db, action="CONTINGENT_CONSIDERATION_REMEASUREMENT_APPROVED", entity_type="CONTINGENT_CONSIDERATION", entity_id=row.id, user_id=user.id, company_id=company_id, after={"status": row.status, "change": str(change), "journal_id": row.journal_id})
    db.commit()
    return {"id": row.id, "status": row.status, "fair_value_change": row.fair_value_change, "journal_id": row.journal_id}


@router.get("/contingent-consideration")
def list_contingent_consideration(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    rows = db.scalars(select(ContingentConsiderationRemeasurement).join(BusinessCombination).where(BusinessCombination.acquirer_company_id == company_id).order_by(ContingentConsiderationRemeasurement.measurement_date.desc())).all()
    return [{"id": row.id, "combination_id": row.combination_id, "measurement_date": row.measurement_date, "version": row.version, "classification": row.classification, "measurement_type": row.measurement_type, "opening_fair_value": row.opening_fair_value, "closing_fair_value": row.closing_fair_value, "fair_value_change": row.fair_value_change, "status": row.status, "journal_id": row.journal_id} for row in rows]


@router.post("/foreign-operation-disposals", status_code=201)
def create_foreign_operation_disposal(data: ForeignOperationDisposalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    translation = db.get(ForeignOperationTranslationRun, data.translation_run_id)
    if not translation or translation.status != "APPROVED_FOR_CONSOLIDATION":
        raise HTTPException(422, "An approved foreign-operation translation is required")
    ensure_permission(db, user, translation.member_company_id, "finance.corporate.manage")
    disposal_type = data.disposal_type.upper()
    if disposal_type not in {"FULL_DISPOSAL", "PARTIAL_LOSS_OF_CONTROL", "PARTIAL_NO_LOSS_OF_CONTROL"}:
        raise HTTPException(422, "Invalid disposal type")
    percent = _rate(data.disposal_percent)
    if disposal_type == "FULL_DISPOSAL" and percent != Decimal("1.000000"):
        raise HTTPException(422, "FULL_DISPOSAL requires disposal_percent = 1")
    if data.disposal_date < translation.period_end:
        raise HTTPException(422, "Disposal date cannot precede the translation period end")
    existing = db.scalar(select(ForeignOperationDisposal).where(
        ForeignOperationDisposal.translation_run_id == translation.id,
        ForeignOperationDisposal.status == "APPROVED_FOR_CONSOLIDATION",
    ))
    if existing:
        raise HTTPException(409, "This translation run already has an approved disposal treatment")
    cta = money(translation.cta_amount)
    recycled = money(cta * percent)
    row = ForeignOperationDisposal(
        translation_run_id=translation.id, disposal_date=data.disposal_date, disposal_type=disposal_type,
        disposal_percent=percent, cta_before_disposal=cta, cta_recycled=recycled,
        remaining_cta=money(cta - recycled), evidence_reference=data.evidence_reference,
        rationale=data.rationale, prepared_by=user.id,
    )
    db.add(row)
    db.flush()
    write_audit(db, action="FOREIGN_OPERATION_DISPOSAL_CREATED", entity_type="FOREIGN_OPERATION_DISPOSAL", entity_id=row.id, user_id=user.id, company_id=translation.member_company_id, after={"translation_run_id": translation.id, "disposal_type": disposal_type, "disposal_percent": str(percent), "cta_before": str(cta), "cta_recycled": str(recycled)})
    db.commit()
    return {"id": row.id, "status": row.status, "disposal_type": row.disposal_type, "disposal_percent": row.disposal_percent, "cta_before_disposal": row.cta_before_disposal, "cta_recycled": row.cta_recycled, "remaining_cta": row.remaining_cta}


@router.post("/foreign-operation-disposals/{disposal_id}/review")
def review_foreign_operation_disposal(disposal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ForeignOperationDisposal, disposal_id)
    if not row:
        raise HTTPException(404, "Foreign operation disposal not found")
    ensure_permission(db, user, row.translation.member_company_id, "finance.corporate.review")
    _review(row, user)
    write_audit(db, action="FOREIGN_OPERATION_DISPOSAL_REVIEWED", entity_type="FOREIGN_OPERATION_DISPOSAL", entity_id=row.id, user_id=user.id, company_id=row.translation.member_company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/foreign-operation-disposals/{disposal_id}/approve")
def approve_foreign_operation_disposal(disposal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ForeignOperationDisposal, disposal_id)
    if not row:
        raise HTTPException(404, "Foreign operation disposal not found")
    translation = row.translation
    ensure_permission(db, user, translation.member_company_id, "finance.corporate.approve")
    _approve(row, user)
    amount = abs(money(row.cta_recycled))
    if amount == 0:
        raise HTTPException(422, "There is no CTA balance to recycle or reattribute")
    version = _version(db, ConsolidationWorksheet,
                       ConsolidationWorksheet.group_id == translation.group_id,
                       ConsolidationWorksheet.period_end == row.disposal_date)
    worksheet = ConsolidationWorksheet(
        group_id=translation.group_id, period_end=row.disposal_date, version=version,
        worksheet_type="FOREIGN_OPERATION_DISPOSAL",
        reference=f"CTA-DISPOSAL-{row.id}",
        description_ar="إعادة تصنيف احتياطي فروق ترجمة عملية أجنبية عند التخلص",
        description_en="Reclassification of foreign currency translation reserve on disposal",
        total_debit=amount, total_credit=amount, balance_difference=0,
        status="APPROVED_FOR_CONSOLIDATION", prepared_by=row.prepared_by,
        reviewed_by=row.reviewed_by, approved_by=user.id,
        reviewed_at=row.reviewed_at, approved_at=utc_now(),
    )
    if row.disposal_type == "PARTIAL_NO_LOSS_OF_CONTROL":
        counterpart_code = "314010"
        counterpart_ar = "حقوق غير المسيطرين"
        counterpart_en = "Non-controlling interests"
    else:
        counterpart_code = "423010" if row.cta_recycled > 0 else "623010"
        counterpart_ar = "أرباح التخلص من عملية أجنبية" if row.cta_recycled > 0 else "خسائر التخلص من عملية أجنبية"
        counterpart_en = "Gain on disposal of foreign operation" if row.cta_recycled > 0 else "Loss on disposal of foreign operation"
    if row.cta_recycled > 0:
        debit_code, debit_ar, debit_en = "313010", "احتياطي فروق ترجمة العملات", "Foreign currency translation reserve"
        credit_code, credit_ar, credit_en = counterpart_code, counterpart_ar, counterpart_en
    else:
        debit_code, debit_ar, debit_en = counterpart_code, counterpart_ar, counterpart_en
        credit_code, credit_ar, credit_en = "313010", "احتياطي فروق ترجمة العملات", "Foreign currency translation reserve"
    worksheet.lines.extend([
        ConsolidationWorksheetLine(line_number=1, adjustment_type="CTA_RECYCLE", account_code=debit_code,
                                   description_ar=debit_ar, description_en=debit_en, debit=amount, credit=0,
                                   source_reference=row.evidence_reference),
        ConsolidationWorksheetLine(line_number=2, adjustment_type="CTA_RECYCLE", account_code=credit_code,
                                   description_ar=credit_ar, description_en=credit_en, debit=0, credit=amount,
                                   source_reference=row.evidence_reference),
    ])
    db.add(worksheet)
    db.flush()
    row.worksheet_id = worksheet.id
    row.status = "APPROVED_FOR_CONSOLIDATION"
    write_audit(db, action="FOREIGN_OPERATION_DISPOSAL_APPROVED", entity_type="FOREIGN_OPERATION_DISPOSAL", entity_id=row.id, user_id=user.id, company_id=translation.member_company_id, after={"status": row.status, "cta_recycled": str(row.cta_recycled), "remaining_cta": str(row.remaining_cta), "worksheet_id": worksheet.id})
    db.commit()
    return {"id": row.id, "status": row.status, "cta_recycled": row.cta_recycled, "remaining_cta": row.remaining_cta, "worksheet_id": row.worksheet_id}


@router.get("/foreign-operation-disposals")
def list_foreign_operation_disposals(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, members = _group_members(db, group_id)
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.corporate.read")
    rows = db.scalars(select(ForeignOperationDisposal).join(ForeignOperationTranslationRun).where(ForeignOperationTranslationRun.group_id == group_id).order_by(ForeignOperationDisposal.disposal_date.desc())).all()
    return [{"id": row.id, "translation_run_id": row.translation_run_id, "disposal_date": row.disposal_date, "disposal_type": row.disposal_type, "disposal_percent": row.disposal_percent, "cta_before_disposal": row.cta_before_disposal, "cta_recycled": row.cta_recycled, "remaining_cta": row.remaining_cta, "status": row.status, "worksheet_id": row.worksheet_id} for row in rows]


@router.get("/dashboard")
def finance_completion_dashboard(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    group_ids = db.scalars(select(ConsolidationMember.group_id).where(ConsolidationMember.company_id == company_id)).all()
    approved_tb = int(db.scalar(select(func.count(ConsolidatedTrialBalanceRun.id)).where(
        ConsolidatedTrialBalanceRun.group_id.in_(group_ids or [-1]), ConsolidatedTrialBalanceRun.status == "APPROVED_LOCKED")) or 0)
    pending_tb = int(db.scalar(select(func.count(ConsolidatedTrialBalanceRun.id)).where(
        ConsolidatedTrialBalanceRun.group_id.in_(group_ids or [-1]), ConsolidatedTrialBalanceRun.status.in_(("READY_FOR_REVIEW", "REVIEWED")))) or 0)
    contingent = int(db.scalar(select(func.count(ContingentConsiderationRemeasurement.id)).join(BusinessCombination).where(BusinessCombination.acquirer_company_id == company_id)) or 0)
    disposals = int(db.scalar(select(func.count(ForeignOperationDisposal.id)).join(ForeignOperationTranslationRun).where(
        ForeignOperationTranslationRun.group_id.in_(group_ids or [-1]), ForeignOperationDisposal.status == "APPROVED_FOR_CONSOLIDATION")) or 0)
    return {
        "approved_locked_consolidated_trial_balances": approved_tb,
        "pending_consolidated_trial_balances": pending_tb,
        "contingent_consideration_measurements": contingent,
        "approved_foreign_operation_disposals": disposals,
    }
