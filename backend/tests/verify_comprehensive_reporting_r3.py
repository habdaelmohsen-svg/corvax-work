"""CORVAX RC27.4 R3 comprehensive reporting center verification."""
from __future__ import annotations

import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp/verify_comprehensive_reporting_r3.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-comprehensive-reporting-r3",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r3",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.api.system_reports import REPORT_CATALOG  # noqa: E402


EXPECTED_CODES = {
    *(f"VAT-{index:02d}" for index in range(1, 11)),
    *(f"FS-{index:02d}" for index in range(1, 13)),
    *(f"SAL-{index:02d}" for index in range(1, 13)),
    *(f"PUR-{index:02d}" for index in range(1, 6)),
    *(f"INV-{index:02d}" for index in range(1, 6)),
    *(f"GL-{index:02d}" for index in range(1, 7)),
    "CASH-01", "CASH-02", "FA-01", "FA-02", "BUD-01", "AUD-01", "CLOSE-01",
}


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def main() -> None:
    assert len(REPORT_CATALOG) == 57
    assert {row["code"] for row in REPORT_CATALOG} == EXPECTED_CODES
    assert all(row["status"] == "IMPLEMENTED" for row in REPORT_CATALOG)
    assert all(row["export_formats"] == ["XLSX", "PDF"] for row in REPORT_CATALOG)

    with TestClient(app) as client:
        login = ok(client.post("/api/v1/auth/login", json={
            "email": "admin@corvaxplatform.com",
            "password": "Corvax@123",
        }))
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        catalog = ok(client.get("/api/v1/system-reports/catalog?company_id=1", headers=headers))
        assert catalog["section_name_ar"] == "مركز التقارير الشامل"
        assert catalog["report_count"] == 57
        assert {row["code"] for row in catalog["reports"]} == EXPECTED_CODES
        assert catalog["can_export"] is True and catalog["can_configure_tax"] is True

        profile = ok(client.put("/api/v1/system-reports/vat-profile", headers=headers, json={
            "company_id": 1,
            "filing_frequency": "MONTHLY",
            "return_layout_version": "ZATCA_STANDARD",
        }))
        assert profile["filing_frequency"] == "MONTHLY"

        for code in sorted(EXPECTED_CODES):
            # VAT return and reconciliation must respect the configured filing
            # frequency; other reports deliberately exercise a full-year custom
            # range.  Keeping one range for all 57 reports masked this contract.
            # Every VAT report is backed by the same period-bound VAT snapshot,
            # so the whole VAT family must use a complete filing period.
            vat_return_report = code.startswith("VAT-")
            start_date = "2026-01-01"
            end_date = "2026-01-31" if vat_return_report else "2026-12-31"
            result = ok(client.post("/api/v1/system-reports/run", headers=headers, json={
                "company_id": 1,
                "report_code": code,
                "period_type": "CUSTOM",
                "start_date": start_date,
                "end_date": end_date,
                "method": "indirect",
                "slow_days": 90,
                "obsolete_days": 180,
                "limit": 5000,
            }))
            assert result["report"]["code"] == code
            assert result["report"]["status"] == "IMPLEMENTED"
            assert result["metadata"]["company_id"] == 1
            assert result["metadata"]["period_start"] == start_date
            assert result["metadata"]["period_end"] == end_date
            assert len(result["metadata"]["result_sha256"]) == 64
            assert result["row_count"] == len(result["rows"])
            assert isinstance(result["columns"], list) and result["columns"], code
            assert all({"key", "name_ar", "name_en", "type"} <= set(column) for column in result["columns"])

        runs = ok(client.get("/api/v1/system-reports/runs?company_id=1&limit=100", headers=headers))
        assert len(runs) >= 57
        assert EXPECTED_CODES <= {row["report_code"] for row in runs}
        assert all(len(row["result_sha256"]) == 64 for row in runs)

        missing = client.post("/api/v1/system-reports/run", headers=headers, json={
            "company_id": 1, "report_code": "MISSING-01", "period_type": "MONTH", "anchor_date": "2026-01-15",
        })
        assert missing.status_code == 404

    page = (PROJECT_DIR / "frontend/src/dashboard/reportsCenterPage.tsx").read_text(encoding="utf-8")
    exporter = (PROJECT_DIR / "frontend/src/dashboard/reportExport.ts").read_text(encoding="utf-8")
    navigation = (PROJECT_DIR / "frontend/src/dashboard/navigation.tsx").read_text(encoding="utf-8")
    for required in (
        "مركز التقارير الشامل", "system-reports/catalog", "system-reports/run",
        "exportSystemReportExcel", "printSystemReportPdf",
    ):
        assert required in page or required in navigation
    for required in (
        'ySplit="7"', "<autoFilter", "fitToWidth=\"1\"", "<headerFooter>",
        "company_logo_url", "result_sha256", "display:table-header-group", "counter(page)",
    ):
        assert required in exporter

    print("CORVAX RC27.4 R3 comprehensive reporting center: 57/57 VERIFICATIONS PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
