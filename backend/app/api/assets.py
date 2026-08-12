from __future__ import annotations

import calendar
import csv
import io
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (Account, AssetCategory, AssetDepreciation, AssetLifecycleTransaction, BankAccount, Branch, CostCenter, FixedAsset, User, UserCompanyRole)
from app.core.time import utc_now
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal
from app.services.tax import get_tax_code

router = APIRouter(prefix="/assets", tags=["IAS 16 fixed assets"])


class CategoryIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    useful_life_months: int = Field(ge=1, le=600)
    residual_percent: Decimal = Field(default=0, ge=0, le=100)
    depreciation_convention: str = "FULL_MONTH_BY_15TH"


class AssetIn(BaseModel):
    company_id: int
    name_ar: str
    name_en: str
    category_id: int
    acquisition_date: date
    in_service_date: date
    cost: Decimal = Field(gt=0)
    residual_value: Decimal | None = Field(default=None, ge=0)
    useful_life_months: int | None = Field(default=None, ge=1, le=600)
    bank_account_id: int
    branch_id: int | None = None
    cost_center_id: int | None = None
    custodian_user_id: int | None = None


class DepreciationRunIn(BaseModel):
    company_id: int
    as_of_date: date


class AssetOpeningValueIn(BaseModel):
    company_id: int
    opening_date: date
    cost: Decimal = Field(gt=0)
    residual_value: Decimal = Field(default=0, ge=0)
    accumulated_depreciation: Decimal = Field(default=0, ge=0)
    accumulated_impairment: Decimal = Field(default=0, ge=0)
    offset_account_id: int
    bank_account_id: int | None = None


class LifecycleIn(BaseModel):
    company_id: int
    asset_id: int
    transaction_type: str
    transaction_date: date
    reason: str = Field(min_length=3, max_length=1000)
    reference: str | None = Field(default=None, max_length=150)
    to_branch_id: int | None = None
    to_cost_center_id: int | None = None
    to_custodian_user_id: int | None = None
    disposal_percent: Decimal = Field(default=100, gt=0, le=100)
    proceeds_net: Decimal = Field(default=0, ge=0)
    vat_rate: Decimal = Field(default=0, ge=0, le=100)
    tax_code: str | None = Field(default=None, max_length=30)
    recoverable_amount: Decimal | None = Field(default=None, ge=0)
    fair_value_less_cost_to_sell: Decimal | None = Field(default=None, ge=0)
    bank_account_id: int | None = None


ALLOWED_LIFECYCLE_TYPES = {
    "TRANSFER", "SALE", "DISPOSAL", "WRITE_OFF", "IMPAIRMENT",
    "IMPAIRMENT_REVERSAL", "HELD_FOR_SALE", "HELD_FOR_SALE_REVERSAL",
}


def month_end(value: date) -> date:
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def next_asset_number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(FixedAsset.id)).where(FixedAsset.company_id == company_id)) or 0
    return f"FA-{company_id}-{year}-{count + 1:05d}"


def next_lifecycle_number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(AssetLifecycleTransaction.id)).where(AssetLifecycleTransaction.company_id == company_id)) or 0
    return f"FAT-{company_id}-{year}-{count + 1:06d}"


def serialize_lifecycle(row: AssetLifecycleTransaction) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "asset_id": row.asset_id,
        "asset_number": row.asset.asset_number if row.asset else None,
        "number": row.number, "transaction_type": row.transaction_type,
        "transaction_date": row.transaction_date, "status": row.status,
        "reason": row.reason, "reference": row.reference,
        "from_branch_id": row.from_branch_id, "to_branch_id": row.to_branch_id,
        "from_cost_center_id": row.from_cost_center_id, "to_cost_center_id": row.to_cost_center_id,
        "from_custodian_user_id": row.from_custodian_user_id, "to_custodian_user_id": row.to_custodian_user_id,
        "disposal_percent": row.disposal_percent, "proceeds_net": row.proceeds_net,
        "vat_rate": row.vat_rate, "vat_amount": row.vat_amount, "proceeds_gross": row.proceeds_gross,
        "tax_code": row.tax_code.code if row.tax_code else None,
        "disposed_cost": row.disposed_cost,
        "disposed_accumulated_depreciation": row.disposed_accumulated_depreciation,
        "disposed_accumulated_impairment": row.disposed_accumulated_impairment,
        "disposed_net_book_value": row.disposed_net_book_value,
        "gain_amount": row.gain_amount, "loss_amount": row.loss_amount,
        "recoverable_amount": row.recoverable_amount,
        "fair_value_less_cost_to_sell": row.fair_value_less_cost_to_sell,
        "impairment_amount": row.impairment_amount, "reversal_amount": row.reversal_amount,
        "journal_id": row.journal_id, "created_by": row.created_by,
        "submitted_by": row.submitted_by, "approved_by": row.approved_by,
        "created_at": row.created_at, "submitted_at": row.submitted_at, "approved_at": row.approved_at,
    }


