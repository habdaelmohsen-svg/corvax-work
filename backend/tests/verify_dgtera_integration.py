"""Acceptance gate for the automatic DGTERA sales-only mirror."""
from __future__ import annotations

import os
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp") / f"corvax_dgtera_{os.getpid()}.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SECRET_KEY": "dgtera-acceptance-secret-key-2026",
        "ENVIRONMENT": "testing",
        "SEED_DEMO_DATA": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
        "ENABLE_RATE_LIMIT_TESTING": "true",
        "DGTERA_SCHEDULER_ENABLED": "false",
        "DGTERA_ALLOWED_HOSTS": "cheesehouse.dgtera.com",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account,
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
    FiscalPeriod,
    FiscalYear,
    JournalEntry,
    Party,
)
from app.services.dgtera_connector import (  # noqa: E402
    BRANCH_REPORT_FINANCIAL_SOURCE,
    BRANCH_REPORT_ORDER_STATES,
    DAY_END,
    DAY_START,
    DgteraRemoteError,
    DgteraResultLimitExceeded,
    Odoo14Client,
    classify_sale,
    validate_dgtera_url,
)
from app.services.dgtera_sales_sync import (  # noqa: E402
    DgteraReconciliationError,
    HISTORY_CHUNK_DAYS,
    SOURCE_LOCAL_WINDOW_MARKER,
    _decode_source_payload,
    _encode_source_payload,
    _is_transient_operational_error,
    historical_backfill_status,
    historical_backfill_window,
    sync_connection,
)
from app.workers.dgtera_daily_sync import (  # noqa: E402
    CHANGED_DAYS_PER_CYCLE,
    HISTORY_CHUNKS_PER_CYCLE,
    _date_windows,
)
import app.workers.dgtera_daily_sync as daily_worker  # noqa: E402


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def verify_scheduler_queue_serialization() -> None:
    """One poll may drain several independently committed historical days."""
    current_day = date(2026, 8, 15)
    history_days = [current_day - timedelta(days=value) for value in (1, 2, 3)]
    connection = SimpleNamespace(id=77, created_by=1, last_sync_at=None)

    class ScalarRows:
        def all(self):
            return [connection.id]

    class DiscoveryDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalars(self, _query):
            return ScalarRows()

    class WorkDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _model, object_id):
            return connection if object_id == connection.id else None

    session_factory = MagicMock(side_effect=[DiscoveryDb(), WorkDb()])
    sync = MagicMock(return_value={"strict_reconciled": True})
    changed = MagicMock(return_value=[current_day - timedelta(days=2)])
    audit = MagicMock(return_value=(current_day - timedelta(days=3), current_day - timedelta(days=3)))
    with (
        patch.object(daily_worker, "SessionLocal", session_factory),
        patch.object(daily_worker, "connection_is_due", return_value=True),
        patch.object(daily_worker, "catchup_window", return_value=(current_day, current_day)),
        patch.object(daily_worker, "sync_connection", sync),
        patch.object(daily_worker, "historical_backfill_window", side_effect=[
            *((value, value) for value in history_days), None,
        ]),
        patch.object(daily_worker, "changed_historical_sales_dates", changed),
        patch.object(daily_worker, "historical_recheck_window", audit),
    ):
        daily_worker.run_due_syncs()
    assert sync.call_count == 4
    assert sync.call_args_list[0].args[1:] == (connection, current_day, current_day, 1)
    assert sync.call_args_list[0].kwargs == {}
    for index, history_day in enumerate(history_days, start=1):
        assert sync.call_args_list[index].args[1:] == (connection, history_day, history_day, 1)
        assert sync.call_args_list[index].kwargs == {"mark_current_sync": False}
    changed.assert_not_called()
    audit.assert_not_called()

    # Once backfill is complete, changed-date discovery is also capped at one
    # independently committed day and the rolling audit remains deferred.
    work_db = WorkDb()
    session_factory = MagicMock(side_effect=[DiscoveryDb(), work_db])
    sync = MagicMock(return_value={"strict_reconciled": True})
    changed_days = [current_day - timedelta(days=3), current_day - timedelta(days=2)]
    audit = MagicMock(return_value=(current_day - timedelta(days=4), current_day - timedelta(days=4)))
    with (
        patch.object(daily_worker, "SessionLocal", session_factory),
        patch.object(daily_worker, "connection_is_due", return_value=True),
        patch.object(daily_worker, "catchup_window", return_value=(current_day, current_day)),
        patch.object(daily_worker, "sync_connection", sync),
        patch.object(daily_worker, "historical_backfill_window", return_value=None),
        patch.object(daily_worker, "changed_historical_sales_dates", return_value=changed_days),
        patch.object(daily_worker, "historical_recheck_window", audit),
    ):
        daily_worker.run_due_syncs()
    assert sync.call_count == 2
    assert sync.call_args_list[0].args[2:4] == (current_day, current_day)
    assert sync.call_args_list[1].args[2:4] == (changed_days[0], changed_days[0])
    assert sync.call_args_list[1].kwargs == {"mark_current_sync": False}
    audit.assert_not_called()


class FakeClient:
    def __init__(self, source: dict | list[dict], sales_date: date):
        self.source = source
        self.sales_date = sales_date

    def test_connection(self):
        return {"connected": True, "final_sales_orders": 1, "odoo_version": "14", "mode": "SALES_ONLY"}

    def daily_sales(self, start_date, end_date, timezone_name):
        assert timezone_name == "Asia/Riyadh"
        rows = self.source if isinstance(self.source, list) else [self.source]
        return rows if start_date <= self.sales_date <= end_date else []


