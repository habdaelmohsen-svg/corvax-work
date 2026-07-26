# CORVAX RC12 — HR and Payroll Control Policy

## Payroll calculation inputs

Payroll calculations may use only approved and auditable sources:

- approved employee contract and salary components;
- assigned shift and scheduled working days;
- attendance records, late minutes and approved manual corrections;
- approved paid and unpaid leave;
- approved overtime requests;
- approved earnings and deduction adjustments;
- approved company payroll policy and GOSI basis.

## Required workflow

In strict mode, payroll follows the statuses below:

`CALCULATED → REVIEWED → APPROVED_POSTED → WPS ACCEPTED → PAID`

The preparer cannot review the same payroll run. The approver cannot be the preparer or reviewer. Direct posting is disabled. The analysis hash is recomputed before review and approval; any underlying change blocks the workflow.

## Attendance control

Each company policy defines the minimum attendance-completeness percentage. Runs below the threshold require a documented reviewer override and remain visible in the audit trail.

## WPS control

- WPS file content is regenerated from database lines and verified against its SHA-256 hash before download.
- Employee IBAN and bank code are mandatory.
- Employee-level acceptance or rejection details are retained.
- Payment is blocked in strict mode until the batch status is `ACCEPTED`.
- Official transmission remains provider-specific and requires official credentials.

## Employee-benefit valuation

The RC12 valuation workflow provides documented assumptions, employee-level present-value calculations, analysis-hash integrity and three-user approval. It is a management-support tool. External actuarial validation remains mandatory for financial reporting where required.
