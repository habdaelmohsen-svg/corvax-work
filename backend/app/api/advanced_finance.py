from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, ConsolidationGroup, ConsolidationMember, FinancialDisclosureNote,
    FinancialReportRun, FinancialStatementMapping, FiscalPeriod, FiscalYear,
    JournalEntry, JournalLine, LeaseContract, LeaseModification, LeasePartialTermination, LeaseSchedule, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/advanced-finance", tags=["advanced financial reporting"])
Q = Decimal("0.01")
POSTED = ("POSTED", "REVERSED")
MANDATORY_DISCLOSURE_CODES = {
    "BASIS_OF_PREPARATION", "SIGNIFICANT_ACCOUNTING_POLICIES", "REVENUE",
    "LEASES", "FINANCIAL_INSTRUMENTS", "RELATED_PARTIES", "EVENTS_AFTER_REPORTING",
}


class MappingBootstrapIn(BaseModel):
    company_id: int


class MappingUpdateIn(BaseModel):
    statement: str
    ifrs18_category: str
    line_code: str
    line_name_ar: str
    line_name_en: str
    sort_order: int = 100
    is_oci: bool = False


class ReportRunIn(BaseModel):
    company_id: int
    start_date: date
    end_date: date
    comparative_start_date: date | None = None
    comparative_end_date: date | None = None


class DisclosureIn(BaseModel):
    company_id: int
    period_end: date
    note_code: str = Field(min_length=1, max_length=40)
    title_ar: str
    title_en: str
    standard: str
    content_ar: str
    content_en: str
    supporting_reference: str | None = None


class LeaseModificationIn(BaseModel):
    lease_id: int
    effective_date: date
    modification_type: str = "REMEASUREMENT"
    new_end_date: date
    new_payment_amount: Decimal = Field(gt=0)
    new_discount_rate: Decimal = Field(ge=0, le=1)
    reason: str = Field(min_length=5)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _loads(value: str) -> dict:
    return json.loads(value)


