from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "frontend" / "src" / "dashboard"

finance = (DASHBOARD / "financePages.tsx").read_text(encoding="utf-8")
governance = (DASHBOARD / "governancePages.tsx").read_text(encoding="utf-8")
operations = (DASHBOARD / "operationsPages.tsx").read_text(encoding="utf-8")

assert "const DEMO_ACTIONS_ENABLED = import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_ACTIONS === 'true';" in finance
assert "const DEMO_ACTIONS_ENABLED = import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_ACTIONS === 'true';" in governance
assert "const DEMO_ACTIONS_ENABLED = import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_ACTIONS === 'true';" in operations

for marker in (
    "onClick={runFx}",
    "onClick={createPipeline}",
    "onClick={createOperationalSample}",
    "onClick={runProcurement}",
    "onClick={runProduction}",
):
    source = finance if marker == "onClick={runFx}" else governance if marker in {"onClick={createPipeline}", "onClick={createOperationalSample}"} else operations
    assert f"DEMO_ACTIONS_ENABLED&&<button disabled={{busy}} {marker}" in source, marker

assert "rate_date:today" in finance
assert "revaluation_date:today" in finance
assert "rate_date:'2026-07-12'" not in finance
assert "revaluation_date:'2026-07-12'" not in finance

print("Production UI Controls RC27.3 Verification: PASS")
