"""UAT-only reset of transaction data and trial monetary balances.

The operator wants to keep the configured business foundation (customers,
suppliers, items, employees, warehouses, asset cards, etc.) and remove only the
trial activity before semi-real UAT entry.  This module therefore uses an
explicit closed classification.  A new or unmapped table blocks execution until
its treatment is reviewed; it is never guessed to be deletable.

Fixed assets need special handling because identity and valuation share one
row.  Their cards remain, but monetary values and transaction links are reset
and the card becomes ``DRAFT_UNVALUED`` until an opening value is entered.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, inspect as sa_inspect, or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import Base, get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Role, User, UserCompanyRole
from app.services.audit import write_audit

router = APIRouter(prefix="/uat-reset", tags=["UAT reset"])

CONFIRMATION_PHRASE = "حذف الحركات والقيم التجريبية فقط - جميع الشركات"
AUTHORIZATION_TTL_SECONDS = 10 * 60

# Explicit business foundation retained across the reset.  The list contains
# identities/configuration, not documents, postings, balances, runs or events.
PRESERVED_MASTER_TABLES = frozenset(
    {
        # Platform, access and accounting foundation.
        "companies",
        "branches",
        "cost_centers",
        "accounts",
        "fiscal_years",
        "fiscal_periods",
        "permissions",
        "roles",
        "role_permissions",
        "users",
        "user_company_roles",
        "user_company_role_branches",
        "password_history",
        "user_sessions",
        "audit_logs",
        "backup_records",
        "currencies",
        "tax_codes",
        "legal_rule_versions",
        "journal_sequences",
        "financial_statement_mappings",
        "corporate_finance_configs",
        "sod_rules",
        # External sales connection and mirrored master dimensions survive a
        # UAT value reset. Imported orders and sync runs are transactions.
        "dgtera_connections",
        "dgtera_branches",
        "dgtera_products",
        "dgtera_customers",
        # Parties, people, inventory and banking master data.
        "parties",
        "employees",
        "employee_contracts",
        "employee_shift_assignments",
        "shifts",
        "leave_types",
        "bank_accounts",
        "warehouses",
        "items",
        "item_uom_conversions",
        "supplier_item_planning",
        # Fixed-asset, fleet, maintenance, IT and legal identities.
        "asset_categories",
        "fixed_assets",
        "lease_contracts",
        "cip_projects",
        "cip_contracts",
        "fleet_drivers",
        "fleet_vehicles",
        "maintenance_assets",
        "maintenance_plans",
        "maintenance_spare_parts",
        "it_assets",
        "legal_cases",
        "legal_contracts",
        "legal_licenses",
        # Manufacturing, restaurant and gym configuration/master records.
        "bills_of_material",
        "bill_of_material_lines",
        "work_centers",
        "work_center_calendar_days",
        "manufacturing_routings",
        "manufacturing_routing_operations",
        "delivery_platforms",
        "menu_items",
        "kitchen_stations",
        "menu_kitchen_stations",
        "restaurant_tables",
        "members",
        "membership_plans",
        "gym_departments",
        "gym_department_plan_access",
        "gym_facilities",
        "gym_lockers",
        "gym_pt_packages",
        "gym_trainers",
        "gym_class_types",
        "gym_cafe_product_profiles",
        # Tax, quality, governance and finance reference configuration.
        "excise_products",
        "excise_tax_categories",
        "excise_warehouse_profiles",
        "withholding_tax_categories",
        "withholding_beneficiary_profiles",
        "zakat_taxpayer_profiles",
        "employee_benefit_assumptions",
        "commission_beneficiaries",
        "credit_risk_buckets",
        "credit_risk_portfolios",
        "consolidation_groups",
        "consolidation_members",
        "operating_segments",
        "recurring_journal_templates",
        "recurring_journal_lines",
        "governance_controls",
        "governance_risks",
        "controlled_documents",
        "quality_inspection_plans",
        "quality_objectives",
        "haccp_plans",
        "haccp_hazards",
        "payroll_policies",
    }
)

# Closed, reviewed classification of transaction/event/value tables in the
# current schema.  Any future table is UNKNOWN and blocks the reset.
TRANSACTION_TABLES = frozenset(
    {
        "access_review_campaigns", "access_review_items", "accrual_entries",
        "asset_depreciation", "asset_lifecycle_transactions", "attendance_records",
        "audit_engagements", "audit_findings", "background_jobs",
        "bank_statement_lines", "bank_statements", "budget_lines", "budgets",
        "business_combinations", "calibration_records", "cashier_shifts",
        "certificates_of_analysis", "cip_costs", "cip_payments",
        "cip_progress_certificates", "close_orchestration_checks",
        "close_orchestration_runs", "commission_accruals",
        "consolidated_trial_balance_lines", "consolidated_trial_balance_runs",
        "consolidation_adjustments", "consolidation_lines", "consolidation_runs",
        "consolidation_worksheet_lines", "consolidation_worksheets",
        "contingent_consideration_remeasurements", "corrective_actions",
        "cost_rollup_lines", "cost_rollup_snapshots", "credit_exposures",
        "credit_note_applications", "credit_note_lines", "credit_notes",
        "crm_leads", "crm_opportunities", "customer_quality_complaints",
        "deferred_tax_items", "deferred_tax_runs", "demo_data_records",
        "e_invoices", "earnings_per_share_runs", "ecl_run_lines", "ecl_runs",
        "employee_benefit_valuation_lines", "employee_benefit_valuations",
        "end_of_service_settlements", "exchange_rates", "excise_movements",
        "excise_tax_return_lines", "excise_tax_returns", "export_evidence",
        "financial_assurance_checks", "financial_assurance_runs",
        "financial_certifications", "financial_disclosure_notes",
        "financial_evidence", "financial_open_items", "financial_report_runs",
        "financial_settlement_allocations", "fleet_trips",
        "foreign_currency_balances", "foreign_operation_disposals",
        "foreign_operation_translation_runs", "fx_revaluation_runs",
        "goods_receipt_lines", "goods_receipts", "goodwill_impairment_tests",
        "gym_access_records", "gym_branch_transfers", "gym_class_bookings",
        "gym_class_sessions", "gym_department_access_records",
        "gym_facility_bookings", "gym_locker_assignments", "gym_member_ledger",
        "gym_membership_modifications", "gym_membership_states", "gym_pt_sales",
        "gym_pt_sessions", "gym_trainer_commission_batches",
        "gym_trainer_commission_lines", "haccp_monitoring_logs",
        "import_declaration_lines", "import_declarations",
        "inbound_shipment_lines", "inbound_shipments", "intercompany_matches",
        "intercompany_records", "internal_cost_runs", "internal_cost_variance_lines",
        "inventory_count_lines", "inventory_counts", "inventory_write_downs",
        "journal_entries", "journal_lines", "kitchen_ticket_lines",
        "kitchen_tickets", "landed_cost_allocations", "landed_cost_charges",
        "landed_cost_documents", "lead_schedule_items", "lead_schedules",
        "lease_modifications", "lease_partial_terminations", "lease_schedules",
        "lease_variable_payments", "leave_requests", "maintenance_work_order_parts",
        "maintenance_work_orders", "management_performance_measures",
        "marketing_campaigns", "membership_contracts", "mrp_capacity_allocations",
        "mrp_demand_lines", "mrp_plan_runs", "mrp_requirement_lines",
        "non_conformances", "offline_pos_transactions", "overtime_requests",
        "party_credit_balances", "payments", "payroll_adjustments", "payroll_lines",
        "payroll_runs", "period_close_checks", "period_close_runs",
        "planning_scenario_lines", "planning_scenarios",
        "platform_settlement_batches", "platform_settlement_lines",
        "pos_control_lines", "pos_control_requests", "pos_order_lines", "pos_orders",
        "dgtera_sales_payments", "dgtera_sales_order_lines",
        "dgtera_sales_orders", "dgtera_sync_runs",
        "prepaid_expense_schedules", "prepaid_expenses", "product_recall_lines",
        "product_recalls", "production_cost_closes", "production_operation_logs",
        "production_orders", "production_runs", "production_scrap_records",
        "purchase_invoice_lines", "purchase_invoices", "purchase_order_lines",
        "purchase_orders", "purchase_price_allocation_items", "quality_actions",
        "quality_inspections", "quality_management_reviews",
        "readiness_assessment_checks", "readiness_assessments", "receipts",
        "recurring_journal_runs", "restaurant_reservations",
        "restaurant_waste_records", "revenue_schedules",
        "sale_leaseback_transactions", "sales_invoice_lines", "sales_invoices",
        "segment_report_lines", "segment_report_runs", "service_tickets",
        "sod_conflicts", "stock_movements", "sublease_arrangements",
        "supplier_quality_evaluations", "tax_loss_carryforwards",
        "tax_loss_utilizations", "vat_return_lines", "vat_return_snapshots",
        "withholding_tax_return_lines", "withholding_tax_returns",
        "withholding_tax_transactions", "wps_batch_lines", "wps_batches",
        "year_end_close_checks", "year_end_close_runs",
        "zakat_income_tax_returns", "zakat_tax_adjustments",
    }
)

PARTIAL_TABLES = frozenset({"attachments"})

PRESERVED_ATTACHMENT_ENTITY_TYPES = frozenset(
    {"FIXED_ASSET", "LEGAL_CONTRACT", "EMPLOYEE", "CIP_PROJECT", "CIP_CONTRACT", "OTHER"}
)

# Preserved-to-transaction links explicitly nulled before journals are deleted.
RESETTABLE_MASTER_LINKS = frozenset(
    {
        ("fixed_assets", "acquisition_journal_id", "journal_entries"),
        ("lease_contracts", "initial_journal_id", "journal_entries"),
        ("cip_projects", "capitalization_journal_id", "journal_entries"),
    }
)


class UatResetIn(BaseModel):
    company_id: int
    confirmation: str = Field(min_length=1, max_length=300)
    backup_acknowledged: bool = False
    dry_run: bool = True
    authorization_token: str | None = Field(default=None, max_length=4000)


def _enabled() -> bool:
    return settings.environment.strip().lower() in {"uat", "testing"} and bool(
        settings.allow_data_reset
    )


def _ensure_enabled() -> None:
    environment = settings.environment.strip().lower()
    if environment not in {"uat", "testing"}:
        raise HTTPException(403, "Transaction reset is available only in UAT")
    if not settings.allow_data_reset:
        raise HTTPException(403, "Set ALLOW_DATA_RESET=true temporarily in UAT")


def _ensure_system_admin(db: Session, user: User, company_id: int) -> None:
    ensure_permission(db, user, company_id, "data.reset")
    membership = db.scalar(
        select(UserCompanyRole.id)
        .join(Role, Role.id == UserCompanyRole.role_id)
        .where(
            UserCompanyRole.user_id == user.id,
            UserCompanyRole.company_id == company_id,
            Role.code == "SUPER_ADMIN",
        )
    )
    if membership is None:
        raise HTTPException(403, "Only a System Administrator can reset UAT data")


def _classified_tables(db: Session | None = None) -> tuple[list[str], list[str]]:
    existing = set(Base.metadata.tables)
    classified = PRESERVED_MASTER_TABLES | TRANSACTION_TABLES | PARTIAL_TABLES
    unknown = existing - classified
    obsolete = classified - existing
    if unknown or obsolete:
        raise HTTPException(
            503,
            {
                "message": "UAT reset policy does not exactly match ORM schema",
                "unknown": sorted(unknown),
                "obsolete": sorted(obsolete),
            },
        )
    if db is not None:
        actual = set(sa_inspect(db.bind).get_table_names()) - {"alembic_version"}
        unmapped = actual - existing
        missing_runtime = existing - actual
        if unmapped or missing_runtime:
            raise HTTPException(
                503,
                {
                    "message": "UAT reset policy does not exactly match database schema",
                    "unmapped_database_tables": sorted(unmapped),
                    "missing_database_tables": sorted(missing_runtime),
                },
            )
    targets = set(TRANSACTION_TABLES)
    unsafe: list[str] = []
    for table_name in sorted(PRESERVED_MASTER_TABLES):
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            parent_name = foreign_key.column.table.name
            link = (table_name, foreign_key.parent.name, parent_name)
            if parent_name in targets and link not in RESETTABLE_MASTER_LINKS:
                unsafe.append(f"{table_name}.{foreign_key.parent.name}->{parent_name}")
            if link in RESETTABLE_MASTER_LINKS and not foreign_key.parent.nullable:
                unsafe.append(f"{table_name}.{foreign_key.parent.name} must be nullable")
    if unsafe:
        raise HTTPException(
            503,
            {"message": "Unsafe transaction-reset classification", "links": unsafe},
        )
    return sorted(targets), sorted(PRESERVED_MASTER_TABLES)


def _asset_needs_value_reset(table):
    zero = Decimal("0")
    return or_(
        table.c.cost != zero,
        table.c.residual_value != zero,
        table.c.accumulated_depreciation != zero,
        table.c.accumulated_impairment != zero,
        table.c.net_book_value != zero,
        table.c.status != "DRAFT_UNVALUED",
        table.c.acquisition_journal_id.is_not(None),
        table.c.bank_account_id.is_not(None),
        table.c.held_for_sale_date.is_not(None),
        table.c.disposal_date.is_not(None),
        table.c.disposal_reference.is_not(None),
    )


def _hybrid_reset_specs() -> dict[str, tuple[Any, dict[str, Any]]]:
    """Predicates and reset values for master rows that also hold live balances."""
    zero = Decimal("0")
    fixed_assets = Base.metadata.tables["fixed_assets"]
    leases = Base.metadata.tables["lease_contracts"]
    cip = Base.metadata.tables["cip_projects"]
    spares = Base.metadata.tables["maintenance_spare_parts"]
    calendar_days = Base.metadata.tables["work_center_calendar_days"]
    objectives = Base.metadata.tables["quality_objectives"]
    sequences = Base.metadata.tables["journal_sequences"]
    restaurant_tables = Base.metadata.tables["restaurant_tables"]
    lockers = Base.metadata.tables["gym_lockers"]
    facilities = Base.metadata.tables["gym_facilities"]
    vehicles = Base.metadata.tables["fleet_vehicles"]
    drivers = Base.metadata.tables["fleet_drivers"]
    return {
        "fixed_assets": (
            _asset_needs_value_reset(fixed_assets),
            {
                "cost": zero,
                "residual_value": zero,
                "accumulated_depreciation": zero,
                "accumulated_impairment": zero,
                "net_book_value": zero,
                "status": "DRAFT_UNVALUED",
                "acquisition_journal_id": None,
                "bank_account_id": None,
                "held_for_sale_date": None,
                "disposal_date": None,
                "disposal_reference": None,
            },
        ),
        "lease_contracts": (
            or_(
                leases.c.initial_liability != zero,
                leases.c.initial_rou_asset != zero,
                leases.c.initial_journal_id.is_not(None),
                leases.c.status != "DRAFT_UNVALUED",
            ),
            {
                "initial_liability": zero,
                "initial_rou_asset": zero,
                "initial_journal_id": None,
                "status": "DRAFT_UNVALUED",
            },
        ),
        "cip_projects": (
            or_(
                cip.c.capitalized_cost != zero,
                cip.c.expensed_cost != zero,
                cip.c.capitalization_journal_id.is_not(None),
                cip.c.fixed_asset_id.is_not(None),
                cip.c.ready_for_use_date.is_not(None),
                cip.c.status.in_(["IN_PROGRESS", "READY", "CAPITALIZED"]),
            ),
            {
                "capitalized_cost": zero,
                "expensed_cost": zero,
                "capitalization_journal_id": None,
                "fixed_asset_id": None,
                "ready_for_use_date": None,
                "status": "PLANNING",
            },
        ),
        "maintenance_spare_parts": (
            or_(spares.c.quantity_on_hand != zero, spares.c.average_cost != zero),
            {"quantity_on_hand": zero, "average_cost": zero},
        ),
        "work_center_calendar_days": (
            calendar_days.c.reserved_minutes != zero,
            {"reserved_minutes": zero},
        ),
        "quality_objectives": (
            objectives.c.current_value != zero,
            {"current_value": zero},
        ),
        "journal_sequences": (
            sequences.c.last_number != 0,
            {"last_number": 0},
        ),
        "restaurant_tables": (
            restaurant_tables.c.status.in_(["OCCUPIED", "RESERVED"]),
            {"status": "AVAILABLE"},
        ),
        "gym_lockers": (
            lockers.c.status == "ASSIGNED",
            {"status": "AVAILABLE"},
        ),
        "gym_facilities": (
            facilities.c.status == "RESERVED",
            {"status": "AVAILABLE"},
        ),
        "fleet_vehicles": (
            vehicles.c.status == "ON_TRIP",
            {"status": "AVAILABLE"},
        ),
        "fleet_drivers": (
            drivers.c.status == "ON_TRIP",
            {"status": "AVAILABLE"},
        ),
    }


def _table_snapshot(db: Session) -> dict[str, Any]:
    targets, protected = _classified_tables(db)
    counts: dict[str, int] = {}
    fingerprint: list[list[Any]] = []
    for table_name in targets:
        table = Base.metadata.tables[table_name]
        count = int(db.scalar(select(func.count()).select_from(table)) or 0)
        if count:
            counts[table_name] = count
        max_id: Any = None
        if "id" in table.c and count:
            max_id = db.scalar(select(func.max(table.c.id)))
        fingerprint.append([table_name, count, str(max_id) if max_id is not None else None])

    attachments = Base.metadata.tables["attachments"]
    attachment_filter = attachments.c.entity_type.not_in(
        PRESERVED_ATTACHMENT_ENTITY_TYPES
    )
    attachment_rows = int(
        db.scalar(select(func.count()).select_from(attachments).where(attachment_filter))
        or 0
    )
    attachment_max_id = db.scalar(
        select(func.max(attachments.c.id)).where(attachment_filter)
    )
    if attachment_rows:
        counts["attachments (transaction documents)"] = attachment_rows
    fingerprint.append(
        [
            "attachments (transaction documents)",
            attachment_rows,
            str(attachment_max_id) if attachment_max_id is not None else None,
        ]
    )

    value_records: dict[str, int] = {}
    for table_name, (predicate, _) in _hybrid_reset_specs().items():
        table = Base.metadata.tables[table_name]
        affected = int(
            db.scalar(select(func.count()).select_from(table).where(predicate)) or 0
        )
        if affected:
            value_records[table_name] = affected
        rows = db.execute(select(table).order_by(table.c.id)).all()
        fingerprint.append(
            [
                f"{table_name} (preserved values/state)",
                affected,
                [
                    [str(value) if value is not None else None for value in row]
                    for row in rows
                ],
            ]
        )

    digest = hashlib.sha256(
        json.dumps(fingerprint, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    transaction_rows = sum(counts.values())
    total_value_records = sum(value_records.values())
    return {
        "tables": counts,
        "transaction_rows": transaction_rows,
        "value_records": value_records,
        "assets_to_reset": value_records.get("fixed_assets", 0),
        "leases_to_reset": value_records.get("lease_contracts", 0),
        "total_value_records": total_value_records,
        "total_changes": transaction_rows + total_value_records,
        "target_table_count": len(targets) + 1,
        "protected": protected,
        "digest": digest,
    }


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _sign(payload: dict[str, Any]) -> str:
    body = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def _verify(token: str | None, *, user_id: int, company_id: int, digest: str) -> None:
    if not token or "." not in token:
        raise HTTPException(428, "Run the safe preview before deleting")
    try:
        body, supplied = token.split(".", 1)
        expected = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(supplied), expected):
            raise ValueError("signature")
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) < int(time.time()):
            raise HTTPException(428, "Preview authorization expired; run it again")
        if int(payload["uid"]) != user_id or int(payload["cid"]) != company_id:
            raise HTTPException(403, "Preview authorization belongs to another user or company")
        if not hmac.compare_digest(str(payload["digest"]), digest):
            raise HTTPException(409, "UAT data changed after preview; run it again")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(428, "Invalid preview authorization; run it again") from exc


def _reset_hybrid_values(db: Session) -> dict[str, int]:
    affected: dict[str, int] = {}
    for table_name, (predicate, values) in _hybrid_reset_specs().items():
        table = Base.metadata.tables[table_name]
        result = db.execute(update(table).where(predicate).values(**values))
        if result.rowcount:
            affected[table_name] = int(result.rowcount)
    return affected


def _delete_transaction_rows(db: Session, targets: list[str]) -> None:
    if db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("PRAGMA defer_foreign_keys = ON")

    attachments = Base.metadata.tables["attachments"]
    db.execute(
        delete(attachments).where(
            attachments.c.entity_type.not_in(PRESERVED_ATTACHMENT_ENTITY_TYPES)
        )
    )

    target_set = set(targets)
    ordered = [
        table.name
        for table in reversed(Base.metadata.sorted_tables)
        if table.name in target_set
    ]
    for table_name in ordered:
        db.execute(delete(Base.metadata.tables[table_name]))


def _acquire_reset_lock(db: Session) -> None:
    """Serialize destructive UAT resets on PostgreSQL."""
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(274093)"))


@router.get("/preview")
def preview_uat_reset(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_system_admin(db, user, company_id)
    snapshot = _table_snapshot(db)
    return {
        "scope": "ALL_COMPANIES_TRANSACTIONS_AND_TRIAL_VALUES",
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "enabled": _enabled(),
        "production_blocked": settings.environment.strip().lower() not in {"uat", "testing"},
        "transaction_rows": snapshot["transaction_rows"],
        "assets_to_reset": snapshot["assets_to_reset"],
        "leases_to_reset": snapshot["leases_to_reset"],
        "value_records": snapshot["value_records"],
        "total_value_records": snapshot["total_value_records"],
        "total_changes": snapshot["total_changes"],
        "target_table_count": snapshot["target_table_count"],
        "tables": snapshot["tables"],
        "protected": snapshot["protected"],
        "preserved_attachment_types": sorted(PRESERVED_ATTACHMENT_ENTITY_TYPES),
        "note_ar": (
            "سيتم حذف الحركات والأرصدة التجريبية في جميع الشركات. تبقى بطاقات العملاء "
            "والموردين والأصناف والموظفين والمستودعات والبنوك والسيارات والآلات. "
            "تُصفّر قيم الأصول الثابتة وتصبح غير مقيّمة حتى إدخال قيمتها الافتتاحية."
        ),
        "note_en": (
            "Transactions and trial balances across all companies will be removed. "
            "Master records remain; fixed-asset cards become unvalued until opening values are entered."
        ),
    }


@router.post("/execute")
def execute_uat_reset(
    data: UatResetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_system_admin(db, user, data.company_id)
    _ensure_enabled()
    if data.confirmation != CONFIRMATION_PHRASE:
        raise HTTPException(422, {"message_ar": f"اكتب العبارة حرفيًا: {CONFIRMATION_PHRASE}"})
    if not data.backup_acknowledged:
        raise HTTPException(422, {"message_ar": "يجب تأكيد أخذ نسخة احتياطية أو قبول عدم إمكانية الاسترجاع."})

    if not data.dry_run:
        _acquire_reset_lock(db)
    snapshot = _table_snapshot(db)
    if data.dry_run:
        now = int(time.time())
        token = _sign(
            {
                "uid": user.id,
                "cid": data.company_id,
                "digest": snapshot["digest"],
                "iat": now,
                "exp": now + AUTHORIZATION_TTL_SECONDS,
            }
        )
        write_audit(
            db,
            action="UAT_TRANSACTION_VALUES_RESET_DRY_RUN",
            entity_type="SYSTEM",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            after={
                "transaction_rows": snapshot["transaction_rows"],
                "assets_to_reset": snapshot["assets_to_reset"],
                "leases_to_reset": snapshot["leases_to_reset"],
                "value_records": snapshot["value_records"],
                "digest": snapshot["digest"],
            },
        )
        db.commit()
        return {
            "dry_run": True,
            "rows_that_would_be_deleted": snapshot["transaction_rows"],
            "assets_that_would_be_unvalued": snapshot["assets_to_reset"],
            "leases_that_would_be_unvalued": snapshot["leases_to_reset"],
            "value_records_that_would_be_reset": snapshot["value_records"],
            "tables_affected": len(snapshot["tables"]),
            "authorization_token": token,
            "authorization_expires_in_seconds": AUTHORIZATION_TTL_SECONDS,
            "message_ar": (
                f"المعاينة ناجحة: سيُحذف {snapshot['transaction_rows']} صف حركة، "
                f"وستُعاد {snapshot['total_value_records']} بطاقة/قيمة تشغيلية إلى حالتها الافتتاحية، "
                f"منها {snapshot['assets_to_reset']} أصل ثابت مع بقاء بطاقاته."
            ),
            "message_en": (
                f"Preview passed: {snapshot['transaction_rows']} transaction rows will be removed and "
                f"{snapshot['total_value_records']} preserved value/state records will be reset."
            ),
        }

    _verify(
        data.authorization_token,
        user_id=user.id,
        company_id=data.company_id,
        digest=snapshot["digest"],
    )
    if snapshot["total_changes"] == 0:
        return {
            "dry_run": False,
            "rows_deleted": 0,
            "assets_unvalued": 0,
            "tables_affected": 0,
            "message_ar": "لا توجد حركات أو قيم تجريبية؛ التأسيس محفوظ والنظام جاهز.",
            "message_en": "No trial transactions or values remain; master data is ready.",
        }

    targets, _ = _classified_tables(db)
    try:
        write_audit(
            db,
            action="UAT_TRANSACTION_VALUES_RESET_STARTED",
            entity_type="SYSTEM",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            before={
                "transaction_rows": snapshot["transaction_rows"],
                "assets_to_reset": snapshot["assets_to_reset"],
                "value_records": snapshot["value_records"],
                "digest": snapshot["digest"],
            },
        )
        db.flush()
        value_records_reset = _reset_hybrid_values(db)
        _delete_transaction_rows(db, targets)
        write_audit(
            db,
            action="UAT_TRANSACTION_VALUES_RESET_COMPLETED",
            entity_type="SYSTEM",
            entity_id=data.company_id,
            user_id=user.id,
            company_id=data.company_id,
            after={
                "rows_deleted": snapshot["transaction_rows"],
                "value_records_reset": value_records_reset,
                "master_tables_preserved": len(PRESERVED_MASTER_TABLES),
            },
        )
        db.commit()
    except (SQLAlchemyError, RuntimeError) as exc:
        db.rollback()
        raise HTTPException(
            409, "UAT transaction reset failed atomically; no partial deletion was committed"
        ) from exc

    remaining = _table_snapshot(db)
    if remaining["total_changes"]:
        raise HTTPException(500, "Post-reset verification failed")
    return {
        "dry_run": False,
        "rows_deleted": snapshot["transaction_rows"],
        "assets_unvalued": snapshot["assets_to_reset"],
        "leases_unvalued": snapshot["leases_to_reset"],
        "value_records_reset": snapshot["value_records"],
        "tables_affected": len(snapshot["tables"]),
        "message_ar": (
            "تم حذف الحركات والقيم التجريبية فقط. بقيت جميع بيانات التأسيس وبطاقات "
            "السيارات والآلات، وقيم الأصول الآن صفر لحين إدخال القيم الافتتاحية."
        ),
        "message_en": (
            "Trial transactions and values were removed. Master data and fixed-asset cards remain."
        ),
    }