def _default_mapping(account: Account) -> dict:
    group = account.statement_group
    position_map = {
        "CASH": ("FINANCIAL_POSITION", "ASSETS", "CASH_AND_EQUIVALENTS", "النقد وما في حكمه", "Cash and cash equivalents", 10),
        "RECEIVABLES": ("FINANCIAL_POSITION", "ASSETS", "TRADE_RECEIVABLES", "الذمم التجارية", "Trade receivables", 20),
        "INVENTORY": ("FINANCIAL_POSITION", "ASSETS", "INVENTORIES", "المخزون", "Inventories", 30),
        "VAT_RECOVERABLE": ("FINANCIAL_POSITION", "ASSETS", "TAX_RECEIVABLES", "ضرائب قابلة للاسترداد", "Tax receivables", 40),
        "PREPAID_EXPENSES": ("FINANCIAL_POSITION", "ASSETS", "PREPAYMENTS", "مصروفات مدفوعة مقدمًا", "Prepayments", 50),
        "ACCRUED_REVENUE": ("FINANCIAL_POSITION", "ASSETS", "ACCRUED_REVENUE", "إيرادات مستحقة", "Accrued revenue", 60),
        "PPE": ("FINANCIAL_POSITION", "ASSETS", "PROPERTY_PLANT_EQUIPMENT", "ممتلكات وآلات ومعدات", "Property, plant and equipment", 100),
        "ACCUMULATED_DEPRECIATION": ("FINANCIAL_POSITION", "ASSETS", "ACCUMULATED_DEPRECIATION", "مجمع الإهلاك", "Accumulated depreciation", 110),
        "NON_CURRENT_ASSETS": ("FINANCIAL_POSITION", "ASSETS", "OTHER_NON_CURRENT_ASSETS", "أصول غير متداولة أخرى", "Other non-current assets", 120),
        "PAYABLES": ("FINANCIAL_POSITION", "LIABILITIES", "TRADE_PAYABLES", "الذمم الدائنة", "Trade payables", 200),
        "VAT": ("FINANCIAL_POSITION", "LIABILITIES", "TAX_PAYABLES", "ضرائب مستحقة", "Tax payables", 210),
        "CONTRACT_LIABILITY": ("FINANCIAL_POSITION", "LIABILITIES", "CONTRACT_LIABILITIES", "التزامات العقود", "Contract liabilities", 220),
        "CURRENT_LIABILITIES": ("FINANCIAL_POSITION", "LIABILITIES", "OTHER_CURRENT_LIABILITIES", "التزامات متداولة أخرى", "Other current liabilities", 230),
        "ACCRUED_EXPENSES": ("FINANCIAL_POSITION", "LIABILITIES", "ACCRUED_EXPENSES", "مصروفات مستحقة", "Accrued expenses", 240),
        "BORROWINGS": ("FINANCIAL_POSITION", "LIABILITIES", "BORROWINGS", "قروض وتمويل", "Borrowings", 260),
        "NON_CURRENT_LIABILITIES": ("FINANCIAL_POSITION", "LIABILITIES", "OTHER_NON_CURRENT_LIABILITIES", "التزامات غير متداولة أخرى", "Other non-current liabilities", 270),
        "CAPITAL": ("FINANCIAL_POSITION", "EQUITY", "SHARE_CAPITAL", "رأس المال", "Share capital", 300),
        "RETAINED_EARNINGS": ("FINANCIAL_POSITION", "EQUITY", "RETAINED_EARNINGS", "الأرباح المبقاة", "Retained earnings", 310),
        "EQUITY": ("FINANCIAL_POSITION", "EQUITY", "OTHER_EQUITY", "حقوق ملكية أخرى", "Other equity", 320),
    }
    profit_map = {
        "OPERATING_REVENUE": ("PROFIT_OR_LOSS", "OPERATING", "REVENUE", "الإيرادات", "Revenue", 10),
        "COST_OF_REVENUE": ("PROFIT_OR_LOSS", "OPERATING", "COST_OF_SALES", "تكلفة المبيعات", "Cost of sales", 20),
        "OPERATING_EXPENSES": ("PROFIT_OR_LOSS", "OPERATING", "OPERATING_EXPENSES", "المصروفات التشغيلية", "Operating expenses", 30),
        "OTHER_INCOME": ("PROFIT_OR_LOSS", "INVESTING", "OTHER_INCOME", "إيرادات ومكاسب أخرى", "Other income and gains", 50),
        "OTHER_EXPENSE": ("PROFIT_OR_LOSS", "INVESTING", "OTHER_EXPENSES", "مصروفات وخسائر أخرى", "Other expenses and losses", 60),
        "FINANCE_COSTS": ("PROFIT_OR_LOSS", "FINANCING", "FINANCE_COSTS", "تكاليف التمويل", "Finance costs", 70),
        "ZAKAT_TAX": ("PROFIT_OR_LOSS", "INCOME_TAX", "INCOME_TAX", "الزكاة والضريبة", "Zakat and income tax", 90),
    }
    if group in profit_map:
        statement, category, code, ar, en, order = profit_map[group]
    elif group in position_map:
        statement, category, code, ar, en, order = position_map[group]
    else:
        statement = "FINANCIAL_POSITION" if account.account_type in {"ASSET", "LIABILITY", "EQUITY"} else "PROFIT_OR_LOSS"
        category = "ASSETS" if account.account_type == "ASSET" else "LIABILITIES" if account.account_type == "LIABILITY" else "EQUITY" if account.account_type == "EQUITY" else "OPERATING"
        code, ar, en, order = f"OTHER_{account.account_type}", "بنود أخرى", f"Other {account.account_type.lower()}", 900
    return {"statement": statement, "ifrs18_category": category, "line_code": code, "line_name_ar": ar, "line_name_en": en, "sort_order": order, "is_oci": False}


def _activity_accounts(db: Session, company_id: int, start_date: date | None = None, end_date: date | None = None) -> set[int]:
    conditions = [JournalEntry.company_id == company_id, JournalEntry.status.in_(POSTED)]
    if start_date:
        conditions.append(JournalEntry.entry_date >= start_date)
    if end_date:
        conditions.append(JournalEntry.entry_date <= end_date)
    return set(db.scalars(select(JournalLine.account_id).join(JournalEntry).where(*conditions).distinct()).all())


