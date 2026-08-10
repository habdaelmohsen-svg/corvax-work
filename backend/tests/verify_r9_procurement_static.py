"""Static R9 procurement UI/API contract gate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "backend/app/api/procurement.py").read_text(encoding="utf-8")
MODEL = (ROOT / "backend/app/models/supply_chain.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / "frontend/src/dashboard/procurementWorkflowTab.tsx").read_text(encoding="utf-8")
PURCHASES = (ROOT / "frontend/src/dashboard/purchasesPage.tsx").read_text(encoding="utf-8")

for contract in ('@router.get("/workflow-center")', 'current_owner', 'stalled_days', 'price_variance_percent', 'control_flags'):
    assert contract in API, contract
for contract in ('SupplierProcurementProfile', 'pending_iban', 'approved_iban', 'iban_change_requested_by'):
    assert contract in MODEL, contract
for contract in ('workflow-drill-through', 'supplier-profile-save', 'supplier-iban-request', 'supplier-iban-approve'):
    assert contract in WORKFLOW, contract
assert 'Maker-checker: IBAN requester cannot approve' in API
assert 'purchase-duplicate-risk' in PURCHASES and 'duplicateRisk?.blocking' in PURCHASES
assert '@router.get("/suppliers/{supplier_id}/invoice-risk")' in API

print("CORVAX R9 PROCUREMENT STATIC CONTRACTS: PASS")
