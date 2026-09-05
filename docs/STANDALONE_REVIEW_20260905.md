# CORVAX standalone review — 2026-09-05

## Verified baseline

- GitHub main: e76fa31c0afe10f7aecfdf89c07c5084f272d7f3 (AUTH-R4).
- Local source tree exactly matched GitHub tree 2c33c15c35a16555d43b396a8eedd3b7ad7ba03d before edits.
- Render GET /api/v1/system/release: AUTH-R3, commit 1d52ec26e212467ab259d1b7e79f5f2799a291c7.
- Render GET /health/ready: ready, environment uat, database reachable, schema e20300000001, DGTERA scheduler enabled.
- A HEAD request returned 404; the successful GET is the health evidence. No inference about Auto-Deploy settings was made.

## Implemented in this branch

- Remove the registered external integration API and startup scheduler. Old worker entry points are inert. Connector construction rejects requests before creating a network client, regardless of stale scheduler environment settings.
- Remove external revenue substitution from financial statements. Posted general ledger supplies revenue, consistent with trial balance and other statement calculations.
- Remove dashboard external requests, automatic sync writes, external cards, navigation entry and external report. Native sales and restaurant operations replace external pages.
- Restaurant HTTP failures produce an error instead of an empty successful dataset.
- Distinct release identity STANDALONE-R1-20260905.
- Historical models and migrations remain for database compatibility. Existing imported data and encrypted connection credentials have NOT been deleted.

## Validation

Local SQLite test fixtures only; no production writes.

- Frontend TypeScript and Vite production build passed.
- verify_final_internal.py passed (costing, separation of approval duties, posting, closing and readiness flows).
- 17 additional suites passed: admin recovery/MFA, admin tenant source checks, branch scope, health contract, security source checks, and operational suites v010 through v032 at increments of two.
- Additional retirement guard covers connector rejection, inert scheduler even with the old enabled flag, removed route and ledger reporting source.
- These are script suites, not a claimed count of individual assertions. Some checks are static. They do not prove PostgreSQL, load, browser usability, or complete accounting acceptance.

## Unfinished work — do not call this a clean deployment

1. Connect the Render account and inspect service settings, build logs, database ownership and persistent disks. No authenticated Render management access was available in this turn.
2. Implement and validate a clean initialization path: bootstrap_first_admin currently calls seed_database, which creates demo parties, journals and operational records. Emptying the database and restarting would recreate demo data.
3. Replace the insecure default bootstrap password and remove/rework the recurring force-reset path, which currently disables MFA and does not provide a proper one-time recovery workflow. Existing emergency recovery links expired in August.
4. Before the authorized full reset, take and verify a recoverable snapshot; quiesce all writers; enumerate database tables, attachments and caches; remove all old business and integration data including stored connector credentials; provision fresh access and only the agreed system configuration. No destructive startup migration has been added.
5. Complete PostgreSQL migration and reset/restart tests, then verify table counts, no demo regeneration, no external traffic, login, company isolation, complete sales/purchase/cash/inventory/asset cycles, ledger/subledger and statement reconciliation, reports and exports on the actual deployed commit.
6. Only then deploy and verify release identity, health, logs and browser behavior. No data deletion, new admin credential, deployment or complete-system certification occurred in this turn.

User has already authorized removal, reset and repairs. The remaining external requirement is authenticated service access, not another approval of scope.
