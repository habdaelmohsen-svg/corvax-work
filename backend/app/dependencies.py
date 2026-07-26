from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.core.security import decode_token
from app.db import get_db
from app.models import Branch, Role, User, UserCompanyRole, UserSession


# Endpoints reachable while a password change is pending (audit H-02).
_PASSWORD_CHANGE_ALLOWED_PATHS = {
    "/api/v1/auth/password/change",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/mfa/setup",
    "/api/v1/auth/mfa/enable",
}
# How often the session heartbeat is persisted (audit M-11).
_LAST_SEEN_REFRESH_SECONDS = 300


def get_current_user(
    request: Request = None,  # noqa: B008 - FastAPI injects the live request
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing access token")
    try:
        payload = decode_token(authorization.removeprefix("Bearer "))
    except Exception as exc:
        raise HTTPException(401, "Invalid or expired access token") from exc
    session = db.scalar(
        select(UserSession).where(
            UserSession.id == str(payload.get("sid")),
            UserSession.user_id == int(payload["sub"]),
        )
    )
    if not session or session.revoked_at is not None or session.expires_at < utc_now():
        raise HTTPException(401, "Session is expired or revoked")
    user = db.scalar(
        select(User)
        .options(selectinload(User.memberships).selectinload(UserCompanyRole.role))
        .where(User.id == int(payload["sub"]), User.active.is_(True))
    )
    if not user or int(payload.get("ver", 0)) != user.token_version or session.token_version != user.token_version:
        raise HTTPException(401, "Session is no longer valid")
    # AUDIT M-11: last_seen_at used to be written on EVERY request, turning reads
    # into writes. Refresh it at most once every few minutes instead.
    now = utc_now()
    last_seen = session.last_seen_at
    if last_seen is None or (now - last_seen).total_seconds() >= _LAST_SEEN_REFRESH_SECONDS:
        session.last_seen_at = now
        db.commit()

    # AUDIT H-02: a temporary password must be replaced before anything else.
    # The login response flagged it but no endpoint enforced it, so a user with
    # require_password_change could reach protected data. Only the endpoints that
    # let the user fix the situation are allowed through.
    if getattr(user, "require_password_change", False):
        path = (request.url.path or "").rstrip("/") if request is not None else ""
        if path not in _PASSWORD_CHANGE_ALLOWED_PATHS:
            raise HTTPException(
                428,
                "A password change is required before using the system",
            )
    return user


def company_permissions(db: Session, user: User, company_id: int) -> set[str]:
    memberships = db.scalars(
        select(UserCompanyRole)
        .options(selectinload(UserCompanyRole.role).selectinload(Role.permissions))
        .where(UserCompanyRole.user_id == user.id, UserCompanyRole.company_id == company_id)
    ).all()
    permissions: set[str] = set()
    for membership in memberships:
        permissions.update(permission.code for permission in membership.role.permissions)
    return permissions


def ensure_company_access(db: Session, user: User, company_id: int) -> set[str]:
    permissions = company_permissions(db, user, company_id)
    if not permissions:
        raise HTTPException(403, "Company access denied")
    return permissions


def ensure_permission(db: Session, user: User, company_id: int, permission: str) -> set[str]:
    permissions = ensure_company_access(db, user, company_id)
    if "*" not in permissions and permission not in permissions:
        raise HTTPException(403, f"Missing permission: {permission}")
    return permissions


def allowed_branch_ids(db: Session, user: User, company_id: int) -> set[int]:
    memberships = db.scalars(
        select(UserCompanyRole)
        .options(selectinload(UserCompanyRole.branches))
        .where(UserCompanyRole.user_id == user.id, UserCompanyRole.company_id == company_id)
    ).all()
    if not memberships:
        raise HTTPException(403, "Company access denied")
    if any((membership.branch_scope or "ALL").upper() == "ALL" for membership in memberships):
        return set(db.scalars(select(Branch.id).where(Branch.company_id == company_id)).all())
    branch_ids: set[int] = set()
    for membership in memberships:
        branch_ids.update(branch.id for branch in membership.branches)
    return branch_ids


def ensure_branch_access(db: Session, user: User, company_id: int, branch_id: int) -> None:
    branch = db.get(Branch, branch_id)
    if not branch or branch.company_id != company_id:
        raise HTTPException(422, "Branch does not belong to company")
    if branch_id not in allowed_branch_ids(db, user, company_id):
        raise HTTPException(403, "Branch access denied")


# ------------------------------------------------------------- branch isolation
# AUDIT C-05: branch_id exists on 32 tables and branch_scope_by_company is computed
# at sign-in, but almost no list endpoint filtered by it, so a user restricted to a
# single branch could read every branch of the company.
#
# Usage:
#   condition = branch_scope_condition(db, user, company_id, PosOrder)
#   query = select(PosOrder).where(PosOrder.company_id == company_id)
#   if condition is not None:
#       query = query.where(condition)


def has_full_branch_scope(db: Session, user: User, company_id: int) -> bool:
    """True when the user is not restricted to specific branches."""
    memberships = db.scalars(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == user.id, UserCompanyRole.company_id == company_id
        )
    ).all()
    if not memberships:
        raise HTTPException(403, "Company access denied")
    return any((membership.branch_scope or "ALL").upper() == "ALL" for membership in memberships)


def branch_scope_condition(db: Session, user: User, company_id: int, model):
    """Return a filter restricting ``model`` rows to the user's branches.

    Returns None when no restriction applies - the user has full scope, or the
    model has no branch_id. Rows with a NULL branch_id remain visible: they are
    company-level records, not another branch's data.
    """
    column = getattr(model, "branch_id", None)
    if column is None:
        return None
    if has_full_branch_scope(db, user, company_id):
        return None
    permitted = allowed_branch_ids(db, user, company_id)
    if not permitted:
        return column.is_(None)
    return or_(column.is_(None), column.in_(permitted))

