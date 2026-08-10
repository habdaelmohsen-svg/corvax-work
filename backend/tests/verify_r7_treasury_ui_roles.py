"""Run the TreasuryPage three-role UI simulation against a fresh database."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_DIR / "backend"
FRONTEND_DIR = PROJECT_DIR / "frontend"
UI_SCRIPT = FRONTEND_DIR / "uat" / "treasury_three_role_simulation.tsx"
VITE_NODE = FRONTEND_DIR / "node_modules" / ".bin" / "vite-node"
SERVER_READY_TIMEOUT_SECONDS = int(
    os.environ.get("CORVAX_TEST_SERVER_READY_TIMEOUT_SECONDS", "60")
)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


with tempfile.TemporaryDirectory(prefix="verify_r7_treasury_ui_roles_") as temp_dir:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{Path(temp_dir) / 'treasury.db'}",
            "SECRET_KEY": "r7-treasury-ui-role-test-secret",
            "SEED_DEMO_DATA": "true",
            "ENVIRONMENT": "testing",
            "PYTHONPATH": os.pathsep.join(
                filter(
                    None,
                    [
                        str(BACKEND_DIR),
                        environment.get("PYTHONPATH", ""),
                    ],
                )
            ),
        }
    )
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
            "--log-level",
            "warning",
        ],
        cwd=PROJECT_DIR,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        # A fresh CORVAX database applies the complete migration chain and seeds
        # every maintained module before Uvicorn can serve /health.  Cold CI
        # filesystems can legitimately take longer than the historical 20s
        # threshold, especially after a new release migration is added.  Keep
        # the readiness probe strict, but allow enough time for real startup.
        deadline = time.monotonic() + SERVER_READY_TIMEOUT_SECONDS
        while True:
            if server.poll() is not None:
                raise RuntimeError(f"Treasury UI test server exited with {server.returncode}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Treasury UI test server did not become ready")
                time.sleep(0.1)

        ui_environment = environment | {"CORVAX_UAT_BASE_URL": base_url}
        result = subprocess.run(
            [str(VITE_NODE), str(UI_SCRIPT)],
            cwd=FRONTEND_DIR,
            env=ui_environment,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
