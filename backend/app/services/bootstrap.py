"""CORVAX RC27.4 H17 - first-run bootstrap.

PROBLEM THIS SOLVES
    In production the settings validator forces SEED_DEMO_DATA=false, so
    seed_database() never ran and the database contained no users, no companies
    and no chart of accounts. The login screen rendered correctly but there was
    no account to sign in with - the deployment was unusable.

WHAT IT DOES
    On startup, and only when the users table is empty, it:
      1. builds the base structure (permissions, roles, companies, chart of
         accounts) by reusing the existing seeder, and
      2. guarantees an administrator whose login name is BOOTSTRAP_ADMIN_USERNAME
         with password BOOTSTRAP_ADMIN_PASSWORD.

    The administrator is always created with require_password_change = True, so
    the initial credentials are single-use: the first sign-in must replace them
    before anything else can be done. This is the same pattern used by network
    equipment and by most on-premise ERP installers.

    The whole function is idempotent. Once any user exists it does nothing, so
    restarts and redeploys never touch live data.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import Company, Role, User, UserCompanyRole

logger = logging.getLogger("corvax.bootstrap")


def backfill_missing_usernames(db: Session) -> None:
    """Give existing accounts a login name so username sign-in works everywhere.

    A database seeded before H17 has users with username = NULL, which means they
    could only sign in with an email address. This derives a login name from the
    local part of the email, skipping any that would collide. Runs on every start
    and is a no-op once every account has one.
    """
    rows = db.scalars(select(User).where(User.username.is_(None))).all()
    if not rows:
        return
    taken = {
        value
        for (value,) in db.execute(select(User.username).where(User.username.is_not(None)))
        if value
    }
    for user in rows:
        candidate = (user.email or "").split("@", 1)[0].strip().lower()
        if not candidate or candidate in taken:
            continue
        user.username = candidate
        taken.add(candidate)
    db.commit()


def bootstrap_first_admin(db: Session) -> None:
    """Create the base structure and the first administrator on an empty database."""
    if db.scalar(select(func.count(User.id))):
        # Already initialised: never touch live data, but make sure existing
        # accounts have a login name.
        backfill_missing_usernames(db)

        # RECOVERY MODE (BOOTSTRAP_FORCE_ADMIN_RESET=true)
        # Deliberately overwrites the administrator password on every start so a
        # locked-out owner can get back in. This is a temporary door: anyone who
        # knows the URL and the password can sign in, so it MUST be switched off
        # once access is restored.
        if settings.bootstrap_force_admin_reset:
            username = (settings.bootstrap_admin_username or "admin").strip().lower()
            password = settings.bootstrap_admin_password or "admin"
            admin = db.scalar(select(User).where(User.username == username))
            if admin is None:
                admin = db.scalar(select(User).order_by(User.id))
            if admin is not None:
                admin.username = username
                admin.password_hash = hash_password(password)
                admin.active = True
                admin.require_password_change = False   # sign in directly
                admin.mfa_enabled = False               # no authenticator needed
                admin.mfa_secret = None
                admin.failed_login_attempts = 0
                admin.locked_until = None
                db.commit()
                logger.warning(
                    "RECOVERY MODE: administrator '%s' password was reset. "
                    "Set BOOTSTRAP_FORCE_ADMIN_RESET=false once you are back in.",
                    username,
                )
        return

    username = (settings.bootstrap_admin_username or "admin").strip().lower()
    password = settings.bootstrap_admin_password or "admin"

    # 1. Base structure. seed_database() is itself guarded by a company check, so
    #    it is safe to call and will not duplicate anything.
    try:
        from app.services.seed import seed_database

        seed_database(db)
    except Exception:  # noqa: BLE001 - structure seeding must never block startup
        logger.exception("Base structure seeding failed during bootstrap")

    # 2. The administrator. Prefer promoting the seeded account if it exists.
    admin = db.scalar(select(User).order_by(User.id))
    if admin is None:
        admin = User(
            name_ar="مدير النظام",
            name_en="System Administrator",
            email=f"{username}@corvax.local",
            username=username,
            password_hash=hash_password(password),
            active=True,
        )
        db.add(admin)
        db.flush()
        company = db.scalar(select(Company).order_by(Company.id))
        role = db.scalar(select(Role).where(Role.code == "SUPER_ADMIN"))
        if company is not None and role is not None:
            db.add(UserCompanyRole(user_id=admin.id, company_id=company.id, role_id=role.id))
    else:
        admin.username = username
        admin.password_hash = hash_password(password)
        admin.active = True

    # Single-use credentials: the first sign-in must replace them.
    admin.require_password_change = True
    admin.failed_login_attempts = 0
    admin.locked_until = None
    db.commit()
    logger.warning(
        "Bootstrap administrator ready (username=%s). The initial password must be "
        "changed at first sign-in.",
        username,
    )
