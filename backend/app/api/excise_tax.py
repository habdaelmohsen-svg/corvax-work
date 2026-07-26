from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BankAccount, ExciseMovement, ExciseProduct, ExciseTaxCategory, ExciseTaxReturn,
    ExciseTaxReturnLine, ExciseWarehouseProfile, Item, JournalLine, User, Warehouse,
)
from app.services.audit import write_audit
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/excise-tax", tags=["Saudi excise tax, tax warehouses and returns"])
MONEY = Decimal("0.01")
QTY = Decimal("0.0001")
RATE = Decimal("0.0001")

DEFAULT_CATEGORIES = [
    ("SOFT_DRINK", "المشروبات الغازية", "Soft drinks", "50", "GCC excise category"),
    ("SWEETENED_BEVERAGE", "المشروبات المحلاة", "Sweetened beverages", "50", "GCC excise category"),
    ("ENERGY_DRINK", "مشروبات الطاقة", "Energy drinks", "100", "GCC excise category"),
    ("TOBACCO", "التبغ ومشتقاته", "Tobacco and derivatives", "100", "Chapter 24 / GCC tariff"),
    ("E_SMOKING_DEVICE", "أجهزة وأدوات التدخين الإلكتروني", "Electronic smoking devices and tools", "100", "GCC tariff schedule"),
    ("E_SMOKING_LIQUID", "سوائل التدخين الإلكتروني", "Electronic smoking liquids", "100", "GCC tariff schedule"),
]
INBOUND_EVENTS = {"PRODUCTION", "IMPORT_RECEIPT", "RETURN_TO_SUSPENSION"}
OUTBOUND_EVENTS = {"RELEASE_CONSUMPTION", "SELF_CONSUMPTION", "EXPORT", "AUTHORIZED_DESTRUCTION", "UNEXPLAINED_LOSS"}
NON_TAXABLE_EVENTS = {"PRODUCTION", "TRANSFER_SUSPENDED", "EXPORT", "AUTHORIZED_DESTRUCTION", "RETURN_TO_SUSPENSION"}
TAXABLE_EVENTS = {"RELEASE_CONSUMPTION", "SELF_CONSUMPTION", "UNEXPLAINED_LOSS"}
ALL_EVENTS = INBOUND_EVENTS | OUTBOUND_EVENTS | {"TRANSFER_SUSPENDED"}
SETTLEMENTS = {"SUSPENDED", "PAYABLE", "CUSTOMS_PAID", "EXEMPT"}


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def qty(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY, rounding=ROUND_HALF_UP)


def rate(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(RATE, rounding=ROUND_HALF_UP)


def account(db: Session, company_id: int, code: str) -> Account:
    row = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code, Account.active.is_(True)))
    if not row or not row.is_postable:
        raise HTTPException(422, f"Account is missing or non-postable: {code}")
    return row


def _number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{int(count)+1:06d}"


def _maker_checker(creator: int | None, user_id: int):
    if creator == user_id:
        raise HTTPException(409, "Maker-checker control: creator cannot approve the same document")


def _csv(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
    buf = io.StringIO(); writer = csv.writer(buf); writer.writerow(headers); writer.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})




def ensure_excise_accounts(db: Session, company_id: int):
    liability = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == "218020"))
    if not liability:
        parent = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == "210000"))
        liability = Account(company_id=company_id, code="218020", name_ar="ضريبة انتقائية مستحقة", name_en="Excise Tax Payable", account_type="LIABILITY", statement_group="CURRENT_LIABILITIES", parent_id=parent.id if parent else None, level=3, is_postable=True, is_cash=False, active=True)
        db.add(liability); db.flush()
    expense = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == "624120"))
    if not expense:
        parent = db.scalar(select(Account).where(Account.company_id == company_id, Account.code.in_(["620000", "600000"])).order_by(Account.code.desc()))
        expense = Account(company_id=company_id, code="624120", name_ar="مصروف الضريبة الانتقائية", name_en="Excise Tax Expense", account_type="EXPENSE", statement_group="OTHER_EXPENSE", parent_id=parent.id if parent else None, level=3, is_postable=True, is_cash=False, active=True)
        db.add(expense); db.flush()
    return liability, expense

def ensure_categories(db: Session, company_id: int, user_id: int | None = None):
    existing = {x.code: x for x in db.scalars(select(ExciseTaxCategory).where(ExciseTaxCategory.company_id == company_id)).all()}
    for code, ar, en, statutory, reference in DEFAULT_CATEGORIES:
        if code in existing:
            continue
        row = ExciseTaxCategory(company_id=company_id, code=code, name_ar=ar, name_en=en,
            statutory_rate=Decimal(statutory), tariff_reference=reference, system_code=True,
            active=True, created_by=user_id)
        db.add(row); db.flush(); existing[code] = row
    return existing


