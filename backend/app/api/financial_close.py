from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BusinessCombination, Company, ConsolidationGroup, ConsolidationMember,
    ConsolidationWorksheet, ConsolidationWorksheetLine, FinancialEvidence, JournalEntry,
    JournalLine, LeadSchedule, LeadScheduleItem, LeaseContract, LeaseModification,
    LeasePartialTermination, LeaseSchedule, PurchasePriceAllocationItem, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/financial-close", tags=["financial close workbench"])
Q = Decimal("0.01")
R6 = Decimal("0.000001")
ALLOWED_EVIDENCE_TYPES = {
    "application/pdf", "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png", "image/jpeg",
}
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
BACKEND_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = BACKEND_ROOT / "data" / "evidence"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _rate(value: Decimal | str | float) -> Decimal:
    return Decimal(str(value)).quantize(R6, rounding=ROUND_HALF_UP)


def _next_version(db: Session, model, *conditions) -> int:
    return int(db.scalar(select(func.max(model.version)).where(*conditions)) or 0) + 1


def _group_and_members(db: Session, group_id: int) -> tuple[ConsolidationGroup, set[int]]:
    group = db.get(ConsolidationGroup, group_id)
    if not group:
        raise HTTPException(404, "Consolidation group not found")
    members = set(db.scalars(select(ConsolidationMember.company_id).where(ConsolidationMember.group_id == group_id)).all())
    if not members:
        raise HTTPException(422, "Consolidation group has no members")
    return group, members


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


def _ledger_balance(db: Session, company_id: int, code_from: str, code_to: str, period_end: date) -> Decimal:
    rows = db.execute(
        select(
            Account.account_type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(
            Account.company_id == company_id,
            Account.code >= code_from,
            Account.code <= code_to,
            JournalEntry.status.in_(("POSTED", "REVERSED")),
            JournalEntry.entry_date <= period_end,
        )
        .group_by(Account.account_type)
    ).all()
    total = Decimal("0")
    for account_type, debit, credit in rows:
        debit_d, credit_d = Decimal(debit), Decimal(credit)
        total += credit_d - debit_d if account_type in {"LIABILITY", "EQUITY", "REVENUE"} else debit_d - credit_d
    return money(total)


def _carrying_rou(db: Session, lease: LeaseContract, effective_date: date) -> Decimal:
    approved_mods = db.scalars(select(LeaseModification).where(
        LeaseModification.lease_id == lease.id,
        LeaseModification.status == "APPROVED_POSTED",
        LeaseModification.effective_date <= effective_date,
    )).all()
    prior_terms = db.scalars(select(LeasePartialTermination).where(
        LeasePartialTermination.lease_id == lease.id,
        LeasePartialTermination.status == "APPROVED_POSTED",
        LeasePartialTermination.effective_date < effective_date,
    )).all()
    gross_rou = Decimal(lease.initial_rou_asset) + sum((Decimal(x.rou_adjustment) for x in approved_mods), Decimal("0"))
    gross_rou -= sum((Decimal(x.rou_reduction) for x in prior_terms), Decimal("0"))
    depreciation = sum((Decimal(s.depreciation) for s in lease.schedules if s.status == "POSTED" and s.payment_date <= effective_date), Decimal("0"))
    return money(max(gross_rou - depreciation, Decimal("0")))


class PPAItemIn(BaseModel):
    item_code: str = Field(min_length=1, max_length=60)
    item_type: str
    name_ar: str = Field(min_length=1, max_length=250)
    name_en: str = Field(min_length=1, max_length=250)
    book_value: Decimal = Decimal("0")
    fair_value: Decimal = Field(ge=0)
    tax_base: Decimal = Decimal("0")
    useful_life_months: int | None = Field(default=None, ge=1)
    identifiable_intangible: bool = False
    evidence_reference: str = Field(min_length=3, max_length=500)


class BusinessCombinationIn(BaseModel):
    group_id: int
    acquirer_company_id: int
    acquiree_company_id: int
    acquisition_date: date
    ownership_percent: Decimal = Field(gt=0.5, le=1)
    nci_measurement_method: str = "PROPORTIONATE_SHARE"
    consideration_cash: Decimal = Field(default=Decimal("0"), ge=0)
    consideration_shares: Decimal = Field(default=Decimal("0"), ge=0)
    contingent_consideration: Decimal = Field(default=Decimal("0"), ge=0)
    previously_held_interest_fv: Decimal = Field(default=Decimal("0"), ge=0)
    nci_fair_value: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    rationale: dict
    items: list[PPAItemIn] = Field(min_length=1)


class WorksheetLineIn(BaseModel):
    adjustment_type: str = Field(min_length=1, max_length=40)
    account_code: str = Field(min_length=1, max_length=60)
    description_ar: str = Field(min_length=1, max_length=500)
    description_en: str = Field(min_length=1, max_length=500)
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)
    source_reference: str = Field(min_length=3, max_length=500)


