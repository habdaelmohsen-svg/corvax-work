from __future__ import annotations

import calendar
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.finance import account_balances, financial_statements
from app.api.period_close import _checks as build_close_checks
from app.core.time import utc_now
from app.db import get_db
from app.dependencies import (
    branch_scope_condition,
    ensure_branch_access,
    ensure_company_access,
    ensure_permission,
    get_current_user,
)
from app.models import (
    Account,
    AssetDepreciation,
    AuditLog,
    BankAccount,
    BankStatement,
    BankStatementLine,
    Branch,
    Budget,
    BudgetLine,
    Company,
    CreditNote,
    FinancialOpenItem,
    FiscalPeriod,
    FiscalYear,
    FixedAsset,
    Item,
    JournalEntry,
    JournalLine,
    MenuItem,
    Party,
    PeriodCloseCheck,
    PeriodCloseRun,
    PosOrder,
    PosOrderLine,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    Receipt,
    SalesInvoice,
    SalesInvoiceLine,
    StockMovement,
    SystemReportRun,
    TaxCode,
    User,
    VatReportingProfile,
    VatReturnSnapshot,
    Warehouse,
)
from app.services.audit import write_audit
from app.services.operations import money
from app.services.tax import build_vat_return, serialize_vat_return


router = APIRouter(prefix="/system-reports", tags=["comprehensive system reports"])
POSTED = ("POSTED", "REVERSED", "APPROVED_POSTED")
ZERO = Decimal("0")


def _report(code: str, category: str, ar: str, en: str, priority: str, source: str, *, as_of: bool = False) -> dict:
    return {
        "code": code,
        "category": category,
        "name_ar": ar,
        "name_en": en,
        "priority": priority,
        "source": source,
        "period_mode": "AS_OF" if as_of else "RANGE",
        "status": "IMPLEMENTED",
        "export_formats": ["XLSX", "PDF"],
    }


REPORT_CATALOG = [
    _report("VAT-01", "VAT", "تفصيل ضريبة المبيعات", "Sales VAT Detail", "P0", "SALES_TAX_LINES"),
    _report("VAT-02", "VAT", "ملخص ضريبة المبيعات", "Sales VAT Summary", "P0", "SALES_TAX_LINES"),
    _report("VAT-03", "VAT", "تفصيل ضريبة المشتريات", "Purchase VAT Detail", "P0", "PURCHASE_TAX_LINES"),
    _report("VAT-04", "VAT", "ملخص ضريبة المشتريات", "Purchase VAT Summary", "P0", "PURCHASE_TAX_LINES"),
    _report("VAT-05", "VAT", "محاكاة إقرار ضريبة القيمة المضافة - ZATCA", "ZATCA VAT Return Simulation", "P0", "VAT_RETURN"),
    _report("VAT-06", "VAT", "مطابقة الإقرار مع الأستاذ العام", "VAT Return to GL Reconciliation", "P0", "VAT_RETURN"),
    _report("VAT-07", "VAT", "استثناءات ضريبة المبيعات", "Sales VAT Exceptions", "P0", "SALES_TAX_LINES"),
    _report("VAT-08", "VAT", "استثناءات ضريبة المشتريات", "Purchase VAT Exceptions", "P0", "PURCHASE_TAX_LINES"),
    _report("VAT-09", "VAT", "حركة تعديلات الإقرار", "VAT Return Adjustments", "P1", "CREDIT_NOTES"),
    _report("VAT-10", "VAT", "رصيد VAT المستحق / الدائن", "VAT Payable / Receivable Balance", "P0", "VAT_RETURN"),
    _report("FS-01", "FINANCIAL", "قائمة الدخل - شهرية", "Monthly Income Statement", "P0", "GENERAL_LEDGER"),
    _report("FS-02", "FINANCIAL", "قائمة الدخل - ربع سنوية", "Quarterly Income Statement", "P0", "GENERAL_LEDGER"),
    _report("FS-03", "FINANCIAL", "قائمة الدخل - سنوية", "Annual Income Statement", "P0", "GENERAL_LEDGER"),
    _report("FS-04", "FINANCIAL", "المركز المالي - شهري", "Monthly Financial Position", "P0", "GENERAL_LEDGER", as_of=True),
    _report("FS-05", "FINANCIAL", "المركز المالي - ربع سنوي", "Quarterly Financial Position", "P0", "GENERAL_LEDGER", as_of=True),
    _report("FS-06", "FINANCIAL", "المركز المالي - سنوي", "Annual Financial Position", "P0", "GENERAL_LEDGER", as_of=True),
    _report("FS-07", "FINANCIAL", "التدفقات النقدية - شهري", "Monthly Cash Flows", "P0", "GENERAL_LEDGER"),
    _report("FS-08", "FINANCIAL", "التدفقات النقدية - ربع سنوي", "Quarterly Cash Flows", "P0", "GENERAL_LEDGER"),
    _report("FS-09", "FINANCIAL", "التدفقات النقدية - سنوي", "Annual Cash Flows", "P0", "GENERAL_LEDGER"),
    _report("FS-10", "FINANCIAL", "التغيرات في حقوق الملكية", "Changes in Equity", "P0", "GENERAL_LEDGER"),
    _report("FS-11", "FINANCIAL", "تحليل أفقي للقوائم المالية", "Horizontal Financial Analysis", "P0", "GENERAL_LEDGER"),
    _report("FS-12", "FINANCIAL", "تحليل رأسي للقوائم المالية", "Vertical Financial Analysis", "P0", "GENERAL_LEDGER"),
    _report("SAL-01", "SALES", "فواتير المبيعات", "Sales Invoices", "P0", "SALES"),
    _report("SAL-02", "SALES", "سندات القبض", "Receipts", "P0", "RECEIPTS"),
    _report("SAL-03", "SALES", "متأخرات العملاء", "Customer Overdues", "P0", "AR_OPEN_ITEMS", as_of=True),
    _report("SAL-04", "SALES", "أعمار ديون العملاء", "Customer Aging", "P0", "AR_OPEN_ITEMS", as_of=True),
    _report("SAL-05", "SALES", "أكثر العملاء مبيعات", "Top Customers by Sales", "P1", "SALES"),
    _report("SAL-06", "SALES", "أكثر العملاء ربحية", "Most Profitable Customers", "P1", "POS_ACTUAL_COST"),
    _report("SAL-07", "SALES", "أكثر المنتجات مبيعًا", "Top Selling Products", "P1", "SALES_LINES"),
    _report("SAL-08", "SALES", "أقل المنتجات مبيعًا", "Lowest Selling Products", "P1", "SALES_LINES"),
    _report("SAL-09", "SALES", "المنتجات بدون مبيعات", "Products Without Sales", "P1", "ITEM_MASTER"),
    _report("SAL-10", "SALES", "دليل العملاء بالأرقام الحسابية", "Customer Account Directory", "P1", "PARTIES"),
    _report("SAL-11", "SALES", "قائمة أسماء العملاء", "Customer Name List", "P1", "PARTIES"),
    _report("SAL-12", "SALES", "العملاء المتجاوزون للحد الائتماني", "Customers Over Credit Limit", "P0", "AR_OPEN_ITEMS", as_of=True),
    _report("PUR-01", "PURCHASES", "فواتير المشتريات", "Purchase Invoices", "P0", "PURCHASES"),
    _report("PUR-02", "PURCHASES", "أعمار ديون الموردين", "Supplier Aging", "P0", "AP_OPEN_ITEMS", as_of=True),
    _report("PUR-03", "PURCHASES", "أكبر الموردين مشتريات", "Top Suppliers by Purchases", "P1", "PURCHASES"),
    _report("PUR-04", "PURCHASES", "تحليل تغير أسعار الشراء", "Purchase Price Change Analysis", "P1", "PURCHASE_LINES"),
    _report("PUR-05", "PURCHASES", "الدفعات المستحقة للموردين", "Supplier Payments Due", "P0", "AP_OPEN_ITEMS", as_of=True),
    _report("INV-01", "INVENTORY", "رصيد المخزون", "Inventory Balance", "P1", "STOCK_MOVEMENTS", as_of=True),
    _report("INV-02", "INVENTORY", "بطاقة الصنف", "Item Card", "P1", "STOCK_MOVEMENTS"),
    _report("INV-03", "INVENTORY", "أعمار المخزون", "Inventory Aging", "P1", "STOCK_MOVEMENTS", as_of=True),
    _report("INV-04", "INVENTORY", "بطيء / غير متحرك", "Slow / Non-moving Inventory", "P1", "STOCK_MOVEMENTS", as_of=True),
    _report("INV-05", "INVENTORY", "قيمة المخزون المعرضة للخطر", "Inventory Value at Risk", "P1", "STOCK_MOVEMENTS", as_of=True),
    _report("GL-01", "GENERAL_LEDGER", "الأستاذ العام", "General Ledger", "P1", "GENERAL_LEDGER"),
    _report("GL-02", "GENERAL_LEDGER", "ميزان المراجعة", "Trial Balance", "P0", "GENERAL_LEDGER", as_of=True),
    _report("GL-03", "GENERAL_LEDGER", "دفتر اليومية", "Journal Book", "P1", "GENERAL_LEDGER"),
    _report("GL-04", "GENERAL_LEDGER", "القيود اليدوية", "Manual Journals", "P1", "GENERAL_LEDGER"),
    _report("GL-05", "GENERAL_LEDGER", "القيود غير المرحلة", "Unposted Journals", "P0", "GENERAL_LEDGER"),
    _report("GL-06", "GENERAL_LEDGER", "Actual vs Budget", "Actual vs Budget", "P1", "BUDGET_LEDGER"),
    _report("CASH-01", "CASH", "الموقف النقدي اليومي", "Daily Cash Position", "P1", "BANK_LEDGER", as_of=True),
    _report("CASH-02", "CASH", "مطابقة البنك", "Bank Reconciliation", "P1", "BANK_STATEMENTS", as_of=True),
    _report("FA-01", "FIXED_ASSETS", "سجل الأصول", "Fixed Asset Register", "P2", "FIXED_ASSETS", as_of=True),
    _report("FA-02", "FIXED_ASSETS", "حركة الإهلاك", "Depreciation Movement", "P2", "FIXED_ASSETS"),
    _report("BUD-01", "BUDGET", "الموازنة مقابل الفعلي", "Budget versus Actual", "P1", "BUDGET_LEDGER"),
    _report("AUD-01", "AUDIT", "Audit Trail", "Audit Trail", "P2", "AUDIT_LOG"),
    _report("CLOSE-01", "CLOSE", "حالة الإقفال الشهري", "Monthly Close Status", "P2", "PERIOD_CLOSE"),
]
REPORT_BY_CODE = {row["code"]: row for row in REPORT_CATALOG}


