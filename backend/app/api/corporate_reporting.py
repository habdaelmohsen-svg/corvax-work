from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, Company, ConsolidationGroup, ConsolidationMember, CorporateFinanceConfig,
    DeferredTaxItem, DeferredTaxRun, EarningsPerShareRun, FinancialReportRun,
    ForeignOperationTranslationRun, GoodwillImpairmentTest, JournalEntry, JournalLine,
    ManagementPerformanceMeasure, OperatingSegment, SegmentReportLine, SegmentReportRun, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/corporate-reporting", tags=["corporate reporting and tax"])
Q = Decimal("0.01")
R6 = Decimal("0.000001")
POSTED = ("POSTED", "REVERSED")
CONFIG_CODES = {
    "deferred_tax_asset_account_id": "154010",
    "deferred_tax_liability_account_id": "223010",
    "deferred_tax_expense_account_id": "812010",
    "deferred_tax_oci_account_id": "313020",
    "impairment_expense_account_id": "620010",
    "accumulated_impairment_account_id": "154030",
}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _loads(value: str):
    return json.loads(value)


def _rate(value: Decimal | float | str) -> Decimal:
    return Decimal(str(value)).quantize(R6, rounding=ROUND_HALF_UP)


def _version(db: Session, model, company_id: int, period_end: date) -> int:
    return int(db.scalar(select(func.max(model.version)).where(model.company_id == company_id, model.period_end == period_end)) or 0) + 1


def _approved_config(db: Session, company_id: int) -> CorporateFinanceConfig:
    config = db.scalar(select(CorporateFinanceConfig).where(CorporateFinanceConfig.company_id == company_id))
    if not config or config.status != "APPROVED":
        raise HTTPException(409, "Approved corporate finance account configuration is required")
    return config


def _three_step_review(row, user: User, *, draft_statuses: set[str] | None = None) -> None:
    allowed = draft_statuses or {"DRAFT", "READY_FOR_REVIEW"}
    if row.status not in allowed:
        raise HTTPException(409, "Record is not ready for review")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot review this record")
    row.status = "REVIEWED"
    row.reviewed_by = user.id
    row.reviewed_at = utc_now()


def _three_step_approve(row, user: User) -> None:
    if row.status != "REVIEWED":
        raise HTTPException(409, "Record must be reviewed before final approval")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot approve this record")
    if row.reviewed_by == user.id:
        raise HTTPException(409, "Three-step control: reviewer cannot be final approver")
    row.approved_by = user.id
    row.approved_at = utc_now()


class CompanyIn(BaseModel):
    company_id: int


class DeferredTaxItemIn(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    description_ar: str = Field(min_length=1, max_length=500)
    description_en: str = Field(min_length=1, max_length=500)
    source_account_id: int | None = None
    carrying_amount: Decimal
    tax_base: Decimal
    difference_type: str
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    recognition_status: str = "RECOGNIZED"
    presentation_basis: str = "PNL"
    recoverability_evidence: str | None = None


class DeferredTaxRunIn(BaseModel):
    company_id: int
    period_end: date
    default_tax_rate: Decimal = Field(ge=0, le=1)
    items: list[DeferredTaxItemIn] = Field(min_length=1)


class GoodwillTestIn(BaseModel):
    company_id: int
    period_end: date
    cgu_code: str = Field(min_length=1, max_length=50)
    cgu_name_ar: str
    cgu_name_en: str
    goodwill_carrying_amount: Decimal = Field(ge=0)
    other_assets_carrying_amount: Decimal = Field(ge=0)
    value_in_use: Decimal = Field(ge=0)
    fair_value_less_costs: Decimal = Field(ge=0)
    assumptions: dict
    sensitivity: dict


class TranslationRunIn(BaseModel):
    group_id: int
    member_company_id: int
    period_start: date
    period_end: date
    closing_rate: Decimal = Field(gt=0)
    average_rate: Decimal = Field(gt=0)
    historical_equity_rate: Decimal = Field(gt=0)


class MPMAdjustmentIn(BaseModel):
    label_ar: str
    label_en: str
    amount: Decimal
    tax_effect: Decimal = Decimal("0")
    nci_effect: Decimal = Decimal("0")
    supporting_reference: str = Field(min_length=1, max_length=500)


class MPMIn(BaseModel):
    company_id: int
    period_end: date
    code: str = Field(min_length=1, max_length=50)
    name_ar: str
    name_en: str
    explanation_ar: str = Field(min_length=20)
    explanation_en: str = Field(min_length=20)
    base_report_run_id: int
    base_subtotal_code: str
    adjustments: list[MPMAdjustmentIn] = Field(min_length=1)


class EPSIn(BaseModel):
    company_id: int
    period_end: date
    profit_attributable: Decimal
    preference_dividends: Decimal = Decimal("0")
    weighted_average_shares: Decimal = Field(gt=0)
    diluted_profit_adjustment: Decimal = Decimal("0")
    incremental_shares: Decimal = Field(default=Decimal("0"), ge=0)
    support_reference: str = Field(min_length=5, max_length=500)


class SegmentIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=50)
    name_ar: str
    name_en: str
    codm_title: str = Field(min_length=2, max_length=250)
    reportable: bool = True


