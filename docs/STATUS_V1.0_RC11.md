# CORVAX v1.0 RC11 — Audit Remediation Status

## Release position

RC11 is a remediation release created in response to the independent RC10 audit. It is approved only for development, staging, sanitized pilot and UAT. It is not approved as the sole financial book of record.

## Verified internal changes

1. Security and authentication
   - RS256 JWT with `kid`.
   - Rotating refresh tokens; old token replay is rejected.
   - Sensitive-role MFA policy.
   - Endpoint-aware rate limiting.
   - AES-GCM field encryption with external key ring required in production.

2. Financial integrity
   - Race-safe journal sequence per company/year.
   - Existing balance and open-period controls retained.
   - IFRS 9 General Approach and IFRS 16 advanced workflows added.

3. Manufacturing planning
   - Background MRP queue and worker.
   - Supplier lead times, open PO receipts and lot sizing.
   - Work-center calendars and finite-capacity allocation status.

4. Architecture
   - Dashboard monolith reduced to a route host.
   - Route-level page groups and lazy loading.
   - ORM split into domain modules; largest model file is under 500 lines.
   - Application code has no `datetime.utcnow()` usage.

5. Operations
   - Structured JSON request logging and Prometheus metrics.
   - Locust test profile and production load plan.
   - Opening balance import utility and parallel-run runbook.
   - PostgreSQL DR drill utility and runbook.

## Schema

- Alembic head: `e17300000001`.
- 173 tables including `alembic_version` on a fresh migration.
- 171 ORM classes in 17 domain files.
- 42 registered API routers.

## Open items that cannot be claimed closed

- CR-01 ZATCA live integration.
- CR-02 independent penetration test. Internal Bandit SAST is not a substitute.
- CR-03 company data migration, UAT and parallel run.
- Official bank and government integrations.
- Production load test and isolated PostgreSQL PITR drill.
- Independent IFRS validation on real portfolios and lease contracts.

## Honest readiness statement

RC11 materially reduces internal technical risk, but the audit opinion remains qualified until the external and operational evidence above is completed and signed by the responsible owners.