class ReportRunIn(BaseModel):
    company_id: int
    report_code: str = Field(min_length=4, max_length=20)
    period_type: str = Field(default="CUSTOM", pattern="^(CUSTOM|MONTH|QUARTER|YEAR)$")
    start_date: date | None = None
    end_date: date | None = None
    anchor_date: date | None = None
    branch_id: int | None = None
    item_id: int | None = None
    party_id: int | None = None
    method: str = Field(default="indirect", pattern="^(direct|indirect)$")
    slow_days: int = Field(default=90, ge=1, le=3650)
    obsolete_days: int = Field(default=180, ge=1, le=7300)
    limit: int = Field(default=5000, ge=1, le=20000)


class VatProfileIn(BaseModel):
    company_id: int
    filing_frequency: str = Field(pattern="^(MONTHLY|QUARTERLY)$")
    return_layout_version: str = Field(default="ZATCA_STANDARD", min_length=2, max_length=50)


def _decimal(value: Any) -> Decimal:
    return money(value or 0)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _period(data: ReportRunIn) -> dict:
    anchor = data.anchor_date or data.end_date or date.today()
    if data.period_type == "CUSTOM":
        if not data.start_date or not data.end_date:
            raise HTTPException(422, "start_date and end_date are required for CUSTOM periods")
        start, end = data.start_date, data.end_date
    elif data.period_type == "MONTH":
        start = anchor.replace(day=1)
        end = anchor.replace(day=calendar.monthrange(anchor.year, anchor.month)[1])
    elif data.period_type == "QUARTER":
        first_month = ((anchor.month - 1) // 3) * 3 + 1
        start = date(anchor.year, first_month, 1)
        last_month = first_month + 2
        end = date(anchor.year, last_month, calendar.monthrange(anchor.year, last_month)[1])
    else:
        start, end = date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    if start > end:
        raise HTTPException(422, "start_date must not be after end_date")
    days = (end - start).days + 1
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=days - 1)
    try:
        py_start, py_end = start.replace(year=start.year - 1), end.replace(year=end.year - 1)
    except ValueError:
        py_start, py_end = start.replace(year=start.year - 1, day=28), end.replace(year=end.year - 1, day=28)
    return {
        "type": data.period_type,
        "start": start,
        "end": end,
        "prior_start": prior_start,
        "prior_end": prior_end,
        "prior_year_start": py_start,
        "prior_year_end": py_end,
    }


def _col(key: str, ar: str, en: str, kind: str = "text") -> dict:
    return {"key": key, "name_ar": ar, "name_en": en, "type": kind}


def _vat_snapshot(db: Session, data: ReportRunIn, period: dict, user: User) -> VatReturnSnapshot:
    row = db.scalar(
        select(VatReturnSnapshot)
        .where(
            VatReturnSnapshot.company_id == data.company_id,
            VatReturnSnapshot.period_start == period["start"],
            VatReturnSnapshot.period_end == period["end"],
        )
        .options(selectinload(VatReturnSnapshot.lines))
    )
    if row:
        return row
    row = build_vat_return(
        db,
        company_id=data.company_id,
        period_start=period["start"],
        period_end=period["end"],
        user_id=user.id,
    )
    db.flush()
    return row


def _tax_detail(db: Session, data: ReportRunIn, period: dict, sales: bool) -> tuple[list[dict], list[dict], dict, list[str]]:
    if sales:
        lines = db.scalars(
            select(SalesInvoiceLine)
            .join(SalesInvoice)
            .where(
                SalesInvoice.company_id == data.company_id,
                SalesInvoice.invoice_date.between(period["start"], period["end"]),
                SalesInvoice.status.in_(POSTED),
            )
            .options(
                selectinload(SalesInvoiceLine.invoice).selectinload(SalesInvoice.customer),
                selectinload(SalesInvoiceLine.tax_code),
            )
            .limit(data.limit)
        ).all()
        rows = [{
            "document_no": line.invoice.number,
            "date": line.invoice.invoice_date,
            "party_code": line.invoice.customer.code,
            "party_name": line.invoice.customer.name_ar,
            "vat_number": line.invoice.customer.vat_number or "",
            "description": line.description,
            "tax_code": line.tax_code.code if line.tax_code else "",
            "return_box": line.tax_code.return_box if line.tax_code else "",
            "category": line.tax_code.category if line.tax_code else "",
            "base_amount": _decimal(line.subtotal),
            "vat_amount": _decimal(line.vat_amount),
            "total": _decimal(line.total),
        } for line in lines]
        columns = [
            _col("document_no", "رقم المستند", "Document No."),
            _col("date", "التاريخ", "Date", "date"),
            _col("party_code", "كود العميل", "Customer Code"),
            _col("party_name", "العميل", "Customer"),
            _col("vat_number", "الرقم الضريبي", "VAT Number"),
            _col("description", "البيان", "Description"),
            _col("tax_code", "كود الضريبة", "Tax Code"),
            _col("return_box", "خانة الإقرار", "Return Box"),
            _col("category", "التصنيف", "Category"),
            _col("base_amount", "الأساس", "Taxable Base", "money"),
            _col("vat_amount", "الضريبة", "VAT", "money"),
            _col("total", "الإجمالي", "Total", "money"),
        ]
    else:
        lines = db.scalars(
            select(PurchaseInvoiceLine)
            .join(PurchaseInvoice)
            .where(
                PurchaseInvoice.company_id == data.company_id,
                PurchaseInvoice.invoice_date.between(period["start"], period["end"]),
                PurchaseInvoice.status.in_(POSTED),
            )
            .options(
                selectinload(PurchaseInvoiceLine.invoice).selectinload(PurchaseInvoice.supplier),
                selectinload(PurchaseInvoiceLine.tax_code),
            )
            .limit(data.limit)
        ).all()
        rows = [{
            "document_no": line.invoice.number,
            "supplier_invoice_no": line.invoice.supplier_invoice_number,
            "date": line.invoice.invoice_date,
            "party_code": line.invoice.supplier.code,
            "party_name": line.invoice.supplier.name_ar,
            "vat_number": line.invoice.supplier.vat_number or "",
            "description": line.description,
            "tax_code": line.tax_code.code if line.tax_code else "",
            "return_box": line.tax_code.return_box if line.tax_code else "",
            "category": line.tax_code.category if line.tax_code else "",
            "deductible_percent": _decimal(line.tax_code.deductible_percent if line.tax_code else 0),
            "base_amount": _decimal(line.subtotal),
            "vat_amount": _decimal(line.vat_amount),
            "deductible_vat": money(_decimal(line.vat_amount) * _decimal(line.tax_code.deductible_percent if line.tax_code else 0) / 100),
            "total": _decimal(line.total),
        } for line in lines]
        columns = [
            _col("document_no", "رقم المستند", "Document No."),
            _col("supplier_invoice_no", "فاتورة المورد", "Supplier Invoice"),
            _col("date", "التاريخ", "Date", "date"),
            _col("party_code", "كود المورد", "Supplier Code"),
            _col("party_name", "المورد", "Supplier"),
            _col("vat_number", "الرقم الضريبي", "VAT Number"),
            _col("description", "البيان", "Description"),
            _col("tax_code", "كود الضريبة", "Tax Code"),
            _col("return_box", "خانة الإقرار", "Return Box"),
            _col("category", "التصنيف", "Category"),
            _col("deductible_percent", "نسبة الخصم", "Deductible %", "percent"),
            _col("base_amount", "الأساس", "Taxable Base", "money"),
            _col("vat_amount", "الضريبة", "VAT", "money"),
            _col("deductible_vat", "الضريبة القابلة للخصم", "Deductible VAT", "money"),
            _col("total", "الإجمالي", "Total", "money"),
        ]
    totals = {
        "base_amount": money(sum((_decimal(row["base_amount"]) for row in rows), ZERO)),
        "vat_amount": money(sum((_decimal(row["vat_amount"]) for row in rows), ZERO)),
        "total": money(sum((_decimal(row["total"]) for row in rows), ZERO)),
    }
    return columns, rows, totals, []


