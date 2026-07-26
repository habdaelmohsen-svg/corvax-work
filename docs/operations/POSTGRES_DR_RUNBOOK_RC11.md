# PostgreSQL Disaster-Recovery Drill — RC11

The code package contains an executable isolated-restore tool. The audit finding remains **open pending execution on independent infrastructure and signed RPO/RTO**.

1. Provision an empty isolated PostgreSQL server in a different failure domain.
2. Set `SOURCE_DATABASE_URL` and `TARGET_DATABASE_URL` as secrets.
3. Run `python backend/scripts/postgres_dr_drill.py`.
4. Apply `alembic current`, log in, verify company counts, trial balances, attachments, audit-chain integrity and encryption-key access.
5. Measure backup data age (RPO) and elapsed restoration time (RTO).
6. Security, IT and Finance sign the evidence file. Target: RPO ≤15 minutes and RTO ≤4 hours.
7. Destroy the isolated restored copy according to the data-retention policy.
