# CORVAX v1.0 RC20 — Status

## Release scope

RC20 closes the agreed sequence for:

1. Import/export VAT treatment controls.
2. Landed cost for foreign purchases.
3. Recursive finished-product cost explosion.
4. Perpetual inventory, physical counts, aging, damage/expiry/NRV controls.
5. Budget versus actual versus historical analysis with automated comments.

## Import and export controls

- The foreign supplier invoice is recorded without Saudi VAT where applicable.
- The customs declaration separately records one treatment: `AT_CUSTOMS`, `THROUGH_RETURN`, `SUSPENDED`, or `EXEMPT`.
- A zero amount collected on the customs declaration is not silently interpreted as zero-rated purchasing; a reason is mandatory.
- `THROUGH_RETURN` self-accounts import VAT in both output and recoverable input VAT, subject to deductibility.
- Export sales stay in a pending-evidence VAT box until independently approved export evidence exists.

## Landed cost

Capitalizable charges are allocated to received inventory using value, quantity or equal allocation. Recoverable VAT is excluded from inventory cost. Nonrecoverable tax and directly attributable charges are capitalized where policy permits. Supplier invoices and GL postings are created with maker-checker controls.

## Cost roll-up

The engine recursively explodes nested BOMs and approved routings. It separately reports direct materials, packaging, direct labor, direct expenses, variable manufacturing overhead and fixed manufacturing overhead. Approved roll-ups update the finished item's standard cost only after preparation, review and independent approval.

## Perpetual inventory

Every stock movement remains in the inventory subledger. RC20 adds full/cycle count snapshots, frozen counts, approved count adjustments, aging, expiry, slow/obsolete classification, NRV write-downs, UOM conversions and inventory-subledger-to-GL reconciliation.

## Budget analytics

Approved budgets are compared with posted GL actuals and historical averages. Analysis supports daily, monthly and annual granularity and generates Arabic or English variance commentary with favorable/unfavorable interpretation by account type.

## Stage

`RELEASE_CANDIDATE_STAGING_UAT_ONLY`