def _vat_report(db: Session, data: ReportRunIn, period: dict, user: User) -> tuple:
    code = data.report_code
    if code in {"VAT-01", "VAT-03"}:
        return _tax_detail(db, data, period, code == "VAT-01")
    if code in {"VAT-02", "VAT-04"}:
        columns, detail, _, warnings = _tax_detail(db, data, period, code == "VAT-02")
        grouped: dict[tuple, dict] = {}
        for row in detail:
            key = (row["return_box"] or "UNCLASSIFIED", row["category"] or "UNCLASSIFIED", row["tax_code"] or "—")
            item = grouped.setdefault(key, {
                "return_box": key[0], "category": key[1], "tax_code": key[2],
                "transaction_count": 0, "base_amount": ZERO, "vat_amount": ZERO, "total": ZERO,
            })
            item["transaction_count"] += 1
            for field in ("base_amount", "vat_amount", "total"):
                item[field] += _decimal(row[field])
        rows = sorted(grouped.values(), key=lambda item: (item["return_box"], item["tax_code"]))
        columns = [
            _col("return_box", "خانة الإقرار", "Return Box"),
            _col("category", "التصنيف", "Category"),
            _col("tax_code", "كود الضريبة", "Tax Code"),
            _col("transaction_count", "عدد الحركات", "Transactions", "integer"),
            _col("base_amount", "الأساس", "Taxable Base", "money"),
            _col("vat_amount", "الضريبة", "VAT", "money"),
            _col("total", "الإجمالي", "Total", "money"),
        ]
        totals = {field: money(sum((_decimal(row[field]) for row in rows), ZERO)) for field in ("base_amount", "vat_amount", "total")}
        totals["transaction_count"] = sum(row["transaction_count"] for row in rows)
        return columns, rows, totals, warnings
    snapshot = _vat_snapshot(db, data, period, user)
    vat = serialize_vat_return(snapshot)
    if code == "VAT-05":
        rows = [{
            "box_code": line["box_code"],
            "name_ar": line["name_ar"],
            "name_en": line["name_en"],
            "base_amount": line["base_amount"],
            "tax_amount": line["tax_amount"],
            "adjustment_base": line["adjustment_base"],
            "adjustment_tax": line["adjustment_tax"],
            "transaction_count": line["transaction_count"],
        } for line in vat["lines"]]
        columns = [
            _col("box_code", "رمز الخانة", "Box Code"),
            _col("name_ar", "اسم الخانة", "Arabic Name"),
            _col("name_en", "اسم الخانة بالإنجليزية", "English Name"),
            _col("base_amount", "الأساس", "Base", "money"),
            _col("tax_amount", "الضريبة", "Tax", "money"),
            _col("adjustment_base", "تعديل الأساس", "Base Adjustment", "money"),
            _col("adjustment_tax", "تعديل الضريبة", "Tax Adjustment", "money"),
            _col("transaction_count", "عدد الحركات", "Transactions", "integer"),
        ]
        warnings = [] if vat["classification_complete"] else [vat["classification_note"]]
        warnings.append("المحاكاة داخلية، ويُربط ترتيب الخانات 1:1 بعد تحميل نموذج ZATCA الرسمي المعتمد من المستخدم.")
        return columns, rows, {"output_vat": vat["output_vat"], "input_vat": vat["input_vat"], "net_vat_payable": vat["net_vat_payable"]}, warnings
    if code == "VAT-06":
        rows = [
            {"side": "OUTPUT", "return_amount": vat["output_vat"], "gl_amount": vat["gl_output_vat"], "difference": vat["output_reconciliation_difference"], "reconciled": vat["output_reconciled"]},
            {"side": "INPUT", "return_amount": vat["input_vat"], "gl_amount": vat["gl_input_vat"], "difference": vat["input_reconciliation_difference"], "reconciled": vat["input_reconciled"]},
        ]
        return [
            _col("side", "الجانب", "Side"),
            _col("return_amount", "مبلغ الإقرار", "Return Amount", "money"),
            _col("gl_amount", "مبلغ الأستاذ العام", "GL Amount", "money"),
            _col("difference", "الفرق", "Difference", "money"),
            _col("reconciled", "مطابق", "Reconciled", "boolean"),
        ], rows, {"net_vat_payable": vat["net_vat_payable"]}, []
    if code in {"VAT-07", "VAT-08"}:
        _, detail, _, _ = _tax_detail(db, data, period, code == "VAT-07")
        rows = []
        for row in detail:
            reasons = []
            expected = money(_decimal(row["base_amount"]) * Decimal("0.15"))
            if not row["tax_code"]:
                reasons.append("MISSING_TAX_CODE")
            if not row["return_box"]:
                reasons.append("MISSING_RETURN_BOX")
            if row["category"] == "STANDARD" and abs(_decimal(row["vat_amount"]) - expected) > Decimal("0.02"):
                reasons.append("VAT_CALCULATION_MISMATCH")
            if row["vat_amount"] and not row["vat_number"]:
                reasons.append("MISSING_PARTY_VAT_NUMBER")
            if reasons:
                rows.append({**row, "exception_reason": ", ".join(reasons)})
        columns = [
            _col("document_no", "رقم المستند", "Document No."),
            _col("date", "التاريخ", "Date", "date"),
            _col("party_name", "الطرف", "Party"),
            _col("description", "البيان", "Description"),
            _col("base_amount", "الأساس", "Base", "money"),
            _col("vat_amount", "الضريبة", "VAT", "money"),
            _col("exception_reason", "سبب الاستثناء", "Exception Reason"),
        ]
        return columns, rows, {"exceptions": len(rows)}, []
    if code == "VAT-09":
        notes = db.scalars(
            select(CreditNote)
            .where(
                CreditNote.company_id == data.company_id,
                CreditNote.note_date.between(period["start"], period["end"]),
            )
            .options(selectinload(CreditNote.party))
            .order_by(CreditNote.note_date, CreditNote.number)
            .limit(data.limit)
        ).all()
        rows = [{
            "number": note.number, "date": note.note_date, "type": note.note_type,
            "original_document": note.original_document_number, "party": note.party.name_ar,
            "reason_code": note.reason_code, "reason": note.reason, "base_adjustment": -_decimal(note.subtotal),
            "vat_adjustment": -_decimal(note.vat_amount), "status": note.status,
        } for note in notes]
        return [
            _col("number", "رقم الإشعار", "Credit Note No."),
            _col("date", "التاريخ", "Date", "date"),
            _col("type", "النوع", "Type"),
            _col("original_document", "المستند الأصلي", "Original Document"),
            _col("party", "الطرف", "Party"),
            _col("reason_code", "كود السبب", "Reason Code"),
            _col("reason", "السبب", "Reason"),
            _col("base_adjustment", "تعديل الأساس", "Base Adjustment", "money"),
            _col("vat_adjustment", "تعديل الضريبة", "VAT Adjustment", "money"),
            _col("status", "الحالة", "Status"),
        ], rows, {"vat_adjustment": money(sum((_decimal(row["vat_adjustment"]) for row in rows), ZERO))}, []
    rows = [
        {"balance_type": "OUTPUT_VAT", "amount": vat["output_vat"]},
        {"balance_type": "INPUT_VAT", "amount": vat["input_vat"]},
        {"balance_type": "NET_PAYABLE" if _decimal(vat["net_vat_payable"]) >= 0 else "NET_RECEIVABLE", "amount": abs(_decimal(vat["net_vat_payable"]))},
    ]
    return [_col("balance_type", "نوع الرصيد", "Balance Type"), _col("amount", "المبلغ", "Amount", "money")], rows, {"net_vat_payable": vat["net_vat_payable"]}, []


INCOME_LABELS = [
    ("revenue", "الإيرادات", "Revenue"),
    ("cost_of_revenue", "تكلفة الإيرادات", "Cost of Revenue"),
    ("gross_profit", "مجمل الربح", "Gross Profit"),
    ("operating_expenses", "المصروفات التشغيلية", "Operating Expenses"),
    ("operating_profit", "الربح التشغيلي", "Operating Profit"),
    ("other_income", "إيرادات أخرى", "Other Income"),
    ("other_expenses", "مصروفات أخرى", "Other Expenses"),
    ("finance_cost", "تكلفة التمويل", "Finance Cost"),
    ("zakat_tax", "الزكاة والضريبة", "Zakat and Tax"),
    ("net_profit", "صافي الربح", "Net Profit"),
]
POSITION_LABELS = [
    ("current_assets", "الأصول المتداولة", "Current Assets"),
    ("non_current_assets", "الأصول غير المتداولة", "Non-current Assets"),
    ("total_assets", "إجمالي الأصول", "Total Assets"),
    ("current_liabilities", "الخصوم المتداولة", "Current Liabilities"),
    ("non_current_liabilities", "الخصوم غير المتداولة", "Non-current Liabilities"),
    ("total_liabilities", "إجمالي الخصوم", "Total Liabilities"),
    ("equity", "حقوق الملكية", "Equity"),
]
CASH_LABELS = [
    ("net_operating", "صافي التشغيل", "Net Operating"),
    ("net_investing", "صافي الاستثمار", "Net Investing"),
    ("net_financing", "صافي التمويل", "Net Financing"),
    ("net_change", "صافي التغير", "Net Change"),
    ("opening_cash", "النقد الافتتاحي", "Opening Cash"),
    ("closing_cash", "النقد الختامي", "Closing Cash"),
    ("cash_reconciliation_difference", "فرق المطابقة", "Reconciliation Difference"),
]


def _statement(db: Session, data: ReportRunIn, user: User, start: date, end: date) -> dict:
    return financial_statements(
        company_id=data.company_id,
        start_date=start,
        end_date=end,
        method=data.method,
        user=user,
        db=db,
    )


