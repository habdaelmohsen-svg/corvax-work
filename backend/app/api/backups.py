from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess  # nosec B404
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.core.config import settings
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import BackupRecord, User
from app.services.audit import write_audit

router = APIRouter(prefix="/backups", tags=["backup and recovery"])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_export(target: Path) -> str:
    url = settings.database_url
    if url.startswith("sqlite:///"):
        source_text = url.removeprefix("sqlite:///")
        source = Path(source_text)
        if not source.is_absolute():
            source = Path.cwd() / source
        if not source.exists():
            raise HTTPException(404, "SQLite database file not found")
        connection = sqlite3.connect(source)
        destination = sqlite3.connect(target)
        try:
            connection.backup(destination)
        finally:
            destination.close(); connection.close()
        return "SQLITE_ONLINE_BACKUP"
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise HTTPException(
            501,
            "pg_dump is not available in this image. It is installed by the "
            "Dockerfile; if you see this, the deployment is running an older build.",
        )
    parsed = make_url(url)
    if parsed.drivername.split("+")[0] not in {"postgresql", "postgres"}:
        raise HTTPException(422, "Unsupported database driver for PostgreSQL backup")
    if not parsed.database or not parsed.host or not parsed.username:
        raise HTTPException(422, "Incomplete PostgreSQL backup connection settings")
    command = [
        pg_dump,
        "--format=custom",
        "--file", str(target),
        "--host", parsed.host,
        "--port", str(parsed.port or 5432),
        "--username", parsed.username,
        "--dbname", parsed.database,
        "--no-password",
    ]
    environment = os.environ.copy()
    if parsed.password:
        environment["PGPASSWORD"] = parsed.password
    subprocess.run(  # nosec B603
        command, check=True, timeout=300, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    return "POSTGRESQL_PG_DUMP"


@router.post("", status_code=201)
def create_backup(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "backup.manage")
    timestamp = utc_now().strftime("%Y%m%dT%H%M%S%f")
    zip_path = settings.backup_path / f"corvax-backup-{timestamp}.zip"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        dump_name = "database.db" if settings.database_url.startswith("sqlite") else "database.dump"
        dump_path = tmp / dump_name
        method = _database_export(dump_path)
        dump_checksum = _sha256(dump_path)
        manifest = {
            "app": settings.app_name,
            "version": settings.app_version,
            "created_at": utc_now().isoformat(),
            "created_by": user.id,
            "requested_company_id": company_id,
            "backup_method": method,
            "database_file": dump_name,
            "database_sha256": dump_checksum,
            "restore_test": "VERIFY_MANIFEST_AND_DATABASE_INTEGRITY_BEFORE_RESTORE",
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(dump_path, dump_name)
            archive.write(tmp / "manifest.json", "manifest.json")
    checksum = _sha256(zip_path)
    row = BackupRecord(company_id=company_id, backup_type="FULL_DATABASE", storage_path=str(zip_path), checksum_sha256=checksum, size_bytes=zip_path.stat().st_size, status="COMPLETED", created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="BACKUP_CREATED", entity_type="BACKUP", entity_id=row.id, user_id=user.id, company_id=company_id, after={"checksum": checksum, "size_bytes": row.size_bytes, "method": method})
    db.commit()
    # AUDIT H-03: on a container platform the local disk is wiped on every deploy
    # and restart. The caller must download the file or copy it to durable storage,
    # otherwise the backup is lost with the next release.
    return {
        "id": row.id,
        "status": row.status,
        "created_at": row.created_at,
        "size_bytes": row.size_bytes,
        "checksum_sha256": row.checksum_sha256,
        "download_url": f"/api/v1/backups/{row.id}/download",
        "storage": "EPHEMERAL_CONTAINER_DISK",
        "warning_ar": "هذه النسخة محفوظة على قرص مؤقت يُمحى عند إعادة النشر. نزّلها فورًا أو انسخها إلى تخزين دائم.",
        "warning_en": "This backup lives on ephemeral container storage and is erased on redeploy. Download it now or copy it to durable storage.",
    }


@router.get("")
def list_backups(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "backup.manage")
    rows = db.scalars(select(BackupRecord).where(BackupRecord.company_id == company_id).order_by(BackupRecord.created_at.desc())).all()
    return [{"id": r.id, "backup_type": r.backup_type, "size_bytes": r.size_bytes, "checksum_sha256": r.checksum_sha256, "status": r.status, "created_at": r.created_at, "verified_at": r.verified_at} for r in rows]


@router.post("/{backup_id}/verify")
def verify_backup(backup_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(BackupRecord, backup_id)
    if not row:
        raise HTTPException(404, "Backup not found")
    if row.company_id is not None:
        ensure_permission(db, user, row.company_id, "backup.manage")
    path = Path(row.storage_path)
    if not path.exists() or _sha256(path) != row.checksum_sha256:
        row.status = "CORRUPT"; db.commit()
        raise HTTPException(409, "Backup file checksum failed")
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP CRC failed")
            manifest = json.loads(archive.read("manifest.json"))
            database_bytes = archive.read(manifest["database_file"])
            if hashlib.sha256(database_bytes).hexdigest() != manifest["database_sha256"]:
                raise ValueError("Database checksum failed")
            if manifest["database_file"].endswith(".db"):
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
                    handle.write(database_bytes); temp_name = handle.name
                try:
                    connection = sqlite3.connect(temp_name)
                    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
                    connection.close()
                    if result != "ok":
                        raise ValueError(f"SQLite integrity check: {result}")
                finally:
                    os.unlink(temp_name)
    except Exception as exc:
        row.status = "CORRUPT"; db.commit()
        raise HTTPException(409, f"Backup verification failed: {exc}") from exc
    row.status = "VERIFIED"; row.verified_at = utc_now()
    write_audit(db, action="BACKUP_VERIFIED", entity_type="BACKUP", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"verified_at": str(row.verified_at)})
    db.commit()
    return {"id": row.id, "status": row.status, "verified_at": row.verified_at, "restore_status": "NOT_RESTORED"}


@router.get("/{backup_id}/download")
def download_backup(backup_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(BackupRecord, backup_id)
    if not row:
        raise HTTPException(404, "Backup not found")
    if row.company_id is not None:
        ensure_permission(db, user, row.company_id, "backup.manage")
    path = Path(row.storage_path)
    if not path.exists():
        raise HTTPException(404, "Backup file is missing")
    return FileResponse(path, filename=path.name, media_type="application/zip")
