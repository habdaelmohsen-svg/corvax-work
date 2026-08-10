# CORVAX RC27.4 R9 — Platform Assurance Integration Record

This package is fully integrated into the R9 release branch. The sections below record the
completed bindings, migration contract, permissions and safeguards; they are not pending
release-integrator tasks.

## 1. Backend registration

1. `app.models.r9_platform` is registered through the model facade before metadata evaluation.
2. `app.api.r9_platform` is included with the common `/api/v1` prefix.
3. Do not enable production `AUTO_CREATE_SCHEMA`; deploy the Alembic revision first.

## 2. Alembic revision

Revision `e20500000001` follows the previous single head and creates, in dependency order:

1. `r9_platform_alerts`: integer PK; non-null company FK; fingerprint 64; category 30; severity 12;
   Arabic/English titles 250; JSON text details; source type/id; status; assignee/due; resolver,
   resolution and timestamps. Unique `(company_id, fingerprint)`. Index company, category,
   severity, status and detected time.
2. `r9_import_batches`: company FK; target; safe original filename; SHA-256; status; total/valid/
   invalid counts; validation summary; maker/validator/checker FKs and timestamps. Unique
   `(company_id, file_sha256, target_type)`.
3. `r9_import_rows`: batch FK with cascade delete; source row number; source/normalized/error JSON
   text and validation status. Unique `(batch_id, row_number)`.
4. `r9_restore_drills`: company FK, backup FK, isolated environment, result, integrity check,
   evidence notes, performer and time.
5. `r9_zatca_readiness`: one row per company; onboarding state, environment, hard-false production
   flag, four readiness booleans, validation/update times, notes and updater.
6. `r9_zatca_sandbox_submissions`: company/source identity, UUID, current/previous hash, QR metadata,
   validation result/errors, sandbox evidence state/correlation, maker and time. Unique
   `(company_id, invoice_uuid)`.

The downgrade must drop only these six tables in reverse order. It must not touch legacy
`e_invoices`, backups, audit logs or access-governance tables.

## 3. Permission seed and recommended assignment

| Permission | Minimum roles | Purpose |
|---|---|---|
| `platform.view` | Owner, CFO, Internal Audit, IT Operations | Read health, alerts, imports and readiness |
| `platform.manage` | IT Operations, Internal Audit lead | Scan controls, assign/resolve alerts, record restore drills |
| `import.stage` | Data migration operator | Upload and validate staging batches |
| `import.approve` | Financial Controller or designated checker | Approve staging; cannot be the batch maker |
| `zatca.manage` | Tax Manager and designated IT integration role | Maintain sandbox readiness and evidence |

Do not grant `import.stage` and `import.approve` to the same operational role. Super-admin may retain
both only under monitored emergency access. The endpoint still enforces maker-checker by user ID.

## 4. Frontend registration

1. `R9PlatformPage` is lazy-imported from `frontend/src/dashboard/r9PlatformPage.tsx` in `routes.tsx`.
2. Navigation includes System Assurance under Governance, protected by `platform.view`.
3. The page receives the selected `companyId` and language flag and never infers a company from a batch ID.

## 5. Production safeguards

- Health responses expose driver/pool counters only, never URLs, passwords, backup paths or tokens.
- Excel stays in staging. `APPROVED_STAGING_ONLY` is not a posting status. Each target needs a later,
  separately approved domain adapter with reconciliation before master/GL writes.
- ZATCA states are sandbox-only. No CSID, OTP or signing key is accepted or persisted here. A later
  official connector must use secret storage and ZATCA onboarding; it must not reinterpret this
  readiness evidence as production clearance.
- Schedule control scans and restore drills through the deployment scheduler only after the router,
  permissions and migration are live.

## 6. Verification commands

Run:

```bash
python backend/tests/verify_r9_platform_static.py
python backend/tests/verify_r9_platform_cycle.py
cd frontend && npm run build
```

The cycle test mounts the router independently, creates a fresh database, checks tenant isolation,
control-scan idempotency, alert evidence, Excel maker-checker, and sandbox-only ZATCA semantics.
