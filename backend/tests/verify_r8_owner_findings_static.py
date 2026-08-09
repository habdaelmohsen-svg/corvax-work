"""Static regression gate for the four owner findings reported from Render."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGETS = (ROOT / "frontend/src/dashboard/executiveNavigation.ts").read_text(encoding="utf-8")
AI_CSS = (ROOT / "frontend/src/styles/rc27_4_ai_assistant_h5.css").read_text(encoding="utf-8")
PURCHASE_UI = (ROOT / "frontend/src/dashboard/procurementWorkflowTab.tsx").read_text(encoding="utf-8")
PROCUREMENT_API = (ROOT / "backend/app/api/procurement.py").read_text(encoding="utf-8")
INVENTORY = (ROOT / "frontend/src/dashboard/inventoryRealPage.tsx").read_text(encoding="utf-8")
VALUATION = (ROOT / "frontend/src/dashboard/inventoryValuationControls.tsx").read_text(encoding="utf-8")
TRACEABILITY = (ROOT / "frontend/src/dashboard/inventoryTraceabilityPage.tsx").read_text(encoding="utf-8")
MIGRATION = (ROOT / "backend/migrations/versions/e20400000001_pr_supplier_context.py").read_text(encoding="utf-8")

# Executive KPIs must target a visible, permission-authorised navigation item.
assert "revenue: 'reports'" in TARGETS
assert ": 'finance'" not in TARGETS and ": 'aging'" not in TARGETS

# No answer/source string may widen the AI drawer and create horizontal scroll.
assert "overflow-x: hidden" in AI_CSS
assert "overflow-wrap: anywhere" in AI_CSS

# The purchase requisition visibly carries the optional supplier context, VAT
# master-data field, and actual receipt-backed latest purchase reference.
for contract in (
    'data-testid="pr-suggested-supplier"',
    'data-testid="pr-supplier-vat"',
    'data-testid="pr-last-purchase"',
    'data-testid="pr-use-last-price"',
    "/last-purchase?company_id=",
):
    assert contract in PURCHASE_UI, contract
assert '@router.get("/items/{item_id}/last-purchase")' in PROCUREMENT_API
assert 'GoodsReceipt.status == "POSTED"' in PROCUREMENT_API
assert 'suggested_supplier_id' in MIGRATION

# Classification and NRV belong to Inventory & Warehouses, never shipment
# traceability. The traceability screen now contains shipment controls only.
assert "InventoryValuationControls" in INVENTORY
assert "'classify'" in INVENTORY and "'nrv'" in INVENTORY
assert "تصنيف الأصناف وسياسة التقييم" in VALUATION
assert "تقييم صافي القيمة القابلة للتحقق NRV" in VALUATION
for misplaced in ("items/classify", "nrv-assessment", "nrv-writedown", "تصنيف الأصناف", "تقييم NRV"):
    assert misplaced not in TRACEABILITY, misplaced

print("CORVAX R8 OWNER FINDINGS STATIC GATE: PASS")
