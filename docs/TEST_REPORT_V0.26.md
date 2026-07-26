# CORVAX Business Platform v0.26 — Test Report

## Accrual scenario verified

- Expense accrual created as draft for SAR 5,000.
- Period-close review detected and blocked the unposted draft.
- Accrual posted to expense and accrued-expense liability accounts.
- Period-close review detected the due automatic reversal.
- Reversal posted in the following open period.
- Duplicate reversal was prevented by persistent linkage.

## Recurring journal scenario verified

- Balanced monthly template created.
- Period close detected the due unprocessed template.
- One posted journal generated for the due date.
- Next run date advanced by one month.
- Duplicate run prevented by unique template/date control.

## Financial checks verified

- Accrued revenue included in current assets.
- Accrued expenses included in current liabilities.
- Trial balance remained balanced.
- Statement of financial position remained balanced.
- Audit events were recorded.

## Engineering checks passed

- Python application and migrations compile.
- Fresh Alembic migration through revision `e26000000001`.
- Fresh schema contains 96 tables.
- Upgrade from a seeded v0.24 database to v0.26.
- New permissions and accounts inserted during upgrade.
- React/TypeScript production build.
- Regression suites v0.10, v0.12, v0.14, v0.16, v0.18, v0.20, v0.22 and v0.24.
- v0.26 end-to-end verification.

Result: `CORVAX v0.26 accruals and recurring journals: ALL VERIFICATIONS PASSED`
