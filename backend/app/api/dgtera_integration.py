from __future__ import annotations

import calendar
import json
import re
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now, utc_now_aware
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Branch,
    Company,
    DgteraBranch,
    DgteraConnection,
    DgteraCustomer,
    DgteraProduct,
    DgteraSalesOrder,
    DgteraSalesOrderLine,
    DgteraSyncRun,
    User,
)
from app.services.audit import write_audit
from app.services.dgtera_connector import DgteraRemoteError, money, validate_dgtera_url
from app.services import dgtera_sales_sync


router = APIRouter(prefix="/integrations/dgtera", tags=["DGTERA Sales Mirror"])


class ConnectionIn(BaseModel):
    company_id: int
    name: str = Field(default="DGTERA", min_length=1, max_length=120)
    base_url: str = Field(min_length=8, max_length=500)
    database_name: str | None = Field(default=None, min_length=1, max_length=150)
    login: str | None = Field(default=None, min_length=1, max_length=250)
    api_key: str | None = Field(default=None, min_length=8, max_length=500)
    active: bool = True
    timezone: str = Field(default="Asia/Riyadh", max_length=80)

    @model_validator(mode="after")
    def validate_connection(self):
        self.base_url = validate_dgtera_url(self.base_url)
        self.timezone = self.timezone.strip()
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return self


_LINKED_DGTERA_COMPANY_TYPES = {
    "HOLDING": "RESTAURANT",
    "RESTAURANT": "HOLDING",
}


def _connection_scope(
    db: Session,
    company_id: int,
    *,
    required: bool = True,
) -> tuple[DgteraConnection | None, bool]:
    """Resolve one shared restaurant-sales connection without copying orders.

    CORVAX stores the encrypted credential once.  The holding and restaurant
    workspaces can then read the same connection-scoped mirror, so the same
    DGTERA order can never be counted twice merely because the user changed
    company context.
    """
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    row = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == company_id))
    if row is None:
        linked_type = _LINKED_DGTERA_COMPANY_TYPES.get(str(company.company_type or "").upper())
        if linked_type:
            row = db.scalar(
                select(DgteraConnection)
                .join(Company, Company.id == DgteraConnection.company_id)
                .where(
                    Company.company_type == linked_type,
                    Company.active.is_(True),
                )
                .order_by(Company.id, DgteraConnection.id)
            )
    if row is None and required:
        raise HTTPException(404, "DGTERA connection is not configured")
    return row, bool(row and row.company_id != company_id)


def _connection(db: Session, company_id: int) -> DgteraConnection:
    row, _ = _connection_scope(db, company_id)
    assert row is not None
    return row


def _connection_out(row: DgteraConnection | None, company_id: int) -> dict:
    if not row:
        return {
            "company_id": company_id,
            "configured": False,
            "connected": False,
            "mode": "SALES_ONLY",
            "day_window": "00:00-23:59:59 Asia/Riyadh",
            "sync_interval_minutes": 2,
            "inherited": False,
        }
    return {
        "id": row.id,
        "company_id": company_id,
        "connection_company_id": row.company_id,
        "inherited": row.company_id != company_id,
        "configured": True,
        # A completed credential test defines connectivity.  A later history
        # slice warning must not incorrectly label the live connection offline.
        "connected": bool(row.last_tested_at),
        "sync_healthy": bool(row.last_sync_at and not row.last_error),
        "name": row.name,
        "base_url": row.base_url,
        "credentials_configured": bool(row.database_name and row.login and row.api_key),
        "active": row.active,
        "mode": "SALES_ONLY",
        "day_window": f"00:00-23:59:59 {row.timezone}",
        "sync_interval_minutes": 2,
        "timezone": row.timezone,
        "last_tested_at": row.last_tested_at,
        "last_sync_at": row.last_sync_at,
        "last_error": row.last_error,
    }


