"""CORVAX - chart of accounts management.

GAP THIS CLOSES
    The chart of accounts was read-only. It was created once by the seeder with
    three levels and there was no endpoint - and no screen - to add, rename or
    retire an account. An accounting system that cannot extend its own chart is
    not usable for a real business, and a 4th or 5th level was impossible.

WHAT THIS PROVIDES
    * create an account under any parent, to any depth
    * rename / re-classify / activate / deactivate
    * a tree view that shows the hierarchy with balances
    * guards that protect the ledger

GUARDS (these are the accounting rules, not optional niceties)
    * A parent may not be postable. The moment an account gains a child it stops
      accepting entries, because a total must not also hold its own movements.
    * The child inherits account_type and statement_group from the parent, so a
      liability can never end up hanging under assets.
    * An account that already carries journal lines cannot change its type or be
      deleted - only deactivated - otherwise historical statements would shift.
    * Codes are unique per company and must sit under the parent's numeric range.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Account, User
from app.models.finance import JournalLine
from app.services.audit import write_audit

router = APIRouter(prefix="/chart-of-accounts", tags=["chart of accounts"])

ACCOUNT_TYPES = ["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"]
MAX_DEPTH = 8  # deep enough for any practical chart; guards against loops


class AccountIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=30)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    parent_code: str | None = None
    # Only needed for a root account; otherwise inherited from the parent.
    account_type: str | None = None
    statement_group: str | None = None
    is_cash: bool = False


class AccountUpdate(BaseModel):
    company_id: int
    name_ar: str | None = Field(default=None, min_length=2, max_length=250)
    name_en: str | None = Field(default=None, min_length=2, max_length=250)
    is_cash: bool | None = None
    active: bool | None = None


def _get(db: Session, company_id: int, code: str) -> Account:
    account = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code))
    if not account:
        raise HTTPException(404, f"Account not found: {code}")
    return account


def _has_movements(db: Session, account_id: int) -> int:
    return db.scalar(select(func.count(JournalLine.id)).where(JournalLine.account_id == account_id)) or 0


@router.get("/tree")
def account_tree(company_id: int, include_inactive: bool = False,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The full chart as a nested tree, with per-account movement counts.

    The UI uses this to render levels 1..N and to show which accounts may still
    receive entries.
    """
    ensure_permission(db, user, company_id, "finance.read")
    query = select(Account).where(Account.company_id == company_id)
    if not include_inactive:
        query = query.where(Account.active.is_(True))
    rows = db.scalars(query.order_by(Account.code)).all()

    counts = dict(
        db.execute(
            select(JournalLine.account_id, func.count(JournalLine.id)).group_by(JournalLine.account_id)
        ).all()
    )

    by_id: dict[int, dict] = {}
    for row in rows:
        by_id[row.id] = {
            "id": row.id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "account_type": row.account_type,
            "statement_group": row.statement_group,
            "level": row.level,
            "is_postable": row.is_postable,
            "is_cash": row.is_cash,
            "active": row.active,
            "parent_id": row.parent_id,
            "movement_lines": int(counts.get(row.id, 0)),
            "children": [],
        }

    roots: list[dict] = []
    for node in by_id.values():
        parent = by_id.get(node["parent_id"]) if node["parent_id"] else None
        (parent["children"] if parent else roots).append(node)

    def depth(nodes: list[dict], current: int = 1) -> int:
        return max([depth(n["children"], current + 1) for n in nodes if n["children"]] + [current])

    return {
        "company_id": company_id,
        "total_accounts": len(rows),
        "max_level": depth(roots) if roots else 0,
        "postable_accounts": sum(1 for r in rows if r.is_postable),
        "tree": sorted(roots, key=lambda n: n["code"]),
    }


