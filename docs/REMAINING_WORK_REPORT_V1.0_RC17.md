# Remaining Work after CORVAX RC17

## Next priority — RC18

Native customer and supplier aging:

- Allocate receipts to individual sales invoices.
- Allocate payments and credits to individual purchase invoices.
- Support partial allocations, advances, unapplied cash and reversals.
- Produce current, 1–30, 31–60, 61–90, 91–120 and over-120-day buckets.
- Reconcile customer and supplier subledgers to the general ledger.
- Load opening balances by party and invoice rather than one control-account total.

## Following finance sequence

1. VAT return classification and tax-code matrix.
2. Withholding tax, excise tax, zakat and income-tax engines.
3. Fixed-asset transfer, sale, disposal, write-off and impairment lifecycle.
4. Landed cost, stock counts, slow-moving, damaged stock and NRV.
5. Advanced costing, variances, joint/by-products and production hardening.

## Production gates

PostgreSQL load and concurrency, backup/restore drills, migration reconciliation, departmental UAT, a full parallel reporting cycle, integrations and independent assurance remain mandatory before production approval.