def _financial_report(db: Session, data: ReportRunIn, period: dict, user: User) -> tuple:
    current = _statement(db, data, user, period["start"], period["end"])
    prior = _statement(db, data, user, period["prior_start"], period["prior_end"])
    prior_year = _statement(db, data, user, period["prior_year_start"], period["prior_year_end"])
    code = data.report_code
    if code in {"FS-01", "FS-02", "FS-03", "FS-11", "FS-12"}:
        section, labels = "income_statement", INCOME_LABELS
    elif code in {"FS-04", "FS-05", "FS-06"}:
        section, labels = "financial_position", POSITION_LABELS
    elif code in {"FS-07", "FS-08", "FS-09"}:
        section, labels = "cash_flows", CASH_LABELS
    else:
        section, labels = "changes_in_equity", [
            ("opening", "حقوق الملكية الافتتاحية", "Opening Equity"),
            ("capital_contributions", "مساهمات رأس المال", "Capital Contributions"),
            ("profit", "ربح الفترة", "Period Profit"),
            ("dividends", "توزيعات الأرباح", "Dividends"),
            ("other_comprehensive_income", "الدخل الشامل الآخر", "Other Comprehensive Income"),
            ("closing", "حقوق الملكية الختامية", "Closing Equity"),
        ]
    rows = []
    for key, ar, en in labels:
        value = _decimal(current.get(section, {}).get(key))
        previous = _decimal(prior.get(section, {}).get(key))
        py = _decimal(prior_year.get(section, {}).get(key))
        denominator = abs(previous)
        rows.append({
            "line_code": key,
            "line_ar": ar,
            "line_en": en,
            "current": value,
            "prior_period": previous,
            "prior_year": py,
            "variance": money(value - previous),
            "variance_percent": money((value - previous) / denominator * 100) if denominator else None,
        })
    if code == "FS-12":
        base = abs(_decimal(current.get(section, {}).get("revenue" if section == "income_statement" else "total_assets")))
        for row in rows:
            row["common_size_percent"] = money(_decimal(row["current"]) / base * 100) if base else None
    columns = [
        _col("line_code", "الكود", "Code"),
        _col("line_ar", "البند", "Arabic Line"),
        _col("line_en", "البند بالإنجليزية", "English Line"),
        _col("current", "الفترة الحالية", "Current", "money"),
        _col("prior_period", "الفترة السابقة", "Prior Period", "money"),
        _col("prior_year", "الفترة المقارنة", "Prior Year", "money"),
        _col("variance", "الانحراف", "Variance", "money"),
        _col("variance_percent", "نسبة الانحراف", "Variance %", "percent"),
    ]
    if code == "FS-12":
        columns.append(_col("common_size_percent", "النسبة الرأسية", "Common Size %", "percent"))
    warnings = []
    if section == "cash_flows" and current.get("cash_flows", {}).get("classification_complete") is False:
        warnings.append("توجد حركات نقدية غير مصنفة ويجب مراجعتها قبل اعتماد قائمة التدفقات.")
    return columns, rows, {}, warnings


def _aging(db: Session, data: ReportRunIn, period: dict, ledger: str) -> tuple[list[dict], list[dict], dict, list[str]]:
    effective = period["end"]
    query = (
        select(FinancialOpenItem)
        .where(
            FinancialOpenItem.company_id == data.company_id,
            FinancialOpenItem.ledger_type == ledger,
            FinancialOpenItem.document_date <= effective,
        )
        .options(selectinload(FinancialOpenItem.party), selectinload(FinancialOpenItem.allocations))
        .order_by(FinancialOpenItem.party_id, FinancialOpenItem.due_date)
    )
    if data.party_id:
        query = query.where(FinancialOpenItem.party_id == data.party_id)
    summaries: dict[int, dict] = {}
    details = []
    for item in db.scalars(query.limit(data.limit)).all():
        allocated = sum((_decimal(a.amount) for a in item.allocations if a.allocation_date <= effective and a.reversed_at is None), ZERO)
        outstanding = money(_decimal(item.original_amount) - allocated)
        if outstanding <= 0:
            continue
        days = max(0, (effective - item.due_date).days)
        bucket = "CURRENT" if days == 0 else "1_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "91_120" if days <= 120 else "OVER_120"
        details.append({
            "party_code": item.party.code, "party_name": item.party.name_ar, "document_no": item.document_number,
            "document_date": item.document_date, "due_date": item.due_date, "overdue_days": days,
            "bucket": bucket, "original_amount": _decimal(item.original_amount), "outstanding_amount": outstanding,
        })
        summary = summaries.setdefault(item.party_id, {
            "party_code": item.party.code, "party_name": item.party.name_ar, "credit_limit": _decimal(item.party.credit_limit),
            "CURRENT": ZERO, "1_30": ZERO, "31_60": ZERO, "61_90": ZERO, "91_120": ZERO, "OVER_120": ZERO, "total": ZERO,
        })
        summary[bucket] += outstanding
        summary["total"] += outstanding
    summary_rows = list(summaries.values())
    columns = [
        _col("party_code", "كود الطرف", "Party Code"),
        _col("party_name", "اسم الطرف", "Party"),
        _col("CURRENT", "حالي", "Current", "money"),
        _col("1_30", "1-30", "1-30", "money"),
        _col("31_60", "31-60", "31-60", "money"),
        _col("61_90", "61-90", "61-90", "money"),
        _col("91_120", "91-120", "91-120", "money"),
        _col("OVER_120", "+120", "Over 120", "money"),
        _col("total", "الإجمالي", "Total", "money"),
    ]
    totals = {"total": money(sum((_decimal(row["total"]) for row in summary_rows), ZERO))}
    return columns, summary_rows, totals, []


