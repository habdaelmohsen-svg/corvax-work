# CORVAX RC13 — Restaurant Operations and POS Control Policy

## Purpose

RC13 establishes a controlled restaurant operating cycle connected to inventory, VAT, cost of sales, cash management, delivery-platform receivables and the general ledger. It extends the existing POS engine without replacing the accounting, inventory or HR controls delivered in previous releases.

## Order and service controls

- Supported service modes are dine-in, takeaway and delivery.
- Dine-in orders require an active restaurant table and enforce table/reservation consistency.
- Each client order may carry a unique `client_order_id` to prevent duplicate posting.
- Menu items may be routed to a defined kitchen station. KDS status transitions are sequential: NEW → ACCEPTED → PREPARING → READY → SERVED.
- A table cannot be released through service completion while an associated kitchen ticket remains open.
- Recipe consumption creates inventory movements and food-cost accounting from the approved menu recipe.

## Cashier-shift controls

- The cashier opens a shift with a business date, branch, bank/cash account and opening balance.
- Only the opening cashier may submit the shift close.
- Expected cash is calculated from opening balance, posted cash sales and approved cash refunds.
- Counted cash and variance are retained permanently.
- A different authorized user must approve the close. A non-zero variance requires documented notes.

## Voids and returns

- Voids and returns are requests, not direct destructive edits.
- The requester cannot approve the same request.
- Approved requests create balanced revenue/VAT reversal journals.
- Inventory restoration is optional and, when selected, creates a COGS reversal and stock movement based on the original recipe consumption.
- Cumulative returned quantity cannot exceed the originally sold quantity.

## Delivery-platform settlements

- Delivery orders remain in platform receivables until settlement.
- Settlement batches reconcile gross sales, contractual commission, other fees, expected net, bank receipt and variance.
- Preparation, review and final approval require three different users.
- A settlement cannot be finally approved unless its variance is exactly zero.
- Approved settlement batches post the bank, commission expense and platform-receivable clearing journal.

## Waste controls

- Waste records require item, warehouse, branch, date, quantity, reason code and explanation.
- Available stock is checked before submission and again before posting.
- The preparer cannot approve the same waste record.
- Approval posts inventory reduction and restaurant-waste expense with a permanent stock movement and audit record.

## Offline controls

- Offline transactions use company, device and client-transaction identifiers plus a payload SHA-256 hash.
- Repeated submission of the same unchanged transaction is idempotent and returns the existing POS order.
- A reused identifier with a different payload is recorded as a conflict rather than silently posted.
- RC13 supplies the server-side offline queue and conflict foundation; field testing on the final POS hardware/browser remains required.

## Segregation of duties

RC13 adds a `RESTAURANT_MANAGER` role and granular permissions for tables, reservations, cashier shifts, KDS, controls, settlements, waste and offline synchronization. Financial approval permissions remain separated from restaurant preparation permissions.

## Scope limitation

RC13 does not certify physical POS devices, printers, payment terminals, delivery-platform APIs or production offline behavior. These require actual hardware, provider credentials, field testing and operational sign-off.
