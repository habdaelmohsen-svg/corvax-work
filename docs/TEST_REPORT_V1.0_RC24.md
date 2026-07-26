# CORVAX v1.0 RC24 — Test Report

## RC24 functional verification

Passed:

- Taxpayer profile and ownership validation.
- Controlled ledger profit extraction.
- Zakat and CIT additions and deductions.
- Tax-loss utilization cap and remaining loss balance.
- Mixed-ownership Zakat and CIT calculation.
- Maker-checker rejection of self-approval.
- Accrual journal, GL reconciliation and SADAD payment.
- Balanced journals and foreign-key integrity.
- UTF-8 return and adjustment exports.

## Migration verification

- Clean upgrade to `e18500000001`: passed.
- Downgrade to `e18400000001`: passed.
- Re-upgrade to `e18500000001`: passed.
- Tables after upgrade, including Alembic: 253.

## Regression verification

Passed directly: RC23, RC22, RC21, RC20, RC19, RC18, RC17, RC16, RC15, RC14, RC13 and RC12.

RC11 and RC10 also passed after normalizing only their historical release-version and migration-head assertions in temporary test copies. Their source tests were not changed.

## Frontend and package

- TypeScript and Vite production build: passed.
- Frontend modules transformed: 1,807.
- npm declared vulnerabilities: zero.
- Python compilation: passed.
