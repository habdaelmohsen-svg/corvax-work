# CORVAX RC27.4 R9.4 — Unified Comparative Reporting

هذه الحزمة هي خط الأساس المصحح بعد RC27.

## بيانات الإصدار المعتمدة

- Version: `1.0.0-agreement-completion-rc27.4-r9.4`
- Migration head: `e20200000001`
- DGTERA daily sales runbook: `docs/DGTERA_DAILY_SALES_INTEGRATION.md`
- DGTERA V8 uses the exact Branch Sales source-report date without the former Riyadh boundary shift; V6/V7 proofs are invalidated and history is reverified from `2025-01-01`.
- Frontend production build: `2,036` modules — PASSED
- Backend compilation: PASSED
- Security, branch scope, health, RC20, RC21 and RC25 verification: PASSED in the RC27.2 execution round
- Migration head, readiness and release info are now derived from Alembic at runtime, not hard-coded

راجع `CORVAX_RC27_1_EXECUTION_REPORT_AR.md` و`CORVAX_AGREEMENT_MASTER_AR.md`.

## Deployment boundary

The internal software scope is complete for controlled staging, pilot and UAT. Production approval remains evidence-driven and cannot be asserted from code alone. It requires a real PostgreSQL staging/production environment, sanitized or approved real data, signed UAT, parallel operation, independent penetration/accounting/tax reviews and official credentials for ZATCA, banks, WPS/Mudad, Qiwa, Muqeem and GOSI.

Apply migrations through `e20200000001`. The transaction/value reset is available only with `ENVIRONMENT=uat` and `ALLOW_DATA_RESET=true`; production rejects it unconditionally.

## R9.3 UAT transaction/value reset

- Visible action: **مسح الحركات والقيم التجريبية**.
- Deletes transaction documents and postings across all UAT companies.
- Preserves configured master cards, including parties, items, warehouses, employees, banks, vehicles, machines, fixed assets and company branding.
- Fixed-asset cards remain with zero cost/depreciation/NBV and can receive a new opening value from the Fixed Assets screen.
- Requires the `SUPER_ADMIN` role, `data.reset`, backup acknowledgement, exact phrase, safe preview and a signed 10-minute authorization.
- Focused gate: `backend/tests/verify_uat_full_reset.py`.
- Full release verification: `53/53` maintained verification gates passed.

## R9.3 usability and reporting

- Fixed chatbot layout collision and added an in-app Back button.
- Added journal printing and a bilingual, A4 business-report template.
- Report data and CSV export follow the active Arabic/English language.
- Added authenticated company-logo upload for printed reports and journals.
- Added a controlled Opening Balances screen for bank/asset/liability/equity GL balances, plus fixed-asset opening-value entry.

## R9.4 reporting and assistant remediation

- The AI assistant is rendered through a body-level portal, so the sticky header and its backdrop filter can no longer clip the dialog into a thin strip.
- Financial Statements and Reports Center now share one comparative engine and one visual hierarchy.
- Profit or loss, financial position and cash-flow reports show current period, previous period, same period last year, variance and variance percentage.
- Local calendar dates replace UTC date slicing, preventing 1 January from appearing as 31 December in UTC+ time zones.
- Print output uses a zero browser page margin, controlled audit footer, company logo, preparer, bilingual metadata and subtotal/total hierarchy.
- Demo seeding is disabled by default in local, Docker, UAT and production configuration; the delivered data directories are empty.

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