class StubOdooClient(Odoo14Client):
    """Exercise the real daily_sales transformation without network access."""

    def __init__(self, sales_date: date):
        self.sales_date = sales_date
        self.models_read: list[str] = []
        self.order_domains: list[list] = []
        self._field_cache = {}

    def fields(self, model: str):
        fields = {
            "pos.order": {
                name: {} for name in (
                    "id", "name", "pos_reference", "date_order", "state", "session_id", "partner_id",
                    "lines", "amount_untaxed", "amount_tax", "amount_total", "amount_paid",
                    "config_id", "payment_ids", "table_id", "amount_return", "write_date",
                )
            },
            "pos.session": {name: {} for name in ("id", "name", "config_id", "write_date")},
            "pos.order.line": {
                name: {} for name in (
                    "id", "order_id", "product_id", "full_product_name", "qty", "price_unit",
                    "discount", "price_subtotal", "price_subtotal_incl", "tax_ids", "write_date",
                )
            },
            "product.product": {
                name: {} for name in (
                    "id", "default_code", "barcode", "display_name", "categ_id", "lst_price", "active", "write_date",
                )
            },
            "res.partner": {name: {} for name in ("id", "name", "ref", "active", "write_date")},
            "pos.payment": {name: {} for name in ("id", "pos_order_id", "payment_method_id", "amount", "payment_date", "write_date")},
            "pos.payment.method": {name: {} for name in ("id", "name")},
        }
        return fields[model]

    def _search_read_all(self, model, domain, fields, *, order="id", maximum):
        self.models_read.append(model)
        if model == "pos.order":
            self.order_domains.append(domain)
        d = self.sales_date
        previous_day = d - timedelta(days=1)
        next_day = d + timedelta(days=1)
        orders = [
            {
                "id": 1, "name": "EXCLUDED-PREVIOUS", "pos_reference": "EXCLUDED-PREVIOUS",
                "date_order": f"{previous_day.isoformat()} 23:59:59", "state": "done",
                "session_id": [501, "S501"], "partner_id": False, "lines": [101],
                "amount_untaxed": 10, "amount_tax": 1.5, "amount_total": 11.5, "amount_paid": 11.5,
            },
            {
                "id": 2, "name": "INCLUDED-0000", "pos_reference": "INCLUDED-0000",
                "date_order": f"{d.isoformat()} 00:00:00", "state": "draft",
                "session_id": [501, "S501"], "partner_id": False, "lines": [102],
                "amount_untaxed": 20, "amount_tax": 3, "amount_total": 23, "amount_paid": 23,
            },
            {
                "id": 3, "name": "INCLUDED-2359", "pos_reference": "INCLUDED-2359",
                "date_order": f"{d.isoformat()} 23:59:59", "state": "done",
                "session_id": [501, "S501"], "partner_id": [301, "Keeta"], "lines": [103],
                "amount_untaxed": 30, "amount_tax": 4.5, "amount_total": 34.5, "amount_paid": 34.5,
            },
            {
                "id": 4, "name": "EXCLUDED-NEXT", "pos_reference": "EXCLUDED-NEXT",
                "date_order": f"{next_day.isoformat()} 00:00:00", "state": "done",
                "session_id": [501, "S501"], "partner_id": False, "lines": [104],
                "amount_untaxed": 40, "amount_tax": 6, "amount_total": 46, "amount_paid": 46,
            },
        ]
        if model == "pos.order":
            return orders
        if model == "pos.session":
            return [{"id": 501, "name": "S501", "config_id": [701, "Al Aziziyah"]}]
        if model == "pos.order.line":
            result = []
            for order_row in orders:
                # Open orders can have a stale header while the Branch Sales
                # line view already reflects the current sale.  CORVAX must
                # use the report-line values, never the stale header.
                total = 22 if order_row["id"] == 2 else order_row["amount_total"]
                subtotal = 19 if order_row["id"] == 2 else order_row["amount_untaxed"]
                result.append({
                    "id": 100 + order_row["id"], "order_id": [order_row["id"], order_row["name"]],
                    "product_id": [2001, "Burger"], "full_product_name": "Burger / Large", "qty": 1,
                    "price_unit": total, "discount": 0, "price_subtotal": subtotal,
                    "price_subtotal_incl": total, "tax_ids": [15],
                })
            return result
        if model == "product.product":
            return [{"id": 2001, "default_code": "BURGER", "display_name": "Burger", "categ_id": [90, "Food"], "lst_price": 34.5, "active": True}]
        if model == "res.partner":
            return [{"id": 301, "name": "Keeta", "ref": "KEETA", "active": True}]
        if model == "pos.payment":
            return [
                {"id": 601, "pos_order_id": [2, "INCLUDED-0001"], "payment_method_id": [41, "Cash"], "amount": 23},
                {"id": 602, "pos_order_id": [3, "INCLUDED-2359"], "payment_method_id": [42, "Keeta"], "amount": 34.5},
            ]
        if model == "pos.payment.method":
            return [{"id": 41, "name": "Cash"}, {"id": 42, "name": "Keeta"}]
        raise AssertionError(model)


def verify_server_capped_keyset_pagination() -> None:
    """Read every row when DGTERA silently caps each response at 300."""

    class ServerCappedClient(Odoo14Client):
        def __init__(self, *, stop_after_first_page: bool = False):
            self.uid = 1
            self.stop_after_first_page = stop_after_first_page
            self.calls: list[dict] = []

        def execute_kw(self, model, method, args=None, kwargs=None):
            assert model == "pos.order"
            if method == "search_count":
                return 750
            assert method == "search_read"
            kwargs = kwargs or {}
            self.calls.append(kwargs)
            domain = (args or [[]])[0]
            cursor = next(
                int(condition[2])
                for condition in domain
                if isinstance(condition, tuple) and condition[:2] == ("id", ">")
            )
            if self.stop_after_first_page and cursor >= 300:
                return []
            # Reproduce DGTERA's observed behaviour: it returns no more than
            # 300 records even when CORVAX requests a larger page.
            server_limit = min(int(kwargs.get("limit") or 0), 300)
            return [
                {"id": row_id, "name": f"ORDER-{row_id:04d}"}
                for row_id in range(cursor + 1, min(cursor + server_limit, 750) + 1)
            ]

    client = ServerCappedClient()
    rows = client._search_read_all(
        "pos.order", [("state", "!=", "cancel")], ["id", "name"],
        order="date_order,id", maximum=10000,
    )
    assert len(rows) == 750
    assert [row["id"] for row in rows] == list(range(1, 751))
    assert len(client.calls) == 3
    assert all(call["offset"] == 0 and call["order"] == "id" for call in client.calls)

    stopped = ServerCappedClient(stop_after_first_page=True)
    try:
        stopped._search_read_all(
            "pos.order", [], ["id"], order="id", maximum=10000,
        )
    except DgteraRemoteError as exc:
        assert "stopped after 300 of 750 records" in str(exc)
    else:
        raise AssertionError("an incomplete DGTERA page sequence was accepted")


