# CORVAX v1.0 Final Internal Release — Test Report

## Results

- Final end-to-end verification: PASSED.
- Module registry verification: PASSED.
- Historical/current regression suites: 36 adapted historical suites plus 2 current suites, all PASSED.
- Historical adaptation changed expected release/migration metadata and temporary absolute path only; business logic remained unchanged.
- Python compile: PASSED.
- Clean Alembic upgrade: PASSED to `e18700000001`.
- Downgrade to `e18600000001`: PASSED.
- Re-upgrade to final head: PASSED.
- Schema count: 262 tables including `alembic_version`.
- Frontend TypeScript/Vite build: PASSED, 1,808 modules.
- npm audit: 0 info/low/moderate/high/critical vulnerabilities.
- Internal concurrent HTTP smoke: PASSED, 400/400 HTTP 200, concurrency 20, 77.83 requests/second, p95 694.25 ms, p99 942.64 ms.
- SQLite backup API create and checksum verification: PASSED.
- Isolated SQLite restore and integrity check: PASSED (`integrity_check=ok`).
- Balanced journals and foreign-key integrity in final functional simulation: PASSED.

## Important test boundary

The internal HTTP smoke used a disposable SQLite environment. It is not evidence of production PostgreSQL capacity, network behavior, reverse-proxy behavior, long-running soak, or real-data performance. A reusable PostgreSQL smoke, Locust profile and DR drill are included but require the company staging infrastructure.
