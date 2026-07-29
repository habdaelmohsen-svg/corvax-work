"""Run every maintained CORVAX verification script as one release gate."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
TESTS = BACKEND / "tests"


def _tail(value: str, limit: int = 20) -> str:
    lines = value.strip().splitlines()
    return "\n".join(lines[-limit:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    scripts = sorted(TESTS.glob("verify_*.py"))
    failures: list[tuple[str, str]] = []
    started = time.monotonic()

    for index, script in enumerate(scripts, start=1):
        item_started = time.monotonic()
        # Historical scripts used persistent files under backend/data and some
        # did not remove them before a run.  Always start each verification from
        # its own clean database so a stale schema cannot create false failures.
        databases = (
            BACKEND / "data" / f"{script.stem}.db",
            Path("/tmp") / f"{script.stem}.db",
        )
        for database in databases:
            for suffix in ("", "-journal", "-shm", "-wal"):
                Path(f"{database}{suffix}").unlink(missing_ok=True)
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = (
            f"{BACKEND}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else str(BACKEND)
        )
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=BACKEND if script.name == "verify_v030.py" else ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
            elapsed = time.monotonic() - item_started
            if result.returncode == 0:
                print(
                    f"[PASS {index:02d}/{len(scripts):02d}] "
                    f"{script.name} ({elapsed:.1f}s)",
                    flush=True,
                )
                continue
            detail = _tail("\n".join([result.stdout, result.stderr]))
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - item_started
            detail = f"Timed out after {elapsed:.1f}s\n{_tail(exc.stdout or '')}"

        failures.append((script.name, detail))
        print(
            f"[FAIL {index:02d}/{len(scripts):02d}] "
            f"{script.name} ({elapsed:.1f}s)",
            flush=True,
        )

    elapsed = time.monotonic() - started
    if failures:
        print(f"\n{len(failures)} verification script(s) failed:")
        for name, detail in failures:
            print(f"\n--- {name} ---\n{detail}")
        return 1

    print(
        f"\nCORVAX FULL VERIFICATION GATE PASSED — "
        f"{len(scripts)} scripts in {elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
