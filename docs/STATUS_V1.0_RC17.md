# CORVAX v1.0 RC17 Status

## Completed scope

- Corrected base profit or loss for `OTHER_INCOME` and future `OTHER_EXPENSE` groups.
- Corrected cumulative profit, equity and opening-equity calculations.
- Added profit-before-tax and other-income lines to the API and bilingual UI.
- Rebuilt the IAS 7 indirect cash-flow method with separately disclosed non-cash and working-capital adjustments.
- Added direct-method controls for unclassified cash journals.
- Added opening/closing cash reconciliation and a zero-difference control.
- Added explicit default IFRS 18 mappings for other income and other expenses.

## Scope intentionally not included

RC17 does not implement AR/AP invoice allocation, native aging, VAT return boxes, WHT, excise tax, zakat, income tax, asset disposal, landed cost or stock-count workflows. Those items remain in the approved finance sequence and must not be represented as complete.

## Deployment status

Staging / sanitized pilot / UAT only. No database migration is required; schema head remains `e17700000001`.
