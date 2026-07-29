"""CORVAX RC25 fixed asset lifecycle verification."""
from __future__ import annotations
import os, sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v125.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-rc25-assets",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})
import subprocess
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=True)
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.db import SessionLocal
from app.main import app
from app.models import Account, AssetLifecycleTransaction, Branch, CostCenter, FixedAsset, JournalEntry


def D(v): return Decimal(str(v)).quantize(Decimal("0.01"))
def ok(r, status=200): assert r.status_code == status, r.text; return r.json()


def main():
    with TestClient(app) as c:
        login = ok(c.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        admin = {"Authorization": f"Bearer {login['access_token']}"}
        assert ok(c.get("/health"))["version"] == "1.0.0-agreement-completion-rc27.4"
        # Compare against the live head so this test cannot rot (audit M-05).
        from app.core.migration_head import expected_migration_head
        assert ok(c.get("/health/ready"))["migration_head"] == expected_migration_head()
        ok(c.post("/api/v1/admin/users", headers=admin, json={
            "name_ar": "معتمد دورة الأصول", "name_en": "Asset Lifecycle Approver",
            "email": "rc25.approver@corvaxplatform.com", "password": "Rc25Approver@123",
            "require_password_change": False, "memberships": [{"company_id": 1, "role_code": "SUPER_ADMIN"}],
        }), 201)
        al = ok(c.post("/api/v1/auth/login", json={"email": "rc25.approver@corvaxplatform.com", "password": "Rc25Approver@123"}))
        approver = {"Authorization": f"Bearer {al['access_token']}"}
        with SessionLocal() as db:
            db.execute(text("update fiscal_periods set status='OPEN'"))
            branches = db.scalars(select(Branch).where(Branch.company_id == 1).order_by(Branch.id)).all()
            centers = db.scalars(select(CostCenter).where(CostCenter.company_id == 1).order_by(CostCenter.id)).all()
            assert branches and centers
            branch1 = branches[0].id
            center1 = centers[0].id
            destination_branch = db.scalar(select(Branch).where(Branch.company_id == 1, Branch.code == "RC25-DST"))
            if not destination_branch:
                destination_branch = Branch(company_id=1, code="RC25-DST", name_ar="فرع نقل الأصول", name_en="Asset Transfer Branch", active=True)
                db.add(destination_branch); db.flush()
            destination_center = db.scalar(select(CostCenter).where(CostCenter.company_id == 1, CostCenter.code == "RC25-DST"))
            if not destination_center:
                destination_center = CostCenter(company_id=1, code="RC25-DST", name_ar="مركز نقل الأصول", name_en="Asset Transfer Cost Center", active=True)
                db.add(destination_center); db.flush()
            branch2 = destination_branch.id
            center2 = destination_center.id
            db.commit()
        cats = ok(c.get("/api/v1/assets/categories?company_id=1", headers=admin))
        banks = ok(c.get("/api/v1/subledgers/bank-accounts?company_id=1", headers=admin))
        asset = ok(c.post("/api/v1/assets", headers=admin, json={
            "company_id": 1, "name_ar": "ماكينة تعبئة", "name_en": "Filling Machine",
            "category_id": cats[0]["id"], "acquisition_date": "2026-07-01", "in_service_date": "2026-07-10",
            "cost": 120000, "residual_value": 0, "useful_life_months": 60, "bank_account_id": banks[0]["id"],
            "branch_id": branch1, "cost_center_id": center1,
        }), 201)
        dep = ok(c.post("/api/v1/assets/depreciation/run", headers=admin, json={"company_id": 1, "as_of_date": "2026-07-31"}))
        assert D(dep["depreciation_amount"]) == D(2000)

        def lifecycle(payload):
            row = ok(c.post("/api/v1/assets/lifecycle", headers=admin, json={"company_id": 1, "asset_id": asset["id"], **payload}), 201)
            ok(c.post(f"/api/v1/assets/lifecycle/{row['id']}/submit", headers=admin))
            assert c.post(f"/api/v1/assets/lifecycle/{row['id']}/approve-post", headers=admin).status_code == 409
            return ok(c.post(f"/api/v1/assets/lifecycle/{row['id']}/approve-post", headers=approver))

        transfer = lifecycle({"transaction_type": "TRANSFER", "transaction_date": "2026-08-01", "reason": "Move machine to production branch", "to_branch_id": branch2, "to_cost_center_id": center2})
        assert transfer["status"] == "APPROVED_POSTED" and transfer["journal_id"]
        with SessionLocal() as db:
            transferred_asset = db.get(FixedAsset, asset["id"])
            assert transferred_asset.branch_id == branch2 and transferred_asset.cost_center_id == center2

        impairment = lifecycle({"transaction_type": "IMPAIRMENT", "transaction_date": "2026-08-02", "reason": "Recoverable amount test", "recoverable_amount": 100000})
        assert D(impairment["impairment_amount"]) == D(18000)
        reversal = lifecycle({"transaction_type": "IMPAIRMENT_REVERSAL", "transaction_date": "2026-08-03", "reason": "Partial recovery in market value", "recoverable_amount": 110000})
        assert D(reversal["reversal_amount"]) == D(10000)

        hfs = lifecycle({"transaction_type": "HELD_FOR_SALE", "transaction_date": "2026-08-04", "reason": "Board-approved sale plan", "fair_value_less_cost_to_sell": 95000})
        assert D(hfs["impairment_amount"]) == D(15000)
        assets = ok(c.get("/api/v1/assets?company_id=1", headers=admin)); current = next(x for x in assets if x["id"] == asset["id"])
        assert current["status"] == "HELD_FOR_SALE" and D(current["net_book_value"]) == D(95000)
        dep2 = ok(c.post("/api/v1/assets/depreciation/run", headers=admin, json={"company_id": 1, "as_of_date": "2026-08-31"}))
        assert D(dep2["depreciation_amount"]) == D(0)

        hfs_rev = lifecycle({"transaction_type": "HELD_FOR_SALE_REVERSAL", "transaction_date": "2026-09-01", "reason": "Sale plan withdrawn"})
        assert hfs_rev["status"] == "APPROVED_POSTED"
        sale = lifecycle({"transaction_type": "SALE", "transaction_date": "2026-09-02", "reason": "Sell 25 percent of machine components", "reference": "INV-ASSET-01", "disposal_percent": 25, "proceeds_net": 30000, "vat_rate": 15, "tax_code": "S15", "bank_account_id": banks[0]["id"]})
        assert D(sale["disposed_net_book_value"]) == D(23750) and D(sale["gain_amount"]) == D(6250) and D(sale["vat_amount"]) == D(4500)
        vat = ok(c.post("/api/v1/compliance/vat-return", headers=admin, json={"company_id": 1, "period_start": "2026-09-01", "period_end": "2026-09-30"}), 201)
        standard = next(x for x in vat["lines"] if x["box_code"] == "SALES_STANDARD")
        assert standard["details"]["sources"].get("ASSET_SALE") == 1 and vat["output_reconciled"]
        writeoff = lifecycle({"transaction_type": "WRITE_OFF", "transaction_date": "2026-09-03", "reason": "Remaining damaged machine written off", "disposal_percent": 100})
        assert D(writeoff["loss_amount"]) == D(71250)

        assets = ok(c.get("/api/v1/assets?company_id=1", headers=admin)); current = next(x for x in assets if x["id"] == asset["id"])
        assert current["status"] == "WRITTEN_OFF" and D(current["net_book_value"]) == D(0)
        history = ok(c.get(f"/api/v1/assets/lifecycle?company_id=1&asset_id={asset['id']}", headers=admin))
        assert len(history) == 7 and all(x["status"] == "APPROVED_POSTED" for x in history)
        exported = c.get("/api/v1/assets/lifecycle/export.csv?company_id=1", headers=admin)
        assert exported.status_code == 200 and exported.content.startswith(b"\xef\xbb\xbf") and b"WRITE_OFF" in exported.content
        with SessionLocal() as db:
            row = db.get(FixedAsset, asset["id"]); assert row.status == "WRITTEN_OFF"
            assert db.scalar(select(AssetLifecycleTransaction).where(AssetLifecycleTransaction.number == writeoff["number"])).journal_id
            assert not db.execute(select(JournalEntry.id).where(JournalEntry.total_debit != JournalEntry.total_credit)).all()
            assert not db.execute(text("PRAGMA foreign_key_check")).all()
            for code in ("119020", "425010", "426010", "626010"):
                assert db.scalar(select(Account.id).where(Account.company_id == 1, Account.code == code))
    print("CORVAX v1.0 RC25 fixed asset lifecycle: ALL VERIFICATIONS PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__": main()
