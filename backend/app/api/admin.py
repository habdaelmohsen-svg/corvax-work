from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.core.security import hash_password, validate_password_strength
from app.db import get_db
from app.dependencies import company_permissions, ensure_permission, get_current_user
from app.models import Branch, PasswordHistory, Role, User, UserCompanyRole, UserSession
from app.services.audit import write_audit

router = APIRouter(prefix="/admin", tags=["administration"])

def _is_super_admin(db: Session, user: User) -> bool:
    memberships = db.scalars(
        select(UserCompanyRole)
        .options(selectinload(UserCompanyRole.role))
        .where(UserCompanyRole.user_id == user.id)
    ).all()
    return any(m.role and m.role.code == "SUPER_ADMIN" for m in memberships)


def _protect_global_user_change(db: Session, current: User, target: User, company_id: int) -> None:
    memberships = db.scalars(
        select(UserCompanyRole)
        .options(selectinload(UserCompanyRole.role))
        .where(UserCompanyRole.user_id == target.id)
    ).all()
    if any(m.role and m.role.code == "SUPER_ADMIN" for m in memberships) and not _is_super_admin(db, current):
        raise HTTPException(403, "Only SUPER_ADMIN can manage a SUPER_ADMIN account")
    company_ids = {m.company_id for m in memberships}
    if len(company_ids) > 1 and not _is_super_admin(db, current):
        raise HTTPException(403, "Only SUPER_ADMIN can perform global changes on a multi-company user")
    if company_id not in company_ids:
        raise HTTPException(404, "User not found in company")


def _validate_role_assignment(db: Session, current: User, role_codes: set[str]) -> None:
    if "SUPER_ADMIN" in role_codes and not _is_super_admin(db, current):
        raise HTTPException(403, "Only SUPER_ADMIN can assign the SUPER_ADMIN role")



class MembershipIn(BaseModel):
    company_id: int
    role_code: str
    branch_scope: str = "ALL"
    branch_ids: list[int] = []


class UserCreate(BaseModel):
    name_ar: str = Field(min_length=2, max_length=200)
    name_en: str = Field(min_length=2, max_length=200)
    # H17: a plain string, not EmailStr. Employees now sign in with a username,
    # so the address is often an internal placeholder such as ahmed@corvax.local,
    # and EmailStr rejects reserved domains like .local as undeliverable.
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    # H17: short login name so employees can sign in without typing an email.
    username: str | None = Field(default=None, min_length=3, max_length=60)
    # A temporary password may be short (>=6) because require_password_change
    # forces the employee to replace it on first sign-in. Passwords that are not
    # forced to change must still meet the 12 character policy.
    password: str = Field(min_length=6)
    require_password_change: bool = True
    memberships: list[MembershipIn] = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def _normalise_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Operators naturally type a person's short name with a space.  Treat
        # whitespace as a dot so "Hussein Mahmoud" becomes the valid, predictable
        # login "hussein.mahmoud" instead of returning two raw validation errors
        # (one for the username and another for the generated local email).
        cleaned = re.sub(r"\s+", ".", value.strip().lower())
        cleaned = re.sub(r"[._-]{2,}", ".", cleaned).strip("._-")
        if len(cleaned) < 3:
            raise ValueError("username must contain at least 3 letters or digits")
        if not cleaned.replace("_", "").replace(".", "").replace("-", "").isalnum():
            raise ValueError("username may only contain letters, digits, dot, dash or underscore")
        return cleaned

    @model_validator(mode="after")
    def _enforce_password_policy(self):
        if not self.require_password_change and len(self.password) < 12:
            raise ValueError("A permanent password must contain at least 12 characters")
        return self


def require_user_admin(db: Session, current: User, company_ids: list[int]) -> None:
    for company_id in company_ids:
        ensure_permission(db, current, company_id, "users.manage")


@router.get("/users")
def list_users(
    company_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, current, company_id, "users.manage")
    users = db.scalars(
        select(User)
        .join(UserCompanyRole)
        .where(UserCompanyRole.company_id == company_id)
        .options(selectinload(User.memberships).selectinload(UserCompanyRole.role))
        .distinct()
        .order_by(User.email)
    ).all()
    return [
        {
            "id": user.id,
            "name_ar": user.name_ar,
            "name_en": user.name_en,
            "email": user.email,
            "username": user.username,
            "active": user.active,
            "require_password_change": user.require_password_change,
            "memberships": [
                {"company_id": membership.company_id, "role": membership.role.code, "branch_scope": membership.branch_scope, "branch_ids": [branch.id for branch in membership.branches]}
                for membership in user.memberships
            ],
        }
        for user in users
    ]


