"""CORVAX - controlled removal of trial / demo data.

WHY THIS EXISTS
    After exploring the system with demo records the owner needs a clean slate
    before entering real accounting data. Deleting rows by hand across ~90
    transactional tables is impractical and easy to get wrong.

WHAT IT DELETES
    Only MOVEMENT data: journals, invoices, receipts, payments, stock moves, POS
    orders, production orders, projects, commissions, attachments and so on.

WHAT IT KEEPS
    Everything you configured: companies, branches, cost centres, the chart of
    accounts, users, roles, permissions, fiscal periods, warehouses, items,
    parties, employees and bank accounts.

SAFEGUARDS
    * SUPER_ADMIN permission on the company ("*" or data.reset)
    * The caller must echo the exact company name as a confirmation phrase, so a
      mis-click cannot wipe live data
    * Refused when ALLOW_DATA_RESET is false (the default in production)
    * Every run is written to the audit log before the delete happens
    * Scoped to one company; other companies are untouched
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect as sa_inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Company, User
from app.services.audit import write_audit

router = APIRouter(prefix="/data-reset", tags=["data reset"])


# Tables that hold configuration the owner entered deliberately. Never touched.
PRESERVED_TABLES = {
    "alembic_version",
    "companies", "branches", "cost_centers", "accounts", "fiscal_periods",
    "users", "roles", "permissions", "role_permissions", "user_company_roles",
    "user_branch_scopes", "password_history", "user_sessions",
    "warehouses", "items", "item_categories", "parties", "bank_accounts",
    "employees", "asset_categories", "tax_codes", "menu_items", "menu_categories",
    "pos_platforms", "boms", "bom_lines", "work_centers", "journal_sequences",
    "audit_logs",
}

# Order matters: children before parents so foreign keys never block the delete.
DELETE_ORDER = [
    # journals last of the finance group - many tables reference them
    "cip_payments", "cip_progress_certificates", "cip_costs", "cip_contracts", "cip_projects",
    "commission_accruals", "commission_beneficiaries",
    "attachments",
    "pos_order_lines", "pos_orders",
    "kitchen_tickets", "restaurant_reservations", "restaurant_waste_records", "cashier_shifts",
    "gym_access_records", "gym_pt_sessions", "gym_pt_sales", "gym_membership_modifications",
    "gym_facility_bookings", "gym_class_sessions", "gym_membership_states",
    "production_order_lines", "production_orders",
    "quality_inspections", "quality_ncrs",
    "inbound_shipment_lines", "inbound_shipments",
    "stock_movements", "stock_balances",
    "purchase_order_lines", "purchase_orders",
    "receipt_allocations", "payment_allocations",
    "receipts", "payments",
    "sales_invoice_lines", "sales_invoices",
    "purchase_invoice_lines", "purchase_invoices",
    "credit_note_lines", "credit_notes",
    "payroll_run_lines", "payroll_runs", "attendance_records",
    "asset_lifecycle_transactions", "depreciation_runs", "fixed_assets",
    "lease_schedules", "leases",
    "prepaid_schedules", "prepaid_expenses",
    "accrual_entries", "recurring_journal_lines", "recurring_journals",
    "maintenance_work_orders", "maintenance_assets",
    "fleet_trips", "fleet_drivers", "fleet_vehicles",
    "legal_cases", "legal_licenses", "legal_contracts",
    "itsm_tickets", "itsm_assets",
    "crm_opportunities", "crm_leads", "crm_campaigns",
    "vat_returns", "withholding_certificates", "excise_declarations", "zakat_declarations",
    "journal_lines", "journal_entries",
]


class ResetIn(BaseModel):
    company_id: int
    # The caller must type the company name exactly. A mis-click cannot pass this.
    confirmation: str = Field(min_length=1, max_length=250)
    dry_run: bool = True


@router.get("/preview")
def preview_reset(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Row counts that WOULD be deleted, so the user sees the impact first."""
    ensure_permission(db, user, company_id, "data.reset")
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    existing = set(sa_inspect(db.bind).get_table_names())
    counts: dict[str, int] = {}
    total = 0
    for table in DELETE_ORDER:
        if table not in existing or table in PRESERVED_TABLES:
            continue
        columns = {c["name"] for c in sa_inspect(db.bind).get_columns(table)}
        if "company_id" not in columns:
            continue
        found = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE company_id = :cid"), {"cid": company_id}
        ).scalar() or 0
        if found:
            counts[table] = int(found)
            total += int(found)

    return {
        "company_id": company_id,
        "company_name": company.name_ar,
        "confirmation_phrase": company.name_ar,
        "total_rows": total,
        "tables": counts,
        "preserved": sorted(PRESERVED_TABLES),
        "enabled": bool(getattr(settings, "allow_data_reset", False)),
        "note_ar": "سيُحذف كل ما في الجدول أدناه لهذه الشركة فقط. الإعدادات وشجرة الحسابات والمستخدمون تبقى كما هي.",
        "note_en": "Only the rows listed below are removed, and only for this company. Configuration, the chart of accounts and users are kept.",
    }