def verify_real_connector_window(sales_date: date) -> None:
    # DGTERA's custom Branch Sales report applies 00:00:00..23:59:59 to
    # date_order as exposed by the source. Do not shift that report window by
    # three hours merely because the display timestamp is shown in Riyadh.
    stub = StubOdooClient(sales_date)
    rows = stub.daily_sales(sales_date, sales_date, "Asia/Riyadh")
    assert [row["order_id"] for row in rows] == ["2", "3"]
    assert rows[0]["date_order_utc"].endswith("00:00:00")
    assert rows[1]["date_order_utc"].endswith("23:59:59")
    assert rows[0]["date_order_local"].endswith("03:00:00")
    assert rows[1]["date_order_local"].startswith((sales_date + timedelta(days=1)).isoformat())
    assert rows[1]["date_order_local"].endswith("02:59:59")
    assert {row["sales_date"] for row in rows} == {sales_date.isoformat()}
    assert rows[0]["service_mode"] == "TAKEAWAY"
    assert rows[0]["state"] == "draft"
    assert rows[0]["source_metadata"]["corvax_financial_source"] == BRANCH_REPORT_FINANCIAL_SOURCE
    assert rows[0]["total"] == "22.00" and rows[0]["vat_amount"] == "3.00"
    assert rows[0]["line_total_difference"] == "-1.00"
    assert rows[0]["source_metadata"]["odoo_order_header"]["total"] == "23.00"
    assert rows[0]["lines"][0]["product"]["name"] == "Burger"
    assert rows[0]["lines"][0]["line_product_name"] == "Burger / Large"
    assert rows[1]["sales_scope"] == "EXTERNAL" and rows[1]["delivery_platform_name"] == "Keeta"
    assert set(stub.models_read) == {
        "pos.order", "pos.session", "pos.order.line", "product.product",
        "res.partner", "pos.payment", "pos.payment.method",
    }
    assert not any(model.startswith("account.") or model.startswith("stock.") for model in stub.models_read)
    state_condition = next(condition for condition in stub.order_domains[0] if condition[0] == "state")
    assert state_condition == ("state", "in", list(BRANCH_REPORT_ORDER_STATES))
    assert "draft" in state_condition[2] and "cancel" not in state_condition[2]
    date_domain = stub.order_domains[0]
    assert ("date_order", ">=", f"{sales_date.isoformat()} 00:00:00") in date_domain
    assert ("date_order", "<=", f"{sales_date.isoformat()} 23:59:59") in date_domain
    changed_dates = stub.changed_sales_dates(
        datetime.now(timezone.utc) - timedelta(minutes=5),
        sales_date - timedelta(days=365),
        "Asia/Riyadh",
    )
    assert sales_date in changed_dates
    changed_domain = stub.order_domains[-1]
    assert any(condition[0] == "write_date" for condition in changed_domain)
    assert not any(condition[0] == "state" for condition in changed_domain)


def verify_attached_report_reference_totals() -> None:
    """Lock the exact source values visible in the user's DGTERA screenshots."""
    day_qty = sum(map(Decimal, ("208", "213", "128", "226", "126", "196", "49")))
    day_net = sum(map(Decimal, ("3252.35", "3906.96", "2373.92", "4202.44", "1839.13", "3022.26", "878.26")))
    day_vat = sum(map(Decimal, ("487.85", "586.04", "356.08", "630.36", "275.87", "453.34", "131.74")))
    day_gross = sum(map(Decimal, ("3740.20", "4493.00", "2730.00", "4832.80", "2115.00", "3475.60", "1010.00")))
    assert (day_qty, day_net, day_vat, day_gross) == (
        Decimal("1146"), Decimal("19475.32"), Decimal("2921.28"), Decimal("22396.60")
    )
    assert day_net + day_vat == day_gross
    year_net, year_vat, year_gross = Decimal("6464308.29"), Decimal("969636.26"), Decimal("7433944.55")
    assert year_net + year_vat == year_gross
    # An intraday 13-Aug screenshot is retained only as an arithmetic fixture,
    # never as a closed-day acceptance total: DGTERA continued receiving sales
    # later that day.  Closed-day reconciliation must use a source report run
    # after the business window has ended.
    intraday_qty = sum(map(Decimal, ("67", "38", "9", "53", "21", "1", "4")))
    intraday_net = Decimal("3793.06")
    intraday_vat = Decimal("568.94")
    intraday_gross = Decimal("4362.00")
    assert intraday_qty == Decimal("193")
    assert intraday_net + intraday_vat == intraday_gross


