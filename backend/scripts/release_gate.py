"""Deterministic release gate for CORVAX RC27.4 remediation.

This gate intentionally checks facts that previously drifted between code,
documentation and the user interface. It is safe to run without a database.
Database migrations and functional verification remain separate commands.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
EXPECTED_VERSION = "1.0.0-agreement-completion-rc27.4-r9.4"
EXPECTED_HEAD = "e20200000001"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def check_release_identity() -> None:
    config = text("backend/app/core/config.py")
    package = text("frontend/package.json")
    readme = text("README.md")
    checklist = text("deploy/PRODUCTION_CHECKLIST.md")
    require(EXPECTED_VERSION in config, "backend version drift")
    require(EXPECTED_VERSION in package, "frontend version drift")
    require(EXPECTED_HEAD in readme, "README migration head drift")
    require(EXPECTED_HEAD in checklist, "production checklist migration head drift")


def check_no_fake_header_badges() -> None:
    shell = text("frontend/src/dashboard/Shell.tsx")
    require("with-badge" not in shell, "static notification/message badge remains")
    require("v1.0 RC23" not in shell, "obsolete RC23 label remains")


def check_gym_read_contract() -> None:
    api = text("backend/app/api/gym_operations_advanced.py")
    ui = text("frontend/src/dashboard/gymRealPage.tsx")
    require('@router.get("/class-types")' in api, "GET class-types missing")
    require('@router.get("/pt-packages")' in api, "GET pt-packages missing")
    require("/gym/class-types?company_id=" in ui, "class-type list is not loaded")
    require("/gym/pt-packages?company_id=" in ui, "PT-package list is not loaded")
    require("no list endpoint" not in ui.lower(), "obsolete missing-endpoint fallback remains")


def check_route_authentication() -> None:
    """Reject API handlers that accidentally omit an authentication dependency.

    Health endpoints live in main.py and are deliberately outside this scan.
    Login/refresh/MFA bootstrap endpoints are the only public API handlers.
    """
    public = {
        ("auth.py", "login"),
        ("auth.py", "refresh_session"),
        ("auth.py", "enable_mfa_preauth"),
    }
    failures: list[str] = []
    for path in sorted((BACKEND / "app" / "api").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route = any(
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "router"
                for dec in node.decorator_list
            )
            if not route or (path.name, node.name) in public:
                continue
            source = ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
            if "Depends(get_current_user)" not in source:
                failures.append(f"{path.name}:{node.lineno}:{node.name}")
    require(not failures, "unauthenticated API routes: " + ", ".join(failures[:20]))


def check_no_obsolete_head_claims() -> None:
    for relative in ("README.md", "deploy/PRODUCTION_CHECKLIST.md"):
        body = text(relative)
        claimed = set(re.findall(r"reaches? to `?(e\d{11})|يصل إلى `?(e\d{11})", body))
        flattened = {value for pair in claimed for value in pair if value}
        require(not flattened or flattened == {EXPECTED_HEAD}, f"obsolete head claim in {relative}")


def main() -> int:
    checks = [
        check_release_identity,
        check_no_fake_header_badges,
        check_gym_read_contract,
        check_route_authentication,
        check_no_obsolete_head_claims,
    ]
    for check in checks:
        check()
        print(f"[PASS] {check.__name__}")
    print(f"CORVAX RELEASE GATE PASSED — {EXPECTED_VERSION} / {EXPECTED_HEAD}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