def _profile(db: Session, profile_id: int, company_id: int | None = None) -> ExciseWarehouseProfile:
    stmt = select(ExciseWarehouseProfile).where(ExciseWarehouseProfile.id == profile_id).options(selectinload(ExciseWarehouseProfile.warehouse))
    if company_id is not None:
        stmt = stmt.where(ExciseWarehouseProfile.company_id == company_id)
    row = db.scalar(stmt)
    if not row:
        raise HTTPException(404, "Excise tax warehouse profile not found")
    return row


def _product(db: Session, product_id: int, company_id: int | None = None) -> ExciseProduct:
    stmt = select(ExciseProduct).where(ExciseProduct.id == product_id).options(selectinload(ExciseProduct.item), selectinload(ExciseProduct.category))
    if company_id is not None:
        stmt = stmt.where(ExciseProduct.company_id == company_id)
    row = db.scalar(stmt)
    if not row:
        raise HTTPException(404, "Excise product not found")
    return row


def _movement(db: Session, movement_id: int) -> ExciseMovement:
    row = db.scalar(select(ExciseMovement).where(ExciseMovement.id == movement_id).options(
        selectinload(ExciseMovement.product).selectinload(ExciseProduct.item),
        selectinload(ExciseMovement.product).selectinload(ExciseProduct.category),
        selectinload(ExciseMovement.warehouse_profile).selectinload(ExciseWarehouseProfile.warehouse),
        selectinload(ExciseMovement.destination_warehouse_profile).selectinload(ExciseWarehouseProfile.warehouse),
    ))
    if not row:
        raise HTTPException(404, "Excise movement not found")
    return row


def _stock_map(db: Session, company_id: int, as_of: date | None = None) -> dict[tuple[int, int], Decimal]:
    stmt = select(ExciseMovement).where(ExciseMovement.company_id == company_id, ExciseMovement.status == "APPROVED_POSTED")
    if as_of:
        stmt = stmt.where(ExciseMovement.movement_date <= as_of)
    rows = db.scalars(stmt.order_by(ExciseMovement.id)).all()
    balances: dict[tuple[int, int], Decimal] = {}
    def add(profile_id: int | None, product_id: int, value: Decimal):
        if not profile_id:
            return
        key = (profile_id, product_id); balances[key] = qty(balances.get(key, Decimal(0)) + value)
    for row in rows:
        q = qty(row.quantity)
        if row.event_type in INBOUND_EVENTS:
            add(row.warehouse_profile_id, row.product_id, q)
        elif row.event_type in OUTBOUND_EVENTS:
            add(row.warehouse_profile_id, row.product_id, -q)
        elif row.event_type == "TRANSFER_SUSPENDED":
            add(row.warehouse_profile_id, row.product_id, -q)
            add(row.destination_warehouse_profile_id, row.product_id, q)
    return balances


class WarehouseProfileIn(BaseModel):
    company_id: int
    warehouse_id: int
    license_number: str = Field(min_length=2, max_length=150)
    license_start_date: date
    license_expiry_date: date
    permitted_activities: str = Field(default="STORE", max_length=250)
    bank_guarantee_amount: Decimal = Field(default=0, ge=0)
    estimated_monthly_excise_value: Decimal = Field(default=0, ge=0)
    status: str = "ACTIVE"
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.license_expiry_date < self.license_start_date:
            raise ValueError("License expiry cannot precede its start date")
        self.status = self.status.upper()
        if self.status not in {"ACTIVE", "SUSPENDED", "EXPIRED", "CANCELLED"}:
            raise ValueError("Invalid tax warehouse status")
        return self


class ProductIn(BaseModel):
    company_id: int
    item_id: int
    category_id: int
    hs_code: str | None = Field(default=None, max_length=30)
    zatca_registration_reference: str | None = Field(default=None, max_length=150)
    registered_retail_price: Decimal = Field(ge=0)
    indicative_price: Decimal = Field(default=0, ge=0)
    package_quantity: Decimal = Field(default=1, gt=0)
    package_uom: str = Field(default="EA", min_length=1, max_length=20)
    tax_stamp_required: bool = False


class MovementIn(BaseModel):
    company_id: int
    movement_date: date
    event_type: str
    product_id: int
    warehouse_profile_id: int | None = None
    destination_warehouse_profile_id: int | None = None
    quantity: Decimal = Field(gt=0)
    tax_settlement_method: str = "SUSPENDED"
    customs_declaration_number: str | None = Field(default=None, max_length=150)
    customs_excise_paid: Decimal = Field(default=0, ge=0)
    debit_account_code: str | None = None
    bank_account_id: int | None = None
    reference: str | None = Field(default=None, max_length=150)
    description: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_event(self):
        self.event_type = self.event_type.upper(); self.tax_settlement_method = self.tax_settlement_method.upper()
        if self.event_type not in ALL_EVENTS:
            raise ValueError("Invalid excise movement event")
        if self.tax_settlement_method not in SETTLEMENTS:
            raise ValueError("Invalid excise settlement method")
        if self.event_type == "TRANSFER_SUSPENDED" and not self.destination_warehouse_profile_id:
            raise ValueError("Destination tax warehouse is required for suspended transfers")
        if self.event_type != "TRANSFER_SUSPENDED" and self.destination_warehouse_profile_id:
            raise ValueError("Destination tax warehouse is only valid for suspended transfers")
        if self.event_type == "IMPORT_RECEIPT" and self.tax_settlement_method == "CUSTOMS_PAID" and not self.customs_declaration_number:
            raise ValueError("Customs declaration number is required for customs-paid imports")
        if self.tax_settlement_method == "CUSTOMS_PAID" and not self.bank_account_id:
            raise ValueError("Bank account is required when excise tax was paid at customs")
        return self


