# CORVAX v1.0 RC21 — Test Report

## RC21 functional verification

`backend/tests/verify_v121.py` passed.

Verified scenarios:

- Eligible posted invoice and remaining-return quantity endpoint.
- Partial sales return in a later VAT period.
- Repeated return up to, but not beyond, original invoice quantity.
- Maker-checker rejection for self-approval.
- AR open-item reduction and AR-to-GL reconciliation.
- Fully settled invoice creating a customer credit balance.
- Customer credit cash refund and restored reconciliation.
- Purchase return with inventory carrying cost above supplier net credit.
- Stock reduction at carrying cost and explicit landed-cost loss posting.
- AP open-item reduction without worsening historical AP reconciliation difference.
- Original July VAT and negative August sales/purchase adjustments.
- Export credit note reversing the approved export box.
- VAT-to-GL output and input reconciliation.
- Internal type-381 structured sales credit-note document.
- UTF-8 BOM CSV export.
- Balanced journals and clean SQLite foreign-key integrity.

## Migration verification

- Clean upgrade through `e18200000001`: passed.
- Downgrade to `e18100000001`: passed.
- Re-upgrade to `e18200000001`: passed.
- Resulting schema: 237 tables including Alembic.

## Regression verification

Passed:

- RC20 operational finance controls.
- RC19 VAT classification after updating its regression fixture to meet the RC20+ approved-export-evidence requirement.
- RC18 native AR/AP aging and allocation.
- RC17 financial statements and IAS 7 cash flow.
- RC16 work center and search.
- RC15 gym departments and cafe.
- RC14 gym operations.
- RC13 restaurant and POS.

## Frontend and package checks

- TypeScript: passed.
- Vite production build: passed with 1,804 transformed modules.
- npm audit: zero declared vulnerabilities.
- Python compileall: passed.

## Not run

- PostgreSQL concurrent load and locking tests.
- Production ZATCA CSID, XML signing, reporting or clearance.
- Real payment gateway, POS hardware, customs or bank integration.
- Real-company UAT, data migration and parallel operation.
- Independent tax, IFRS, security and penetration reviews.
