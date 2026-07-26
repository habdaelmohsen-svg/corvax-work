# CORVAX RC14 — Remaining Work Report

## Executive conclusion

RC14 raises estimated internal readiness to approximately 95%. The remaining two percentage points toward the 97% internal target are not cosmetic: they are concentrated in enterprise-wide user experience, reporting depth, manufacturing edge cases and production hardening. External integrations and independent assurance are excluded from the internal percentage and remain mandatory before production reliance.

## Internal work remaining

### 1. Enterprise UX and operational depth — RC15
- Replace remaining API/demo-oriented screens with full controlled forms and work queues.
- Add global search, saved views, bulk operations, drill-down and cross-module navigation.
- Standardize print, PDF and Excel outputs across finance, HR, manufacturing, restaurant and gym modules.
- Complete notification/escalation center and real-device PWA/offline testing.
- Perform accessibility, responsive, RTL/LTR and browser/device regression.

### 2. Manufacturing and costing — RC16
- Complete periodic actual-cost roll-up for multilevel BOMs and production variances.
- Finish subcontracting, by-products, co-products, rework and alternate-resource scenarios.
- Add production-scale performance tests and optimize expensive database queries.
- Rehearse PostgreSQL migration, backup, point-in-time recovery and restore evidence.
- Complete controlled import/migration and opening-balance reconciliation tooling.

### 3. Quality assurance depth
- Expand unit, integration, authorization and tenant-isolation coverage beyond release verification scripts.
- Conduct concurrency, idempotency and high-volume tests for payroll, POS, inventory, posting and gym access.
- Complete formal defect triage, user acceptance evidence and sign-off matrices.

## External and operational blockers

- ZATCA production onboarding, signing, clearance/reporting and certified e-invoicing validation.
- Official bank, WPS, Mudad, Qiwa, Muqeem, GOSI and other Saudi platform integrations.
- Physical POS, printers, payment terminals, access gates and delivery-provider certification.
- Independent penetration test and remediation sign-off.
- Real company data migration and reconciliation.
- Departmental UAT and one complete parallel financial/reporting cycle.
- Production load/stress testing and PostgreSQL disaster-recovery drill.
- External IFRS and actuarial validation against the company’s contracts and employee data.

## Current release decision

RC14 may proceed to staging, sanitized pilot and departmental UAT. It must not yet replace the official accounting books or be treated as a certified production platform.
