# CORVAX v1.0 RC13 — Verification Report

## Result

**RC13 restaurant operations and POS completion verification: PASSED.**

## RC13 end-to-end verification

`backend/tests/verify_v113.py` completed the following controlled scenario:

1. Create a restaurant table and reservation.
2. Create a kitchen station and route a menu item to it.
3. Open a cashier shift.
4. Post a dine-in cash order linked to the table, reservation and shift.
5. Verify KDS creation and sequential status transitions through SERVED.
6. Request a partial return and verify rejection of self-approval.
7. Independently approve the return and post the accounting reversal.
8. Complete table service and release the table.
9. Submit exact cashier close, reject self-approval and independently approve the close.
10. Synchronize an offline delivery order and verify duplicate idempotency.
11. Process the offline order through the KDS workflow.
12. Prepare, independently review and independently approve a zero-variance delivery-platform settlement.
13. Submit restaurant waste, reject self-approval and independently approve its inventory/accounting posting.
14. Verify final restaurant summary values.

Final output:

`CORVAX v1.0 RC13 restaurant operations and POS completion: ALL VERIFICATIONS PASSED`

## Regression verification

All 24 verification scripts passed against the RC13 codebase:

- `verify_v010.py` through `verify_v032.py` for the historical core and operational releases.
- `verify_v100.py`, `verify_v102.py`, and `verify_v104.py` through `verify_v113.py` for governance, assurance, QMS, finance, manufacturing, audit remediation, HR/payroll and restaurant/POS completion.

## Build, migration and security verification

- Python compile for application, migrations and tests: passed.
- TypeScript and Vite production build: passed.
- Frontend transformed modules: 1,801.
- Fresh Alembic upgrade to `e17500000001`: passed.
- Fresh schema count: 195 tables including `alembic_version`.
- Downgrade to `e17400000001` and re-upgrade to `e17500000001`: passed.
- npm production audit: 0 known vulnerabilities at test time.
- Bandit SAST over `backend/app`: 0 findings and 0 scan errors at test time.

## Evidence not verified by this report

- Physical POS terminals, receipt/kitchen printers and payment devices.
- Live delivery-platform API settlement files.
- Production offline behavior under real network interruption and device clock drift.
- ZATCA production clearance/reporting and cryptographic signing.
- Independent third-party penetration testing.
- Company-data migration, departmental UAT and parallel run.
- Production load/stress testing and PostgreSQL disaster-recovery drill.