@router.get("/status")
def status(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    row, _ = _connection_scope(db, company_id, required=False)
    payload = _connection_out(row, company_id)
    if row:
        payload["history"] = dgtera_sales_sync.historical_backfill_status(db, row)
    return payload


@router.put("/connection")
def save_connection(data: ConnectionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Save, test and start the first import as one automatic setup action."""
    ensure_permission(db, user, data.company_id, "pos.manage")
    row = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == data.company_id))
    if row is None:
        if not data.api_key or not data.database_name or not data.login:
            raise HTTPException(422, "Database, login and API key are required for the first setup")
        row = DgteraConnection(company_id=data.company_id, created_by=user.id)
        db.add(row)
    before = _connection_out(row, data.company_id) if row.id else None
    row.name = data.name.strip()
    row.base_url = validate_dgtera_url(data.base_url)
    if data.database_name:
        row.database_name = data.database_name.strip()
    if data.login:
        row.login = data.login.strip()
    if data.api_key:
        row.api_key = data.api_key.strip()
    row.active = data.active
    row.import_mode = "SALES_ONLY"
    row.sync_interval_minutes = 2
    row.timezone = data.timezone
    row.last_tested_at = None
    row.last_error = None
    db.flush()
    try:
        test_result = dgtera_sales_sync.client_for(row).test_connection()
    except (DgteraRemoteError, ValueError) as exc:
        row.last_error = str(exc)
        write_audit(
            db,
            action="DGTERA_CONNECTION_TEST_FAILED",
            entity_type="DGTERA_CONNECTION",
            entity_id=row.id,
            user_id=user.id,
            company_id=data.company_id,
            after={"base_url": row.base_url, "credentials": "REDACTED", "error": str(exc)},
        )
        db.commit()
        raise HTTPException(502, f"Connection saved but automatic verification failed: {exc}") from exc
    row.last_tested_at = utc_now()
    write_audit(
        db,
        action="DGTERA_CONNECTION_ACTIVATED",
        entity_type="DGTERA_CONNECTION",
        entity_id=row.id,
        user_id=user.id,
        company_id=data.company_id,
        before=before,
        after={
            "base_url": row.base_url,
            "active": row.active,
            "mode": "SALES_ONLY",
            "day_window": f"00:00-23:59:59 {row.timezone}",
            "sync_interval_minutes": 2,
            "credentials": "REDACTED",
            "automatic_test": test_result,
        },
    )
    db.commit()
    if not row.active:
        return {**_connection_out(row, data.company_id), "automatic_test": test_result}
    start_date, end_date = dgtera_sales_sync.catchup_window(row)
    try:
        initial_sync = dgtera_sales_sync.sync_connection(db, row, start_date, end_date, user.id)
    except dgtera_sales_sync.DgteraSyncBusy:
        initial_sync = {"queued": True}
    except (DgteraRemoteError, ValueError, dgtera_sales_sync.DgteraReconciliationError) as exc:
        raise HTTPException(502, f"Connection verified but the automatic sales import failed: {exc}") from exc
    return {
        **_connection_out(row, data.company_id),
        "automatic_test": test_result,
        "initial_sync": initial_sync,
    }


def _date_window(row: DgteraConnection, start_date: date | None, end_date: date | None) -> tuple[date, date]:
    today = utc_now_aware().astimezone(ZoneInfo(row.timezone)).date()
    start = start_date or today
    end = end_date or start
    if end < start:
        raise HTTPException(422, "end_date must not be before start_date")
    if (end - start).days > 731:
        raise HTTPException(422, "The displayed sales window cannot exceed two years")
    return start, end


def _range_coverage(db: Session, connection: DgteraConnection, start: date, end: date) -> dict:
    """Tell the UI whether a local aggregate is complete, not merely non-zero."""
    history = dgtera_sales_sync.historical_backfill_status(db, connection)
    target_end = history["target_end_date"]
    proof = dgtera_sales_sync.strict_range_coverage_status(db, connection, start, end)
    future_period = start > target_end
    return {
        "complete": bool(proof["complete"] and not future_period),
        "requested_start_date": start,
        "requested_end_date": end,
        "earliest_imported_date": history["earliest_imported_date"],
        "target_end_date": target_end,
        "progress_percent": history["progress_percent"],
        "first_missing_date": proof["first_missing_date"],
        "covered_days": proof["covered_days"],
        "required_days": proof["required_days"],
        "oldest_verified_at": proof.get("oldest_verified_at"),
        "last_verified_at": proof.get("last_verified_at"),
        "strict_reconciliation": True,
        "future_period": future_period,
    }


def _order_conditions(
    connection_id: int,
    start: date,
    end: date,
    *,
    branch_id: int | None = None,
    sales_scope: str | None = None,
    service_mode: str | None = None,
) -> list:
    conditions = [
        DgteraSalesOrder.connection_id == connection_id,
        DgteraSalesOrder.sales_date >= start,
        DgteraSalesOrder.sales_date <= end,
    ]
    if branch_id is not None:
        conditions.append(DgteraSalesOrder.branch_id == branch_id)
    if sales_scope:
        conditions.append(DgteraSalesOrder.sales_scope == sales_scope)
    if service_mode:
        conditions.append(DgteraSalesOrder.service_mode == service_mode)
    return conditions


def _order_metrics(db: Session, conditions: list) -> dict:
    row = db.execute(select(
        func.count(DgteraSalesOrder.id),
        func.coalesce(func.sum(DgteraSalesOrder.subtotal), 0),
        func.coalesce(func.sum(DgteraSalesOrder.vat_amount), 0),
        func.coalesce(func.sum(DgteraSalesOrder.total), 0),
        func.coalesce(func.sum(case(
            (DgteraSalesOrder.total < 0, -DgteraSalesOrder.total),
            else_=0,
        )), 0),
    ).where(*conditions)).one()
    quantity_total = db.scalar(select(func.coalesce(func.sum(DgteraSalesOrderLine.quantity), 0)).join(
        DgteraSalesOrder,
        DgteraSalesOrder.id == DgteraSalesOrderLine.order_id,
    ).where(*conditions)) or Decimal("0")
    return {
        "orders": int(row[0] or 0),
        "quantity": quantity_decimal(quantity_total),
        "subtotal": money(row[1]),
        "vat": money(row[2]),
        "sales": money(row[3]),
        "refunds": money(row[4]),
    }


def _grouped_orders(db: Session, column, conditions: list) -> list[tuple]:
    return list(db.execute(select(
        column,
        func.count(DgteraSalesOrder.id),
        func.coalesce(func.sum(DgteraSalesOrder.subtotal), 0),
        func.coalesce(func.sum(DgteraSalesOrder.vat_amount), 0),
        func.coalesce(func.sum(DgteraSalesOrder.total), 0),
    ).where(*conditions).group_by(column)).all())


def _summary_from_group(rows: list[tuple], labels: dict | None = None, empty_label: str = "—") -> list[dict]:
    result = []
    for key, order_count, subtotal, vat, sales in rows:
        shown = labels.get(key, f"Branch #{key}") if labels is not None else (key or empty_label)
        result.append({
            "key": shown,
            "orders": int(order_count or 0),
            "subtotal": money(subtotal),
            "vat": money(vat),
            "sales": money(sales),
        })
    return sorted(result, key=lambda item: (money(item["sales"]), str(item["key"])), reverse=True)


_CASH_PAYMENT_TOKENS = ("cash", "نقد")
_CARD_PAYMENT_TOKENS = (
    "card", "mada", "visa", "mastercard", "bank", "credit", "debit", "pos",
    "مدى", "شبكة", "بطاقة",
)


def _payment_channel_name(method_name: str) -> str:
    normalized = re.sub(r"[^\w\u0600-\u06ff]+", " ", (method_name or "").casefold()).strip()
    if any(token in normalized for token in _CASH_PAYMENT_TOKENS):
        return "CASH"
    if any(token in normalized for token in _CARD_PAYMENT_TOKENS):
        return "CARD"
    return "OTHER"


def _payment_channel_summary(db: Session, conditions: list) -> list[dict]:
    """Classify collections without changing the DGTERA source totals.

    Delivery-app orders are receivables (on-account).  Restaurant payments
    are split between cash/card using the source payment lines; split tenders
    receive a proportional share of net and VAT.
    """
    orders = db.scalars(
        select(DgteraSalesOrder)
        .where(*conditions)
        .options(selectinload(DgteraSalesOrder.payments))
    ).all()
    buckets: dict[str, dict] = {}

    def add(key: str, order: DgteraSalesOrder, ratio: Decimal) -> None:
        row = buckets.setdefault(key, {
            "key": key, "orders": set(), "subtotal": Decimal("0"),
            "vat": Decimal("0"), "sales": Decimal("0"),
        })
        row["orders"].add(order.id)
        row["subtotal"] += Decimal(str(order.subtotal or 0)) * ratio
        row["vat"] += Decimal(str(order.vat_amount or 0)) * ratio
        row["sales"] += Decimal(str(order.total or 0)) * ratio

    for order in orders:
        if order.sales_scope == "EXTERNAL" or order.service_mode == "DELIVERY":
            add("PLATFORM_CREDIT", order, Decimal("1"))
            continue
        valid = [payment for payment in order.payments if Decimal(str(payment.amount or 0)) != 0]
        paid = sum((abs(Decimal(str(payment.amount or 0))) for payment in valid), Decimal("0"))
        if not valid or paid == 0:
            add("UNCLASSIFIED", order, Decimal("1"))
            continue
        for payment in valid:
            ratio = abs(Decimal(str(payment.amount or 0))) / paid
            add(_payment_channel_name(payment.method_name), order, ratio)
    result = [{
        "key": key,
        "orders": len(row["orders"]),
        "subtotal": money(row["subtotal"]),
        "vat": money(row["vat"]),
        "sales": money(row["sales"]),
    } for key, row in buckets.items()]
    return sorted(result, key=lambda item: (money(item["sales"]), item["key"]), reverse=True)


@router.get("/snapshot")
def snapshot(
    company_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    branch_id: int | None = None,
    sales_scope: str | None = Query(default=None, pattern="^(INTERNAL|EXTERNAL)$"),
    service_mode: str | None = Query(default=None, pattern="^(DINE_IN|TAKEAWAY|DELIVERY)$"),
    limit: int = Query(default=500, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "pos.read")
    connection = _connection(db, company_id)
    start, end = _date_window(connection, start_date, end_date)
    conditions = _order_conditions(
        connection.id,
        start,
        end,
        branch_id=branch_id,
        sales_scope=sales_scope,
        service_mode=service_mode,
    )
    orders = db.scalars(
        select(DgteraSalesOrder)
        .where(*conditions)
        .options(
            selectinload(DgteraSalesOrder.lines),
            selectinload(DgteraSalesOrder.payments),
        )
        .order_by(DgteraSalesOrder.ordered_at_local.desc(), DgteraSalesOrder.id.desc())
        .limit(limit)
    ).all()

    branches = db.scalars(select(DgteraBranch).where(
        DgteraBranch.connection_id == connection.id,
        DgteraBranch.active.is_(True),
    ).order_by(DgteraBranch.name)).all()
    branch_name = {row.branch_id: row.name for row in branches}
    customers = db.scalars(select(DgteraCustomer).where(DgteraCustomer.connection_id == connection.id)).all()
    customer_by_id = {row.id: row for row in customers}
    product_groups = list(db.execute(select(
        DgteraSalesOrderLine.product_id,
        func.coalesce(func.sum(DgteraSalesOrderLine.quantity), 0),
        func.coalesce(func.sum(DgteraSalesOrderLine.subtotal), 0),
        func.coalesce(func.sum(DgteraSalesOrderLine.vat_amount), 0),
        func.coalesce(func.sum(DgteraSalesOrderLine.total), 0),
    ).join(
        DgteraSalesOrder,
        DgteraSalesOrder.id == DgteraSalesOrderLine.order_id,
    ).where(*conditions).group_by(DgteraSalesOrderLine.product_id)).all())
    product_ids = {int(row[0]) for row in product_groups}
    product_ids.update(line.product_id for order in orders for line in order.lines)
    products = db.scalars(select(DgteraProduct).where(DgteraProduct.id.in_(product_ids))).all() if product_ids else []
    product_by_id = {row.id: row for row in products}

    totals = _order_metrics(db, conditions)
    scope_groups = _grouped_orders(db, DgteraSalesOrder.sales_scope, conditions)
    scope_sales = _summary_from_group(scope_groups)
    scope_totals = {row["key"]: row["sales"] for row in scope_sales}
    totals["internal_sales"] = money(scope_totals.get("INTERNAL", 0))
    totals["external_sales"] = money(scope_totals.get("EXTERNAL", 0))
    branch_sales = []
    for current_branch_id, branch_metrics in _branch_metric_map(db, conditions).items():
        branch_sales.append({
            "key": branch_name.get(current_branch_id, f"Branch #{current_branch_id}"),
            **branch_metrics,
        })
    branch_sales.sort(key=lambda item: (money(item["sales"]), str(item["key"])), reverse=True)
    service_sales = _summary_from_group(_grouped_orders(db, DgteraSalesOrder.service_mode, conditions))
    platform_sales = _summary_from_group(
        _grouped_orders(db, DgteraSalesOrder.delivery_platform_name, conditions),
        empty_label="No delivery platform",
    )
    customer_sales = _summary_from_group(
        _grouped_orders(db, DgteraSalesOrder.customer_id, conditions),
        {row.id: row.name for row in customers} | {None: "Walk-in / no DGTERA customer"},
    )
    product_sales = []
    for product_id, qty, subtotal, vat, sales in product_groups:
        product = product_by_id.get(product_id)
        product_sales.append({
            "key": product.name if product else f"Product #{product_id}",
            "code": product.code if product else "",
            "quantity": quantity_decimal(qty),
            "subtotal": money(subtotal),
            "vat": money(vat),
            "sales": money(sales),
        })
    product_sales.sort(key=lambda row: (money(row["sales"]), row["key"]), reverse=True)

    payment_channels = _payment_channel_summary(db, conditions)
    strict_evidence = dgtera_sales_sync.strict_range_reconciliation_evidence(
        db, connection, start, end
    )
    reconciliation = {
        "available": bool(strict_evidence["verified_from_live_source"]),
        "strict": True,
        "matched": strict_evidence["matched"],
        "source_orders": strict_evidence["source"]["orders"],
        "imported_orders": strict_evidence["corvax"]["orders"],
        "source_lines": strict_evidence["source"]["lines"],
        "imported_lines": strict_evidence["corvax"]["lines"],
        "source_payments": strict_evidence["source"]["payments"],
        "imported_payments": strict_evidence["corvax"]["payments"],
        "source_quantity": strict_evidence["source"]["quantity"],
        "imported_quantity": strict_evidence["corvax"]["quantity"],
        "source_subtotal": strict_evidence["source"]["subtotal"],
        "imported_subtotal": strict_evidence["corvax"]["subtotal"],
        "source_vat": strict_evidence["source"]["vat"],
        "imported_vat": strict_evidence["corvax"]["vat"],
        "source_total": strict_evidence["source"]["gross"],
        "imported_total": strict_evidence["corvax"]["gross"],
        "difference": strict_evidence["difference"],
        "checks": strict_evidence["checks"],
        "mismatch_count": strict_evidence["mismatch_count"],
        "mismatches": strict_evidence["mismatches"],
        "verification_hash": strict_evidence["verification_hash"],
        "oldest_verified_at": strict_evidence["oldest_verified_at"],
        "last_verified_at": strict_evidence["last_verified_at"],
        "days_verified": strict_evidence["days_verified"],
        "orders_verified_individually": strict_evidence["orders_verified_individually"],
    }

    order_rows = []
    for order in orders:
        customer = customer_by_id.get(order.customer_id)
        order_rows.append({
            "id": order.id,
            "external_order_id": order.external_order_id,
            "order_name": order.external_order_name,
            "pos_reference": order.pos_reference,
            "ordered_at": order.ordered_at_local,
            "sales_date": order.sales_date,
            "branch": branch_name.get(order.branch_id, f"Branch #{order.branch_id}"),
            "customer": customer.name if customer else None,
            "sales_scope": order.sales_scope,
            "service_mode": order.service_mode,
            "classification_source": order.classification_source,
            "platform": order.delivery_platform_name,
            "state": order.state,
            "subtotal": order.subtotal,
            "vat": order.vat_amount,
            "total": order.total,
            "amount_paid": order.amount_paid,
            "amount_return": order.amount_return,
            "discount": order.discount_amount,
            "line_total_difference": order.line_total_difference,
            "lines": [{
                "external_line_id": line.external_line_id,
                "product": product_by_id.get(line.product_id).name if product_by_id.get(line.product_id) else line.product_name,
                "code": product_by_id.get(line.product_id).code if product_by_id.get(line.product_id) else "",
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_percent": line.discount_percent,
                "subtotal": line.subtotal,
                "vat": line.vat_amount,
                "total": line.total,
            } for line in order.lines],
            "payments": [{
                "method": payment.method_name,
                "amount": payment.amount,
            } for payment in order.payments],
        })

    return {
        "mode": "SALES_ONLY",
        "window": {"start_date": start, "end_date": end, "day_start": "00:00", "day_end": "23:59:59", "timezone": connection.timezone},
        "filters": {"branch_id": branch_id, "sales_scope": sales_scope, "service_mode": service_mode, "limit": limit},
        "coverage": _range_coverage(db, connection, start, end),
        "totals": totals,
        "master_counts": {
            "branches": len(branches),
            "products": db.scalar(select(func.count(DgteraProduct.id)).where(
                DgteraProduct.connection_id == connection.id,
                DgteraProduct.active.is_(True),
            )) or 0,
            "customers": db.scalar(select(func.count(DgteraCustomer.id)).where(
                DgteraCustomer.connection_id == connection.id,
                DgteraCustomer.active.is_(True),
            )) or 0,
        },
        "branches": [{"branch_id": row.branch_id, "external_id": row.external_config_id, "code": row.code, "name": row.name} for row in branches],
        "branch_sales": branch_sales,
        "scope_sales": scope_sales,
        "service_sales": service_sales,
        "platform_sales": [row for row in platform_sales if row["key"] != "No delivery platform"],
        "payment_channels": payment_channels,
        "reconciliation": reconciliation,
        "customer_sales": customer_sales,
        "product_sales": product_sales,
        "orders": order_rows,
    }


def quantity_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _shift_month(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _shift_year(value: date, years: int) -> date:
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return date(year, value.month, day)


def _comparison_windows(as_of: date, period: str) -> dict[str, tuple[date, date]]:
    if period == "DAY":
        current = (as_of, as_of)
        previous = (as_of - timedelta(days=1), as_of - timedelta(days=1))
        next_period = (as_of + timedelta(days=1), as_of + timedelta(days=1))
        prior_year = (_shift_year(as_of, -1), _shift_year(as_of, -1))
    elif period == "WEEK":
        current = (as_of - timedelta(days=as_of.weekday()), as_of)
        previous = (current[0] - timedelta(days=7), current[1] - timedelta(days=7))
        next_period = (current[0] + timedelta(days=7), current[1] + timedelta(days=7))
        prior_year = (current[0] - timedelta(days=364), current[1] - timedelta(days=364))
    elif period == "MONTH":
        current = (as_of.replace(day=1), as_of)
        previous_end = _shift_month(as_of, -1)
        previous = (previous_end.replace(day=1), previous_end)
        next_end = _shift_month(as_of, 1)
        next_period = (next_end.replace(day=1), next_end)
        prior_year = (_shift_year(current[0], -1), _shift_year(current[1], -1))
    else:
        current = (as_of.replace(month=1, day=1), as_of)
        previous = (_shift_year(current[0], -1), _shift_year(current[1], -1))
        next_period = (_shift_year(current[0], 1), _shift_year(current[1], 1))
        prior_year = previous
    return {"current": current, "previous": previous, "next": next_period, "prior_year": prior_year}


def _change_percent(current: object, reference: object) -> Decimal | None:
    current_value, reference_value = money(current), money(reference)
    if reference_value == 0:
        return None
    return (current_value - reference_value) * Decimal("100") / abs(reference_value)


def _branch_metric_map(db: Session, conditions: list) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for branch_id, orders, subtotal, vat, sales in _grouped_orders(db, DgteraSalesOrder.branch_id, conditions):
        result[int(branch_id)] = {
            "orders": int(orders or 0),
            "subtotal": money(subtotal),
            "vat": money(vat),
            "sales": money(sales),
            "quantity": Decimal("0"),
        }
    qty_rows = db.execute(select(
        DgteraSalesOrder.branch_id,
        func.coalesce(func.sum(DgteraSalesOrderLine.quantity), 0),
    ).join(
        DgteraSalesOrder,
        DgteraSalesOrder.id == DgteraSalesOrderLine.order_id,
    ).where(*conditions).group_by(DgteraSalesOrder.branch_id)).all()
    for branch_id, qty in qty_rows:
        if int(branch_id) in result:
            result[int(branch_id)]["quantity"] = quantity_decimal(qty)
    return result


@router.get("/analytics")
def analytics(
    company_id: int,
    as_of_date: date | None = None,
    period: str = Query(default="DAY", pattern="^(DAY|WEEK|MONTH|YEAR)$"),
    branch_id: int | None = None,
    sales_scope: str | None = Query(default=None, pattern="^(INTERNAL|EXTERNAL)$"),
    service_mode: str | None = Query(default=None, pattern="^(DINE_IN|TAKEAWAY|DELIVERY)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Matched daily, WTD, MTD and YTD sales comparisons."""
    ensure_permission(db, user, company_id, "pos.read")
    connection = _connection(db, company_id)
    today = utc_now_aware().astimezone(ZoneInfo(connection.timezone)).date()
    as_of = as_of_date or today
    windows = _comparison_windows(as_of, period)

    def conditions_for(window: tuple[date, date]) -> list:
        return _order_conditions(
            connection.id,
            window[0],
            window[1],
            branch_id=branch_id,
            sales_scope=sales_scope,
            service_mode=service_mode,
        )

    metrics = {key: _order_metrics(db, conditions_for(window)) for key, window in windows.items()}
    current, previous, next_period, prior_year = (
        metrics["current"], metrics["previous"], metrics["next"], metrics["prior_year"]
    )

    branches = db.scalars(select(DgteraBranch).where(
        DgteraBranch.connection_id == connection.id,
        DgteraBranch.active.is_(True),
    )).all()
    branch_names = {row.branch_id: row.name for row in branches}
    branch_maps = {key: _branch_metric_map(db, conditions_for(window)) for key, window in windows.items()}
    branch_ids = set().union(*(mapping.keys() for mapping in branch_maps.values()))
    branch_comparison = []
    for current_branch_id in branch_ids:
        current_row = branch_maps["current"].get(current_branch_id, {})
        previous_row = branch_maps["previous"].get(current_branch_id, {})
        next_row = branch_maps["next"].get(current_branch_id, {})
        prior_row = branch_maps["prior_year"].get(current_branch_id, {})
        current_sales = money(current_row.get("subtotal", 0))
        previous_sales = money(previous_row.get("subtotal", 0))
        next_sales = money(next_row.get("subtotal", 0))
        prior_sales = money(prior_row.get("subtotal", 0))
        branch_comparison.append({
            "branch_id": current_branch_id,
            "branch": branch_names.get(current_branch_id, f"Branch #{current_branch_id}"),
            "orders": int(current_row.get("orders", 0)),
            "quantity": quantity_decimal(current_row.get("quantity", 0)),
            "subtotal": money(current_row.get("subtotal", 0)),
            "vat": money(current_row.get("vat", 0)),
            "sales": current_sales,
            "previous_sales": previous_sales,
            "previous_change_percent": _change_percent(current_sales, previous_sales),
            "next_sales": next_sales,
            "next_change_percent": _change_percent(next_sales, current_sales),
            "prior_year_sales": prior_sales,
            "prior_year_change_percent": _change_percent(current_sales, prior_sales),
        })
    branch_comparison.sort(key=lambda row: (money(row["sales"]), row["branch"]), reverse=True)

    current_conditions = conditions_for(windows["current"])
    daily_rows = db.execute(select(
        DgteraSalesOrder.sales_date,
        func.count(DgteraSalesOrder.id),
        func.coalesce(func.sum(DgteraSalesOrder.subtotal), 0),
    ).where(*current_conditions).group_by(DgteraSalesOrder.sales_date).order_by(DgteraSalesOrder.sales_date)).all()
    trend: list[dict] = []
    if period == "YEAR":
        monthly: dict[str, dict] = {}
        for sales_date, order_count, sales in daily_rows:
            key = sales_date.strftime("%Y-%m")
            row = monthly.setdefault(key, {"key": key, "orders": 0, "sales": Decimal("0")})
            row["orders"] += int(order_count or 0)
            row["sales"] += money(sales)
        trend = list(monthly.values())
    else:
        trend = [{"key": sales_date.isoformat(), "orders": int(order_count or 0), "sales": money(sales)} for sales_date, order_count, sales in daily_rows]

    coverage = {
        key: _range_coverage(db, connection, window[0], window[1])
        for key, window in windows.items()
    }
    reconciliation = {
        key: dgtera_sales_sync.strict_range_reconciliation_evidence(
            db, connection, window[0], window[1]
        )
        for key, window in windows.items()
    }
    for key in windows:
        coverage[key]["complete"] = bool(
            coverage[key]["complete"] and reconciliation[key]["matched"]
        )
    return {
        "period": period,
        "as_of_date": as_of,
        "windows": {
            key: {"start_date": window[0], "end_date": window[1]}
            for key, window in windows.items()
        },
        "filters": {"branch_id": branch_id, "sales_scope": sales_scope, "service_mode": service_mode},
        "metrics": metrics,
        "coverage": coverage,
        "reconciliation": reconciliation,
        "comparison": {
            "previous_change_percent": _change_percent(current["subtotal"], previous["subtotal"]),
            "next_change_percent": _change_percent(next_period["subtotal"], current["subtotal"]),
            "prior_year_change_percent": _change_percent(current["subtotal"], prior_year["subtotal"]),
        },
        "branch_comparison": branch_comparison,
        "trend": trend,
        "history": dgtera_sales_sync.historical_backfill_status(db, connection),
    }


@router.get("/executive-summary")
def executive_summary(
    company_id: int,
    as_of_date: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One lightweight source for the holding and restaurant home cards."""
    ensure_permission(db, user, company_id, "pos.read")
    connection, inherited = _connection_scope(db, company_id)
    assert connection is not None
    today = utc_now_aware().astimezone(ZoneInfo(connection.timezone)).date()
    as_of = as_of_date or today
    periods: dict[str, dict] = {}
    for period in ("DAY", "WEEK", "MONTH", "YEAR"):
        windows = _comparison_windows(as_of, period)
        metrics = {
            key: _order_metrics(
                db,
                _order_conditions(connection.id, window[0], window[1]),
            )
            for key, window in windows.items()
        }
        coverage = {
            key: _range_coverage(db, connection, window[0], window[1])
            for key, window in windows.items()
        }
        current_evidence = dgtera_sales_sync.strict_range_reconciliation_evidence(
            db, connection, windows["current"][0], windows["current"][1]
        )
        coverage["current"]["complete"] = bool(
            coverage["current"]["complete"] and current_evidence["matched"]
        )
        periods[period] = {
            "windows": {
                key: {"start_date": window[0], "end_date": window[1]}
                for key, window in windows.items()
            },
            "metrics": metrics,
            "coverage": coverage,
            "reconciliation": current_evidence,
            "comparison": {
                "previous_change_percent": _change_percent(
                    metrics["current"]["subtotal"], metrics["previous"]["subtotal"]
                ),
                "next_change_percent": _change_percent(
                    metrics["next"]["subtotal"], metrics["current"]["subtotal"]
                ),
                "prior_year_change_percent": _change_percent(
                    metrics["current"]["subtotal"], metrics["prior_year"]["subtotal"]
                ),
            },
        }
    return {
        "company_id": company_id,
        "connection_company_id": connection.company_id,
        "inherited": inherited,
        "as_of_date": as_of,
        "timezone": connection.timezone,
        "periods": periods,
        "history": dgtera_sales_sync.historical_backfill_status(db, connection),
    }


@router.get("/sync-runs")
def sync_runs(
    company_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "pos.read")
    connection = _connection(db, company_id)
    rows = db.scalars(
        select(DgteraSyncRun)
        .where(DgteraSyncRun.connection_id == connection.id)
        .order_by(DgteraSyncRun.id.desc())
        .limit(limit)
    ).all()
    return [{
        "id": row.id,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "window": row.window_label,
        "status": row.status,
        "source_orders": row.source_orders,
        "source_lines": row.source_lines,
        "source_payments": row.source_payments,
        "source_quantity": row.source_quantity,
        "source_subtotal": row.source_subtotal,
        "source_vat": row.source_vat,
        "inserted": row.inserted_orders,
        "updated": row.updated_orders,
        "unchanged": row.unchanged_orders,
        "source_total": row.source_total,
        "strict_reconciled": row.strict_reconciled,
        "verification_hash": row.verification_hash,
        "reconciliation": json.loads(row.reconciliation_details) if row.reconciliation_details else None,
        "error": row.error_message,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
    } for row in rows]
