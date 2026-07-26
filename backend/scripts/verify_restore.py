#!/usr/bin/env python3
"""Offline verification and restore helper for CORVAX backup ZIP files.

Usage:
  python scripts/verify_restore.py backup.zip --verify-only
  python scripts/verify_restore.py backup.zip --target ./data/restored-corvax.db

PostgreSQL custom dumps are verified structurally here and require pg_restore for actual restore.
Run restores only while the application is stopped and after taking an additional safety copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--postgres-url")
    args = parser.parse_args()

    if not args.backup.exists():
        raise SystemExit(f"Backup not found: {args.backup}")
    with zipfile.ZipFile(args.backup) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"ZIP CRC failed: {bad}")
        manifest = json.loads(archive.read("manifest.json"))
        database_name = manifest["database_file"]
        database_bytes = archive.read(database_name)
        if sha256_bytes(database_bytes) != manifest["database_sha256"]:
            raise SystemExit("Database SHA-256 does not match manifest")

    if database_name.endswith(".db"):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            handle.write(database_bytes)
            handle.flush()
            connection = sqlite3.connect(handle.name)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            table_count = connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            connection.close()
        if integrity != "ok":
            raise SystemExit(f"SQLite integrity check failed: {integrity}")
        print(f"VERIFIED SQLite backup: {table_count} tables")
        if args.verify_only:
            return 0
        if not args.target:
            raise SystemExit("--target is required for SQLite restore")
        args.target.parent.mkdir(parents=True, exist_ok=True)
        if args.target.exists():
            raise SystemExit(f"Refusing to overwrite existing target: {args.target}")
        args.target.write_bytes(database_bytes)
        print(f"RESTORED SQLite database to {args.target}")
        return 0

    print("VERIFIED PostgreSQL custom dump checksum and ZIP structure")
    if args.verify_only:
        return 0
    if not args.postgres_url:
        raise SystemExit("--postgres-url is required for PostgreSQL restore")
    pg_restore = shutil.which("pg_restore")
    if not pg_restore:
        raise SystemExit("pg_restore is not installed")
    with tempfile.NamedTemporaryFile(suffix=".dump") as handle:
        handle.write(database_bytes)
        handle.flush()
        subprocess.run([pg_restore, "--clean", "--if-exists", "--no-owner", "--dbname", args.postgres_url, handle.name], check=True)
    print("RESTORED PostgreSQL dump")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
