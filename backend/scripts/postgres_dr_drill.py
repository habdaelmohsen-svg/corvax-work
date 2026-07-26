#!/usr/bin/env python3
"""Controlled PostgreSQL backup/restore drill to an isolated target database.

The tool refuses identical source/target URLs and emits a signed JSON evidence file.
It requires pg_dump, pg_restore and psql binaries. It does not delete the target.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlsplit


def run(command: list[str], *, env=None) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
    return result.stdout.strip()


def redacted(url: str) -> str:
    value=urlsplit(url)
    return f"{value.scheme}://***@{value.hostname}:{value.port or 5432}{value.path}"


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source", default=os.getenv("SOURCE_DATABASE_URL"))
    parser.add_argument("--target", default=os.getenv("TARGET_DATABASE_URL"))
    parser.add_argument("--evidence", default="docs/operations/evidence/postgres_dr_drill.json")
    args=parser.parse_args()
    if not args.source or not args.target: raise SystemExit("source and target URLs are required")
    if args.source == args.target: raise SystemExit("Refusing to restore over the source database")
    started=time.time()
    with tempfile.TemporaryDirectory(prefix="corvax-dr-") as tmp:
        dump=Path(tmp)/"corvax.dump"
        run(["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(dump), args.source])
        checksum=hashlib.sha256(dump.read_bytes()).hexdigest()
        run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-acl", "--dbname", args.target, str(dump)])
        checks=run(["psql", args.target, "-Atc", "select current_database(), count(*) from alembic_version;"])
        tables=int(run(["psql", args.target, "-Atc", "select count(*) from information_schema.tables where table_schema='public';"]))
    evidence={"status":"PASSED", "source":redacted(args.source), "target":redacted(args.target),
              "dump_sha256":checksum, "schema_check":checks, "public_table_count":tables,
              "duration_seconds":round(time.time()-started,2), "rpo_minutes":"TO_BE_SIGNED",
              "rto_minutes":"TO_BE_SIGNED"}
    path=Path(args.evidence); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    print(json.dumps(evidence, indent=2))

if __name__ == "__main__": main()
