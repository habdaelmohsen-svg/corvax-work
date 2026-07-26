# CORVAX v1.0 RC14 — Test Report

## Passed verification

- RC14 end-to-end gym lifecycle verification: **PASSED**.
- RC13 restaurant/POS regression verification: **PASSED**.
- Python application compilation: **PASSED**.
- Frontend TypeScript and Vite production build: **PASSED**, 1,801 modules transformed.
- npm dependency audit: **PASSED**, zero reported vulnerabilities at build time.
- Fresh Alembic migration to `e17600000001`: **PASSED**, 211 tables including `alembic_version`.
- Downgrade from RC14 to `e17500000001` and re-upgrade: **PASSED**.
- ZIP CRC/integrity and file SHA-256 manifest: required at packaging and recorded in the release manifest.

## RC14 end-to-end scenarios exercised

- Membership sale and branch assignment.
- Upgrade and freeze with independent approval.
- Frozen access denial and post-freeze access grant.
- Class capacity, waitlist, cancellation promotion and attendance.
- PT sale, session completion, deferred-revenue recognition and commission accrual.
- Three-user commission prepare/review/approve payout.
- Locker assignment and release on approved branch transfer.
- Cancellation to member credit and later credit use.
- IFRS 15 billed/recognized/deferred/refunded reconciliation.

## Qualification and limitations

The release-verification scripts are not a substitute for production-scale load testing, independent penetration testing, tenant-isolation assurance, hardware certification, company-data UAT or a parallel financial close. A complete historical regression sweep was initiated but not represented as fully completed in this report; RC13 and the new RC14 workflow were specifically rerun and passed.
