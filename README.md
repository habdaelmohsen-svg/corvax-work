# CORVAX RC27.4 R9.2 — UAT Clean Slate

هذه الحزمة هي خط الأساس المصحح بعد RC27.

## بيانات الإصدار المعتمدة

- Version: `1.0.0-agreement-completion-rc27.4-r9.2`
- Migration head: `e19700000001`
- Frontend production build: `1,808` modules — PASSED
- Backend compilation: PASSED
- Security, branch scope, health, RC20, RC21 and RC25 verification: PASSED in the RC27.2 execution round
- Migration head, readiness and release info are now derived from Alembic at runtime, not hard-coded

راجع `CORVAX_RC27_1_EXECUTION_REPORT_AR.md` و`CORVAX_AGREEMENT_MASTER_AR.md`.

## Deployment boundary

The internal software scope is complete for controlled staging, pilot and UAT. Production approval remains evidence-driven and cannot be asserted from code alone. It requires a real PostgreSQL staging/production environment, sanitized or approved real data, signed UAT, parallel operation, independent penetration/accounting/tax reviews and official credentials for ZATCA, banks, WPS/Mudad, Qiwa, Muqeem and GOSI.

Apply migrations through `e19700000001`. The full clean-slate reset is available only with `ENVIRONMENT=uat` and `ALLOW_DATA_RESET=true`; production rejects it unconditionally.

## R9.2 UAT clean-slate reset

- Visible top-level action: **مسح بيانات UAT وبدء الإدخال**.
- Deletes all added business/master/transaction data across the UAT database.
- Preserves companies, branches, chart of accounts, periods, users, roles, permissions, sessions, audit trail and backups.
- Requires the `SUPER_ADMIN` role, `data.reset`, backup acknowledgement, exact phrase, safe preview and a signed 10-minute authorization.
- Focused gate: `backend/tests/verify_uat_full_reset.py`.


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
