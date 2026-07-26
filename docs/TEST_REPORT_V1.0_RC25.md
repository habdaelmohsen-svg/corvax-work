# CORVAX v1.0 RC25 — Test Report

## RC25 functional verification

Passed:

- Capitalization of a SAR 120,000 machine and July depreciation of SAR 2,000.
- Actual branch and cost-center transfer to newly created destination dimensions.
- Maker-checker rejection of self-approval.
- IAS 36 impairment of SAR 18,000 and reversal of SAR 10,000.
- IFRS 5 classification at SAR 95,000 FVLCTS and SAR 15,000 write-down.
- Depreciation suspension while held for sale.
- Reversal of held-for-sale classification.
- Partial 25% asset sale with SAR 30,000 net proceeds, SAR 4,500 VAT, SAR 23,750 disposed NBV and SAR 6,250 gain.
- Inclusion of the asset sale in the VAT return with output-tax GL reconciliation.
- Write-off of the remaining SAR 71,250 NBV.
- Final zero NBV and WRITTEN_OFF status.
- Seven approved lifecycle transactions, UTF-8 CSV export, balanced journals and foreign-key integrity.

## Migration verification

- Clean upgrade to `e18600000001`: passed.
- Downgrade to `e18500000001`: passed.
- Re-upgrade to `e18600000001`: passed.
- Tables after migration, including Alembic: 254.

## Regression verification

Passed: RC24 through RC12, RC11 and RC10, plus the v0.12 operating core and v0.10 financial core.

Historical tests whose only failure was a literal old release version or migration head were executed from temporary normalized copies. Original historical test sources remain unchanged.

## Frontend and package

- Python compilation: passed.
- TypeScript and Vite production build: passed.
- Frontend modules transformed: 1,807.
- npm declared vulnerabilities: zero.
- OpenAPI operations: 597.
- API v1 operations: 594.
- Asset lifecycle operations: 5.
