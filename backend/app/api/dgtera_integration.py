from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now, utc_now_aware
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Branch,
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


def _connection(db: Session, company_id: int) -> DgteraConnection:
    row = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == company_id))
    if not row:
        raise HTTPException(404, "DGTERA connection is not configured")
    return row


def _connection_out(row: DgteraConnection | None, company_id: int) -> dict:
    if not row:
        return {
            "company_id": company_id,
            "configured": False,
            "connected": False,
            "mode": "SALES_ONLY",
            "day_window": "00:01-23:59 Asia/Riyadh",
            "sync_interval_minutes": 5,
        }
    return {
        "id": row.id,
        "company_id": row.company_id,
        "configured": True,
        "connected": bool(row.last_tested_at and not row.last_error),
        "name": row.name,
        "base_url": row.base_url,
        "credentials_configured": bool(row.database_name and row.login and row.api_key),
        "active": row.active,
        "mode": "SALES_ONLY",
        "day_window": f"00:01-23:59 {row.timezone}",
        "sync_interval_minutes": row.sync_interval_minutes,
        "timezone": row.timezone,
        "last_tested_at": row.last_tested_at,
        "last_sync_at": row.last_sync_at,
        "last_error": row.last_error,
    }


@router.get("/status")
def status(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    row = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == company_id))
    return _connection_out(row, company_id)


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
    row.sync_interval_minutes = 5
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
            "day_window": f"00:01-23:59 {row.timezone}",
            "sync_interval_minutes": 5,
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
    except (DgteraRemoteError, ValueError) as exc:
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
    if (end - start).days > 31:
        raise HTTPException(422, "The displayed sales window cannot exceed 32 days")
    return start, end


def _summary_row(key: str) -> dict:
    return {"key": key, "orders": 0, "subtotal": Decimal("0"), "vat": Decimal("0"), "sales": Decimal("0")}


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
    conditions = [
        DgteraSalesOrder.company_id == company_id,
        DgteraSalesOrder.sales_date >= start,
        DgteraSalesOrder.sales_date <= end,
    ]
    if branch_id is not None:
        conditions.append(DgteraSalesOrder.branch_id == branch_id)
    if sales_scope:
        conditions.append(DgteraSalesOrder.sales_scope == sales_scope)
    if service_mode:
        conditions.append(DgteraSalesOrder.service_mode == service_mode)
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
        DgteraBranch.company_id == company_id,
        DgteraBranch.active.is_(True),
    ).order_by(DgteraBranch.name)).all()
    branch_name = {row.branch_id: row.name for row in branches}
    customers = db.scalars(select(DgteraCustomer).where(
        DgteraCustomer.company_id == company_id,
        DgteraCustomer.active.is_(True),
    )).all()
    customer_by_id = {row.id: row for row in customers}
    product_ids = {line.product_id for order in orders for line in order.lines}
    products = db.scalars(select(DgteraProduct).where(DgteraProduct.id.in_(product_ids))).all() if product_ids else []
    product_by_id = {row.id: row for row in products}

    totals = {
        "orders": len(orders),
        "subtotal": Decimal("0"),
        "vat": Decimal("0"),
        "sales": Decimal("0"),
        "internal_sales": Decimal("0"),
        "external_sales": Decimal("0"),
        "refunds": Decimal("0"),
    }
    by_branch: dict[str, dict] = {}
    by_scope: dict[str, dict] = {}
    by_service: dict[str, dict] = {}
    by_platform: dict[str, dict] = {}
    by_customer: dict[str, dict] = {}
    by_product: dict[str, dict] = {}

    def add(bucket: dict[str, dict], key: str, subtotal: Decimal, vat: Decimal, sales: Decimal):
        row = bucket.setdefault(key, _summary_row(key))
        row["orders"] += 1
        row["subtotal"] += subtotal
        row["vat"] += vat
        row["sales"] += sales

    for order in orders:
        subtotal, vat, sales = money(order.subtotal), money(order.vat_amount), money(order.total)
        totals["subtotal"] += subtotal
        totals["vat"] += vat
        totals["sales"] += sales
        totals["internal_sales" if order.sales_scope == "INTERNAL" else "external_sales"] += sales
        if sales < 0:
            totals["refunds"] += abs(sales)
        add(by_branch, branch_name.get(order.branch_id, f"Branch #{order.branch_id}"), subtotal, vat, sales)
        add(by_scope, order.sales_scope, subtotal, vat, sales)
        add(by_service, order.service_mode, subtotal, vat, sales)
        if order.delivery_platform_name:
            add(by_platform, order.delivery_platform_name, subtotal, vat, sales)
        customer = customer_by_id.get(order.customer_id)
        add(by_customer, customer.name if customer else "Walk-in / no DGTERA customer", subtotal, vat, sales)
        for line in order.lines:
            product = product_by_id.get(line.product_id)
            key = product.name if product else line.product_name
            row = by_product.setdefault(key, {
                "key": key,
                "code": product.code if product else "",
                "quantity": Decimal("0"),
                "subtotal": Decimal("0"),
                "vat": Decimal("0"),
                "sales": Decimal("0"),
            })
            row["quantity"] += quantity_decimal(line.quantity)
            row["subtotal"] += money(line.subtotal)
            row["vat"] += money(line.vat_amount)
            row["sales"] += money(line.total)

    def rows(bucket: dict[str, dict]) -> list[dict]:
        return sorted(bucket.values(), key=lambda row: (money(row["sales"]), row["key"]), reverse=True)

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
        "window": {"start_date": start, "end_date": end, "day_start": "00:01", "day_end": "23:59", "timezone": connection.timezone},
        "filters": {"branch_id": branch_id, "sales_scope": sales_scope, "service_mode": service_mode, "limit": limit},
        "totals": totals,
        "master_counts": {
            "branches": len(branches),
            "products": db.scalar(select(func.count(DgteraProduct.id)).where(
                DgteraProduct.company_id == company_id,
                DgteraProduct.active.is_(True),
            )) or 0,
            "customers": db.scalar(select(func.count(DgteraCustomer.id)).where(
                DgteraCustomer.company_id == company_id,
                DgteraCustomer.active.is_(True),
            )) or 0,
        },
        "branches": [{"branch_id": row.branch_id, "external_id": row.external_config_id, "code": row.code, "name": row.name} for row in branches],
        "branch_sales": rows(by_branch),
        "scope_sales": rows(by_scope),
        "service_sales": rows(by_service),
        "platform_sales": rows(by_platform),
        "customer_sales": rows(by_customer),
        "product_sales": sorted(by_product.values(), key=lambda row: (money(row["sales"]), row["key"]), reverse=True),
        "orders": order_rows,
    }


def quantity_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


@router.get("/sync-runs")
def sync_runs(
    company_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(
        select(DgteraSyncRun)
        .where(DgteraSyncRun.company_id == company_id)
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
        "inserted": row.inserted_orders,
        "updated": row.updated_orders,
        "unchanged": row.unchanged_orders,
        "source_total": row.source_total,
        "error": row.error_message,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
    } for row in rows]
