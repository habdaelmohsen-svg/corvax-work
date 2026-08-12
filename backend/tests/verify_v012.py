"""End-to-end verification for CORVAX v0.12 operational engines."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v012.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-v012"
os.environ["SEED_DEMO_DATA"] = "true"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def assert_ok(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


with TestClient(app) as client:
    admin = login(client)
    health = assert_ok(client.get("/health"))
    assert health["version"] == "1.0.0-agreement-completion-rc27.4-r9.4"
    assert health.get("status") == "ok"

    # Budget control from seeded approved budget.
    budgets = assert_ok(client.get("/api/v1/budgets?company_id=1", headers=admin))
    assert budgets and budgets[0]["status"] == "APPROVED"
    control = assert_ok(client.get(f"/api/v1/budgets/{budgets[0]['id']}/control", headers=admin))
    assert Decimal(str(control["totals"]["budget"])) > 0
    assert Decimal(str(control["totals"]["actual"])) > 0

    # Bank reconciliation through actual posted bank journal lines up to 11 July.
    bank = assert_ok(client.get("/api/v1/banking/accounts?company_id=1", headers=admin))[0]
    statement = assert_ok(client.post("/api/v1/banking/statements", headers=admin, json={
        "company_id": 1,
        "bank_account_id": bank["id"],
        "statement_date": "2026-07-11",
        "opening_balance": 0,
        "closing_balance": 2395000,
        "lines": [
            {"transaction_date":"2026-01-01","reference":"OPENING","description":"Capital","amount":2000000,"direction":"CREDIT"},
            {"transaction_date":"2026-07-04","reference":"RCPT-001","description":"Customer receipt","amount":575000,"direction":"CREDIT"},
            {"transaction_date":"2026-07-07","reference":"PAY-EMP","description":"Payroll","amount":200000,"direction":"DEBIT"},
            {"transaction_date":"2026-07-08","reference":"RENT-001","description":"Rent","amount":80000,"direction":"DEBIT"},
            {"transaction_date":"2026-07-09","reference":"PPE-001","description":"Equipment","amount":300000,"direction":"DEBIT"},
            {"transaction_date":"2026-07-10","reference":"LOAN-001","description":"Loan","amount":500000,"direction":"CREDIT"},
            {"transaction_date":"2026-07-11","reference":"SUP-PAY","description":"Supplier","amount":100000,"direction":"DEBIT"},
        ],
    }), 201)
    matched = assert_ok(client.post(f"/api/v1/banking/statements/{statement['id']}/auto-match", headers=admin))
    assert matched["status"] == "MATCHED" and matched["unmatched"] == 0
    reconciled = assert_ok(client.post(f"/api/v1/banking/statements/{statement['id']}/reconcile", headers=admin))
    assert reconciled["status"] == "RECONCILED" and Decimal(str(reconciled["difference"])) == 0

    # Procurement -> PO -> GRN -> supplier invoice / three-way match.
    suppliers = assert_ok(client.get("/api/v1/subledgers/parties?company_id=4", headers=admin))
    supplier = next(row for row in suppliers if row["party_type"] == "SUPPLIER")
    warehouse = assert_ok(client.get("/api/v1/inventory/warehouses?company_id=4", headers=admin))[0]
    items = assert_ok(client.get(f"/api/v1/inventory/items?company_id=4&warehouse_id={warehouse['id']}", headers=admin))
    raw = next(row for row in items if row["code"] == "RAW-001")
    po = assert_ok(client.post("/api/v1/inventory/purchase-orders", headers=admin, json={
        "company_id":4,"order_date":"2026-07-12","supplier_id":supplier["id"],"warehouse_id":warehouse["id"],
        "lines":[{"item_id":raw["id"],"quantity":100,"unit_price":12,"vat_rate":15}],
    }), 201)
    assert assert_ok(client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/approve", headers=admin))["status"] == "APPROVED"
    grn = assert_ok(client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/receive", headers=admin, json={
        "receipt_date":"2026-07-12","lines":[{"purchase_order_line_id":1,"quantity":100,"lot_number":"LOT-PO-001","expiry_date":"2027-07-12"}],
    }), 201)
    # Get the actual line id if seed/DB sequence differs.
    if grn.get("detail"):
        raise AssertionError(grn)
    matched_invoice = assert_ok(client.post(f"/api/v1/inventory/goods-receipts/{grn['id']}/supplier-invoice", headers=admin, json={
        "invoice_date":"2026-07-12","due_date":"2026-08-11","supplier_invoice_number":"SUP-VERIFY-001",
    }), 201)
    assert matched_invoice["match_status"] == "PO_GRN_INVOICE_MATCHED"
    stock = assert_ok(client.get("/api/v1/inventory/stock-summary?company_id=4", headers=admin))
    raw_stock = next(row for row in stock if row["item_code"] == "RAW-001")
    assert Decimal(str(raw_stock["quantity"])) == Decimal("6100.0000")

    # Manufacturing: release, issue, complete, OEE.
    boms = assert_ok(client.get("/api/v1/manufacturing/boms?company_id=4", headers=admin))
    bom = boms[0]
    order = assert_ok(client.post("/api/v1/manufacturing/orders", headers=admin, json={
        "company_id":4,"order_date":"2026-07-12","bom_id":bom["id"],"warehouse_id":warehouse["id"],"planned_quantity":100,
    }), 201)
    issued = assert_ok(client.post(f"/api/v1/manufacturing/orders/{order['id']}/issue-materials", headers=admin))
    assert issued["status"] == "IN_PROCESS" and Decimal(str(issued["material_cost"])) > 0
    completed = assert_ok(client.post(f"/api/v1/manufacturing/orders/{order['id']}/complete", headers=admin, json={
        "completion_date":"2026-07-12","completed_quantity":100,"actual_hours":4.5,"lot_number":"FG-LOT-001","expiry_date":"2027-01-12",
    }))
    assert completed["status"] == "COMPLETED" and Decimal(str(completed["unit_cost"])) > 0
    oee = assert_ok(client.post(f"/api/v1/manufacturing/orders/{order['id']}/runs", headers=admin, json={
        "run_date":"2026-07-12","planned_minutes":480,"downtime_minutes":30,"ideal_cycle_seconds":240,"total_units":100,"good_units":98,
    }), 201)
    assert Decimal(str(oee["oee"])) > 0

    # Quality inspection creates NCR automatically when rejected units exist.
    fg = next(row for row in assert_ok(client.get(f"/api/v1/inventory/items?company_id=4&warehouse_id={warehouse['id']}", headers=admin)) if row["code"] == "FG-001")
    inspection = assert_ok(client.post("/api/v1/quality/inspections", headers=admin, json={
        "company_id":4,"inspection_date":"2026-07-12","inspection_type":"FINAL","reference_type":"PRODUCTION_ORDER","reference_id":order["id"],"item_id":fg["id"],"lot_number":"FG-LOT-001","inspected_quantity":100,"accepted_quantity":98,"rejected_quantity":2,"notes":"Two units rejected","severity":"MEDIUM",
    }), 201)
    assert inspection["result"] == "PARTIAL" and inspection["ncr"]
    ncr = assert_ok(client.patch(f"/api/v1/quality/ncrs/{inspection['ncr']['id']}", headers=admin, json={
        "root_cause":"Packaging seal variation","corrective_action":"Calibrate sealing station and retrain operator","due_date":"2026-07-20","status":"IN_PROGRESS",
    }))
    assert ncr["status"] == "IN_PROGRESS"

    # IFRS 15 membership sale and revenue recognition.
    members = assert_ok(client.get("/api/v1/revenue-recognition/members?company_id=2", headers=admin))
    plans = assert_ok(client.get("/api/v1/revenue-recognition/plans?company_id=2", headers=admin))
    gym_bank = assert_ok(client.get("/api/v1/banking/accounts?company_id=2", headers=admin))[0]
    contract = assert_ok(client.post("/api/v1/revenue-recognition/contracts", headers=admin, json={
        "company_id":2,"member_id":members[0]["id"],"plan_id":plans[0]["id"],"start_date":"2026-07-01","bank_account_id":gym_bank["id"],
    }), 201)
    assert len(contract["schedule"]) == 12 and Decimal(str(contract["net_amount"])) == Decimal("1200.00")
    recognition = assert_ok(client.post("/api/v1/revenue-recognition/recognize", headers=admin, json={"company_id":2,"recognition_date":"2026-07-31"}))
    assert recognition["recognized_count"] == 1 and Decimal(str(recognition["recognized_amount"])) == Decimal("100.00")
    rev_summary = assert_ok(client.get("/api/v1/revenue-recognition/summary?company_id=2", headers=admin))
    assert Decimal(str(rev_summary["reconciliation_difference"])) == 0

    # IFRS 16 initial recognition plus first monthly schedule.
    company_bank = assert_ok(client.get("/api/v1/banking/accounts?company_id=1", headers=admin))[0]
    lease = assert_ok(client.post("/api/v1/leases", headers=admin, json={
        "company_id":1,"name_ar":"إيجار فرع تجريبي","name_en":"Demo Branch Lease","commencement_date":"2026-07-01","end_date":"2027-06-30","payment_amount":10000,"payment_frequency_months":1,"payment_timing":"ARREARS","annual_discount_rate":0.05,"bank_account_id":company_bank["id"],
    }), 201)
    assert Decimal(str(lease["initial_liability"])) > 0 and len(lease["schedule"]) == 12
    lease_run = assert_ok(client.post("/api/v1/leases/post-schedules", headers=admin, json={"company_id":1,"as_of_date":"2026-07-31"}))
    assert lease_run["posted_count"] == 1

    # Final accounting controls remain balanced after all automated postings.
    for company_id in (1, 2, 4):
        tb = assert_ok(client.get(f"/api/v1/finance/trial-balance?company_id={company_id}&end_date=2026-07-31", headers=admin))
        assert tb["balanced"] is True
        statements = assert_ok(client.get(f"/api/v1/finance/statements?company_id={company_id}&start_date=2026-01-01&end_date=2026-07-31&method=direct", headers=admin))
        assert statements["financial_position"]["balanced"] is True, statements["financial_position"]

    audit = assert_ok(client.get("/api/v1/audit-log?company_id=4&limit=500", headers=admin))
    actions = {row["action"] for row in audit}
    assert {"THREE_WAY_MATCH_POSTED","PRODUCTION_ORDER_COMPLETED","OEE_RUN_RECORDED","QUALITY_INSPECTION_RECORDED"}.issubset(actions)

print("CORVAX v0.12 operational engines: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
