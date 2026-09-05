import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.audit_logs import router as audit_log_router
from app.api.assets import router as assets_router
from app.api.backups import router as backups_router
from app.api.banking import router as banking_router
from app.api.budgeting import router as budgeting_router
from app.api.inventory import router as inventory_router
from app.api.inventory_traceability import router as inventory_traceability_router  # H9
from app.api.new_departments import router as new_departments_router  # H10
from app.api.sales_commissions import router as sales_commissions_router  # H11
from app.api.attachments import router as attachments_router  # H13
from app.api.data_reset import router as data_reset_router
from app.api.uat_reset import router as uat_reset_router
from app.api.chart_of_accounts import router as chart_of_accounts_router
from app.api.cip_projects import router as cip_projects_router  # H13
from app.api.intercompany import router as intercompany_router
from app.api.hr_operations import router as hr_operations_router
from app.api.hr_payroll_advanced import router as hr_payroll_advanced_router
from app.api.leases import router as leases_router
from app.api.lease_advanced import router as lease_advanced_router
from app.api.manufacturing import router as manufacturing_router
from app.api.advanced_manufacturing import router as advanced_manufacturing_router
from app.api.payroll import router as payroll_router
from app.api.period_close import router as period_close_router
from app.api.year_end_close import router as year_end_close_router
from app.api.governance import router as governance_router
from app.api.itsm import router as itsm_router
from app.api.crm import router as crm_router
from app.api.assurance import router as assurance_router
from app.api.workspace import router as workspace_router
from app.api.operational_controls import router as operational_controls_router
from app.api.prepaids import router as prepaids_router
from app.api.accruals import router as accruals_router
from app.api.pos import router as pos_router
from app.api.restaurant_pos_advanced import router as restaurant_pos_advanced_router
from app.api.gym_operations_advanced import router as gym_operations_advanced_router
from app.api.gym_commercial_activities import router as gym_commercial_activities_router
from app.api.quality import router as quality_router
from app.api.qms import router as qms_router
from app.api.food_safety import router as food_safety_router
from app.api.access_governance import router as access_governance_router
from app.api.advanced_finance import router as advanced_finance_router
from app.api.corporate_reporting import router as corporate_reporting_router
from app.api.financial_close import router as financial_close_router
from app.api.finance_completion import router as finance_completion_router
from app.api.revenue_recognition import router as revenue_recognition_router
from app.api.auth import router as auth_router
from app.api.companies import router as companies_router
from app.api.compliance import router as compliance_router
from app.api.enterprise import router as enterprise_router
from app.api.finance import router as finance_router
from app.api.fx_consolidation import router as fx_consolidation_router
from app.api.risk_maintenance import router as risk_maintenance_router
from app.api.modules import router as modules_router
from app.api.roles import router as roles_router
from app.api.subledgers import router as subledgers_router
from app.api.credit_notes import router as credit_notes_router
from app.api.withholding_tax import router as withholding_tax_router
from app.api.excise_tax import router as excise_tax_router
from app.api.zakat_income_tax import router as zakat_income_tax_router
from app.api.internal_completion import router as internal_completion_router
from app.api.ai_assistant import router as ai_assistant_router
from app.core.config import settings
from app.core.migration_head import expected_migration_head
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.core.observability import configure_logging, initialize_external_observability, metrics_response
from app.db import Base, SessionLocal, engine
from app.services.seed import seed_database


configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Development convenience only. Production is migration-only and the settings
    # validator rejects AUTO_CREATE_SCHEMA=true.
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_database(db)
    # H17: guarantee a usable administrator even when demo seeding is disabled
    # (production forbids SEED_DEMO_DATA, which previously left zero users).
    if settings.bootstrap_first_admin:
        from app.services.bootstrap import bootstrap_first_admin

        with SessionLocal() as db:
            bootstrap_first_admin(db)
    # The external sales integration has been retired.
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
if settings.force_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=settings.origins != ["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
initialize_external_observability(app)
app.include_router(companies_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(roles_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(enterprise_router, prefix="/api/v1")
app.include_router(finance_router, prefix="/api/v1")
app.include_router(fx_consolidation_router, prefix="/api/v1")
app.include_router(risk_maintenance_router, prefix="/api/v1")
app.include_router(subledgers_router, prefix="/api/v1")
app.include_router(credit_notes_router, prefix="/api/v1")
app.include_router(withholding_tax_router, prefix="/api/v1")
app.include_router(excise_tax_router, prefix="/api/v1")
app.include_router(zakat_income_tax_router, prefix="/api/v1")
app.include_router(audit_log_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(modules_router, prefix="/api/v1")
app.include_router(banking_router, prefix="/api/v1")
app.include_router(budgeting_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(inventory_traceability_router, prefix="/api/v1")  # H9
app.include_router(new_departments_router, prefix="/api/v1")  # H10
app.include_router(sales_commissions_router, prefix="/api/v1")  # H11
app.include_router(attachments_router, prefix="/api/v1")  # H13
app.include_router(data_reset_router, prefix="/api/v1")
app.include_router(uat_reset_router, prefix="/api/v1")
app.include_router(chart_of_accounts_router, prefix="/api/v1")
app.include_router(cip_projects_router, prefix="/api/v1")  # H13
app.include_router(intercompany_router, prefix="/api/v1")
app.include_router(revenue_recognition_router, prefix="/api/v1")
app.include_router(leases_router, prefix="/api/v1")
app.include_router(lease_advanced_router, prefix="/api/v1")
app.include_router(manufacturing_router, prefix="/api/v1")
app.include_router(advanced_manufacturing_router, prefix="/api/v1")
app.include_router(payroll_router, prefix="/api/v1")
app.include_router(pos_router, prefix="/api/v1")
app.include_router(restaurant_pos_advanced_router, prefix="/api/v1")
app.include_router(gym_operations_advanced_router, prefix="/api/v1")
app.include_router(gym_commercial_activities_router, prefix="/api/v1")
app.include_router(quality_router, prefix="/api/v1")
app.include_router(qms_router, prefix="/api/v1")
app.include_router(food_safety_router, prefix="/api/v1")
app.include_router(access_governance_router, prefix="/api/v1")
app.include_router(advanced_finance_router, prefix="/api/v1")
app.include_router(corporate_reporting_router, prefix="/api/v1")
app.include_router(financial_close_router, prefix="/api/v1")
app.include_router(finance_completion_router, prefix="/api/v1")
app.include_router(hr_operations_router, prefix="/api/v1")
app.include_router(hr_payroll_advanced_router, prefix="/api/v1")
app.include_router(period_close_router, prefix="/api/v1")
app.include_router(year_end_close_router, prefix="/api/v1")
app.include_router(prepaids_router, prefix="/api/v1")
app.include_router(accruals_router, prefix="/api/v1")
app.include_router(compliance_router, prefix="/api/v1")
app.include_router(backups_router, prefix="/api/v1")
app.include_router(governance_router, prefix="/api/v1")
app.include_router(itsm_router, prefix="/api/v1")
app.include_router(crm_router, prefix="/api/v1")
app.include_router(assurance_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")
app.include_router(operational_controls_router, prefix="/api/v1")
app.include_router(internal_completion_router, prefix="/api/v1")
app.include_router(ai_assistant_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "release_id": settings.release_id,
        "commit": settings.render_git_commit,
        "environment": settings.environment,
    }


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {
        "status": "alive",
        "version": settings.app_version,
        "release_id": settings.release_id,
        "commit": settings.render_git_commit,
    }


@app.get("/health/ready")
def readiness() -> dict:
    expected_head = expected_migration_head()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            try:
                current_head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            except Exception as exc:
                raise HTTPException(503, "Database migration state is unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Database is not ready: {type(exc).__name__}") from exc
    if current_head != expected_head:
        raise HTTPException(503, f"Migration head mismatch: expected {expected_head}, found {current_head}")
    return {
        "status": "ready",
        "version": settings.app_version,
        "release_id": settings.release_id,
        "commit": settings.render_git_commit,
        "environment": settings.environment,
        "database": "reachable",
        "migration_head": current_head,
        "dgtera": {
            "scheduler_enabled": False,
            "poll_seconds": settings.dgtera_scheduler_poll_seconds,
            "sync_interval_minutes": 2,
            "history_days_per_cycle": settings.dgtera_history_days_per_cycle,
            "retired": True,
        },
    }


@app.get("/metrics", include_in_schema=False)
def metrics(x_metrics_token: str | None = Header(default=None)):
    """Operational metrics.

    AUDIT H-09: this endpoint was public and enabled by default, exposing route
    names, status codes and latency to anyone. It now requires METRICS_TOKEN, and
    when no token is configured it is only served outside production.
    """
    if not settings.metrics_enabled:
        raise HTTPException(404, "Metrics are disabled")
    expected = (settings.metrics_token or "").strip()
    if expected:
        if not x_metrics_token or x_metrics_token.strip() != expected:
            raise HTTPException(404, "Metrics are disabled")
    elif settings.environment == "production":
        raise HTTPException(404, "Metrics are disabled")
    return metrics_response()


@app.get("/api/v1/system/release")
def release_information() -> dict:
    return {
        "product": settings.app_name,
        "version": settings.app_version,
        "release_id": settings.release_id,
        "commit": settings.render_git_commit,
        "stage": "FINAL_INTERNAL_RELEASE",
        "database_schema_head": expected_migration_head(),
        "production_claim": "INTERNAL_SCOPE_COMPLETE_WITH_EXTERNAL_CREDENTIALS_AND_SIGNED_PRODUCTION_EVIDENCE_PENDING",
        "external_blockers": [
            "ZATCA production CSID and sandbox certification",
            "bank and government platform credentials",
            "independent penetration and load testing",
            "company UAT, parallel close and signed accounting policies",
        ],
    }


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
