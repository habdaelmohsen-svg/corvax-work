# CORVAX v1.0 RC12 — HR & Payroll Completion Status

## Release position

RC12 completes the next internal workstream after the RC10 independent audit and RC11 technical remediation. It upgrades HR and payroll from a foundational module to a controlled, database-backed workflow suitable for staging, sanitized pilot and departmental UAT.

RC12 is **not** approved as the sole financial book of record. Official WPS/bank transmission, government-platform integrations, production data migration, parallel run, independent penetration testing and external actuarial/IFRS validation remain outside the evidence available in this release.

## Implemented in RC12

- Payroll policy by company with independent approval.
- Employee contracts with maker-checker approval and salary terms synchronized to the employee master.
- Attendance, paid/unpaid leave, absence, lateness and approved overtime integrated into payroll calculation.
- Three-user payroll workflow: calculate → review → approve and post → WPS → pay.
- SHA-256 payroll analysis integrity check before review and approval.
- Attendance-completeness control gate with documented reviewer override.
- Payroll adjustments with prepare-review-approve segregation.
- WPS batch generation, file-integrity hash, employee-level results, rejection codes and response reconciliation.
- Payment blocked in strict mode until the WPS batch is accepted.
- Sensitive employee, bank and salary fields stored through the existing encrypted field type.
- Employee-benefit assumptions and valuation support workflow with prepare-review-approve and journal posting.
- HR_MANAGER role and granular permissions for contracts, overtime, adjustments, payroll review/approval, WPS and benefit valuations.
- New bilingual HR/payroll dashboard using database data; the former one-click demo payroll action was removed.

## Technical facts

- Migration head: `e17400000001`.
- Application tables: 181.
- Schema tables including `alembic_version`: 182.
- ORM entities: 180.
- API routers: 43.
- Frontend production build: 1,801 modules.

## Strict limitations

The employee-benefit valuation is a controlled management-support model based on documented assumptions. It does not constitute an independent actuarial valuation and does not replace a qualified actuary's report for IAS 19 reporting.

The WPS implementation creates and reconciles controlled files and responses. It does not transmit to a bank or Mudad without official credentials and a provider-specific adapter.

## Internal maturity estimate

- HR operations and payroll internal scope: approximately 85–88%.
- Overall internal system scope: approximately 93%.

The estimate excludes official external integrations and does not override the qualified production opinion from the independent audit.
