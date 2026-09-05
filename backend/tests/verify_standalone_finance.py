"""Prove retirement prevents network access and preserves ledger reporting."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(DATABASE_URL="sqlite:////tmp/verify_standalone_finance.db",
    BOOTSTRAP_FIRST_ADMIN="false", AUTO_CREATE_SCHEMA="true",
    DGTERA_SCHEDULER_ENABLED="true", SEED_DEMO_DATA="false")
Path("/tmp/verify_standalone_finance.db").unlink(missing_ok=True)
from fastapi.testclient import TestClient
from app.main import app
from app.services.dgtera_connector import Odoo14Client, DgteraRemoteError
from app.workers.dgtera_daily_sync import run_due_syncs
from app.api.finance import financial_statements
import inspect

with patch("httpx.Client", side_effect=AssertionError("Unexpected network client")):
    try:
        Odoo14Client(base_url="https://example.com", database="test", login="test", api_key="test")
    except DgteraRemoteError:
        pass
    else:
        raise AssertionError("Retired connector accepted credentials")
    run_due_syncs()
with TestClient(app) as client:
    paths = {route.path for route in app.routes}
    assert not any("/integrations/dgtera" in path for path in paths)
    assert client.post("/api/v1/integrations/dgtera/sync", json={}).status_code in (404, 405)
source = inspect.getsource(financial_statements)
assert "revenue = ledger_revenue" in source
assert "verified_dgtera_revenue_source" not in source
print("Standalone retirement: network, scheduler, routes and ledger source verified")