def _sales_purchase_report(db: Session, data: ReportRunIn, period: dict) -> tuple:
    code = data.report_code
    if code in {"SAL-01", "VAT-01"}:
        invoices = db.scalars(
            select(SalesInvoice).where(
                SalesInvoice.company_id == data.company_id,
                SalesInvoice.invoice_date.between(period["start"], period["end"]),
            ).options(selectinload(SalesInvoice.customer)).order_by(SalesInvoice.invoice_date, SalesInvoice.number).limit(data.limit)
        ).all()
        rows = [{"number": x.number, "date": x.invoice_date, "due_date": x.due_date, "party_code": x.customer.code,
                 "party_name": x.customer.name_ar, "subtotal": _decimal(x.subtotal), "vat": _decimal(x.vat_amount),
                 "total": _decimal(x.total), "status": x.status} for x in invoices]
        return [
            _col("number", "رقم الفاتورة", "Invoice No."), _col("date", "التاريخ", "Date", "date"),
            _col("due_date", "تاريخ الاستحقاق", "Due Date", "date"), _col("party_code", "كود العميل", "Customer Code"),
            _col("party_name", "العميل", "Customer"), _col("subtotal", "الصافي", "Subtotal", "money"),
            _col("vat", "الضريبة", "VAT", "money"), _col("total", "الإجمالي", "Total", "money"),
            _col("status", "الحالة", "Status"),
        ], rows, {"total": money(sum((_decimal(x["total"]) for x in rows), ZERO))}, []
    if code == "SAL-02":
        rows0 = db.scalars(select(Receipt).where(
            Receipt.company_id == data.company_id, Receipt.receipt_date.between(period["start"], period["end"])
        ).options(selectinload(Receipt.customer), selectinload(Receipt.bank_account)).order_by(Receipt.receipt_date, Receipt.number).limit(data.limit)).all()
        rows = [{"number": x.number, "date": x.receipt_date, "customer": x.customer.name_ar, "bank": x.bank_account.bank_name_ar,
                 "amount": _decimal(x.amount), "reference": x.reference} for x in rows0]
        return [
            _col("number", "رقم السند", "Receipt No."), _col("date", "التاريخ", "Date", "date"),
            _col("customer", "العميل", "Customer"), _col("bank", "الحساب البنكي", "Bank"),
            _col("amount", "المبلغ", "Amount", "money"), _col("reference", "المرجع", "Reference"),
        ], rows, {"amount": money(sum((_decimal(x["amount"]) for x in rows), ZERO))}, []
    if code in {"SAL-03", "SAL-04", "SAL-12"}:
        columns, summary, totals, warnings = _aging(db, data, period, "AR")
        if code == "SAL-03":
            rows = [x for x in summary if sum((_decimal(x[b]) for b in ("1_30", "31_60", "61_90", "91_120", "OVER_120")), ZERO) > 0]
        elif code == "SAL-12":
            rows = [{**x, "excess": money(_decimal(x["total"]) - _decimal(x["credit_limit"]))} for x in summary if _decimal(x["total"]) > _decimal(x["credit_limit"])]
            columns += [_col("credit_limit", "الحد الائتماني", "Credit Limit", "money"), _col("excess", "التجاوز", "Excess", "money")]
        else:
            rows = summary
        return columns, rows, totals, warnings
    if code in {"SAL-05", "PUR-03"}:
        sales = code == "SAL-05"
        model = SalesInvoice if sales else PurchaseInvoice
        party_column = model.customer_id if sales else model.supplier_id
        date_column = model.invoice_date
        query = (
            select(Party.code, Party.name_ar, Party.name_en, func.count(model.id), func.sum(model.subtotal), func.sum(model.vat_amount), func.sum(model.total))
            .join(model, party_column == Party.id)
            .where(model.company_id == data.company_id, date_column.between(period["start"], period["end"]), model.status.in_(POSTED))
            .group_by(Party.id).order_by(func.sum(model.total).desc()).limit(data.limit)
        )
        rows = [{"party_code": x[0], "party_name_ar": x[1], "party_name_en": x[2], "document_count": x[3],
                 "subtotal": _decimal(x[4]), "vat": _decimal(x[5]), "total": _decimal(x[6])} for x in db.execute(query).all()]
        return [
            _col("party_code", "كود الطرف", "Party Code"), _col("party_name_ar", "اسم الطرف", "Arabic Name"),
            _col("party_name_en", "الاسم بالإنجليزية", "English Name"), _col("document_count", "عدد المستندات", "Documents", "integer"),
            _col("subtotal", "الصافي", "Subtotal", "money"), _col("vat", "الضريبة", "VAT", "money"),
            _col("total", "الإجمالي", "Total", "money"),
        ], rows, {"total": money(sum((_decimal(x["total"]) for x in rows), ZERO))}, []
    if code == "SAL-06":
        query = (
            select(PosOrder.customer_name, func.count(PosOrder.id), func.sum(PosOrder.subtotal), func.sum(PosOrder.food_cost))
            .where(
                PosOrder.company_id == data.company_id,
                PosOrder.order_date.between(period["start"], period["end"]),
                PosOrder.status.in_(POSTED),
            )
            .group_by(PosOrder.customer_name).order_by((func.sum(PosOrder.subtotal) - func.sum(PosOrder.food_cost)).desc()).limit(data.limit)
        )
        rows = [{"customer": x[0] or "عميل نقدي", "orders": x[1], "revenue": _decimal(x[2]), "actual_cost": _decimal(x[3]),
                 "gross_profit": money(_decimal(x[2]) - _decimal(x[3])),
                 "margin_percent": money(((_decimal(x[2]) - _decimal(x[3])) / _decimal(x[2]) * 100)) if _decimal(x[2]) else None} for x in db.execute(query).all()]
        return [
            _col("customer", "العميل", "Customer"), _col("orders", "عدد الطلبات", "Orders", "integer"),
            _col("revenue", "الإيراد", "Revenue", "money"), _col("actual_cost", "التكلفة الفعلية", "Actual Cost", "money"),
            _col("gross_profit", "مجمل الربح", "Gross Profit", "money"), _col("margin_percent", "هامش الربح", "Margin %", "percent"),
        ], rows, {}, ["تعتمد الربحية على مبيعات نقاط البيع ذات تكلفة الطعام الفعلية؛ فواتير المبيعات العامة لا تحتوي بعدُ على ربط صنف/تكلفة ولا تُقدّر بقيم وهمية."]
    if code in {"SAL-07", "SAL-08"}:
        grouped: dict[str, dict] = {}
        invoice_lines = db.scalars(
            select(SalesInvoiceLine).join(SalesInvoice).where(
                SalesInvoice.company_id == data.company_id,
                SalesInvoice.invoice_date.between(period["start"], period["end"]),
                SalesInvoice.status.in_(POSTED),
            )
        ).all()
        for line in invoice_lines:
            item = grouped.setdefault(line.description, {"product": line.description, "quantity": ZERO, "net_sales": ZERO, "vat": ZERO, "gross_sales": ZERO})
            item["quantity"] += _decimal(line.quantity); item["net_sales"] += _decimal(line.subtotal)
            item["vat"] += _decimal(line.vat_amount); item["gross_sales"] += _decimal(line.total)
        pos_lines = db.scalars(
            select(PosOrderLine).join(PosOrder).where(
                PosOrder.company_id == data.company_id,
                PosOrder.order_date.between(period["start"], period["end"]),
                PosOrder.status.in_(POSTED),
            ).options(selectinload(PosOrderLine.menu_item))
        ).all()
        for line in pos_lines:
            name = line.menu_item.name_ar
            item = grouped.setdefault(name, {"product": name, "quantity": ZERO, "net_sales": ZERO, "vat": ZERO, "gross_sales": ZERO})
            item["quantity"] += _decimal(line.quantity); item["net_sales"] += _decimal(line.net_amount)
            item["vat"] += _decimal(line.vat_amount); item["gross_sales"] += _decimal(line.total_amount)
        rows = sorted(grouped.values(), key=lambda x: (_decimal(x["quantity"]), _decimal(x["gross_sales"])), reverse=code == "SAL-07")[:data.limit]
        return [
            _col("product", "المنتج", "Product"), _col("quantity", "الكمية", "Quantity", "number"),
            _col("net_sales", "صافي المبيعات", "Net Sales", "money"), _col("vat", "الضريبة", "VAT", "money"),
            _col("gross_sales", "إجمالي المبيعات", "Gross Sales", "money"),
        ], rows, {}, []
    if code == "SAL-09":
        sold_item_ids = set(db.scalars(
            select(MenuItem.inventory_item_id).join(PosOrderLine, PosOrderLine.menu_item_id == MenuItem.id).join(
                PosOrder, PosOrder.id == PosOrderLine.pos_order_id
            ).where(
                PosOrder.company_id == data.company_id,
                PosOrder.order_date.between(period["start"], period["end"]),
                PosOrder.status.in_(POSTED),
            )
        ).all())
        rows0 = db.scalars(select(Item).where(Item.company_id == data.company_id, Item.active.is_(True)).order_by(Item.code)).all()
        rows = [{"item_code": x.code, "name_ar": x.name_ar, "name_en": x.name_en, "uom": x.uom, "standard_cost": _decimal(x.standard_cost)}
                for x in rows0 if x.id not in sold_item_ids]
        return [
            _col("item_code", "كود الصنف", "Item Code"), _col("name_ar", "اسم الصنف", "Arabic Name"),
            _col("name_en", "الاسم بالإنجليزية", "English Name"), _col("uom", "الوحدة", "UOM"),
            _col("standard_cost", "التكلفة المعيارية", "Standard Cost", "money"),
        ], rows, {"items": len(rows)}, ["يشمل الفحص الأصناف المرتبطة فعليًا بمبيعات POS؛ أوصاف فواتير البيع الحرة لا تنشئ ارتباطًا وهميًا بسجل الأصناف."]
    if code in {"SAL-10", "SAL-11"}:
        parties = db.scalars(select(Party).where(
            Party.company_id == data.company_id, Party.party_type.in_(("CUSTOMER", "BOTH"))
        ).order_by(Party.code).limit(data.limit)).all()
        rows = [{"account_no": x.code, "name_ar": x.name_ar, "name_en": x.name_en, "vat_number": x.vat_number or "",
                 "credit_limit": _decimal(x.credit_limit), "active": x.active} for x in parties]
        columns = [_col("account_no", "الرقم الحسابي", "Account No."), _col("name_ar", "اسم العميل", "Arabic Name"),
                   _col("name_en", "الاسم بالإنجليزية", "English Name"), _col("vat_number", "الرقم الضريبي", "VAT Number")]
        if code == "SAL-10":
            columns += [_col("credit_limit", "الحد الائتماني", "Credit Limit", "money"), _col("active", "نشط", "Active", "boolean")]
        return columns, rows, {"customers": len(rows)}, []
    if code == "PUR-01":
        invoices = db.scalars(select(PurchaseInvoice).where(
            PurchaseInvoice.company_id == data.company_id, PurchaseInvoice.invoice_date.between(period["start"], period["end"])
        ).options(selectinload(PurchaseInvoice.supplier)).order_by(PurchaseInvoice.invoice_date, PurchaseInvoice.number).limit(data.limit)).all()
        rows = [{"number": x.number, "supplier_invoice_no": x.supplier_invoice_number, "date": x.invoice_date,
                 "due_date": x.due_date, "supplier_code": x.supplier.code, "supplier": x.supplier.name_ar,
                 "subtotal": _decimal(x.subtotal), "vat": _decimal(x.vat_amount), "total": _decimal(x.total), "status": x.status} for x in invoices]
        return [
            _col("number", "رقم الفاتورة", "Invoice No."), _col("supplier_invoice_no", "فاتورة المورد", "Supplier Invoice"),
            _col("date", "التاريخ", "Date", "date"), _col("due_date", "الاستحقاق", "Due Date", "date"),
            _col("supplier_code", "كود المورد", "Supplier Code"), _col("supplier", "المورد", "Supplier"),
            _col("subtotal", "الصافي", "Subtotal", "money"), _col("vat", "الضريبة", "VAT", "money"),
            _col("total", "الإجمالي", "Total", "money"), _col("status", "الحالة", "Status"),
        ], rows, {"total": money(sum((_decimal(x["total"]) for x in rows), ZERO))}, []
    if code in {"PUR-02", "PUR-05"}:
        columns, summary, totals, warnings = _aging(db, data, period, "AP")
        if code == "PUR-02":
            return columns, summary, totals, warnings
        query = select(FinancialOpenItem).where(
            FinancialOpenItem.company_id == data.company_id,
            FinancialOpenItem.ledger_type == "AP",
            FinancialOpenItem.document_date <= period["end"],
        ).options(selectinload(FinancialOpenItem.party), selectinload(FinancialOpenItem.allocations)).order_by(FinancialOpenItem.due_date).limit(data.limit)
        details = []
        for x in db.scalars(query).all():
            allocated = sum((_decimal(a.amount) for a in x.allocations if a.allocation_date <= period["end"] and a.reversed_at is None), ZERO)
            outstanding = money(_decimal(x.original_amount) - allocated)
            if outstanding > 0:
                details.append({"supplier_code": x.party.code, "supplier": x.party.name_ar, "document_no": x.document_number,
                                "document_date": x.document_date, "due_date": x.due_date,
                                "days_overdue": max(0, (period["end"] - x.due_date).days), "outstanding": outstanding,
                                "due_status": "OVERDUE" if x.due_date < period["end"] else "DUE"})
        return [
            _col("supplier_code", "كود المورد", "Supplier Code"), _col("supplier", "المورد", "Supplier"),
            _col("document_no", "رقم المستند", "Document No."), _col("document_date", "تاريخ المستند", "Document Date", "date"),
            _col("due_date", "الاستحقاق", "Due Date", "date"), _col("days_overdue", "أيام التأخير", "Days Overdue", "integer"),
            _col("outstanding", "المبلغ المستحق", "Outstanding", "money"), _col("due_status", "الحالة", "Due Status"),
        ], details, {"outstanding": money(sum((_decimal(x["outstanding"]) for x in details), ZERO))}, warnings
    lines = db.scalars(
        select(PurchaseInvoiceLine).join(PurchaseInvoice).where(
            PurchaseInvoice.company_id == data.company_id,
            PurchaseInvoice.invoice_date.between(period["start"], period["end"]),
            PurchaseInvoice.status.in_(POSTED),
        ).options(selectinload(PurchaseInvoiceLine.invoice)).order_by(PurchaseInvoiceLine.description, PurchaseInvoice.invoice_date)
    ).all()
    grouped: dict[str, list] = defaultdict(list)
    for line in lines:
        grouped[line.description].append(line)
    rows = []
    for description, values in grouped.items():
        first, last = values[0], values[-1]
        old, new = _decimal(first.unit_price), _decimal(last.unit_price)
        rows.append({"description": description, "first_date": first.invoice.invoice_date, "last_date": last.invoice.invoice_date,
                     "old_price": old, "new_price": new, "change": money(new - old),
                     "change_percent": money((new - old) / abs(old) * 100) if old else None, "invoice_count": len(values)})
    return [
        _col("description", "الصنف / البيان", "Item / Description"), _col("first_date", "أول تاريخ", "First Date", "date"),
        _col("last_date", "آخر تاريخ", "Last Date", "date"), _col("old_price", "السعر السابق", "Old Price", "money"),
        _col("new_price", "السعر الحالي", "New Price", "money"), _col("change", "التغير", "Change", "money"),
        _col("change_percent", "نسبة التغير", "Change %", "percent"), _col("invoice_count", "عدد الفواتير", "Invoices", "integer"),
    ], rows[:data.limit], {}, []


