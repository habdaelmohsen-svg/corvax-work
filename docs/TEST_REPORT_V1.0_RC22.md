# CORVAX v1.0 RC22 — Test Report

## Direct RC22 verification

- Non-resident beneficiary profile: PASSED
- Statutory category and rate selection: PASSED
- Technical and consulting payment at 5%: PASSED
- Gross, withheld tax and net cash calculation: PASSED
- AP invoice gross settlement with net bank payment: PASSED
- Maker-checker transaction approval: PASSED
- Direct treaty relief blocked without approval: PASSED
- Approved treaty rate and reference validation: PASSED
- Monthly return generation and due date: PASSED
- Return-to-GL reconciliation: PASSED
- Maker-checker return approval: PASSED
- SADAD payment journal: PASSED
- Certificate blocked before return payment and enabled after payment: PASSED
- UTF-8 CSV exports: PASSED
- Balanced journals and foreign-key integrity: PASSED

## Migration verification

- Clean upgrade to e18300000001: PASSED
- Downgrade to e18200000001: PASSED
- Re-upgrade to e18300000001: PASSED
- Tables including Alembic: 242
- New withholding-tax tables: 5
- Payment net-cash and withholding columns: PRESENT

## Regression verification

All verification suites from RC21 down to v0.10 were executed successfully. Historical suites containing old release-number or migration-head assertions were run from temporary normalized copies only; production test files were not rewritten.

Verified suites: 33

## Frontend

- TypeScript compilation: PASSED
- Vite production build: PASSED
- Modules transformed: 1,805
- npm audit declared vulnerabilities: 0

## API inventory

- OpenAPI paths: 465
- Total operations: 559
- API v1 operations: 556
- API groups/tags: 50
- Withholding-tax paths: 12
- Withholding-tax operations: 15

## Not executed

- ZATCA production portal submission
- Official certificate issuance
- DTA refund workflow through ZATCA
- PostgreSQL concurrency and load testing
- Real-company data migration and parallel run
- Independent tax, security and legal review
