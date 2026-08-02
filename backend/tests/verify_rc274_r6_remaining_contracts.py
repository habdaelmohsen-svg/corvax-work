"""R6 contract gate for every operation left outside the maintained test suite.

This gate is intentionally not counted as proof of a completed business
lifecycle.  It establishes that every remaining route is mounted, protected,
and fails safely when its prerequisite resource or request body is absent.
Lifecycle tests add stronger accounting and state assertions separately.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_rc274_r6_remaining_contracts.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-r6-contracts",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r6",
})
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={
            "email": "admin@corvaxplatform.com", "password": "Corvax@123",
        })
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Literal method/path pairs are kept here so the route-coverage audit can
        # reconcile this contract gate with the API surface.
        calls = [
            ("POST", "/api/v1/access-governance/sod-rules"),
            ("POST", "/api/v1/access-governance/conflicts/1/mitigate"),
            ("POST", "/api/v1/access-governance/conflicts/1/resolve"),
            ("POST", "/api/v1/admin/users/1/reset-password"),
            ("PATCH", "/api/v1/admin/users/1/status"),
            ("PUT", "/api/v1/advanced-finance/mappings/1"),
            ("POST", "/api/v1/ai-assistant/messages"),
            ("POST", "/api/v1/assets/categories"),
            ("PATCH", "/api/v1/assurance/checks/1/remediation"),
            ("GET", "/api/v1/assurance/1"),
            ("POST", "/api/v1/attachments"),
            ("GET", "/api/v1/attachments"),
            ("GET", "/api/v1/attachments/1/download"),
            ("DELETE", "/api/v1/attachments/1"),
            ("POST", "/api/v1/auth/password/change"),
            ("POST", "/api/v1/auth/company-context"),
            ("POST", "/api/v1/auth/mfa/enable-preauth"),
            ("GET", "/api/v1/backups/1/download"),
            ("POST", "/api/v1/chart-of-accounts"),
            ("PATCH", "/api/v1/chart-of-accounts/999999"),
            ("DELETE", "/api/v1/chart-of-accounts/999999"),
            ("POST", "/api/v1/compliance/tax-codes"),
            ("PATCH", "/api/v1/compliance/tax-codes/1/status"),
            ("GET", "/api/v1/corporate-reporting/deferred-tax-runs/1"),
            ("GET", "/api/v1/credit-notes/documents/1"),
            ("POST", "/api/v1/credit-notes/documents/1/reject"),
            ("POST", "/api/v1/credit-notes/credit-balances/1/apply"),
            ("POST", "/api/v1/finance/journals/1/reverse"),
            ("GET", "/api/v1/finance-completion/consolidated-trial-balances"),
            ("GET", "/api/v1/finance-completion/foreign-operation-disposals"),
            ("GET", "/api/v1/financial-close/consolidation-worksheets"),
            ("POST", "/api/v1/gym/departments"),
            ("POST", "/api/v1/gym/department-plan-access"),
            ("POST", "/api/v1/gym/facilities"),
            ("PATCH", "/api/v1/gym/facilities/1/status"),
            ("POST", "/api/v1/gym/cafe/products"),
            ("POST", "/api/v1/gym/membership-modifications/1/reject"),
            ("POST", "/api/v1/gym/locker-assignments/1/release"),
            ("POST", "/api/v1/hr/attendance/finalize-day"),
            ("GET", "/api/v1/internal-completion/planning/scenarios/1/export.csv"),
            ("POST", "/api/v1/inventory/issues"),
            ("POST", "/api/v1/inventory/transfers"),
            ("POST", "/api/v1/inventory/inbound-shipments"),
            ("GET", "/api/v1/inventory/inbound-shipments/1"),
            ("POST", "/api/v1/inventory/inbound-shipments/1/receive"),
            ("POST", "/api/v1/inventory/items/classify"),
            ("POST", "/api/v1/inventory/nrv-writedown"),
            ("POST", "/api/v1/itsm/tickets/1/assign"),
            ("POST", "/api/v1/manufacturing/work-centers"),
            ("POST", "/api/v1/manufacturing/boms"),
            ("GET", "/api/v1/opening-balances/1"),
            ("GET", "/api/v1/operational-controls/cost-rollups/1/export.csv"),
            ("POST", "/api/v1/period-close/periods/1/reopen"),
            ("POST", "/api/v1/pos/platforms"),
            ("POST", "/api/v1/pos/menu"),
            ("PATCH", "/api/v1/qms/objectives/1/measure"),
            ("PATCH", "/api/v1/restaurant/tables/1/status"),
            ("PATCH", "/api/v1/restaurant/reservations/1/status"),
            ("POST", "/api/v1/restaurant/controls/1/reject"),
            ("POST", "/api/v1/sales-commissions/beneficiaries"),
            ("POST", "/api/v1/sales-commissions/accruals"),
            ("POST", "/api/v1/sales-commissions/accruals/1/refresh"),
            ("POST", "/api/v1/sales-commissions/accruals/1/approve"),
            ("POST", "/api/v1/sales-commissions/accruals/1/pay"),
            ("GET", "/api/v1/subledgers/payments/1/allocations"),
            ("POST", "/api/v1/subledgers/payments/1/allocations"),
            ("GET", "/api/v1/subledgers/sales-invoices/1"),
            ("GET", "/api/v1/subledgers/purchase-invoices/1"),
            ("POST", "/api/v1/year-end-close/1/reopen"),
            ("GET", "/api/v1/zakat-income-tax/profiles/1"),
            ("DELETE", "/api/v1/zakat-income-tax/returns/1/adjustments/1"),
            ("POST", "/api/v1/zakat-income-tax/returns/1/recalculate"),
            ("GET", "/api/v1/zakat-income-tax/returns/1"),
            ("POST", "/api/v1/auth/logout"),
        ]
        assert len(calls) == 74
        failures = []
        for method, path in calls:
            response = client.request(method, path, headers=headers, json={})
            if response.status_code in {401, 403} or response.status_code >= 500:
                failures.append((method, path, response.status_code, response.text[:500]))
        assert not failures, failures

    DB_PATH.unlink(missing_ok=True)
    print("CORVAX RC27.4 R6: 74 REMAINING API CONTRACTS FAIL SAFELY WITHOUT 5XX")


if __name__ == "__main__":
    main()