class WorksheetIn(BaseModel):
    group_id: int
    period_end: date
    worksheet_type: str = "MANUAL_ADJUSTMENT"
    reference: str = Field(min_length=1, max_length=120)
    description_ar: str = Field(min_length=1, max_length=500)
    description_en: str = Field(min_length=1, max_length=500)
    lines: list[WorksheetLineIn] = Field(min_length=2)


class LeadScheduleItemIn(BaseModel):
    reference: str = Field(min_length=1, max_length=120)
    description_ar: str = Field(min_length=1, max_length=500)
    description_en: str = Field(min_length=1, max_length=500)
    amount: Decimal
    reconciling_item: bool = False
    ageing_days: int | None = Field(default=None, ge=0)
    owner: str | None = Field(default=None, max_length=250)
    due_date: date | None = None
    status: str = "OPEN"


class LeadScheduleIn(BaseModel):
    company_id: int
    period_end: date
    code: str = Field(min_length=1, max_length=60)
    title_ar: str = Field(min_length=1, max_length=250)
    title_en: str = Field(min_length=1, max_length=250)
    account_code_from: str = Field(min_length=1, max_length=30)
    account_code_to: str = Field(min_length=1, max_length=30)
    conclusion_ar: str = Field(min_length=10)
    conclusion_en: str = Field(min_length=10)
    items: list[LeadScheduleItemIn] = Field(min_length=1)


class LeasePartialTerminationIn(BaseModel):
    lease_id: int
    effective_date: date
    reduction_percent: Decimal = Field(gt=0, lt=1)
    reason: str = Field(min_length=10, max_length=500)