@router.post("/categories", status_code=201)
def create_category(data: CategoryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "assets.manage")
    if db.scalar(select(AssetCategory).where(AssetCategory.company_id == data.company_id, AssetCategory.code == data.code)):
        raise HTTPException(409, "Asset category code already exists")
    asset_account = get_account(db, data.company_id, "151010")
    accumulated = get_account(db, data.company_id, "153010")
    expense = get_account(db, data.company_id, "617010")
    row = AssetCategory(
        company_id=data.company_id,
        code=data.code,
        name_ar=data.name_ar,
        name_en=data.name_en,
        asset_account_id=asset_account.id,
        accumulated_depreciation_account_id=accumulated.id,
        depreciation_expense_account_id=expense.id,
        useful_life_months=data.useful_life_months,
        residual_percent=data.residual_percent,
        depreciation_convention=data.depreciation_convention,
        active=True,
    )
    db.add(row); db.flush()
    write_audit(db, action="ASSET_CATEGORY_CREATED", entity_type="ASSET_CATEGORY", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code})
    db.commit()
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "useful_life_months": row.useful_life_months, "depreciation_convention": row.depreciation_convention}


@router.get("/categories")
def list_categories(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "assets.read")
    rows = db.scalars(select(AssetCategory).where(AssetCategory.company_id == company_id, AssetCategory.active.is_(True)).order_by(AssetCategory.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "useful_life_months": r.useful_life_months, "residual_percent": r.residual_percent, "depreciation_convention": r.depreciation_convention} for r in rows]


@router.post("", status_code=201)
def create_asset(data: AssetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "assets.manage")
    category = db.scalar(select(AssetCategory).where(AssetCategory.id == data.category_id, AssetCategory.company_id == data.company_id, AssetCategory.active.is_(True)))
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not category: raise HTTPException(404, "Asset category not found")
    if not bank: raise HTTPException(404, "Bank account not found")
    cost = money(data.cost)
    residual = money(data.residual_value if data.residual_value is not None else cost * category.residual_percent / Decimal("100"))
    if residual >= cost: raise HTTPException(422, "Residual value must be lower than cost")
    useful_life = data.useful_life_months or category.useful_life_months
    number = next_asset_number(db, data.company_id, data.acquisition_date.year)
    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=data.acquisition_date,
        reference=number, description=f"Asset acquisition {number}",
        lines=[
            {"account_id": category.asset_account_id, "debit": cost, "credit": 0, "branch_id": data.branch_id, "cost_center_id": data.cost_center_id},
            {"account_id": bank.gl_account_id, "debit": 0, "credit": cost, "branch_id": data.branch_id, "cost_center_id": data.cost_center_id},
        ], cash_flow_activity="INVESTING", cash_flow_kind="PURCHASE_OF_PPE",
    )
    row = FixedAsset(
        company_id=data.company_id, asset_number=number, name_ar=data.name_ar, name_en=data.name_en,
        category_id=category.id, acquisition_date=data.acquisition_date, in_service_date=data.in_service_date,
        cost=cost, residual_value=residual, useful_life_months=useful_life, depreciation_method="STRAIGHT_LINE",
        accumulated_depreciation=Decimal("0"), accumulated_impairment=Decimal("0"), net_book_value=cost, status="ACTIVE",
        acquisition_journal_id=journal.id, bank_account_id=bank.id, branch_id=data.branch_id,
        cost_center_id=data.cost_center_id, custodian_user_id=data.custodian_user_id, created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="FIXED_ASSET_CAPITALIZED", entity_type="FIXED_ASSET", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"asset_number": number, "cost": str(cost), "journal": journal.number})
    db.commit()
    return {"id": row.id, "asset_number": row.asset_number, "cost": row.cost, "residual_value": row.residual_value, "net_book_value": row.net_book_value, "journal": journal.number}


