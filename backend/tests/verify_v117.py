"""CORVAX RC17 financial statement and IAS 7 cash-flow correction verification."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v117.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SECRET_KEY": "verification-secret-key-corvax-rc17-finance",
        "SEED_DEMO_DATA": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
        "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r9.3",
        "ENABLE_RATE_LIMIT_TESTING": "true",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FiscalPeriod  # noqa: E402


def amount(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def post_journal(
    client: TestClient,
    maker: dict[str, str],
    approver: dict[str, str],
    *,
    reference: str,
    lines: list[dict],
    activity: str | None = None,
    kind: str | None = None,
) -> int:
    payload = {
        "company_id": 1,
        "entry_date": "2026-09-30",
        "reference": reference,
        "description": reference,
        "lines": lines,
    }
    if activity:
        payload["cash_flow_activity"] = activity
    if kind:
        payload["cash_flow_kind"] = kind
    created = client.post("/api/v1/finance/journals", headers=maker, json=payload)
    assert created.status_code == 201, created.text
    journal_id = created.json()["id"]
    submitted = client.post(f"/api/v1/finance/journals/{journal_id}/submit", headers=maker)
    assert submitted.status_code == 200 and submitted.json()["status"] == "PENDING_APPROVAL", submitted.text
    approved = client.post(f"/api/v1/finance/journals/{journal_id}/approve", headers=approver)
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED", approved.text
    posted = client.post(f"/api/v1/finance/journals/{journal_id}/post", headers=approver)
    assert posted.status_code == 200 and posted.json()["status"] == "POSTED", posted.text
    return journal_id


def main() -> None:
    with TestClient(app) as client:
        admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
        user = client.post(
            "/api/v1/admin/users",
            headers=admin,
            json={
                "name_ar": "محاسب اختبار RC17",
                "name_en": "RC17 Test Accountant",
                "email": "rc17.accountant@corvaxplatform.com",
                "password": "Rc17Accountant@123",
                "require_password_change": False, "memberships": [{"company_id": 1, "role_code": "ACCOUNTANT"}],
            },
        )
        assert user.status_code == 201, user.text
        accountant = login(client, "rc17.accountant@corvaxplatform.com", "Rc17Accountant@123")

        with SessionLocal() as db:
            for period in db.query(FiscalPeriod).all():
                period.status = "OPEN"
            db.commit()

        # Non-cash other gain: liability derecognition against OTHER_INCOME.
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-OTHER-INCOME",
            lines=[
                {"account_code": "222010", "debit": 25000, "credit": 0},
                {"account_code": "421010", "debit": 0, "credit": 25000},
            ],
        )
        # Depreciation and impairment must be added back in the indirect method.
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-DEPRECIATION",
            lines=[
                {"account_code": "617010", "debit": 10000, "credit": 0},
                {"account_code": "153010", "debit": 0, "credit": 10000},
            ],
        )
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-ECL",
            lines=[
                {"account_code": "620010", "debit": 4000, "credit": 0},
                {"account_code": "154030", "debit": 0, "credit": 4000},
            ],
        )
        # Working-capital movements and their related cash settlements.
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-CREDIT-SALE",
            lines=[
                {"account_code": "112010", "debit": 100000, "credit": 0},
                {"account_code": "411010", "debit": 0, "credit": 100000},
            ],
        )
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-INVENTORY-PURCHASE",
            lines=[
                {"account_code": "113010", "debit": 50000, "credit": 0},
                {"account_code": "211010", "debit": 0, "credit": 50000},
            ],
        )
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-CUSTOMER-RECEIPT",
            activity="OPERATING",
            kind="CUSTOMER_RECEIPTS",
            lines=[
                {"account_code": "111010", "debit": 60000, "credit": 0},
                {"account_code": "112010", "debit": 0, "credit": 60000},
            ],
        )
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-SUPPLIER-PAYMENT",
            activity="OPERATING",
            kind="SUPPLIER_PAYMENTS",
            lines=[
                {"account_code": "211010", "debit": 20000, "credit": 0},
                {"account_code": "111010", "debit": 0, "credit": 20000},
            ],
        )

        url = "/api/v1/finance/statements?company_id=1&start_date=2026-09-01&end_date=2026-09-30&method=indirect"
        response = client.get(url, headers=admin)
        assert response.status_code == 200, response.text
        result = response.json()
        income = result["income_statement"]
        position = result["financial_position"]
        cash = result["cash_flows"]

        assert amount(income["revenue"]) == Decimal("100000.00")
        assert amount(income["other_income"]) == Decimal("25000.00")
        assert amount(income["operating_expenses"]) == Decimal("14000.00")
        assert amount(income["net_profit"]) == Decimal("111000.00")
        assert position["balanced"] is True, position

        assert amount(cash["depreciation_and_amortization"]) == Decimal("10000.00")
        assert amount(cash["ecl_and_impairment"]) == Decimal("4000.00")
        assert amount(cash["non_cash_gains"]) == Decimal("25000.00")
        assert amount(cash["non_cash_adjustments"]) == Decimal("-11000.00")
        assert amount(cash["working_capital_changes"]["trade_and_other_receivables"]) == Decimal("-40000.00")
        assert amount(cash["working_capital_changes"]["inventories"]) == Decimal("-50000.00")
        assert amount(cash["working_capital_changes"]["trade_and_other_payables"]) == Decimal("30000.00")
        assert amount(cash["working_capital_adjustments"]) == Decimal("-60000.00")
        assert amount(cash["other_operating_reconciliation"]) == Decimal("0.00")
        assert amount(cash["net_operating"]) == Decimal("40000.00")
        assert cash["indirect_reconciles_to_direct_operating"] is True
        assert cash["cash_reconciled"] is True
        assert cash["classification_complete"] is True

        # An unclassified cash journal must not disappear from net cash movement.
        post_journal(
            client,
            accountant,
            admin,
            reference="RC17-UNCLASSIFIED-CASH",
            lines=[
                {"account_code": "613010", "debit": 5000, "credit": 0},
                {"account_code": "111010", "debit": 0, "credit": 5000},
            ],
        )
        direct = client.get(
            "/api/v1/finance/statements?company_id=1&start_date=2026-09-01&end_date=2026-09-30&method=direct",
            headers=admin,
        )
        assert direct.status_code == 200, direct.text
        direct_cash = direct.json()["cash_flows"]
        assert amount(direct_cash["unclassified_cash_change"]) == Decimal("-5000.00")
        assert amount(direct_cash["classified_net_change"]) == Decimal("40000.00")
        assert amount(direct_cash["net_change"]) == Decimal("35000.00")
        assert amount(direct_cash["closing_cash"]) - amount(direct_cash["opening_cash"]) == Decimal("35000.00")
        assert amount(direct_cash["cash_reconciliation_difference"]) == Decimal("0.00")
        assert direct_cash["cash_reconciled"] is True
        assert direct_cash["classification_complete"] is False

        # New mapping bootstrap classifies OTHER_INCOME explicitly rather than as a fallback line.
        bootstrap = client.post("/api/v1/advanced-finance/mappings/bootstrap", headers=admin, json={"company_id": 1})
        assert bootstrap.status_code == 200, bootstrap.text
        mappings = client.get("/api/v1/advanced-finance/mappings?company_id=1", headers=admin)
        assert mappings.status_code == 200, mappings.text
        other_income_mapping = next(row for row in mappings.json() if row["account_code"] == "421010")
        assert other_income_mapping["ifrs18_category"] == "INVESTING"
        assert other_income_mapping["line_code"] == "OTHER_INCOME"

    print("CORVAX v1.0 RC17 financial statements and IAS 7 cash flows: ALL VERIFICATIONS PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
