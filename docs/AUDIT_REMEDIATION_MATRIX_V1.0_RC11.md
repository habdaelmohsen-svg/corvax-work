# RC10 Independent Audit — RC11 Remediation Matrix

Status meanings:

- **CLOSED-INTERNAL**: code and automated verification completed.
- **IMPLEMENTED-PENDING-ASSURANCE**: code exists and tests pass, but independent professional or real-data validation remains.
- **PARTIAL**: tooling or preparation exists, but the audit condition is not closed.
- **OPEN-EXTERNAL**: cannot be closed without official credentials or independent parties.

| Finding | RC11 status | Evidence / remaining condition |
|---|---|---|
| CR-01 ZATCA Phase 2 | OPEN-EXTERNAL | Local foundation retained. CSID, XAdES, clearance/reporting and official certification remain required. |
| CR-02 Independent penetration test | PARTIAL | Bandit SAST report has zero findings; independent SAST/DAST/API/network pentest is still required. |
| CR-03 Migration and parallel run | PARTIAL | Opening-balance tool and runbook added; no company migration, UAT sign-off or parallel cycle has occurred. |
| HI-01 Custom HMAC token | CLOSED-INTERNAL | Replaced by RS256 JWT, `kid`, standard claims and public-key verification. |
| HI-02 IFRS 9 simplified only | IMPLEMENTED-PENDING-ASSURANCE | General approach, stages 1–3, PD/LGD/EAD, SPPI, SICR and forbearance added; IFRS advisor and real-data parallel validation remain. |
| HI-03 IFRS 16 complex cases | IMPLEMENTED-PENDING-ASSURANCE | Variable payments, sale-and-leaseback and subleases added; prior modification and partial-termination flows retained. Real-contract validation remains. |
| HI-04 Field-level encryption | CLOSED-INTERNAL | AES-GCM encrypted string/decimal types applied to IBAN, tax/registration and payroll salary fields. Production requires externally managed key ring. |
| HI-05 Finite capacity scheduling | CLOSED-INTERNAL | Work-center daily calendars and capacity allocation status added to MRP. |
| HI-06 Lead times, PO receipts, lot sizing | CLOSED-INTERNAL | Supplier-item planning, open purchase receipts, lead-time back scheduling and FOQ/LFL/min/max/multiple rules added. |
| HI-07 Load testing | PARTIAL | Locust profile and acceptance plan added. Target production test has not been executed. |
| HI-08 Disaster recovery drill | PARTIAL | PostgreSQL DR/PITR runbook and automation added. Isolated-server drill and signed RPO/RTO remain. |
| HI-09 Fixed demo financial endpoints | CLOSED-INTERNAL | Fixed-number endpoints removed; module summary declares legacy demo endpoints removed. |
| HI-10 Dashboard monolith | CLOSED-INTERNAL | Dashboard is a 13-line route host; pages are lazy-loaded and grouped by domain using React Router and Zustand. |
| HI-11 entities.py monolith | CLOSED-INTERNAL | Models split across 17 domain files; largest file is 344 lines. |
| HI-12 datetime.utcnow | CLOSED-INTERNAL | No usage remains under `backend/app`. |
| HI-13 API rate limiting | CLOSED-INTERNAL | Middleware enforces login, refresh, MRP, write and read limits; automated 429 test passes. |
| HI-14 Refresh token mechanism | CLOSED-INTERNAL | Rotating one-time refresh tokens with hashed storage, parent-session lineage and replay rejection. |
| HI-15 Banks/WPS/GOSI/Qiwa/Mudad/Muqeem | OPEN-EXTERNAL | Official agreements, credentials, sandbox and production access remain required. |

## Conclusion

RC11 closes or materially remediates the internal code findings, but it does not close the audit's three critical conditions. A second audit should verify the code remediations and keep the production opinion qualified until independent security assurance and operational evidence are supplied.