def _inventory_report(db: Session, data: ReportRunIn, period: dict, user: User) -> tuple:
    code = data.report_code
    query = select(StockMovement).where(
        StockMovement.company_id == data.company_id,
        StockMovement.movement_date <= period["end"],
    ).options(selectinload(StockMovement.item), selectinload(StockMovement.warehouse))
    if code == "INV-02":
        query = query.where(StockMovement.movement_date >= period["start"])
    if data.item_id:
        query = query.where(StockMovement.item_id == data.item_id)
    if data.branch_id:
        ensure_branch_access(db, user, data.company_id, data.branch_id)
        query = query.join(Warehouse).where(Warehouse.branch_id == data.branch_id)
    movements = db.scalars(query.order_by(StockMovement.movement_date, StockMovement.id).limit(data.limit)).all()
    if code == "INV-02":
        running: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        rows = []
        for x in movements:
            key = (x.item_id, x.warehouse_id)
            running[key] += _decimal(x.quantity)
            rows.append({"date": x.movement_date, "item_code": x.item.code, "item": x.item.name_ar,
                         "warehouse": x.warehouse.name_ar, "movement_type": x.movement_type, "reference_type": x.reference_type,
                         "quantity": _decimal(x.quantity), "unit_cost": _decimal(x.unit_cost), "value": _decimal(x.total_cost),
                         "running_quantity": running[key]})
        return [
            _col("date", "التاريخ", "Date", "date"), _col("item_code", "كود الصنف", "Item Code"),
            _col("item", "الصنف", "Item"), _col("warehouse", "المستودع", "Warehouse"),
            _col("movement_type", "نوع الحركة", "Movement Type"), _col("reference_type", "المرجع", "Reference"),
            _col("quantity", "الكمية", "Quantity", "number"), _col("unit_cost", "تكلفة الوحدة", "Unit Cost", "money"),
            _col("value", "القيمة", "Value", "money"), _col("running_quantity", "الرصيد التراكمي", "Running Quantity", "number"),
        ], rows, {}, []
    grouped: dict[tuple, dict] = {}
    for x in movements:
        key = (x.item_id, x.warehouse_id)
        item = grouped.setdefault(key, {
            "item_code": x.item.code, "item": x.item.name_ar, "warehouse_code": x.warehouse.code,
            "warehouse": x.warehouse.name_ar, "quantity": ZERO, "carrying_value": ZERO,
            "last_movement_date": None, "earliest_expiry": None,
        })
        item["quantity"] += _decimal(x.quantity)
        item["carrying_value"] += _decimal(x.total_cost)
        if item["last_movement_date"] is None or x.movement_date > item["last_movement_date"]:
            item["last_movement_date"] = x.movement_date
        if x.expiry_date and (item["earliest_expiry"] is None or x.expiry_date < item["earliest_expiry"]):
            item["earliest_expiry"] = x.expiry_date
    rows = []
    for item in grouped.values():
        days = (period["end"] - item["last_movement_date"]).days if item["last_movement_date"] else 99999
        classification = "EXPIRED" if item["earliest_expiry"] and item["earliest_expiry"] < period["end"] else "OBSOLETE" if days >= data.obsolete_days else "SLOW_MOVING" if days >= data.slow_days else "ACTIVE"
        item.update({"days_without_movement": days, "classification": classification,
                     "risk_value": item["carrying_value"] if classification in {"EXPIRED", "OBSOLETE", "SLOW_MOVING"} else ZERO})
        rows.append(item)
    if code == "INV-04":
        rows = [x for x in rows if x["classification"] in {"SLOW_MOVING", "OBSOLETE"}]
    elif code == "INV-05":
        rows = [x for x in rows if x["risk_value"] > 0]
    columns = [
        _col("item_code", "كود الصنف", "Item Code"), _col("item", "الصنف", "Item"),
        _col("warehouse_code", "كود المستودع", "Warehouse Code"), _col("warehouse", "المستودع", "Warehouse"),
        _col("quantity", "الكمية", "Quantity", "number"), _col("carrying_value", "القيمة الدفترية", "Carrying Value", "money"),
    ]
    if code != "INV-01":
        columns += [_col("last_movement_date", "آخر حركة", "Last Movement", "date"),
                    _col("days_without_movement", "أيام بدون حركة", "Days Without Movement", "integer"),
                    _col("earliest_expiry", "أقرب انتهاء", "Earliest Expiry", "date"),
                    _col("classification", "التصنيف", "Classification")]
    if code == "INV-05":
        columns.append(_col("risk_value", "القيمة المعرضة للخطر", "Value at Risk", "money"))
    totals = {"quantity": money(sum((_decimal(x["quantity"]) for x in rows), ZERO)),
              "carrying_value": money(sum((_decimal(x["carrying_value"]) for x in rows), ZERO))}
    if code == "INV-05":
        totals["risk_value"] = money(sum((_decimal(x["risk_value"]) for x in rows), ZERO))
    return columns, rows, totals, []


def _budget_actual(db: Session, data: ReportRunIn, period: dict) -> tuple:
    accounts = {x.id: x for x in db.scalars(select(Account).where(Account.company_id == data.company_id)).all()}
    budgets = db.scalars(
        select(Budget).join(FiscalYear).where(
            Budget.company_id == data.company_id,
            FiscalYear.start_date <= period["end"],
            FiscalYear.end_date >= period["start"],
            Budget.status.in_(("APPROVED", "ACTIVE", "POSTED")),
        ).options(selectinload(Budget.lines))
    ).all()
    budget_map: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for budget in budgets:
        for line in budget.lines:
            budget_map[line.account_id] += _decimal(line.amount)
    actual_rows = account_balances(db, data.company_id, period["end"], period["start"])
    actual_map = {x["id"]: _decimal(x["credit"]) - _decimal(x["debit"]) if x["account_type"] in {"REVENUE", "LIABILITY", "EQUITY"} else _decimal(x["debit"]) - _decimal(x["credit"]) for x in actual_rows}
    rows = []
    for account_id in sorted(set(budget_map) | set(actual_map), key=lambda x: accounts[x].code if x in accounts else ""):
        account = accounts.get(account_id)
        if not account:
            continue
        budget = budget_map[account_id]
        actual = actual_map.get(account_id, ZERO)
        rows.append({"account_code": account.code, "account_ar": account.name_ar, "account_en": account.name_en,
                     "budget": budget, "actual": actual, "variance": money(actual - budget),
                     "variance_percent": money((actual - budget) / abs(budget) * 100) if budget else None})
    return [
        _col("account_code", "رقم الحساب", "Account Code"), _col("account_ar", "اسم الحساب", "Arabic Account"),
        _col("account_en", "الاسم بالإنجليزية", "English Account"), _col("budget", "الموازنة", "Budget", "money"),
        _col("actual", "الفعلي", "Actual", "money"), _col("variance", "الانحراف", "Variance", "money"),
        _col("variance_percent", "نسبة الانحراف", "Variance %", "percent"),
    ], rows, {"budget": money(sum((_decimal(x["budget"]) for x in rows), ZERO)), "actual": money(sum((_decimal(x["actual"]) for x in rows), ZERO))}, []


