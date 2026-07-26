# Credit Notes, Returns and VAT Policy — RC21

1. A return must reference a posted original invoice and one or more original invoice lines.
2. The user cannot override the original tax code or tax rate through the credit-note entry screen.
3. Total credited quantity, including drafts and pending notes, cannot exceed the original invoiced quantity unless an earlier note is rejected.
4. The credit-note date cannot precede the original invoice date and must fall in an open accounting period.
5. A VAT period already approved cannot accept a back-dated credit note. The adjustment must be issued in the current permitted period according to approved tax policy.
6. The maker and submitter cannot approve or post their own credit note.
7. Sales returns may use `RETURN_TO_STOCK`, `QUARANTINE`, `DAMAGED` or no inventory effect as operationally appropriate; only restorable/quarantine quantities create stock and COGS reversal in RC21.
8. Purchase returns use `RETURN_TO_SUPPLIER`; stock leaves at carrying cost, while the supplier credit follows the original supplier invoice amount and tax.
9. Any excess credit after reducing the original open item becomes a controlled customer or supplier credit balance.
10. Credit balances can be applied only to open items belonging to the same company, party and ledger, or settled through an authorized bank transaction.
11. Every financial and stock effect retains the credit-note number, original invoice reference, approving user and journal reference.
12. The internal structured credit-note output is not a claim of production ZATCA clearance or reporting integration.
