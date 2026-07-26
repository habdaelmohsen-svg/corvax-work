# CORVAX Final Production Evidence Runbook

## 1. PostgreSQL staging

Create a sanitized PostgreSQL clone with the intended production major version. Set `SEED_DEMO_DATA=false` and `AUTO_CREATE_SCHEMA=false`, then run:

```bash
alembic upgrade head
python backend/scripts/postgres_smoke.py --url "$DATABASE_URL"
```

Expected head: `e18800000001`. Archive JSON evidence, database logs and deployment hash.

## 2. Load and concurrency

Use the corrected Locust profile in `backend/tests/performance/locustfile.py` against disposable staging. Execute baseline, normal, target, stress and soak stages documented under `docs/performance/`. Preserve CSV, HTML, Prometheus and PostgreSQL evidence.

## 3. Backup and disaster recovery

Use separate source and target databases:

```bash
python backend/scripts/postgres_dr_drill.py --source "$SOURCE_DATABASE_URL" --target "$TARGET_DATABASE_URL"
```

Record measured RPO/RTO and obtain infrastructure-owner sign-off.

## 4. Data migration

Load approved masters and opening balances using controlled import files. Reconcile GL, AR, AP, inventory, fixed assets, leases, payroll, taxes and retained earnings to signed legacy balances. No unexplained difference may remain.

## 5. UAT and parallel run

Obtain signed UAT from Finance, Supply Chain, Manufacturing, HR, Restaurant, Gym, Operations, IT and Executive Management. Run at least one complete financial/payroll/tax cycle in parallel and reconcile outputs.

## 6. Independent reviews

Complete penetration testing and independent accounting/tax review. Track every finding to closure or formally accepted residual risk.

## 7. Official integrations

Activate only with official credentials and certification for ZATCA, banks, WPS/Mudad, Qiwa, Muqeem, GOSI and approved devices. Store credentials in a secret manager, never in source files.