def _gl_cash_asset_control_report(db: Session, data: ReportRunIn, period: dict, user: User) -> tuple:
    code = data.report_code
    if code in {"GL-06", "BUD-01"}:
        return _budget_actual(db, data, period)
    if code in {"GL-01", "GL-02", "GL-03", "GL-04", "GL-05"}:
        if code == "GL-02":
            balances = account_balances(db, data.company_id, period["end"])
            rows, total_debit, total_credit = [], ZERO, ZERO
            for x in balances:
                net = _decimal(x["debit"]) - _decimal(x["credit"])
                debit, credit = max(net, ZERO), max(-net, ZERO)
                total_debit += debit; total_credit += credit
                rows.append({"account_code": x["code"], "account_ar": x["name_ar"], "account_en": x["name_en"],
                             "debit": debit, "credit": credit})
            return [
                _col("account_code", "رقم الحساب", "Account Code"), _col("account_ar", "اسم الحساب", "Arabic Account"),
                _col("account_en", "الاسم بالإنجليزية", "English Account"), _col("debit", "مدين", "Debit", "money"),
                _col("credit", "دائن", "Credit", "money"),
            ], rows, {"debit": money(total_debit), "credit": money(total_credit), "difference": money(total_debit - total_credit)}, []
        query = select(JournalEntry).where(
            JournalEntry.company_id == data.company_id,
            JournalEntry.entry_date.between(period["start"], period["end"]),
        ).options(selectinload(JournalEntry.lines).selectinload(JournalLine.account),
                  selectinload(JournalEntry.lines).selectinload(JournalLine.branch)).order_by(JournalEntry.entry_date, JournalEntry.number)
        if code == "GL-04":
            query = query.where(JournalEntry.entry_origin == "MANUAL")
        elif code == "GL-05":
            query = query.where(JournalEntry.status.not_in(POSTED))
        entries = db.scalars(query.limit(data.limit)).all()
        if code == "GL-01":
            rows = []
            for entry in entries:
                for line in entry.lines:
                    if data.branch_id and line.branch_id != data.branch_id:
                        continue
                    rows.append({"date": entry.entry_date, "journal_no": entry.number, "reference": entry.reference,
                                 "account_code": line.account.code, "account": line.account.name_ar,
                                 "description": line.description or entry.description, "branch": line.branch.name_ar if line.branch else "",
                                 "debit": _decimal(line.debit), "credit": _decimal(line.credit), "status": entry.status})
            return [
                _col("date", "التاريخ", "Date", "date"), _col("journal_no", "رقم القيد", "Journal No."),
                _col("reference", "المرجع", "Reference"), _col("account_code", "رقم الحساب", "Account Code"),
                _col("account", "الحساب", "Account"), _col("description", "البيان", "Description"),
                _col("branch", "الفرع", "Branch"), _col("debit", "مدين", "Debit", "money"),
                _col("credit", "دائن", "Credit", "money"), _col("status", "الحالة", "Status"),
            ], rows, {"debit": money(sum((_decimal(x["debit"]) for x in rows), ZERO)), "credit": money(sum((_decimal(x["credit"]) for x in rows), ZERO))}, []
        rows = [{"date": x.entry_date, "journal_no": x.number, "reference": x.reference, "description": x.description,
                 "origin": x.entry_origin, "debit": _decimal(x.total_debit), "credit": _decimal(x.total_credit),
                 "status": x.status, "created_by": x.created_by, "approved_by": x.approved_by, "posted_by": x.posted_by} for x in entries]
        return [
            _col("date", "التاريخ", "Date", "date"), _col("journal_no", "رقم القيد", "Journal No."),
            _col("reference", "المرجع", "Reference"), _col("description", "البيان", "Description"),
            _col("origin", "المصدر", "Origin"), _col("debit", "مدين", "Debit", "money"),
            _col("credit", "دائن", "Credit", "money"), _col("status", "الحالة", "Status"),
            _col("created_by", "أعد بواسطة", "Prepared By", "integer"), _col("approved_by", "اعتمد بواسطة", "Approved By", "integer"),
            _col("posted_by", "رحّل بواسطة", "Posted By", "integer"),
        ], rows, {"debit": money(sum((_decimal(x["debit"]) for x in rows), ZERO)), "credit": money(sum((_decimal(x["credit"]) for x in rows), ZERO))}, []
    if code == "CASH-01":
        accounts = db.scalars(select(BankAccount).where(BankAccount.company_id == data.company_id, BankAccount.active.is_(True)).options(selectinload(BankAccount.gl_account))).all()
        rows = []
        for account in accounts:
            amount = db.scalar(
                select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
                .join(JournalEntry).where(
                    JournalEntry.company_id == data.company_id, JournalEntry.entry_date <= period["end"],
                    JournalEntry.status.in_(POSTED), JournalLine.account_id == account.gl_account_id,
                )
            )
            latest = db.scalar(select(BankStatement).where(
                BankStatement.company_id == data.company_id, BankStatement.bank_account_id == account.id,
                BankStatement.statement_date <= period["end"],
            ).order_by(BankStatement.statement_date.desc()))
            rows.append({"bank_code": account.code, "bank_name": account.bank_name_ar, "gl_account": account.gl_account.code,
                         "gl_balance": _decimal(amount), "statement_balance": _decimal(latest.closing_balance) if latest else None,
                         "statement_date": latest.statement_date if latest else None,
                         "difference": money(_decimal(amount) - _decimal(latest.closing_balance)) if latest else None})
        return [
            _col("bank_code", "كود البنك", "Bank Code"), _col("bank_name", "البنك", "Bank"),
            _col("gl_account", "حساب الأستاذ", "GL Account"), _col("gl_balance", "رصيد الأستاذ", "GL Balance", "money"),
            _col("statement_balance", "رصيد الكشف", "Statement Balance", "money"), _col("statement_date", "تاريخ الكشف", "Statement Date", "date"),
            _col("difference", "الفرق", "Difference", "money"),
        ], rows, {"gl_balance": money(sum((_decimal(x["gl_balance"]) for x in rows), ZERO))}, []
    if code == "CASH-02":
        statements = db.scalars(select(BankStatement).where(
            BankStatement.company_id == data.company_id, BankStatement.statement_date <= period["end"]
        ).options(selectinload(BankStatement.bank_account), selectinload(BankStatement.lines)).order_by(BankStatement.statement_date.desc()).limit(data.limit)).all()
        rows = []
        for statement in statements:
            matched = sum(1 for line in statement.lines if line.status == "MATCHED")
            unmatched_amount = sum((_decimal(line.amount) for line in statement.lines if line.status != "MATCHED"), ZERO)
            rows.append({"statement_id": statement.id, "bank": statement.bank_account.bank_name_ar, "date": statement.statement_date,
                         "opening_balance": _decimal(statement.opening_balance), "closing_balance": _decimal(statement.closing_balance),
                         "line_count": len(statement.lines), "matched_lines": matched, "unmatched_lines": len(statement.lines) - matched,
                         "unmatched_amount": money(unmatched_amount), "status": statement.status})
        return [
            _col("statement_id", "رقم الكشف", "Statement ID", "integer"), _col("bank", "البنك", "Bank"),
            _col("date", "التاريخ", "Date", "date"), _col("opening_balance", "الرصيد الافتتاحي", "Opening Balance", "money"),
            _col("closing_balance", "الرصيد الختامي", "Closing Balance", "money"), _col("line_count", "عدد الحركات", "Lines", "integer"),
            _col("matched_lines", "حركات مطابقة", "Matched", "integer"), _col("unmatched_lines", "غير مطابقة", "Unmatched", "integer"),
            _col("unmatched_amount", "مبلغ غير مطابق", "Unmatched Amount", "money"), _col("status", "الحالة", "Status"),
        ], rows, {"unmatched_amount": money(sum((_decimal(x["unmatched_amount"]) for x in rows), ZERO))}, []
    if code == "FA-01":
        query = select(FixedAsset).where(FixedAsset.company_id == data.company_id, FixedAsset.acquisition_date <= period["end"]).options(selectinload(FixedAsset.category))
        condition = branch_scope_condition(db, user, data.company_id, FixedAsset)
        if condition is not None:
            query = query.where(condition)
        if data.branch_id:
            ensure_branch_access(db, user, data.company_id, data.branch_id); query = query.where(FixedAsset.branch_id == data.branch_id)
        assets = db.scalars(query.order_by(FixedAsset.asset_number).limit(data.limit)).all()
        rows = [{"asset_no": x.asset_number, "name_ar": x.name_ar, "name_en": x.name_en, "category": x.category.name_ar,
                 "acquisition_date": x.acquisition_date, "in_service_date": x.in_service_date, "cost": _decimal(x.cost),
                 "accumulated_depreciation": _decimal(x.accumulated_depreciation), "accumulated_impairment": _decimal(x.accumulated_impairment),
                 "net_book_value": _decimal(x.net_book_value), "status": x.status, "branch_id": x.branch_id} for x in assets]
        return [
            _col("asset_no", "رقم الأصل", "Asset No."), _col("name_ar", "اسم الأصل", "Arabic Name"),
            _col("name_en", "الاسم بالإنجليزية", "English Name"), _col("category", "الفئة", "Category"),
            _col("acquisition_date", "تاريخ الشراء", "Acquisition Date", "date"), _col("in_service_date", "تاريخ التشغيل", "In-service Date", "date"),
            _col("cost", "التكلفة", "Cost", "money"), _col("accumulated_depreciation", "مجمع الإهلاك", "Accumulated Depreciation", "money"),
            _col("accumulated_impairment", "مجمع الانخفاض", "Accumulated Impairment", "money"), _col("net_book_value", "صافي القيمة", "Net Book Value", "money"),
            _col("status", "الحالة", "Status"), _col("branch_id", "معرف الفرع", "Branch ID", "integer"),
        ], rows, {"cost": money(sum((_decimal(x["cost"]) for x in rows), ZERO)), "net_book_value": money(sum((_decimal(x["net_book_value"]) for x in rows), ZERO))}, []
    if code == "FA-02":
        rows0 = db.scalars(select(AssetDepreciation).join(FixedAsset).where(
            FixedAsset.company_id == data.company_id, AssetDepreciation.period_date.between(period["start"], period["end"])
        ).options(selectinload(AssetDepreciation.asset)).order_by(AssetDepreciation.period_date, FixedAsset.asset_number).limit(data.limit)).all()
        rows = [{"period_date": x.period_date, "asset_no": x.asset.asset_number, "asset": x.asset.name_ar,
                 "opening_nbv": _decimal(x.opening_nbv), "depreciation": _decimal(x.depreciation),
                 "closing_nbv": _decimal(x.closing_nbv), "journal_id": x.journal_id, "posted_at": x.posted_at} for x in rows0]
        return [
            _col("period_date", "الفترة", "Period", "date"), _col("asset_no", "رقم الأصل", "Asset No."),
            _col("asset", "الأصل", "Asset"), _col("opening_nbv", "القيمة الافتتاحية", "Opening NBV", "money"),
            _col("depreciation", "الإهلاك", "Depreciation", "money"), _col("closing_nbv", "القيمة الختامية", "Closing NBV", "money"),
            _col("journal_id", "رقم القيد", "Journal ID", "integer"), _col("posted_at", "تاريخ الترحيل", "Posted At", "datetime"),
        ], rows, {"depreciation": money(sum((_decimal(x["depreciation"]) for x in rows), ZERO))}, []
    if code == "AUD-01":
        start_dt, end_dt = period["start"].isoformat(), (period["end"] + timedelta(days=1)).isoformat()
        rows0 = db.scalars(select(AuditLog).where(
            AuditLog.company_id == data.company_id, AuditLog.created_at >= start_dt, AuditLog.created_at < end_dt
        ).order_by(AuditLog.sequence_number, AuditLog.id).limit(data.limit)).all()
        rows = [{"sequence": x.sequence_number, "timestamp": x.created_at, "user_id": x.user_id, "action": x.action,
                 "entity_type": x.entity_type, "entity_id": x.entity_id, "previous_hash": x.previous_hash,
                 "record_hash": x.record_hash, "before": x.before_json or "", "after": x.after_json or ""} for x in rows0]
        return [
            _col("sequence", "التسلسل", "Sequence", "integer"), _col("timestamp", "التوقيت", "Timestamp", "datetime"),
            _col("user_id", "المستخدم", "User ID", "integer"), _col("action", "الإجراء", "Action"),
            _col("entity_type", "نوع الكيان", "Entity Type"), _col("entity_id", "معرف الكيان", "Entity ID"),
            _col("previous_hash", "البصمة السابقة", "Previous Hash"), _col("record_hash", "بصمة السجل", "Record Hash"),
            _col("before", "قبل", "Before"), _col("after", "بعد", "After"),
        ], rows, {"records": len(rows)}, []
    years = db.scalars(select(FiscalYear).where(
        FiscalYear.company_id == data.company_id, FiscalYear.start_date <= period["end"], FiscalYear.end_date >= period["start"]
    ).options(selectinload(FiscalYear.periods))).all()
    rows = []
    for year in years:
        for fiscal_period in year.periods:
            if fiscal_period.end_date < period["start"] or fiscal_period.start_date > period["end"]:
                continue
            run = db.scalar(select(PeriodCloseRun).where(
                PeriodCloseRun.company_id == data.company_id, PeriodCloseRun.fiscal_period_id == fiscal_period.id
            ).options())
            checks = db.scalars(select(PeriodCloseCheck).where(PeriodCloseCheck.close_run_id == run.id)).all() if run else []
            if not run and fiscal_period.start_date <= date.today():
                calculated = build_close_checks(db, data.company_id, fiscal_period)
                failed = sum(1 for x in calculated if x["status"] == "FAIL")
                warnings = sum(1 for x in calculated if x["status"] == "WARNING")
            else:
                failed = sum(1 for x in checks if x.status == "FAIL")
                warnings = sum(1 for x in checks if x.status == "WARNING")
            rows.append({"year": year.name, "period_no": fiscal_period.number, "period_name": fiscal_period.name_ar,
                         "start_date": fiscal_period.start_date, "end_date": fiscal_period.end_date,
                         "period_status": fiscal_period.status, "close_status": run.status if run else "NOT_REVIEWED",
                         "failed_checks": failed, "warning_checks": warnings,
                         "requested_by": run.requested_by if run else None, "approved_by": run.approved_by if run else None,
                         "closed_at": run.closed_at if run else None})
    return [
        _col("year", "السنة المالية", "Fiscal Year"), _col("period_no", "رقم الفترة", "Period No.", "integer"),
        _col("period_name", "اسم الفترة", "Period Name"), _col("start_date", "من", "Start", "date"),
        _col("end_date", "إلى", "End", "date"), _col("period_status", "حالة الفترة", "Period Status"),
        _col("close_status", "حالة الإقفال", "Close Status"), _col("failed_checks", "فحوص فاشلة", "Failed Checks", "integer"),
        _col("warning_checks", "تحذيرات", "Warnings", "integer"), _col("requested_by", "أعد بواسطة", "Prepared By", "integer"),
        _col("approved_by", "اعتمد بواسطة", "Approved By", "integer"), _col("closed_at", "تاريخ الإقفال", "Closed At", "datetime"),
    ], rows, {"periods": len(rows), "closed": sum(1 for x in rows if x["period_status"] == "CLOSED")}, []


