"""Static UI/API contract gate for R9 inventory efficiency."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = (ROOT / "backend/app/api/inventory_traceability.py").read_text(encoding="utf-8")
MODEL = (ROOT / "backend/app/models/inbound_shipment.py").read_text(encoding="utf-8")
TRACE = (ROOT / "frontend/src/dashboard/inventoryTraceabilityPage.tsx").read_text(encoding="utf-8")
INVENTORY = (ROOT / "frontend/src/dashboard/inventoryRealPage.tsx").read_text(encoding="utf-8")

for contract in ('@router.post("/mobile-receipts"', '@router.get("/mobile-receipts/{grn_id}/inspection")', '@router.get("/alerts")',
                 "ensure_open_period", "Inspected quantity exceeds PO remaining quantity",
                 'reference_type="GOODS_RECEIPT"'):
    assert contract in API, contract
for field in ("barcode_value", "accepted_quantity", "rejected_quantity", "production_date",
              "storage_location", "evidence_metadata", "quality_status"):
    assert field in MODEL, field
for label in ("الاستلام المحمول بالباركود / QR", "capture=\"environment\"", "اعتماد الفحص وإنشاء GRN"):
    assert label in TRACE, label
assert "/api/v1/inventory/alerts?company_id=" in TRACE
assert "Inventory & procurement alerts" in INVENTORY

# Preserve the R8 placement decision: classification and NRV remain in Inventory.
assert "InventoryValuationControls" in INVENTORY and "'classify'" in INVENTORY and "'nrv'" in INVENTORY
for misplaced in ("items/classify", "nrv-assessment", "nrv-writedown", "تصنيف الأصناف", "تقييم NRV"):
    assert misplaced not in TRACE, misplaced

print("CORVAX R9 INVENTORY STATIC GATE: PASS")
