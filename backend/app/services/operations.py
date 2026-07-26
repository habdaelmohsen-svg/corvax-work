from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Item, StockMovement, Warehouse

MONEY = Decimal("0.01")
QTY = Decimal("0.0001")


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def quantity(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(QTY, rounding=ROUND_HALF_UP)


def get_account(db: Session, company_id: int, code: str) -> Account:
    account = db.scalar(
        select(Account).where(
            Account.company_id == company_id,
            Account.code == code,
            Account.active.is_(True),
        )
    )
    if not account or not account.is_postable:
        raise HTTPException(422, f"Postable account not found: {code}")
    return account


def get_item(db: Session, company_id: int, item_id: int) -> Item:
    item = db.scalar(select(Item).where(Item.id == item_id, Item.company_id == company_id, Item.active.is_(True)))
    if not item:
        raise HTTPException(404, "Item not found")
    return item


def get_warehouse(db: Session, company_id: int, warehouse_id: int) -> Warehouse:
    warehouse = db.scalar(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.company_id == company_id,
            Warehouse.active.is_(True),
        )
    )
    if not warehouse:
        raise HTTPException(404, "Warehouse not found")
    return warehouse


def stock_balance(db: Session, company_id: int, warehouse_id: int, item_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
            StockMovement.company_id == company_id,
            StockMovement.warehouse_id == warehouse_id,
            StockMovement.item_id == item_id,
        )
    )
    return quantity(value or 0)


def stock_value(db: Session, company_id: int, warehouse_id: int | None = None, item_id: int | None = None) -> Decimal:
    query = select(func.coalesce(func.sum(StockMovement.total_cost), 0)).where(StockMovement.company_id == company_id)
    if warehouse_id is not None:
        query = query.where(StockMovement.warehouse_id == warehouse_id)
    if item_id is not None:
        query = query.where(StockMovement.item_id == item_id)
    return money(db.scalar(query) or 0)


def next_document_number(db: Session, model, company_id: int, prefix: str, document_date: date) -> str:
    count = db.scalar(
        select(func.count(model.id)).where(
            model.company_id == company_id,
            func.extract("year", getattr(model, next(c for c in ("order_date", "receipt_date", "run_date", "statement_date", "start_date", "commencement_date", "inspection_date") if hasattr(model, c)))) == document_date.year,
        )
    ) or 0
    return f"{prefix}-{company_id}-{document_date.year}-{count + 1:05d}"
