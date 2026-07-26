# CORVAX Business Platform v0.28 Test Report

## New verification

`backend/tests/verify_v028.py`

Validated:

- v0.28 health/version response.
- Creation of reciprocal intercompany records.
- Rejection controls for invalid counterparties/directions are implemented.
- Matching within tolerance.
- Reconciliation with zero open records after matching.
- Automatic elimination in a consolidation run.
- Equal debit and credit totals.
- Persistence of records, match, adjustment and elimination lines.

Result:

`CORVAX v0.28 intercompany reconciliation and elimination: ALL VERIFICATIONS PASSED`

## Regression verification

The following suites passed after integration:

- v0.10 financial/subledger core
- v0.12 operational engines
- v0.14 fixed assets, payroll and restaurant POS
- v0.16 security, HR, compliance, period close and backup
- v0.18 FX and consolidation
- v0.20 IFRS 9 and maintenance
- v0.22 maintenance control
- v0.24 prepaid expenses
- v0.26 accruals and recurring journals
- v0.28 intercompany reconciliation and elimination

## Build and migration

- React/TypeScript production build: PASS
- Alembic upgrade from base to `e28000000001`: PASS
- Fresh database table count: 99
- Final Alembic revision: `e28000000001`
