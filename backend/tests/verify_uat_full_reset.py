"""Acceptance gate for transaction/value-only UAT reset and asset revaluation."""
from __future__ import annotations

import base64
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp") / f"corvax_uat_value_reset_{os.getpid()}.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SECRET_KEY": "verification-secret-key-uat-value-reset-2026",
        "ENVIRONMENT": "testing",
        "SEED_DEMO_DATA": "true",
        "ALLOW_DATA_RESET": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
        "ENABLE_RATE_LIMIT_TESTING": "true",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.api.uat_reset import (  # noqa: E402
    CONFIRMATION_PHRASE,
    PARTIAL_TABLES,
    PRESERVED_MASTER_TABLES,
    TRANSACTION_TABLES,
    _classified_tables,
)
from app.core.config import settings  # noqa: E402
from app.db import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Account, AssetCategory, BankAccount, Company, FiscalPeriod, FixedAsset, LeaseContract  # noqa: E402


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def table_counts(db, names):
    return {
        name: int(db.scalar(select(func.count()).select_from(Base.metadata.tables[name])) or 0)
        for name in names
    }


def main() -> None:
    page = (ROOT / "frontend/src/dashboard/dataResetPage.tsx").read_text(encoding="utf-8")
    nav = (ROOT / "frontend/src/dashboard/navigation.tsx").read_text(encoding="utf-8")
    selector = (ROOT / "frontend/src/components/CompanySelector.tsx").read_text(encoding="utf-8")
    assert "مسح الحركات والقيم التجريبية" in page
    assert "Clear trial transactions and values now" in page
    assert "key: 'dataReset'" in nav and "requires: ['data.reset']" in nav
    assert "context.permissions" in selector and "permissions_by_company" in selector

    targets, protected = _classified_tables()
    assert set(targets) == TRANSACTION_TABLES
    assert set(protected) == PRESERVED_MASTER_TABLES
    assert set(targets).isdisjoint(PRESERVED_MASTER_TABLES)
    assert set(targets) | set(protected) | set(PARTIAL_TABLES) == set(Base.metadata.tables)
    assert len(targets) >= 180, len(targets)

    with TestClient(app) as client:
        login = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        # A real asset card and acquisition journal prove the reset removes value,
        # not identity.  Select configured master records instead of hard-coding IDs.
        with SessionLocal() as db:
            category = db.scalar(select(AssetCategory).where(AssetCategory.company_id == 1))
            bank = db.scalar(select(BankAccount).where(BankAccount.company_id == 1, BankAccount.active.is_(True)))
            open_period = db.scalar(select(FiscalPeriod).where(FiscalPeriod.status == "OPEN").order_by(FiscalPeriod.start_date))
            assert category and bank and open_period
            posting_date = open_period.start_date
        created = ok(
            client.post(
                "/api/v1/assets",
                headers=headers,
                json={
                    "company_id": 1,
                    "name_ar": "آلة التعبئة الرئيسية",
                    "name_en": "Main Packaging Machine",
                    "category_id": category.id,
                    "acquisition_date": posting_date.isoformat(),
                    "in_service_date": posting_date.isoformat(),
                    "cost": 125000,
                    "residual_value": 5000,
                    "useful_life_months": 60,
                    "bank_account_id": bank.id,
                },
            ),
            201,
        )
        asset_id = created["id"]
        lease_created = ok(
            client.post(
                "/api/v1/leases",
                headers=headers,
                json={
                    "company_id": 1,
                    "name_ar": "عقد المقر الرئيسي",
                    "name_en": "Head Office Lease",
                    "commencement_date": posting_date.isoformat(),
                    "end_date": (posting_date + timedelta(days=365)).isoformat(),
                    "payment_amount": 6000,
                    "payment_frequency_months": 1,
                    "payment_timing": "ARREARS",
                    "annual_discount_rate": 0.05,
                    "bank_account_id": bank.id,
                },
            ),
            201,
        )
        lease_id = lease_created["id"]

        # Company branding is foundation and must survive a value reset.
        one_pixel_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        logo = ok(
            client.post(
                "/api/v1/companies/1/logo",
                headers=headers,
                json={
                    "file_name": "company-logo.png",
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(one_pixel_png).decode(),
                },
            )
        )
        assert logo["logo_url"].startswith("data:image/png;base64,")

        with SessionLocal() as db:
            before_foundation = table_counts(db, protected)
            asset = db.get(FixedAsset, asset_id)
            assert asset and asset.cost == Decimal("125000.00")
            identity = (
                asset.id,
                asset.company_id,
                asset.asset_number,
                asset.name_ar,
                asset.name_en,
                asset.category_id,
                asset.acquisition_date,
                asset.in_service_date,
                asset.useful_life_months,
                asset.depreciation_method,
            )
            logo_before = db.get(Company, 1).logo_url

        preview = ok(client.get("/api/v1/uat-reset/preview?company_id=1", headers=headers))
        assert preview["enabled"] is True
        assert preview["transaction_rows"] > 0
        assert preview["assets_to_reset"] >= 1
        assert preview["scope"] == "ALL_COMPANIES_TRANSACTIONS_AND_TRIAL_VALUES"
        assert preview["confirmation_phrase"] == CONFIRMATION_PHRASE
        assert "fixed_assets" in preview["protected"]

        wrong = client.post(
            "/api/v1/uat-reset/execute",
            headers=headers,
            json={"company_id": 1, "confirmation": "wrong", "backup_acknowledged": True, "dry_run": True},
        )
        assert wrong.status_code == 422
        no_backup = client.post(
            "/api/v1/uat-reset/execute",
            headers=headers,
            json={"company_id": 1, "confirmation": CONFIRMATION_PHRASE, "backup_acknowledged": False, "dry_run": True},
        )
        assert no_backup.status_code == 422

        dry = ok(
            client.post(
                "/api/v1/uat-reset/execute",
                headers=headers,
                json={
                    "company_id": 1,
                    "confirmation": CONFIRMATION_PHRASE,
                    "backup_acknowledged": True,
                    "dry_run": True,
                },
            )
        )
        assert dry["rows_that_would_be_deleted"] == preview["transaction_rows"]
        assert dry["assets_that_would_be_unvalued"] >= 1
        assert dry["authorization_token"]

        result = ok(
            client.post(
                "/api/v1/uat-reset/execute",
                headers=headers,
                json={
                    "company_id": 1,
                    "confirmation": CONFIRMATION_PHRASE,
                    "backup_acknowledged": True,
                    "dry_run": False,
                    "authorization_token": dry["authorization_token"],
                },
            )
        )
        assert result["rows_deleted"] == preview["transaction_rows"]
        assert result["assets_unvalued"] >= 1

        after = ok(client.get("/api/v1/uat-reset/preview?company_id=1", headers=headers))
        assert after["transaction_rows"] == 0
        assert after["total_value_records"] == 0
        with SessionLocal() as db:
            after_foundation = table_counts(db, protected)
            for name in protected:
                if name == "audit_logs":
                    assert after_foundation[name] >= before_foundation[name]
                else:
                    assert after_foundation[name] == before_foundation[name], name
            asset = db.get(FixedAsset, asset_id)
            assert asset is not None
            assert identity == (
                asset.id,
                asset.company_id,
                asset.asset_number,
                asset.name_ar,
                asset.name_en,
                asset.category_id,
                asset.acquisition_date,
                asset.in_service_date,
                asset.useful_life_months,
                asset.depreciation_method,
            )
            assert asset.cost == asset.residual_value == asset.accumulated_depreciation == Decimal("0")
            assert asset.accumulated_impairment == asset.net_book_value == Decimal("0")
            assert asset.status == "DRAFT_UNVALUED"
            assert asset.acquisition_journal_id is None and asset.bank_account_id is None
            lease = db.get(LeaseContract, lease_id)
            assert lease is not None and lease.status == "DRAFT_UNVALUED"
            assert lease.initial_liability == lease.initial_rou_asset == Decimal("0")
            assert lease.initial_journal_id is None and not lease.schedules
            assert db.get(Company, 1).logo_url == logo_before
            offset = db.scalar(
                select(Account).where(
                    Account.company_id == 1,
                    Account.is_postable.is_(True),
                    Account.active.is_(True),
                    Account.account_type == "EQUITY",
                    Account.id != asset.category.asset_account_id,
                )
            )
            assert offset

        opened = ok(
            client.post(
                f"/api/v1/assets/{asset_id}/initialize-opening-value",
                headers=headers,
                json={
                    "company_id": 1,
                    "opening_date": posting_date.isoformat(),
                    "cost": 120000,
                    "residual_value": 5000,
                    "accumulated_depreciation": 20000,
                    "accumulated_impairment": 3000,
                    "offset_account_id": offset.id,
                },
            )
        )
        assert Decimal(str(opened["net_book_value"])) == Decimal("97000.00")
        with SessionLocal() as db:
            asset = db.get(FixedAsset, asset_id)
            assert asset.status == "ACTIVE"
            assert asset.cost == Decimal("120000.00")
            assert asset.net_book_value == Decimal("97000.00")
            assert asset.acquisition_journal_id is not None
            bank_account = db.get(BankAccount, bank.id)
            equity_account = db.scalar(select(Account).where(Account.company_id == 1, Account.code == "311010"))
            revenue_account = db.scalar(select(Account).where(Account.company_id == 1, Account.account_type == "REVENUE", Account.is_postable.is_(True)))
            assert bank_account and equity_account and revenue_account
            bank_gl_code = bank_account.gl_account.code

        lease_opened = ok(
            client.post(
                f"/api/v1/leases/{lease_id}/initialize-opening-value",
                headers=headers,
                json={
                    "company_id": 1,
                    "opening_date": posting_date.isoformat(),
                    "lease_liability": 60000,
                    "rou_asset": 60000,
                },
            )
        )
        assert lease_opened["status"] == "ACTIVE" and lease_opened["remaining_periods"] > 0
        with SessionLocal() as db:
            lease = db.get(LeaseContract, lease_id)
            assert lease.status == "ACTIVE" and lease.initial_journal_id is not None
            assert lease.initial_liability == lease.initial_rou_asset == Decimal("60000.00")
            assert len(lease.schedules) == lease_opened["remaining_periods"]

        # Opening-balance journals use maker/approver/poster workflow and are
        # treated as opening cash, never as current-period cash movement.
        opening_journal = ok(
            client.post(
                "/api/v1/finance/journals",
                headers=headers,
                json={
                    "company_id": 1,
                    "entry_date": posting_date.isoformat(),
                    "reference": "OPENING-BANK-TEST",
                    "description": "Opening main bank balance",
                    "cash_flow_kind": "OPENING_BALANCE",
                    "lines": [
                        {"account_code": bank_gl_code, "debit": 50000, "credit": 0},
                        {"account_code": equity_account.code, "debit": 0, "credit": 50000},
                    ],
                },
            ),
            201,
        )
        assert opening_journal["cash_flow_kind"] == "OPENING_BALANCE"
        journal_id = opening_journal["id"]
        ok(client.post(f"/api/v1/finance/journals/{journal_id}/submit", headers=headers))
        ok(client.post(f"/api/v1/finance/journals/{journal_id}/approve", headers=headers))
        ok(client.post(f"/api/v1/finance/journals/{journal_id}/post", headers=headers))
        statements = ok(
            client.get(
                f"/api/v1/finance/statements?company_id=1&start_date={posting_date}&end_date={posting_date}",
                headers=headers,
            )
        )
        cash = statements["cash_flows"]
        assert Decimal(str(cash["opening_cash"])) == Decimal("50000.00")
        assert Decimal(str(cash["net_change"])) == Decimal("0.00")
        assert Decimal(str(cash["unclassified_cash_change"])) == Decimal("0.00")

        invalid_opening = client.post(
            "/api/v1/finance/journals",
            headers=headers,
            json={
                "company_id": 1,
                "entry_date": posting_date.isoformat(),
                "reference": "OPENING-PNL-BLOCK",
                "description": "Must be blocked",
                "cash_flow_kind": "OPENING_BALANCE",
                "lines": [
                    {"account_code": revenue_account.code, "debit": 100, "credit": 0},
                    {"account_code": equity_account.code, "debit": 0, "credit": 100},
                ],
            },
        )
        assert invalid_opening.status_code == 422

        previous_environment = settings.environment
        previous_flag = settings.allow_data_reset
        settings.environment = "production"
        settings.allow_data_reset = True
        try:
            denied = client.post(
                "/api/v1/uat-reset/execute",
                headers=headers,
                json={
                    "company_id": 1,
                    "confirmation": CONFIRMATION_PHRASE,
                    "backup_acknowledged": True,
                    "dry_run": True,
                },
            )
            assert denied.status_code == 403
        finally:
            settings.environment = previous_environment
            settings.allow_data_reset = previous_flag

    DB_PATH.unlink(missing_ok=True)
    print("verify_uat_full_reset: PASSED")


if __name__ == "__main__":
    main()
