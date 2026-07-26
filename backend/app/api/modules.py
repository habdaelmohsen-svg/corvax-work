from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.migration_head import expected_migration_head
from app.core.config import settings
from app.dependencies import get_current_user
from app.models import User

router = APIRouter(prefix="/modules", tags=["module registry"])


@router.get("/summary")
def summary(_: User = Depends(get_current_user)) -> dict:
    """Return the controlled module registry.

    Legacy hard-coded demo data endpoints were removed in RC5; RC6 and RC7 added controlled advanced finance and corporate reporting.
    RC8 added database-backed IFRS 3 purchase-price allocation, consolidation worksheets, lead schedules with evidence,
    and controlled IFRS 16 partial lease termination. RC9 adds the final account-level consolidated trial balance,
    controlled contingent-consideration remeasurement and foreign-operation disposal CTA treatment.
    Operational and financial figures must come only from domain APIs.
    """
    return {
        "version": settings.app_version,
        "modules": {
            "core": "ACTIVE_DATABASE_ENGINE",
            "finance": "ACTIVE_POSTED_LEDGER_AND_IFRS18_CONTROLLED_REPORTING",
            "financial_disclosures": "ACTIVE_THREE_STEP_WORKFLOW",
            "deferred_tax": "ACTIVE_IAS12_CONTROLLED_ENGINE",
            "goodwill_impairment": "ACTIVE_IAS36_CONTROLLED_ENGINE",
            "foreign_operation_translation": "ACTIVE_IAS21_CONTROLLED_ENGINE",
            "management_performance_measures": "ACTIVE_IFRS18_DISCLOSURE_ENGINE",
            "earnings_per_share": "ACTIVE_IAS33_DISCLOSURE_ENGINE",
            "segment_reporting": "ACTIVE_IFRS8_RECONCILED_ENGINE",
            "business_combinations": "ACTIVE_IFRS3_PPA_WORKFLOW",
            "consolidation_workbench": "ACTIVE_BALANCED_ADJUSTMENT_WORKSHEETS",
            "lead_schedules": "ACTIVE_GL_RECONCILIATION_AND_EVIDENCE",
            "lease_partial_termination": "ACTIVE_IFRS16_SCOPE_REDUCTION",
            "final_consolidated_trial_balance": "ACTIVE_ACCOUNT_LEVEL_LOCKED_REPORT",
            "contingent_consideration": "ACTIVE_CONTROLLED_REMEASUREMENT",
            "foreign_operation_disposal": "ACTIVE_CTA_RECYCLING_AND_REATTRIBUTION",
            "fixed_asset_lifecycle": "ACTIVE_IAS16_IAS36_IFRS5_CONTROLLED_ENGINE",
            "advanced_cost_variance_bridge": "ACTIVE_MATERIAL_LABOR_OVERHEAD_IDLE_CAPACITY_ENGINE",
            "planning_scenarios": "ACTIVE_BUDGET_FORECAST_ACTUAL_PRIOR_YEAR_ENGINE",
            "unified_financial_close": "ACTIVE_CROSS_MODULE_CHECKLIST_AND_DRILLDOWN",
            "production_readiness_gate": "ACTIVE_EVIDENCE_BASED_INTERNAL_AND_PRODUCTION_ASSESSMENT",
            "lease_modifications": "ACTIVE_IFRS16_REMEASUREMENT",
            "budget": "ACTIVE_DATABASE_ENGINE",
            "inventory": "ACTIVE_DATABASE_ENGINE",
            "purchasing": "ACTIVE_DATABASE_ENGINE",
            "sales": "ACTIVE_DATABASE_ENGINE",
            "gym": "ACTIVE_DATABASE_ENGINE",
            "restaurant": "ACTIVE_DATABASE_ENGINE",
            "manufacturing": "ACTIVE_DATABASE_ENGINE",
            "quality": "ACTIVE_ENTERPRISE_QMS",
            "hr_payroll": "ACTIVE_DATABASE_ENGINE",
            "audit_grc": "ACTIVE_DATABASE_ENGINE",
            "it_governance": "ACTIVE_DATABASE_ENGINE",
            "controlled_documents": "ACTIVE_DATABASE_ENGINE",
            "crm_marketing": "ACTIVE_DATABASE_ENGINE",
            "financial_assurance": "ACTIVE_STRICT_CERTIFICATION_GATE",
            "audit_integrity": "ACTIVE_HASH_CHAIN",
            "jwt_security": "ACTIVE_RS256_WITH_KID_AND_REFRESH_ROTATION",
            "field_encryption": "ACTIVE_APPLICATION_ENVELOPE_ENCRYPTION",
            "api_rate_limiting": "ACTIVE_ENDPOINT_POLICIES",
            "observability": "ACTIVE_PROMETHEUS_JSON_LOGGING_OPTIONAL_OTEL_SENTRY",
            "advanced_mrp_planning": "ACTIVE_PO_RECEIPTS_LEAD_TIMES_LOT_SIZING_FCS_BACKGROUND_QUEUE",
            "ai": "NOT_ENABLED",
        },
        "release_stage": "FINAL_INTERNAL_RELEASE",
        "persistence": "SQL_DATABASE",
        "migration_head": expected_migration_head(),
        "legacy_demo_endpoints": "REMOVED",
        "external_certification": "PENDING_OFFICIAL_CREDENTIALS_AND_UAT",
    }
