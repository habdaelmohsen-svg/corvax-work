#!/usr/bin/env python3
"""Run the gym employee UI workflow against an isolated, freshly migrated database.

Usage from the repository root:
    CORVAX_UAT_ADMIN_PASSWORD='...' python3 frontend/uat/run_gym_employee_workflow.py \
        --output /tmp/corvax_gym_ui_final.json

The administrator password is required through the environment and is never
written to the evidence file, command line, database path, or server log.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPOSITORY_ROOT / "backend"
FRONTEND_DIR = REPOSITORY_ROOT / "frontend"
UI_SCENARIO = FRONTEND_DIR / "uat" / "gym_employee_workflow_simulation.tsx"
TSX_LOADER = FRONTEND_DIR / "node_modules" / "tsx" / "dist" / "loader.mjs"


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_until_ready(base_url: str, process: subprocess.Popen[str], timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"CORVAX server exited during startup with status {process.returncode}")
        try:
            with urlopen(f"{base_url}/health", timeout=1.0) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError(f"CORVAX server did not become ready within {timeout:.0f} seconds")


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def tail(path: Path, lines: int = 100) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=os.environ.get("CORVAX_UAT_OUTPUT", "/tmp/corvax_gym_ui_final.json"))
    parser.add_argument("--anchor-date", default=os.environ.get("CORVAX_UAT_ANCHOR_DATE", date.today().isoformat()))
    parser.add_argument("--company-id", type=int, default=int(os.environ.get("CORVAX_UAT_COMPANY_ID", "2")))
    parser.add_argument("--keep-db", action="store_true", help="Keep the isolated database and logs after a successful run")
    args = parser.parse_args()

    admin_password = os.environ.get("CORVAX_UAT_ADMIN_PASSWORD")
    if not admin_password:
        parser.error("CORVAX_UAT_ADMIN_PASSWORD must be set in the environment")
    if args.company_id <= 0:
        parser.error("--company-id must be positive")
    if not TSX_LOADER.is_file():
        parser.error("frontend dependencies are missing; run npm install in frontend first")
    node_binary = shutil.which("node")
    if not node_binary:
        parser.error("Node.js is required to run the gym UI scenario")

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix="corvax-gym-uat-"))
    database_path = temporary_root / f"gym_workflow_{secrets.token_hex(6)}.db"
    server_log_path = temporary_root / "server.log"
    port = available_port()
    base_url = f"http://127.0.0.1:{port}"
    server: subprocess.Popen[str] | None = None
    succeeded = False

    site_packages = REPOSITORY_ROOT / ".venv" / "lib" / "python3.12" / "site-packages"
    python_paths = [str(site_packages), str(BACKEND_DIR)]
    if os.environ.get("PYTHONPATH"):
        python_paths.append(os.environ["PYTHONPATH"])
    run_environment = os.environ.copy()
    run_environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "SECRET_KEY": secrets.token_urlsafe(48),
            "SEED_DEMO_DATA": "true",
            "AUTO_CREATE_SCHEMA": "true",
            "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
            "RATE_LIMIT_ENABLED": "false",
            "ENABLE_RATE_LIMIT_TESTING": "true",
            "PYTHONPATH": os.pathsep.join(python_paths),
            "CORVAX_UAT_BASE_URL": base_url,
            "CORVAX_UAT_ADMIN_EMAIL": os.environ.get("CORVAX_UAT_ADMIN_EMAIL", "admin@corvaxplatform.com"),
            "CORVAX_UAT_ADMIN_PASSWORD": admin_password,
            "CORVAX_UAT_COMPANY_ID": str(args.company_id),
            "CORVAX_UAT_ANCHOR_DATE": args.anchor_date,
            "CORVAX_UAT_OUTPUT": str(output_path),
        }
    )

    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(BACKEND_DIR / "alembic.ini"), "upgrade", "head"],
            cwd=REPOSITORY_ROOT,
            env=run_environment,
            check=True,
        )
        with server_log_path.open("w", encoding="utf-8") as server_log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--app-dir",
                    str(BACKEND_DIR),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=REPOSITORY_ROOT,
                env=run_environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            wait_until_ready(base_url, server)

            # The demo seed marks future periods as FUTURE. This isolated UAT run
            # deliberately opens them so document posting follows the chosen date.
            with sqlite3.connect(database_path) as connection:
                connection.execute("UPDATE fiscal_periods SET status = 'OPEN'")
                connection.commit()

            completed = subprocess.run(
                [node_binary, "--import", str(TSX_LOADER), str(UI_SCENARIO)],
                cwd=FRONTEND_DIR,
                env=run_environment,
                text=True,
                capture_output=True,
            )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        if completed.returncode != 0:
            raise RuntimeError(f"Gym UI scenario failed with status {completed.returncode}")
        if not output_path.is_file():
            raise RuntimeError(f"Gym UI scenario did not create {output_path}")
        evidence = json.loads(output_path.read_text(encoding="utf-8"))
        if evidence.get("passed") != evidence.get("total") or evidence.get("failed"):
            raise RuntimeError("Gym UI evidence contains failed checks")
        if evidence.get("requests", {}).get("unexpected_errors"):
            raise RuntimeError("Gym UI evidence contains unexpected HTTP errors")
        succeeded = True
        print(f"Verified gym UI evidence: {output_path}")
        return 0
    except Exception as error:
        print(f"Gym employee workflow failed: {error}", file=sys.stderr)
        server_tail = tail(server_log_path)
        if server_tail:
            print("--- server log tail ---", file=sys.stderr)
            print(server_tail, file=sys.stderr)
        print(f"Isolated run files kept at: {temporary_root}", file=sys.stderr)
        return 1
    finally:
        stop_process(server)
        if succeeded and not args.keep_db:
            shutil.rmtree(temporary_root)


if __name__ == "__main__":
    raise SystemExit(main())
