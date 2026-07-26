# CORVAX v1.0 RC17 Test Report

## New RC17 verification

The RC17 test posted an integrated September scenario containing:

- SAR 25,000 non-cash other income.
- SAR 10,000 depreciation.
- SAR 4,000 ECL/impairment.
- SAR 100,000 credit sale.
- SAR 50,000 inventory purchase on credit.
- SAR 60,000 customer receipt.
- SAR 20,000 supplier payment.
- A separate SAR 5,000 cash journal without cash-flow classification.

Verified results:

- Other income included in profit: PASSED.
- Statement of financial position balanced: PASSED.
- Depreciation and ECL added back: PASSED.
- Non-cash gain deducted: PASSED.
- Working-capital movements calculated by category: PASSED.
- Indirect operating cash reconciled to direct operating cash before the intentionally unclassified journal: PASSED.
- Unclassified journal retained in total cash movement and flagged: PASSED.
- Opening-to-closing cash difference: ZERO.
- Default IFRS 18 mapping for other income: PASSED.

## Regression verification

- Financial and subledger core v0.10: PASSED.
- Prepaid expenses v0.24: PASSED.
- Accruals and recurring journals v0.26: PASSED.
- Advanced financial reporting RC6: PASSED.
- Corporate reporting RC7: PASSED.
- Restaurant and POS RC13: PASSED.
- Gym operations RC14: PASSED.
- Gym departments and cafe RC15: PASSED.
- Enterprise work center RC16: PASSED.

## Not performed

- Independent penetration testing.
- Production PostgreSQL load and concurrency testing.
- Statutory tax validation against company filings.
- External auditor or IFRS specialist sign-off.
