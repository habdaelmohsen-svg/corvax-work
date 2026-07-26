# CORVAX v1.0 RC15 Test Report

## Passed checks

1. Python compile for application and migration modules.
2. RC15 end-to-end verification:
   - department entitlement and access;
   - swimming trainer/class/facility linkage;
   - paid padel booking;
   - maker cannot approve own booking;
   - independent approval and accounting journal;
   - overlapping booking rejection;
   - cancellation and refund reversal;
   - gym cafe member pricing;
   - recipe/inventory-based cafe sale;
   - restaurant/cafe business-unit separation;
   - commercial summary and product catalogue.
3. RC14 gym-operation regression verification.
4. RC13 restaurant/POS regression verification.
5. Module registry and legacy fixed-data endpoint verification.
6. Frontend TypeScript and Vite production build: 1,801 modules.
7. npm audit: zero reported vulnerabilities at build time.
8. Fresh Alembic upgrade to `e17700000001`: passed.
9. Schema after upgrade: 217 tables including Alembic.
10. Downgrade to `e17600000001` and re-upgrade to `e17700000001`: passed.
11. Application route count: 479 `/api/` routes and 46 API tag groups.

## Not performed in this build environment

- Independent SAST/DAST and penetration testing.
- Physical POS, receipt-printer, payment-terminal and access-gate certification.
- Production PostgreSQL load, failover and disaster-recovery exercises.
- Full historical verification-script replay for every legacy release.
- Real-company data migration and full parallel financial close.

## Result

RC15 scope verification passed. This is a release-candidate verification, not production certification.
