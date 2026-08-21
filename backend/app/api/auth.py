from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.security import (
    create_refresh_token,
    create_token,
    decode_token,
    generate_mfa_secret,
    hash_password,
    hash_refresh_token,
    mfa_uri,
    validate_password_strength,
    verify_password,
    verify_refresh_token,
    verify_totp,
)
from app.core.time import utc_now
from app.db import get_db
from app.dependencies import company_permissions, ensure_company_access, get_current_user
from app.models import AuditLog, PasswordHistory, Role, User, UserCompanyRole, UserSession
from app.schemas.auth import (
    CompanyContextIn,
    LoginIn,
    LoginOut,
    MfaVerifyIn,
    PasswordChangeIn,
    RefreshTokenOut,
    UserOut,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/auth", tags=["authentication"])


# One-time owner recovery for the August 2026 UAT lockout. Only the SHA-256
# digest is committed; the high-entropy token is delivered privately to the
# owner. The token expires, is consumed through the tamper-evident audit log,
# and can never be used as an application session.
_ADMIN_RECOVERY_TOKEN_SHA256 = "ecb85eb6bfffdce991aaf4a5caf8e9cdf952ee32f0f19240ff859ca0f61c3fe2"
_ADMIN_RECOVERY_TOKEN_ID = _ADMIN_RECOVERY_TOKEN_SHA256[:16]
_ADMIN_RECOVERY_LOCK_KEY = int(_ADMIN_RECOVERY_TOKEN_SHA256[:15], 16)
_ADMIN_RECOVERY_NOT_AFTER = datetime(2026, 8, 23, 23, 59, 59)
_ADMIN_RECOVERY_ACTION = "ONE_TIME_ADMIN_RECOVERY_V17"


class AdminRecoveryIn(BaseModel):
    token: str = Field(min_length=40, max_length=160)
    new_password: str = Field(min_length=12, max_length=200)


def _role_codes(db: Session, user_id: int) -> set[str]:
    memberships = db.scalars(
        select(UserCompanyRole)
        .options(selectinload(UserCompanyRole.role))
        .where(UserCompanyRole.user_id == user_id)
    ).all()
    return {membership.role.code.upper() for membership in memberships}


def user_to_out(db: Session, user: User) -> UserOut:
    memberships = db.scalars(
        select(UserCompanyRole)
        .options(selectinload(UserCompanyRole.role).selectinload(Role.permissions), selectinload(UserCompanyRole.branches))
        .where(UserCompanyRole.user_id == user.id)
    ).all()
    company_ids = sorted({m.company_id for m in memberships})
    permissions_by_company = {company_id: sorted(company_permissions(db, user, company_id)) for company_id in company_ids}
    role_codes = sorted({m.role.code for m in memberships})
    branch_scope_by_company: dict[int, dict] = {}
    for company_id in company_ids:
        company_memberships = [m for m in memberships if m.company_id == company_id]
        all_scope = any((m.branch_scope or "ALL").upper() == "ALL" for m in company_memberships)
        branch_scope_by_company[company_id] = {
            "scope": "ALL" if all_scope else "SELECTED",
            "branch_ids": [] if all_scope else sorted({b.id for m in company_memberships for b in m.branches}),
        }
    return UserOut(
        id=user.id,
        name_ar=user.name_ar,
        name_en=user.name_en,
        email=user.email,
        username=user.username,
        role=role_codes[0] if len(role_codes) == 1 else "MULTI_ROLE",
        allowed_company_ids=company_ids,
        permissions_by_company=permissions_by_company,
        branch_scope_by_company=branch_scope_by_company,
        mfa_enabled=user.mfa_enabled,
        require_password_change=user.require_password_change,
    )


def _create_session_pair(
    db: Session,
    *,
    user: User,
    request: Request,
    parent_session_id: str | None = None,
) -> tuple[UserSession, str, str, object, object]:
    now = utc_now()
    session_id = secrets.token_urlsafe(32)
    access_token, access_expires = create_token(user.id, session_id, user.token_version)
    refresh_token, refresh_hash, refresh_expires = create_refresh_token()
    session = UserSession(
        id=session_id,
        user_id=user.id,
        token_version=user.token_version,
        issued_at=now,
        expires_at=access_expires.replace(tzinfo=None),
        last_seen_at=now,
        refresh_token_hash=refresh_hash,
        refresh_expires_at=refresh_expires.replace(tzinfo=None),
        parent_session_id=parent_session_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    db.add(session)
    return session, access_token, refresh_token, access_expires, refresh_expires


@router.post("/login", response_model=LoginOut)
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginOut:
    now = utc_now()
    # H17: accept a username or an email address in the same field.
    identifier = data.email.strip().lower()
    user = db.scalar(
        select(User).where(or_(User.email == identifier, User.username == identifier))
    )
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(423, "Account is temporarily locked")
    if not user or not user.active or not verify_password(data.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_attempts = 0
            write_audit(
                db,
                action="LOGIN_FAILED",
                entity_type="USER",
                entity_id=user.id,
                user_id=user.id,
                after={"ip": request.client.host if request.client else None},
            )
            db.commit()
        raise HTTPException(401, "Invalid username or password")

    role_codes = _role_codes(db, user.id)
    sensitive_mfa_required = settings.enforce_sensitive_role_mfa and bool(role_codes & settings.sensitive_roles)
    if sensitive_mfa_required and not user.mfa_enabled:
        write_audit(
            db,
            action="MFA_ENROLLMENT_REQUIRED",
            entity_type="USER",
            entity_id=user.id,
            user_id=user.id,
            after={"roles": sorted(role_codes & settings.sensitive_roles)},
        )
        enrolment_secret = user.mfa_secret or generate_mfa_secret()
        user.mfa_secret = enrolment_secret
        db.commit()
        # AUDIT C-04: this used to be a dead end. Enrolment needed an access token,
        # but the token was withheld until MFA was enabled. The response now carries
        # everything required to enrol (secret + otpauth URI) plus a short-lived
        # enrolment token accepted only by /auth/mfa/enable-preauth.
        raise HTTPException(
            428,
            {
                "message": "MFA enrollment is mandatory for this sensitive role",
                "enrollment_required": True,
                "secret": enrolment_secret,
                "otpauth_uri": mfa_uri(enrolment_secret, user.username or user.email),
                "enrollment_token": _issue_enrolment_token(user),
                "next": "/api/v1/auth/mfa/enable-preauth",
            },
        )
    if user.mfa_enabled and (not user.mfa_secret or not verify_totp(user.mfa_secret, data.otp or "")):
        write_audit(db, action="MFA_FAILED", entity_type="USER", entity_id=user.id, user_id=user.id)
        db.commit()
        raise HTTPException(401, "Valid MFA code required")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    session, access_token, refresh_token, access_expires, refresh_expires = _create_session_pair(
        db, user=user, request=request
    )
    write_audit(
        db,
        action="LOGIN_SUCCESS",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        after={"session_id": session.id[:12], "jwt_kid": settings.jwt_active_kid},
    )
    db.commit()
    response.set_cookie(
        key="corvax_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="strict",
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )
    return LoginOut(
        access_token=access_token,
        access_expires_at=access_expires,
        refresh_expires_at=refresh_expires,
        user=user_to_out(db, user),
    )


@router.post("/recover-admin")
def recover_admin(
    data: AdminRecoveryIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Consume the owner-only recovery token and replace the admin password.

    The endpoint intentionally grants no session. It revokes every existing
    admin session, clears a stale lock/MFA enrolment, and requires a normal
    login afterwards. Production MFA policy is then enforced by ``login``.
    """
    response.headers["Cache-Control"] = "no-store"
    supplied_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    token_valid = secrets.compare_digest(supplied_hash, _ADMIN_RECOVERY_TOKEN_SHA256)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # Serialize consumption so two simultaneous taps cannot both pass the
        # one-time audit check before either transaction commits.
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMIN_RECOVERY_LOCK_KEY})
    already_used = db.scalar(
        select(AuditLog.id).where(
            AuditLog.action == _ADMIN_RECOVERY_ACTION,
            AuditLog.entity_id == _ADMIN_RECOVERY_TOKEN_ID,
        )
    )
    if not token_valid or utc_now() > _ADMIN_RECOVERY_NOT_AFTER or already_used:
        raise HTTPException(410, "Recovery link is invalid, expired, or already used")

    username = (settings.bootstrap_admin_username or "admin").strip().lower()
    admin = db.scalar(select(User).where(User.username == username))
    if admin is None:
        admin = db.scalar(
            select(User)
            .join(UserCompanyRole, UserCompanyRole.user_id == User.id)
            .join(Role, Role.id == UserCompanyRole.role_id)
            .where(Role.code == "SUPER_ADMIN")
            .order_by(User.id)
        )
    if admin is None:
        raise HTTPException(503, "Administrator recovery is unavailable")

    errors = validate_password_strength(data.new_password)
    if errors:
        raise HTTPException(422, errors)
    if verify_password(data.new_password, admin.password_hash):
        raise HTTPException(422, "New password must differ from the current password")
    recent = db.scalars(
        select(PasswordHistory)
        .where(PasswordHistory.user_id == admin.id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(settings.password_history_count)
    ).all()
    if any(verify_password(data.new_password, row.password_hash) for row in recent):
        raise HTTPException(422, "Password was used recently")

    now = utc_now()
    db.add(PasswordHistory(user_id=admin.id, password_hash=admin.password_hash))
    admin.password_hash = hash_password(data.new_password)
    admin.password_changed_at = now
    admin.require_password_change = False
    admin.active = True
    admin.failed_login_attempts = 0
    admin.locked_until = None
    admin.mfa_enabled = False
    admin.mfa_secret = None
    admin.token_version += 1
    db.query(UserSession).filter(
        UserSession.user_id == admin.id,
        UserSession.revoked_at.is_(None),
    ).update({"revoked_at": now, "revoke_reason": "ADMIN_RECOVERY"})
    write_audit(
        db,
        action=_ADMIN_RECOVERY_ACTION,
        entity_type="AUTH_RECOVERY_TOKEN",
        entity_id=_ADMIN_RECOVERY_TOKEN_ID,
        user_id=admin.id,
        after={
            "admin_user_id": admin.id,
            "ip": request.client.host if request.client else None,
            "sessions_revoked": True,
            "mfa_reenrollment_required": bool(settings.enforce_sensitive_role_mfa),
        },
    )
    db.commit()
    return {
        "status": "recovered",
        "login": admin.username or admin.email,
        "mfa_reenrollment_required": bool(settings.enforce_sensitive_role_mfa),
    }


@router.post("/refresh", response_model=RefreshTokenOut)
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)) -> RefreshTokenOut:
    now = utc_now()
    refresh_token_value = request.cookies.get("corvax_refresh_token")
    if not refresh_token_value:
        raise HTTPException(401, "Missing refresh cookie")
    refresh_hash = hash_refresh_token(refresh_token_value)
    current = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == refresh_hash))
    if (
        not current
        or current.revoked_at is not None
        or current.refresh_expires_at is None
        or current.refresh_expires_at <= now
        or not verify_refresh_token(refresh_token_value, current.refresh_token_hash)
    ):
        raise HTTPException(401, "Invalid or expired refresh token")
    user = db.get(User, current.user_id)
    if not user or not user.active or user.token_version != current.token_version:
        raise HTTPException(401, "Session is no longer valid")

    current.revoked_at = now
    current.rotated_at = now
    current.revoke_reason = "REFRESH_ROTATED"
    new_session, access_token, refresh_token, access_expires, refresh_expires = _create_session_pair(
        db, user=user, request=request, parent_session_id=current.id
    )
    write_audit(
        db,
        action="SESSION_REFRESHED",
        entity_type="USER_SESSION",
        entity_id=new_session.id,
        user_id=user.id,
        after={"parent_session_id": current.id[:12], "new_session_id": new_session.id[:12]},
    )
    db.commit()
    response.set_cookie(
        key="corvax_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="strict",
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )
    return RefreshTokenOut(
        access_token=access_token,
        access_expires_at=access_expires,
        refresh_expires_at=refresh_expires,
    )


@router.post("/logout")
def logout(
    response: Response,
    authorization: str | None = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = utc_now()
    revoked = 0
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = decode_token(authorization.removeprefix("Bearer "))
            session = db.get(UserSession, str(payload.get("sid")))
            if session and session.user_id == user.id and session.revoked_at is None:
                session.revoked_at = now
                session.revoke_reason = "USER_LOGOUT"
                revoked = 1
        except ValueError:
            pass
    write_audit(
        db,
        action="LOGOUT",
        entity_type="USER",
        entity_id=user.id,
        user_id=user.id,
        after={"revoked_sessions": revoked},
    )
    db.commit()
    response.delete_cookie("corvax_refresh_token", path="/api/v1/auth")
    return {"status": "logged_out", "revoked_sessions": revoked}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_to_out(db, user)


@router.post("/mfa/setup")
def setup_mfa(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = generate_mfa_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False
    write_audit(db, action="MFA_SETUP_STARTED", entity_type="USER", entity_id=user.id, user_id=user.id)
    db.commit()
    return {"secret": secret, "otpauth_uri": mfa_uri(secret, user.email), "enabled": False}


@router.post("/mfa/enable")
def enable_mfa(data: MfaVerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_secret or not verify_totp(user.mfa_secret, data.code):
        raise HTTPException(422, "Invalid MFA code")
    now = utc_now()
    user.mfa_enabled = True
    user.token_version += 1
    db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).update(
        {"revoked_at": now, "revoke_reason": "MFA_ENABLED"}
    )
    write_audit(db, action="MFA_ENABLED", entity_type="USER", entity_id=user.id, user_id=user.id)
    db.commit()
    return {"enabled": True, "relogin_required": True}


@router.post("/password/change")
def change_password(data: PasswordChangeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(422, "Current password is incorrect")
    errors = validate_password_strength(data.new_password)
    if errors:
        raise HTTPException(422, errors)
    if verify_password(data.new_password, user.password_hash):
        raise HTTPException(422, "New password must differ from current password")
    recent = db.scalars(
        select(PasswordHistory)
        .where(PasswordHistory.user_id == user.id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(settings.password_history_count)
    ).all()
    if any(verify_password(data.new_password, row.password_hash) for row in recent):
        raise HTTPException(422, "Password was used recently")
    now = utc_now()
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    user.password_hash = hash_password(data.new_password)
    user.password_changed_at = now
    user.require_password_change = False
    user.token_version += 1
    db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).update(
        {"revoked_at": now, "revoke_reason": "PASSWORD_CHANGED"}
    )
    write_audit(db, action="PASSWORD_CHANGED", entity_type="USER", entity_id=user.id, user_id=user.id)
    db.commit()
    return {"status": "password_changed", "relogin_required": True}


@router.post("/company-context")
def set_company_context(
    data: CompanyContextIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    permissions = ensure_company_access(db, user, data.company_id)
    write_audit(
        db,
        action="COMPANY_CONTEXT_SELECTED",
        entity_type="COMPANY",
        entity_id=data.company_id,
        user_id=user.id,
        company_id=data.company_id,
    )
    db.commit()
    from app.dependencies import allowed_branch_ids
    return {"company_id": data.company_id, "status": "active", "permissions": sorted(permissions), "allowed_branch_ids": sorted(allowed_branch_ids(db, user, data.company_id))}

# ---------------------------------------------------------------- MFA enrolment
# AUDIT C-04 support: a signed, short-lived token that ONLY allows completing MFA
# enrolment. It grants no access to data.
_ENROLMENT_TTL_SECONDS = 600


def _issue_enrolment_token(user: User) -> str:
    import hashlib
    import hmac
    import time

    expires = int(time.time()) + _ENROLMENT_TTL_SECONDS
    payload = f"{user.id}.{expires}"
    signature = hmac.new(
        settings.secret_key.encode(), f"mfa-enrol:{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def _verify_enrolment_token(token: str) -> int:
    import hashlib
    import hmac
    import time

    try:
        user_id_text, expires_text, signature = token.split(".")
        payload = f"{user_id_text}.{expires_text}"
    except ValueError as exc:
        raise HTTPException(401, "Invalid enrollment token") from exc
    expected = hmac.new(
        settings.secret_key.encode(), f"mfa-enrol:{payload}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid enrollment token")
    if int(expires_text) < int(time.time()):
        raise HTTPException(401, "Enrollment token has expired")
    return int(user_id_text)


class PreAuthMfaIn(BaseModel):
    enrollment_token: str
    code: str = Field(min_length=6, max_length=6)


@router.post("/mfa/enable-preauth")
def enable_mfa_preauth(data: PreAuthMfaIn, db: Session = Depends(get_db)):
    """Complete MFA enrolment without an access token (audit C-04).

    Used only by a sensitive-role user who is blocked at sign-in until MFA is
    enabled. The enrolment token proves identity, the TOTP code proves the
    authenticator was configured. No session is issued here - the user signs in
    again normally afterwards with their code.
    """
    user_id = _verify_enrolment_token(data.enrollment_token)
    user = db.scalar(select(User).where(User.id == user_id, User.active.is_(True)))
    if not user or not user.mfa_secret:
        raise HTTPException(404, "Enrollment is not in progress for this user")
    if not verify_totp(user.mfa_secret, data.code):
        raise HTTPException(422, "Invalid MFA code")
    user.mfa_enabled = True
    write_audit(db, action="MFA_ENABLED_PREAUTH", entity_type="USER", entity_id=user.id, user_id=user.id)
    db.commit()
    return {"enabled": True, "message": "MFA enabled. Sign in again with your code."}