def _balances(db: Session, company_id: int, start_date: date | None, end_date: date) -> dict[int, dict]:
    conditions = [JournalEntry.company_id == company_id, JournalEntry.status.in_(POSTED), JournalEntry.entry_date <= end_date]
    if start_date:
        conditions.append(JournalEntry.entry_date >= start_date)
    rows = db.execute(
        select(Account.id, Account.code, Account.account_type, func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(Account.company_id == company_id, *conditions)
        .group_by(Account.id, Account.code, Account.account_type)
    ).all()
    return {r[0]: {"code": r[1], "account_type": r[2], "debit": Decimal(r[3]), "credit": Decimal(r[4])} for r in rows}


def _signed_amount(balance: dict) -> Decimal:
    if balance["account_type"] in {"REVENUE", "LIABILITY", "EQUITY"}:
        amount = balance["credit"] - balance["debit"]
    else:
        amount = balance["debit"] - balance["credit"]
    if balance["account_type"] == "EXPENSE":
        amount = -amount
    return money(amount)


def _generate_report(db: Session, data: ReportRunIn) -> tuple[dict, dict]:
    mappings = db.scalars(select(FinancialStatementMapping).where(FinancialStatementMapping.company_id == data.company_id).options(selectinload(FinancialStatementMapping.account))).all()
    mapping_by_account = {m.account_id: m for m in mappings}
    active_accounts = _activity_accounts(db, data.company_id, data.start_date, data.end_date)
    unmapped = sorted(db.scalars(select(Account.code).where(Account.id.in_(active_accounts - set(mapping_by_account)))).all()) if active_accounts - set(mapping_by_account) else []
    unapproved = sorted(m.account.code for m in mappings if m.account_id in active_accounts and m.status != "APPROVED")

    current = _balances(db, data.company_id, data.start_date, data.end_date)
    comparative = _balances(db, data.company_id, data.comparative_start_date, data.comparative_end_date) if data.comparative_start_date and data.comparative_end_date else {}
    grouped: dict[tuple, dict] = {}
    for account_id, mapping in mapping_by_account.items():
        if account_id not in current and account_id not in comparative:
            continue
        key = (mapping.statement, mapping.ifrs18_category, mapping.line_code, mapping.line_name_ar, mapping.line_name_en, mapping.sort_order, mapping.is_oci)
        row = grouped.setdefault(key, {"current": Decimal("0"), "comparative": Decimal("0")})
        if account_id in current:
            row["current"] += _signed_amount(current[account_id])
        if account_id in comparative:
            row["comparative"] += _signed_amount(comparative[account_id])

    lines = []
    categories_current: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    categories_comparative: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for key, value in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][5], item[0][2])):
        statement, category, code, ar, en, order, is_oci = key
        current_value = money(value["current"])
        comp_value = money(value["comparative"])
        lines.append({"statement": statement, "category": category, "line_code": code, "line_name_ar": ar, "line_name_en": en, "sort_order": order, "is_oci": is_oci, "current": current_value, "comparative": comp_value})
        if statement == "PROFIT_OR_LOSS":
            categories_current[category] += current_value
            categories_comparative[category] += comp_value

    def subtotals(values: dict[str, Decimal]) -> dict:
        operating = money(values["OPERATING"])
        investing = money(values["INVESTING"])
        financing = money(values["FINANCING"])
        tax = money(values["INCOME_TAX"])
        discontinued = money(values["DISCONTINUED_OPERATIONS"])
        oci = money(values["OCI"])
        before_financing_tax = money(operating + investing)
        before_tax = money(before_financing_tax + financing)
        profit = money(before_tax + tax + discontinued)
        return {
            "operating_profit": operating,
            "profit_before_financing_and_income_tax": before_financing_tax,
            "profit_before_tax": before_tax,
            "profit_for_period": profit,
            "other_comprehensive_income": oci,
            "total_comprehensive_income": money(profit + oci),
        }

    cumulative = _balances(db, data.company_id, None, data.end_date)
    total_debit = sum((b["debit"] for b in cumulative.values()), Decimal("0"))
    total_credit = sum((b["credit"] for b in cumulative.values()), Decimal("0"))
    validation = {
        "unmapped_accounts": unmapped,
        "unapproved_mappings": unapproved,
        "trial_balance_difference": money(total_debit - total_credit),
        "comparative_period_present": bool(data.comparative_start_date and data.comparative_end_date),
    }
    validation["blocking_count"] = len(unmapped) + len(unapproved) + (1 if validation["trial_balance_difference"] != 0 else 0)
    report = {
        "framework": "IFRS_18",
        "company_id": data.company_id,
        "period": {"start_date": data.start_date, "end_date": data.end_date},
        "comparative_period": {"start_date": data.comparative_start_date, "end_date": data.comparative_end_date} if data.comparative_start_date else None,
        "currency": "SAR",
        "source": "POSTED_GENERAL_LEDGER_AND_APPROVED_MAPPINGS",
        "lines": lines,
        "subtotals": {"current": subtotals(categories_current), "comparative": subtotals(categories_comparative)},
    }
    return report, validation


