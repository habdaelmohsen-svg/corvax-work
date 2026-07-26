# CORVAX RC19 Test Report

## RC19 functional verification

**Passed**

The verification created and posted transactions using:

- S15 standard-rated sales.
- S0 zero-rated domestic sales.
- SEX zero-rated exports.
- SE exempt sales.
- SOOS out-of-scope sales.
- P15 standard domestic purchases.
- P0 zero-rated purchases.
- PE exempt purchases.
- PIMP15 imports with VAT paid at customs.
- PRC15 reverse-charge purchases.
- PND15 non-deductible VAT purchases.

Verified results:

- Standard-rated sales base: SAR 1,000.
- Sales output VAT: SAR 150.
- Reverse-charge output VAT: SAR 75.
- Total output VAT: SAR 225.
- Recoverable input VAT: SAR 315.
- Net VAT: SAR (90).
- Output and input VAT differences to GL: zero.
- Non-deductible VAT was expensed and not deducted.
- Creator/submitter self-approval was blocked.
- Approved VAT return regeneration was blocked.
- Draft regeneration produced one clean set of return lines.

## Migration verification

- Clean database upgrade to `e17900000001`: passed.
- Downgrade to RC18: passed.
- Re-upgrade to RC19: passed.
- Tables including Alembic: 221.

## Regression verification

Passed:

- RC18 AR/AP allocation and aging.
- RC17 statements and IAS 7 cash flows.
- RC16 work center.
- RC15 gym departments and cafe.
- RC14 gym operations.
- RC13 restaurant/POS.
- v0.16 compliance/security/close.
- v0.14 enterprise engines.
- v0.12 operational engines.
- v0.10 financial core.

## Frontend and dependency verification

- TypeScript build: passed.
- Vite production build: passed.
- Modules transformed: 1,802.
- npm audit declared vulnerabilities: 0.

## Not run

- PostgreSQL concurrency and load test.
- ZATCA sandbox filing.
- Production certificates and CSID.
- Real company UAT and parallel return preparation.
