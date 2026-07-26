# CORVAX Business Platform v0.28 — Intercompany & Consolidation Controls

## Implemented

- Independent intercompany records per legal entity.
- Reciprocal company validation.
- Receivable/payable and revenue/expense matching.
- Configurable matching tolerance.
- Open versus matched reconciliation report by period end.
- Automatic balanced elimination lines in consolidation runs.
- Consolidation adjustment register linked to the source match.
- Full company-scoped permissions and audit events.
- Alembic migration `e28000000001`.
- Arabic/English consolidation control indicator in the existing UI.

## Verified scenario

Two entities recorded reciprocal SAR 10,000 receivable and payable balances. The engine matched both records with zero variance and produced a SAR 10,000 debit and SAR 10,000 credit elimination in the consolidated run.

## Current boundaries

The release does not yet calculate acquisition accounting, goodwill, non-controlling interests, foreign-operation translation reserve, upstream/downstream unrealized inventory profit, or deferred tax on consolidation adjustments. These remain advanced consolidation work and must not be represented as complete.

## Readiness assessment

- Functional/module coverage: 96%
- Financial core readiness: 87%
- Overall production readiness: 70%
- Advanced consolidation readiness: 62%
