# CORVAX Business Platform v0.22 — Maintenance Control

## Implemented in this release
- Preventive maintenance plans by calendar interval or equipment meter.
- Automatic generation of due preventive work orders.
- Duplicate-open-work-order protection for the same plan and asset.
- Maintenance spare-parts master with on-hand quantity, reorder level and average cost.
- Spare-parts issue to work orders with stock validation and automatic cost accumulation.
- Calibration records with result, certificate reference and next due date.
- Alerts for low spare-parts stock, overdue calibration and due preventive plans.
- Full audit-trail events for plans, parts issues and calibration.
- Alembic migration from v0.20 to v0.22.

## Current assessment
- Functional/module coverage: 95% (prototype and connected-engine scope).
- Financial core readiness: 84%.
- Overall production readiness: 67%.

## Still required before formal production use
- Full enterprise asset hierarchy and maintenance labor scheduling.
- Purchase requisitions generated from spare-parts reorder alerts.
- Calibration approval workflow and certificate attachments.
- Advanced reliability metrics (MTBF by failure mode, Weibull analysis).
- ZATCA production onboarding and external integrations.
- Penetration, load, disaster-recovery and full UAT testing.