def _dispatch(db: Session, data: ReportRunIn, period: dict, user: User) -> tuple:
    prefix = data.report_code.split("-", 1)[0]
    if prefix == "VAT":
        return _vat_report(db, data, period, user)
    if prefix == "FS":
        return _financial_report(db, data, period, user)
    if prefix in {"SAL", "PUR"}:
        return _sales_purchase_report(db, data, period)
    if prefix == "INV":
        return _inventory_report(db, data, period, user)
    return _gl_cash_asset_control_report(db, data, period, user)


@router.get("/catalog")
def catalog(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_company_access(db, user, company_id)
    permissions = ensure_permission(db, user, company_id, "reports.read")
    profile = db.scalar(select(VatReportingProfile).where(VatReportingProfile.company_id == company_id))
    return {
        "section_name_ar": "مركز التقارير الشامل",
        "section_name_en": "Comprehensive Reporting Center",
        "report_count": len(REPORT_CATALOG),
        "reports": REPORT_CATALOG,
        "vat_profile": {
            "filing_frequency": profile.filing_frequency if profile else "QUARTERLY",
            "return_layout_version": profile.return_layout_version if profile else "ZATCA_STANDARD",
        },
        "can_export": "*" in permissions or "reports.export" in permissions,
        "can_configure_tax": "*" in permissions or "reports.tax.configure" in permissions,
    }


@router.put("/vat-profile")
def update_vat_profile(data: VatProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "reports.tax.configure")
    row = db.scalar(select(VatReportingProfile).where(VatReportingProfile.company_id == data.company_id))
    before = None
    if not row:
        row = VatReportingProfile(company_id=data.company_id, updated_by=user.id)
        db.add(row)
    else:
        before = {"filing_frequency": row.filing_frequency, "return_layout_version": row.return_layout_version}
    row.filing_frequency = data.filing_frequency
    row.return_layout_version = data.return_layout_version
    row.updated_by = user.id
    row.updated_at = utc_now()
    db.flush()
    write_audit(db, action="VAT_REPORTING_PROFILE_UPDATED", entity_type="VAT_REPORTING_PROFILE", entity_id=row.id,
                user_id=user.id, company_id=data.company_id, before=before,
                after={"filing_frequency": row.filing_frequency, "return_layout_version": row.return_layout_version})
    db.commit()
    return {"company_id": data.company_id, "filing_frequency": row.filing_frequency, "return_layout_version": row.return_layout_version}


@router.post("/run")
def run_report(data: ReportRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    code = data.report_code.upper()
    if code not in REPORT_BY_CODE:
        raise HTTPException(404, "System report code not found")
    data.report_code = code
    ensure_permission(db, user, data.company_id, "reports.read")
    if data.branch_id:
        ensure_branch_access(db, user, data.company_id, data.branch_id)
    company = db.get(Company, data.company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    period = _period(data)
    columns, rows, totals, warnings = _dispatch(db, data, period, user)
    rows_json = _jsonable(rows)
    payload_hash = hashlib.sha256(
        json.dumps(rows_json, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    filters = {
        "period_type": data.period_type, "branch_id": data.branch_id, "item_id": data.item_id,
        "party_id": data.party_id, "method": data.method, "slow_days": data.slow_days,
        "obsolete_days": data.obsolete_days,
    }
    audit = SystemReportRun(
        company_id=data.company_id, report_code=code, period_start=period["start"], period_end=period["end"],
        filters_json=json.dumps(filters, ensure_ascii=False), row_count=len(rows_json),
        result_sha256=payload_hash, generated_by=user.id, generated_at=utc_now(),
    )
    db.add(audit)
    db.flush()
    write_audit(db, action="SYSTEM_REPORT_GENERATED", entity_type="SYSTEM_REPORT", entity_id=audit.id,
                user_id=user.id, company_id=data.company_id,
                after={"report_code": code, "row_count": len(rows_json), "result_sha256": payload_hash})
    db.commit()
    definition = REPORT_BY_CODE[code]
    return {
        "run_id": audit.id,
        "report": definition,
        "metadata": {
            "company_id": company.id,
            "company_code": company.code,
            "company_name_ar": company.legal_name_ar or company.name_ar,
            "company_name_en": company.legal_name_en or company.name_en,
            "company_logo_url": company.logo_url,
            "currency": company.currency,
            "vat_number": company.vat_number or "",
            "report_code": code,
            "report_name_ar": definition["name_ar"],
            "report_name_en": definition["name_en"],
            "period_type": period["type"],
            "period_start": period["start"],
            "period_end": period["end"],
            "prior_period_start": period["prior_start"],
            "prior_period_end": period["prior_end"],
            "prior_year_start": period["prior_year_start"],
            "prior_year_end": period["prior_year_end"],
            "filters": filters,
            "generated_at": audit.generated_at,
            "generated_by_id": user.id,
            "generated_by_ar": user.name_ar,
            "generated_by_en": user.name_en,
            "result_sha256": payload_hash,
        },
        "columns": columns,
        "rows": rows_json,
        "totals": _jsonable(totals),
        "warnings": warnings,
        "row_count": len(rows_json),
        "drilldown_supported": code not in {"FS-12", "SAL-09"},
    }


@router.get("/runs")
def report_runs(
    company_id: int,
    report_code: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "reports.read")
    query = select(SystemReportRun).where(SystemReportRun.company_id == company_id)
    if report_code:
        query = query.where(SystemReportRun.report_code == report_code.upper())
    rows = db.scalars(query.order_by(SystemReportRun.generated_at.desc()).limit(limit)).all()
    return [{
        "id": row.id, "report_code": row.report_code, "period_start": row.period_start, "period_end": row.period_end,
        "filters": json.loads(row.filters_json or "{}"), "row_count": row.row_count,
        "result_sha256": row.result_sha256, "generated_by": row.generated_by, "generated_at": row.generated_at,
    } for row in rows]