@router.post("/execute")
def execute_reset(data: ResetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete the trial data for one company after an explicit confirmation."""
    ensure_permission(db, user, data.company_id, "data.reset")
    if not getattr(settings, "allow_data_reset", False):
        raise HTTPException(
            403,
            "Data reset is disabled. Set ALLOW_DATA_RESET=true to enable it, then turn it off again.",
        )
    company = db.get(Company, data.company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    if data.confirmation.strip() != (company.name_ar or "").strip():
        raise HTTPException(
            422,
            {
                "message_ar": f"عبارة التأكيد غير مطابقة. اكتب اسم الشركة بالضبط: {company.name_ar}",
                "message_en": f"Confirmation does not match. Type the company name exactly: {company.name_ar}",
            },
        )

    existing = set(sa_inspect(db.bind).get_table_names())
    deleted: dict[str, int] = {}
    total = 0

    # Record the intent BEFORE deleting, so the audit trail survives the delete.
    write_audit(
        db,
        action="DATA_RESET_STARTED" if not data.dry_run else "DATA_RESET_PREVIEWED",
        entity_type="COMPANY",
        entity_id=data.company_id,
        user_id=user.id,
        company_id=data.company_id,
        before={"company": company.name_ar},
    )
    db.commit()

    for table in DELETE_ORDER:
        if table not in existing or table in PRESERVED_TABLES:
            continue
        columns = {c["name"] for c in sa_inspect(db.bind).get_columns(table)}
        if "company_id" not in columns:
            continue
        found = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE company_id = :cid"), {"cid": data.company_id}
        ).scalar() or 0
        if not found:
            continue
        if not data.dry_run:
            db.execute(text(f"DELETE FROM {table} WHERE company_id = :cid"), {"cid": data.company_id})
        deleted[table] = int(found)
        total += int(found)

    if not data.dry_run:
        db.commit()
        write_audit(
            db,
            action="DATA_RESET_COMPLETED",
            entity_type="COMPANY",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            after={"rows_deleted": total, "tables": len(deleted)},
        )
        db.commit()

    return {
        "dry_run": data.dry_run,
        "company_id": data.company_id,
        "company_name": company.name_ar,
        "tables_affected": len(deleted),
        "rows_deleted": total if not data.dry_run else 0,
        "rows_that_would_be_deleted": total if data.dry_run else 0,
        "detail": deleted,
        "message_ar": (
            f"تجربة فقط: سيُحذف {total} صفًا من {len(deleted)} جدولًا."
            if data.dry_run
            else f"تم حذف {total} صفًا من {len(deleted)} جدولًا. الإعدادات وشجرة الحسابات والمستخدمون لم تُمس."
        ),
        "message_en": (
            f"Dry run: {total} rows across {len(deleted)} tables would be removed."
            if data.dry_run
            else f"Removed {total} rows across {len(deleted)} tables. Configuration, chart of accounts and users are untouched."
        ),
    }
