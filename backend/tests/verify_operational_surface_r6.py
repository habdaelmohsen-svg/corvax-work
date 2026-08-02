"""R6 authenticated read-surface simulation across every list/report endpoint.

The historical suites exercise deep business lifecycles.  This gate complements
them by opening every authenticated GET operation that does not require an
existing resource ID, using one clean seeded tenant and realistic report dates.
"""
from __future__ import annotations

import os
import re
import json
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_operational_surface_r6.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH}",
        "SECRET_KEY": "verification-secret-key-corvax-operational-surface-r6",
        "FIELD_ENCRYPTION_KEY": "verification-field-key-corvax-operational-surface-r6",
        "SEED_DEMO_DATA": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
        "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r6",
    }
)
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


QUERY_VALUES = {
    "company_id": 1,
    "branch_id": 1,
    "fiscal_year": 2026,
    "year": 2026,
    "month": 1,
    "period_year": 2026,
    "period_month": 1,
    "period_start": "2026-01-01",
    "period_end": "2026-12-31",
    "date_from": "2026-01-01",
    "date_to": "2026-12-31",
    "from_date": "2026-01-01",
    "to_date": "2026-12-31",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
    "as_of_date": "2026-12-31",
    "as_of": "2026-12-31",
    "reporting_date": "2026-12-31",
    "period_code": "2026-01",
    "account_code": "111010",
    "ledger_type": "AR",
    "q": "VAT",
    "limit": 100,
    "offset": 0,
}
PUBLIC_PATHS = {"/health"}
SKIP_PATHS = {
    # These are intentional binary exports/downloads that require a generated
    # artifact or resource identifier and are covered in their lifecycle tests.
    "/api/v1/opening-balances/template.xlsx",
}


def required_query(operation: dict) -> dict[str, object]:
    values: dict[str, object] = {}
    missing: list[str] = []
    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "query" or not parameter.get("required"):
            continue
        name = parameter["name"]
        schema = parameter.get("schema", {})
        if "default" in schema:
            values[name] = schema["default"]
        elif schema.get("enum"):
            values[name] = schema["enum"][0]
        elif schema.get("pattern"):
            choices = re.fullmatch(r"\^\(([^)]+)\)\$", schema["pattern"])
            if choices:
                values[name] = choices.group(1).split("|", 1)[0]
            else:
                missing.append(name)
        elif name in QUERY_VALUES:
            values[name] = QUERY_VALUES[name]
        elif name.endswith("_id"):
            values[name] = 1
        elif name.endswith("_date") or "date" in name:
            values[name] = "2026-12-31"
        elif name.endswith("_code"):
            values[name] = "2026-01"
        elif schema.get("type") == "boolean":
            values[name] = False
        else:
            missing.append(name)
    assert not missing, f"R6 query fixture missing for: {missing}"
    return values


def main() -> None:
    with TestClient(app) as client:
        with SessionLocal() as db:
            admin = db.scalar(select(User).where(User.email == "admin@corvaxplatform.com"))
            assert admin
            admin.require_password_change = False
            db.execute(text("update fiscal_periods set status='OPEN'"))
            db.commit()
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        checked: list[str] = []
        empty_prerequisite: list[str] = []
        for path, methods in sorted(app.openapi()["paths"].items()):
            if "{" in path or "get" not in methods or path in SKIP_PATHS:
                continue
            operation = methods["get"]
            required_names = {
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "query" and parameter.get("required")
            }
            # Reports bound to a specific pre-existing business object belong
            # to that object's lifecycle test, not the general read surface.
            if any(name.endswith("_id") and name not in {"company_id", "branch_id"} for name in required_names):
                continue
            response = client.get(
                path,
                headers={} if path in PUBLIC_PATHS else headers,
                params=required_query(operation),
            )
            assert response.status_code in {200, 404}, (
                f"GET {path} failed with {response.status_code}: {response.text[:500]}"
            )
            if response.status_code == 404:
                empty_prerequisite.append(path)
            checked.append(path)
        assert len(checked) >= 100, f"Unexpectedly small R6 surface: {len(checked)}"
        print(
            "CORVAX R6 AUTHENTICATED READ SURFACE VERIFIED: "
            f"{len(checked)} endpoints; "
            f"{len(checked) - len(empty_prerequisite)} returned data/empty lists; "
            f"{len(empty_prerequisite)} require a prior configured object"
        )
        (BACKEND.parent / "CORVAX_R6_READ_SURFACE.json").write_text(
            json.dumps(
                {
                    "checked": checked,
                    "successful": sorted(set(checked) - set(empty_prerequisite)),
                    "requires_prerequisite": empty_prerequisite,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
