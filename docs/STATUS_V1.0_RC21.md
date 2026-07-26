# CORVAX v1.0 RC21 — Status

## Release scope

RC21 closes the tax and accounting gap for sales and purchase returns. It creates invoice-linked credit notes, preserves original line tax treatment, posts the financial and inventory reversals, updates native AR/AP open items, and reports VAT adjustments in the credit-note period.

## Sales returns

- Full, partial and repeated credit notes are controlled by the original invoice-line quantity.
- The original revenue account, tax code, tax rate and invoice reference are retained.
- Approved credit notes debit revenue and output VAT and credit accounts receivable.
- Returned inventory can be restored to available stock or quarantine, with COGS reversal at carrying cost.
- If the invoice is already settled, the credit becomes an open customer balance that can be applied to another invoice or refunded through a bank account.

## Purchase returns

- Supplier credit notes are linked to the original posted purchase invoice and supplier reference.
- The supplier balance and recoverable input VAT are reversed in the credit-note period.
- Stock returned to the supplier is removed at current carrying cost.
- Differences between carrying cost, including landed cost, and the supplier net credit are posted to explicit purchase-return gain or loss accounts.
- Excess supplier credits are retained as supplier credit balances for later application or cash receipt.

## VAT return treatment

- Original invoices remain in their original VAT period.
- Credit notes enter the VAT return as negative adjustments in the credit-note date period.
- Standard, zero-rated, exempt, out-of-scope, export, reverse-charge, import-through-return and non-deductible treatments inherit the original line's tax code.
- Export credit notes reverse the final export box only when the original export evidence is approved; otherwise they reverse the pending-evidence control box.
- An approved VAT-return period blocks posting a credit note dated inside that period.
- VAT-to-GL reconciliation includes general credit notes and POS return controls.

## Workflow and evidence

- Draft → pending approval → independently approved and posted.
- The maker or submitter cannot approve the credit note.
- Rejected records remain in the audit trail.
- UTF-8 CSV export is available.
- A structured internal sales credit-note document uses document type code 381 and links to the original invoice. Production ZATCA submission still requires CSID, signing and official integration.

## Stage

`RELEASE_CANDIDATE_STAGING_UAT_ONLY`
