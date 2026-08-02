"""Audit direct operational API coverage in maintained CORVAX verification scripts.

This is deliberately stricter than counting verification files.  A route is
considered directly covered only when a maintained verification script calls
the same HTTP method and normalized API path.  Dynamic IDs in f-strings and
numeric IDs are normalized to the same placeholder.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
API_DIR = BACKEND / "app" / "api"
TEST_DIR = BACKEND / "tests"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def normalize_path(value: str) -> str:
    value = value.split("?", 1)[0]
    value = value.replace("/api/v1", "", 1)
    value = re.sub(r"/\{[^}]+\}", "/{}", value)
    value = re.sub(r"/\d+(?=/|$)", "/{}", value)
    return value.rstrip("/") or "/"


def collect_routes() -> list[dict[str, object]]:
    routes: list[dict[str, object]] = []
    for source in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        prefix = ""
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "router" for target in node.targets):
                continue
            if not isinstance(node.value, ast.Call):
                continue
            for keyword in node.value.keywords:
                if keyword.arg == "prefix":
                    prefix = string_value(keyword.value) or ""
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "router"
                ):
                    continue
                method = decorator.func.attr.upper()
                path = string_value(decorator.args[0]) if decorator.args else None
                if method not in HTTP_METHODS or path is None:
                    continue
                routes.append(
                    {
                        "method": method,
                        "path": prefix + path,
                        "normalized_path": normalize_path(prefix + path),
                        "module": source.name,
                        "line": node.lineno,
                    }
                )
    return routes


def collect_direct_calls() -> set[tuple[str, str]]:
    calls: set[tuple[str, str]] = set()
    for source in sorted(TEST_DIR.glob("verify_*.py")):
        # The contract gate proves routing/authentication/error safety only.
        # Counting its deliberately invalid calls as lifecycle coverage would
        # inflate the operational result to a misleading 100%.
        if source.name == "verify_rc274_r6_remaining_contracts.py":
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr.upper() in HTTP_METHODS
                and node.args
            ):
                continue
            value = string_value(node.args[0])
            if value and "/api/v1" in value:
                calls.add((node.func.attr.upper(), normalize_path(value)))
    surface_manifest = ROOT / "CORVAX_R6_READ_SURFACE.json"
    if surface_manifest.exists():
        surface = json.loads(surface_manifest.read_text(encoding="utf-8"))
        for path in surface.get("checked", []):
            calls.add(("GET", normalize_path(path)))
    return calls


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# CORVAX — تدقيق تغطية المحاكاة التشغيلية",
        "",
        f"تاريخ القياس: {result['generated_at']}",
        "",
        "## النتيجة",
        "",
        f"- إجمالي عمليات API: **{result['route_count']}**",
        f"- عمليات لها استدعاء مباشر في اختبارات التحقق: **{result['covered_count']}**",
        f"- عمليات بلا استدعاء مباشر: **{result['uncovered_count']}**",
        f"- نسبة التغطية المباشرة: **{result['coverage_percent']}%**",
        "",
        "> نجاح اختبار وحدة أو وجود شاشة لا يساوي محاكاة دورة أعمال. هذا القياس",
        "> يثبت الاستدعاء المباشر فقط، ولا يدّعي صحة الأرقام أو القيود دون assertions.",
        "",
        "## الفجوات حسب الوحدة",
        "",
        "| الوحدة | العمليات غير المغطاة |",
        "|---|---:|",
    ]
    for module, count in result["uncovered_by_module"]:
        lines.append(f"| `{module}` | {count} |")
    lines.extend(
        [
            "",
            "## العمليات غير المغطاة مباشرة",
            "",
            "| الطريقة | المسار | الوحدة |",
            "|---|---|---|",
        ]
    )
    for route in result["uncovered_routes"]:
        lines.append(f"| {route['method']} | `{route['path']}` | `{route['module']}` |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=ROOT / "CORVAX_OPERATIONAL_COVERAGE.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "CORVAX_OPERATIONAL_COVERAGE_AR.md")
    parser.add_argument("--max-uncovered", type=int)
    args = parser.parse_args()

    routes = collect_routes()
    direct_calls = collect_direct_calls()
    uncovered = [
        route
        for route in routes
        if (str(route["method"]), str(route["normalized_path"])) not in direct_calls
    ]
    covered_count = len(routes) - len(uncovered)
    result: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "route_count": len(routes),
        "covered_count": covered_count,
        "uncovered_count": len(uncovered),
        "coverage_percent": round((covered_count / len(routes)) * 100, 2) if routes else 100.0,
        "uncovered_by_module": Counter(str(route["module"]) for route in uncovered).most_common(),
        "uncovered_routes": uncovered,
    }
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown.write_text(render_markdown(result), encoding="utf-8")
    print(
        "CORVAX OPERATIONAL COVERAGE: "
        f"{covered_count}/{len(routes)} direct operations covered "
        f"({result['coverage_percent']}%); {len(uncovered)} uncovered"
    )
    if args.max_uncovered is not None and len(uncovered) > args.max_uncovered:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
