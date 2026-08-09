# CORVAX v1.0 Agreement Completion RC27.4 R8

هذه الحزمة هي خط الأساس المصحح بعد RC27.

## بيانات الإصدار المعتمدة

- Version: `1.0.0-agreement-completion-rc27.4-r8`
- Migration head: `e20400000001`
- Frontend production build: `2,041` modules — PASSED
- Backend compilation: PASSED
- Security, branch scope, health, RC20, RC21 and RC25 verification: PASSED in the RC27.2 execution round
- Migration head, readiness and release info are now derived from Alembic at runtime, not hard-coded

راجع `CORVAX_RC27_1_EXECUTION_REPORT_AR.md` و`CORVAX_AGREEMENT_MASTER_AR.md`.

## Deployment boundary

The internal software scope is complete for controlled staging, pilot and UAT. Production approval remains evidence-driven and cannot be asserted from code alone. It requires a real PostgreSQL staging/production environment, sanitized or approved real data, signed UAT, parallel operation, independent penetration/accounting/tax reviews and official credentials for ZATCA, banks, WPS/Mudad, Qiwa, Muqeem and GOSI.

Apply migrations through `e20400000001`; use `backend/.env.production.template`; do not enable demo seeding, Demo-data reset, or automatic schema creation in production.

## RC27.4 R8 Owner Findings Closure

- Executive KPI cards now open an authorized reporting view instead of a legacy route rejected by the navigation guard.
- The read-only system assistant wraps long answers and sources without horizontal overflow.
- Purchase requisitions can carry an optional suggested supplier, show its VAT number, and retrieve the latest actual posted GRN purchase price.
- Item classification and IAS 2 NRV assessment are located under Inventory & Warehouses, not shipment tracking.
- Clean verification gate: `63/63` scenarios passed; migration head: `e20400000001`.

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
