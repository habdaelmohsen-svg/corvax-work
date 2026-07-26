# CORVAX v1.0 RC11 — Verification Report

Test date: 15 July 2026

## Executed successfully

- Python `compileall` for application, migrations, scripts and tests.
- RC11 end-to-end verification `backend/tests/verify_v111.py`.
- RS256 JWT header and `kid` verification.
- Refresh-token rotation and replay rejection.
- Field encryption persistence: plaintext absent from raw database rows.
- Concurrent journal number allocation: 24 unique sequential numbers across 8 workers.
- Supplier lead time, PO receipt netting, lot sizing and capacity planning.
- Durable MRP queue and worker completion.
- IFRS 9 portfolios, SPPI, stages 1/2/3, PD/LGD/EAD and three-user approval.
- IFRS 16 variable payments, sale-and-leaseback and subleases.
- Rate limiting: third login request rejected with HTTP 429 at configured limit.
- Prometheus `/metrics` endpoint.
- Removal of legacy fixed-number demo endpoints.
- Frontend TypeScript and Vite production build: 1,801 modules transformed.
- Fresh Alembic migration to `e17300000001`: 173 tables including Alembic.
- Downgrade from RC11 to RC10 head `e17100000001`, then re-upgrade to RC11: passed.
- Bandit SAST over `backend/app`: zero findings; three explicitly documented skips for safe subprocess/dev-sentinel cases.
- `npm audit --omit=dev`: zero known production dependency vulnerabilities at test time.

## Not executed / cannot be represented as passed

- Independent third-party penetration test.
- DAST against a deployed staging environment.
- 500-user production infrastructure load test.
- PostgreSQL PITR restore to a separate server.
- Company data migration and one-month parallel run.
- ZATCA, bank and government platform certification.

## Result

**Internal RC11 remediation verification: PASSED.**

**Production go-live assurance: NOT PASSED / NOT YET PERFORMED.**