class ReturnIn(BaseModel):
    company_id: int
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_start.day != 1 or self.period_start.month not in {1, 3, 5, 7, 9, 11}:
            raise ValueError("Excise return must start on the first day of an odd-numbered month")
        expected_month = self.period_start.month + 1
        if self.period_end.year != self.period_start.year or self.period_end.month != expected_month:
            raise ValueError("Excise return must cover one complete two-month period")
        next_month = date(self.period_end.year + (1 if self.period_end.month == 12 else 0), 1 if self.period_end.month == 12 else self.period_end.month + 1, 1)
        if self.period_end != next_month - timedelta(days=1):
            raise ValueError("Excise return period end is invalid")
        return self


class ReturnPaymentIn(BaseModel):
    bank_account_id: int
    payment_date: date
    sadad_invoice_number: str = Field(min_length=2, max_length=120)
    payment_reference: str = Field(min_length=2, max_length=150)


def serialize_profile(row: ExciseWarehouseProfile) -> dict:
    required = money(row.estimated_monthly_excise_value) * Decimal("0.05")
    return {"id": row.id, "company_id": row.company_id, "warehouse_id": row.warehouse_id,
        "warehouse_code": row.warehouse.code, "warehouse_name_ar": row.warehouse.name_ar,
        "warehouse_name_en": row.warehouse.name_en, "license_number": row.license_number,
        "license_start_date": row.license_start_date, "license_expiry_date": row.license_expiry_date,
        "permitted_activities": row.permitted_activities, "bank_guarantee_amount": money(row.bank_guarantee_amount),
        "estimated_monthly_excise_value": money(row.estimated_monthly_excise_value),
        "minimum_guarantee_indicator": money(required), "guarantee_indicator_sufficient": money(row.bank_guarantee_amount) >= money(required),
        "status": row.status, "notes": row.notes}


def serialize_product(row: ExciseProduct) -> dict:
    base = max(Decimal(row.registered_retail_price or 0), Decimal(row.indicative_price or 0))
    return {"id": row.id, "company_id": row.company_id, "item_id": row.item_id, "item_code": row.item.code,
        "item_name_ar": row.item.name_ar, "item_name_en": row.item.name_en, "category_id": row.category_id,
        "category_code": row.category.code, "category_name_ar": row.category.name_ar, "category_name_en": row.category.name_en,
        "excise_rate": rate(row.category.statutory_rate), "hs_code": row.hs_code,
        "zatca_registration_reference": row.zatca_registration_reference,
        "registered_retail_price": Decimal(row.registered_retail_price or 0), "indicative_price": Decimal(row.indicative_price or 0),
        "taxable_unit_value": base, "package_quantity": Decimal(row.package_quantity or 1), "package_uom": row.package_uom,
        "tax_stamp_required": row.tax_stamp_required, "active": row.active}


def serialize_movement(row: ExciseMovement) -> dict:
    return {"id": row.id, "company_id": row.company_id, "number": row.number, "movement_date": row.movement_date,
        "event_type": row.event_type, "product_id": row.product_id, "item_code": row.product.item.code,
        "item_name_ar": row.product.item.name_ar, "item_name_en": row.product.item.name_en,
        "category_code": row.product.category.code, "warehouse_profile_id": row.warehouse_profile_id,
        "warehouse_code": row.warehouse_profile.warehouse.code if row.warehouse_profile else None,
        "destination_warehouse_profile_id": row.destination_warehouse_profile_id,
        "destination_warehouse_code": row.destination_warehouse_profile.warehouse.code if row.destination_warehouse_profile else None,
        "quantity": qty(row.quantity), "taxable_unit_value": Decimal(row.taxable_unit_value or 0),
        "taxable_value": money(row.taxable_value), "excise_rate": rate(row.excise_rate), "excise_amount": money(row.excise_amount),
        "customs_declaration_number": row.customs_declaration_number, "customs_excise_paid": money(row.customs_excise_paid),
        "tax_settlement_method": row.tax_settlement_method, "reference": row.reference, "description": row.description,
        "status": row.status, "journal_id": row.journal_id}


