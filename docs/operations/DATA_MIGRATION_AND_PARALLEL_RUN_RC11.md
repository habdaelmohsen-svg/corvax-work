# CORVAX RC11 — Data Migration and Parallel-Run Pack

This package provides repeatable validation tooling. **CR-03 remains open** until company data is migrated, departments sign UAT, and a complete parallel cycle is reconciled.

## Opening balances
CSV columns:
`company_code,account_code,debit,credit,branch_code,cost_center_code,description`

Dry run:
```bash
python backend/scripts/opening_balance_import.py opening_balances.csv --posting-date 2026-01-01
```
Apply after CFO approval and database backup:
```bash
python backend/scripts/opening_balance_import.py opening_balances.csv --posting-date 2026-01-01 --apply --user-id <migration-user>
```
The tool validates balanced totals per company, active companies, posting accounts, branches/cost centers, open periods, and records the source SHA-256 in the journal reference/evidence report.

## Parallel-run minimum scope
- Opening trial balance and audited financial statements.
- One full payroll cycle, WPS output and employee-level reconciliation.
- Sales/POS/VAT invoice totals and receivables.
- Purchase/AP/VAT and supplier balances.
- Inventory quantities, valuation and manufacturing cost close.
- Bank reconciliation and cash balances.
- Accruals, prepaids, fixed assets, leases and ECL.
- Period close, five statements and consolidation where applicable.

Every difference must have owner, cause, correction, retest and sign-off. Finance, HR, Operations, Quality, IT and Internal Audit must sign the final reconciliation.
