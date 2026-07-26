# CORVAX v1.0 RC13 — Restaurant Operations & POS Completion Status

## Release position

RC13 is built directly on RC12 HR & Payroll Completion. It closes the principal internal restaurant/POS workflow gaps identified after the RC10 audit while preserving the accounting, manufacturing, HR/payroll, governance and assurance controls from prior releases.

RC13 is suitable for development, staging, sanitized pilot and departmental UAT. It is **not** approved as the sole financial book of record or as a certified production POS deployment until external assurance, data migration, hardware/provider testing and parallel operation are complete.

## Implemented in RC13

- Restaurant tables, capacity, area and controlled operating statuses.
- Reservations with capacity checks, overlap prevention and seated/completed/no-show lifecycle.
- Dine-in, takeaway and delivery order metadata.
- Cashier-shift opening, expected cash, counted cash, variance and independent close approval.
- Kitchen stations, menu routing and sequential KDS workflow.
- Controlled service completion and table release.
- Void and return request workflow with maker-checker approval, financial reversals and optional inventory restoration.
- Delivery-platform settlement batches with three-user segregation and zero-variance approval gate.
- Restaurant waste workflow with stock validation, approval and accounting posting.
- Offline POS transaction queue, SHA-256 payload identity, idempotency and conflict recording.
- Twelve new granular permissions and a dedicated Restaurant Manager role.
- Bilingual database-backed restaurant operations dashboard covering tables, reservations, KDS, shifts, orders, settlements, controls, waste and food cost.

## Technical facts

- Version: `1.0.0-rc13`.
- Migration head: `e17500000001`.
- Application tables: 194.
- Schema tables including `alembic_version`: 195.
- ORM entities: 193.
- API routers: 44.
- Frontend production build: 1,801 modules.

## Internal maturity estimate

- Restaurant operations and POS internal scope: approximately 89–92%.
- Overall internal system scope: approximately 94%.

These are management estimates, not independent assurance ratings. Full transaction-entry UX depth, POS hardware certification, payment-terminal integration, live delivery-platform APIs, real-device offline testing and production operating evidence remain outside the completed evidence.