def serialize_return(row: ExciseTaxReturn, as_of: date | None = None) -> dict:
    as_of = as_of or date.today(); days = max(0, (as_of - row.due_date).days) if row.status not in {"PAID"} else 0
    penalty = money(math_ceil_periods(days) * Decimal("0.05") * money(row.tax_payable)) if days else Decimal(0)
    return {"id": row.id, "company_id": row.company_id, "number": row.number, "period_start": row.period_start,
        "period_end": row.period_end, "due_date": row.due_date, "status": row.status,
        "taxable_value": money(row.taxable_value), "gross_excise": money(row.gross_excise), "customs_paid": money(row.customs_paid),
        "tax_payable": money(row.tax_payable), "gl_payable": money(row.gl_payable),
        "reconciliation_difference": money(row.reconciliation_difference), "estimated_late_penalty": penalty,
        "sadad_invoice_number": row.sadad_invoice_number, "payment_reference": row.payment_reference, "payment_date": row.payment_date,
        "lines": [{"category_id": x.category_id, "category_code": x.category.code, "category_name_ar": x.category.name_ar,
            "category_name_en": x.category.name_en, "rate": rate(x.category.statutory_rate), "quantity": qty(x.quantity),
            "taxable_value": money(x.taxable_value), "gross_excise": money(x.gross_excise), "customs_paid": money(x.customs_paid),
            "tax_payable": money(x.tax_payable), "movement_count": x.movement_count} for x in row.lines]}


def math_ceil_periods(days: int) -> int:
    return (days + 29) // 30


