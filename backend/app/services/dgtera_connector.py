"""Read-only DGTERA/Odoo 14 sales connector.

Only POS sales included by DGTERA's Branch Sales report and their dimensions
are read, including open orders when the report's "include unclosed" option is
enabled. Cancelled orders are excluded. No accounting moves, inventory
movements or recipes are requested from DGTERA.

DGTERA's custom Branch Sales report applies its visible From/To dates directly
to the source ``pos.order.date_order`` value.  Odoo exposes that value over RPC
as a naive UTC string.  The report day must therefore remain the source date
(``00:00:00`` through ``23:59:59``) rather than a Riyadh-shifted window.  A
separate local timestamp is retained only for display and audit.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings


MONEY = Decimal("0.01")
QTY = Decimal("0.0001")
# DGTERA's attached "Branch Sales" report is explicitly filtered with
# "include unclosed orders".  Odoo 14 calls that POS state ``draft`` (New).
# Match the report by including every non-cancelled business state.
BRANCH_REPORT_ORDER_STATES = ("draft", "paid", "done", "invoiced")
DAY_START = time(0, 0, 0)
DAY_END = time(23, 59, 59)
BRANCH_REPORT_FINANCIAL_SOURCE = (
    "pos.order.line:price_subtotal+price_subtotal_incl"
)

DELIVERY_TOKENS = (
    "hungerstation", "hunger station", "هنقرستيشن", "هنقر ستيشن",
    "keeta", "كيتا", "jahez", "جاهز", "mrsool", "مرسول",
    "the chefz", "chefz", "ذا شفز", "toyou", "تويو", "ninja", "نينجا",
    "careem", "كريم", "noon", "نون", "delivery", "توصيل",
)
TAKEAWAY_TOKENS = ("takeaway", "take away", "take-away", "سفري", "استلام")
DINE_IN_TOKENS = ("dinein", "dine in", "dine-in", "محلي", "صالة", "table")
GENERIC_PAYMENT_TOKENS = (
    "cash", "card", "bank", "visa", "mastercard", "mada", "مدى", "نقد",
    "شبكة", "credit", "debit", "pos",
)
OPTIONAL_ORDER_FIELDS = (
    "config_id", "payment_ids", "table_id", "amount_return", "write_date",
    "order_type", "service_type", "delivery_type", "delivery_partner_id",
    "aggregator_id", "platform_id", "online_order_source", "order_source",
    "is_delivery", "is_takeaway", "takeaway", "customer_count",
)
CUSTOM_FIELD_HINTS = (
    "delivery", "aggregator", "platform", "order_type", "service_type",
    "takeaway", "dine", "table", "channel", "order_source",
)


class DgteraRemoteError(RuntimeError):
    """Safe remote error which never contains credentials or response bodies."""


class DgteraResultLimitExceeded(DgteraRemoteError):
    """A complete source window is too large for one safe in-memory read.

    The caller may split the date range and retry.  A single-day failure is
    still fatal so CORVAX never truncates a busy day silently.
    """

    def __init__(self, model: str, total: int, maximum: int):
        self.model = model
        self.total = int(total)
        self.maximum = int(maximum)
        super().__init__(
            f"DGTERA returned {self.total} {self.model} records; safety limit is "
            f"{self.maximum}. CORVAX splits multi-day windows automatically and "
            "rejects a single oversized business day."
        )


def money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def quantity(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY, rounding=ROUND_HALF_UP)


def validate_dgtera_url(value: str) -> str:
    raw = (value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("DGTERA URL must be an https URL without embedded credentials")
    host = parsed.hostname.lower().rstrip(".")
    allowed = settings.dgtera_hosts
    if not allowed or not any(
        host == rule.lstrip(".") or (rule.startswith(".") and host.endswith(rule))
        for rule in allowed
    ):
        raise ValueError("DGTERA host is not in DGTERA_ALLOWED_HOSTS")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    return urlunparse(("https", f"{host}{port}", path, "", "", ""))


def _many2one(value: object) -> tuple[str, str]:
    if isinstance(value, (list, tuple)) and value:
        return str(value[0]), str(value[1] if len(value) > 1 else value[0])
    if value not in (None, False, ""):
        return str(value), str(value)
    return "", ""


def _ids(value: object) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _odoo_source_local_datetime(value: object, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Return a DGTERA/Odoo UTC timestamp and its business-local value."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("DGTERA order has no date_order")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    ordered_utc = (
        parsed.astimezone(timezone.utc)
        if parsed.tzinfo is not None
        else parsed.replace(tzinfo=timezone.utc)
    )
    ordered_local = ordered_utc.astimezone(zone)
    return ordered_local, ordered_utc


def _safe_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    return str(value)


def _normal(value: object) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", " ", str(value or "").lower()).strip()


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    compact = text.replace(" ", "")
    return any(token in text or token.replace(" ", "") in compact for token in tokens)


def _display_value(value: object) -> str:
    _, display = _many2one(value)
    if display:
        return display
    if isinstance(value, bool):
        return "true" if value else ""
    return str(value or "").strip()


def classify_sale(
    *,
    partner_name: str,
    payment_method_names: list[str],
    optional_values: dict[str, object],
) -> tuple[str, str, str, str | None]:
    """Return scope, service mode, evidence label and source platform name."""
    evidence_parts = [partner_name, *payment_method_names]
    explicit_delivery_values: list[str] = []
    explicit_service_values: list[str] = []
    has_table = False
    for field_name, value in optional_values.items():
        key = field_name.lower()
        shown = _display_value(value)
        if "table" in key and value not in (None, False, "", [], ()):
            has_table = True
        if any(token in key for token in ("delivery", "aggregator", "platform")) and value not in (None, False, "", [], ()):
            explicit_delivery_values.append(shown or field_name)
        if any(token in key for token in ("order_type", "service_type", "takeaway", "dine", "channel", "order_source")):
            if value not in (None, False, "", [], ()):
                explicit_service_values.append(shown)
    evidence_parts.extend(explicit_delivery_values)
    evidence_parts.extend(explicit_service_values)
    evidence_text = _normal(" | ".join(part for part in evidence_parts if part))

    platform_name = next(
        (
            candidate.strip()
            for candidate in explicit_delivery_values
            if candidate and _normal(candidate) not in {"true", "1", "yes", "نعم", "delivery", "توصيل"}
        ),
        None,
    )
    for candidate in [partner_name, *payment_method_names]:
        normalized = _normal(candidate)
        if not platform_name and candidate and _contains_any(normalized, DELIVERY_TOKENS):
            platform_name = candidate.strip()
            break

    if explicit_delivery_values or _contains_any(evidence_text, DELIVERY_TOKENS):
        if not platform_name:
            platform_name = next(
                (name.strip() for name in payment_method_names
                 if name and not _contains_any(_normal(name), GENERIC_PAYMENT_TOKENS)),
                None,
            )
        return "EXTERNAL", "DELIVERY", "DGTERA_DELIVERY_EVIDENCE", platform_name
    if has_table or _contains_any(evidence_text, DINE_IN_TOKENS):
        return "INTERNAL", "DINE_IN", "DGTERA_TABLE_OR_SERVICE_TYPE", None
    if _contains_any(evidence_text, TAKEAWAY_TOKENS):
        return "INTERNAL", "TAKEAWAY", "DGTERA_SERVICE_TYPE", None
    # A final Odoo POS sale with no table and no delivery evidence is the
    # restaurant-counter/takeaway channel.  Keep the evidence label visible so
    # this deterministic fallback is never confused with an explicit source flag.
    return "INTERNAL", "TAKEAWAY", "DEFAULT_NON_DELIVERY_POS", None


class Odoo14Client:
    """Minimal JSON-RPC client. The API key is used as the Odoo password."""

    def __init__(self, *, base_url: str, database: str, login: str, api_key: str):
        self.base_url = validate_dgtera_url(base_url)
        self.database = database
        self.login = login
        self.api_key = api_key
        self.uid: int | None = None
        self._rpc_id = 0
        self._field_cache: dict[str, dict[str, dict[str, object]]] = {}

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/jsonrpc"

    def _call(self, service: str, method: str, args: list[object]) -> Any:
        self._rpc_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": self._rpc_id,
        }
        try:
            with httpx.Client(
                timeout=settings.dgtera_request_timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": "CORVAX-DGTERA-Sales/2.0"},
            ) as client:
                response = client.post(self.endpoint, json=request)
            if response.is_redirect:
                raise DgteraRemoteError("DGTERA unexpectedly redirected the API request")
            response.raise_for_status()
            payload = response.json()
        except DgteraRemoteError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise DgteraRemoteError(f"DGTERA API is unavailable ({type(exc).__name__})") from exc
        if payload.get("error"):
            data = payload["error"].get("data") or {}
            label = data.get("name") or payload["error"].get("message") or "RemoteError"
            raise DgteraRemoteError(f"DGTERA rejected the API request ({label})")
        return payload.get("result")

    def authenticate(self) -> int:
        uid = self._call("common", "authenticate", [self.database, self.login, self.api_key, {}])
        if not uid:
            raise DgteraRemoteError("DGTERA authentication failed")
        self.uid = int(uid)
        return self.uid

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
    ) -> Any:
        if self.uid is None:
            self.authenticate()
        return self._call(
            "object",
            "execute_kw",
            [self.database, self.uid, self.api_key, model, method, args or [], kwargs or {}],
        )

    def fields(self, model: str) -> dict[str, dict[str, object]]:
        if model not in self._field_cache:
            result = self.execute_kw(model, "fields_get", [], {"attributes": ["type", "relation", "string"]})
            self._field_cache[model] = result or {}
        return self._field_cache[model]

    def _available(self, model: str, requested: Iterable[str]) -> list[str]:
        available = self.fields(model)
        return [field for field in dict.fromkeys(requested) if field in available]

    def _search_read_all(
        self,
        model: str,
        domain: list[object],
        fields: list[str],
        *,
        order: str = "id",
        maximum: int,
    ) -> list[dict[str, object]]:
        total = int(self.execute_kw(model, "search_count", [domain]) or 0)
        if total > maximum:
            raise DgteraResultLimitExceeded(model, total, maximum)
        rows: list[dict[str, object]] = []
        # Some DGTERA installations impose a lower server-side page cap than
        # the requested limit (300 has been observed in production).  Offset
        # pagination is not reliable in that setup: the first page is returned
        # but a later offset can be empty even while search_count still proves
        # that unread records remain.  Walk the immutable Odoo primary key
        # instead.  This also avoids skips/duplicates if records are written
        # while a busy business day is being read.
        last_id = 0
        seen_ids: set[int] = set()
        page_size = min(500, maximum)
        requested_fields = list(dict.fromkeys(["id", *fields]))
        while len(rows) < total:
            remaining = total - len(rows)
            page = self.execute_kw(
                model,
                "search_read",
                [[*domain, ("id", ">", last_id)]],
                {
                    "fields": requested_fields,
                    "order": "id",
                    "offset": 0,
                    "limit": min(page_size, remaining),
                },
            ) or []
            if not page:
                break
            page_ids: list[int] = []
            for row in page:
                try:
                    row_id = int(row["id"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise DgteraRemoteError(
                        f"DGTERA {model} returned a record without a valid id"
                    ) from exc
                if row_id <= last_id or row_id in seen_ids:
                    raise DgteraRemoteError(
                        f"DGTERA {model} pagination did not advance safely"
                    )
                seen_ids.add(row_id)
                page_ids.append(row_id)
            rows.extend(page)
            last_id = page_ids[-1]
        if len(rows) != total:
            raise DgteraRemoteError(
                f"DGTERA {model} pagination stopped after {len(rows)} of {total} records"
            )
        return rows

    def test_connection(self) -> dict[str, object]:
        self.authenticate()
        count = self.execute_kw("pos.order", "search_count", [[("state", "in", list(BRANCH_REPORT_ORDER_STATES))]])
        return {"connected": True, "branch_report_sales_orders": int(count or 0), "odoo_version": "14", "mode": "SALES_ONLY"}

    def changed_sales_dates(
        self,
        since_utc: datetime,
        history_start: date,
        timezone_name: str,
    ) -> list[date]:
        """Return every business date touched since the last poll.

        This query intentionally has no state filter so a newly cancelled old
        order still causes its original sales day to be reread and cleaned.
        """
        zone = ZoneInfo(timezone_name)
        since = since_utc.astimezone(timezone.utc) if since_utc.tzinfo else since_utc.replace(tzinfo=timezone.utc)
        history_start_source = datetime.combine(history_start, DAY_START)
        today = datetime.now(timezone.utc).astimezone(zone).date()
        today_end_source = datetime.combine(today, DAY_END)
        rows = self._search_read_all(
            "pos.order",
            [
                ("write_date", ">=", since.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")),
                ("date_order", ">=", history_start_source.strftime("%Y-%m-%d %H:%M:%S")),
                ("date_order", "<=", today_end_source.strftime("%Y-%m-%d %H:%M:%S")),
            ],
            self._available("pos.order", ["id", "date_order", "write_date", "state"]),
            order="write_date,id",
            maximum=settings.dgtera_max_orders_per_sync,
        )
        result = set()
        for row in rows:
            _, ordered_utc = _odoo_source_local_datetime(row.get("date_order"), zone)
            report_date = ordered_utc.date()
            if history_start <= report_date <= today:
                result.add(report_date)
        return sorted(result)

    def daily_sales(self, start_date: date, end_date: date, timezone_name: str) -> list[dict[str, object]]:
        if end_date < start_date:
            raise ValueError("end_date must not be before start_date")
        if (end_date - start_date).days > 31:
            raise ValueError("A DGTERA sales window cannot exceed 32 days")
        zone = ZoneInfo(timezone_name)
        # Match DGTERA's custom Branch Sales report literally: its From/To
        # values are applied to the naive source date_order field without a
        # Riyadh boundary shift.
        start_source = datetime.combine(start_date, DAY_START)
        end_source = datetime.combine(end_date, DAY_END)
        domain = [
            ("state", "in", list(BRANCH_REPORT_ORDER_STATES)),
            ("date_order", ">=", start_source.strftime("%Y-%m-%d %H:%M:%S")),
            ("date_order", "<=", end_source.strftime("%Y-%m-%d %H:%M:%S")),
        ]

        order_field_meta = self.fields("pos.order")
        custom_fields = [
            name for name in order_field_meta
            if name.startswith("x_") and any(hint in name.lower() for hint in CUSTOM_FIELD_HINTS)
        ][:30]
        order_fields = self._available(
            "pos.order",
            [
                "id", "name", "pos_reference", "date_order", "state", "session_id",
                "partner_id", "lines", "amount_untaxed", "amount_tax", "amount_total",
                "amount_paid", *OPTIONAL_ORDER_FIELDS, *custom_fields,
            ],
        )
        orders = self._search_read_all(
            "pos.order", domain, order_fields, order="date_order,id",
            maximum=settings.dgtera_max_orders_per_sync,
        )
        # Enforce the source-report date again after reading.  The Riyadh value
        # is display metadata only and must not decide which DGTERA report day
        # owns the sale.
        filtered_orders = []
        for row in orders:
            ordered_local, ordered_utc = _odoo_source_local_datetime(row.get("date_order"), zone)
            report_date = ordered_utc.date()
            if not (start_date <= report_date <= end_date):
                continue
            report_time = ordered_utc.time().replace(tzinfo=None)
            if report_time < DAY_START or report_time > DAY_END:
                continue
            row["_ordered_utc"] = ordered_utc
            row["_ordered_local"] = ordered_local
            row["_report_date"] = report_date
            filtered_orders.append(row)
        orders = filtered_orders
        if not orders:
            return []

        order_ids = [int(row["id"]) for row in orders]
        session_ids = sorted({int(_many2one(row.get("session_id"))[0]) for row in orders if _many2one(row.get("session_id"))[0]})
        sessions = self._search_read_all(
            "pos.session", [("id", "in", session_ids)],
            self._available("pos.session", ["id", "name", "config_id", "write_date"]),
            maximum=max(len(session_ids), 1),
        ) if session_ids else []
        session_by_id = {str(row["id"]): row for row in sessions}

        line_fields = self._available(
            "pos.order.line",
            ["id", "order_id", "product_id", "full_product_name", "name", "qty", "price_unit",
             "discount", "price_subtotal", "price_subtotal_incl", "tax_ids", "write_date"],
        )
        lines = self._search_read_all(
            "pos.order.line", [("order_id", "in", order_ids)], line_fields,
            maximum=settings.dgtera_max_order_lines_per_sync,
        )
        lines_by_order: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in lines:
            order_id, _ = _many2one(row.get("order_id"))
            if order_id:
                lines_by_order[order_id].append(row)

        product_ids = sorted({int(_many2one(row.get("product_id"))[0]) for row in lines if _many2one(row.get("product_id"))[0]})
        product_rows = self._search_read_all(
            "product.product", [("id", "in", product_ids)],
            self._available(
                "product.product",
                ["id", "default_code", "barcode", "display_name", "name", "categ_id",
                 "lst_price", "list_price", "active", "write_date"],
            ),
            maximum=max(len(product_ids), 1),
        ) if product_ids else []
        product_by_id = {str(row["id"]): row for row in product_rows}

        partner_ids = sorted({int(_many2one(row.get("partner_id"))[0]) for row in orders if _many2one(row.get("partner_id"))[0]})
        partner_rows = self._search_read_all(
            "res.partner", [("id", "in", partner_ids)],
            self._available("res.partner", ["id", "name", "ref", "active", "write_date"]),
            maximum=max(len(partner_ids), 1),
        ) if partner_ids else []
        partner_by_id = {str(row["id"]): row for row in partner_rows}

        payment_fields_available = self.fields("pos.payment")
        payments: list[dict[str, object]] = []
        if {"pos_order_id", "payment_method_id", "amount"}.issubset(payment_fields_available):
            payments = self._search_read_all(
                "pos.payment", [("pos_order_id", "in", order_ids)],
                self._available("pos.payment", ["id", "pos_order_id", "payment_method_id", "amount", "payment_date", "write_date"]),
                maximum=settings.dgtera_max_payments_per_sync,
            )
        payments_by_order: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in payments:
            order_id, _ = _many2one(row.get("pos_order_id"))
            if order_id:
                payments_by_order[order_id].append(row)
        payment_method_ids = sorted({
            int(_many2one(row.get("payment_method_id"))[0])
            for row in payments if _many2one(row.get("payment_method_id"))[0]
        })
        method_rows = self._search_read_all(
            "pos.payment.method", [("id", "in", payment_method_ids)],
            self._available("pos.payment.method", ["id", "name"]),
            maximum=max(len(payment_method_ids), 1),
        ) if payment_method_ids else []
        method_by_id = {str(row["id"]): row for row in method_rows}

        result: list[dict[str, object]] = []
        for order in orders:
            order_id = str(order["id"])
            session_id, session_display = _many2one(order.get("session_id"))
            session = session_by_id.get(session_id, {})
            config_id, config_name = _many2one(order.get("config_id"))
            if not config_id:
                config_id, config_name = _many2one(session.get("config_id"))
            if not config_id:
                config_id, config_name = "UNASSIGNED", "DGTERA POS"

            partner_id, partner_display = _many2one(order.get("partner_id"))
            partner = partner_by_id.get(partner_id, {})
            partner_name = str(partner.get("name") or partner_display or "").strip()

            canonical_payments = []
            payment_method_names = []
            for payment in payments_by_order.get(order_id, []):
                method_id, method_display = _many2one(payment.get("payment_method_id"))
                method_name = str(method_by_id.get(method_id, {}).get("name") or method_display or "DGTERA payment")
                payment_method_names.append(method_name)
                canonical_payments.append({
                    "payment_id": str(payment["id"]),
                    "method_id": method_id,
                    "method_name": method_name,
                    "amount": format(money(payment.get("amount")), "f"),
                })

            optional_values = {
                field: _safe_value(order.get(field))
                for field in [*OPTIONAL_ORDER_FIELDS, *custom_fields]
                if field in order and order.get(field) not in (None, False, "", [], ())
            }
            scope, service_mode, classification_source, platform_name = classify_sale(
                partner_name=partner_name,
                payment_method_names=payment_method_names,
                optional_values=optional_values,
            )

            canonical_lines = []
            discount_amount = Decimal("0.00")
            for line in lines_by_order.get(order_id, []):
                product_id, product_display = _many2one(line.get("product_id"))
                if not product_id:
                    raise DgteraRemoteError(f"DGTERA POS line {line.get('id')} has no product")
                product = product_by_id.get(product_id, {})
                category_id, category_name = _many2one(product.get("categ_id"))
                # ``full_product_name`` is a line label and may contain combo,
                # size or attribute text.  It must not overwrite the shared
                # product master because the same product can legitimately
                # have a different line label on another order/day.
                product_name = str(
                    product.get("display_name") or product.get("name")
                    or product_display or product_id
                )
                line_product_name = str(
                    line.get("full_product_name") or line.get("name")
                    or product_name
                )
                qty = quantity(line.get("qty"))
                unit_price = Decimal(str(line.get("price_unit") or 0)).quantize(QTY, rounding=ROUND_HALF_UP)
                discount = Decimal(str(line.get("discount") or 0)).quantize(QTY, rounding=ROUND_HALF_UP)
                subtotal = money(line.get("price_subtotal"))
                total = money(line.get("price_subtotal_incl"))
                discount_amount = money(discount_amount + money(unit_price * qty * discount / Decimal("100")))
                canonical_lines.append({
                    "line_id": str(line["id"]),
                    "product": {
                        "product_id": product_id,
                        "code": str(product.get("default_code") or f"DGT-P-{product_id}"),
                        "barcode": str(product.get("barcode") or "") or None,
                        "name": product_name,
                        "category_id": category_id or None,
                        "category_name": category_name or None,
                        "list_price": format(money(product.get("lst_price") or product.get("list_price")), "f"),
                        "active": bool(product.get("active", True)),
                        "source_updated_at": product.get("write_date") or None,
                    },
                    "line_product_name": line_product_name,
                    "quantity": format(qty, "f"),
                    "unit_price": format(unit_price, "f"),
                    "discount_percent": format(discount, "f"),
                    "subtotal": format(subtotal, "f"),
                    "vat_amount": format(money(total - subtotal), "f"),
                    "total": format(total, "f"),
                    "tax_ids": [str(value) for value in _ids(line.get("tax_ids"))],
                })

            # DGTERA's Branch Sales report is a POS-line report (quantity,
            # sales before tax, tax and sales including tax).  Derive the
            # canonical financial values from the exact line fields used by
            # that report instead of trusting a possibly stale order header.
            # The original header remains in source_metadata as an audit
            # witness; it is never used for displayed sales.
            header_total = money(order.get("amount_total"))
            header_tax = money(order.get("amount_tax"))
            header_untaxed = money(order.get("amount_untaxed"))
            if "amount_untaxed" not in order:
                header_untaxed = money(header_total - header_tax)
            amount_untaxed = money(sum(
                (money(line["subtotal"]) for line in canonical_lines), Decimal("0")
            ))
            amount_total = money(sum(
                (money(line["total"]) for line in canonical_lines), Decimal("0")
            ))
            amount_tax = money(amount_total - amount_untaxed)
            ordered_utc = order["_ordered_utc"]
            ordered_local = order["_ordered_local"]
            customer = None
            if partner_id:
                customer = {
                    "partner_id": partner_id,
                    "code": str(partner.get("ref") or f"DGT-C-{partner_id}"),
                    "name": partner_name or f"DGTERA customer {partner_id}",
                    "active": bool(partner.get("active", True)),
                    "source_updated_at": partner.get("write_date") or None,
                }
            canonical = {
                "order_id": order_id,
                "order_name": str(order.get("name") or order_id),
                "pos_reference": str(order.get("pos_reference") or "") or None,
                "state": str(order.get("state") or ""),
                "date_order_utc": ordered_utc.replace(tzinfo=None).isoformat(sep=" "),
                "date_order_local": ordered_local.replace(tzinfo=None).isoformat(sep=" "),
                "sales_date": order["_report_date"].isoformat(),
                "session_id": session_id or None,
                "session_name": str(session.get("name") or session_display or "") or None,
                "branch": {"config_id": config_id, "config_name": config_name},
                "customer": customer,
                "sales_scope": scope,
                "service_mode": service_mode,
                "classification_source": classification_source,
                "delivery_platform_name": platform_name,
                "subtotal": format(amount_untaxed, "f"),
                "vat_amount": format(amount_tax, "f"),
                "total": format(amount_total, "f"),
                "amount_paid": format(money(order.get("amount_paid")), "f"),
                "amount_return": format(money(order.get("amount_return")), "f"),
                "discount_amount": format(discount_amount, "f"),
                "line_total_difference": format(money(amount_total - header_total), "f"),
                "lines": canonical_lines,
                "payments": sorted(canonical_payments, key=lambda item: item["payment_id"]),
                "source_metadata": {
                    **optional_values,
                    "corvax_financial_source": BRANCH_REPORT_FINANCIAL_SOURCE,
                    "odoo_order_header": {
                        "subtotal": format(header_untaxed, "f"),
                        "vat_amount": format(header_tax, "f"),
                        "total": format(header_total, "f"),
                    },
                },
                "source_updated_at": order.get("write_date") or None,
            }
            canonical_json = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            canonical["source_hash"] = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
            result.append(canonical)
        return sorted(result, key=lambda row: (str(row["date_order_local"]), str(row["order_id"])))
