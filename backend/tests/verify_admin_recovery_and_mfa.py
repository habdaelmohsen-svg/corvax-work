"""Verify the mobile owner-recovery and mandatory MFA enrolment path."""
from __future__ import annotations

import hashlib
import inspect
import os
import sys
import time
from datetime import timedelta
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp/verify_admin_recovery_and_mfa.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "ENVIRONMENT": "testing",
    "SECRET_KEY": "verification-secret-key-admin-recovery-v17",
    "SEED_DEMO_DATA": "false",
    "AUTO_CREATE_SCHEMA": "true",
    "BOOTSTRAP_FIRST_ADMIN": "false",
    "DGTERA_SCHEDULER_ENABLED": "false",
    "ENFORCE_SENSITIVE_ROLE_MFA": "true",
})

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import auth as auth_api
from app.core.security import _totp_code, hash_password, verify_password
from app.core.time import utc_now
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, Company, Role, User, UserCompanyRole


RECOVERY_TOKEN = "test-only-admin-recovery-token-2026-08-21"
NEW_PASSWORD = "RecoveredAdmin@2026!"
FAILSAFE_TOKEN = "test-only-admin-recovery-failsafe-2026-08-21"
FAILSAFE_PASSWORD = "FailsafeAdmin@2026!"


def ok(response, status: int = 200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json()


def main() -> None:
    recovery_source = inspect.getsource(auth_api.recover_admin)
    assert "PasswordHistory" not in recovery_source
    assert "UserSession" not in recovery_source
    assert "with_for_update" in recovery_source

    # Keep the deterministic production expiry while making this verification
    # stable when it is rerun after the emergency window has closed.
    auth_api._ADMIN_RECOVERY_TOKEN_SHA256 = hashlib.sha256(RECOVERY_TOKEN.encode()).hexdigest()
    auth_api._ADMIN_RECOVERY_TOKEN_ID = auth_api._ADMIN_RECOVERY_TOKEN_SHA256[:16]
    auth_api._ADMIN_RECOVERY_ISSUED_AT = utc_now() - timedelta(minutes=10)
    auth_api._ADMIN_RECOVERY_NOT_AFTER = utc_now() + timedelta(minutes=10)

    with TestClient(app) as client:
        with SessionLocal() as db:
            company = Company(code="AUTH", name_ar="شركة الاختبار", name_en="Auth Test")
            role = Role(code="SUPER_ADMIN", name_ar="مدير النظام", name_en="Super Admin")
            admin = User(
                name_ar="مدير النظام",
                name_en="System Administrator",
                email="admin@corvaxplatform.com",
                username="admin",
                password_hash=hash_password("OldAdmin@2026!"),
                password_changed_at=utc_now() - timedelta(days=1),
                active=True,
                failed_login_attempts=4,
                locked_until=utc_now() + timedelta(minutes=15),
                mfa_enabled=True,
                mfa_secret="JBSWY3DPEHPK3PXP",
            )
            db.add_all([company, role, admin])
            db.flush()
            db.add(UserCompanyRole(user_id=admin.id, company_id=company.id, role_id=role.id))
            db.commit()

        invalid = client.post("/api/v1/auth/recover-admin", json={
            "token": "0" * 48,
            "new_password": NEW_PASSWORD,
        })
        assert invalid.status_code == 410

        weak = client.post("/api/v1/auth/recover-admin", json={
            "token": RECOVERY_TOKEN,
            "new_password": "weak-password",
        })
        assert weak.status_code == 422

        recovered = ok(client.post("/api/v1/auth/recover-admin", json={
            "token": RECOVERY_TOKEN,
            "new_password": NEW_PASSWORD,
        }))
        assert recovered == {
            "status": "recovered",
            "login": "admin",
            "mfa_reenrollment_required": True,
        }

        with SessionLocal() as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            assert admin and verify_password(NEW_PASSWORD, admin.password_hash)
            assert admin.active is True
            assert admin.failed_login_attempts == 0
            assert admin.locked_until is None
            assert admin.mfa_enabled is False and admin.mfa_secret is None
            assert admin.token_version == 2
            assert db.scalar(select(func.count(AuditLog.id)).where(
                AuditLog.action == auth_api._ADMIN_RECOVERY_ACTION
            )) == 1

        second_use = client.post("/api/v1/auth/recover-admin", json={
            "token": RECOVERY_TOKEN,
            "new_password": "AnotherAdmin@2026!",
        })
        assert second_use.status_code == 410

        old_login = client.post("/api/v1/auth/login", json={
            "email": "admin",
            "password": "OldAdmin@2026!",
        })
        assert old_login.status_code == 401

        enrollment = client.post("/api/v1/auth/login", json={
            "email": "admin",
            "password": NEW_PASSWORD,
        })
        assert enrollment.status_code == 428, enrollment.text
        detail = enrollment.json()["detail"]
        assert detail["enrollment_required"] is True
        code = _totp_code(detail["secret"], int(time.time()) // 30)
        ok(client.post("/api/v1/auth/mfa/enable-preauth", json={
            "enrollment_token": detail["enrollment_token"],
            "code": code,
        }))
        logged_in = ok(client.post("/api/v1/auth/login", json={
            "email": "admin",
            "password": NEW_PASSWORD,
            "otp": code,
        }))
        assert logged_in["user"]["mfa_enabled"] is True
        assert logged_in["user"]["username"] == "admin"

        # PostgreSQL/UAT has previously contained partial auxiliary schema.
        # Prove an audit-table failure can no longer roll back the essential
        # users-table password change.
        original_write_audit = auth_api.write_audit
        auth_api._ADMIN_RECOVERY_TOKEN_SHA256 = hashlib.sha256(FAILSAFE_TOKEN.encode()).hexdigest()
        auth_api._ADMIN_RECOVERY_TOKEN_ID = auth_api._ADMIN_RECOVERY_TOKEN_SHA256[:16]
        auth_api._ADMIN_RECOVERY_ACTION = "ONE_TIME_ADMIN_RECOVERY_FAILSAFE_TEST"
        auth_api._ADMIN_RECOVERY_ISSUED_AT = utc_now()

        def fail_auxiliary_audit(*_args, **_kwargs):
            raise RuntimeError("simulated auxiliary audit schema drift")

        auth_api.write_audit = fail_auxiliary_audit
        try:
            failsafe = ok(client.post("/api/v1/auth/recover-admin", json={
                "token": FAILSAFE_TOKEN,
                "new_password": FAILSAFE_PASSWORD,
            }))
            assert failsafe["status"] == "recovered"
        finally:
            auth_api.write_audit = original_write_audit

        with SessionLocal() as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            assert admin and verify_password(FAILSAFE_PASSWORD, admin.password_hash)
            assert admin.token_version == 3

    print("Admin recovery, unlock and mandatory MFA enrolment: PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
