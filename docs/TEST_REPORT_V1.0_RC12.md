# CORVAX v1.0 RC12 — Verification Report

## Result

**RC12 HR and payroll completion verification: PASSED.**

## Functional verification

`backend/tests/verify_v112.py` completed the following scenario:

1. Create an employee with encrypted sensitive fields.
2. Prepare and independently approve payroll policy.
3. Create and approve an employee contract.
4. Assign a shift and record attendance, lateness, absence and unpaid leave.
5. Submit and independently approve overtime.
6. Prepare, review and approve a payroll adjustment using three distinct users.
7. Calculate payroll from attendance, leave, overtime, adjustments and GOSI rules.
8. Reject direct posting in strict mode.
9. Reject self-review, then complete independent payroll review and approval.
10. Generate a WPS batch and verify its SHA-256 file hash.
11. Record an accepted WPS response and complete payroll payment.
12. Prepare, review and approve employee-benefit assumptions and valuation.
13. Verify encrypted database storage for protected fields.

Final output:

`CORVAX v1.0 RC12 HR and payroll completion: ALL VERIFICATIONS PASSED`

## Regression verification

All 23 existing verification scripts passed after compatibility corrections:

- `verify_v010.py` through `verify_v032.py` for the historical core releases.
- `verify_v100.py`, `verify_v102.py`, `verify_v104.py` through `verify_v112.py` for RC governance, assurance, quality, finance, manufacturing, audit remediation and RC12.

The legacy payroll compatibility policy preserves the historical BASIC GOSI basis only when strict workflow is disabled. Production configuration requires an approved company payroll policy and strict workflow.

## Build and migration verification

- Python compile for application, migrations and tests: passed.
- TypeScript and Vite production build: passed.
- Frontend transformed modules: 1,801.
- Fresh Alembic upgrade to `e17400000001`: passed.
- Fresh schema count: 182 tables including `alembic_version`.
- Downgrade to `e17300000001` and re-upgrade to `e17400000001`: passed.
- npm production audit: 0 known vulnerabilities at test time.
- Bandit SAST over `backend/app`: 0 findings at test time.

## Unverified external evidence

This report does not claim completion of:

- official bank or Mudad WPS submission;
- ZATCA Phase 2 certification or production clearance/reporting;
- Qiwa, Muqeem or GOSI official API connections;
- independent third-party penetration testing;
- production load test;
- company-data migration, departmental UAT or parallel run;
- independent actuarial validation.
