# CORVAX Business Platform v0.24 — Prepaid Expense Policy

## Core rule
A payment is not expensed immediately when its economic benefit relates to future periods. The net service cost is recorded as a prepaid asset, while recoverable VAT is recorded separately. The prepaid asset is then amortized over the actual service period.

## Default and alternatives
- Default: `MONTHLY_STRAIGHT_LINE` over the actual start and end dates.
- Optional: `DAILY_PRORATA` for partial months or contracts requiring exact day allocation.
- Twelve months is a configurable default for annual contracts, not a mandatory assumption for every prepaid item.

## Initial payment entry
- Dr Prepaid Expenses — 117010
- Dr VAT Recoverable — 114010, when applicable
- Cr Bank

## Monthly amortization entry
- Dr Selected Expense Account
- Cr Prepaid Expenses — 117010

## Exact example requested
Contract period: 1 March 2026 to 28 February 2027
Net amount: SAR 12,000
Monthly allocation: SAR 1,000

At 31 December 2026:
- Expense recognized March–December: SAR 10,000
- Remaining prepaid debit balance: SAR 2,000
- January and February 2027 remain pending in the schedule.

## Close control
The month-end close review fails when a prepaid schedule due on or before the period end remains unposted. After the amortization run is posted, the control passes.

## Audit controls
- No duplicate schedule for the same prepaid item and period.
- Every payment and monthly amortization creates a posted journal.
- Branch and cost center dimensions flow to the journals.
- Creation and amortization runs are recorded in the audit trail.
- The remaining prepaid balance is included in current assets.
