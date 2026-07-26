"""Static verification that no hard-coded operational demo endpoints remain."""
from pathlib import Path

MODULE_FILE = Path(__file__).resolve().parents[1] / "app" / "api" / "modules.py"
text = MODULE_FILE.read_text(encoding="utf-8")
assert "financial_statements" not in text
assert "budget_overview" not in text
assert "manufacturing_oee" not in text
assert "legacy_demo_endpoints\": \"REMOVED" in text
print("CORVAX module registry verified: legacy fixed-data endpoints removed")
