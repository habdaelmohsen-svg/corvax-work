# CORVAX Business Platform v0.24 — Prepaid Expenses & Asset Policy Correction

## Implemented
- Persistent prepaid expense register by company.
- Exact service start and end dates.
- Monthly straight-line and daily-prorata allocation methods.
- Automatic schedule generation across financial years.
- Initial payment journal with separate recoverable VAT.
- Monthly automatic amortization journals.
- Real-time amortized and remaining debit balances.
- Current-asset presentation in the statement of financial position.
- Blocking month-end close control for due unposted amortization.
- Audit trail and company-level permissions.
- Arabic/English connected UI page.

## Fixed assets correction
The 15-day convention is now applied as approved:
- In service on or before day 15: full-month depreciation.
- In service after day 15: no depreciation in that month; full depreciation begins next month.

The previous half-month behavior was removed.

## Current assessment
- Functional/module coverage: 96% within the connected prototype scope.
- Financial core readiness: 87%.
- Overall production readiness: 70%.

These percentages are estimates, not legal, audit, tax, or production certification.