class SegmentLineIn(BaseModel):
    segment_id: int
    external_revenue: Decimal = Decimal("0")
    intersegment_revenue: Decimal = Decimal("0")
    segment_profit: Decimal = Decimal("0")
    segment_assets: Decimal = Decimal("0")
    segment_liabilities: Decimal = Decimal("0")
    measurement_basis: str = Field(min_length=5, max_length=500)


class SegmentReportIn(BaseModel):
    company_id: int
    period_end: date
    base_report_run_id: int
    lines: list[SegmentLineIn] = Field(min_length=1)


@router.post("/config/bootstrap")
def bootstrap_config(data: CompanyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    accounts = {a.code: a for a in db.scalars(select(Account).where(Account.company_id == data.company_id)).all()}
    missing = [code for code in CONFIG_CODES.values() if code not in accounts or not accounts[code].is_postable]
    if missing:
        raise HTTPException(422, f"Required postable accounts are missing: {', '.join(missing)}")
    values = {field: accounts[code].id for field, code in CONFIG_CODES.items()}
    row = db.scalar(select(CorporateFinanceConfig).where(CorporateFinanceConfig.company_id == data.company_id))
    if row:
        for field, value in values.items():
            setattr(row, field, value)
        row.status = "DRAFT"
        row.configured_by = user.id
        row.approved_by = None
        row.approved_at = None
        action = "CORPORATE_FINANCE_CONFIG_REBUILT"
    else:
        row = CorporateFinanceConfig(company_id=data.company_id, configured_by=user.id, **values)
        db.add(row)
        db.flush()
        action = "CORPORATE_FINANCE_CONFIG_BOOTSTRAPPED"
    write_audit(db, action=action, entity_type="CORPORATE_FINANCE_CONFIG", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"status": row.status, "account_codes": CONFIG_CODES})
    db.commit()
    return {"id": row.id, "company_id": row.company_id, "status": row.status, "account_codes": CONFIG_CODES}