def verify_adaptive_safe_split() -> None:
    """A large source response is split, fully read and proved—not truncated."""
    range_start = date(2026, 8, 10)
    range_end = date(2026, 8, 13)
    calls: list[tuple[date, date, bool]] = []

    class DummyDb:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1

    class DummyConnection:
        id = 1
        company_id = 1
        timezone = "Asia/Riyadh"
        last_sync_at = None
        last_error = "old result-limit error"

    checks = {
        name: True for name in (
            "order_ids", "order_headers", "branches", "customers", "products",
            "lines", "payments", "states", "quantity", "net", "vat", "gross",
            "paid", "returns", "discounts", "source_hashes",
        )
    }

    def result_for(day: date) -> dict:
        source = {
            "orders": 100,
            "lines": 193,
            "payments": 100,
            "quantity": "193.0000",
            "subtotal": "3793.06",
            "vat": "568.94",
            "gross": "4362.00",
            "paid": "4362.00",
            "returns": "0.00",
            "discounts": "0.00",
        }
        proof_hash = f"{day.toordinal():064x}"[-64:]
        report = {
            "strict": True,
            "matched": True,
            "mismatch_count": 0,
            "checks": dict(checks),
            "source": dict(source),
            "corvax": dict(source),
            "difference": "0.00",
            "verification_hash": proof_hash,
            "daily": {day.isoformat(): {"matched": True, "verification_hash": proof_hash}},
            "mismatches": [],
        }
        return {
            "run_id": day.toordinal(),
            "start_date": day,
            "end_date": day,
            "window": "00:00-23:59:59 DGTERA source date / strict-v8",
            "source_orders": 100,
            "inserted": 100,
            "updated": 0,
            "unchanged": 0,
            "removed": 0,
            "source_total": Decimal("4362.00"),
            "imported_total": Decimal("4362.00"),
            "reconciled": True,
            "strict_reconciled": True,
            "verification_hash": proof_hash,
            "reconciliation": report,
            "mode": "SALES_ONLY",
        }

    def fake_sync(db, connection, start_date, end_date, actor_user_id, *, mark_current_sync):
        calls.append((start_date, end_date, mark_current_sync))
        if start_date != end_date:
            raise DgteraResultLimitExceeded("pos.order", 15911, 10000)
        return result_for(start_date)

    db = DummyDb()
    connection = DummyConnection()
    with patch("app.services.dgtera_sales_sync._sync_unlocked", side_effect=fake_sync):
        merged = sync_connection(db, connection, range_start, range_end, 1)

    assert calls[0] == (range_start, range_end, True)
    leaf_calls = [item for item in calls[1:] if item[0] == item[1]]
    assert [item[0] for item in leaf_calls] == [
        date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)
    ]
    assert all(mark_current_sync is False for _, _, mark_current_sync in calls[1:])
    assert merged["split_windows"] == 4
    assert merged["source_orders"] == 400
    assert merged["source_total"] == merged["imported_total"] == Decimal("17448.00")
    assert merged["reconciliation"]["matched"] is True
    assert merged["reconciliation"]["difference"] == "0.00"
    assert set(merged["reconciliation"]["daily"]) == {
        "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"
    }
    assert all(merged["reconciliation"]["checks"].values())
    assert db.commits == 1
    assert connection.last_sync_at is not None and connection.last_error is None

    # A single business day cannot be split further.  It must fail closed
    # instead of accepting a capped/truncated response as complete sales.
    single_day_db = DummyDb()
    single_day_connection = DummyConnection()
    with patch(
        "app.services.dgtera_sales_sync._sync_unlocked",
        side_effect=DgteraResultLimitExceeded("pos.order", 10001, 10000),
    ):
        try:
            sync_connection(
                single_day_db,
                single_day_connection,
                range_start,
                range_start,
                1,
            )
        except DgteraResultLimitExceeded:
            pass
        else:
            raise AssertionError("a truncated single DGTERA business day was accepted")
    assert single_day_db.commits == 0
    assert single_day_connection.last_sync_at is None

    # A transient managed-database disconnect retries the complete auditable
    # range exactly once after rollback.  Partial work is never resumed.
    class RetryDb(DummyDb):
        def __init__(self, refreshed_connection):
            super().__init__()
            self.refreshed_connection = refreshed_connection
            self.rollbacks = 0
            self.expirations = 0
            self.gets = 0

        def rollback(self):
            self.rollbacks += 1

        def expire_all(self):
            self.expirations += 1

        def get(self, model, object_id):
            assert model is DgteraConnection and object_id == self.refreshed_connection.id
            self.gets += 1
            return self.refreshed_connection

    retry_connection = DummyConnection()
    retry_db = RetryDb(retry_connection)
    retry_result = result_for(range_start)
    transient = OperationalError(
        "SELECT redacted",
        {},
        ConnectionResetError("server closed the connection"),
    )
    with patch(
        "app.services.dgtera_sales_sync._sync_unlocked",
        side_effect=[transient, retry_result],
    ) as mocked_sync:
        retried = sync_connection(
            retry_db,
            retry_connection,
            range_start,
            range_start,
            1,
        )
    assert mocked_sync.call_count == 2
    assert retry_db.rollbacks == retry_db.expirations == retry_db.gets == 1
    assert retried["strict_reconciled"] is True
    assert retried["source_total"] == retried["imported_total"] == Decimal("4362.00")