@router.get("/categories")
def categories(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read"); ensure_excise_accounts(db, company_id); ensure_categories(db, company_id, user.id); db.commit()
    rows = db.scalars(select(ExciseTaxCategory).where(ExciseTaxCategory.company_id == company_id, ExciseTaxCategory.active.is_(True)).order_by(ExciseTaxCategory.code)).all()
    return [{"id": x.id, "code": x.code, "name_ar": x.name_ar, "name_en": x.name_en, "statutory_rate": rate(x.statutory_rate), "tariff_reference": x.tariff_reference} for x in rows]


@router.post("/warehouse-profiles", status_code=201)
def upsert_warehouse_profile(data: WarehouseProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    warehouse = db.scalar(select(Warehouse).where(Warehouse.id == data.warehouse_id, Warehouse.company_id == data.company_id))
    if not warehouse: raise HTTPException(422, "Warehouse not found")
    row = db.scalar(select(ExciseWarehouseProfile).where(ExciseWarehouseProfile.company_id == data.company_id, ExciseWarehouseProfile.warehouse_id == data.warehouse_id))
    if not row:
        row = ExciseWarehouseProfile(company_id=data.company_id, warehouse_id=data.warehouse_id, created_by=user.id); db.add(row)
    for key, value in data.model_dump().items():
        if key not in {"company_id", "warehouse_id"}: setattr(row, key, value)
    row.updated_by = user.id; db.flush(); write_audit(db, action="EXCISE_WAREHOUSE_PROFILE_SAVED", entity_type="EXCISE_WAREHOUSE", entity_id=row.id, user_id=user.id, company_id=data.company_id)
    db.commit(); return serialize_profile(_profile(db, row.id))


@router.get("/warehouse-profiles")
def list_warehouse_profiles(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(ExciseWarehouseProfile).where(ExciseWarehouseProfile.company_id == company_id).options(selectinload(ExciseWarehouseProfile.warehouse)).order_by(ExciseWarehouseProfile.id)).all()
    return [serialize_profile(x) for x in rows]


@router.post("/products", status_code=201)
def upsert_product(data: ProductIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage"); ensure_categories(db, data.company_id, user.id)
    item = db.scalar(select(Item).where(Item.id == data.item_id, Item.company_id == data.company_id, Item.active.is_(True)))
    category = db.scalar(select(ExciseTaxCategory).where(ExciseTaxCategory.id == data.category_id, ExciseTaxCategory.company_id == data.company_id, ExciseTaxCategory.active.is_(True)))
    if not item or not category: raise HTTPException(422, "Item or excise category not found")
    row = db.scalar(select(ExciseProduct).where(ExciseProduct.company_id == data.company_id, ExciseProduct.item_id == data.item_id))
    if not row:
        row = ExciseProduct(company_id=data.company_id, item_id=data.item_id, created_by=user.id); db.add(row)
    for key, value in data.model_dump().items():
        if key not in {"company_id", "item_id"}: setattr(row, key, value)
    row.updated_by = user.id; db.flush(); write_audit(db, action="EXCISE_PRODUCT_SAVED", entity_type="EXCISE_PRODUCT", entity_id=row.id, user_id=user.id, company_id=data.company_id)
    db.commit(); return serialize_product(_product(db, row.id))


@router.get("/products")
def list_products(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(ExciseProduct).where(ExciseProduct.company_id == company_id).options(selectinload(ExciseProduct.item), selectinload(ExciseProduct.category)).order_by(ExciseProduct.id)).all()
    return [serialize_product(x) for x in rows]


@router.post("/movements", status_code=201)
def create_movement(data: MovementIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage"); ensure_excise_accounts(db, data.company_id)
    product = _product(db, data.product_id, data.company_id)
    source = _profile(db, data.warehouse_profile_id, data.company_id) if data.warehouse_profile_id else None
    destination = _profile(db, data.destination_warehouse_profile_id, data.company_id) if data.destination_warehouse_profile_id else None
    if not source:
        raise HTTPException(422, "Source tax warehouse is required")
    if source and source.status != "ACTIVE": raise HTTPException(422, "Source tax warehouse is not active")
    if destination and destination.status != "ACTIVE": raise HTTPException(422, "Destination tax warehouse is not active")
    if source and not (source.license_start_date <= data.movement_date <= source.license_expiry_date): raise HTTPException(422, "Source tax warehouse license is not valid on movement date")
    if destination and not (destination.license_start_date <= data.movement_date <= destination.license_expiry_date): raise HTTPException(422, "Destination tax warehouse license is not valid on movement date")
    if data.event_type in NON_TAXABLE_EVENTS and data.tax_settlement_method not in {"SUSPENDED", "EXEMPT"}:
        raise HTTPException(422, "Non-taxable/suspended event cannot use payable or customs-paid settlement")
    if data.event_type in TAXABLE_EVENTS and data.tax_settlement_method != "PAYABLE":
        raise HTTPException(422, "Release, self-consumption and unexplained loss require PAYABLE settlement")
    if data.event_type == "IMPORT_RECEIPT" and data.tax_settlement_method not in {"SUSPENDED", "CUSTOMS_PAID", "PAYABLE", "EXEMPT"}:
        raise HTTPException(422, "Invalid import settlement")
    if data.tax_settlement_method in {"PAYABLE", "CUSTOMS_PAID"} and not data.debit_account_code:
        raise HTTPException(422, "Debit account code is required for taxable movements")
    debit = account(db, data.company_id, data.debit_account_code) if data.debit_account_code else None
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True))) if data.bank_account_id else None
    if data.tax_settlement_method == "CUSTOMS_PAID" and not bank: raise HTTPException(422, "Active bank account not found")
    taxable_unit = max(Decimal(product.registered_retail_price or 0), Decimal(product.indicative_price or 0))
    taxable_value = money(qty(data.quantity) * taxable_unit)
    excise = money(taxable_value * Decimal(product.category.statutory_rate or 0) / Decimal(100)) if data.tax_settlement_method not in {"SUSPENDED", "EXEMPT"} else Decimal(0)
    customs_paid = money(data.customs_excise_paid)
    if data.tax_settlement_method == "CUSTOMS_PAID" and customs_paid <= 0: customs_paid = excise
    row = ExciseMovement(company_id=data.company_id, number=_number(db, ExciseMovement, data.company_id, "EXM", data.movement_date.year),
        movement_date=data.movement_date, event_type=data.event_type, product_id=data.product_id,
        warehouse_profile_id=data.warehouse_profile_id, destination_warehouse_profile_id=data.destination_warehouse_profile_id,
        quantity=qty(data.quantity), taxable_unit_value=taxable_unit, taxable_value=taxable_value,
        excise_rate=rate(product.category.statutory_rate), excise_amount=excise,
        customs_declaration_number=data.customs_declaration_number, customs_excise_paid=customs_paid,
        tax_settlement_method=data.tax_settlement_method, debit_account_id=debit.id if debit else None,
        bank_account_id=bank.id if bank else None, reference=data.reference, description=data.description,
        status="DRAFT", created_by=user.id)
    db.add(row); db.flush(); write_audit(db, action="EXCISE_MOVEMENT_CREATED", entity_type="EXCISE_MOVEMENT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"event":row.event_type,"quantity":str(row.quantity),"tax":str(row.excise_amount)})
    db.commit(); return serialize_movement(_movement(db, row.id))


@router.get("/movements")
def list_movements(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(ExciseMovement).where(ExciseMovement.company_id == company_id).options(
        selectinload(ExciseMovement.product).selectinload(ExciseProduct.item),
        selectinload(ExciseMovement.product).selectinload(ExciseProduct.category),
        selectinload(ExciseMovement.warehouse_profile).selectinload(ExciseWarehouseProfile.warehouse),
        selectinload(ExciseMovement.destination_warehouse_profile).selectinload(ExciseWarehouseProfile.warehouse),
    ).order_by(ExciseMovement.movement_date.desc(), ExciseMovement.id.desc())).all()
    return [serialize_movement(x) for x in rows]


@router.post("/movements/{movement_id}/submit")
def submit_movement(movement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _movement(db, movement_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft excise movements can be submitted")
    row.status = "PENDING_APPROVAL"; row.submitted_by = user.id; row.submitted_at = utc_now(); write_audit(db, action="EXCISE_MOVEMENT_SUBMITTED", entity_type="EXCISE_MOVEMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id); db.commit(); return serialize_movement(row)


@router.post("/movements/{movement_id}/approve-post")
def approve_post_movement(movement_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _movement(db, movement_id); ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "PENDING_APPROVAL": raise HTTPException(409, "Excise movement is not pending approval")
    _maker_checker(row.created_by, user.id)
    balances = _stock_map(db, row.company_id, row.movement_date)
    if row.event_type in OUTBOUND_EVENTS | {"TRANSFER_SUSPENDED"}:
        available = balances.get((row.warehouse_profile_id, row.product_id), Decimal(0))
        if available < qty(row.quantity): raise HTTPException(409, f"Insufficient excise suspended stock: available {available}")
    journal = None
    if row.tax_settlement_method == "PAYABLE" and money(row.excise_amount) != 0:
        liability = account(db, row.company_id, "218020")
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.movement_date,
            reference=row.number, description=f"Excise tax {row.event_type} {row.number}",
            lines=[{"account_id":row.debit_account_id,"debit":money(row.excise_amount),"credit":0},
                   {"account_id":liability.id,"debit":0,"credit":money(row.excise_amount)}],
            cash_flow_activity="OPERATING", cash_flow_kind="EXCISE_TAX_ACCRUAL")
    elif row.tax_settlement_method == "CUSTOMS_PAID" and money(row.customs_excise_paid) != 0:
        if not row.bank_account_id: raise HTTPException(422, "Bank account is required for customs-paid excise")
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.movement_date,
            reference=row.customs_declaration_number or row.number, description=f"Excise paid at customs {row.number}",
            lines=[{"account_id":row.debit_account_id,"debit":money(row.customs_excise_paid),"credit":0},
                   {"account_id":row.bank_account.gl_account_id,"debit":0,"credit":money(row.customs_excise_paid)}],
            cash_flow_activity="OPERATING", cash_flow_kind="EXCISE_TAX_CUSTOMS_PAYMENT")
    row.journal_id = journal.id if journal else None; row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="EXCISE_MOVEMENT_APPROVED_POSTED", entity_type="EXCISE_MOVEMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"journal_id":row.journal_id,"tax":str(row.excise_amount),"customs_paid":str(row.customs_excise_paid)})
    db.commit(); return serialize_movement(_movement(db, row.id))


@router.get("/stock")
def excise_stock(company_id: int, as_of: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read"); balances = _stock_map(db, company_id, as_of)
    profiles = {x.id:x for x in db.scalars(select(ExciseWarehouseProfile).where(ExciseWarehouseProfile.company_id == company_id).options(selectinload(ExciseWarehouseProfile.warehouse))).all()}
    products = {x.id:x for x in db.scalars(select(ExciseProduct).where(ExciseProduct.company_id == company_id).options(selectinload(ExciseProduct.item), selectinload(ExciseProduct.category))).all()}
    rows=[]
    for (profile_id, product_id), balance in sorted(balances.items()):
        if balance == 0: continue
        profile=profiles.get(profile_id); product=products.get(product_id)
        if not profile or not product: continue
        base=max(Decimal(product.registered_retail_price or 0),Decimal(product.indicative_price or 0)); exposure=money(balance*base*Decimal(product.category.statutory_rate or 0)/Decimal(100))
        rows.append({"warehouse_profile_id":profile_id,"warehouse_code":profile.warehouse.code,"warehouse_name_ar":profile.warehouse.name_ar,"warehouse_name_en":profile.warehouse.name_en,
            "product_id":product_id,"item_code":product.item.code,"item_name_ar":product.item.name_ar,"item_name_en":product.item.name_en,"category_code":product.category.code,
            "quantity":balance,"uom":product.item.uom,"estimated_excise_exposure":exposure})
    return {"as_of":as_of or date.today(),"rows":rows,"total_estimated_excise_exposure":money(sum((Decimal(x["estimated_excise_exposure"]) for x in rows),Decimal(0)))}


def _return_row(db: Session, return_id: int) -> ExciseTaxReturn:
    row = db.scalar(select(ExciseTaxReturn).where(ExciseTaxReturn.id == return_id).options(selectinload(ExciseTaxReturn.lines).selectinload(ExciseTaxReturnLine.category)))
    if not row: raise HTTPException(404, "Excise return not found")
    return row


@router.post("/returns", status_code=201)
def generate_return(data: ReturnIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    existing = db.scalar(select(ExciseTaxReturn).where(ExciseTaxReturn.company_id == data.company_id, ExciseTaxReturn.period_start == data.period_start, ExciseTaxReturn.period_end == data.period_end).options(selectinload(ExciseTaxReturn.lines)))
    if existing and existing.status != "DRAFT": raise HTTPException(409, "Submitted/approved excise return cannot be regenerated")
    movements = db.scalars(select(ExciseMovement).where(ExciseMovement.company_id == data.company_id,
        ExciseMovement.movement_date >= data.period_start, ExciseMovement.movement_date <= data.period_end,
        ExciseMovement.status == "APPROVED_POSTED", ExciseMovement.tax_settlement_method.in_(["PAYABLE","CUSTOMS_PAID"])).options(
            selectinload(ExciseMovement.product).selectinload(ExciseProduct.category),
            selectinload(ExciseMovement.product).selectinload(ExciseProduct.item)).order_by(ExciseMovement.id)).all()
    if not movements: raise HTTPException(422, "No approved taxable excise movements in the selected period")
    if existing: existing.lines.clear(); row=existing
    else:
        due_month = data.period_end.month + 1; due_year = data.period_end.year
        if due_month == 13: due_month=1; due_year+=1
        due_next_month = due_month + 1; due_next_year = due_year
        if due_next_month == 13: due_next_month = 1; due_next_year += 1
        due_date = date(due_next_year, due_next_month, 1) - timedelta(days=1)
        row = ExciseTaxReturn(company_id=data.company_id, number=_number(db, ExciseTaxReturn, data.company_id, "EXR", data.period_end.year),
            period_start=data.period_start, period_end=data.period_end, due_date=due_date, status="DRAFT", prepared_by=user.id)
        db.add(row); db.flush()
    grouped={}
    for movement in movements:
        cat=movement.product.category; bucket=grouped.setdefault(cat.id,{"category":cat,"quantity":Decimal(0),"value":Decimal(0),"gross":Decimal(0),"customs":Decimal(0),"payable":Decimal(0),"details":[]})
        gross=money(movement.excise_amount); customs=money(movement.customs_excise_paid); payable=money(gross-customs)
        bucket["quantity"]+=qty(movement.quantity); bucket["value"]+=money(movement.taxable_value); bucket["gross"]+=gross; bucket["customs"]+=customs; bucket["payable"]+=payable
        bucket["details"].append({"movement_id":movement.id,"number":movement.number,"event":movement.event_type,"item":movement.product.item.code,"quantity":str(qty(movement.quantity)),"taxable_value":str(money(movement.taxable_value)),"gross_excise":str(gross),"customs_paid":str(customs),"tax_payable":str(payable)})
    total_value=sum((x["value"] for x in grouped.values()),Decimal(0)); total_gross=sum((x["gross"] for x in grouped.values()),Decimal(0)); total_customs=sum((x["customs"] for x in grouped.values()),Decimal(0)); total_payable=sum((x["payable"] for x in grouped.values()),Decimal(0))
    for category_id,b in grouped.items():
        row.lines.append(ExciseTaxReturnLine(category_id=category_id,quantity=qty(b["quantity"]),taxable_value=money(b["value"]),gross_excise=money(b["gross"]),customs_paid=money(b["customs"]),tax_payable=money(b["payable"]),movement_count=len(b["details"]),details_json=json.dumps(b["details"],ensure_ascii=False)))
    payable_ids=[m.journal_id for m in movements if m.tax_settlement_method=="PAYABLE" and m.journal_id]
    gl=Decimal(0); liability=account(db,data.company_id,"218020")
    if payable_ids:
        debit,credit=db.execute(select(func.coalesce(func.sum(JournalLine.debit),0),func.coalesce(func.sum(JournalLine.credit),0)).where(JournalLine.journal_id.in_(payable_ids),JournalLine.account_id==liability.id)).one();gl=money(Decimal(credit)-Decimal(debit))
    row.taxable_value=money(total_value);row.gross_excise=money(total_gross);row.customs_paid=money(total_customs);row.tax_payable=money(total_payable);row.gl_payable=gl;row.reconciliation_difference=money(total_payable-gl);row.prepared_by=user.id
    db.flush();write_audit(db,action="EXCISE_RETURN_GENERATED",entity_type="EXCISE_RETURN",entity_id=row.id,user_id=user.id,company_id=data.company_id,after={"period":str(data.period_start),"gross":str(row.gross_excise),"customs":str(row.customs_paid),"payable":str(row.tax_payable),"difference":str(row.reconciliation_difference)});db.commit();return serialize_return(_return_row(db,row.id))


@router.get("/returns")
def list_returns(company_id:int,as_of:date|None=None,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"compliance.read")
    rows=db.scalars(select(ExciseTaxReturn).where(ExciseTaxReturn.company_id==company_id).options(selectinload(ExciseTaxReturn.lines).selectinload(ExciseTaxReturnLine.category)).order_by(ExciseTaxReturn.period_end.desc())).all()
    return [serialize_return(x,as_of=as_of) for x in rows]


@router.post("/returns/{return_id}/submit")
def submit_return(return_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=_return_row(db,return_id);ensure_permission(db,user,row.company_id,"compliance.manage")
    if row.status!="DRAFT":raise HTTPException(409,"Only draft excise returns can be submitted")
    if money(row.reconciliation_difference)!=0:raise HTTPException(409,"Excise return does not reconcile to the general ledger")
    row.status="PENDING_APPROVAL";row.submitted_by=user.id;row.submitted_at=utc_now();write_audit(db,action="EXCISE_RETURN_SUBMITTED",entity_type="EXCISE_RETURN",entity_id=row.id,user_id=user.id,company_id=row.company_id);db.commit();return serialize_return(row)


@router.post("/returns/{return_id}/approve")
def approve_return(return_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=_return_row(db,return_id);ensure_permission(db,user,row.company_id,"compliance.manage")
    if row.status!="PENDING_APPROVAL":raise HTTPException(409,"Excise return is not pending approval")
    _maker_checker(row.prepared_by,user.id);row.status="APPROVED";row.approved_by=user.id;row.approved_at=utc_now();write_audit(db,action="EXCISE_RETURN_APPROVED",entity_type="EXCISE_RETURN",entity_id=row.id,user_id=user.id,company_id=row.company_id);db.commit();return serialize_return(row)


@router.post("/returns/{return_id}/pay")
def pay_return(return_id:int,data:ReturnPaymentIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=_return_row(db,return_id);ensure_permission(db,user,row.company_id,"compliance.manage")
    if row.status!="APPROVED":raise HTTPException(409,"Only approved excise returns can be paid")
    if money(row.tax_payable)<=0:raise HTTPException(409,"Excise return has no payable amount")
    if data.payment_date<row.period_end:raise HTTPException(422,"Payment date cannot precede the return period end")
    bank=db.scalar(select(BankAccount).where(BankAccount.id==data.bank_account_id,BankAccount.company_id==row.company_id,BankAccount.active.is_(True)))
    if not bank:raise HTTPException(422,"Bank account not found")
    liability=account(db,row.company_id,"218020")
    journal=create_posted_journal(db,company_id=row.company_id,user_id=user.id,posting_date=data.payment_date,reference=data.sadad_invoice_number,description=f"Payment of excise return {row.number}",lines=[{"account_id":liability.id,"debit":money(row.tax_payable),"credit":0},{"account_id":bank.gl_account_id,"debit":0,"credit":money(row.tax_payable)}],cash_flow_activity="OPERATING",cash_flow_kind="EXCISE_TAX_PAYMENTS")
    row.status="PAID";row.sadad_invoice_number=data.sadad_invoice_number;row.payment_reference=data.payment_reference;row.payment_date=data.payment_date;row.payment_journal_id=journal.id;row.paid_by=user.id;row.paid_at=utc_now();write_audit(db,action="EXCISE_RETURN_PAID",entity_type="EXCISE_RETURN",entity_id=row.id,user_id=user.id,company_id=row.company_id,after={"journal":journal.number,"sadad":data.sadad_invoice_number,"amount":str(row.tax_payable)});db.commit();return serialize_return(row)


@router.get("/export/movements.csv")
def export_movements(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=list_movements(company_id,user=user,db=db)
    return _csv("excise_movements.csv",["Number","Date","Event","Item","Category","Source warehouse","Destination warehouse","Quantity","Taxable value","Rate","Gross excise","Customs paid","Settlement","Status","Journal ID"],[[x["number"],x["movement_date"],x["event_type"],x["item_code"],x["category_code"],x["warehouse_code"],x["destination_warehouse_code"],x["quantity"],x["taxable_value"],x["excise_rate"],x["excise_amount"],x["customs_excise_paid"],x["tax_settlement_method"],x["status"],x["journal_id"]] for x in rows])


@router.get("/export/returns.csv")
def export_returns(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=list_returns(company_id,user=user,db=db)
    return _csv("excise_tax_returns.csv",["Number","Period start","Period end","Due date","Taxable value","Gross excise","Customs paid","Tax payable","GL payable","Difference","Status","SADAD invoice","Payment date"],[[x["number"],x["period_start"],x["period_end"],x["due_date"],x["taxable_value"],x["gross_excise"],x["customs_paid"],x["tax_payable"],x["gl_payable"],x["reconciliation_difference"],x["status"],x["sadad_invoice_number"],x["payment_date"]] for x in rows])


@router.get("/export/stock.csv")
def export_stock(company_id:int,as_of:date|None=None,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    result=excise_stock(company_id,as_of=as_of,user=user,db=db)
    return _csv("excise_tax_warehouse_stock.csv",["As of","Warehouse","Item","Category","Quantity","UOM","Estimated excise exposure"],[[result["as_of"],x["warehouse_code"],x["item_code"],x["category_code"],x["quantity"],x["uom"],x["estimated_excise_exposure"]] for x in result["rows"]])