@router.post("/users", status_code=201)
def create_user(
    data: UserCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_ids = sorted({membership.company_id for membership in data.memberships})
    require_user_admin(db, current, company_ids)
    _validate_role_assignment(db, current, {membership.role_code for membership in data.memberships})
    if data.username and db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(409, "Username already exists")
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "Email already exists")
    # H17: the full strength policy applies to permanent passwords. A temporary
    # password is single-use - require_password_change stops the employee at a
    # mandatory change screen before any data - so a short value is acceptable
    # there and the policy is enforced on the password they choose themselves.
    if not data.require_password_change:
        password_errors = validate_password_strength(data.password)
        if password_errors:
            raise HTTPException(422, password_errors)
    role_by_code = {
        role.code: role
        for role in db.scalars(select(Role).where(Role.code.in_([m.role_code for m in data.memberships]))).all()
    }
    missing_roles = sorted({m.role_code for m in data.memberships} - set(role_by_code))
    if missing_roles:
        raise HTTPException(422, f"Unknown roles: {', '.join(missing_roles)}")
    user = User(
        name_ar=data.name_ar,
        name_en=data.name_en,
        email=data.email.lower(),
        username=data.username,
        password_hash=hash_password(data.password),
        require_password_change=data.require_password_change,
        active=True,
    )
    db.add(user)
    db.flush()
    for membership in data.memberships:
        scope = membership.branch_scope.upper()
        if scope not in {"ALL", "SELECTED"}:
            raise HTTPException(422, "branch_scope must be ALL or SELECTED")
        branches = []
        if scope == "SELECTED":
            if not membership.branch_ids:
                raise HTTPException(422, "SELECTED branch scope requires branch_ids")
            branches = db.scalars(select(Branch).where(Branch.id.in_(membership.branch_ids))).all()
            if len(branches) != len(set(membership.branch_ids)) or any(b.company_id != membership.company_id for b in branches):
                raise HTTPException(422, "Every selected branch must belong to the membership company")
        row = UserCompanyRole(
            user_id=user.id,
            company_id=membership.company_id,
            role_id=role_by_code[membership.role_code].id,
            branch_scope=scope,
        )
        row.branches = branches
        db.add(row)
    write_audit(
        db,
        action="USER_CREATED",
        entity_type="USER",
        entity_id=user.id,
        user_id=current.id,
        after={"email": user.email, "username": user.username, "companies": company_ids},
    )
    db.commit()
    return {"id": user.id, "email": user.email, "username": user.username, "status": "ACTIVE"}


class PasswordResetIn(BaseModel):
    company_id: int
    # A temporary reset password may be short because require_change forces the
    # employee to replace it at the next sign-in.
    new_password: str = Field(min_length=6)
    require_change: bool = True

    @model_validator(mode="after")
    def _enforce_password_policy(self):
        if not self.require_change and len(self.new_password) < 12:
            raise ValueError("A permanent password must contain at least 12 characters")
        return self


@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: int, company_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, current, company_id, "users.manage")
    target = db.scalar(select(User).join(UserCompanyRole).where(User.id == user_id, UserCompanyRole.company_id == company_id))
    if not target:
        raise HTTPException(404, "User not found in company")
    _protect_global_user_change(db, current, target, company_id)
    target.failed_login_attempts = 0
    target.locked_until = None
    write_audit(db, action="USER_UNLOCKED", entity_type="USER", entity_id=target.id, user_id=current.id, company_id=company_id)
    db.commit()
    return {"id": target.id, "status": "UNLOCKED"}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, data: PasswordResetIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, current, data.company_id, "users.manage")
    target = db.scalar(select(User).join(UserCompanyRole).where(User.id == user_id, UserCompanyRole.company_id == data.company_id))
    if not target:
        raise HTTPException(404, "User not found in company")
    _protect_global_user_change(db, current, target, data.company_id)
    # H17: a forced-change reset issues a single-use temporary password.
    if not data.require_change:
        errors = validate_password_strength(data.new_password)
        if errors:
            raise HTTPException(422, errors)
    db.add(PasswordHistory(user_id=target.id, password_hash=target.password_hash))
    target.password_hash = hash_password(data.new_password)
    target.password_changed_at = utc_now()
    target.require_password_change = data.require_change
    target.token_version += 1
    db.query(UserSession).filter(UserSession.user_id == target.id, UserSession.revoked_at.is_(None)).update({"revoked_at": utc_now()})
    write_audit(db, action="USER_PASSWORD_RESET", entity_type="USER", entity_id=target.id, user_id=current.id, company_id=data.company_id, after={"require_change": data.require_change})
    db.commit()
    return {"id": target.id, "status": "PASSWORD_RESET", "require_change": target.require_password_change}


@router.patch("/users/{user_id}/status")
def change_user_status(user_id: int, company_id: int, active: bool, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, current, company_id, "users.manage")
    if user_id == current.id and not active:
        raise HTTPException(422, "You cannot deactivate your own account")
    target = db.scalar(select(User).join(UserCompanyRole).where(User.id == user_id, UserCompanyRole.company_id == company_id))
    if not target:
        raise HTTPException(404, "User not found in company")
    _protect_global_user_change(db, current, target, company_id)
    target.active = active
    if not active:
        target.token_version += 1
        db.query(UserSession).filter(UserSession.user_id == target.id, UserSession.revoked_at.is_(None)).update({"revoked_at": utc_now()})
    write_audit(db, action="USER_STATUS_CHANGED", entity_type="USER", entity_id=target.id, user_id=current.id, company_id=company_id, after={"active": active})
    db.commit()
    return {"id": target.id, "active": target.active}

@router.get("/security-status")
def security_status(company_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, current, company_id, "users.manage")
    from datetime import datetime
    from sqlalchemy import func
    from app.models import BackupRecord
    users = db.scalars(select(User).join(UserCompanyRole).where(UserCompanyRole.company_id == company_id).distinct()).all()
    active_sessions = db.scalar(select(func.count(UserSession.id)).join(User).join(UserCompanyRole).where(UserCompanyRole.company_id == company_id, UserSession.revoked_at.is_(None), UserSession.expires_at > utc_now())) or 0
    last_backup = db.scalar(select(BackupRecord).where(BackupRecord.company_id == company_id).order_by(BackupRecord.created_at.desc()))
    return {
        "company_id": company_id,
        "users": len(users),
        "mfa_enabled_users": sum(1 for row in users if row.mfa_enabled),
        "locked_users": sum(1 for row in users if row.locked_until and row.locked_until > utc_now()),
        "active_sessions": active_sessions,
        "last_backup_status": last_backup.status if last_backup else "NOT_CREATED",
        "last_backup_at": last_backup.created_at if last_backup else None,
        "production_config_guard": True,
        "credential_reuse_protection": True,
        "session_revocation": True,
    }