def main() -> None:
    payload_sample = {"order_id": "519", "sales_date": "2026-08-17", "lines": [{"name": "اختبار"}] * 20}
    encoded_payload = _encode_source_payload(payload_sample)
    assert encoded_payload.startswith("zlib:v1:")
    assert len(encoded_payload) < len(str(payload_sample))
    assert _decode_source_payload(encoded_payload) == payload_sample
    managed_disconnect = OperationalError(
        "INSERT redacted", {}, RuntimeError("consuming input failed: SSL error: unexpected EOF")
    )
    assert _is_transient_operational_error(managed_disconnect)
    assert str(DAY_START) == "00:00:00"
    assert str(DAY_END) == "23:59:59"
    assert SOURCE_LOCAL_WINDOW_MARKER == "dgtera-source-date-line-report-strict-v10"
    assert BRANCH_REPORT_ORDER_STATES == ("draft", "paid", "done", "invoiced")
    assert HISTORY_CHUNK_DAYS == 1
    assert HISTORY_CHUNKS_PER_CYCLE == 8
    assert CHANGED_DAYS_PER_CYCLE == 1
    assert _date_windows([
        date(2025, 1, 1), date(2025, 1, 2), date(2025, 2, 10)
    ]) == [
        (date(2025, 1, 1), date(2025, 1, 1)),
        (date(2025, 1, 2), date(2025, 1, 2)),
        (date(2025, 2, 10), date(2025, 2, 10)),
    ]
    verify_scheduler_queue_serialization()
    assert validate_dgtera_url("https://cheesehouse.dgtera.com/") == "https://cheesehouse.dgtera.com"
    for unsafe in ("http://cheesehouse.dgtera.com", "https://example.com", "https://user:pass@cheesehouse.dgtera.com"):
        try:
            validate_dgtera_url(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe DGTERA URL accepted: {unsafe}")

    scope, mode, evidence, platform = classify_sale(
        partner_name="HungerStation",
        payment_method_names=["HungerStation"],
        optional_values={},
    )
    assert (scope, mode, platform) == ("EXTERNAL", "DELIVERY", "HungerStation")
    assert evidence == "DGTERA_DELIVERY_EVIDENCE"
    assert classify_sale(partner_name="", payment_method_names=["Cash"], optional_values={"table_id": [12, "T12"]})[:2] == ("INTERNAL", "DINE_IN")
    assert classify_sale(partner_name="", payment_method_names=["Cash"], optional_values={})[:2] == ("INTERNAL", "TAKEAWAY")
    verify_server_capped_keyset_pagination()
    verify_real_connector_window(date.today())
    verify_attached_report_reference_totals()
    verify_adaptive_safe_split()

    sales_date = date.today()
    source = {
        "order_id": "9001",
        "order_name": "Order 9001",
        "pos_reference": "POS/TEST/9001",
        "state": "done",
        "date_order_utc": f"{sales_date.isoformat()} 09:30:00",
        "date_order_local": f"{sales_date.isoformat()} 12:30:00",
        "sales_date": sales_date.isoformat(),
        "session_id": "501",
        "session_name": "POS/SESSION/501",
        "branch": {"config_id": "701", "config_name": "Al Aziziyah"},
        "customer": {
            "partner_id": "301",
            "code": "HUNGERSTATION",
            "name": "HungerStation",
            "active": True,
            "source_updated_at": f"{sales_date.isoformat()} 09:31:00",
        },
        "sales_scope": "EXTERNAL",
        "service_mode": "DELIVERY",
        "classification_source": "DGTERA_DELIVERY_EVIDENCE",
        "delivery_platform_name": "HungerStation",
        "subtotal": "100.00",
        "vat_amount": "15.00",
        "total": "115.00",
        "amount_paid": "115.00",
        "amount_return": "0.00",
        "discount_amount": "0.00",
        "line_total_difference": "0.00",
        "lines": [{
            "line_id": "4001",
            "product": {
                "product_id": "2001",
                "code": "BURGER-001",
                "barcode": "628000000001",
                "name": "Classic Burger",
                "category_id": "90",
                "category_name": "Burgers",
                "list_price": "115.00",
                "active": True,
                "source_updated_at": f"{sales_date.isoformat()} 09:00:00",
            },
            "quantity": "1.0000",
            "unit_price": "115.0000",
            "discount_percent": "0.0000",
            "subtotal": "100.00",
            "vat_amount": "15.00",
            "total": "115.00",
            "tax_ids": ["15"],
        }],
        "payments": [{
            "payment_id": "6001",
            "method_id": "41",
            "method_name": "HungerStation",
            "amount": "115.00",
        }],
        "source_metadata": {"x_delivery_platform_id": [301, "HungerStation"]},
        "source_updated_at": f"{sales_date.isoformat()} 09:32:00",
        "source_hash": "a" * 64,
    }
    fake = FakeClient(source, sales_date)

    with patch("app.services.dgtera_sales_sync.client_for", return_value=fake):
        with TestClient(app) as client:
            token = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            with SessionLocal() as db:
                restaurant_period = db.scalar(select(FiscalPeriod).join(FiscalYear).where(
                    FiscalYear.company_id == 3,
                    FiscalPeriod.start_date <= sales_date,
                    FiscalPeriod.end_date >= sales_date,
                ))
                assert restaurant_period
                restaurant_period.status = "OPEN"
                db.commit()
            secrets = ("private_odoo_database", "integration@example.invalid", "api-key-never-returned-12345")
            saved = ok(client.put(
                "/api/v1/integrations/dgtera/connection",
                headers=headers,
                json={
                    "company_id": 1,
                    "base_url": "https://cheesehouse.dgtera.com",
                    "database_name": secrets[0],
                    "login": secrets[1],
                    "api_key": secrets[2],
                    "timezone": "Asia/Riyadh",
                },
            ))
            assert saved["connected"] and saved["mode"] == "SALES_ONLY"
            assert saved["day_window"] == "00:00-23:59:59 DGTERA source report date"
            assert saved["sync_interval_minutes"] == 2
            assert saved["initial_sync"]["inserted"] == 1
            assert saved["initial_sync"]["reconciled"] is True
            assert saved["initial_sync"]["strict_reconciled"] is True
            assert saved["initial_sync"]["reconciliation"]["matched"] is True
            assert all(saved["initial_sync"]["reconciliation"]["checks"].values())
            assert saved["initial_sync"]["reconciliation"]["source"] == saved["initial_sync"]["reconciliation"]["corvax"]
            assert all(secret not in str(saved) for secret in secrets)

            with SessionLocal() as db:
                raw = db.execute(text("select database_name, login, api_key from dgtera_connections where company_id=1")).one()
                assert all(str(value).startswith("enc:v1:") for value in raw)
                assert db.scalar(select(func.count(DgteraSalesOrder.id))) == 1
                assert db.scalar(select(func.count(DgteraSalesOrderLine.id))) == 1
                assert db.scalar(select(func.count(DgteraSalesPayment.id))) == 1
                assert db.scalar(select(func.count(DgteraBranch.id))) == 1
                assert db.scalar(select(func.count(DgteraProduct.id))) == 1
                assert db.scalar(select(func.count(DgteraCustomer.id))) == 1
                sales_journals = db.scalars(select(JournalEntry).where(
                    JournalEntry.reference.like("DGTERA-SALES:%")
                )).all()
                assert len(sales_journals) == 1
                sales_journal = sales_journals[0]
                assert sales_journal.company_id == 3
                assert sales_journal.total_debit == sales_journal.total_credit == 115
                account_codes = {
                    row.id: row.code for row in db.scalars(select(Account).where(
                        Account.company_id == 3,
                        Account.code.in_(["112010", "212010", "411010"]),
                    )).all()
                }
                journal_amounts = {
                    account_codes[line.account_id]: (line.debit, line.credit)
                    for line in sales_journal.lines
                }
                assert journal_amounts == {
                    "112010": (Decimal("115.00"), Decimal("0.00")),
                    "411010": (Decimal("0.00"), Decimal("100.00")),
                    "212010": (Decimal("0.00"), Decimal("15.00")),
                }
                order = db.scalar(select(DgteraSalesOrder))
                assert order and order.sales_scope == "EXTERNAL" and order.service_mode == "DELIVERY"
                assert str(order.source_payload).startswith("zlib:v1:")  # transparently decrypted by the ORM
                assert _decode_source_payload(order.source_payload)["order_id"] == str(order.external_order_id)
                encrypted_payload = db.execute(text("select source_payload from dgtera_sales_orders where id=:id"), {"id": order.id}).scalar_one()
                assert str(encrypted_payload).startswith("enc:v1:")
                branch = db.get(Branch, order.branch_id)
                customer = db.get(Party, order.party_id)
                platform_row = db.get(DeliveryPlatform, order.delivery_platform_id)
                assert branch and branch.code.startswith("DGT-B-") and branch.name_en == "Al Aziziyah"
                assert customer and customer.name_en == "HungerStation"
                assert platform_row and platform_row.name_en == "HungerStation"

                connection = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == 1))
                next_history = historical_backfill_window(db, connection)
                assert next_history and next_history[1] == sales_date - timedelta(days=1)
                assert next_history[1] == next_history[0]
                isolated_old_run = DgteraSyncRun(
                    connection_id=connection.id,
                    company_id=connection.company_id,
                    start_date=date(2025, 1, 1),
                    end_date=date(2025, 1, 31),
                    window_label=f"00:00-23:59:59 Asia/Riyadh / {SOURCE_LOCAL_WINDOW_MARKER}",
                    status="COMPLETED",
                    strict_reconciled=True,
                    completed_at=datetime.now(),
                )
                db.add(isolated_old_run)
                db.flush()
                gap_status = historical_backfill_status(db, connection)
                assert gap_status["earliest_imported_date"] == sales_date
                assert gap_status["completed"] is False and gap_status["no_date_gaps"] is False
                db.delete(isolated_old_run)
                db.flush()
                product = db.scalar(select(DgteraProduct))
                product.name = "Stale historical line variant"
                db.commit()
                duplicate = sync_connection(db, connection, sales_date, sales_date, 1)
                assert duplicate["unchanged"] == 1 and duplicate["inserted"] == 0
                assert db.scalar(select(DgteraProduct)).name == "Classic Burger"

            source.update({
                "subtotal": "200.00",
                "vat_amount": "30.00",
                "total": "230.00",
                "amount_paid": "230.00",
                "source_hash": "b" * 64,
            })
            source["lines"][0].update({"quantity": "2.0000", "subtotal": "200.00", "vat_amount": "30.00", "total": "230.00"})
            source["payments"][0]["amount"] = "230.00"

            with SessionLocal() as db:
                connection = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == 1))
                updated = sync_connection(db, connection, sales_date, sales_date, 1)
                assert updated["updated"] == 1 and updated["inserted"] == 0
                assert updated["accounting"]["posted"] is True
                assert updated["accounting"]["days"][0]["status"] == "REPLACED"
                order = db.scalar(select(DgteraSalesOrder))
                assert db.scalar(select(func.count(DgteraSalesOrder.id))) == 1
            assert db.scalar(select(func.count(DgteraSalesOrderLine.id))) == 1
            assert order and order.total == 230 and order.source_hash == "b" * 64

            manual = ok(client.post(
                "/api/v1/integrations/dgtera/sync",
                headers=headers,
                json={
                    "company_id": 1,
                    "start_date": sales_date.isoformat(),
                    "end_date": sales_date.isoformat(),
                },
            ))
            assert manual["synchronized"] is True
            assert manual["strict_reconciled"] is True
            assert manual["source_orders"] == 1
            assert float(manual["source_total"]) == 230
            assert manual["verification_hash"]

            # Opening the executive home may request a current-day refresh.
            # A day proven inside the two-minute freshness window must be
            # served without a redundant upstream read.
            home_refresh = ok(client.post(
                "/api/v1/integrations/dgtera/refresh-current?company_id=1",
                headers=headers,
            ))
            assert home_refresh["refreshed"] is False
            assert home_refresh["reason"] == "CURRENT_DAY_ALREADY_VERIFIED"
            assert home_refresh["sales_date"] == sales_date.isoformat()

            snap = ok(client.get(
                f"/api/v1/integrations/dgtera/snapshot?company_id=1&start_date={sales_date}&end_date={sales_date}",
                headers=headers,
            ))
            assert snap["mode"] == "SALES_ONLY"
            assert snap["coverage"]["complete"] is True
            assert snap["window"]["day_start"] == "00:00" and snap["window"]["day_end"] == "23:59:59"
            assert snap["window"]["date_basis"] == "DGTERA_SOURCE_REPORT_DATE"
            assert snap["totals"]["orders"] == 1 and float(snap["totals"]["external_sales"]) == 230
            assert float(snap["totals"]["quantity"]) == 2
            assert snap["master_counts"] == {"branches": 1, "products": 1, "customers": 1}
            assert float(snap["branch_sales"][0]["quantity"]) == 2
            assert snap["platform_sales"][0]["key"] == "HungerStation"
            assert snap["payment_channels"][0]["key"] == "PLATFORM_CREDIT"
            assert snap["reconciliation"]["matched"] is True
            assert snap["reconciliation"]["strict"] is True
            assert snap["reconciliation"]["mismatch_count"] == 0
            assert snap["reconciliation"]["source_lines"] == snap["reconciliation"]["imported_lines"] == 1
            assert snap["reconciliation"]["source_payments"] == snap["reconciliation"]["imported_payments"] == 1
            assert snap["reconciliation"]["verification_hash"]
            assert all(snap["reconciliation"]["checks"].values())
            assert snap["product_sales"][0]["key"] == "Classic Burger"
            assert len(snap["orders"][0]["lines"]) == 1 and len(snap["orders"][0]["payments"]) == 1

            # The accounting/history release advances the proof generation.
            # A V9 row may contain valid pagination, but it has not traversed
            # the V10 path that creates the idempotent historical journal and
            # therefore cannot authorize a current financial value.
            with SessionLocal() as db:
                proof_runs = db.scalars(select(DgteraSyncRun).where(
                    DgteraSyncRun.start_date == sales_date,
                    DgteraSyncRun.end_date == sales_date,
                    DgteraSyncRun.window_label.like(f"%{SOURCE_LOCAL_WINDOW_MARKER}%"),
                )).all()
                assert proof_runs
                for proof_run in proof_runs:
                    proof_run.window_label = proof_run.window_label.replace(
                        SOURCE_LOCAL_WINDOW_MARKER,
                        "dgtera-source-date-line-report-strict-v9",
                    )
                db.commit()
            legacy_untrusted = ok(client.get(
                f"/api/v1/integrations/dgtera/snapshot?company_id=1&start_date={sales_date}&end_date={sales_date}",
                headers=headers,
            ))
            assert legacy_untrusted["trusted_sales"] is False
            assert legacy_untrusted["totals"] is None
            with SessionLocal() as db:
                proof_runs = db.scalars(select(DgteraSyncRun).where(
                    DgteraSyncRun.start_date == sales_date,
                    DgteraSyncRun.end_date == sales_date,
                    DgteraSyncRun.window_label.like("%strict-v9%"),
                )).all()
                for proof_run in proof_runs:
                    proof_run.window_label = proof_run.window_label.replace(
                        "dgtera-source-date-line-report-strict-v9",
                        SOURCE_LOCAL_WINDOW_MARKER,
                    )
                db.commit()
            analytics = ok(client.get(
                f"/api/v1/integrations/dgtera/analytics?company_id=1&as_of_date={sales_date}&period=DAY",
                headers=headers,
            ))
            assert float(analytics["metrics"]["current"]["sales"]) == 230
            assert float(analytics["metrics"]["current"]["quantity"]) == 2
            assert "next" in analytics["metrics"] and "next_change_percent" in analytics["comparison"]
            assert analytics["branch_comparison"][0]["branch"] == "Al Aziziyah"
            assert analytics["history"]["start_date"] == "2025-01-01"
            assert analytics["coverage"]["current"]["complete"] is True
            assert analytics["coverage"]["prior_year"]["complete"] is False
            connection_status = ok(client.get(
                "/api/v1/integrations/dgtera/status?company_id=1",
                headers=headers,
            ))
            assert connection_status["history"]["earliest_imported_date"] == sales_date.isoformat()
            runs = ok(client.get("/api/v1/integrations/dgtera/sync-runs?company_id=1", headers=headers))
            assert len(runs) == 4 and all(row["status"] == "COMPLETED" for row in runs)

            # A newer failed read invalidates the older green proof for that
            # day.  CORVAX may retain the last atomic rows for recovery, but it
            # must not expose their financial values as trusted sales.
            with SessionLocal() as db:
                connection = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == 1))
                failed_run = DgteraSyncRun(
                    connection_id=connection.id,
                    company_id=connection.company_id,
                    start_date=sales_date,
                    end_date=sales_date,
                    window_label=f"00:00-23:59:59 DGTERA source date / {SOURCE_LOCAL_WINDOW_MARKER}",
                    status="ERROR",
                    strict_reconciled=False,
                    error_message="DGTERA pos.order pagination stopped after 300 of 750 records",
                    completed_at=datetime.now(),
                )
                db.add(failed_run)
                db.commit()
                failed_run_id = failed_run.id
            untrusted = ok(client.get(
                f"/api/v1/integrations/dgtera/snapshot?company_id=1&start_date={sales_date}&end_date={sales_date}",
                headers=headers,
            ))
            assert untrusted["trusted_sales"] is False
            assert untrusted["totals"] is None and untrusted["orders"] == []
            assert untrusted["reconciliation"]["matched"] is False
            assert untrusted["coverage"]["complete"] is False
            with SessionLocal() as db:
                db.delete(db.get(DgteraSyncRun, failed_run_id))
                db.commit()

            # The holding owns one encrypted connection, while the restaurant
            # workspace reads the exact same connection-scoped mirror.  This
            # is inheritance, not a second import, so totals and order counts
            # must match without adding another DGTERA connection or order.
            restaurant_status = ok(client.get(
                "/api/v1/integrations/dgtera/status?company_id=3",
                headers=headers,
            ))
            assert restaurant_status["configured"] and restaurant_status["inherited"]
            assert restaurant_status["company_id"] == 3
            assert restaurant_status["connection_company_id"] == 1
            restaurant_snap = ok(client.get(
                f"/api/v1/integrations/dgtera/snapshot?company_id=3&start_date={sales_date}&end_date={sales_date}",
                headers=headers,
            ))
            assert restaurant_snap["totals"] == snap["totals"]
            restaurant_analytics = ok(client.get(
                f"/api/v1/integrations/dgtera/analytics?company_id=3&as_of_date={sales_date}&period=DAY",
                headers=headers,
            ))
            assert restaurant_analytics["metrics"] == analytics["metrics"]
            holding_home = ok(client.get(
                f"/api/v1/integrations/dgtera/executive-summary?company_id=1&as_of_date={sales_date}",
                headers=headers,
            ))
            restaurant_home = ok(client.get(
                f"/api/v1/integrations/dgtera/executive-summary?company_id=3&as_of_date={sales_date}",
                headers=headers,
            ))
            assert not holding_home["inherited"] and restaurant_home["inherited"]
            assert holding_home["connection"]["connected"] is True
            assert restaurant_home["connection"]["inherited"] is True
            assert holding_home["proof_generation"] == SOURCE_LOCAL_WINDOW_MARKER
            assert holding_home["periods"] == restaurant_home["periods"]
            assert float(holding_home["periods"]["DAY"]["metrics"]["current"]["sales"]) == 230
            assert holding_home["periods"]["DAY"]["coverage"]["current"]["complete"] is True
            assert holding_home["periods"]["YEAR"]["coverage"]["current"]["complete"] is False
            restaurant_runs = ok(client.get("/api/v1/integrations/dgtera/sync-runs?company_id=3", headers=headers))
            assert restaurant_runs == runs
            with SessionLocal() as db:
                assert db.scalar(select(func.count(DgteraConnection.id))) == 1
                assert db.scalar(select(func.count(DgteraSalesOrder.id))) == 1

            custom = ok(client.get(
                f"/api/v1/integrations/dgtera/range-comparison?company_id=3&start_date={sales_date}&end_date={sales_date}",
                headers=headers,
            ))
            assert custom["coverage"]["current"]["complete"] is True
            assert float(custom["metrics"]["current"]["subtotal"]) == 200
            assert custom["metrics"]["previous"] is None
            restaurant_statements = ok(client.get(
                f"/api/v1/finance/statements?company_id=3&start_date={sales_date}&end_date={sales_date}",
                headers=headers,
            ))
            assert float(restaurant_statements["income_statement"]["revenue"]) == 200
            with SessionLocal() as db:
                assert db.scalar(select(func.count(JournalEntry.id)).where(
                    JournalEntry.company_id == 1,
                    JournalEntry.reference.like("DGTERA-SALES:%"),
                )) == 0

            # KPI aggregates must cover the full selected range even when the
            # drill-down list is deliberately limited.
            with SessionLocal() as db:
                base_order = db.scalar(select(DgteraSalesOrder))
                assert base_order
                for index in range(505):
                    db.add(DgteraSalesOrder(
                        connection_id=base_order.connection_id,
                        company_id=base_order.company_id,
                        external_order_id=f"BULK-{index}",
                        external_order_name=f"Bulk {index}",
                        sales_date=sales_date,
                        ordered_at_local=datetime.combine(sales_date, datetime.min.time()),
                        ordered_at_utc=datetime.combine(sales_date, datetime.min.time()),
                        branch_id=base_order.branch_id,
                        dgtera_branch_id=base_order.dgtera_branch_id,
                        sales_scope="INTERNAL",
                        service_mode="TAKEAWAY",
                        classification_source="TEST",
                        state="done",
                        subtotal=1,
                        vat_amount=0,
                        total=1,
                        amount_paid=1,
                        amount_return=0,
                        discount_amount=0,
                        line_total_difference=0,
                        source_hash=f"{index:064x}"[-64:],
                        source_payload="{}",
                    ))
                db.commit()
            complete_totals = ok(client.get(
                f"/api/v1/integrations/dgtera/snapshot?company_id=1&start_date={sales_date}&end_date={sales_date}&limit=1",
                headers=headers,
            ))
            assert complete_totals["trusted_sales"] is False
            assert complete_totals["totals"] is None
            assert complete_totals["orders"] == []
            assert complete_totals["branch_sales"] == []
            assert complete_totals["product_sales"] == []
            assert complete_totals["reconciliation"]["matched"] is False
            assert complete_totals["reconciliation"]["mismatch_count"] > 0
            assert complete_totals["reconciliation"]["verification_hash"] is None

            # A strict mismatch must roll back the entire source snapshot; no
            # partially updated order may leak into reports.
            forced_failure = {
                "matched": False,
                "mismatch_count": 1,
                "mismatches": [{"path": "order[9001].vat", "expected": "30.00", "actual": "29.99"}],
            }
            with patch("app.services.dgtera_sales_sync._strict_reconciliation", return_value=forced_failure):
                with SessionLocal() as db:
                    connection = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == 1))
                    try:
                        sync_connection(db, connection, sales_date, sales_date, 1)
                    except DgteraReconciliationError:
                        pass
                    else:
                        raise AssertionError("strict mismatch was accepted")
                    assert db.scalar(select(func.count(DgteraSalesOrder.id))) == 506
                    db.refresh(connection)
                    assert "1 differences" in str(connection.last_error)
                    assert "order[9001].vat" in str(connection.last_error)

            # The user-triggered endpoint is strict and unexpected dependency
            # failures remain a sanitized, structured API response.
            with patch(
                "app.api.dgtera_integration.dgtera_sales_sync.sync_connection",
                side_effect=RuntimeError("simulated safe diagnostic"),
            ):
                unexpected = client.post(
                    "/api/v1/integrations/dgtera/sync",
                    headers=headers,
                    json={
                        "company_id": 1,
                        "start_date": sales_date.isoformat(),
                        "end_date": sales_date.isoformat(),
                    },
                )
            assert unexpected.status_code == 502
            assert unexpected.json()["detail"] == (
                "DGTERA sales synchronization failed safely: "
                "RuntimeError: simulated safe diagnostic"
            )
            assert client.post("/api/v1/integrations/dgtera/sync", headers=headers, json={}).status_code == 422

            # A completed source window is authoritative: cancelled/moved
            # records that disappear from DGTERA must not remain in totals.
            fake.sales_date = date(2024, 1, 1)
            with SessionLocal() as db:
                connection = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == 1))
                cleaned = sync_connection(db, connection, sales_date, sales_date, 1)
                assert cleaned["removed"] == 506
                assert db.scalar(select(func.count(DgteraSalesOrder.id))) == 0

            # Production-like load gate: a dense DGTERA business day with
            # 1,000 orders, lines and payments must commit atomically and a
            # repeated poll must remain idempotent with exactly the same sums.
            load_date = sales_date - timedelta(days=1)
            load_rows: list[dict] = []
            for index in range(1000):
                row = deepcopy(source)
                row["order_id"] = f"LOAD-{index:04d}"
                row["order_name"] = f"Load order {index:04d}"
                row["pos_reference"] = f"POS/LOAD/{index:04d}"
                row["sales_date"] = load_date.isoformat()
                row["date_order_utc"] = f"{load_date.isoformat()} 09:30:00"
                row["date_order_local"] = f"{load_date.isoformat()} 12:30:00"
                row["source_updated_at"] = f"{load_date.isoformat()} 09:32:00"
                row["source_hash"] = f"{index + 1:064x}"
                row["lines"][0]["line_id"] = f"LOAD-LINE-{index:04d}"
                row["payments"][0]["payment_id"] = f"LOAD-PAY-{index:04d}"
                load_rows.append(row)
            fake.source = load_rows
            fake.sales_date = load_date
            with SessionLocal() as db:
                connection = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == 1))
                started = perf_counter()
                loaded = sync_connection(db, connection, load_date, load_date, 1)
                first_elapsed = perf_counter() - started
                assert loaded["inserted"] == 1000 and loaded["strict_reconciled"] is True
                assert loaded["reconciliation"]["source"]["subtotal"] == loaded["reconciliation"]["corvax"]["subtotal"] == "200000.00"
                assert loaded["reconciliation"]["source"]["vat"] == loaded["reconciliation"]["corvax"]["vat"] == "30000.00"
                assert loaded["source_total"] == loaded["imported_total"] == Decimal("230000.00")
                started = perf_counter()
                repeated = sync_connection(db, connection, load_date, load_date, 1)
                second_elapsed = perf_counter() - started
                assert repeated["inserted"] == repeated["updated"] == repeated["removed"] == 0
                assert repeated["unchanged"] == 1000 and repeated["strict_reconciled"] is True
                assert db.scalar(select(func.count(DgteraSalesOrder.id))) == 1000
                assert db.scalar(select(func.count(DgteraSalesOrderLine.id))) == 1000
                assert db.scalar(select(func.count(DgteraSalesPayment.id))) == 1000
                assert first_elapsed < 30 and second_elapsed < 30
            print(
                "DGTERA 1000-order load gate: "
                f"initial={first_elapsed:.2f}s idempotent={second_elapsed:.2f}s "
                "net=200000.00 vat=30000.00 gross=230000.00"
            )

    print("verify_dgtera_integration: PASSED")


if __name__ == "__main__":
    main()
