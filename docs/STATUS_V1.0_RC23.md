# CORVAX Business Platform v1.0 RC23 Status

RC23 adds a controlled Saudi excise-tax engine, tax-warehouse stock records, taxable-release accounting, bi-monthly return preparation, GL reconciliation, payment and CSV-enabled bilingual operations.

## Release status

- Version: 1.0.0-rc23
- Migration head: e18400000001
- Stage: Release Candidate / Staging / UAT only
- Database tables: 248 including Alembic
- OpenAPI operations: 577
- API v1 routes: 574
- Excise-tax routes: 18
- Frontend build: 1,806 modules

## Production restrictions

This release is not approved as the sole production tax record or as a direct ZATCA filing mechanism. Official portal integration, customs data reconciliation, product classification validation, PostgreSQL load testing, real-data migration, parallel operation and independent tax/security review remain open.
