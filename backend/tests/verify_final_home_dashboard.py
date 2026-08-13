"""Static release guard for the RC27.4 executive home.

This catches the two regressions found during final review:
1. controls that look clickable but have no navigation handler;
2. fabricated executive figures mixed with ledger-backed KPIs.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
EXECUTIVE = (ROOT / "frontend/src/dashboard/executive.tsx").read_text(encoding="utf-8")
TARGETS = (ROOT / "frontend/src/dashboard/executiveNavigation.ts").read_text(encoding="utf-8")
ROUTES = (ROOT / "frontend/src/dashboard/routes.tsx").read_text(encoding="utf-8")
SHELL = (ROOT / "frontend/src/dashboard/Shell.tsx").read_text(encoding="utf-8")
UI = (ROOT / "frontend/src/dashboard/ui.tsx").read_text(encoding="utf-8")


for forbidden in (
    "107.5M",
    "32,750,000",
    "18,950,000",
    "14,580,000",
    "22,450,000",
    "5,120,000",
    "2,750,000",
    "<strong>98%</strong>",
    "<strong>96%</strong>",
    "12 items · 10m ago",
    "24 invoices · 25m ago",
):
    assert forbidden not in EXECUTIVE, f"fabricated executive value remains: {forbidden}"

for endpoint in (
    "/api/v1/finance/statements",
    "/api/v1/finance/trial-balance",
    "/api/v1/subledgers/aging",
    "/api/v1/inventory/stock-summary",
    "/api/v1/governance/summary",
    "/api/v1/integrations/dgtera/executive-summary",
):
    assert endpoint in EXECUTIVE, f"live executive source missing: {endpoint}"

assert "Current Period" in EXECUTIVE
assert "Last 12 Months" not in EXECUTIVE
assert "results.some(Boolean)" in EXECUTIVE
assert "dataQuality" in EXECUTIVE and "controlEffectiveness" in EXECUTIVE
assert all(label in EXECUTIVE for label in ("مبيعات اليوم", "مبيعات الأسبوع", "مبيعات الشهر", "مبيعات السنة"))
assert all(target in TARGETS for target in ("dgteraDailySales", "dgteraWeeklySales", "dgteraMonthlySales", "dgteraYearlySales"))

quick_actions = [line for line in EXECUTIVE.splitlines() if "<QuickAction " in line]
assert len(quick_actions) == 8
assert all("onClick=" in action for action in quick_actions)
assert 'arLabel="مركز التقارير"' in EXECUTIVE
assert "reportsCenter: 'reports'" in TARGETS

assert "onClick:()=>void" in UI
assert "onOpen?:()=>void" in UI
assert "onClick?:()=>void" in UI
assert "onNavigate: (view: View) => void" in ROUTES
assert "onNavigate={selectView}" in SHELL
assert "availableNav.some((item) => item.key === next)" in SHELL
assert 'className="navigation-notice" role="alert"' in SHELL

target_values = set(re.findall(r": '([A-Za-z]+)',", TARGETS))
route_keys = set(re.findall(r"\s+([A-Za-z]+):<", ROUTES))
missing = sorted(target_values - route_keys)
assert not missing, f"executive navigation targets without a rendered route: {missing}"

print("CORVAX FINAL HOME DASHBOARD: PASS")
