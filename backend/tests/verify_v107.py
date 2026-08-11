"""End-to-end verification for CORVAX v1.0 RC7 corporate reporting and tax."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v107.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "verification-secret-key-for-corvax-v107-corporate-reporting"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Company, DeferredTaxRun, EarningsPerShareRun, ForeignOperationTranslationRun,
    GoodwillImpairmentTest, ManagementPerformanceMeasure, SegmentReportRun,
)


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client: TestClient, admin: dict[str, str], email: str, role_code: str) -> tuple[dict[str, str], int]:
    response = client.post(
        "/api/v1/admin/users", headers=admin,
        json={"name_ar": role_code, "name_en": role_code, "email": email, "password": "SecureRole@123", "require_password_change": False, "memberships": [{"company_id": 4, "role_code": role_code}]},
    )
    assert response.status_code == 201, response.text
    return login(client, email, "SecureRole@123"), response.json()["id"]


def build_approved_ifrs18_report(client: TestClient, controller: dict[str, str], auditor: dict[str, str]) -> dict:
    bootstrap = client.post("/api/v1/advanced-finance/mappings/bootstrap", headers=controller, json={"company_id": 4})
    assert bootstrap.status_code == 200, bootstrap.text
    mappings = client.get("/api/v1/advanced-finance/mappings?company_id=4", headers=controller)
    assert mappings.status_code == 200, mappings.text
    for mapping in mappings.json():
        if mapping["status"] != "APPROVED":
            approved = client.post(f"/api/v1/advanced-finance/mappings/{mapping['id']}/approve", headers=auditor)
            assert approved.status_code == 200, approved.text
    report = client.post("/api/v1/advanced-finance/reports", headers=controller, json={
        "company_id": 4, "start_date": "2026-01-01", "end_date": "2026-07-31",
        "comparative_start_date": "2025-01-01", "comparative_end_date": "2025-07-31",
    })
    assert report.status_code == 201, report.text
    assert report.json()["status"] == "READY_FOR_APPROVAL", report.text
    approved = client.post(f"/api/v1/advanced-finance/reports/{report.json()['id']}/approve", headers=auditor)
    assert approved.status_code == 200, approved.text
    return client.get(f"/api/v1/advanced-finance/reports/{report.json()['id']}", headers=controller).json()


with TestClient(app) as client:
    admin = login(client, "admin@corvaxplatform.com", "Corvax@123")
    accountant, accountant_id = create_user(client, admin, "accountant.rc7@corvaxplatform.com", "ACCOUNTANT")
    controller, controller_id = create_user(client, admin, "controller.rc7@corvaxplatform.com", "FINANCIAL_CONTROLLER")
    auditor, auditor_id = create_user(client, admin, "auditor.rc7@corvaxplatform.com", "AUDITOR")
    cfo, cfo_id = create_user(client, admin, "cfo.rc7@corvaxplatform.com", "CFO")

    report = build_approved_ifrs18_report(client, controller, auditor)
    report_id = report["id"]

    # Controlled chart mapping for IAS 12 and IAS 36 postings.
    config = client.post("/api/v1/corporate-reporting/config/bootstrap", headers=accountant, json={"company_id": 4})
    assert config.status_code == 200, config.text
    config_id = config.json()["id"]
    assert client.post(f"/api/v1/corporate-reporting/config/{config_id}/approve", headers=accountant).status_code in {403, 409}
    approved_config = client.post(f"/api/v1/corporate-reporting/config/{config_id}/approve", headers=cfo)
    assert approved_config.status_code == 200 and approved_config.json()["status"] == "APPROVED", approved_config.text

    # IAS 12 deferred tax: DTA, DTL and unrecognized DTA with independent review and posting.
    tax = client.post("/api/v1/corporate-reporting/deferred-tax-runs", headers=accountant, json={
        "company_id": 4, "period_end": "2026-07-31", "default_tax_rate": 0.20,
        "items": [
            {"reference": "PPE-TAX-001", "description_ar": "فرق إهلاك ضريبي للمعدات", "description_en": "Tax depreciation difference on equipment",
             "carrying_amount": 1200000, "tax_base": 900000, "difference_type": "TAXABLE", "recognition_status": "RECOGNIZED", "presentation_basis": "PNL"},
            {"reference": "ECL-DTA-001", "description_ar": "مخصص خسائر ائتمانية غير مقبول ضريبيًا", "description_en": "Tax-unrecognized expected credit loss allowance",
             "carrying_amount": 100000, "tax_base": 300000, "difference_type": "DEDUCTIBLE", "recognition_status": "RECOGNIZED", "presentation_basis": "PNL",
             "recoverability_evidence": "Approved taxable-profit forecast covering the reversal period"},
            {"reference": "LOSS-DTA-UNREC", "description_ar": "خسائر ضريبية غير معترف بها", "description_en": "Unrecognized tax losses",
             "carrying_amount": 0, "tax_base": 250000, "difference_type": "DEDUCTIBLE", "recognition_status": "UNRECOGNIZED", "presentation_basis": "PNL"},
        ],
    })
    assert tax.status_code == 201, tax.text
    tax_id = tax.json()["id"]
    assert Decimal(str(tax.json()["recognized_dta"])) == Decimal("40000.00")
    assert Decimal(str(tax.json()["recognized_dtl"])) == Decimal("60000.00")
    assert Decimal(str(tax.json()["unrecognized_dta"])) == Decimal("50000.00")
    assert client.post(f"/api/v1/corporate-reporting/deferred-tax-runs/{tax_id}/review", headers=accountant).status_code in {403, 409}
    reviewed_tax = client.post(f"/api/v1/corporate-reporting/deferred-tax-runs/{tax_id}/review", headers=auditor)
    assert reviewed_tax.status_code == 200 and reviewed_tax.json()["status"] == "REVIEWED", reviewed_tax.text
    assert client.post(f"/api/v1/corporate-reporting/deferred-tax-runs/{tax_id}/approve-post", headers=auditor).status_code == 409
    approved_tax = client.post(f"/api/v1/corporate-reporting/deferred-tax-runs/{tax_id}/approve-post", headers=cfo)
    assert approved_tax.status_code == 200 and approved_tax.json()["status"] == "APPROVED_POSTED", approved_tax.text
    assert approved_tax.json()["journal_id"] is not None

    # IAS 36 impairment test and irreversible goodwill allocation control.
    goodwill = client.post("/api/v1/corporate-reporting/goodwill-impairment-tests", headers=accountant, json={
        "company_id": 4, "period_end": "2026-07-31", "cgu_code": "MFG-CGU-01",
        "cgu_name_ar": "وحدة التصنيع الرئيسية", "cgu_name_en": "Primary manufacturing CGU",
        "goodwill_carrying_amount": 500000, "other_assets_carrying_amount": 1000000,
        "value_in_use": 1180000, "fair_value_less_costs": 1200000,
        "assumptions": {"discount_rate": 0.11, "terminal_growth": 0.025, "forecast_years": 5},
        "sensitivity": {"discount_rate_plus_1pct": 1080000, "growth_minus_1pct": 1100000},
    })
    assert goodwill.status_code == 201, goodwill.text
    goodwill_id = goodwill.json()["id"]
    assert Decimal(str(goodwill.json()["impairment_loss"])) == Decimal("300000.00")
    assert Decimal(str(goodwill.json()["goodwill_impairment"])) == Decimal("300000.00")
    assert client.post(f"/api/v1/corporate-reporting/goodwill-impairment-tests/{goodwill_id}/review", headers=auditor).status_code == 200
    goodwill_post = client.post(f"/api/v1/corporate-reporting/goodwill-impairment-tests/{goodwill_id}/approve-post", headers=cfo)
    assert goodwill_post.status_code == 200 and goodwill_post.json()["status"] == "APPROVED_POSTED", goodwill_post.text

    # IAS 21 foreign-operation translation and CTA approval for consolidation.
    group = client.post("/api/v1/fx-consolidation/groups", headers=admin, json={
        "code": "RC7-GRP", "name_ar": "مجموعة RC7", "name_en": "RC7 Group", "reporting_currency": "SAR", "member_company_ids": [1, 4],
    })
    assert group.status_code == 201, group.text
    with SessionLocal() as db:
        company = db.get(Company, 4)
        company.currency = "USD"
        db.commit()
    translation = client.post("/api/v1/corporate-reporting/foreign-operation-translations", headers=accountant, json={
        "group_id": group.json()["id"], "member_company_id": 4, "period_start": "2026-01-01", "period_end": "2026-07-31",
        "closing_rate": 3.75, "average_rate": 3.72, "historical_equity_rate": 3.68,
    })
    assert translation.status_code == 201, translation.text
    translation_id = translation.json()["id"]
    assert translation.json()["functional_currency"] == "USD"
    assert client.post(f"/api/v1/corporate-reporting/foreign-operation-translations/{translation_id}/review", headers=auditor).status_code == 200
    translation_approved = client.post(f"/api/v1/corporate-reporting/foreign-operation-translations/{translation_id}/approve", headers=cfo)
    assert translation_approved.status_code == 200 and translation_approved.json()["status"] == "APPROVED_FOR_CONSOLIDATION", translation_approved.text

    # IFRS 18 management performance measure reconciliation and three-step approval.
    mpm = client.post("/api/v1/corporate-reporting/management-performance-measures", headers=accountant, json={
        "company_id": 4, "period_end": "2026-07-31", "code": "ADJ-EBIT",
        "name_ar": "الربح التشغيلي المعدل", "name_en": "Adjusted operating profit",
        "explanation_ar": "مقياس إداري يعكس الأداء التشغيلي بعد استبعاد بنود محددة وغير متكررة مع تسوية كاملة.",
        "explanation_en": "A management-defined measure showing operating performance after identified non-recurring items with full reconciliation.",
        "base_report_run_id": report_id, "base_subtotal_code": "operating_profit",
        "adjustments": [
            {"label_ar": "تكاليف إعادة هيكلة", "label_en": "Restructuring costs", "amount": 25000, "tax_effect": -5000, "nci_effect": 0, "supporting_reference": "WP-MPM-001"},
            {"label_ar": "خسارة انخفاض قيمة غير متكررة", "label_en": "Non-recurring impairment", "amount": 300000, "tax_effect": -60000, "nci_effect": -15000, "supporting_reference": "WP-MPM-002"},
        ],
    })
    assert mpm.status_code == 201, mpm.text
    mpm_id = mpm.json()["id"]
    assert Decimal(str(mpm.json()["total_adjustments"])) == Decimal("325000.00")
    assert client.post(f"/api/v1/corporate-reporting/management-performance-measures/{mpm_id}/review", headers=auditor).status_code == 200
    mpm_approved = client.post(f"/api/v1/corporate-reporting/management-performance-measures/{mpm_id}/approve", headers=cfo)
    assert mpm_approved.status_code == 200 and mpm_approved.json()["status"] == "APPROVED_DISCLOSURE_READY", mpm_approved.text

    # IAS 33 EPS with anti-dilution exclusion logic.
    eps = client.post("/api/v1/corporate-reporting/earnings-per-share", headers=accountant, json={
        "company_id": 4, "period_end": "2026-07-31", "profit_attributable": 5000000,
        "preference_dividends": 0, "weighted_average_shares": 1000000,
        "diluted_profit_adjustment": 400000, "incremental_shares": 10000,
        "support_reference": "SHARE-REGISTER-2026-07",
    })
    assert eps.status_code == 201, eps.text
    eps_id = eps.json()["id"]
    assert Decimal(str(eps.json()["basic_eps"])) == Decimal("5.000000")
    assert Decimal(str(eps.json()["diluted_eps"])) == Decimal("5.000000")
    assert Decimal(str(eps.json()["anti_dilutive_excluded"])) == Decimal("10000.0000")
    assert client.post(f"/api/v1/corporate-reporting/earnings-per-share/{eps_id}/review", headers=auditor).status_code == 200
    eps_approved = client.post(f"/api/v1/corporate-reporting/earnings-per-share/{eps_id}/approve", headers=cfo)
    assert eps_approved.status_code == 200 and eps_approved.json()["status"] == "APPROVED_DISCLOSURE_READY", eps_approved.text

    # IFRS 8 segment disclosure reconciled exactly to approved financial statements.
    segment = client.post("/api/v1/corporate-reporting/segments", headers=accountant, json={
        "company_id": 4, "code": "MFG-ALL", "name_ar": "قطاع التصنيع", "name_en": "Manufacturing segment",
        "codm_title": "Chief Executive Officer", "reportable": True,
    })
    assert segment.status_code == 201, segment.text
    segment_id = segment.json()["id"]
    assert client.post(f"/api/v1/corporate-reporting/segments/{segment_id}/approve", headers=cfo).status_code == 200

    payload = report["report"]
    revenue = sum(Decimal(str(x["current"])) for x in payload["lines"] if x["statement"] == "PROFIT_OR_LOSS" and x["line_code"] == "REVENUE")
    assets = sum(Decimal(str(x["current"])) for x in payload["lines"] if x["statement"] == "FINANCIAL_POSITION" and x["category"] == "ASSETS")
    liabilities = sum(Decimal(str(x["current"])) for x in payload["lines"] if x["statement"] == "FINANCIAL_POSITION" and x["category"] == "LIABILITIES")
    profit = Decimal(str(payload["subtotals"]["current"]["operating_profit"]))
    segment_report = client.post("/api/v1/corporate-reporting/segment-reports", headers=accountant, json={
        "company_id": 4, "period_end": "2026-07-31", "base_report_run_id": report_id,
        "lines": [{"segment_id": segment_id, "external_revenue": str(revenue), "intersegment_revenue": 0,
                   "segment_profit": str(profit), "segment_assets": str(assets), "segment_liabilities": str(liabilities),
                   "measurement_basis": "Amounts measured consistently with the approved IFRS 18 report"}],
    })
    assert segment_report.status_code == 201, segment_report.text
    segment_report_id = segment_report.json()["id"]
    assert segment_report.json()["status"] == "READY_FOR_REVIEW", segment_report.text
    assert not segment_report.json()["reconciliation"]["blocking_fields"]
    assert client.post(f"/api/v1/corporate-reporting/segment-reports/{segment_report_id}/review", headers=auditor).status_code == 200
    segment_approved = client.post(f"/api/v1/corporate-reporting/segment-reports/{segment_report_id}/approve", headers=cfo)
    assert segment_approved.status_code == 200 and segment_approved.json()["status"] == "APPROVED_DISCLOSURE_READY", segment_approved.text

    dashboard = client.get("/api/v1/corporate-reporting/dashboard?company_id=4&period_end=2026-07-31", headers=controller)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["deferred_tax"]["status"] == "APPROVED_POSTED"
    assert dashboard.json()["approved_disclosures"] == {"management_performance_measures": 1, "earnings_per_share": 1, "segment_reports": 1}

    with SessionLocal() as db:
        assert db.get(DeferredTaxRun, tax_id).journal_id is not None
        assert db.get(GoodwillImpairmentTest, goodwill_id).journal_id is not None
        assert db.get(ForeignOperationTranslationRun, translation_id).status == "APPROVED_FOR_CONSOLIDATION"
        assert db.get(ManagementPerformanceMeasure, mpm_id).status == "APPROVED_DISCLOSURE_READY"
        assert db.get(EarningsPerShareRun, eps_id).status == "APPROVED_DISCLOSURE_READY"
        assert db.get(SegmentReportRun, segment_report_id).status == "APPROVED_DISCLOSURE_READY"

print("CORVAX v1.0 RC7 corporate reporting and tax: ALL VERIFICATIONS PASSED")
DB_PATH.unlink(missing_ok=True)