@router.post("", status_code=201)
def create_account(data: AccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add an account at any depth under an existing parent."""
    ensure_permission(db, user, data.company_id, "finance.manage")

    if db.scalar(select(Account).where(Account.company_id == data.company_id, Account.code == data.code)):
        raise HTTPException(409, f"Account code already exists: {data.code}")

    parent: Account | None = None
    level = 1
    account_type = (data.account_type or "").upper()
    statement_group = data.statement_group or ""

    if data.parent_code:
        parent = _get(db, data.company_id, data.parent_code)
        level = int(parent.level) + 1
        if level > MAX_DEPTH:
            raise HTTPException(422, f"Maximum depth of {MAX_DEPTH} levels reached")
        # A child always belongs to the same statement side as its parent.
        account_type = parent.account_type
        statement_group = parent.statement_group
        # The child must live inside the parent's numeric range. The parent's
        # significant prefix is its code without the trailing zeros:
        #   600000 -> "6"      so 630000 is valid
        #   613010 -> "61301"  so 613011 is valid
        prefix = data.parent_code.rstrip("0") or data.parent_code[:1]
        if not data.code.startswith(prefix):
            raise HTTPException(
                422,
                {
                    "message_ar": (
                        f"رقم الحساب يجب أن يبدأ بـ{prefix} ليقع داخل نطاق الحساب الأب {data.parent_code}. "
                        f"مثال صحيح: {prefix}{'1'.zfill(max(1, len(data.parent_code) - len(prefix)))}"
                    ),
                    "message_en": (
                        f"The code must start with {prefix} to sit inside parent {data.parent_code}."
                    ),
                },
            )
    else:
        if account_type not in ACCOUNT_TYPES:
            raise HTTPException(422, f"account_type is required for a root account. One of {ACCOUNT_TYPES}")
        if not statement_group:
            statement_group = account_type

    account = Account(
        company_id=data.company_id,
        code=data.code,
        name_ar=data.name_ar,
        name_en=data.name_en,
        account_type=account_type,
        statement_group=statement_group,
        parent_id=parent.id if parent else None,
        level=level,
        is_postable=True,          # a new leaf accepts entries
        is_cash=data.is_cash,
        active=True,
    )
    db.add(account)

    # A parent must stop accepting entries: a total cannot also hold movements.
    demoted = None
    if parent is not None and parent.is_postable:
        if _has_movements(db, parent.id):
            raise HTTPException(
                422,
                {
                    "message_ar": (
                        f"الحساب {parent.code} عليه حركات مرحّلة، فلا يمكن جعله حسابًا رئيسيًا. "
                        "انقل حركاته أولًا أو أنشئ الحساب تحت أب آخر."
                    ),
                    "message_en": (
                        f"Account {parent.code} already carries posted lines, so it cannot become a "
                        "parent. Move its entries first, or choose another parent."
                    ),
                },
            )
        parent.is_postable = False
        demoted = parent.code

    db.flush()
    write_audit(db, action="ACCOUNT_CREATED", entity_type="ACCOUNT", entity_id=account.id,
                user_id=user.id, company_id=data.company_id,
                after={"code": account.code, "level": level, "parent": data.parent_code})
    db.commit()

    return {
        "id": account.id,
        "code": account.code,
        "name_ar": account.name_ar,
        "level": level,
        "account_type": account_type,
        "statement_group": statement_group,
        "is_postable": True,
        "parent_demoted_to_header": demoted,
        "message_ar": (
            f"تم إنشاء الحساب في المستوى {level}."
            + (f" وتحوّل الحساب {demoted} إلى حساب رئيسي لا يقبل الترحيل." if demoted else "")
        ),
        "message_en": (
            f"Account created at level {level}."
            + (f" {demoted} became a header account and no longer accepts entries." if demoted else "")
        ),
    }


@router.patch("/{code}")
def update_account(code: str, data: AccountUpdate,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rename, flag as cash, or retire an account. Type is never changed here."""
    ensure_permission(db, user, data.company_id, "finance.manage")
    account = _get(db, data.company_id, code)
    before = {"name_ar": account.name_ar, "active": account.active}

    if data.name_ar is not None:
        account.name_ar = data.name_ar
    if data.name_en is not None:
        account.name_en = data.name_en
    if data.is_cash is not None:
        account.is_cash = data.is_cash
    if data.active is not None:
        if not data.active:
            children = db.scalar(
                select(func.count(Account.id)).where(
                    Account.parent_id == account.id, Account.active.is_(True)
                )
            ) or 0
            if children:
                raise HTTPException(
                    422,
                    {
                        "message_ar": f"لا يمكن تعطيل {code} لأن تحته {children} حسابًا نشطًا. عطّلها أولًا.",
                        "message_en": f"Cannot deactivate {code}: {children} active child accounts remain.",
                    },
                )
        account.active = data.active

    write_audit(db, action="ACCOUNT_UPDATED", entity_type="ACCOUNT", entity_id=account.id,
                user_id=user.id, company_id=data.company_id, before=before,
                after={"name_ar": account.name_ar, "active": account.active})
    db.commit()
    return {"code": account.code, "name_ar": account.name_ar, "active": account.active,
            "is_postable": account.is_postable, "level": account.level}


@router.delete("/{code}")
def delete_account(code: str, company_id: int,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove an account that was never used. Used accounts are deactivated instead."""
    ensure_permission(db, user, company_id, "finance.manage")
    account = _get(db, company_id, code)

    movements = _has_movements(db, account.id)
    if movements:
        raise HTTPException(
            422,
            {
                "message_ar": f"الحساب {code} عليه {movements} سطر قيد، فلا يُحذف. عطّله بدلًا من ذلك.",
                "message_en": f"{code} carries {movements} journal lines and cannot be deleted. Deactivate it instead.",
            },
        )
    children = db.scalar(select(func.count(Account.id)).where(Account.parent_id == account.id)) or 0
    if children:
        raise HTTPException(422, f"{code} has {children} child accounts. Remove them first.")

    parent_id = account.parent_id
    write_audit(db, action="ACCOUNT_DELETED", entity_type="ACCOUNT", entity_id=account.id,
                user_id=user.id, company_id=company_id, before={"code": code})
    db.delete(account)
    db.flush()

    # If the parent has no children left it can accept entries again.
    restored = None
    if parent_id:
        remaining = db.scalar(select(func.count(Account.id)).where(Account.parent_id == parent_id)) or 0
        if remaining == 0:
            parent = db.get(Account, parent_id)
            if parent is not None:
                parent.is_postable = True
                restored = parent.code
    db.commit()
    return {"deleted": code, "parent_restored_to_postable": restored}
