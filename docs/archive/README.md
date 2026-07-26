# Superseded reports

Everything in this folder documents an EARLIER state of CORVAX and is kept only as
a record of decisions. **Do not treat any figure here as current.**

These files were moved out of the repository root because they quoted a stale
migration head and stale module counts, which misled a later audit into reporting
defects that had already been fixed.

The authoritative, live values are produced by the running system:

| What | Where to read it |
|------|------------------|
| Migration head | `GET /health/ready` -> `migration_head` |
| Release info | `GET /api/v1/modules` |
| Applied revisions | `alembic current` / `alembic heads` |

Nothing in the application reads these documents.