@router.post("/config/{config_id}/approve")
def approve_config(config_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CorporateFinanceConfig, config_id)
    if not row:
        raise HTTPException(404, "Corporate finance configuration not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    if row.configured_by == user.id:
        raise HTTPException(409, "Maker-checker: configuration owner cannot approve it")
    row.status = "APPROVED"
    row.approved_by = user.id
    row.approved_at = utc_now()
    write_audit(db, action="CORPORATE_FINANCE_CONFIG_APPROVED", entity_type="CORPORATE_FINANCE_CONFIG", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status, "approved_by": row.approved_by}


@router.get("/config")
def read_config(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    row = db.scalar(select(CorporateFinanceConfig).where(CorporateFinanceConfig.company_id == company_id))
    if not row:
        raise HTTPException(404, "Corporate finance configuration not found")
    return {"id": row.id, "company_id": company_id, "status": row.status, "configured_by": row.configured_by, "approved_by": row.approved_by,
            "accounts": {field: getattr(row, field) for field in CONFIG_CODES}}


@router.post("/deferred-tax-runs", status_code=201)
def create_deferred_tax_run(data: DeferredTaxRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    default_rate = _rate(data.default_tax_rate)
    seen: set[str] = set()
    recognized_dta = Decimal("0")
    recognized_dtl = Decimal("0")
    unrecognized_dta = Decimal("0")
    prepared: list[dict] = []
    for item in data.items:
        if item.reference in seen:
            raise HTTPException(422, f"Duplicate deferred-tax reference: {item.reference}")
        seen.add(item.reference)
        difference_type = item.difference_type.upper()
        recognition = item.recognition_status.upper()
        basis = item.presentation_basis.upper()
        if difference_type not in {"TAXABLE", "DEDUCTIBLE"}:
            raise HTTPException(422, "difference_type must be TAXABLE or DEDUCTIBLE")
        if recognition not in {"RECOGNIZED", "UNRECOGNIZED"}:
            raise HTTPException(422, "recognition_status must be RECOGNIZED or UNRECOGNIZED")
        if basis not in {"PNL", "OCI", "EQUITY"}:
            raise HTTPException(422, "presentation_basis must be PNL, OCI or EQUITY")
        if item.source_account_id:
            account = db.get(Account, item.source_account_id)
            if not account or account.company_id != data.company_id:
                raise HTTPException(422, "Deferred-tax source account must belong to the selected company")
        carrying = money(item.carrying_amount)
        tax_base = money(item.tax_base)
        temporary = money(carrying - tax_base)
        rate = _rate(item.tax_rate if item.tax_rate is not None else default_rate)
        effect = money(abs(temporary) * rate)
        if difference_type == "DEDUCTIBLE" and recognition == "RECOGNIZED" and effect > 0:
            if not item.recoverability_evidence or len(item.recoverability_evidence.strip()) < 10:
                raise HTTPException(422, f"Recoverability evidence is required for recognized DTA item {item.reference}")
            recognized_dta += effect
        elif difference_type == "DEDUCTIBLE":
            unrecognized_dta += effect
        elif recognition == "RECOGNIZED":
            recognized_dtl += effect
        prepared.append({**item.model_dump(), "difference_type": difference_type, "recognition_status": recognition, "presentation_basis": basis,
                         "carrying_amount": carrying, "tax_base": tax_base, "temporary_difference": temporary, "tax_rate": rate, "tax_effect": effect})
    version = _version(db, DeferredTaxRun, data.company_id, data.period_end)
    row = DeferredTaxRun(company_id=data.company_id, period_end=data.period_end, version=version, default_tax_rate=default_rate,
                         total_recognized_dta=money(recognized_dta), total_recognized_dtl=money(recognized_dtl),
                         total_unrecognized_dta=money(unrecognized_dta), net_deferred_tax_position=money(recognized_dta - recognized_dtl), prepared_by=user.id)
    db.add(row)
    db.flush()
    for item in prepared:
        row.items.append(DeferredTaxItem(**item))
    write_audit(db, action="DEFERRED_TAX_RUN_CREATED", entity_type="DEFERRED_TAX_RUN", entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"period_end": str(data.period_end), "version": version, "dta": str(row.total_recognized_dta), "dtl": str(row.total_recognized_dtl), "unrecognized_dta": str(row.total_unrecognized_dta)})
    db.commit()
    return {"id": row.id, "version": version, "status": row.status, "recognized_dta": row.total_recognized_dta,
            "recognized_dtl": row.total_recognized_dtl, "unrecognized_dta": row.total_unrecognized_dta, "net_position": row.net_deferred_tax_position}


@router.post("/deferred-tax-runs/{run_id}/review")
def review_deferred_tax(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(DeferredTaxRun).where(DeferredTaxRun.id == run_id).options(selectinload(DeferredTaxRun.items)))
    if not row:
        raise HTTPException(404, "Deferred-tax run not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.review")
    _approved_config(db, row.company_id)
    if not row.items:
        raise HTTPException(422, "Deferred-tax run has no items")
    _three_step_review(row, user)
    write_audit(db, action="DEFERRED_TAX_RUN_REVIEWED", entity_type="DEFERRED_TAX_RUN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status, "reviewed_by": row.reviewed_by}


def _append_amount(bucket: dict[int, dict[str, Decimal]], account_id: int, *, debit: Decimal = Decimal("0"), credit: Decimal = Decimal("0")) -> None:
    line = bucket.setdefault(account_id, {"debit": Decimal("0"), "credit": Decimal("0")})
    line["debit"] += money(debit)
    line["credit"] += money(credit)


@router.post("/deferred-tax-runs/{run_id}/approve-post")
def approve_post_deferred_tax(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(DeferredTaxRun).where(DeferredTaxRun.id == run_id).options(selectinload(DeferredTaxRun.items)))
    if not row:
        raise HTTPException(404, "Deferred-tax run not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    _three_step_approve(row, user)
    config = _approved_config(db, row.company_id)
    buckets: dict[int, dict[str, Decimal]] = {}
    for item in row.items:
        if item.recognition_status != "RECOGNIZED" or Decimal(item.tax_effect) == 0:
            continue
        offset_id = config.deferred_tax_expense_account_id if item.presentation_basis == "PNL" else config.deferred_tax_oci_account_id
        amount = money(item.tax_effect)
        if item.difference_type == "DEDUCTIBLE":
            _append_amount(buckets, config.deferred_tax_asset_account_id, debit=amount)
            _append_amount(buckets, offset_id, credit=amount)
        else:
            _append_amount(buckets, offset_id, debit=amount)
            _append_amount(buckets, config.deferred_tax_liability_account_id, credit=amount)
    lines = []
    for account_id, amounts in buckets.items():
        net = money(amounts["debit"] - amounts["credit"])
        if net > 0:
            lines.append({"account_id": account_id, "debit": net, "credit": Decimal("0")})
        elif net < 0:
            lines.append({"account_id": account_id, "debit": Decimal("0"), "credit": abs(net)})
    if lines:
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.period_end,
                                        reference=f"DTA-DTL-{row.period_end}-V{row.version}", description="Deferred tax recognition and measurement", lines=lines)
        row.journal_id = journal.id
        row.status = "APPROVED_POSTED"
    else:
        row.status = "APPROVED_NO_POSTING"
    write_audit(db, action="DEFERRED_TAX_RUN_APPROVED", entity_type="DEFERRED_TAX_RUN", entity_id=row.id, user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "journal_id": row.journal_id, "net_position": str(row.net_deferred_tax_position)})
    db.commit()
    return {"id": row.id, "status": row.status, "journal_id": row.journal_id, "net_position": row.net_deferred_tax_position}


@router.get("/deferred-tax-runs/{run_id}")
def read_deferred_tax(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(DeferredTaxRun).where(DeferredTaxRun.id == run_id).options(selectinload(DeferredTaxRun.items)))
    if not row:
        raise HTTPException(404, "Deferred-tax run not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.read")
    return {"id": row.id, "company_id": row.company_id, "period_end": row.period_end, "version": row.version, "status": row.status,
            "totals": {"recognized_dta": row.total_recognized_dta, "recognized_dtl": row.total_recognized_dtl,
                       "unrecognized_dta": row.total_unrecognized_dta, "net_position": row.net_deferred_tax_position},
            "items": [{"id": x.id, "reference": x.reference, "carrying_amount": x.carrying_amount, "tax_base": x.tax_base,
                       "temporary_difference": x.temporary_difference, "difference_type": x.difference_type, "tax_rate": x.tax_rate,
                       "tax_effect": x.tax_effect, "recognition_status": x.recognition_status, "presentation_basis": x.presentation_basis,
                       "recoverability_evidence": x.recoverability_evidence} for x in row.items]}


@router.post("/goodwill-impairment-tests", status_code=201)
def create_goodwill_test(data: GoodwillTestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    if len(data.assumptions) < 3 or len(data.sensitivity) < 1:
        raise HTTPException(422, "At least three valuation assumptions and one sensitivity scenario are required")
    carrying = money(data.goodwill_carrying_amount + data.other_assets_carrying_amount)
    recoverable = max(money(data.value_in_use), money(data.fair_value_less_costs))
    impairment = money(max(carrying - recoverable, Decimal("0")))
    goodwill_impairment = money(min(impairment, data.goodwill_carrying_amount))
    other_impairment = money(max(impairment - goodwill_impairment, Decimal("0")))
    row = GoodwillImpairmentTest(company_id=data.company_id, period_end=data.period_end, cgu_code=data.cgu_code,
                                  cgu_name_ar=data.cgu_name_ar, cgu_name_en=data.cgu_name_en,
                                  goodwill_carrying_amount=money(data.goodwill_carrying_amount), other_assets_carrying_amount=money(data.other_assets_carrying_amount),
                                  value_in_use=money(data.value_in_use), fair_value_less_costs=money(data.fair_value_less_costs), recoverable_amount=recoverable,
                                  impairment_loss=impairment, goodwill_impairment=goodwill_impairment, other_asset_impairment=other_impairment,
                                  assumptions_payload=_json(data.assumptions), sensitivity_payload=_json(data.sensitivity), prepared_by=user.id)
    db.add(row)
    db.flush()
    write_audit(db, action="GOODWILL_IMPAIRMENT_TEST_CREATED", entity_type="GOODWILL_IMPAIRMENT_TEST", entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"cgu": row.cgu_code, "carrying_amount": str(carrying), "recoverable_amount": str(recoverable), "impairment_loss": str(impairment)})
    db.commit()
    return {"id": row.id, "status": row.status, "recoverable_amount": row.recoverable_amount, "impairment_loss": row.impairment_loss,
            "goodwill_impairment": row.goodwill_impairment, "other_asset_impairment": row.other_asset_impairment}


@router.post("/goodwill-impairment-tests/{test_id}/review")
def review_goodwill_test(test_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(GoodwillImpairmentTest, test_id)
    if not row:
        raise HTTPException(404, "Goodwill impairment test not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.review")
    _approved_config(db, row.company_id)
    _three_step_review(row, user)
    write_audit(db, action="GOODWILL_IMPAIRMENT_TEST_REVIEWED", entity_type="GOODWILL_IMPAIRMENT_TEST", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/goodwill-impairment-tests/{test_id}/approve-post")
def approve_goodwill_test(test_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(GoodwillImpairmentTest, test_id)
    if not row:
        raise HTTPException(404, "Goodwill impairment test not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    _three_step_approve(row, user)
    config = _approved_config(db, row.company_id)
    amount = money(row.impairment_loss)
    if amount > 0:
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.period_end,
                                        reference=f"IAS36-{row.cgu_code}-{row.period_end}", description=f"CGU impairment loss {row.cgu_code}",
                                        lines=[{"account_id": config.impairment_expense_account_id, "debit": amount, "credit": 0},
                                               {"account_id": config.accumulated_impairment_account_id, "debit": 0, "credit": amount}])
        row.journal_id = journal.id
        row.status = "APPROVED_POSTED"
    else:
        row.status = "APPROVED_NO_IMPAIRMENT"
    write_audit(db, action="GOODWILL_IMPAIRMENT_TEST_APPROVED", entity_type="GOODWILL_IMPAIRMENT_TEST", entity_id=row.id, user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "journal_id": row.journal_id, "impairment_loss": str(row.impairment_loss)})
    db.commit()
    return {"id": row.id, "status": row.status, "journal_id": row.journal_id, "impairment_loss": row.impairment_loss}


def _account_type_amounts(db: Session, company_id: int, start: date | None, end: date) -> dict[str, Decimal]:
    conditions = [Account.company_id == company_id, JournalEntry.status.in_(POSTED), JournalEntry.entry_date <= end]
    if start:
        conditions.append(JournalEntry.entry_date >= start)
    rows = db.execute(select(Account.account_type, func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
                      .join(JournalLine, JournalLine.account_id == Account.id).join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
                      .where(*conditions).group_by(Account.account_type)).all()
    result = defaultdict(lambda: Decimal("0"))
    for account_type, debit, credit in rows:
        d, c = Decimal(debit), Decimal(credit)
        if account_type == "ASSET":
            result[account_type] += d - c
        elif account_type in {"LIABILITY", "EQUITY", "REVENUE"}:
            result[account_type] += c - d
        elif account_type == "EXPENSE":
            result[account_type] += d - c
    return result


@router.post("/foreign-operation-translations", status_code=201)
def create_translation(data: TranslationRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.get(ConsolidationGroup, data.group_id)
    company = db.get(Company, data.member_company_id)
    member = db.scalar(select(ConsolidationMember).where(ConsolidationMember.group_id == data.group_id, ConsolidationMember.company_id == data.member_company_id))
    if not group or not company or not member:
        raise HTTPException(404, "Consolidation group member not found")
    ensure_permission(db, user, data.member_company_id, "finance.corporate.manage")
    if data.period_start > data.period_end:
        raise HTTPException(422, "period_start must not be after period_end")
    closing = _account_type_amounts(db, company.id, None, data.period_end)
    activity = _account_type_amounts(db, company.id, data.period_start, data.period_end)
    assets = money(closing["ASSET"])
    liabilities = money(closing["LIABILITY"])
    equity = money(closing["EQUITY"])
    revenue = money(activity["REVENUE"])
    expenses = money(activity["EXPENSE"])
    closing_rate, average_rate, historical_rate = _rate(data.closing_rate), _rate(data.average_rate), _rate(data.historical_equity_rate)
    translated_net_assets = money((assets - liabilities) * closing_rate)
    translated_equity = money(equity * historical_rate)
    translated_profit = money((revenue - expenses) * average_rate)
    cta = money(translated_net_assets - translated_equity - translated_profit)
    row = ForeignOperationTranslationRun(group_id=group.id, member_company_id=company.id, period_start=data.period_start, period_end=data.period_end,
                                          functional_currency=company.currency, reporting_currency=group.reporting_currency,
                                          closing_rate=closing_rate, average_rate=average_rate, historical_equity_rate=historical_rate,
                                          foreign_assets=assets, foreign_liabilities=liabilities, foreign_equity=equity,
                                          foreign_revenue=revenue, foreign_expenses=expenses, translated_net_assets=translated_net_assets,
                                          translated_equity=translated_equity, translated_profit=translated_profit, cta_amount=cta, prepared_by=user.id)
    db.add(row)
    db.flush()
    write_audit(db, action="FOREIGN_OPERATION_TRANSLATION_CREATED", entity_type="FOREIGN_OPERATION_TRANSLATION", entity_id=row.id, user_id=user.id, company_id=company.id,
                after={"group_id": group.id, "period_end": str(data.period_end), "cta_amount": str(cta), "rates": {"closing": str(closing_rate), "average": str(average_rate), "historical": str(historical_rate)}})
    db.commit()
    return {"id": row.id, "status": row.status, "functional_currency": row.functional_currency, "reporting_currency": row.reporting_currency,
            "translated_net_assets": row.translated_net_assets, "translated_profit": row.translated_profit, "cta_amount": row.cta_amount}


@router.post("/foreign-operation-translations/{run_id}/review")
def review_translation(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ForeignOperationTranslationRun, run_id)
    if not row:
        raise HTTPException(404, "Foreign-operation translation not found")
    ensure_permission(db, user, row.member_company_id, "finance.corporate.review")
    _three_step_review(row, user)
    write_audit(db, action="FOREIGN_OPERATION_TRANSLATION_REVIEWED", entity_type="FOREIGN_OPERATION_TRANSLATION", entity_id=row.id, user_id=user.id, company_id=row.member_company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/foreign-operation-translations/{run_id}/approve")
def approve_translation(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ForeignOperationTranslationRun, run_id)
    if not row:
        raise HTTPException(404, "Foreign-operation translation not found")
    ensure_permission(db, user, row.member_company_id, "finance.corporate.approve")
    _three_step_approve(row, user)
    row.status = "APPROVED_FOR_CONSOLIDATION"
    write_audit(db, action="FOREIGN_OPERATION_TRANSLATION_APPROVED", entity_type="FOREIGN_OPERATION_TRANSLATION", entity_id=row.id, user_id=user.id, company_id=row.member_company_id,
                after={"status": row.status, "cta_amount": str(row.cta_amount)})
    db.commit()
    return {"id": row.id, "status": row.status, "cta_amount": row.cta_amount}


@router.post("/management-performance-measures", status_code=201)
def create_mpm(data: MPMIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    report = db.get(FinancialReportRun, data.base_report_run_id)
    if not report or report.company_id != data.company_id or report.end_date != data.period_end or report.status != "APPROVED":
        raise HTTPException(422, "An approved IFRS 18 report for the same company and period is required")
    payload = _loads(report.report_payload)
    subtotals = payload.get("subtotals", {}).get("current", {})
    if data.base_subtotal_code not in subtotals:
        raise HTTPException(422, "Selected IFRS subtotal is not available in the approved report")
    base_amount = money(subtotals[data.base_subtotal_code])
    adjustments = [x.model_dump() for x in data.adjustments]
    total_adjustments = money(sum((x.amount for x in data.adjustments), Decimal("0")))
    tax_effect = money(sum((x.tax_effect for x in data.adjustments), Decimal("0")))
    nci_effect = money(sum((x.nci_effect for x in data.adjustments), Decimal("0")))
    row = ManagementPerformanceMeasure(company_id=data.company_id, period_end=data.period_end, code=data.code,
                                       name_ar=data.name_ar, name_en=data.name_en, explanation_ar=data.explanation_ar, explanation_en=data.explanation_en,
                                       base_report_run_id=report.id, base_subtotal_code=data.base_subtotal_code, base_amount=base_amount,
                                       adjustments_payload=_json(adjustments), total_adjustments=total_adjustments, tax_effect=tax_effect,
                                       nci_effect=nci_effect, measure_value=money(base_amount + total_adjustments), prepared_by=user.id)
    db.add(row)
    db.flush()
    write_audit(db, action="MPM_CREATED", entity_type="MANAGEMENT_PERFORMANCE_MEASURE", entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"code": row.code, "base": str(base_amount), "adjustments": str(total_adjustments), "measure": str(row.measure_value)})
    db.commit()
    return {"id": row.id, "status": row.status, "base_amount": row.base_amount, "total_adjustments": row.total_adjustments,
            "tax_effect": row.tax_effect, "nci_effect": row.nci_effect, "measure_value": row.measure_value}


@router.post("/management-performance-measures/{measure_id}/review")
def review_mpm(measure_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ManagementPerformanceMeasure, measure_id)
    if not row:
        raise HTTPException(404, "Management performance measure not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.review")
    _three_step_review(row, user)
    write_audit(db, action="MPM_REVIEWED", entity_type="MANAGEMENT_PERFORMANCE_MEASURE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/management-performance-measures/{measure_id}/approve")
def approve_mpm(measure_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ManagementPerformanceMeasure, measure_id)
    if not row:
        raise HTTPException(404, "Management performance measure not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    _three_step_approve(row, user)
    row.status = "APPROVED_DISCLOSURE_READY"
    write_audit(db, action="MPM_APPROVED", entity_type="MANAGEMENT_PERFORMANCE_MEASURE", entity_id=row.id, user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "measure_value": str(row.measure_value)})
    db.commit()
    return {"id": row.id, "status": row.status, "measure_value": row.measure_value}


@router.post("/earnings-per-share", status_code=201)
def create_eps(data: EPSIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    numerator = money(data.profit_attributable - data.preference_dividends)
    basic = (numerator / Decimal(data.weighted_average_shares)).quantize(R6, rounding=ROUND_HALF_UP)
    diluted_numerator = money(numerator + data.diluted_profit_adjustment)
    diluted_denominator = Decimal(data.weighted_average_shares) + Decimal(data.incremental_shares)
    candidate = (diluted_numerator / diluted_denominator).quantize(R6, rounding=ROUND_HALF_UP) if diluted_denominator > 0 else basic
    anti_dilutive = Decimal("0")
    if candidate >= basic:
        diluted = basic
        anti_dilutive = Decimal(data.incremental_shares)
    else:
        diluted = candidate
    version = _version(db, EarningsPerShareRun, data.company_id, data.period_end)
    row = EarningsPerShareRun(company_id=data.company_id, period_end=data.period_end, version=version,
                              profit_attributable=money(data.profit_attributable), preference_dividends=money(data.preference_dividends),
                              weighted_average_shares=Decimal(data.weighted_average_shares), diluted_profit_adjustment=money(data.diluted_profit_adjustment),
                              incremental_shares=Decimal(data.incremental_shares), basic_eps=basic, diluted_eps=diluted,
                              anti_dilutive_excluded=anti_dilutive, support_reference=data.support_reference, prepared_by=user.id)
    db.add(row)
    db.flush()
    write_audit(db, action="EPS_RUN_CREATED", entity_type="EARNINGS_PER_SHARE", entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"period_end": str(data.period_end), "version": version, "basic_eps": str(basic), "diluted_eps": str(diluted), "anti_dilutive_shares": str(anti_dilutive)})
    db.commit()
    return {"id": row.id, "version": version, "status": row.status, "basic_eps": row.basic_eps, "diluted_eps": row.diluted_eps,
            "anti_dilutive_excluded": row.anti_dilutive_excluded}


@router.post("/earnings-per-share/{run_id}/review")
def review_eps(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(EarningsPerShareRun, run_id)
    if not row:
        raise HTTPException(404, "EPS run not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.review")
    _three_step_review(row, user)
    write_audit(db, action="EPS_RUN_REVIEWED", entity_type="EARNINGS_PER_SHARE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/earnings-per-share/{run_id}/approve")
def approve_eps(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(EarningsPerShareRun, run_id)
    if not row:
        raise HTTPException(404, "EPS run not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    _three_step_approve(row, user)
    row.status = "APPROVED_DISCLOSURE_READY"
    write_audit(db, action="EPS_RUN_APPROVED", entity_type="EARNINGS_PER_SHARE", entity_id=row.id, user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "basic_eps": str(row.basic_eps), "diluted_eps": str(row.diluted_eps)})
    db.commit()
    return {"id": row.id, "status": row.status, "basic_eps": row.basic_eps, "diluted_eps": row.diluted_eps}


@router.post("/segments", status_code=201)
def create_segment(data: SegmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    row = OperatingSegment(**data.model_dump(), created_by=user.id)
    db.add(row)
    db.flush()
    write_audit(db, action="OPERATING_SEGMENT_CREATED", entity_type="OPERATING_SEGMENT", entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"code": row.code, "reportable": row.reportable})
    db.commit()
    return {"id": row.id, "code": row.code, "status": row.status}


@router.post("/segments/{segment_id}/approve")
def approve_segment(segment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(OperatingSegment, segment_id)
    if not row:
        raise HTTPException(404, "Operating segment not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    if row.created_by == user.id:
        raise HTTPException(409, "Maker-checker: segment creator cannot approve it")
    row.status = "APPROVED"
    row.approved_by = user.id
    row.approved_at = utc_now()
    write_audit(db, action="OPERATING_SEGMENT_APPROVED", entity_type="OPERATING_SEGMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


def _report_entity_totals(report: FinancialReportRun) -> dict[str, Decimal]:
    payload = _loads(report.report_payload)
    revenue = Decimal("0")
    assets = Decimal("0")
    liabilities = Decimal("0")
    for line in payload.get("lines", []):
        value = Decimal(str(line.get("current", 0)))
        if line.get("statement") == "PROFIT_OR_LOSS" and line.get("line_code") == "REVENUE":
            revenue += value
        if line.get("statement") == "FINANCIAL_POSITION" and line.get("category") == "ASSETS":
            assets += value
        if line.get("statement") == "FINANCIAL_POSITION" and line.get("category") == "LIABILITIES":
            liabilities += value
    operating_profit = Decimal(str(payload.get("subtotals", {}).get("current", {}).get("operating_profit", 0)))
    return {"revenue": money(revenue), "profit": money(operating_profit), "assets": money(assets), "liabilities": money(liabilities)}


@router.post("/segment-reports", status_code=201)
def create_segment_report(data: SegmentReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.corporate.manage")
    report = db.get(FinancialReportRun, data.base_report_run_id)
    if not report or report.company_id != data.company_id or report.end_date != data.period_end or report.status != "APPROVED":
        raise HTTPException(422, "An approved IFRS 18 report for the same company and period is required")
    ids = [line.segment_id for line in data.lines]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Each operating segment may appear only once")
    segments = {x.id: x for x in db.scalars(select(OperatingSegment).where(OperatingSegment.id.in_(ids))).all()}
    if len(segments) != len(ids) or any(x.company_id != data.company_id or x.status != "APPROVED" or not x.active for x in segments.values()):
        raise HTTPException(422, "All segment lines must reference approved active segments of the selected company")
    entity = _report_entity_totals(report)
    segment_totals = {
        "revenue": money(sum((x.external_revenue for x in data.lines), Decimal("0"))),
        "profit": money(sum((x.segment_profit for x in data.lines), Decimal("0"))),
        "assets": money(sum((x.segment_assets for x in data.lines), Decimal("0"))),
        "liabilities": money(sum((x.segment_liabilities for x in data.lines), Decimal("0"))),
        "intersegment_revenue": money(sum((x.intersegment_revenue for x in data.lines), Decimal("0"))),
    }
    differences = {key: money(segment_totals[key] - entity[key]) for key in ("revenue", "profit", "assets", "liabilities")}
    blocking = [key for key, value in differences.items() if abs(value) > Q]
    reconciliation = {"entity_totals": entity, "segment_totals": segment_totals, "differences": differences, "blocking_fields": blocking}
    version = _version(db, SegmentReportRun, data.company_id, data.period_end)
    row = SegmentReportRun(company_id=data.company_id, period_end=data.period_end, version=version, base_report_run_id=report.id,
                           status="READY_FOR_REVIEW" if not blocking else "DRAFT_BLOCKED", reconciliation_payload=_json(reconciliation), prepared_by=user.id)
    db.add(row)
    db.flush()
    for line in data.lines:
        row.lines.append(SegmentReportLine(**line.model_dump()))
    write_audit(db, action="SEGMENT_REPORT_CREATED", entity_type="SEGMENT_REPORT", entity_id=row.id, user_id=user.id, company_id=data.company_id,
                after={"period_end": str(data.period_end), "version": version, "status": row.status, "blocking_fields": blocking})
    db.commit()
    return {"id": row.id, "version": version, "status": row.status, "reconciliation": reconciliation}


@router.post("/segment-reports/{run_id}/review")
def review_segment_report(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SegmentReportRun, run_id)
    if not row:
        raise HTTPException(404, "Segment report not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.review")
    if row.status == "DRAFT_BLOCKED":
        raise HTTPException(409, "Segment report does not reconcile to the approved financial report")
    _three_step_review(row, user, draft_statuses={"READY_FOR_REVIEW"})
    write_audit(db, action="SEGMENT_REPORT_REVIEWED", entity_type="SEGMENT_REPORT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/segment-reports/{run_id}/approve")
def approve_segment_report(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SegmentReportRun, run_id)
    if not row:
        raise HTTPException(404, "Segment report not found")
    ensure_permission(db, user, row.company_id, "finance.corporate.approve")
    _three_step_approve(row, user)
    row.status = "APPROVED_DISCLOSURE_READY"
    write_audit(db, action="SEGMENT_REPORT_APPROVED", entity_type="SEGMENT_REPORT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status, "reconciliation": _loads(row.reconciliation_payload)}


@router.get("/dashboard")
def dashboard(company_id: int, period_end: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.corporate.read")
    conditions = []
    if period_end:
        conditions.append(DeferredTaxRun.period_end == period_end)
    latest_tax = db.scalar(select(DeferredTaxRun).where(DeferredTaxRun.company_id == company_id, *conditions).order_by(DeferredTaxRun.period_end.desc(), DeferredTaxRun.version.desc()))
    latest_impairment = db.scalar(select(GoodwillImpairmentTest).where(GoodwillImpairmentTest.company_id == company_id).order_by(GoodwillImpairmentTest.period_end.desc(), GoodwillImpairmentTest.id.desc()))
    approved_mpm = db.scalar(select(func.count(ManagementPerformanceMeasure.id)).where(ManagementPerformanceMeasure.company_id == company_id, ManagementPerformanceMeasure.status == "APPROVED_DISCLOSURE_READY")) or 0
    approved_eps = db.scalar(select(func.count(EarningsPerShareRun.id)).where(EarningsPerShareRun.company_id == company_id, EarningsPerShareRun.status == "APPROVED_DISCLOSURE_READY")) or 0
    approved_segments = db.scalar(select(func.count(SegmentReportRun.id)).where(SegmentReportRun.company_id == company_id, SegmentReportRun.status == "APPROVED_DISCLOSURE_READY")) or 0
    return {"company_id": company_id, "period_end": period_end,
            "deferred_tax": None if not latest_tax else {"run_id": latest_tax.id, "status": latest_tax.status, "net_position": latest_tax.net_deferred_tax_position,
                                                         "recognized_dta": latest_tax.total_recognized_dta, "recognized_dtl": latest_tax.total_recognized_dtl},
            "goodwill_impairment": None if not latest_impairment else {"test_id": latest_impairment.id, "status": latest_impairment.status, "loss": latest_impairment.impairment_loss},
            "approved_disclosures": {"management_performance_measures": approved_mpm, "earnings_per_share": approved_eps, "segment_reports": approved_segments}}
