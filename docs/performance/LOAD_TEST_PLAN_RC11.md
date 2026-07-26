# CORVAX RC11 — Load and Stress Test Plan

This package supplies a reproducible load profile but does **not** claim that the external production-infrastructure test has been completed.

## Required environment
- Disposable PostgreSQL staging clone with sanitized data.
- Same compute class, reverse proxy and network topology planned for production.
- Metrics scraping from `/metrics`; database CPU, locks, connections and slow queries collected.
- `SEED_DEMO_DATA=false` and no real personal data.

## Test stages
1. Baseline: 25 users for 15 minutes.
2. Normal load: 150 users for 45 minutes.
3. Target load: 500 users for 60 minutes.
4. Stress: ramp until first agreed SLA breach.
5. Soak: 150 users for 8 hours.
6. Separate batch tests: 1,000,000 posted journal lines, consolidation, payroll, MRP worker, and period close.

## Acceptance targets
- Read API p95 ≤ 1.5 seconds; p99 ≤ 3 seconds.
- Normal write API p95 ≤ 2.5 seconds.
- Error rate < 0.5%, excluding deliberate 4xx validation.
- No duplicate journal numbers, unbalanced journals, lost background jobs or cross-company leakage.
- Database connections remain below 80% of pool capacity.
- Recovery after peak within 5 minutes without restart.

## Evidence
Export Locust CSV/HTML, Prometheus time series, database logs, deployment version/hash and tester sign-off into `docs/performance/evidence/`.
