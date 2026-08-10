# CORVAX v1.0 Agreement Completion RC27.4 R9.1

هذه الحزمة هي خط الأساس المصحح بعد RC27.

## بيانات الإصدار المعتمدة

- Version: `1.0.0-agreement-completion-rc27.4-r9.1`
- Migration head: `e20500000001`
- Frontend production build: `2,042` modules — PASSED
- Backend compilation: PASSED
- Security, branch scope, health, RC20, RC21 and RC25 verification: PASSED in the RC27.2 execution round
- Migration head, readiness and release info are now derived from Alembic at runtime, not hard-coded

راجع `CORVAX_RC27_1_EXECUTION_REPORT_AR.md` و`CORVAX_AGREEMENT_MASTER_AR.md`.

## Deployment boundary

The internal software scope is complete for controlled staging, pilot and UAT. Production approval remains evidence-driven and cannot be asserted from code alone. It requires a real PostgreSQL staging/production environment, sanitized or approved real data, signed UAT, parallel operation, independent penetration/accounting/tax reviews and official credentials for ZATCA, banks, WPS/Mudad, Qiwa, Muqeem and GOSI.

Apply migrations through `e20500000001`; use `backend/.env.production.template`; do not enable demo seeding, UAT/Demo-data reset, or automatic schema creation in production.

## RC27.4 R9.1 — UAT reset and user-creation hotfix

- Added a guarded, system-wide UAT reset for the 279 operational tables while retaining the 20 access and accounting-foundation tables needed to continue testing.
- The reset is restricted to `SUPER_ADMIN`, non-production environments, `ALLOW_DATA_RESET=true`, an exact Arabic confirmation phrase, a dry run, a short-lived signed authorization token and audit logging.
- Usernames containing spaces are normalized safely (`Hussein Mahmoud` becomes `hussein.mahmoud`); a username can also be generated automatically from the English name.
- `render.yaml` in this package is intentionally configured for the `corvax-test` UAT service. Production must use `ENVIRONMENT=production` and `ALLOW_DATA_RESET=false`.
- R9.1 verification gate: `70/70` scripts passed in `837.8s`; frontend production build passed with `2,042` modules; migration head remains `e20500000001` (no schema migration required).

راجع `CORVAX_R9_1_UAT_HOTFIX_ACCEPTANCE_AR.md` قبل الرفع والتنفيذ.

## RC27.4 R8 Owner Findings Closure

- Executive KPI cards now open an authorized reporting view instead of a legacy route rejected by the navigation guard.
- The read-only system assistant wraps long answers and sources without horizontal overflow.
- Purchase requisitions can carry an optional suggested supplier, show its VAT number, and retrieve the latest actual posted GRN purchase price.
- Item classification and IAS 2 NRV assessment are located under Inventory & Warehouses, not shipment tracking.
- R9 verification gate: `69/69` scripts passed in `760.9s`; migration head `e20500000001`.

## Comprehensive Reporting Center

The `مركز التقارير الشامل / Comprehensive Reporting Center` implements the 57
approved VAT, financial-statement, sales, purchasing, inventory, ledger, cash,
asset, budget, audit, and close reports. Each run is permission-controlled,
period-aware, audit-logged, and fingerprinted. Exports are real XLSX workbooks
and print-ready bilingual PDF layouts with company/report/period/filter/user
metadata.


## RC27.2 UI Quality Closure

راجع `CORVAX_RC27_2_EXECUTION_REPORT_AR.md` و`backend/tests/verify_ui_quality_rc272.py`.


## RC27.4 Production UI Controls

- Production hides CRM, IT operations and FX sample-data actions unless both development mode and `VITE_ENABLE_DEMO_ACTIONS=true` are active.
- FX sample execution uses the current date instead of a hard-coded July 2026 date.
- Regression verification: `backend/tests/verify_production_ui_controls_rc273.py`.

## RC27.4 Production Data Guards

- Demo AR/AP document creation is hidden from production builds.
- Operational dates are generated dynamically at runtime.
- HR attendance defaults to the current calendar month.
- Regression guard: `backend/verify_rc274_production_data_guards.py`.
