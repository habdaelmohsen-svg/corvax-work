# CORVAX Business Platform v0.24 — Test Report

## Prepaid scenario verified
- Annual pest-control service: 1 March 2026 to 28 February 2027.
- Net prepaid amount: SAR 12,000.
- Twelve monthly schedules of SAR 1,000 generated.
- Before amortization, December close review failed with 10 due schedules.
- Amortization through 31 December posted 10 journals totaling SAR 10,000.
- Remaining debit prepaid balance: SAR 2,000.
- Two schedules remained pending for January and February 2027.
- December close prepaid control passed after posting.
- Statement of financial position remained balanced.
- Audit events were created.

## Fixed asset policy verified
- Asset placed in service after day 15 receives no depreciation in the month of addition.
- Existing regression tests were updated to the approved policy.

## Engineering checks passed
- Python application and migrations compile.
- Fresh Alembic migration through revision `e24000000001`.
- Fresh schema contains 92 tables.
- React/TypeScript production build.
- Regression suites v0.10, v0.12, v0.14, v0.16, v0.18, v0.20 and v0.22.
- v0.24 end-to-end prepaid verification.

Result: `CORVAX v0.24 prepaid expenses: ALL VERIFICATIONS PASSED`
