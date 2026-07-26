# CORVAX v1.0 RC20 — Test Report

## Verified release data

- Application version: `1.0.0-rc20`
- Migration head: `e18100000001`
- Database tables including Alembic: 233
- Total API routes: 538
- API v1 routes: 529
- RC20 operational-control routes: 28
- Frontend production modules: 1,803
- npm audit declared vulnerabilities: 0

## RC20 functional verification

Passed:

- Foreign supplier invoice with no Saudi VAT.
- Brazilian import example with zero VAT collected on the customs declaration and VAT accounted through the return.
- Treatment validation for customs-paid, return-accounted, suspended and exempt imports.
- Maker-checker on import approval and posting.
- Export zero-rating pending evidence and release after approved evidence.
- VAT return and GL reconciliation after import treatment.
- Landed cost allocation and exclusion of recoverable VAT from inventory cost.
- Supplier-invoice and clearing-account postings for landed cost.
- Recursive multi-level BOM cost explosion.
- Direct material, packaging, labor, direct expense, variable overhead and fixed overhead separation.
- Cost preparation, review and independent approval.
- Physical inventory count, count variance and journal posting.
- Inventory aging, expiry, obsolescence and NRV write-down.
- Perpetual inventory subledger/GL reconciliation report.
- UOM conversion control.
- Daily, monthly and annual budget analytics.
- Historical average and bilingual automatic variance comments.
- CSV export for imports, cost roll-up and budget analytics.

## Migration verification

- Clean database upgrade to RC20: passed.
- Downgrade from `e18100000001` to `e17900000001`: passed.
- Re-upgrade to RC20: passed.
- Table count after upgrade and re-upgrade: 233.

## Regression verification

Passed after RC20 changes:

- RC18 AR/AP allocation and native aging.
- RC17 financial statements and IAS 7 cash flow corrections.
- RC16 work center and enterprise search.
- RC15 gym departments and cafe.
- RC14 gym operations.
- RC13 restaurant operations and POS.
- v0.12 operational engines.
- v0.10 financial and subledger core.

## Build verification

- Python compileall: passed.
- TypeScript compile: passed.
- Vite production build: passed, 1,803 modules.
- npm audit: zero declared vulnerabilities.

## Not tested as production proof

- ZATCA or customs electronic submission.
- PostgreSQL concurrency and production-scale load.
- Real bank, POS device, customs, ZATCA or government integrations.
- Customer production data migration and full parallel run.
- Independent tax, IFRS, security and penetration review.