@router.post("/business-combinations", status_code=201)
def create_business_combination(data: BusinessCombinationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, members = _group_and_members(db, data.group_id)
    if data.acquirer_company_id == data.acquiree_company_id:
        raise HTTPException(422, "Acquirer and acquiree must be different companies")
    if data.acquirer_company_id not in members or data.acquiree_company_id not in members:
        raise HTTPException(422, "Acquirer and acquiree must both belong to the consolidation group")
    ensure_permission(db, user, data.acquirer_company_id, "finance.corporate.manage")
    ensure_permission(db, user, data.acquiree_company_id, "finance.corporate.manage")
    method = data.nci_measurement_method.upper()
    if method not in {"FAIR_VALUE", "PROPORTIONATE_SHARE"}:
        raise HTTPException(422, "NCI measurement method must be FAIR_VALUE or PROPORTIONATE_SHARE")
    if method == "FAIR_VALUE" and data.ownership_percent < 1 and data.nci_fair_value <= 0:
        raise HTTPException(422, "NCI fair value is required under the fair-value method")
    if not data.rationale:
        raise HTTPException(422, "Acquisition rationale and judgement documentation is required")

    seen: set[str] = set()
    prepared_items: list[dict] = []
    assets = Decimal("0")
    liabilities = Decimal("0")
    deferred_tax = Decimal("0")
    tax_rate = _rate(data.tax_rate)
    for item in data.items:
        code = item.item_code.strip().upper()
        if code in seen:
            raise HTTPException(422, f"Duplicate PPA item code: {code}")
        seen.add(code)
        item_type = item.item_type.upper()
        if item_type not in {"ASSET", "LIABILITY", "CONTINGENT_LIABILITY"}:
            raise HTTPException(422, f"Unsupported PPA item type: {item_type}")
        fair_value = money(item.fair_value)
        book_value = money(item.book_value)
        tax_base = money(item.tax_base)
        fv_adjustment = money(fair_value - book_value)
        if item_type == "ASSET":
            assets += fair_value
            deferred_effect = money((fair_value - tax_base) * tax_rate)
        else:
            liabilities += fair_value
            deferred_effect = money((tax_base - fair_value) * tax_rate)
        deferred_tax += deferred_effect
        prepared_items.append({
            "item_code": code, "item_type": item_type,
            "name_ar": item.name_ar, "name_en": item.name_en,
            "book_value": book_value, "fair_value": fair_value, "tax_base": tax_base,
            "fair_value_adjustment": fv_adjustment, "deferred_tax_effect": deferred_effect,
            "useful_life_months": item.useful_life_months,
            "identifiable_intangible": item.identifiable_intangible,
            "evidence_reference": item.evidence_reference,
        })
    assets, liabilities, deferred_tax = money(assets), money(liabilities), money(deferred_tax)
    net_assets = money(assets - liabilities - deferred_tax)
    ownership = _rate(data.ownership_percent)
    if ownership == 1:
        nci = Decimal("0")
    elif method == "FAIR_VALUE":
        nci = money(data.nci_fair_value)
    else:
        nci = money(net_assets * (Decimal("1") - ownership))
    consideration = money(data.consideration_cash + data.consideration_shares + data.contingent_consideration + data.previously_held_interest_fv)
    acquisition_value = money(consideration + nci)
    difference = money(acquisition_value - net_assets)
    goodwill = max(difference, Decimal("0"))
    bargain = max(-difference, Decimal("0"))
    row = BusinessCombination(
        group_id=data.group_id, acquirer_company_id=data.acquirer_company_id,
        acquiree_company_id=data.acquiree_company_id, acquisition_date=data.acquisition_date,
        ownership_percent=ownership, nci_measurement_method=method,
        consideration_cash=money(data.consideration_cash), consideration_shares=money(data.consideration_shares),
        contingent_consideration=money(data.contingent_consideration), previously_held_interest_fv=money(data.previously_held_interest_fv),
        nci_fair_value=nci, identifiable_assets_fv=assets, identifiable_liabilities_fv=liabilities,
        deferred_tax_net_liability=deferred_tax, identifiable_net_assets_fv=net_assets,
        acquisition_value=acquisition_value, goodwill=goodwill, bargain_purchase_gain=bargain,
        status="READY_FOR_REVIEW", rationale_payload=_json(data.rationale), prepared_by=user.id,
    )
    row.items = [PurchasePriceAllocationItem(**item) for item in prepared_items]
    db.add(row); db.flush()
    write_audit(db, action="IFRS3_BUSINESS_COMBINATION_PREPARED", entity_type="BUSINESS_COMBINATION", entity_id=row.id,
                user_id=user.id, company_id=data.acquirer_company_id,
                after={"acquiree_company_id": data.acquiree_company_id, "net_assets": str(net_assets), "acquisition_value": str(acquisition_value), "goodwill": str(goodwill), "bargain_purchase_gain": str(bargain)})
    db.commit()
    return {"id": row.id, "status": row.status, "identifiable_assets_fv": assets, "identifiable_liabilities_fv": liabilities,
            "deferred_tax_net_liability": deferred_tax, "identifiable_net_assets_fv": net_assets,
            "nci": nci, "acquisition_value": acquisition_value, "goodwill": goodwill, "bargain_purchase_gain": bargain}


@router.post("/business-combinations/{combination_id}/review")
def review_business_combination(combination_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(BusinessCombination, combination_id)
    if not row:
        raise HTTPException(404, "Business combination not found")
    ensure_permission(db, user, row.acquirer_company_id, "finance.corporate.review")
    _review(row, user)
    write_audit(db, action="IFRS3_BUSINESS_COMBINATION_REVIEWED", entity_type="BUSINESS_COMBINATION", entity_id=row.id, user_id=user.id, company_id=row.acquirer_company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


def _ppa_worksheet_lines(row: BusinessCombination) -> list[dict]:
    lines: list[dict] = []
    line_no = 1
    for item in row.items:
        if item.item_type == "ASSET":
            debit, credit = money(item.fair_value), Decimal("0")
        else:
            debit, credit = Decimal("0"), money(item.fair_value)
        lines.append({"line_number": line_no, "adjustment_type": f"PPA_{item.item_type}", "account_code": f"PPA-{item.item_code}",
                      "description_ar": item.name_ar, "description_en": item.name_en, "debit": debit, "credit": credit,
                      "source_reference": item.evidence_reference})
        line_no += 1
    dt = money(row.deferred_tax_net_liability)
    if dt:
        lines.append({"line_number": line_no, "adjustment_type": "PPA_DEFERRED_TAX", "account_code": "PPA-DEFERRED-TAX",
                      "description_ar": "صافي أثر الضريبة المؤجلة من تخصيص سعر الشراء", "description_en": "Net deferred-tax effect from purchase-price allocation",
                      "debit": abs(dt) if dt < 0 else Decimal("0"), "credit": dt if dt > 0 else Decimal("0"), "source_reference": f"IFRS3-{row.id}-TAX"})
        line_no += 1
    if Decimal(row.goodwill) > 0:
        lines.append({"line_number": line_no, "adjustment_type": "PPA_GOODWILL", "account_code": "PPA-GOODWILL",
                      "description_ar": "الشهرة الناتجة عن الاستحواذ", "description_en": "Goodwill arising on acquisition",
                      "debit": money(row.goodwill), "credit": Decimal("0"), "source_reference": f"IFRS3-{row.id}-VALUATION"})
        line_no += 1
    if Decimal(row.bargain_purchase_gain) > 0:
        lines.append({"line_number": line_no, "adjustment_type": "PPA_BARGAIN_PURCHASE", "account_code": "PPA-BARGAIN-GAIN",
                      "description_ar": "ربح شراء بسعر منخفض", "description_en": "Bargain purchase gain",
                      "debit": Decimal("0"), "credit": money(row.bargain_purchase_gain), "source_reference": f"IFRS3-{row.id}-REASSESSMENT"})
        line_no += 1
    lines.append({"line_number": line_no, "adjustment_type": "PPA_ACQUISITION_VALUE", "account_code": "PPA-ACQUISITION-VALUE",
                  "description_ar": "المقابل المحول والحصة المحتفظ بها وحقوق غير المسيطرين", "description_en": "Consideration, previously held interest and non-controlling interests",
                  "debit": Decimal("0"), "credit": money(row.acquisition_value), "source_reference": f"IFRS3-{row.id}-CONSIDERATION"})
    return lines


@router.post("/business-combinations/{combination_id}/approve")
def approve_business_combination(combination_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(BusinessCombination).where(BusinessCombination.id == combination_id).options(selectinload(BusinessCombination.items)))
    if not row:
        raise HTTPException(404, "Business combination not found")
    ensure_permission(db, user, row.acquirer_company_id, "finance.corporate.approve")
    _approve(row, user)
    lines = _ppa_worksheet_lines(row)
    total_debit = money(sum((Decimal(x["debit"]) for x in lines), Decimal("0")))
    total_credit = money(sum((Decimal(x["credit"]) for x in lines), Decimal("0")))
    difference = money(total_debit - total_credit)
    if difference != 0:
        raise HTTPException(409, f"Generated PPA worksheet is not balanced: {difference}")
    version = _next_version(db, ConsolidationWorksheet, ConsolidationWorksheet.group_id == row.group_id, ConsolidationWorksheet.period_end == row.acquisition_date)
    worksheet = ConsolidationWorksheet(group_id=row.group_id, period_end=row.acquisition_date, version=version,
        worksheet_type="IFRS3_PURCHASE_PRICE_ALLOCATION", reference=f"IFRS3-{row.id}",
        description_ar="تخصيص سعر الشراء وإثبات الشهرة أو ربح الشراء بسعر منخفض",
        description_en="Purchase-price allocation and recognition of goodwill or bargain purchase gain",
        total_debit=total_debit, total_credit=total_credit, balance_difference=0,
        status="APPROVED_FOR_CONSOLIDATION", prepared_by=row.prepared_by, reviewed_by=row.reviewed_by,
        approved_by=user.id, reviewed_at=row.reviewed_at, approved_at=utc_now())
    worksheet.lines = [ConsolidationWorksheetLine(**x) for x in lines]
    db.add(worksheet); db.flush()
    row.status = "APPROVED_FOR_CONSOLIDATION"
    row.worksheet_id = worksheet.id
    write_audit(db, action="IFRS3_BUSINESS_COMBINATION_APPROVED", entity_type="BUSINESS_COMBINATION", entity_id=row.id,
                user_id=user.id, company_id=row.acquirer_company_id,
                after={"status": row.status, "worksheet_id": worksheet.id, "total_debit": str(total_debit), "total_credit": str(total_credit)})
    db.commit()
    return {"id": row.id, "status": row.status, "worksheet_id": worksheet.id, "worksheet_balance": difference, "goodwill": row.goodwill, "bargain_purchase_gain": row.bargain_purchase_gain}


@router.get("/business-combinations")
def list_business_combinations(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    rows = db.scalars(select(BusinessCombination).where(
        (BusinessCombination.acquirer_company_id == company_id) | (BusinessCombination.acquiree_company_id == company_id)
    ).order_by(BusinessCombination.acquisition_date.desc(), BusinessCombination.id.desc())).all()
    return [{"id": r.id, "group_id": r.group_id, "acquirer_company_id": r.acquirer_company_id, "acquiree_company_id": r.acquiree_company_id,
             "acquisition_date": r.acquisition_date, "ownership_percent": r.ownership_percent, "status": r.status,
             "identifiable_net_assets_fv": r.identifiable_net_assets_fv, "acquisition_value": r.acquisition_value,
             "goodwill": r.goodwill, "bargain_purchase_gain": r.bargain_purchase_gain, "worksheet_id": r.worksheet_id} for r in rows]


@router.post("/consolidation-worksheets", status_code=201)
def create_consolidation_worksheet(data: WorksheetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, members = _group_and_members(db, data.group_id)
    for company_id in members:
        ensure_permission(db, user, company_id, "consolidation.manage")
    lines = []
    for idx, item in enumerate(data.lines, start=1):
        if (item.debit > 0) == (item.credit > 0):
            raise HTTPException(422, f"Line {idx} must contain either debit or credit, but not both")
        lines.append(ConsolidationWorksheetLine(line_number=idx, adjustment_type=item.adjustment_type.upper(),
            account_code=item.account_code.upper(), description_ar=item.description_ar, description_en=item.description_en,
            debit=money(item.debit), credit=money(item.credit), source_reference=item.source_reference))
    total_debit = money(sum((Decimal(x.debit) for x in lines), Decimal("0")))
    total_credit = money(sum((Decimal(x.credit) for x in lines), Decimal("0")))
    difference = money(total_debit - total_credit)
    version = _next_version(db, ConsolidationWorksheet, ConsolidationWorksheet.group_id == data.group_id, ConsolidationWorksheet.period_end == data.period_end)
    row = ConsolidationWorksheet(group_id=data.group_id, period_end=data.period_end, version=version,
        worksheet_type=data.worksheet_type.upper(), reference=data.reference, description_ar=data.description_ar, description_en=data.description_en,
        total_debit=total_debit, total_credit=total_credit, balance_difference=difference,
        status="READY_FOR_REVIEW" if difference == 0 else "BLOCKED_UNBALANCED", prepared_by=user.id, lines=lines)
    db.add(row); db.flush()
    write_audit(db, action="CONSOLIDATION_WORKSHEET_CREATED", entity_type="CONSOLIDATION_WORKSHEET", entity_id=row.id, user_id=user.id,
                after={"group_id": data.group_id, "period_end": str(data.period_end), "difference": str(difference), "status": row.status})
    db.commit()
    return {"id": row.id, "version": version, "status": row.status, "total_debit": total_debit, "total_credit": total_credit, "balance_difference": difference}


@router.post("/consolidation-worksheets/{worksheet_id}/review")
def review_consolidation_worksheet(worksheet_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ConsolidationWorksheet, worksheet_id)
    if not row:
        raise HTTPException(404, "Consolidation worksheet not found")
    _, members = _group_and_members(db, row.group_id)
    for company_id in members:
        ensure_permission(db, user, company_id, "finance.corporate.review")
    _review(row, user)
    write_audit(db, action="CONSOLIDATION_WORKSHEET_REVIEWED", entity_type="CONSOLIDATION_WORKSHEET", entity_id=row.id, user_id=user.id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/consolidation-worksheets/{worksheet_id}/approve")
def approve_consolidation_worksheet(worksheet_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ConsolidationWorksheet, worksheet_id)
    if not row:
        raise HTTPException(404, "Consolidation worksheet not found")
    _, members = _group_and_members(db, row.group_id)
    for company_id in members:
        ensure_permission(db, user, company_id, "finance.corporate.approve")
    _approve(row, user)
    if money(row.balance_difference) != 0:
        raise HTTPException(409, "Unbalanced worksheet cannot be approved")
    row.status = "APPROVED_FOR_CONSOLIDATION"
    write_audit(db, action="CONSOLIDATION_WORKSHEET_APPROVED", entity_type="CONSOLIDATION_WORKSHEET", entity_id=row.id, user_id=user.id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status, "balance_difference": row.balance_difference}


@router.get("/consolidation-worksheets")
def list_consolidation_worksheets(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, members = _group_and_members(db, group_id)
    if not any(True for company_id in members if _has_read_permission(db, user, company_id)):
        raise HTTPException(403, "Missing consolidation read permission")
    rows = db.scalars(select(ConsolidationWorksheet).where(ConsolidationWorksheet.group_id == group_id).options(selectinload(ConsolidationWorksheet.lines)).order_by(ConsolidationWorksheet.period_end.desc(), ConsolidationWorksheet.version.desc())).all()
    return [{"id": r.id, "period_end": r.period_end, "version": r.version, "worksheet_type": r.worksheet_type, "reference": r.reference,
             "status": r.status, "total_debit": r.total_debit, "total_credit": r.total_credit, "balance_difference": r.balance_difference,
             "line_count": len(r.lines)} for r in rows]


def _has_read_permission(db: Session, user: User, company_id: int) -> bool:
    try:
        ensure_permission(db, user, company_id, "finance.corporate.read")
        return True
    except HTTPException:
        return False


@router.post("/lead-schedules", status_code=201)
def create_lead_schedule(data: LeadScheduleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    if data.account_code_from > data.account_code_to:
        raise HTTPException(422, "Account range is invalid")
    ledger = _ledger_balance(db, data.company_id, data.account_code_from, data.account_code_to, data.period_end)
    total = money(sum((Decimal(item.amount) for item in data.items), Decimal("0")))
    difference = money(ledger - total)
    version = _next_version(db, LeadSchedule, LeadSchedule.company_id == data.company_id, LeadSchedule.period_end == data.period_end, LeadSchedule.code == data.code.upper())
    row = LeadSchedule(company_id=data.company_id, period_end=data.period_end, code=data.code.upper(), title_ar=data.title_ar, title_en=data.title_en,
        account_code_from=data.account_code_from, account_code_to=data.account_code_to, version=version,
        ledger_balance=ledger, schedule_total=total, difference=difference, status="READY_FOR_REVIEW" if difference == 0 else "BLOCKED_UNRECONCILED",
        conclusion_ar=data.conclusion_ar, conclusion_en=data.conclusion_en, prepared_by=user.id)
    row.items = [LeadScheduleItem(reference=x.reference, description_ar=x.description_ar, description_en=x.description_en, amount=money(x.amount),
        reconciling_item=x.reconciling_item, ageing_days=x.ageing_days, owner=x.owner, due_date=x.due_date, status=x.status.upper()) for x in data.items]
    db.add(row); db.flush()
    write_audit(db, action="LEAD_SCHEDULE_CREATED", entity_type="LEAD_SCHEDULE", entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"ledger_balance": str(ledger), "schedule_total": str(total), "difference": str(difference), "status": row.status})
    db.commit()
    return {"id": row.id, "version": version, "status": row.status, "ledger_balance": ledger, "schedule_total": total, "difference": difference}


@router.post("/lead-schedules/{schedule_id}/evidence", status_code=201)
async def upload_lead_schedule_evidence(schedule_id: int, item_id: int | None = None, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(LeadSchedule).where(LeadSchedule.id == schedule_id).options(selectinload(LeadSchedule.items)))
    if not row:
        raise HTTPException(404, "Lead schedule not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.manage")
    if row.status not in {"READY_FOR_REVIEW", "BLOCKED_UNRECONCILED", "DRAFT"}:
        raise HTTPException(409, "Evidence cannot be changed after review")
    if item_id is not None and item_id not in {x.id for x in row.items}:
        raise HTTPException(422, "Lead-schedule item does not belong to this schedule")
    payload = await file.read(MAX_EVIDENCE_BYTES + 1)
    if not payload:
        raise HTTPException(422, "Evidence file is empty")
    if len(payload) > MAX_EVIDENCE_BYTES:
        raise HTTPException(413, "Evidence file exceeds 10 MB")
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_EVIDENCE_TYPES:
        raise HTTPException(415, "Unsupported evidence file type")
    digest = hashlib.sha256(payload).hexdigest()
    duplicate = db.scalar(select(FinancialEvidence.id).where(FinancialEvidence.schedule_id == row.id, FinancialEvidence.sha256 == digest))
    if duplicate:
        raise HTTPException(409, "The same evidence file is already attached")
    safe_name = Path(file.filename or "evidence.bin").name
    directory = EVIDENCE_ROOT / str(row.company_id) / str(row.id)
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{digest[:16]}_{safe_name}"
    path = directory / stored_name
    path.write_bytes(payload)
    evidence = FinancialEvidence(schedule_id=row.id, item_id=item_id, file_name=safe_name, storage_path=str(path.relative_to(BACKEND_ROOT)), mime_type=mime,
        size_bytes=len(payload), sha256=digest, uploaded_by=user.id)
    db.add(evidence); db.flush()
    write_audit(db, action="LEAD_SCHEDULE_EVIDENCE_UPLOADED", entity_type="FINANCIAL_EVIDENCE", entity_id=evidence.id, user_id=user.id, company_id=row.company_id,
                after={"schedule_id": row.id, "item_id": item_id, "file_name": safe_name, "sha256": digest, "size_bytes": len(payload)})
    db.commit()
    return {"id": evidence.id, "file_name": safe_name, "mime_type": mime, "size_bytes": len(payload), "sha256": digest}


@router.post("/lead-schedules/{schedule_id}/review")
def review_lead_schedule(schedule_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(LeadSchedule).where(LeadSchedule.id == schedule_id).options(selectinload(LeadSchedule.items), selectinload(LeadSchedule.evidence)))
    if not row:
        raise HTTPException(404, "Lead schedule not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.review")
    if money(row.difference) != 0:
        raise HTTPException(409, "Lead schedule is not reconciled to the general ledger")
    if not row.evidence:
        raise HTTPException(409, "At least one supporting evidence file is required")
    overdue_open = [x.reference for x in row.items if x.reconciling_item and x.status not in {"RESOLVED", "CLOSED"} and x.due_date and x.due_date < row.period_end]
    if overdue_open:
        raise HTTPException(409, f"Overdue reconciling items must be resolved: {', '.join(overdue_open)}")
    _review(row, user)
    write_audit(db, action="LEAD_SCHEDULE_REVIEWED", entity_type="LEAD_SCHEDULE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status, "evidence_count": len(row.evidence)})
    db.commit()
    return {"id": row.id, "status": row.status, "evidence_count": len(row.evidence)}


@router.post("/lead-schedules/{schedule_id}/approve")
def approve_lead_schedule(schedule_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(LeadSchedule, schedule_id)
    if not row:
        raise HTTPException(404, "Lead schedule not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    _approve(row, user)
    row.status = "APPROVED_AND_SIGNED"
    write_audit(db, action="LEAD_SCHEDULE_APPROVED_SIGNED", entity_type="LEAD_SCHEDULE", entity_id=row.id, user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "difference": str(row.difference)})
    db.commit()
    return {"id": row.id, "status": row.status, "difference": row.difference, "approved_by": row.approved_by}


@router.get("/lead-schedules")
def list_lead_schedules(company_id: int, period_end: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    conditions = [LeadSchedule.company_id == company_id]
    if period_end:
        conditions.append(LeadSchedule.period_end == period_end)
    rows = db.scalars(select(LeadSchedule).where(*conditions).options(selectinload(LeadSchedule.evidence)).order_by(LeadSchedule.period_end.desc(), LeadSchedule.code, LeadSchedule.version.desc())).all()
    return [{"id": r.id, "period_end": r.period_end, "code": r.code, "version": r.version, "title_ar": r.title_ar, "title_en": r.title_en,
             "ledger_balance": r.ledger_balance, "schedule_total": r.schedule_total, "difference": r.difference, "status": r.status,
             "evidence_count": len(r.evidence), "prepared_by": r.prepared_by, "reviewed_by": r.reviewed_by, "approved_by": r.approved_by} for r in rows]


@router.post("/lease-partial-terminations", status_code=201)
def create_lease_partial_termination(data: LeasePartialTerminationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lease = db.scalar(select(LeaseContract).where(LeaseContract.id == data.lease_id).options(selectinload(LeaseContract.schedules)))
    if not lease:
        raise HTTPException(404, "Lease not found")
    ensure_permission(db, user, lease.company_id, "leases.modify")
    if lease.status != "ACTIVE":
        raise HTTPException(409, "Only active leases can be partially terminated")
    affected = sorted((s for s in lease.schedules if s.status == "PENDING" and s.payment_date >= data.effective_date), key=lambda x: x.period_number)
    if not affected:
        raise HTTPException(422, "No unposted future lease schedule is available")
    carrying_liability = money(affected[0].opening_liability)
    carrying_rou = _carrying_rou(db, lease, data.effective_date)
    pct = _rate(data.reduction_percent)
    liability_reduction = money(carrying_liability * pct)
    rou_reduction = money(carrying_rou * pct)
    gain_loss = money(liability_reduction - rou_reduction)
    row = LeasePartialTermination(lease_id=lease.id, effective_date=data.effective_date, reduction_percent=pct, reason=data.reason,
        carrying_liability=carrying_liability, carrying_rou_asset=carrying_rou, liability_reduction=liability_reduction,
        rou_reduction=rou_reduction, gain_loss=gain_loss, created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="IFRS16_PARTIAL_TERMINATION_CREATED", entity_type="LEASE_PARTIAL_TERMINATION", entity_id=row.id,
                user_id=user.id, company_id=lease.company_id,
                after={"lease": lease.number, "reduction_percent": str(pct), "liability_reduction": str(liability_reduction), "rou_reduction": str(rou_reduction), "gain_loss": str(gain_loss)})
    db.commit()
    return {"id": row.id, "status": row.status, "carrying_liability": carrying_liability, "carrying_rou_asset": carrying_rou,
            "liability_reduction": liability_reduction, "rou_reduction": rou_reduction, "gain_loss": gain_loss}


@router.post("/lease-partial-terminations/{termination_id}/approve")
def approve_lease_partial_termination(termination_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(LeasePartialTermination).where(LeasePartialTermination.id == termination_id).options(selectinload(LeasePartialTermination.lease).selectinload(LeaseContract.schedules)))
    if not row:
        raise HTTPException(404, "Lease partial termination not found")
    lease = row.lease
    ensure_permission(db, user, lease.company_id, "leases.modify.approve")
    if row.status != "DRAFT":
        raise HTTPException(409, "Lease partial termination is not in draft status")
    if row.created_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot approve lease termination")
    affected = [s for s in lease.schedules if s.status == "PENDING" and s.payment_date >= row.effective_date]
    if not affected:
        raise HTTPException(409, "Future lease schedule was already posted or changed")
    liability_account = get_account(db, lease.company_id, "222010")
    rou_account = get_account(db, lease.company_id, "152010")
    gain_account = get_account(db, lease.company_id, "421010")
    loss_account = get_account(db, lease.company_id, "621010")
    liability_reduction = money(row.liability_reduction)
    rou_reduction = money(row.rou_reduction)
    gain_loss = money(row.gain_loss)
    lines = [{"account_id": liability_account.id, "debit": liability_reduction, "credit": 0},
             {"account_id": rou_account.id, "debit": 0, "credit": rou_reduction}]
    if gain_loss > 0:
        lines.append({"account_id": gain_account.id, "debit": 0, "credit": gain_loss})
    elif gain_loss < 0:
        lines.append({"account_id": loss_account.id, "debit": abs(gain_loss), "credit": 0})
    journal = create_posted_journal(db, company_id=lease.company_id, user_id=user.id, posting_date=row.effective_date,
        reference=f"LEASE-SCOPE-{lease.number}-{row.id}", description=f"IFRS 16 partial termination {lease.number}", lines=lines)
    remaining = Decimal("1") - Decimal(row.reduction_percent)
    for schedule in affected:
        schedule.opening_liability = money(Decimal(schedule.opening_liability) * remaining)
        schedule.interest = money(Decimal(schedule.interest) * remaining)
        schedule.payment = money(Decimal(schedule.payment) * remaining)
        schedule.principal = money(Decimal(schedule.principal) * remaining)
        schedule.closing_liability = money(Decimal(schedule.closing_liability) * remaining)
        schedule.depreciation = money(Decimal(schedule.depreciation) * remaining)
    lease.payment_amount = money(Decimal(lease.payment_amount) * remaining)
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.journal_id = journal.id
    write_audit(db, action="IFRS16_PARTIAL_TERMINATION_APPROVED", entity_type="LEASE_PARTIAL_TERMINATION", entity_id=row.id,
                user_id=user.id, company_id=lease.company_id,
                after={"journal": journal.number, "remaining_scope": str(remaining), "affected_periods": len(affected), "gain_loss": str(gain_loss)})
    db.commit()
    return {"id": row.id, "status": row.status, "journal": journal.number, "affected_periods": len(affected),
            "remaining_scope": remaining, "gain_loss": gain_loss}


@router.get("/lease-partial-terminations")
def list_lease_partial_terminations(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    rows = db.scalars(select(LeasePartialTermination).join(LeaseContract).where(LeaseContract.company_id == company_id).options(selectinload(LeasePartialTermination.lease)).order_by(LeasePartialTermination.effective_date.desc(), LeasePartialTermination.id.desc())).all()
    return [{"id": r.id, "lease_number": r.lease.number, "effective_date": r.effective_date, "reduction_percent": r.reduction_percent,
             "carrying_liability": r.carrying_liability, "carrying_rou_asset": r.carrying_rou_asset,
             "liability_reduction": r.liability_reduction, "rou_reduction": r.rou_reduction, "gain_loss": r.gain_loss,
             "status": r.status, "journal_id": r.journal_id} for r in rows]


@router.get("/dashboard")
def close_dashboard(company_id: int, period_end: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    approved_leads = db.scalar(select(func.count(LeadSchedule.id)).where(LeadSchedule.company_id == company_id, LeadSchedule.status == "APPROVED_AND_SIGNED", *( [LeadSchedule.period_end == period_end] if period_end else [] ))) or 0
    unreconciled_leads = db.scalar(select(func.count(LeadSchedule.id)).where(LeadSchedule.company_id == company_id, LeadSchedule.status == "BLOCKED_UNRECONCILED", *( [LeadSchedule.period_end == period_end] if period_end else [] ))) or 0
    combinations = db.scalar(select(func.count(BusinessCombination.id)).where(BusinessCombination.acquirer_company_id == company_id, BusinessCombination.status == "APPROVED_FOR_CONSOLIDATION")) or 0
    partial_terms = db.scalar(select(func.count(LeasePartialTermination.id)).join(LeaseContract).where(LeaseContract.company_id == company_id, LeasePartialTermination.status == "APPROVED_POSTED")) or 0
    return {"company_id": company_id, "period_end": period_end,
            "approved_signed_lead_schedules": approved_leads, "unreconciled_lead_schedules": unreconciled_leads,
            "approved_business_combinations": combinations, "approved_partial_lease_terminations": partial_terms}