@router.post("/{asset_id}/initialize-opening-value")
def initialize_asset_opening_value(
    asset_id: int,
    data: AssetOpeningValueIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Value a preserved asset card after an authorized UAT value reset."""
    ensure_permission(db, user, data.company_id, "assets.manage")
    asset = db.scalar(
        select(FixedAsset)
        .where(FixedAsset.id == asset_id, FixedAsset.company_id == data.company_id)
        .options(selectinload(FixedAsset.category))
    )
    if not asset:
        raise HTTPException(404, "Fixed asset not found")
    if asset.status != "DRAFT_UNVALUED" or asset.acquisition_journal_id is not None:
        raise HTTPException(409, "Only an unvalued asset card can receive an opening value")

    cost = money(data.cost)
    residual = money(data.residual_value)
    accumulated_depreciation = money(data.accumulated_depreciation)
    accumulated_impairment = money(data.accumulated_impairment)
    if residual >= cost:
        raise HTTPException(422, "Residual value must be lower than cost")
    if accumulated_depreciation + accumulated_impairment > cost:
        raise HTTPException(422, "Accumulated depreciation and impairment cannot exceed cost")
    net_book_value = money(cost - accumulated_depreciation - accumulated_impairment)

    offset = db.scalar(
        select(Account).where(
            Account.id == data.offset_account_id,
            Account.company_id == data.company_id,
            Account.is_postable.is_(True),
            Account.active.is_(True),
            Account.account_type == "EQUITY",
        )
    )
    if not offset:
        raise HTTPException(404, "Opening-balance offset must be an active postable equity account")
    bank = None
    if data.bank_account_id is not None:
        bank = db.scalar(
            select(BankAccount).where(
                BankAccount.id == data.bank_account_id,
                BankAccount.company_id == data.company_id,
                BankAccount.active.is_(True),
            )
        )
        if not bank:
            raise HTTPException(404, "Bank account not found")

    lines = [
        {
            "account_id": asset.category.asset_account_id,
            "debit": cost,
            "credit": 0,
            "branch_id": asset.branch_id,
            "cost_center_id": asset.cost_center_id,
        }
    ]
    if accumulated_depreciation:
        lines.append(
            {
                "account_id": asset.category.accumulated_depreciation_account_id,
                "debit": 0,
                "credit": accumulated_depreciation,
                "branch_id": asset.branch_id,
                "cost_center_id": asset.cost_center_id,
            }
        )
    if accumulated_impairment:
        impairment_account = get_account(db, data.company_id, "154030")
        lines.append(
            {
                "account_id": impairment_account.id,
                "debit": 0,
                "credit": accumulated_impairment,
                "branch_id": asset.branch_id,
                "cost_center_id": asset.cost_center_id,
            }
        )
    if net_book_value:
        lines.append(
            {
                "account_id": offset.id,
                "debit": 0,
                "credit": net_book_value,
                "branch_id": asset.branch_id,
                "cost_center_id": asset.cost_center_id,
            }
        )

    journal = create_posted_journal(
        db,
        company_id=data.company_id,
        user_id=user.id,
        posting_date=data.opening_date,
        reference=f"OPEN-{asset.asset_number}",
        description=f"Opening value for preserved asset {asset.asset_number}",
        lines=lines,
        cash_flow_kind="OPENING_BALANCE",
    )
    asset.cost = cost
    asset.residual_value = residual
    asset.accumulated_depreciation = accumulated_depreciation
    asset.accumulated_impairment = accumulated_impairment
    asset.net_book_value = net_book_value
    asset.status = "ACTIVE"
    asset.acquisition_journal_id = journal.id
    asset.bank_account_id = bank.id if bank else None
    write_audit(
        db,
        action="FIXED_ASSET_OPENING_VALUE_INITIALIZED",
        entity_type="FIXED_ASSET",
        entity_id=asset.id,
        user_id=user.id,
        company_id=data.company_id,
        after={
            "asset_number": asset.asset_number,
            "cost": str(cost),
            "accumulated_depreciation": str(accumulated_depreciation),
            "accumulated_impairment": str(accumulated_impairment),
            "net_book_value": str(net_book_value),
            "journal": journal.number,
        },
    )
    db.commit()
    return {
        "id": asset.id,
        "asset_number": asset.asset_number,
        "status": asset.status,
        "cost": asset.cost,
        "accumulated_depreciation": asset.accumulated_depreciation,
        "accumulated_impairment": asset.accumulated_impairment,
        "net_book_value": asset.net_book_value,
        "journal": journal.number,
    }


@router.post("/depreciation/run")
def run_depreciation(data: DepreciationRunIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "assets.depreciate")
    period_date = month_end(data.as_of_date)
    assets = db.scalars(select(FixedAsset).where(FixedAsset.company_id == data.company_id, FixedAsset.status == "ACTIVE").options(selectinload(FixedAsset.category), selectinload(FixedAsset.depreciation_runs))).all()
    posted = []
    for asset in assets:
        pending = db.scalar(select(AssetLifecycleTransaction.id).where(
            AssetLifecycleTransaction.asset_id == asset.id,
            AssetLifecycleTransaction.status == "SUBMITTED",
        ))
        if pending:
            continue
        if asset.in_service_date > period_date or asset.net_book_value <= asset.residual_value:
            continue
        if any(run.period_date == period_date for run in asset.depreciation_runs):
            continue
        monthly = money((asset.cost - asset.residual_value) / Decimal(asset.useful_life_months))
        convention = asset.category.depreciation_convention
        first_period = month_end(asset.in_service_date)
        if period_date == first_period and convention in {"HALF_MONTH_15_DAY", "FULL_MONTH_BY_15TH"} and asset.in_service_date.day > 15:
            continue
        depreciation = min(monthly, money(asset.net_book_value - asset.residual_value))
        if depreciation <= 0:
            continue
        journal = create_posted_journal(
            db, company_id=data.company_id, user_id=user.id, posting_date=period_date,
            reference=asset.asset_number, description=f"Monthly depreciation {asset.asset_number}",
            lines=[
                {"account_id": asset.category.depreciation_expense_account_id, "debit": depreciation, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
                {"account_id": asset.category.accumulated_depreciation_account_id, "debit": 0, "credit": depreciation, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
            ],
        )
        opening = money(asset.net_book_value)
        closing = money(opening - depreciation)
        db.add(AssetDepreciation(asset_id=asset.id, period_date=period_date, opening_nbv=opening, depreciation=depreciation, closing_nbv=closing, journal_id=journal.id))
        asset.accumulated_depreciation = money(asset.accumulated_depreciation + depreciation)
        asset.net_book_value = closing
        posted.append({"asset_number": asset.asset_number, "depreciation": depreciation, "closing_nbv": closing, "journal": journal.number})
    write_audit(db, action="ASSET_DEPRECIATION_RUN", entity_type="FIXED_ASSET", entity_id="BATCH", user_id=user.id, company_id=data.company_id, after={"period_date": str(period_date), "posted_count": len(posted), "amount": str(sum((x["depreciation"] for x in posted), Decimal("0")))})
    db.commit()
    return {"company_id": data.company_id, "period_date": period_date, "posted_count": len(posted), "depreciation_amount": sum((x["depreciation"] for x in posted), Decimal("0")), "assets": posted}


@router.get("")
def list_assets(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "assets.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, FixedAsset)
    query = select(FixedAsset).where(FixedAsset.company_id == company_id)
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.options(selectinload(FixedAsset.category), selectinload(FixedAsset.depreciation_runs)).order_by(FixedAsset.id.desc())).all()
    return [{"id": r.id, "asset_number": r.asset_number, "name_ar": r.name_ar, "name_en": r.name_en, "category": r.category.code, "acquisition_date": r.acquisition_date, "in_service_date": r.in_service_date, "cost": r.cost, "accumulated_depreciation": r.accumulated_depreciation, "accumulated_impairment": r.accumulated_impairment, "net_book_value": r.net_book_value, "status": r.status, "branch_id": r.branch_id, "cost_center_id": r.cost_center_id, "custodian_user_id": r.custodian_user_id, "held_for_sale_date": r.held_for_sale_date, "disposal_date": r.disposal_date, "depreciation_runs": len(r.depreciation_runs), "lifecycle_transactions": len(r.lifecycle_transactions)} for r in rows]


@router.get("/summary")
def asset_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "assets.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, FixedAsset)
    query = select(FixedAsset).where(FixedAsset.company_id == company_id)
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query).all()
    active = [r for r in rows if r.status in {"ACTIVE", "HELD_FOR_SALE"}]
    return {
        "assets": len(rows), "active_assets": sum(1 for r in rows if r.status == "ACTIVE"),
        "held_for_sale_assets": sum(1 for r in rows if r.status == "HELD_FOR_SALE"),
        "disposed_assets": sum(1 for r in rows if r.status in {"SOLD", "DISPOSED", "WRITTEN_OFF"}),
        "gross_cost": money(sum((r.cost for r in active), Decimal("0"))),
        "accumulated_depreciation": money(sum((r.accumulated_depreciation for r in active), Decimal("0"))),
        "accumulated_impairment": money(sum((r.accumulated_impairment for r in active), Decimal("0"))),
        "net_book_value": money(sum((r.net_book_value for r in active), Decimal("0"))),
    }


@router.post("/lifecycle", status_code=201)
def create_lifecycle_transaction(data: LifecycleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "assets.manage")
    tx_type = data.transaction_type.strip().upper()
    if tx_type not in ALLOWED_LIFECYCLE_TYPES:
        raise HTTPException(422, "Unsupported asset lifecycle transaction type")
    asset = db.scalar(select(FixedAsset).where(FixedAsset.id == data.asset_id, FixedAsset.company_id == data.company_id).options(selectinload(FixedAsset.category)))
    if not asset:
        raise HTTPException(404, "Fixed asset not found")
    if data.transaction_date < asset.acquisition_date:
        raise HTTPException(422, "Transaction date cannot precede acquisition date")
    if db.scalar(select(AssetLifecycleTransaction.id).where(
        AssetLifecycleTransaction.asset_id == asset.id,
        AssetLifecycleTransaction.status.in_(["DRAFT", "SUBMITTED"]),
    )):
        raise HTTPException(409, "Asset has another pending lifecycle transaction")

    target_branch_id = data.to_branch_id if data.to_branch_id is not None else asset.branch_id
    target_cost_center_id = data.to_cost_center_id if data.to_cost_center_id is not None else asset.cost_center_id
    target_custodian_user_id = data.to_custodian_user_id if data.to_custodian_user_id is not None else asset.custodian_user_id

    if tx_type == "TRANSFER":
        if asset.status != "ACTIVE":
            raise HTTPException(409, "Only active assets can be transferred")
        if target_branch_id == asset.branch_id and target_cost_center_id == asset.cost_center_id and target_custodian_user_id == asset.custodian_user_id:
            raise HTTPException(422, "Transfer must change branch, cost center or custodian")
        if target_branch_id is not None and not db.scalar(select(Branch.id).where(Branch.id == target_branch_id, Branch.company_id == data.company_id, Branch.active.is_(True))):
            raise HTTPException(404, "Destination branch not found or inactive")
        if target_cost_center_id is not None and not db.scalar(select(CostCenter.id).where(CostCenter.id == target_cost_center_id, CostCenter.company_id == data.company_id, CostCenter.active.is_(True))):
            raise HTTPException(404, "Destination cost center not found or inactive")
        if target_custodian_user_id is not None:
            valid_custodian = db.scalar(
                select(UserCompanyRole.id)
                .join(User, User.id == UserCompanyRole.user_id)
                .where(
                    UserCompanyRole.user_id == target_custodian_user_id,
                    UserCompanyRole.company_id == data.company_id,
                    User.active.is_(True),
                )
            )
            if not valid_custodian:
                raise HTTPException(404, "Destination custodian is not an active user in this company")
    elif tx_type in {"SALE", "DISPOSAL", "WRITE_OFF"}:
        if asset.status not in {"ACTIVE", "HELD_FOR_SALE"}:
            raise HTTPException(409, "Asset is not available for disposal")
        if asset.status == "HELD_FOR_SALE" and data.disposal_percent != Decimal("100"):
            raise HTTPException(422, "Held-for-sale assets can only be disposed in full")
        if tx_type == "SALE" and (data.proceeds_net <= 0 or not data.bank_account_id):
            raise HTTPException(422, "Asset sale requires positive proceeds and a bank account")
        if tx_type != "SALE" and data.proceeds_net != 0:
            raise HTTPException(422, "Only SALE transactions may contain proceeds")
    elif tx_type == "IMPAIRMENT":
        if asset.status != "ACTIVE" or data.recoverable_amount is None:
            raise HTTPException(422, "Active asset and recoverable amount are required")
        if money(data.recoverable_amount) >= money(asset.net_book_value):
            raise HTTPException(422, "Recoverable amount must be below net book value")
    elif tx_type == "IMPAIRMENT_REVERSAL":
        if asset.status != "ACTIVE" or data.recoverable_amount is None:
            raise HTTPException(422, "Active asset and recoverable amount are required")
        if money(asset.accumulated_impairment) <= 0:
            raise HTTPException(409, "Asset has no impairment available for reversal")
        if money(data.recoverable_amount) <= money(asset.net_book_value):
            raise HTTPException(422, "Recoverable amount must exceed net book value")
    elif tx_type == "HELD_FOR_SALE":
        if asset.status != "ACTIVE" or data.fair_value_less_cost_to_sell is None:
            raise HTTPException(422, "Active asset and fair value less cost to sell are required")
    elif tx_type == "HELD_FOR_SALE_REVERSAL":
        if asset.status != "HELD_FOR_SALE":
            raise HTTPException(409, "Asset is not classified as held for sale")

    if data.bank_account_id:
        bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
        if not bank:
            raise HTTPException(404, "Bank account not found")

    pct = Decimal(data.disposal_percent) / Decimal("100")
    disposed_cost = money(asset.cost * pct) if tx_type in {"SALE", "DISPOSAL", "WRITE_OFF"} and asset.status != "HELD_FOR_SALE" else Decimal("0")
    disposed_dep = money(asset.accumulated_depreciation * pct) if disposed_cost else Decimal("0")
    disposed_imp = money(asset.accumulated_impairment * pct) if disposed_cost else Decimal("0")
    disposed_nbv = money(asset.net_book_value * pct) if tx_type in {"SALE", "DISPOSAL", "WRITE_OFF"} else Decimal("0")
    tax_code = None
    effective_vat_rate = Decimal("0")
    if tx_type == "SALE":
        tax_code = get_tax_code(db, data.company_id, code=data.tax_code, direction="SALES", vat_rate=data.vat_rate, user_id=user.id)
        effective_vat_rate = Decimal(tax_code.rate)
    vat_amount = money(data.proceeds_net * effective_vat_rate / Decimal("100")) if tx_type == "SALE" else Decimal("0")
    proceeds_gross = money(data.proceeds_net + vat_amount)
    gain = money(max(data.proceeds_net - disposed_nbv, Decimal("0"))) if tx_type == "SALE" else Decimal("0")
    loss = money(max(disposed_nbv - data.proceeds_net, Decimal("0"))) if tx_type in {"SALE", "DISPOSAL", "WRITE_OFF"} else Decimal("0")
    impairment = money(asset.net_book_value - data.recoverable_amount) if tx_type == "IMPAIRMENT" and data.recoverable_amount is not None else Decimal("0")
    reversal = Decimal("0")
    if tx_type == "IMPAIRMENT_REVERSAL" and data.recoverable_amount is not None:
        ceiling_without_impairment = money(asset.cost - asset.accumulated_depreciation)
        permitted_nbv = min(money(data.recoverable_amount), ceiling_without_impairment)
        reversal = money(min(permitted_nbv - asset.net_book_value, asset.accumulated_impairment))
        if reversal <= 0:
            raise HTTPException(422, "No impairment reversal is permitted")

    number = next_lifecycle_number(db, data.company_id, data.transaction_date.year)
    row = AssetLifecycleTransaction(
        company_id=data.company_id, asset_id=asset.id, number=number, transaction_type=tx_type,
        transaction_date=data.transaction_date, status="DRAFT", reason=data.reason, reference=data.reference,
        from_branch_id=asset.branch_id, to_branch_id=target_branch_id,
        from_cost_center_id=asset.cost_center_id, to_cost_center_id=target_cost_center_id,
        from_custodian_user_id=asset.custodian_user_id, to_custodian_user_id=target_custodian_user_id,
        disposal_percent=data.disposal_percent, proceeds_net=money(data.proceeds_net), vat_rate=effective_vat_rate,
        tax_code_id=tax_code.id if tax_code else None,
        vat_amount=vat_amount, proceeds_gross=proceeds_gross, disposed_cost=disposed_cost,
        disposed_accumulated_depreciation=disposed_dep, disposed_accumulated_impairment=disposed_imp,
        disposed_net_book_value=disposed_nbv, gain_amount=gain, loss_amount=loss,
        recoverable_amount=data.recoverable_amount, fair_value_less_cost_to_sell=data.fair_value_less_cost_to_sell,
        impairment_amount=impairment, reversal_amount=reversal, bank_account_id=data.bank_account_id,
        created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="ASSET_LIFECYCLE_CREATED", entity_type="ASSET_LIFECYCLE", entity_id=row.id,
                user_id=user.id, company_id=data.company_id,
                after={"number": number, "asset": asset.asset_number, "type": tx_type, "status": row.status})
    db.commit(); db.refresh(row)
    return serialize_lifecycle(row)


@router.post("/lifecycle/{transaction_id}/submit")
def submit_lifecycle_transaction(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(AssetLifecycleTransaction).where(AssetLifecycleTransaction.id == transaction_id).options(selectinload(AssetLifecycleTransaction.asset)))
    if not row:
        raise HTTPException(404, "Asset lifecycle transaction not found")
    ensure_permission(db, user, row.company_id, "assets.manage")
    if row.status != "DRAFT":
        raise HTTPException(409, "Only draft transactions can be submitted")
    row.status = "SUBMITTED"; row.submitted_by = user.id; row.submitted_at = utc_now()
    write_audit(db, action="ASSET_LIFECYCLE_SUBMITTED", entity_type="ASSET_LIFECYCLE", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"number": row.number, "status": row.status})
    db.commit(); db.refresh(row)
    return serialize_lifecycle(row)


def _post_transfer(db: Session, row: AssetLifecycleTransaction, asset: FixedAsset, user: User):
    lines = []
    if row.to_branch_id != asset.branch_id or row.to_cost_center_id != asset.cost_center_id:
        lines.extend([
            {"account_id": asset.category.asset_account_id, "debit": asset.cost, "credit": 0, "branch_id": row.to_branch_id, "cost_center_id": row.to_cost_center_id},
            {"account_id": asset.category.asset_account_id, "debit": 0, "credit": asset.cost, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
        ])
        if money(asset.accumulated_depreciation) > 0:
            lines.extend([
                {"account_id": asset.category.accumulated_depreciation_account_id, "debit": asset.accumulated_depreciation, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
                {"account_id": asset.category.accumulated_depreciation_account_id, "debit": 0, "credit": asset.accumulated_depreciation, "branch_id": row.to_branch_id, "cost_center_id": row.to_cost_center_id},
            ])
        if money(asset.accumulated_impairment) > 0:
            impairment_account = get_account(db, row.company_id, "154030")
            lines.extend([
                {"account_id": impairment_account.id, "debit": asset.accumulated_impairment, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
                {"account_id": impairment_account.id, "debit": 0, "credit": asset.accumulated_impairment, "branch_id": row.to_branch_id, "cost_center_id": row.to_cost_center_id},
            ])
    journal = None
    if lines:
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.transaction_date,
            reference=row.number, description=f"Asset transfer {asset.asset_number}", lines=lines)
    asset.branch_id = row.to_branch_id
    asset.cost_center_id = row.to_cost_center_id
    asset.custodian_user_id = row.to_custodian_user_id
    return journal


def _post_impairment(db: Session, row: AssetLifecycleTransaction, asset: FixedAsset, user: User):
    expense = get_account(db, row.company_id, "620010")
    accumulated = get_account(db, row.company_id, "154030")
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.transaction_date,
        reference=row.number, description=f"Asset impairment {asset.asset_number}", lines=[
            {"account_id": expense.id, "debit": row.impairment_amount, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
            {"account_id": accumulated.id, "debit": 0, "credit": row.impairment_amount, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
        ])
    asset.accumulated_impairment = money(asset.accumulated_impairment + row.impairment_amount)
    asset.net_book_value = money(asset.net_book_value - row.impairment_amount)
    return journal


def _post_impairment_reversal(db: Session, row: AssetLifecycleTransaction, asset: FixedAsset, user: User):
    accumulated = get_account(db, row.company_id, "154030")
    income = get_account(db, row.company_id, "426010")
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.transaction_date,
        reference=row.number, description=f"Asset impairment reversal {asset.asset_number}", lines=[
            {"account_id": accumulated.id, "debit": row.reversal_amount, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
            {"account_id": income.id, "debit": 0, "credit": row.reversal_amount, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
        ])
    asset.accumulated_impairment = money(asset.accumulated_impairment - row.reversal_amount)
    asset.net_book_value = money(asset.net_book_value + row.reversal_amount)
    return journal


def _post_held_for_sale(db: Session, row: AssetLifecycleTransaction, asset: FixedAsset, user: User):
    held = get_account(db, row.company_id, "119020")
    impairment_account = get_account(db, row.company_id, "154030")
    impairment_expense = get_account(db, row.company_id, "620010")
    target = money(min(asset.net_book_value, row.fair_value_less_cost_to_sell or asset.net_book_value))
    write_down = money(asset.net_book_value - target)
    row.impairment_amount = write_down
    lines = []
    if write_down > 0:
        lines.append({"account_id": impairment_expense.id, "debit": write_down, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    lines.append({"account_id": held.id, "debit": target, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    if money(asset.accumulated_depreciation) > 0:
        lines.append({"account_id": asset.category.accumulated_depreciation_account_id, "debit": asset.accumulated_depreciation, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    if money(asset.accumulated_impairment) > 0:
        lines.append({"account_id": impairment_account.id, "debit": asset.accumulated_impairment, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    lines.append({"account_id": asset.category.asset_account_id, "debit": 0, "credit": asset.cost, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.transaction_date,
        reference=row.number, description=f"Asset held for sale {asset.asset_number}", lines=lines)
    asset.accumulated_impairment = money(asset.accumulated_impairment + write_down)
    asset.net_book_value = target
    asset.status = "HELD_FOR_SALE"; asset.held_for_sale_date = row.transaction_date
    return journal


def _post_held_for_sale_reversal(db: Session, row: AssetLifecycleTransaction, asset: FixedAsset, user: User):
    held = get_account(db, row.company_id, "119020")
    impairment_account = get_account(db, row.company_id, "154030")
    lines = [
        {"account_id": asset.category.asset_account_id, "debit": asset.cost, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
        {"account_id": held.id, "debit": 0, "credit": asset.net_book_value, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id},
    ]
    if money(asset.accumulated_depreciation) > 0:
        lines.append({"account_id": asset.category.accumulated_depreciation_account_id, "debit": 0, "credit": asset.accumulated_depreciation, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    if money(asset.accumulated_impairment) > 0:
        lines.append({"account_id": impairment_account.id, "debit": 0, "credit": asset.accumulated_impairment, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.transaction_date,
        reference=row.number, description=f"Reverse held-for-sale classification {asset.asset_number}", lines=lines)
    asset.status = "ACTIVE"; asset.held_for_sale_date = None
    return journal


def _post_disposal(db: Session, row: AssetLifecycleTransaction, asset: FixedAsset, user: User):
    gain_account = get_account(db, row.company_id, "425010")
    loss_account = get_account(db, row.company_id, "626010")
    vat_account = get_account(db, row.company_id, "212010")
    impairment_account = get_account(db, row.company_id, "154030")
    bank = db.get(BankAccount, row.bank_account_id) if row.bank_account_id else None
    lines = []
    if row.proceeds_gross > 0:
        lines.append({"account_id": bank.gl_account_id, "debit": row.proceeds_gross, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    if asset.status == "HELD_FOR_SALE":
        held = get_account(db, row.company_id, "119020")
        lines.append({"account_id": held.id, "debit": 0, "credit": row.disposed_net_book_value, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    else:
        if row.disposed_accumulated_depreciation > 0:
            lines.append({"account_id": asset.category.accumulated_depreciation_account_id, "debit": row.disposed_accumulated_depreciation, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
        if row.disposed_accumulated_impairment > 0:
            lines.append({"account_id": impairment_account.id, "debit": row.disposed_accumulated_impairment, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
        lines.append({"account_id": asset.category.asset_account_id, "debit": 0, "credit": row.disposed_cost, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    if row.loss_amount > 0:
        lines.append({"account_id": loss_account.id, "debit": row.loss_amount, "credit": 0, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    if row.vat_amount > 0:
        lines.append({"account_id": vat_account.id, "debit": 0, "credit": row.vat_amount, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    if row.gain_amount > 0:
        lines.append({"account_id": gain_account.id, "debit": 0, "credit": row.gain_amount, "branch_id": asset.branch_id, "cost_center_id": asset.cost_center_id})
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.transaction_date,
        reference=row.number, description=f"Asset {row.transaction_type.lower()} {asset.asset_number}", lines=lines,
        cash_flow_activity="INVESTING" if row.proceeds_gross > 0 else None,
        cash_flow_kind="PROCEEDS_FROM_SALE_OF_PPE" if row.proceeds_gross > 0 else None)
    full = money(row.disposal_percent) == Decimal("100.00")
    if full:
        asset.net_book_value = Decimal("0")
        asset.status = "SOLD" if row.transaction_type == "SALE" else ("WRITTEN_OFF" if row.transaction_type == "WRITE_OFF" else "DISPOSED")
        asset.disposal_date = row.transaction_date; asset.disposal_reference = row.reference or row.number
    else:
        asset.cost = money(asset.cost - row.disposed_cost)
        asset.accumulated_depreciation = money(asset.accumulated_depreciation - row.disposed_accumulated_depreciation)
        asset.accumulated_impairment = money(asset.accumulated_impairment - row.disposed_accumulated_impairment)
        asset.residual_value = money(asset.residual_value * (Decimal("1") - Decimal(row.disposal_percent) / Decimal("100")))
        asset.net_book_value = money(asset.net_book_value - row.disposed_net_book_value)
    return journal


@router.post("/lifecycle/{transaction_id}/approve-post")
def approve_post_lifecycle_transaction(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(AssetLifecycleTransaction).where(AssetLifecycleTransaction.id == transaction_id).options(selectinload(AssetLifecycleTransaction.asset).selectinload(FixedAsset.category)))
    if not row:
        raise HTTPException(404, "Asset lifecycle transaction not found")
    ensure_permission(db, user, row.company_id, "assets.manage")
    if row.status != "SUBMITTED":
        raise HTTPException(409, "Only submitted transactions can be approved")
    if user.id in {row.created_by, row.submitted_by}:
        raise HTTPException(409, "Maker-checker violation: preparer cannot approve")
    asset = row.asset
    if row.transaction_type == "TRANSFER":
        journal = _post_transfer(db, row, asset, user)
    elif row.transaction_type == "IMPAIRMENT":
        journal = _post_impairment(db, row, asset, user)
    elif row.transaction_type == "IMPAIRMENT_REVERSAL":
        journal = _post_impairment_reversal(db, row, asset, user)
    elif row.transaction_type == "HELD_FOR_SALE":
        journal = _post_held_for_sale(db, row, asset, user)
    elif row.transaction_type == "HELD_FOR_SALE_REVERSAL":
        journal = _post_held_for_sale_reversal(db, row, asset, user)
    else:
        journal = _post_disposal(db, row, asset, user)
    row.journal_id = journal.id if journal else None
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="ASSET_LIFECYCLE_APPROVED_POSTED", entity_type="ASSET_LIFECYCLE", entity_id=row.id,
                user_id=user.id, company_id=row.company_id,
                after={"number": row.number, "type": row.transaction_type, "status": row.status, "journal_id": row.journal_id, "asset_status": asset.status})
    db.commit(); db.refresh(row)
    return serialize_lifecycle(row)


@router.get("/lifecycle")
def list_lifecycle_transactions(company_id: int, asset_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "assets.read")
    stmt = select(AssetLifecycleTransaction).where(AssetLifecycleTransaction.company_id == company_id).options(selectinload(AssetLifecycleTransaction.asset)).order_by(AssetLifecycleTransaction.id.desc())
    if asset_id:
        stmt = stmt.where(AssetLifecycleTransaction.asset_id == asset_id)
    return [serialize_lifecycle(r) for r in db.scalars(stmt).all()]


@router.get("/lifecycle/export.csv")
def export_lifecycle_transactions(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "assets.read")
    rows = db.scalars(select(AssetLifecycleTransaction).where(AssetLifecycleTransaction.company_id == company_id).options(selectinload(AssetLifecycleTransaction.asset)).order_by(AssetLifecycleTransaction.transaction_date, AssetLifecycleTransaction.id).where(branch_scope_condition(db, user, company_id, AssetLifecycleTransaction) if branch_scope_condition(db, user, company_id, AssetLifecycleTransaction) is not None else sa_true())).all()
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Number", "Asset", "Type", "Date", "Status", "Reason", "Reference", "Disposal percent", "Net proceeds", "VAT", "NBV disposed", "Gain", "Loss", "Impairment", "Reversal", "Journal ID"])
    for r in rows:
        writer.writerow([r.number, r.asset.asset_number, r.transaction_type, r.transaction_date, r.status, r.reason, r.reference or "", r.disposal_percent, r.proceeds_net, r.vat_amount, r.disposed_net_book_value, r.gain_amount, r.loss_amount, r.impairment_amount, r.reversal_amount, r.journal_id or ""])
    content = "\ufeff" + output.getvalue()
    return StreamingResponse(iter([content.encode("utf-8")]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=asset_lifecycle.csv"})
