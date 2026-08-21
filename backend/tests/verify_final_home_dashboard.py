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
DGTERA_PAGE = (ROOT / "frontend/src/dashboard/dgteraIntegrationPage.tsx").read_text(encoding="utf-8")
REPORTS_CENTER = (ROOT / "frontend/src/dashboard/reportsCenterPage.tsx").read_text(encoding="utf-8")
DGTERA_API = (ROOT / "backend/app/api/dgtera_integration.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "backend/app/core/config.py").read_text(encoding="utf-8")
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
MAIN = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")
MUI_THEME = (ROOT / "frontend/src/theme/CorvaxThemeProvider.tsx").read_text(encoding="utf-8")
MUI_CSS = (ROOT / "frontend/src/styles/corvax_mui_v16.css").read_text(encoding="utf-8")
V17_CSS = (ROOT / "frontend/src/styles/corvax_v17.css").read_text(encoding="utf-8")
PACKAGE = (ROOT / "frontend/package.json").read_text(encoding="utf-8")


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
assert all(label in EXECUTIVE for label in ("صافي مبيعات اليوم", "صافي مبيعات الأسبوع", "صافي مبيعات الشهر", "صافي مبيعات السنة"))
assert "metrics?.current?.subtotal" in EXECUTIVE
assert "إجمالي الإيرادات (صافي)" in EXECUTIVE
assert "/api/v1/integrations/dgtera/status" in EXECUTIVE
assert "/api/v1/integrations/dgtera/refresh-current" in EXECUTIVE
assert "dgtera-home-verification" in EXECUTIVE
assert all(label in EXECUTIVE for label in ("صافي اليوم", "ضريبة اليوم", "إجمالي اليوم", "آخر تحقق", "استيراد التاريخ"))
assert "permissions.includes('pos.manage')" in EXECUTIVE
assert '@router.post("/refresh-current")' in DGTERA_API
assert 'ensure_permission(db, user, company_id, "pos.manage")' in DGTERA_API
assert "connection_is_due(connection)" in DGTERA_API
assert '"proof_generation"' in DGTERA_API
assert all(target in TARGETS for target in ("dgteraDailySales", "dgteraWeeklySales", "dgteraMonthlySales", "dgteraYearlySales"))
assert "عرض المبيعات" in DGTERA_PAGE and "setAppliedFilters" in DGTERA_PAGE
assert "reportComplete?" in DGTERA_PAGE and "Totals are hidden until every day is covered" in DGTERA_PAGE
assert "Strict 100% reconciliation" in DGTERA_PAGE and "verification_hash" in DGTERA_PAGE
assert "setInterval(()=>load().catch(rejectStale),120000)" in DGTERA_PAGE
assert "setSnapshot(null);setAnalytics(null)" in DGTERA_PAGE
assert "rangeDays<=32" in REPORTS_CENTER
assert "'/api/v1/integrations/dgtera/sync'" in REPORTS_CENTER
assert "sync.strict_reconciled!==true" in REPORTS_CENTER
assert "120000" in REPORTS_CENTER
assert "Request timed out after" in REPORTS_CENTER

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
assert "/api/v1/system/release" in SHELL
assert "version-line version-full" in SHELL
assert all(field in SHELL for field in ("apiVersion", "releaseId", "buildCommit"))
assert "CORVAX-RC27.4-R9.4-CORE-V17-AUTH-R1-20260821" in CONFIG
assert "CorvaxThemeProvider" in APP
assert "@mui/material" in PACKAGE and "@mui/stylis-plugin-rtl" in PACKAGE
assert "createTheme" in MUI_THEME and "rtlPlugin" in MUI_THEME and "CssBaseline" in MUI_THEME
assert "./styles/corvax_mui_v16.css" in MAIN
assert "./styles/corvax_v17.css" in MAIN
assert all(marker in MUI_CSS for marker in (
    "CORVAX V16 — MUI Executive Workspace",
    ".page-heading",
    ".kpi-card",
    ".data-table",
    ".journal-form",
    ".dash.theme-dark",
    ".auth-page",
    ".company-card",
    "width: min(88vw, 304px)",
    "@media print",
    "prefers-reduced-motion",
))
assert all(marker in V17_CSS for marker in (
    "CORVAX V17 — unified business operating system",
    ".page-stage",
    ".mobile-tabbar",
    ".panel-body",
    ".data-table .tr:not(.th) > span::before",
    ".integration-status-board",
    ".auth-showcase",
    ".selected-workspace",
))

target_values = set(re.findall(r": '([A-Za-z]+)',", TARGETS))
route_keys = set(re.findall(r"\s+([A-Za-z]+):<", ROUTES))
missing = sorted(target_values - route_keys)
assert not missing, f"executive navigation targets without a rendered route: {missing}"

print("CORVAX FINAL HOME DASHBOARD: PASS")
