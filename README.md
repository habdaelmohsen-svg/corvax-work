# CORVAX v1.0 Agreement Completion RC27.4

هذه الحزمة هي خط الأساس المصحح بعد RC27.

## بيانات الإصدار المعتمدة

- Version: `1.0.0-agreement-completion-rc27.4`
- Migration head: `e19500000001`
- Frontend production build: `1,808` modules — PASSED
- Backend compilation: PASSED
- Security, branch scope, health, RC20, RC21 and RC25 verification: PASSED in the RC27.2 execution round
- Migration head, readiness and release info are now derived from Alembic at runtime, not hard-coded

راجع `CORVAX_RC27_1_EXECUTION_REPORT_AR.md` و`CORVAX_AGREEMENT_MASTER_AR.md`.

## Deployment boundary

The internal software scope is complete for controlled staging, pilot and UAT. Production approval remains evidence-driven and cannot be asserted from code alone. It requires a real PostgreSQL staging/production environment, sanitized or approved real data, signed UAT, parallel operation, independent penetration/accounting/tax reviews and official credentials for ZATCA, banks, WPS/Mudad, Qiwa, Muqeem and GOSI.

Apply migrations through `e19500000001`; use `backend/.env.production.template`; do not enable demo seeding or automatic schema creation in production.


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