@router.post("/mappings/bootstrap")
def bootstrap_mappings(data: MappingBootstrapIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.reporting.manage")
    accounts = db.scalars(select(Account).where(Account.company_id == data.company_id, Account.is_postable.is_(True), Account.active.is_(True))).all()
    existing = {m.account_id for m in db.scalars(select(FinancialStatementMapping).where(FinancialStatementMapping.company_id == data.company_id)).all()}
    created = 0
    for account in accounts:
        if account.id in existing:
            continue
        db.add(FinancialStatementMapping(company_id=data.company_id, account_id=account.id, created_by=user.id, status="DRAFT", **_default_mapping(account)))
        created += 1
    write_audit(db, action="IFRS18_MAPPINGS_BOOTSTRAPPED", entity_type="FINANCIAL_MAPPING", entity_id="BATCH", user_id=user.id, company_id=data.company_id, after={"created": created})
    db.commit()
    return {"company_id": data.company_id, "created": created, "status": "DRAFT_REQUIRES_APPROVAL"}


@router.get("/mappings")
def list_mappings(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(select(FinancialStatementMapping).where(FinancialStatementMapping.company_id == company_id).options(selectinload(FinancialStatementMapping.account)).order_by(FinancialStatementMapping.sort_order, FinancialStatementMapping.id)).all()
    return [{"id": r.id, "account_code": r.account.code, "account_name_ar": r.account.name_ar, "account_name_en": r.account.name_en, "statement": r.statement, "ifrs18_category": r.ifrs18_category, "line_code": r.line_code, "line_name_ar": r.line_name_ar, "line_name_en": r.line_name_en, "sort_order": r.sort_order, "is_oci": r.is_oci, "status": r.status, "created_by": r.created_by, "approved_by": r.approved_by} for r in rows]


@router.put("/mappings/{mapping_id}")
def update_mapping(mapping_id: int, data: MappingUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FinancialStatementMapping, mapping_id)
    if not row:
        raise HTTPException(404, "Financial mapping not found")
    ensure_permission(db, user, row.company_id, "finance.reporting.manage")
    before = {"statement": row.statement, "category": row.ifrs18_category, "line_code": row.line_code, "status": row.status}
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    row.status = "DRAFT"; row.approved_by = None; row.approved_at = None
    write_audit(db, action="IFRS18_MAPPING_UPDATED", entity_type="FINANCIAL_MAPPING", entity_id=row.id, user_id=user.id, company_id=row.company_id, before=before, after=data.model_dump())
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/mappings/{mapping_id}/approve")
def approve_mapping(mapping_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FinancialStatementMapping, mapping_id)
    if not row:
        raise HTTPException(404, "Financial mapping not found")
    ensure_permission(db, user, row.company_id, "finance.reporting.approve")
    if row.created_by == user.id:
        raise HTTPException(409, "Maker-checker: mapping creator cannot approve the mapping")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="IFRS18_MAPPING_APPROVED", entity_type="FINANCIAL_MAPPING", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status, "approved_by": row.approved_by}


@router.post("/reports", status_code=201)
def create_report(data: ReportRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.reporting.manage")
    if data.start_date > data.end_date:
        raise HTTPException(422, "start_date must not be after end_date")
    if bool(data.comparative_start_date) != bool(data.comparative_end_date):
        raise HTTPException(422, "Both comparative dates are required")
    report, validation = _generate_report(db, data)
    status = "READY_FOR_APPROVAL" if validation["blocking_count"] == 0 else "DRAFT_BLOCKED"
    run = FinancialReportRun(company_id=data.company_id, start_date=data.start_date, end_date=data.end_date, comparative_start_date=data.comparative_start_date, comparative_end_date=data.comparative_end_date, status=status, report_payload=_json(report), validation_payload=_json(validation), created_by=user.id)
    db.add(run); db.flush()
    write_audit(db, action="IFRS18_REPORT_GENERATED", entity_type="FINANCIAL_REPORT", entity_id=run.id, user_id=user.id, company_id=data.company_id, after={"status": status, "blocking_count": validation["blocking_count"]})
    db.commit()
    return {"id": run.id, "status": run.status, "report": report, "validation": validation}


@router.get("/reports")
def list_reports(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(select(FinancialReportRun).where(FinancialReportRun.company_id == company_id).order_by(FinancialReportRun.end_date.desc(), FinancialReportRun.id.desc())).all()
    return [{"id": r.id, "start_date": r.start_date, "end_date": r.end_date, "framework": r.framework, "status": r.status, "created_by": r.created_by, "approved_by": r.approved_by, "validation": _loads(r.validation_payload), "subtotals": _loads(r.report_payload).get("subtotals", {})} for r in rows]


@router.get("/reports/{run_id}")
def read_report(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(FinancialReportRun, run_id)
    if not run:
        raise HTTPException(404, "Financial report not found")
    ensure_permission(db, user, run.company_id, "finance.read")
    return {"id": run.id, "status": run.status, "created_by": run.created_by, "approved_by": run.approved_by, "report": _loads(run.report_payload), "validation": _loads(run.validation_payload)}


@router.post("/reports/{run_id}/approve")
def approve_report(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(FinancialReportRun, run_id)
    if not run:
        raise HTTPException(404, "Financial report not found")
    ensure_permission(db, user, run.company_id, "finance.reporting.approve")
    if run.status != "READY_FOR_APPROVAL":
        raise HTTPException(409, "Report has blocking validation findings")
    if run.created_by == user.id:
        raise HTTPException(409, "Maker-checker: report preparer cannot approve it")
    run.status = "APPROVED"; run.approved_by = user.id; run.approved_at = utc_now()
    write_audit(db, action="IFRS18_REPORT_APPROVED", entity_type="FINANCIAL_REPORT", entity_id=run.id, user_id=user.id, company_id=run.company_id, after={"status": run.status})
    db.commit()
    return {"id": run.id, "status": run.status, "approved_by": run.approved_by}


@router.post("/disclosures", status_code=201)
def create_disclosure(data: DisclosureIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "finance.disclosures.manage")
    duplicate = db.scalar(select(FinancialDisclosureNote).where(FinancialDisclosureNote.company_id == data.company_id, FinancialDisclosureNote.period_end == data.period_end, FinancialDisclosureNote.note_code == data.note_code))
    if duplicate:
        raise HTTPException(409, "Disclosure note code already exists for this period")
    row = FinancialDisclosureNote(**data.model_dump(), prepared_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="DISCLOSURE_NOTE_CREATED", entity_type="FINANCIAL_DISCLOSURE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"note_code": row.note_code, "standard": row.standard})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/disclosures/{note_id}/review")
def review_disclosure(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FinancialDisclosureNote, note_id)
    if not row:
        raise HTTPException(404, "Disclosure note not found")
    ensure_permission(db, user, row.company_id, "finance.disclosures.approve")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot review the disclosure")
    if not row.supporting_reference:
        raise HTTPException(422, "Supporting reference is required before review")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now()
    write_audit(db, action="DISCLOSURE_NOTE_REVIEWED", entity_type="FINANCIAL_DISCLOSURE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/disclosures/{note_id}/approve")
def approve_disclosure(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(FinancialDisclosureNote, note_id)
    if not row:
        raise HTTPException(404, "Disclosure note not found")
    ensure_permission(db, user, row.company_id, "finance.disclosures.approve")
    if row.status != "REVIEWED":
        raise HTTPException(409, "Disclosure must be reviewed before approval")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker: preparer cannot approve the disclosure")
    if row.reviewed_by == user.id:
        raise HTTPException(409, "Three-step control: disclosure reviewer cannot be the final approver")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="DISCLOSURE_NOTE_APPROVED", entity_type="FINANCIAL_DISCLOSURE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit(); return {"id": row.id, "status": row.status}


@router.get("/disclosures")
def list_disclosures(company_id: int, period_end: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    query = select(FinancialDisclosureNote).where(FinancialDisclosureNote.company_id == company_id)
    if period_end:
        query = query.where(FinancialDisclosureNote.period_end == period_end)
    rows = db.scalars(query.order_by(FinancialDisclosureNote.period_end.desc(), FinancialDisclosureNote.note_code)).all()
    return [{"id": r.id, "period_end": r.period_end, "note_code": r.note_code, "title_ar": r.title_ar, "title_en": r.title_en, "standard": r.standard, "status": r.status, "supporting_reference": r.supporting_reference, "prepared_by": r.prepared_by, "reviewed_by": r.reviewed_by, "approved_by": r.approved_by} for r in rows]


def _add_months(source: date, months: int) -> date:
    index = source.month - 1 + months
    year = source.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(source.day, calendar.monthrange(year, month)[1]))


def _month_end(source: date) -> date:
    return date(source.year, source.month, calendar.monthrange(source.year, source.month)[1])


def _months_between(start: date, end: date) -> int:
    return max((end.year - start.year) * 12 + end.month - start.month + 1, 1)


def _remeasure(lease: LeaseContract, effective_date: date, new_end_date: date, payment: Decimal, rate: Decimal) -> tuple[Decimal, list[dict]]:
    months = _months_between(effective_date, new_end_date)
    monthly_rate = Decimal(rate) / Decimal("12")
    frequency = lease.payment_frequency_months
    payment_months = list(range(frequency, months + 1, frequency))
    if not payment_months or payment_months[-1] < months:
        payment_months.append(months)
    liability = Decimal("0")
    for period in payment_months:
        liability += Decimal(payment) / ((Decimal("1") + monthly_rate) ** period)
    liability = money(liability)
    opening = liability
    schedules = []
    depreciation_base = liability
    monthly_depreciation = money(depreciation_base / months)
    for month in range(1, months + 1):
        interest = money(opening * monthly_rate)
        cash_payment = money(payment) if month in payment_months else Decimal("0")
        principal = money(cash_payment - interest) if cash_payment else Decimal("0")
        closing = money(opening + interest - cash_payment)
        if month == months and abs(closing) <= Decimal("1.00"):
            cash_payment = money(cash_payment + closing); principal = money(principal + closing); closing = Decimal("0")
        depreciation = monthly_depreciation if month < months else money(depreciation_base - monthly_depreciation * (months - 1))
        schedules.append({"payment_date": _month_end(_add_months(effective_date, month - 1)), "opening": opening, "interest": interest, "payment": cash_payment, "principal": principal, "closing": closing, "depreciation": depreciation})
        opening = closing
    return liability, schedules


@router.post("/lease-modifications", status_code=201)
def create_lease_modification(data: LeaseModificationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lease = db.scalar(select(LeaseContract).where(LeaseContract.id == data.lease_id).options(selectinload(LeaseContract.schedules)))
    if not lease:
        raise HTTPException(404, "Lease not found")
    ensure_permission(db, user, lease.company_id, "leases.modify")
    if lease.status != "ACTIVE":
        raise HTTPException(409, "Only active leases can be modified")
    if data.effective_date < lease.commencement_date or data.new_end_date <= data.effective_date:
        raise HTTPException(422, "Invalid modification dates")
    affected = sorted((s for s in lease.schedules if s.status == "PENDING" and s.payment_date >= data.effective_date), key=lambda s: s.period_number)
    if not affected:
        raise HTTPException(422, "No unposted future lease schedule is available for modification")
    carrying = money(affected[0].opening_liability)
    remeasured, _ = _remeasure(lease, data.effective_date, data.new_end_date, data.new_payment_amount, data.new_discount_rate)
    row = LeaseModification(lease_id=lease.id, effective_date=data.effective_date, modification_type=data.modification_type.upper(), new_end_date=data.new_end_date, new_payment_amount=money(data.new_payment_amount), new_discount_rate=data.new_discount_rate, reason=data.reason, carrying_liability=carrying, remeasured_liability=remeasured, rou_adjustment=money(remeasured - carrying), created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="IFRS16_MODIFICATION_CREATED", entity_type="LEASE_MODIFICATION", entity_id=row.id, user_id=user.id, company_id=lease.company_id, after={"lease": lease.number, "carrying": str(carrying), "remeasured": str(remeasured), "adjustment": str(row.rou_adjustment)})
    db.commit()
    return {"id": row.id, "status": row.status, "carrying_liability": row.carrying_liability, "remeasured_liability": row.remeasured_liability, "rou_adjustment": row.rou_adjustment}


@router.post("/lease-modifications/{modification_id}/approve")
def approve_lease_modification(modification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(LeaseModification).where(LeaseModification.id == modification_id).options(selectinload(LeaseModification.lease).selectinload(LeaseContract.schedules)))
    if not row:
        raise HTTPException(404, "Lease modification not found")
    lease = row.lease
    ensure_permission(db, user, lease.company_id, "leases.modify.approve")
    if row.status != "DRAFT":
        raise HTTPException(409, "Lease modification is not in draft status")
    if row.created_by == user.id:
        raise HTTPException(409, "Maker-checker: modification preparer cannot approve it")
    remeasured, schedules = _remeasure(lease, row.effective_date, row.new_end_date, row.new_payment_amount, row.new_discount_rate)
    affected = [s for s in lease.schedules if s.status == "PENDING" and s.payment_date >= row.effective_date]
    if not affected:
        raise HTTPException(409, "Future schedule was already posted or changed")
    carrying = money(sorted(affected, key=lambda s: s.period_number)[0].opening_liability)
    adjustment = money(remeasured - carrying)
    rou = get_account(db, lease.company_id, "152010")
    liability_account = get_account(db, lease.company_id, "222010")
    if adjustment > 0:
        lines = [{"account_id": rou.id, "debit": adjustment, "credit": 0}, {"account_id": liability_account.id, "debit": 0, "credit": adjustment}]
    elif adjustment < 0:
        amount = abs(adjustment)
        lines = [{"account_id": liability_account.id, "debit": amount, "credit": 0}, {"account_id": rou.id, "debit": 0, "credit": amount}]
    else:
        raise HTTPException(422, "Modification does not produce a remeasurement difference")
    journal = create_posted_journal(db, company_id=lease.company_id, user_id=user.id, posting_date=row.effective_date, reference=f"MOD-{lease.number}-{row.id}", description=f"IFRS 16 lease modification {lease.number}", lines=lines)
    affected_ids = [s.id for s in affected]
    db.execute(delete(LeaseSchedule).where(LeaseSchedule.id.in_(affected_ids)))
    db.flush()
    last_period = db.scalar(select(func.max(LeaseSchedule.period_number)).where(LeaseSchedule.lease_id == lease.id)) or 0
    for idx, schedule in enumerate(schedules, start=1):
        db.add(LeaseSchedule(lease_id=lease.id, period_number=last_period + idx, payment_date=schedule["payment_date"], opening_liability=schedule["opening"], interest=schedule["interest"], payment=schedule["payment"], principal=schedule["principal"], closing_liability=schedule["closing"], depreciation=schedule["depreciation"], status="PENDING"))
    lease.end_date = row.new_end_date; lease.payment_amount = row.new_payment_amount; lease.annual_discount_rate = row.new_discount_rate
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.carrying_liability = carrying; row.remeasured_liability = remeasured; row.rou_adjustment = adjustment; row.journal_id = journal.id
    write_audit(db, action="IFRS16_MODIFICATION_APPROVED", entity_type="LEASE_MODIFICATION", entity_id=row.id, user_id=user.id, company_id=lease.company_id, after={"journal": journal.number, "adjustment": str(adjustment), "new_schedule_periods": len(schedules)})
    db.commit()
    return {"id": row.id, "status": row.status, "journal": journal.number, "carrying_liability": carrying, "remeasured_liability": remeasured, "rou_adjustment": adjustment, "new_schedule_periods": len(schedules)}


@router.get("/lease-modifications")
def list_lease_modifications(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    rows = db.scalars(select(LeaseModification).join(LeaseContract).where(LeaseContract.company_id == company_id).options(selectinload(LeaseModification.lease)).order_by(LeaseModification.id.desc())).all()
    return [{"id": r.id, "lease_number": r.lease.number, "effective_date": r.effective_date, "new_end_date": r.new_end_date, "new_payment_amount": r.new_payment_amount, "new_discount_rate": r.new_discount_rate, "status": r.status, "carrying_liability": r.carrying_liability, "remeasured_liability": r.remeasured_liability, "rou_adjustment": r.rou_adjustment, "journal_id": r.journal_id} for r in rows]


@router.get("/lease-disclosures")
def lease_disclosures(company_id: int, as_of_date: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    leases = db.scalars(select(LeaseContract).where(LeaseContract.company_id == company_id).options(selectinload(LeaseContract.schedules))).all()
    current = Decimal("0"); non_current = Decimal("0"); one_to_two = Decimal("0"); two_to_five = Decimal("0"); over_five = Decimal("0")
    undiscounted = Decimal("0"); interest_remaining = Decimal("0"); gross_rou = Decimal("0"); accumulated_depreciation = Decimal("0")
    cutoff_1 = date(as_of_date.year + 1, as_of_date.month, min(as_of_date.day, calendar.monthrange(as_of_date.year + 1, as_of_date.month)[1]))
    cutoff_2 = date(as_of_date.year + 2, as_of_date.month, min(as_of_date.day, calendar.monthrange(as_of_date.year + 2, as_of_date.month)[1]))
    cutoff_5 = date(as_of_date.year + 5, as_of_date.month, min(as_of_date.day, calendar.monthrange(as_of_date.year + 5, as_of_date.month)[1]))
    details = []
    for lease in leases:
        gross_rou += Decimal(lease.initial_rou_asset) + sum((Decimal(m.rou_adjustment) for m in db.scalars(select(LeaseModification).where(LeaseModification.lease_id == lease.id, LeaseModification.status == "APPROVED_POSTED")).all()), Decimal("0"))
        gross_rou -= sum((Decimal(t.rou_reduction) for t in db.scalars(select(LeasePartialTermination).where(LeasePartialTermination.lease_id == lease.id, LeasePartialTermination.status == "APPROVED_POSTED", LeasePartialTermination.effective_date <= as_of_date)).all()), Decimal("0"))
        accumulated_depreciation += sum((Decimal(s.depreciation) for s in lease.schedules if s.status == "POSTED" and s.payment_date <= as_of_date), Decimal("0"))
        future = sorted((s for s in lease.schedules if s.payment_date > as_of_date and s.status == "PENDING"), key=lambda x: x.payment_date)
        liability = Decimal(future[0].opening_liability) if future else Decimal("0")
        lease_current = Decimal("0"); lease_non_current = Decimal("0")
        for schedule in future:
            payment = Decimal(schedule.payment)
            undiscounted += payment; interest_remaining += Decimal(schedule.interest)
            if schedule.payment_date <= cutoff_1:
                current += payment; lease_current += payment
            else:
                non_current += payment; lease_non_current += payment
                if schedule.payment_date <= cutoff_2: one_to_two += payment
                elif schedule.payment_date <= cutoff_5: two_to_five += payment
                else: over_five += payment
        details.append({"lease_number": lease.number, "status": lease.status, "remaining_liability": money(liability), "undiscounted_current": money(lease_current), "undiscounted_non_current": money(lease_non_current)})
    return {"company_id": company_id, "as_of_date": as_of_date, "active_leases": sum(1 for l in leases if l.status == "ACTIVE"), "lease_liability_maturity": {"within_one_year": money(current), "one_to_two_years": money(one_to_two), "two_to_five_years": money(two_to_five), "over_five_years": money(over_five), "non_current_total": money(non_current), "undiscounted_total": money(undiscounted), "future_interest": money(interest_remaining)}, "right_of_use_assets": {"gross": money(gross_rou), "accumulated_depreciation": money(accumulated_depreciation), "net": money(gross_rou - accumulated_depreciation)}, "leases": details}


@router.get("/consolidation-ownership-analysis")
def consolidation_ownership_analysis(group_id: int, period_start: date, period_end: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.get(ConsolidationGroup, group_id)
    if not group:
        raise HTTPException(404, "Consolidation group not found")
    members = db.scalars(select(ConsolidationMember).where(ConsolidationMember.group_id == group_id)).all()
    results = []
    total_nci_net_assets = Decimal("0"); total_nci_profit = Decimal("0")
    for member in members:
        ensure_permission(db, user, member.company_id, "finance.read")
        cumulative = _balances(db, member.company_id, None, period_end)
        period = _balances(db, member.company_id, period_start, period_end)
        net_assets = Decimal("0")
        for balance in cumulative.values():
            signed = _signed_amount(balance)
            if balance["account_type"] == "ASSET": net_assets += signed
            elif balance["account_type"] == "LIABILITY": net_assets -= signed
        profit = sum((_signed_amount(b) for b in period.values() if b["account_type"] in {"REVENUE", "EXPENSE"}), Decimal("0"))
        ownership = Decimal(member.ownership_percent) / Decimal("100")
        nci = Decimal("1") - ownership
        nci_net_assets = money(net_assets * nci); nci_profit = money(profit * nci)
        total_nci_net_assets += nci_net_assets; total_nci_profit += nci_profit
        results.append({"company_id": member.company_id, "ownership_percent": member.ownership_percent, "parent_share_percent": money(ownership * 100), "nci_percent": money(nci * 100), "net_assets": money(net_assets), "profit_for_period": money(profit), "parent_share_net_assets": money(net_assets * ownership), "nci_share_net_assets": nci_net_assets, "parent_share_profit": money(profit * ownership), "nci_share_profit": nci_profit})
    return {"group_id": group_id, "group_code": group.code, "period": {"start": period_start, "end": period_end}, "members": results, "total_nci_net_assets": money(total_nci_net_assets), "total_nci_profit": money(total_nci_profit)}


@router.get("/close-readiness")
def close_readiness(company_id: int, period_end: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    open_journals = db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.company_id == company_id, JournalEntry.entry_date <= period_end, JournalEntry.status.in_(("DRAFT", "PENDING_APPROVAL", "APPROVED")))) or 0
    activity = _activity_accounts(db, company_id, None, period_end)
    mappings = db.scalars(select(FinancialStatementMapping).where(FinancialStatementMapping.company_id == company_id)).all()
    approved_mapping_ids = {m.account_id for m in mappings if m.status == "APPROVED"}
    unmapped_or_unapproved = len(activity - approved_mapping_ids)
    disclosure_rows = db.scalars(select(FinancialDisclosureNote).where(FinancialDisclosureNote.company_id == company_id, FinancialDisclosureNote.period_end == period_end)).all()
    approved_disclosure_codes = {row.note_code for row in disclosure_rows if row.status == "APPROVED"}
    missing_mandatory_disclosures = sorted(MANDATORY_DISCLOSURE_CODES - approved_disclosure_codes)
    unapproved_disclosures = sum(1 for row in disclosure_rows if row.status != "APPROVED")
    due_lease_schedules = db.scalar(select(func.count(LeaseSchedule.id)).join(LeaseContract).where(LeaseContract.company_id == company_id, LeaseSchedule.payment_date <= period_end, LeaseSchedule.status == "PENDING")) or 0
    latest_report = db.scalar(select(FinancialReportRun).where(FinancialReportRun.company_id == company_id, FinancialReportRun.end_date == period_end).order_by(FinancialReportRun.id.desc()))
    balances = _balances(db, company_id, None, period_end)
    difference = money(sum((b["debit"] for b in balances.values()), Decimal("0")) - sum((b["credit"] for b in balances.values()), Decimal("0")))
    checks = [
        {"code": "JOURNAL_WORKFLOW", "passed": open_journals == 0, "blocking_count": open_journals},
        {"code": "IFRS18_MAPPING", "passed": unmapped_or_unapproved == 0, "blocking_count": unmapped_or_unapproved},
        {"code": "DISCLOSURES", "passed": unapproved_disclosures == 0 and not missing_mandatory_disclosures, "blocking_count": unapproved_disclosures + len(missing_mandatory_disclosures), "missing_required_notes": missing_mandatory_disclosures},
        {"code": "LEASE_SCHEDULES", "passed": due_lease_schedules == 0, "blocking_count": due_lease_schedules},
        {"code": "TRIAL_BALANCE", "passed": difference == 0, "difference": difference},
        {"code": "APPROVED_FINANCIAL_REPORT", "passed": bool(latest_report and latest_report.status == "APPROVED"), "report_id": latest_report.id if latest_report else None, "status": latest_report.status if latest_report else "MISSING"},
    ]
    blockers = sum(1 for check in checks if not check["passed"])
    return {"company_id": company_id, "period_end": period_end, "status": "READY_TO_CLOSE" if blockers == 0 else "BLOCKED", "blocking_checks": blockers, "checks": checks}
