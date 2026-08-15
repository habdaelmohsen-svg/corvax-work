"""Automatic, idempotent DGTERA sales mirroring."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, defer, selectinload

from app.core.time import utc_now, utc_now_aware
from app.models import (
    Branch,
    DeliveryPlatform,
    DgteraBranch,
    DgteraConnection,
    DgteraCustomer,
    DgteraProduct,
    DgteraSalesOrder,
    DgteraSalesOrderLine,
    DgteraSalesPayment,
    DgteraSyncRun,
    Party,
)
from app.services.audit import write_audit
from app.services.dgtera_connector import (
    BRANCH_REPORT_ORDER_STATES,
    DgteraRemoteError,
    DgteraResultLimitExceeded,
    Odoo14Client,
    money,
    quantity,
)


_SYNC_LOCK = Lock()
HISTORY_START_DATE = date(2025, 1, 1)
# A single DGTERA business day is the smallest auditable and operationally
# safe transaction.  Committing each day separately prevents the 2025
# backfill from holding one large PostgreSQL transaction while live reports
# are being read.
HISTORY_CHUNK_DAYS = 1
LIVE_SYNC_INTERVAL_MINUTES = 2
HISTORY_RECHECK_INTERVAL_HOURS = 24
SOURCE_LOCAL_WINDOW_MARKER = "dgtera-source-date-line-report-strict-v8"
_TRANSIENT_DB_SQLSTATES = {
    "08000", "08001", "08003", "08004", "08006", "08007", "08P01",
    "40001", "40P01", "53300", "53400", "55P03", "57P01", "57P02", "57P03",
}


class DgteraSyncBusy(RuntimeError):
    pass


class DgteraReconciliationError(RuntimeError):
    def __init__(self, report: dict):
        self.report = report
        preview = "; ".join(
            f"{item['path']}: {item['expected']} != {item['actual']}"
            for item in report.get("mismatches", [])[:3]
        )
        super().__init__(
            f"strict reconciliation failed ({report.get('mismatch_count', 0)} differences)"
            + (f": {preview}" if preview else "")
        )


def _operational_error_code(exc: OperationalError) -> str | None:
    original = getattr(exc, "orig", None)
    return (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
    )


def _is_transient_operational_error(exc: OperationalError) -> bool:
    code = _operational_error_code(exc)
    if code in _TRANSIENT_DB_SQLSTATES or (code and code.startswith("08")):
        return True
    message = str(getattr(exc, "orig", exc)).casefold()
    return any(token in message for token in (
        "connection reset",
        "connection refused",
        "connection is closed",
        "connection has been closed",
        "server closed the connection",
        "terminating connection",
        "timeout expired",
        "remaining connection slots",
    ))


def _safe_sync_error(exc: Exception) -> str:
    """Return actionable diagnostics without SQL text, parameters or secrets."""
    if isinstance(exc, OperationalError):
        code = _operational_error_code(exc) or "unknown"
        original = type(getattr(exc, "orig", exc)).__name__
        return f"OperationalError[{code}] ({original})"
    return f"{type(exc).__name__}: {str(exc)[:850]}"


def client_for(connection: DgteraConnection) -> Odoo14Client:
    return Odoo14Client(
        base_url=connection.base_url,
        database=str(connection.database_name),
        login=str(connection.login),
        api_key=str(connection.api_key),
    )


def _window_label(connection: DgteraConnection) -> str:
    return f"00:00-23:59:59 DGTERA source date / {SOURCE_LOCAL_WINDOW_MARKER}"


def _source_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return parsed.replace(tzinfo=None)


def _generated_code(prefix: str, external_id: str, maximum: int) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", external_id).strip("-")
    candidate = f"{prefix}{clean}"
    if len(candidate) <= maximum:
        return candidate
    digest = hashlib.sha1(external_id.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}{digest}"[:maximum]


def _normalized_name(value: str) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", "", (value or "").casefold())


def _upsert_branch(
    db: Session,
    connection: DgteraConnection,
    source: dict,
    cache: dict[str, DgteraBranch] | None = None,
) -> DgteraBranch:
    external_id = str(source["config_id"])
    name = str(source.get("config_name") or f"DGTERA branch {external_id}")[:250]
    row = cache.get(external_id) if cache is not None else None
    if row is None:
        row = db.scalar(select(DgteraBranch).where(
            DgteraBranch.connection_id == connection.id,
            DgteraBranch.external_config_id == external_id,
        ))
    if row is None:
        code = _generated_code("DGT-B-", external_id, 30)
        branch = db.scalar(select(Branch).where(
            Branch.company_id == connection.company_id,
            Branch.code == code,
        ))
        if branch is None:
            branch = Branch(
                company_id=connection.company_id,
                code=code,
                name_ar=name[:200],
                name_en=name[:200],
                active=True,
            )
            db.add(branch)
            db.flush()
        row = DgteraBranch(
            connection_id=connection.id,
            company_id=connection.company_id,
            external_config_id=external_id,
            code=code,
            name=name,
            branch_id=branch.id,
            active=True,
        )
        db.add(row)
        db.flush()
    else:
        branch = db.get(Branch, row.branch_id)
        if branch:
            branch.name_ar = name[:200]
            branch.name_en = name[:200]
            branch.active = True
        row.name = name
        row.active = True
    if cache is not None:
        cache[external_id] = row
    return row


def _upsert_product(
    db: Session,
    connection: DgteraConnection,
    source: dict,
    cache: dict[str, DgteraProduct] | None = None,
) -> DgteraProduct:
    external_id = str(source["product_id"])
    row = cache.get(external_id) if cache is not None else None
    if row is None:
        row = db.scalar(select(DgteraProduct).where(
            DgteraProduct.connection_id == connection.id,
            DgteraProduct.external_product_id == external_id,
        ))
    if row is None:
        row = DgteraProduct(
            connection_id=connection.id,
            company_id=connection.company_id,
            external_product_id=external_id,
            code=str(source.get("code") or _generated_code("DGT-P-", external_id, 80))[:80],
            name=str(source.get("name") or external_id)[:300],
        )
        db.add(row)
        db.flush()
    row.code = str(source.get("code") or row.code)[:80]
    row.barcode = (str(source.get("barcode"))[:120] if source.get("barcode") else None)
    row.name = str(source.get("name") or row.name)[:300]
    row.external_category_id = (str(source.get("category_id"))[:80] if source.get("category_id") else None)
    row.category_name = (str(source.get("category_name"))[:250] if source.get("category_name") else None)
    row.list_price = money(source.get("list_price"))
    row.active = bool(source.get("active", True))
    row.source_updated_at = _source_datetime(source.get("source_updated_at"))
    if cache is not None:
        cache[external_id] = row
    return row


def _upsert_customer(
    db: Session,
    connection: DgteraConnection,
    source: dict | None,
    *,
    is_platform: bool,
    cache: dict[str, DgteraCustomer] | None = None,
) -> DgteraCustomer | None:
    if not source:
        return None
    external_id = str(source["partner_id"])
    name = str(source.get("name") or f"DGTERA customer {external_id}")[:300]
    row = cache.get(external_id) if cache is not None else None
    if row is None:
        row = db.scalar(select(DgteraCustomer).where(
            DgteraCustomer.connection_id == connection.id,
            DgteraCustomer.external_partner_id == external_id,
        ))
    if row is None:
        party_code = _generated_code("DGT-C-", external_id, 30)
        party = db.scalar(select(Party).where(
            Party.company_id == connection.company_id,
            Party.code == party_code,
        ))
        if party is None:
            party = Party(
                company_id=connection.company_id,
                code=party_code,
                name_ar=name[:250],
                name_en=name[:250],
                party_type="CUSTOMER",
                active=True,
            )
            db.add(party)
            db.flush()
        row = DgteraCustomer(
            connection_id=connection.id,
            company_id=connection.company_id,
            external_partner_id=external_id,
            code=str(source.get("code") or party_code)[:80],
            name=name,
            customer_kind="DELIVERY_PLATFORM" if is_platform else "CUSTOMER",
            party_id=party.id,
            active=True,
        )
        db.add(row)
        db.flush()
    party = db.get(Party, row.party_id)
    if party:
        party.name_ar = name[:250]
        party.name_en = name[:250]
        party.active = bool(source.get("active", True))
    row.code = str(source.get("code") or row.code)[:80]
    row.name = name
    if is_platform:
        row.customer_kind = "DELIVERY_PLATFORM"
    row.active = bool(source.get("active", True))
    row.source_updated_at = _source_datetime(source.get("source_updated_at"))
    if cache is not None:
        cache[external_id] = row
    return row


def _upsert_platform(
    db: Session,
    connection: DgteraConnection,
    name: str | None,
    cache: dict[str, DeliveryPlatform] | None = None,
) -> DeliveryPlatform | None:
    clean_name = str(name or "").strip()
    if not clean_name:
        return None
    normalized = _normalized_name(clean_name)
    if cache is not None and normalized in cache:
        platform = cache[normalized]
        platform.active = True
        return platform
    if cache is None:
        platforms = db.scalars(select(DeliveryPlatform).where(
            DeliveryPlatform.company_id == connection.company_id,
        )).all()
        for platform in platforms:
            if normalized in {
                _normalized_name(platform.code),
                _normalized_name(platform.name_ar),
                _normalized_name(platform.name_en),
            }:
                platform.active = True
                return platform
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12].upper()
    code = f"DGT-{digest}"[:30]
    platform = db.scalar(select(DeliveryPlatform).where(
        DeliveryPlatform.company_id == connection.company_id,
        DeliveryPlatform.code == code,
    ))
    if platform is None:
        platform = DeliveryPlatform(
            company_id=connection.company_id,
            code=code,
            name_ar=clean_name[:150],
            name_en=clean_name[:150],
            commission_rate=Decimal("0"),
            active=True,
        )
        db.add(platform)
        db.flush()
    if cache is not None:
        cache[normalized] = platform
    return platform


def _apply_order(
    db: Session,
    connection: DgteraConnection,
    source: dict,
    caches: dict[str, dict] | None = None,
) -> str:
    caches = caches or {}
    branch_source = source["branch"]
    dgtera_branch = _upsert_branch(db, connection, branch_source, caches.get("branches"))
    customer_source = source.get("customer")
    platform_name = str(source.get("delivery_platform_name") or "")
    is_platform = bool(
        customer_source
        and platform_name
        and _normalized_name(str(customer_source.get("name") or "")) == _normalized_name(platform_name)
    )
    customer = _upsert_customer(
        db, connection, customer_source,
        is_platform=is_platform,
        cache=caches.get("customers"),
    )
    platform = _upsert_platform(
        db, connection, source.get("delivery_platform_name"), caches.get("platforms")
    )
    # Product masters are shared across every sales date, while a line label
    # can vary by size/combo.  Refresh the master even when the order payload
    # itself is unchanged so a historical slice can never leave the global
    # master in a state that makes the next live-day reconciliation fail.
    products_by_external_id: dict[str, DgteraProduct] = {}
    for line_source in source.get("lines", []):
        product_source = line_source["product"]
        external_product_id = str(product_source["product_id"])
        products_by_external_id[external_product_id] = _upsert_product(
            db, connection, product_source, caches.get("products")
        )
    external_id = str(source["order_id"])
    order_cache = caches.get("orders")
    order = order_cache.get(external_id) if order_cache is not None else None
    if order is None and order_cache is None:
        order = db.scalar(select(DgteraSalesOrder).where(
            DgteraSalesOrder.connection_id == connection.id,
            DgteraSalesOrder.external_order_id == external_id,
        ))
    if order is not None and order.source_hash == source["source_hash"]:
        return "UNCHANGED"
    outcome = "INSERTED" if order is None else "UPDATED"
    if order is None:
        order = DgteraSalesOrder(
            connection_id=connection.id,
            company_id=connection.company_id,
            external_order_id=external_id,
            external_order_name=str(source["order_name"])[:150],
            sales_date=date.fromisoformat(str(source["sales_date"])),
            ordered_at_local=datetime.fromisoformat(str(source["date_order_local"])),
            ordered_at_utc=datetime.fromisoformat(str(source["date_order_utc"])),
            branch_id=dgtera_branch.branch_id,
            dgtera_branch_id=dgtera_branch.id,
            classification_source=str(source["classification_source"])[:120],
            state=str(source["state"])[:30],
            source_hash=str(source["source_hash"]),
            source_payload="{}",
        )
        db.add(order)
        db.flush()
        if order_cache is not None:
            order_cache[external_id] = order
    else:
        db.execute(delete(DgteraSalesOrderLine).where(DgteraSalesOrderLine.order_id == order.id))
        db.execute(delete(DgteraSalesPayment).where(DgteraSalesPayment.order_id == order.id))
        # Direct child deletes bypass ORM relationship bookkeeping.  Expire
        # the collections so the strict verifier reloads the replacement
        # lines/payments instead of reusing an identity-map snapshot.
        db.expire(order, ["lines", "payments"])

    order.external_order_name = str(source["order_name"])[:150]
    order.pos_reference = (str(source.get("pos_reference"))[:180] if source.get("pos_reference") else None)
    order.external_session_id = (str(source.get("session_id"))[:80] if source.get("session_id") else None)
    order.external_session_name = (str(source.get("session_name"))[:150] if source.get("session_name") else None)
    order.sales_date = date.fromisoformat(str(source["sales_date"]))
    order.ordered_at_local = datetime.fromisoformat(str(source["date_order_local"]))
    order.ordered_at_utc = datetime.fromisoformat(str(source["date_order_utc"]))
    order.branch_id = dgtera_branch.branch_id
    order.dgtera_branch_id = dgtera_branch.id
    order.customer_id = customer.id if customer else None
    order.party_id = customer.party_id if customer else None
    order.sales_scope = str(source["sales_scope"])[:20]
    order.service_mode = str(source["service_mode"])[:20]
    order.classification_source = str(source["classification_source"])[:120]
    order.delivery_platform_id = platform.id if platform else None
    order.delivery_platform_name = (
        str(source.get("delivery_platform_name"))[:250]
        if source.get("delivery_platform_name") else None
    )
    order.state = str(source["state"])[:30]
    order.subtotal = money(source.get("subtotal"))
    order.vat_amount = money(source.get("vat_amount"))
    order.total = money(source.get("total"))
    order.amount_paid = money(source.get("amount_paid"))
    order.amount_return = money(source.get("amount_return"))
    order.discount_amount = money(source.get("discount_amount"))
    order.line_total_difference = money(source.get("line_total_difference"))
    order.source_hash = str(source["source_hash"])
    order.source_payload = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    order.source_updated_at = _source_datetime(source.get("source_updated_at"))
    order.imported_at = utc_now()
    db.flush()

    for line_source in source.get("lines", []):
        product = products_by_external_id[str(line_source["product"]["product_id"])]
        db.add(DgteraSalesOrderLine(
            order_id=order.id,
            external_line_id=str(line_source["line_id"])[:80],
            product_id=product.id,
            product_name=str(
                line_source.get("line_product_name")
                or line_source["product"]["name"]
            )[:300],
            quantity=quantity(line_source.get("quantity")),
            unit_price=quantity(line_source.get("unit_price")),
            discount_percent=quantity(line_source.get("discount_percent")),
            subtotal=money(line_source.get("subtotal")),
            vat_amount=money(line_source.get("vat_amount")),
            total=money(line_source.get("total")),
            source_tax_ids=json.dumps(line_source.get("tax_ids") or [], separators=(",", ":"))[:500],
        ))
    for payment_source in source.get("payments", []):
        db.add(DgteraSalesPayment(
            order_id=order.id,
            external_payment_id=str(payment_source["payment_id"])[:80],
            external_method_id=(
                str(payment_source.get("method_id"))[:80]
                if payment_source.get("method_id") else None
            ),
            method_name=str(payment_source.get("method_name") or "DGTERA payment")[:250],
            amount=money(payment_source.get("amount")),
        ))
    return outcome


_STRICT_CHECKS = (
    "order_ids", "order_headers", "branches", "customers", "products",
    "lines", "payments", "states", "quantity", "net", "vat", "gross",
    "paid", "returns", "discounts", "source_hashes",
)


def _source_metrics(source_orders: list[dict]) -> dict:
    lines = [line for order in source_orders for line in order.get("lines", [])]
    payments = [payment for order in source_orders for payment in order.get("payments", [])]
    return {
        "orders": len(source_orders),
        "lines": len(lines),
        "payments": len(payments),
        "quantity": sum((quantity(line.get("quantity")) for line in lines), Decimal("0")),
        "subtotal": sum((money(order.get("subtotal")) for order in source_orders), Decimal("0")),
        "vat": sum((money(order.get("vat_amount")) for order in source_orders), Decimal("0")),
        "gross": sum((money(order.get("total")) for order in source_orders), Decimal("0")),
        "paid": sum((money(order.get("amount_paid")) for order in source_orders), Decimal("0")),
        "returns": sum((money(order.get("amount_return")) for order in source_orders), Decimal("0")),
        "discounts": sum((money(order.get("discount_amount")) for order in source_orders), Decimal("0")),
    }


def _shown_metrics(metrics: dict) -> dict:
    return {
        "orders": int(metrics["orders"]),
        "lines": int(metrics["lines"]),
        "payments": int(metrics["payments"]),
        "quantity": format(quantity(metrics["quantity"]), "f"),
        "subtotal": format(money(metrics["subtotal"]), "f"),
        "vat": format(money(metrics["vat"]), "f"),
        "gross": format(money(metrics["gross"]), "f"),
        "paid": format(money(metrics["paid"]), "f"),
        "returns": format(money(metrics["returns"]), "f"),
        "discounts": format(money(metrics["discounts"]), "f"),
    }


def _strict_reconciliation(
    db: Session,
    connection: DgteraConnection,
    start_date: date,
    end_date: date,
    source_orders: list[dict],
) -> dict:
    """Compare every normalized source fact with the persisted mirror.

    Aggregate equality is necessary but not sufficient. Two wrong orders can
    cancel each other financially, so this gate also verifies identities,
    headers, branch/customer/product dimensions, every line, every payment and
    the canonical source hash. A failed gate is rolled back by the caller.
    """
    checks = {name: True for name in _STRICT_CHECKS}
    mismatches: list[dict] = []
    mismatch_count = 0

    def mismatch(category: str, path: str, expected: object, actual: object) -> None:
        nonlocal mismatch_count
        checks[category] = False
        mismatch_count += 1
        if len(mismatches) < 100:
            mismatches.append({
                "category": category,
                "path": path,
                "expected": str(expected),
                "actual": str(actual),
            })

    def same(category: str, path: str, expected: object, actual: object) -> None:
        if expected != actual:
            mismatch(category, path, expected, actual)

    source_ids = [str(row["order_id"]) for row in source_orders]
    if len(source_ids) != len(set(source_ids)):
        duplicates = sorted({value for value in source_ids if source_ids.count(value) > 1})
        mismatch("order_ids", "source.duplicate_order_ids", "none", ",".join(duplicates))
    for source in source_orders:
        source_id = str(source["order_id"])
        if str(source.get("state")) not in BRANCH_REPORT_ORDER_STATES:
            mismatch("states", f"order[{source_id}].state", BRANCH_REPORT_ORDER_STATES, source.get("state"))
        if not (start_date <= date.fromisoformat(str(source["sales_date"])) <= end_date):
            mismatch("order_headers", f"order[{source_id}].sales_date", f"{start_date}..{end_date}", source.get("sales_date"))

    local_orders = db.scalars(
        select(DgteraSalesOrder)
        .where(
            DgteraSalesOrder.connection_id == connection.id,
            DgteraSalesOrder.sales_date >= start_date,
            DgteraSalesOrder.sales_date <= end_date,
        )
        .options(
            selectinload(DgteraSalesOrder.lines),
            selectinload(DgteraSalesOrder.payments),
        )
    ).all()
    source_by_id = {str(row["order_id"]): row for row in source_orders}
    local_by_id = {row.external_order_id: row for row in local_orders}
    same("order_ids", "window.order_ids", sorted(source_by_id), sorted(local_by_id))

    branch_rows = db.scalars(select(DgteraBranch).where(
        DgteraBranch.id.in_({row.dgtera_branch_id for row in local_orders})
    )).all() if local_orders else []
    branch_by_id = {row.id: row for row in branch_rows}
    customer_ids = {row.customer_id for row in local_orders if row.customer_id}
    customer_rows = db.scalars(select(DgteraCustomer).where(
        DgteraCustomer.id.in_(customer_ids)
    )).all() if customer_ids else []
    customer_by_id = {row.id: row for row in customer_rows}
    product_ids = {line.product_id for order in local_orders for line in order.lines}
    product_rows = db.scalars(select(DgteraProduct).where(
        DgteraProduct.id.in_(product_ids)
    )).all() if product_ids else []
    product_by_id = {row.id: row for row in product_rows}

    expected_branches: dict[str, dict] = {}
    expected_customers: dict[str, dict] = {}
    expected_products: dict[str, dict] = {}
    for source in source_orders:
        expected_branches[str(source["branch"]["config_id"])] = source["branch"]
        if source.get("customer"):
            expected_customers[str(source["customer"]["partner_id"])] = source["customer"]
        for line in source.get("lines", []):
            expected_products[str(line["product"]["product_id"])] = line["product"]

    for external_id in sorted(set(source_by_id) | set(local_by_id)):
        source = source_by_id.get(external_id)
        order = local_by_id.get(external_id)
        if source is None or order is None:
            continue
        prefix = f"order[{external_id}]"
        branch = branch_by_id.get(order.dgtera_branch_id)
        customer = customer_by_id.get(order.customer_id) if order.customer_id else None
        same("order_headers", f"{prefix}.name", str(source["order_name"])[:150], order.external_order_name)
        same("order_headers", f"{prefix}.pos_reference", str(source.get("pos_reference"))[:180] if source.get("pos_reference") else None, order.pos_reference)
        same("order_headers", f"{prefix}.session_id", str(source.get("session_id"))[:80] if source.get("session_id") else None, order.external_session_id)
        same("order_headers", f"{prefix}.session_name", str(source.get("session_name"))[:150] if source.get("session_name") else None, order.external_session_name)
        same("order_headers", f"{prefix}.sales_date", date.fromisoformat(str(source["sales_date"])), order.sales_date)
        same("order_headers", f"{prefix}.ordered_at_local", datetime.fromisoformat(str(source["date_order_local"])), order.ordered_at_local)
        same("order_headers", f"{prefix}.ordered_at_utc", datetime.fromisoformat(str(source["date_order_utc"])), order.ordered_at_utc)
        same("branches", f"{prefix}.branch_id", str(source["branch"]["config_id"]), branch.external_config_id if branch else None)
        expected_customer = str(source["customer"]["partner_id"]) if source.get("customer") else None
        same("customers", f"{prefix}.customer_id", expected_customer, customer.external_partner_id if customer else None)
        same("order_headers", f"{prefix}.sales_scope", str(source["sales_scope"])[:20], order.sales_scope)
        same("order_headers", f"{prefix}.service_mode", str(source["service_mode"])[:20], order.service_mode)
        same("order_headers", f"{prefix}.classification_source", str(source["classification_source"])[:120], order.classification_source)
        same("order_headers", f"{prefix}.platform", str(source.get("delivery_platform_name"))[:250] if source.get("delivery_platform_name") else None, order.delivery_platform_name)
        same("states", f"{prefix}.state", str(source["state"])[:30], order.state)
        for category, source_key, local_value in (
            ("net", "subtotal", order.subtotal),
            ("vat", "vat_amount", order.vat_amount),
            ("gross", "total", order.total),
            ("paid", "amount_paid", order.amount_paid),
            ("returns", "amount_return", order.amount_return),
            ("discounts", "discount_amount", order.discount_amount),
            ("gross", "line_total_difference", order.line_total_difference),
        ):
            same(category, f"{prefix}.{source_key}", money(source.get(source_key)), money(local_value))
        same("source_hashes", f"{prefix}.source_hash", str(source["source_hash"]), order.source_hash)
        try:
            stored_payload = json.loads(str(order.source_payload))
        except (TypeError, ValueError, json.JSONDecodeError):
            stored_payload = None
        same("source_hashes", f"{prefix}.source_payload", source, stored_payload)

        source_lines = {str(row["line_id"]): row for row in source.get("lines", [])}
        local_lines = {row.external_line_id: row for row in order.lines}
        same("lines", f"{prefix}.line_ids", sorted(source_lines), sorted(local_lines))
        if len(source.get("lines", [])) != len(source_lines):
            mismatch("lines", f"{prefix}.source_duplicate_line_ids", "none", "duplicates")
        for line_id in sorted(set(source_lines) & set(local_lines)):
            source_line, line = source_lines[line_id], local_lines[line_id]
            line_prefix = f"{prefix}.line[{line_id}]"
            product = product_by_id.get(line.product_id)
            same("products", f"{line_prefix}.product_id", str(source_line["product"]["product_id"]), product.external_product_id if product else None)
            same(
                "products",
                f"{line_prefix}.product_name",
                str(source_line.get("line_product_name") or source_line["product"]["name"])[:300],
                line.product_name,
            )
            same("quantity", f"{line_prefix}.quantity", quantity(source_line.get("quantity")), quantity(line.quantity))
            same("lines", f"{line_prefix}.unit_price", quantity(source_line.get("unit_price")), quantity(line.unit_price))
            same("lines", f"{line_prefix}.discount_percent", quantity(source_line.get("discount_percent")), quantity(line.discount_percent))
            same("net", f"{line_prefix}.subtotal", money(source_line.get("subtotal")), money(line.subtotal))
            same("vat", f"{line_prefix}.vat", money(source_line.get("vat_amount")), money(line.vat_amount))
            same("gross", f"{line_prefix}.total", money(source_line.get("total")), money(line.total))
            expected_taxes = sorted(str(item) for item in (source_line.get("tax_ids") or []))
            try:
                actual_taxes = sorted(str(item) for item in json.loads(line.source_tax_ids or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                actual_taxes = [str(line.source_tax_ids)]
            same("lines", f"{line_prefix}.tax_ids", expected_taxes, actual_taxes)

        source_payments = {str(row["payment_id"]): row for row in source.get("payments", [])}
        local_payments = {row.external_payment_id: row for row in order.payments}
        same("payments", f"{prefix}.payment_ids", sorted(source_payments), sorted(local_payments))
        if len(source.get("payments", [])) != len(source_payments):
            mismatch("payments", f"{prefix}.source_duplicate_payment_ids", "none", "duplicates")
        for payment_id in sorted(set(source_payments) & set(local_payments)):
            source_payment, payment = source_payments[payment_id], local_payments[payment_id]
            payment_prefix = f"{prefix}.payment[{payment_id}]"
            same("payments", f"{payment_prefix}.method_id", str(source_payment.get("method_id"))[:80] if source_payment.get("method_id") else None, payment.external_method_id)
            same("payments", f"{payment_prefix}.method_name", str(source_payment.get("method_name") or "DGTERA payment")[:250], payment.method_name)
            same("payments", f"{payment_prefix}.amount", money(source_payment.get("amount")), money(payment.amount))

    actual_branches = {row.external_config_id: row for row in branch_rows}
    for external_id, expected in expected_branches.items():
        actual = actual_branches.get(external_id)
        same("branches", f"branch[{external_id}].name", str(expected.get("config_name") or f"DGTERA branch {external_id}")[:250], actual.name if actual else None)
    actual_customers = {row.external_partner_id: row for row in customer_rows}
    for external_id, expected in expected_customers.items():
        actual = actual_customers.get(external_id)
        same("customers", f"customer[{external_id}].name", str(expected.get("name") or f"DGTERA customer {external_id}")[:300], actual.name if actual else None)
        same("customers", f"customer[{external_id}].code", str(expected.get("code") or _generated_code("DGT-C-", external_id, 30))[:80], actual.code if actual else None)
    actual_products = {row.external_product_id: row for row in product_rows}
    for external_id, expected in expected_products.items():
        actual = actual_products.get(external_id)
        same("products", f"product[{external_id}].code", str(expected.get("code") or _generated_code("DGT-P-", external_id, 80))[:80], actual.code if actual else None)
        same("products", f"product[{external_id}].name", str(expected.get("name") or external_id)[:300], actual.name if actual else None)
        same("products", f"product[{external_id}].barcode", str(expected.get("barcode"))[:120] if expected.get("barcode") else None, actual.barcode if actual else None)

    source_metrics = _source_metrics(source_orders)
    local_metrics = {
        "orders": len(local_orders),
        "lines": sum(len(order.lines) for order in local_orders),
        "payments": sum(len(order.payments) for order in local_orders),
        "quantity": sum((quantity(line.quantity) for order in local_orders for line in order.lines), Decimal("0")),
        "subtotal": sum((money(order.subtotal) for order in local_orders), Decimal("0")),
        "vat": sum((money(order.vat_amount) for order in local_orders), Decimal("0")),
        "gross": sum((money(order.total) for order in local_orders), Decimal("0")),
        "paid": sum((money(order.amount_paid) for order in local_orders), Decimal("0")),
        "returns": sum((money(order.amount_return) for order in local_orders), Decimal("0")),
        "discounts": sum((money(order.discount_amount) for order in local_orders), Decimal("0")),
    }
    for metric, category in (
        ("orders", "order_ids"), ("lines", "lines"), ("payments", "payments"),
        ("quantity", "quantity"), ("subtotal", "net"), ("vat", "vat"),
        ("gross", "gross"), ("paid", "paid"), ("returns", "returns"),
        ("discounts", "discounts"),
    ):
        same(category, f"window.{metric}", source_metrics[metric], local_metrics[metric])

    source_fingerprint = hashlib.sha256("\n".join(
        f"{external_id}:{source_by_id[external_id].get('source_hash', '')}"
        for external_id in sorted(source_by_id)
    ).encode("utf-8")).hexdigest()
    local_fingerprint = hashlib.sha256("\n".join(
        f"{external_id}:{local_by_id[external_id].source_hash}"
        for external_id in sorted(local_by_id)
    ).encode("utf-8")).hexdigest()
    same("source_hashes", "window.fingerprint", source_fingerprint, local_fingerprint)
    daily: dict[str, dict] = {}
    sales_day_value = start_date
    sales_days: list[str] = []
    while sales_day_value <= end_date:
        sales_days.append(sales_day_value.isoformat())
        sales_day_value += timedelta(days=1)
    for sales_day in sales_days:
        day_orders = [row for row in source_orders if str(row["sales_date"]) == sales_day]
        day_by_id = {str(row["order_id"]): row for row in day_orders}
        daily[sales_day] = {
            "source": _shown_metrics(_source_metrics(day_orders)),
            "verification_hash": hashlib.sha256("\n".join(
                f"{external_id}:{day_by_id[external_id].get('source_hash', '')}"
                for external_id in sorted(day_by_id)
            ).encode("utf-8")).hexdigest(),
        }
    return {
        "strict": True,
        "matched": mismatch_count == 0,
        "mismatch_count": mismatch_count,
        "checks": checks,
        "source": _shown_metrics(source_metrics),
        "corvax": _shown_metrics(local_metrics),
        "verification_hash": source_fingerprint if source_fingerprint == local_fingerprint else None,
        "daily": daily,
        "mismatches": mismatches,
    }


def catchup_window(connection: DgteraConnection) -> tuple[date, date]:
    zone = ZoneInfo(connection.timezone or "Asia/Riyadh")
    now_local = utc_now_aware().astimezone(zone)
    today = now_local.date()
    if connection.last_sync_at:
        last_sync = connection.last_sync_at.replace(tzinfo=timezone.utc).astimezone(zone).date()
        start = min(last_sync, today)
    else:
        start = today.replace(day=1)
    start = max(start, today - timedelta(days=31))
    return start, today


def _strict_completed_intervals(
    db: Session,
    connection: DgteraConnection,
    start_date: date,
    end_date: date,
) -> list[tuple[date, date]]:
    rows = db.execute(select(
        DgteraSyncRun.start_date,
        DgteraSyncRun.end_date,
    ).where(
        DgteraSyncRun.connection_id == connection.id,
        DgteraSyncRun.status == "COMPLETED",
        DgteraSyncRun.strict_reconciled.is_(True),
        DgteraSyncRun.window_label.like(f"%{SOURCE_LOCAL_WINDOW_MARKER}%"),
        DgteraSyncRun.end_date >= start_date,
        DgteraSyncRun.start_date <= end_date,
    ).order_by(DgteraSyncRun.start_date, DgteraSyncRun.end_date)).all()
    merged: list[tuple[date, date]] = []
    for row_start, row_end in rows:
        current_start, current_end = max(row_start, start_date), min(row_end, end_date)
        if not merged or current_start > merged[-1][1] + timedelta(days=1):
            merged.append((current_start, current_end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], current_end))
    return merged


def strict_range_coverage_status(
    db: Session,
    connection: DgteraConnection,
    start_date: date,
    end_date: date,
) -> dict:
    """Prove every requested historical day belongs to a strict completed run."""
    zone = ZoneInfo(connection.timezone or "Asia/Riyadh")
    today = utc_now_aware().astimezone(zone).date()
    historical_end = min(end_date, today)
    if start_date > historical_end:
        return {
            "complete": True,
            "first_missing_date": None,
            "covered_days": 0,
            "required_days": 0,
        }
    intervals = _strict_completed_intervals(db, connection, start_date, historical_end)
    cursor = start_date
    covered_days = 0
    first_missing = None
    for interval_start, interval_end in intervals:
        covered_days += (interval_end - interval_start).days + 1
        if interval_end < cursor:
            continue
        if interval_start > cursor:
            first_missing = cursor
            break
        cursor = max(cursor, interval_end + timedelta(days=1))
        if cursor > historical_end:
            break
    if cursor <= historical_end and first_missing is None:
        first_missing = cursor
    required_days = (historical_end - start_date).days + 1
    verification_rows = db.execute(select(
        DgteraSyncRun.start_date,
        DgteraSyncRun.end_date,
        DgteraSyncRun.completed_at,
    ).where(
        DgteraSyncRun.connection_id == connection.id,
        DgteraSyncRun.status == "COMPLETED",
        DgteraSyncRun.strict_reconciled.is_(True),
        DgteraSyncRun.window_label.like(f"%{SOURCE_LOCAL_WINDOW_MARKER}%"),
        DgteraSyncRun.end_date >= start_date,
        DgteraSyncRun.start_date <= historical_end,
    )).all()
    day_verifications: list[datetime] = []
    day = start_date
    while day <= historical_end:
        candidates = [
            completed_at for run_start, run_end, completed_at in verification_rows
            if completed_at is not None and run_start <= day <= run_end
        ]
        if candidates:
            day_verifications.append(max(candidates))
        day += timedelta(days=1)
    return {
        "complete": first_missing is None,
        "first_missing_date": first_missing,
        "covered_days": min(covered_days, required_days),
        "required_days": required_days,
        "oldest_verified_at": min(day_verifications) if day_verifications else None,
        "last_verified_at": max(day_verifications) if day_verifications else None,
    }


def strict_persisted_reconciliation(
    db: Session,
    connection: DgteraConnection,
    start_date: date,
    end_date: date,
) -> dict:
    """Recheck the mirror against the immutable payload captured from DGTERA."""
    rows = db.scalars(select(DgteraSalesOrder).where(
        DgteraSalesOrder.connection_id == connection.id,
        DgteraSalesOrder.sales_date >= start_date,
        DgteraSalesOrder.sales_date <= end_date,
    )).all()
    source_orders: list[dict] = []
    payload_errors: list[str] = []
    for row in rows:
        try:
            payload = json.loads(str(row.source_payload))
            if not isinstance(payload, dict):
                raise ValueError("payload is not an object")
            source_orders.append(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            payload_errors.append(f"order[{row.external_order_id}]: {type(exc).__name__}")
    report = _strict_reconciliation(
        db, connection, start_date, end_date, source_orders
    )
    coverage = strict_range_coverage_status(db, connection, start_date, end_date)
    if payload_errors:
        report["matched"] = False
        report["mismatch_count"] += len(payload_errors)
        report["checks"]["source_hashes"] = False
        report["mismatches"].extend({
            "category": "source_hashes",
            "path": value,
            "expected": "valid encrypted source payload",
            "actual": "unreadable",
        } for value in payload_errors[:100 - len(report["mismatches"])])
    report["coverage"] = coverage
    report["matched"] = bool(report["matched"] and coverage["complete"])
    report["verified_from_live_source"] = coverage["complete"]
    return report


def strict_range_reconciliation_evidence(
    db: Session,
    connection: DgteraConnection,
    start_date: date,
    end_date: date,
) -> dict:
    """Compose daily live-source proofs and compare them to current aggregates."""
    coverage = strict_range_coverage_status(db, connection, start_date, end_date)
    checks = {name: True for name in _STRICT_CHECKS}
    mismatches: list[dict] = []

    def mismatch(category: str, path: str, expected: object, actual: object) -> None:
        checks[category] = False
        if len(mismatches) < 100:
            mismatches.append({
                "category": category,
                "path": path,
                "expected": str(expected),
                "actual": str(actual),
            })

    if coverage["required_days"] == 0:
        mismatch("order_ids", "range.live_source", "historical/current period", "future period")

    runs = db.scalars(select(DgteraSyncRun).where(
        DgteraSyncRun.connection_id == connection.id,
        DgteraSyncRun.status == "COMPLETED",
        DgteraSyncRun.strict_reconciled.is_(True),
        DgteraSyncRun.window_label.like(f"%{SOURCE_LOCAL_WINDOW_MARKER}%"),
        DgteraSyncRun.end_date >= start_date,
        DgteraSyncRun.start_date <= end_date,
    ).order_by(DgteraSyncRun.completed_at.desc(), DgteraSyncRun.id.desc())).all()
    daily: dict[str, dict] = {}
    for run in runs:
        try:
            details = json.loads(run.reconciliation_details or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for day_key, evidence in (details.get("daily") or {}).items():
            if start_date <= date.fromisoformat(day_key) <= end_date and day_key not in daily:
                daily[day_key] = evidence

    required_end = min(end_date, utc_now_aware().astimezone(ZoneInfo(connection.timezone)).date())
    day = start_date
    while day <= required_end:
        if day.isoformat() not in daily:
            mismatch("source_hashes", f"day[{day.isoformat()}].proof", "strict live-source proof", "missing")
        day += timedelta(days=1)

    source_metrics = {
        "orders": 0, "lines": 0, "payments": 0, "quantity": Decimal("0"),
        "subtotal": Decimal("0"), "vat": Decimal("0"), "gross": Decimal("0"),
        "paid": Decimal("0"), "returns": Decimal("0"), "discounts": Decimal("0"),
    }
    for evidence in daily.values():
        metrics = evidence.get("source") or {}
        for key in ("orders", "lines", "payments"):
            source_metrics[key] += int(metrics.get(key) or 0)
        for key in ("quantity", "subtotal", "vat", "gross", "paid", "returns", "discounts"):
            source_metrics[key] += Decimal(str(metrics.get(key) or 0))

    order_row = db.execute(select(
        func.count(DgteraSalesOrder.id),
        func.coalesce(func.sum(DgteraSalesOrder.subtotal), 0),
        func.coalesce(func.sum(DgteraSalesOrder.vat_amount), 0),
        func.coalesce(func.sum(DgteraSalesOrder.total), 0),
        func.coalesce(func.sum(DgteraSalesOrder.amount_paid), 0),
        func.coalesce(func.sum(DgteraSalesOrder.amount_return), 0),
        func.coalesce(func.sum(DgteraSalesOrder.discount_amount), 0),
    ).where(
        DgteraSalesOrder.connection_id == connection.id,
        DgteraSalesOrder.sales_date >= start_date,
        DgteraSalesOrder.sales_date <= end_date,
    )).one()
    line_row = db.execute(select(
        func.count(DgteraSalesOrderLine.id),
        func.coalesce(func.sum(DgteraSalesOrderLine.quantity), 0),
    ).join(DgteraSalesOrder, DgteraSalesOrder.id == DgteraSalesOrderLine.order_id).where(
        DgteraSalesOrder.connection_id == connection.id,
        DgteraSalesOrder.sales_date >= start_date,
        DgteraSalesOrder.sales_date <= end_date,
    )).one()
    payment_count = db.scalar(select(func.count(DgteraSalesPayment.id)).join(
        DgteraSalesOrder, DgteraSalesOrder.id == DgteraSalesPayment.order_id
    ).where(
        DgteraSalesOrder.connection_id == connection.id,
        DgteraSalesOrder.sales_date >= start_date,
        DgteraSalesOrder.sales_date <= end_date,
    )) or 0
    local_metrics = {
        "orders": int(order_row[0] or 0),
        "lines": int(line_row[0] or 0),
        "payments": int(payment_count),
        "quantity": quantity(line_row[1]),
        "subtotal": money(order_row[1]),
        "vat": money(order_row[2]),
        "gross": money(order_row[3]),
        "paid": money(order_row[4]),
        "returns": money(order_row[5]),
        "discounts": money(order_row[6]),
    }
    for metric, category in (
        ("orders", "order_ids"), ("lines", "lines"), ("payments", "payments"),
        ("quantity", "quantity"), ("subtotal", "net"), ("vat", "vat"),
        ("gross", "gross"), ("paid", "paid"), ("returns", "returns"),
        ("discounts", "discounts"),
    ):
        if source_metrics[metric] != local_metrics[metric]:
            mismatch(category, f"range.{metric}", source_metrics[metric], local_metrics[metric])

    local_hash_rows = db.execute(select(
        DgteraSalesOrder.sales_date,
        DgteraSalesOrder.external_order_id,
        DgteraSalesOrder.source_hash,
    ).where(
        DgteraSalesOrder.connection_id == connection.id,
        DgteraSalesOrder.sales_date >= start_date,
        DgteraSalesOrder.sales_date <= end_date,
    ).order_by(DgteraSalesOrder.sales_date, DgteraSalesOrder.external_order_id)).all()
    local_day_hashes: dict[str, list[tuple[str, str]]] = {}
    for sales_day, external_id, source_hash in local_hash_rows:
        local_day_hashes.setdefault(sales_day.isoformat(), []).append((external_id, source_hash))
    for day_key, evidence in daily.items():
        actual_hash = hashlib.sha256("\n".join(
            f"{external_id}:{source_hash}"
            for external_id, source_hash in local_day_hashes.get(day_key, [])
        ).encode("utf-8")).hexdigest()
        expected_hash = evidence.get("verification_hash")
        if expected_hash != actual_hash:
            mismatch("source_hashes", f"day[{day_key}].fingerprint", expected_hash, actual_hash)

    if not coverage["complete"]:
        mismatch("order_ids", "range.date_coverage", "no missing days", coverage.get("first_missing_date"))
    aggregate_hash = hashlib.sha256("\n".join(
        f"{day_key}:{daily[day_key].get('verification_hash', '')}"
        for day_key in sorted(daily)
    ).encode("utf-8")).hexdigest()
    return {
        "strict": True,
        "matched": len(mismatches) == 0,
        "mismatch_count": len(mismatches),
        "checks": checks,
        "source": _shown_metrics(source_metrics),
        "corvax": _shown_metrics(local_metrics),
        "difference": format(money(local_metrics["gross"] - source_metrics["gross"]), "f"),
        "verification_hash": aggregate_hash if not mismatches else None,
        "verified_from_live_source": bool(coverage["complete"] and coverage["required_days"] > 0),
        "oldest_verified_at": coverage.get("oldest_verified_at"),
        "last_verified_at": coverage.get("last_verified_at"),
        "days_verified": len(daily),
        "orders_verified_individually": True,
        "mismatches": mismatches,
    }


def historical_backfill_status(db: Session, connection: DgteraConnection) -> dict:
    """Return progress for the contiguous DGTERA report-date history import.

    Runs created before the V8 source-report date correction are intentionally
    not counted. Re-reading those dates updates their existing order ids and
    moves each order to the exact date used by DGTERA's Branch Sales report.
    """
    zone = ZoneInfo(connection.timezone or "Asia/Riyadh")
    today = utc_now_aware().astimezone(zone).date()
    intervals = _strict_completed_intervals(db, connection, HISTORY_START_DATE, today)
    earliest = None
    for interval_start, interval_end in intervals:
        if interval_start <= today <= interval_end:
            earliest = interval_start
            break
    total_days = max(1, (today - HISTORY_START_DATE).days + 1)
    covered_days = 0 if earliest is None else max(0, (today - max(earliest, HISTORY_START_DATE)).days + 1)
    covered_days = min(total_days, covered_days)
    completed = bool(earliest and earliest <= HISTORY_START_DATE)
    return {
        "start_date": HISTORY_START_DATE,
        "target_end_date": today,
        "earliest_imported_date": earliest,
        "covered_days": covered_days,
        "total_days": total_days,
        "progress_percent": round(covered_days * 100 / total_days, 1),
        "completed": completed,
        "strict_reconciliation": True,
        "no_date_gaps": completed,
    }


def historical_backfill_window(db: Session, connection: DgteraConnection) -> tuple[date, date] | None:
    status = historical_backfill_status(db, connection)
    if status["completed"]:
        return None
    earliest = status["earliest_imported_date"]
    if earliest is None:
        end = status["target_end_date"]
    else:
        end = earliest - timedelta(days=1)
    if end < HISTORY_START_DATE:
        return None
    start = max(HISTORY_START_DATE, end - timedelta(days=HISTORY_CHUNK_DAYS - 1))
    return start, end


def connection_is_due(connection: DgteraConnection) -> bool:
    if not connection.active or not connection.last_tested_at:
        return False
    if not connection.last_sync_at:
        return True
    elapsed = utc_now() - connection.last_sync_at
    return elapsed >= timedelta(minutes=LIVE_SYNC_INTERVAL_MINUTES)


def changed_historical_sales_dates(
    connection: DgteraConnection,
    since_utc: datetime,
) -> list[date]:
    # Overlap the watermark so a source write committed on a poll boundary is
    # observed twice rather than missed once. Idempotent order ids make this safe.
    safe_since = since_utc - timedelta(minutes=5)
    return client_for(connection).changed_sales_dates(
        safe_since, HISTORY_START_DATE, connection.timezone
    )


def historical_recheck_window(
    db: Session,
    connection: DgteraConnection,
) -> tuple[date, date] | None:
    """Select the stalest completed historical slice for a rolling full audit."""
    status = historical_backfill_status(db, connection)
    if not status["completed"]:
        return None
    rows = db.execute(select(
        DgteraSyncRun.start_date,
        DgteraSyncRun.end_date,
        func.max(DgteraSyncRun.completed_at).label("last_verified_at"),
    ).where(
        DgteraSyncRun.connection_id == connection.id,
        DgteraSyncRun.status == "COMPLETED",
        DgteraSyncRun.strict_reconciled.is_(True),
        DgteraSyncRun.window_label.like(f"%{SOURCE_LOCAL_WINDOW_MARKER}%"),
    ).group_by(
        DgteraSyncRun.start_date,
        DgteraSyncRun.end_date,
    ).order_by("last_verified_at", DgteraSyncRun.start_date)).all()
    if not rows:
        return None
    start_date, end_date, last_verified_at = rows[0]
    if last_verified_at and last_verified_at > utc_now() - timedelta(hours=HISTORY_RECHECK_INTERVAL_HOURS):
        return None
    return start_date, end_date


def _sync_caches(
    db: Session,
    connection: DgteraConnection,
    source_orders: list[dict],
) -> dict[str, dict]:
    """Prefetch reusable mirror rows for one transaction.

    The former implementation queried and flushed branch, product, customer,
    platform and order rows repeatedly for every order line.  A normal sales
    day therefore produced thousands of PostgreSQL round trips, and the 2025
    backfill could exhaust the live database connection.  These maps retain
    the same idempotent keys while reducing each entity to one lookup.
    """
    branches = {
        row.external_config_id: row
        for row in db.scalars(select(DgteraBranch).where(
            DgteraBranch.connection_id == connection.id,
        )).all()
    }
    products = {
        row.external_product_id: row
        for row in db.scalars(select(DgteraProduct).where(
            DgteraProduct.connection_id == connection.id,
        )).all()
    }
    customers = {
        row.external_partner_id: row
        for row in db.scalars(select(DgteraCustomer).where(
            DgteraCustomer.connection_id == connection.id,
        )).all()
    }
    platforms: dict[str, DeliveryPlatform] = {}
    for row in db.scalars(select(DeliveryPlatform).where(
        DeliveryPlatform.company_id == connection.company_id,
    )).all():
        for value in (row.code, row.name_ar, row.name_en):
            normalized = _normalized_name(str(value or ""))
            if normalized:
                platforms[normalized] = row
    source_ids = sorted({str(row["order_id"]) for row in source_orders})
    order_rows = db.scalars(
        select(DgteraSalesOrder)
        .where(
            DgteraSalesOrder.connection_id == connection.id,
            DgteraSalesOrder.external_order_id.in_(source_ids),
        )
        .options(defer(DgteraSalesOrder.source_payload))
    ).all() if source_ids else []
    return {
        "branches": branches,
        "products": products,
        "customers": customers,
        "platforms": platforms,
        "orders": {row.external_order_id: row for row in order_rows},
    }


def _sync_unlocked(
    db: Session,
    connection: DgteraConnection,
    start_date: date,
    end_date: date,
    actor_user_id: int,
    *,
    mark_current_sync: bool,
) -> dict:
    try:
        source_orders = client_for(connection).daily_sales(start_date, end_date, connection.timezone)
    except DgteraResultLimitExceeded:
        # Nothing has been changed locally yet.  Let the outer orchestrator
        # split this source range without recording a false failed sync run.
        raise
    except (DgteraRemoteError, ValueError) as exc:
        connection.last_error = str(exc)
        run = DgteraSyncRun(
            connection_id=connection.id,
            company_id=connection.company_id,
            start_date=start_date,
            end_date=end_date,
            window_label=_window_label(connection),
            status="ERROR",
            error_message=str(exc)[:1000],
            completed_at=utc_now(),
        )
        db.add(run)
        db.commit()
        raise

    source_metrics = _source_metrics(source_orders)
    run = DgteraSyncRun(
        connection_id=connection.id,
        company_id=connection.company_id,
        start_date=start_date,
        end_date=end_date,
        window_label=_window_label(connection),
        status="RUNNING",
        source_orders=len(source_orders),
        source_lines=source_metrics["lines"],
        source_payments=source_metrics["payments"],
        source_quantity=source_metrics["quantity"],
        source_subtotal=source_metrics["subtotal"],
        source_vat=source_metrics["vat"],
        source_total=source_metrics["gross"],
        source_paid=source_metrics["paid"],
        source_return=source_metrics["returns"],
        source_discount=source_metrics["discounts"],
    )
    db.add(run)
    db.flush()
    caches = _sync_caches(db, connection, source_orders)
    counts = {"INSERTED": 0, "UPDATED": 0, "UNCHANGED": 0}
    removed = 0
    try:
        # A completed range is a source-of-truth snapshot.  Removing records
        # no longer returned also clears cancelled orders and, importantly,
        # orders assigned to the wrong day by the former UTC conversion.
        source_ids = {str(row["order_id"]) for row in source_orders}
        stale_ids = list(db.scalars(select(DgteraSalesOrder.id).where(
            DgteraSalesOrder.connection_id == connection.id,
            DgteraSalesOrder.sales_date >= start_date,
            DgteraSalesOrder.sales_date <= end_date,
            *(
                [DgteraSalesOrder.external_order_id.not_in(source_ids)]
                if source_ids else []
            ),
        )).all())
        if stale_ids:
            removed = len(stale_ids)
            db.execute(delete(DgteraSalesOrder).where(DgteraSalesOrder.id.in_(stale_ids)))
        for source in source_orders:
            counts[_apply_order(db, connection, source, caches)] += 1
        db.flush()
        reconciliation = _strict_reconciliation(
            db, connection, start_date, end_date, source_orders
        )
        if not reconciliation["matched"]:
            raise DgteraReconciliationError(reconciliation)
        imported_total = money(reconciliation["corvax"]["gross"])
        run.inserted_orders = counts["INSERTED"]
        run.updated_orders = counts["UPDATED"]
        run.unchanged_orders = counts["UNCHANGED"]
        run.strict_reconciled = True
        run.verification_hash = reconciliation["verification_hash"]
        run.reconciliation_details = json.dumps(
            reconciliation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        run.status = "COMPLETED"
        run.completed_at = utc_now()
        if mark_current_sync:
            connection.last_sync_at = utc_now()
        connection.last_error = None
        write_audit(
            db,
            action="DGTERA_SALES_SYNC_COMPLETED",
            entity_type="DGTERA_SYNC_RUN",
            entity_id=run.id,
            user_id=actor_user_id,
            company_id=connection.company_id,
            after={
                "start_date": str(start_date),
                "end_date": str(end_date),
                "window": run.window_label,
                "source_orders": len(source_orders),
                "inserted": counts["INSERTED"],
                "updated": counts["UPDATED"],
                "unchanged": counts["UNCHANGED"],
                "removed": removed,
                "source_total": str(run.source_total),
                "strict_reconciled": True,
                "verification_hash": run.verification_hash,
                "checks": reconciliation["checks"],
                "mode": "SALES_ONLY",
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        connection = db.get(DgteraConnection, connection.id)
        if connection:
            if isinstance(exc, DgteraReconciliationError):
                first_paths = [
                    str(item.get("path") or "")
                    for item in exc.report.get("mismatches", [])[:3]
                    if item.get("path")
                ]
                detail = f": {exc.report.get('mismatch_count', 0)} differences"
                if first_paths:
                    detail += f" [{', '.join(first_paths)}]"
                connection.last_error = f"Sales mirror failed (DgteraReconciliationError){detail}"[:1000]
            else:
                connection.last_error = f"Sales mirror failed — {_safe_sync_error(exc)}"[:1000]
        failed_report = exc.report if isinstance(exc, DgteraReconciliationError) else None
        failed = DgteraSyncRun(
            connection_id=connection.id if connection else run.connection_id,
            company_id=connection.company_id if connection else run.company_id,
            start_date=start_date,
            end_date=end_date,
            window_label=(
                _window_label(connection)
                if connection else f"00:00-23:59:59 DGTERA source date / {SOURCE_LOCAL_WINDOW_MARKER}"
            ),
            status="ERROR",
            source_orders=len(source_orders),
            source_lines=source_metrics["lines"],
            source_payments=source_metrics["payments"],
            source_quantity=source_metrics["quantity"],
            source_subtotal=source_metrics["subtotal"],
            source_vat=source_metrics["vat"],
            source_total=source_metrics["gross"],
            source_paid=source_metrics["paid"],
            source_return=source_metrics["returns"],
            source_discount=source_metrics["discounts"],
            strict_reconciled=False,
            reconciliation_details=(
                json.dumps(failed_report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if failed_report else None
            ),
            error_message=_safe_sync_error(exc),
            completed_at=utc_now(),
        )
        db.add(failed)
        db.commit()
        raise
    return {
        "run_id": run.id,
        "start_date": start_date,
        "end_date": end_date,
        "window": run.window_label,
        "source_orders": len(source_orders),
        "inserted": counts["INSERTED"],
        "updated": counts["UPDATED"],
        "unchanged": counts["UNCHANGED"],
        "removed": removed,
        "source_total": run.source_total,
        "imported_total": imported_total,
        "reconciled": True,
        "strict_reconciled": True,
        "verification_hash": reconciliation["verification_hash"],
        "reconciliation": reconciliation,
        "mode": "SALES_ONLY",
    }


def _merge_split_sync_results(
    start_date: date,
    end_date: date,
    results: list[dict],
) -> dict:
    """Combine independently reconciled child windows without losing proof."""
    if not results:
        raise RuntimeError("DGTERA split synchronization produced no verified windows")
    source_metrics = {
        "orders": 0, "lines": 0, "payments": 0, "quantity": Decimal("0"),
        "subtotal": Decimal("0"), "vat": Decimal("0"), "gross": Decimal("0"),
        "paid": Decimal("0"), "returns": Decimal("0"), "discounts": Decimal("0"),
    }
    local_metrics = dict(source_metrics)
    checks = {name: True for name in _STRICT_CHECKS}
    daily: dict[str, dict] = {}
    verification_parts: list[str] = []
    for result in results:
        report = result["reconciliation"]
        if not report.get("matched"):
            raise DgteraReconciliationError(report)
        for name in checks:
            checks[name] = bool(checks[name] and report.get("checks", {}).get(name, False))
        for destination, shown in (
            (source_metrics, report.get("source", {})),
            (local_metrics, report.get("corvax", {})),
        ):
            for key in ("orders", "lines", "payments"):
                destination[key] += int(shown.get(key) or 0)
            for key in ("quantity", "subtotal", "vat", "gross", "paid", "returns", "discounts"):
                destination[key] += Decimal(str(shown.get(key) or 0))
        daily.update(report.get("daily") or {})
        verification_parts.append(
            f"{result['start_date']}:{result['end_date']}:{result.get('verification_hash') or ''}"
        )
    verification_hash = hashlib.sha256("\n".join(verification_parts).encode("utf-8")).hexdigest()
    reconciliation = {
        "strict": True,
        "matched": all(checks.values()) and source_metrics == local_metrics,
        "mismatch_count": 0,
        "checks": checks,
        "source": _shown_metrics(source_metrics),
        "corvax": _shown_metrics(local_metrics),
        "difference": format(money(local_metrics["gross"] - source_metrics["gross"]), "f"),
        "verification_hash": verification_hash,
        "daily": daily,
        "mismatches": [],
    }
    if not reconciliation["matched"]:
        reconciliation["mismatch_count"] = 1
        reconciliation["mismatches"] = [{
            "category": "source_hashes",
            "path": "split.aggregate",
            "expected": "all child proofs and aggregate metrics equal",
            "actual": "aggregate proof mismatch",
        }]
        raise DgteraReconciliationError(reconciliation)
    return {
        "run_id": results[-1]["run_id"],
        "run_ids": [result["run_id"] for result in results],
        "start_date": start_date,
        "end_date": end_date,
        "window": f"{results[0]['window']} / adaptive-safe-split",
        "split_windows": len(results),
        "source_orders": sum(int(result.get("source_orders") or 0) for result in results),
        "inserted": sum(int(result.get("inserted") or 0) for result in results),
        "updated": sum(int(result.get("updated") or 0) for result in results),
        "unchanged": sum(int(result.get("unchanged") or 0) for result in results),
        "removed": sum(int(result.get("removed") or 0) for result in results),
        "source_total": money(sum(
            (Decimal(str(result.get("source_total") or 0)) for result in results), Decimal("0")
        )),
        "imported_total": money(sum(
            (Decimal(str(result.get("imported_total") or 0)) for result in results), Decimal("0")
        )),
        "reconciled": True,
        "strict_reconciled": True,
        "verification_hash": verification_hash,
        "reconciliation": reconciliation,
        "mode": "SALES_ONLY",
    }


def sync_connection(
    db: Session,
    connection: DgteraConnection,
    start_date: date,
    end_date: date,
    actor_user_id: int,
    *,
    mark_current_sync: bool = True,
) -> dict:
    if not _SYNC_LOCK.acquire(blocking=False):
        raise DgteraSyncBusy("A DGTERA sales synchronization is already running")

    connection_id = connection.id

    def sync_attempt(current_connection: DgteraConnection) -> dict:
        """Run one complete, auditable attempt for the requested date range."""
        try:
            return _sync_unlocked(
                db,
                current_connection,
                start_date,
                end_date,
                actor_user_id,
                mark_current_sync=mark_current_sync,
            )
        except DgteraResultLimitExceeded:
            if start_date >= end_date:
                # A complete business day is the minimum auditable unit.  It
                # must never be accepted partially, even on an unusually busy
                # day.
                raise

        leaf_results: list[dict] = []

        def sync_split(window_start: date, window_end: date) -> None:
            try:
                leaf_results.append(_sync_unlocked(
                    db,
                    current_connection,
                    window_start,
                    window_end,
                    actor_user_id,
                    mark_current_sync=False,
                ))
            except DgteraResultLimitExceeded:
                if window_start >= window_end:
                    raise
                midpoint = window_start + timedelta(days=(window_end - window_start).days // 2)
                sync_split(window_start, midpoint)
                sync_split(midpoint + timedelta(days=1), window_end)

        midpoint = start_date + timedelta(days=(end_date - start_date).days // 2)
        sync_split(start_date, midpoint)
        sync_split(midpoint + timedelta(days=1), end_date)
        if mark_current_sync:
            current_connection.last_sync_at = utc_now()
            current_connection.last_error = None
            db.commit()
        return _merge_split_sync_results(start_date, end_date, leaf_results)

    try:
        current_connection = connection
        for attempt in range(2):
            try:
                return sync_attempt(current_connection)
            except OperationalError as exc:
                # A managed database may briefly recycle a connection.  Retry
                # the *whole* auditable range once after a clean rollback; do
                # not continue from a half-written transaction.
                if attempt or not _is_transient_operational_error(exc):
                    raise
                db.rollback()
                db.expire_all()
                refreshed = db.get(DgteraConnection, connection_id)
                if refreshed is None:
                    raise RuntimeError("DGTERA connection disappeared during database retry") from exc
                current_connection = refreshed
        raise RuntimeError("DGTERA synchronization retry loop ended unexpectedly")
    finally:
        _SYNC_LOCK.release()
