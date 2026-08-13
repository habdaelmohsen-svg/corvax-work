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
from sqlalchemy.orm import Session

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
from app.services.dgtera_connector import DgteraRemoteError, Odoo14Client, money, quantity


_SYNC_LOCK = Lock()
HISTORY_START_DATE = date(2025, 1, 1)
HISTORY_CHUNK_DAYS = 7
SOURCE_LOCAL_WINDOW_MARKER = "source-local-v2"


class DgteraSyncBusy(RuntimeError):
    pass


def client_for(connection: DgteraConnection) -> Odoo14Client:
    return Odoo14Client(
        base_url=connection.base_url,
        database=str(connection.database_name),
        login=str(connection.login),
        api_key=str(connection.api_key),
    )


def _window_label(connection: DgteraConnection) -> str:
    return f"00:01-23:59 {connection.timezone} / {SOURCE_LOCAL_WINDOW_MARKER}"


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


def _upsert_branch(db: Session, connection: DgteraConnection, source: dict) -> DgteraBranch:
    external_id = str(source["config_id"])
    name = str(source.get("config_name") or f"DGTERA branch {external_id}")[:250]
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
    else:
        branch = db.get(Branch, row.branch_id)
        if branch:
            branch.name_ar = name[:200]
            branch.name_en = name[:200]
            branch.active = True
        row.name = name
        row.active = True
    db.flush()
    return row


def _upsert_product(db: Session, connection: DgteraConnection, source: dict) -> DgteraProduct:
    external_id = str(source["product_id"])
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
    row.code = str(source.get("code") or row.code)[:80]
    row.barcode = (str(source.get("barcode"))[:120] if source.get("barcode") else None)
    row.name = str(source.get("name") or row.name)[:300]
    row.external_category_id = (str(source.get("category_id"))[:80] if source.get("category_id") else None)
    row.category_name = (str(source.get("category_name"))[:250] if source.get("category_name") else None)
    row.list_price = money(source.get("list_price"))
    row.active = bool(source.get("active", True))
    row.source_updated_at = _source_datetime(source.get("source_updated_at"))
    db.flush()
    return row


def _upsert_customer(
    db: Session,
    connection: DgteraConnection,
    source: dict | None,
    *,
    is_platform: bool,
) -> DgteraCustomer | None:
    if not source:
        return None
    external_id = str(source["partner_id"])
    name = str(source.get("name") or f"DGTERA customer {external_id}")[:300]
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
    db.flush()
    return row


def _upsert_platform(db: Session, connection: DgteraConnection, name: str | None) -> DeliveryPlatform | None:
    clean_name = str(name or "").strip()
    if not clean_name:
        return None
    normalized = _normalized_name(clean_name)
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
    return platform


def _apply_order(db: Session, connection: DgteraConnection, source: dict) -> str:
    branch_source = source["branch"]
    dgtera_branch = _upsert_branch(db, connection, branch_source)
    customer_source = source.get("customer")
    platform_name = str(source.get("delivery_platform_name") or "")
    is_platform = bool(
        customer_source
        and platform_name
        and _normalized_name(str(customer_source.get("name") or "")) == _normalized_name(platform_name)
    )
    customer = _upsert_customer(db, connection, customer_source, is_platform=is_platform)
    platform = _upsert_platform(db, connection, source.get("delivery_platform_name"))
    external_id = str(source["order_id"])
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
    else:
        db.execute(delete(DgteraSalesOrderLine).where(DgteraSalesOrderLine.order_id == order.id))
        db.execute(delete(DgteraSalesPayment).where(DgteraSalesPayment.order_id == order.id))

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
        product = _upsert_product(db, connection, line_source["product"])
        db.add(DgteraSalesOrderLine(
            order_id=order.id,
            external_line_id=str(line_source["line_id"])[:80],
            product_id=product.id,
            product_name=str(line_source["product"]["name"])[:300],
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


def historical_backfill_status(db: Session, connection: DgteraConnection) -> dict:
    """Return progress for the contiguous source-local history import.

    Runs created before the source-local date correction are intentionally not
    counted.  Re-reading those dates updates their existing order ids and
    moves each order to the same business date used by DGTERA's branch report.
    """
    zone = ZoneInfo(connection.timezone or "Asia/Riyadh")
    today = utc_now_aware().astimezone(zone).date()
    earliest = db.scalar(select(func.min(DgteraSyncRun.start_date)).where(
        DgteraSyncRun.connection_id == connection.id,
        DgteraSyncRun.status == "COMPLETED",
        DgteraSyncRun.window_label.like(f"%{SOURCE_LOCAL_WINDOW_MARKER}%"),
    ))
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
    return elapsed >= timedelta(minutes=max(1, connection.sync_interval_minutes or 5))


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

    run = DgteraSyncRun(
        connection_id=connection.id,
        company_id=connection.company_id,
        start_date=start_date,
        end_date=end_date,
        window_label=_window_label(connection),
        status="RUNNING",
        source_orders=len(source_orders),
        source_total=money(sum((money(row.get("total")) for row in source_orders), Decimal("0"))),
    )
    db.add(run)
    db.flush()
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
            counts[_apply_order(db, connection, source)] += 1
        run.inserted_orders = counts["INSERTED"]
        run.updated_orders = counts["UPDATED"]
        run.unchanged_orders = counts["UNCHANGED"]
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
                "mode": "SALES_ONLY",
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        connection = db.get(DgteraConnection, connection.id)
        if connection:
            connection.last_error = f"Sales mirror failed ({type(exc).__name__})"
        failed = DgteraSyncRun(
            connection_id=connection.id if connection else run.connection_id,
            company_id=connection.company_id if connection else run.company_id,
            start_date=start_date,
            end_date=end_date,
            window_label=(
                _window_label(connection)
                if connection else f"00:01-23:59 Asia/Riyadh / {SOURCE_LOCAL_WINDOW_MARKER}"
            ),
            status="ERROR",
            source_orders=len(source_orders),
            source_total=money(sum((money(row.get("total")) for row in source_orders), Decimal("0"))),
            error_message=f"{type(exc).__name__}: {str(exc)[:900]}",
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
    try:
        return _sync_unlocked(
            db,
            connection,
            start_date,
            end_date,
            actor_user_id,
            mark_current_sync=mark_current_sync,
        )
    finally:
        _SYNC_LOCK.release()
