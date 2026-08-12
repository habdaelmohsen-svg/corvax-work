"""Acceptance gate for the automatic DGTERA sales-only mirror."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch


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

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
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
    JournalEntry,
    Party,
)
from app.services.dgtera_connector import (  # noqa: E402
    DAY_END,
    DAY_START,
    Odoo14Client,
    classify_sale,
    validate_dgtera_url,
)
from app.services.dgtera_sales_sync import sync_connection  # noqa: E402


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


class FakeClient:
    def __init__(self, source: dict, sales_date: date):
        self.source = source
        self.sales_date = sales_date

    def test_connection(self):
        return {"connected": True, "final_sales_orders": 1, "odoo_version": "14", "mode": "SALES_ONLY"}

    def daily_sales(self, start_date, end_date, timezone_name):
        assert timezone_name == "Asia/Riyadh"
        return [self.source] if start_date <= self.sales_date <= end_date else []


class StubOdooClient(Odoo14Client):
    """Exercise the real daily_sales transformation without network access."""

    def __init__(self, sales_date: date):
        self.sales_date = sales_date
        self.models_read: list[str] = []
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
        d = self.sales_date
        orders = [
            {
                "id": 1, "name": "EXCLUDED-0000", "pos_reference": "EXCLUDED-0000",
                "date_order": f"{d.isoformat()} 21:00:00", "state": "done",
                "session_id": [501, "S501"], "partner_id": False, "lines": [101],
                "amount_untaxed": 10, "amount_tax": 1.5, "amount_total": 11.5, "amount_paid": 11.5,
            },
            {
                "id": 2, "name": "INCLUDED-0001", "pos_reference": "INCLUDED-0001",
                "date_order": f"{d.isoformat()} 21:01:00", "state": "done",
                "session_id": [501, "S501"], "partner_id": False, "lines": [102],
                "amount_untaxed": 20, "amount_tax": 3, "amount_total": 23, "amount_paid": 23,
            },
            {
                "id": 3, "name": "INCLUDED-2359", "pos_reference": "INCLUDED-2359",
                "date_order": f"{(date.fromordinal(d.toordinal()+1)).isoformat()} 20:59:59", "state": "done",
                "session_id": [501, "S501"], "partner_id": [301, "Keeta"], "lines": [103],
                "amount_untaxed": 30, "amount_tax": 4.5, "amount_total": 34.5, "amount_paid": 34.5,
            },
        ]
        if model == "pos.order":
            return orders
        if model == "pos.session":
            return [{"id": 501, "name": "S501", "config_id": [701, "Al Aziziyah"]}]
        if model == "pos.order.line":
            result = []
            for order_row in orders:
                total = order_row["amount_total"]
                result.append({
                    "id": 100 + order_row["id"], "order_id": [order_row["id"], order_row["name"]],
                    "product_id": [2001, "Burger"], "full_product_name": "Burger", "qty": 1,
                    "price_unit": total, "discount": 0, "price_subtotal": order_row["amount_untaxed"],
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


def verify_real_connector_window(sales_date: date) -> None:
    # The stub dates are UTC-naive as Odoo stores them.  Use the previous UTC
    # date so 21:00/21:01 become 00:00/00:01 on the requested Riyadh date.
    utc_base = date.fromordinal(sales_date.toordinal() - 1)
    stub = StubOdooClient(utc_base)
    rows = stub.daily_sales(sales_date, sales_date, "Asia/Riyadh")
    assert [row["order_id"] for row in rows] == ["2", "3"]
    assert rows[0]["date_order_local"].endswith("00:01:00")
    assert rows[1]["date_order_local"].endswith("23:59:59")
    assert rows[0]["service_mode"] == "TAKEAWAY"
    assert rows[1]["sales_scope"] == "EXTERNAL" and rows[1]["delivery_platform_name"] == "Keeta"
    assert set(stub.models_read) == {
        "pos.order", "pos.session", "pos.order.line", "product.product",
        "res.partner", "pos.payment", "pos.payment.method",
    }
    assert not any(model.startswith("account.") or model.startswith("stock.") for model in stub.models_read)


def main() -> None:
    assert str(DAY_START) == "00:01:00"
    assert str(DAY_END) == "23:59:59"
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
    verify_real_connector_window(date.today())

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
            assert saved["day_window"] == "00:01-23:59 Asia/Riyadh"
            assert saved["sync_interval_minutes"] == 5
            assert saved["initial_sync"]["inserted"] == 1
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
                assert db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.reference.like("DGTERA:%"))) == 0
                order = db.scalar(select(DgteraSalesOrder))
                assert order and order.sales_scope == "EXTERNAL" and order.service_mode == "DELIVERY"
                assert str(order.source_payload).startswith("{")  # transparently decrypted by the ORM
                encrypted_payload = db.execute(text("select source_payload from dgtera_sales_orders where id=:id"), {"id": order.id}).scalar_one()
                assert str(encrypted_payload).startswith("enc:v1:")
                branch = db.get(Branch, order.branch_id)
                customer = db.get(Party, order.party_id)
                platform_row = db.get(DeliveryPlatform, order.delivery_platform_id)
                assert branch and branch.code.startswith("DGT-B-") and branch.name_en == "Al Aziziyah"
                assert customer and customer.name_en == "HungerStation"
                assert platform_row and platform_row.name_en == "HungerStation"

                connection = db.scalar(select(DgteraConnection).where(DgteraConnection.company_id == 1))
                duplicate = sync_connection(db, connection, sales_date, sales_date, 1)
                assert duplicate["unchanged"] == 1 and duplicate["inserted"] == 0

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
                order = db.scalar(select(DgteraSalesOrder))
                assert db.scalar(select(func.count(DgteraSalesOrder.id))) == 1
                assert db.scalar(select(func.count(DgteraSalesOrderLine.id))) == 1
                assert order and order.total == 230 and order.source_hash == "b" * 64

            snap = ok(client.get(
                f"/api/v1/integrations/dgtera/snapshot?company_id=1&start_date={sales_date}&end_date={sales_date}",
                headers=headers,
            ))
            assert snap["mode"] == "SALES_ONLY"
            assert snap["window"]["day_start"] == "00:01" and snap["window"]["day_end"] == "23:59"
            assert snap["totals"]["orders"] == 1 and float(snap["totals"]["external_sales"]) == 230
            assert snap["master_counts"] == {"branches": 1, "products": 1, "customers": 1}
            assert snap["platform_sales"][0]["key"] == "HungerStation"
            assert snap["product_sales"][0]["key"] == "Classic Burger"
            assert len(snap["orders"][0]["lines"]) == 1 and len(snap["orders"][0]["payments"]) == 1
            runs = ok(client.get("/api/v1/integrations/dgtera/sync-runs?company_id=1", headers=headers))
            assert len(runs) == 3 and all(row["status"] == "COMPLETED" for row in runs)

            # There is intentionally no user-triggered import endpoint.
            assert client.post("/api/v1/integrations/dgtera/sync", headers=headers, json={}).status_code in {404, 405}

    print("verify_dgtera_integration: PASSED")


if __name__ == "__main__":
    main()
