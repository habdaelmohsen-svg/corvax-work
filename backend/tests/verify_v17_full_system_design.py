"""Static acceptance gate for the V17 full-system redesign contract."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


main = read("frontend/src/main.tsx")
shell = read("frontend/src/dashboard/Shell.tsx")
routes = read("frontend/src/dashboard/routes.tsx")
ui = read("frontend/src/dashboard/ui.tsx")
css = read("frontend/src/styles/corvax_v17.css")
login = read("frontend/src/components/Login.tsx")
selector = read("frontend/src/components/CompanySelector.tsx")
restaurant = read("frontend/src/dashboard/restaurantRealPage.tsx")
dgtera = read("frontend/src/dashboard/dgteraIntegrationPage.tsx")

assert main.index("./styles/corvax_mui_v16.css") < main.index("./styles/corvax_v17.css")
assert 'className={`page-stage view-${view}`}' in shell
assert 'className="mobile-tabbar"' in shell
assert 'className="mobile-brand"' in shell
assert 'className="page-heading-icon"' in shell
assert "mobilePrimary" in shell
assert "CORVAX-RC27.4-R9.4-CORE-V17-AUTH-R2-20260821" in shell

route_keys = set(re.findall(r"\s+([A-Za-z]+):<", routes))
assert len(route_keys) >= 45, f"expected the full route catalog, found {len(route_keys)}"
assert all(key in route_keys for key in (
    "executive", "finance", "inventory", "sales", "restaurant", "gym",
    "manufacturing", "hr", "reports", "users", "audit", "security",
))

assert 'className="panel-body"' in ui
assert "data-label={headers[j]}" in ui
assert 'className="kpi-main"' in ui
assert 'className="mini-status-copy"' in ui

for selector_name in (
    ".dash", ".workspace", ".app-header", ".page-heading", ".page-stage",
    ".kpis", ".kpi-card", ".panel", ".panel-body", ".data-table",
    ".dash input", ".statement-tabs", ".auth-page", ".company-card",
    ".mobile-tabbar", ".module-commandbar", ".integration-status-board",
    ".dash.theme-dark", "@media (max-width: 700px)", "@media print",
):
    assert selector_name in css, f"V17 system selector missing: {selector_name}"

assert "content: attr(data-label)" in css
assert "grid-template-columns: repeat(2, minmax(0,1fr))" in css
assert "showcase-preview" in login
assert "workspace-stats" in selector and "selected-workspace" in selector
assert "/api/v1/integrations/dgtera/refresh-current" in restaurant
assert "module-commandbar" in restaurant and "integration-health" in restaurant
assert "integration-status-metrics" in dgtera
assert "status.accounting?.posted_days" in dgtera
assert "status.proof?.verified_days" in dgtera

print(f"CORVAX V17 FULL-SYSTEM DESIGN: PASS ({len(route_keys)} routes)")
