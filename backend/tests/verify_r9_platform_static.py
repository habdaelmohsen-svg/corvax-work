"""Static contracts that prevent unsafe integration shortcuts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
api = (ROOT / "backend/app/api/r9_platform.py").read_text(encoding="utf-8")
models = (ROOT / "backend/app/models/r9_platform.py").read_text(encoding="utf-8")
ui = (ROOT / "frontend/src/dashboard/r9PlatformPage.tsx").read_text(encoding="utf-8")

for permission in ("platform.view", "platform.manage", "import.stage", "import.approve", "zatca.manage"):
    assert permission in api
assert "Maker-checker: batch creator cannot approve" in api
assert '"posted_to_master": False' in api
assert 'row.environment = "SANDBOX"' in api and "row.production_connected = False" in api
assert "Internal readiness evidence only; not a ZATCA acceptance or clearance" in api
for prohibited_column in ("csid = Column", "otp = Column", "private_key = Column", "database_url = Column"):
    assert prohibited_column.lower() not in models.lower()
for table in ("r9_platform_alerts", "r9_import_batches", "r9_import_rows", "r9_restore_drills", "r9_zatca_readiness", "r9_zatca_sandbox_submissions"):
    assert table in models
assert "لا يوجد ترحيل مباشر" in ui and "لا تثبت الربط الإنتاجي" in ui
print("CORVAX R9 PLATFORM STATIC CONTRACTS: PASS")
