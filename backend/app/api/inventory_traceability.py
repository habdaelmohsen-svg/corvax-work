"""CORVAX RC27.4 H9 - strict inventory traceability API.

Inbound shipments (container / PL / commercial invoice / customs clearance),
value-based landed-cost allocation, weighted-average receipt into perpetual stock,
strict item classification, and IAS 2 lower-of-cost-or-NRV write-downs.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Account, Item, StockMovement, User, Warehouse
from app.models.inbound_shipment import (
    ALLOCATION_METHODS, InboundShipment, InboundShipmentLine, ITEM_TYPES,
    PHYSICAL_ISSUE_METHODS, RAW_MATERIAL_SUBTYPES, VALUATION_METHODS,
)
from app.services.audit import write_audit
from app.services.operations import get_account, get_item, get_warehouse, money, quantity, stock_balance, stock_value
from app.services.posting import create_posted_journal, ensure_open_period

router = APIRouter(prefix="/inventory", tags=["inventory traceability"])

TWO = Decimal("0.01")
FOUR = Decimal("0.0001")


# --------------------------------------------------------------------------- schemas
class ShipmentLineIn(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0)
    supplier_unit_cost: Decimal = Field(gt=0)
    lot_number: str | None = None
    expiry_date: date | None = None


class ShipmentIn(BaseModel):
    company_id: int
    warehouse_id: int
    supplier_id: int
    arrival_date: date
    container_number: str = Field(min_length=1, max_length=60)
    packing_list_number: str = Field(min_length=1, max_length=60)
    commercial_invoice_number: str = Field(min_length=1, max_length=60)
    customs_clearance_number: str | None = None
    customs_declaration_number: str | None = None
    purchase_order_id: int | None = None
    port_of_entry: str | None = None
    carrier: str | None = None
    freight_cost: Decimal = Field(ge=0, default=0)
    customs_duty: Decimal = Field(ge=0, default=0)
    clearance_fees: Decimal = Field(ge=0, default=0)
    other_costs: Decimal = Field(ge=0, default=0)
    allocation_method: str = "VALUE"
    lines: list[ShipmentLineIn] = Field(min_length=1)


class ItemClassificationIn(BaseModel):
    company_id: int
    item_id: int
    item_type: str
    item_subtype: str | None = None
    valuation_method: str | None = None
    physical_issue_method: str | None = None


class NrvIn(BaseModel):
    company_id: int
    item_id: int
    warehouse_id: int
    nrv_per_unit: Decimal | None = Field(default=None, ge=0)
    expense_account_code: str = "620010"      # خسائر انخفاض القيمة
    provision_account_code: str = "113020"    # مخصص انخفاض قيمة المخزون
    write_date: date | None = None


# --------------------------------------------------------------------------- helpers
def _shipment_number(db: Session, company_id: int, on: date) -> str:
    # func.extract('year', ...) is portable across SQLite and PostgreSQL (Render),
    # unlike strftime which only exists on SQLite.
    count = db.scalar(
        select(func.count(InboundShipment.id)).where(
            InboundShipment.company_id == company_id,
            func.extract("year", InboundShipment.created_at) == on.year,
        )
    ) or 0
    return f"SHP-{company_id}-{on.year}-{count + 1:05d}"


def _serialize(shipment: InboundShipment, *, with_lines: bool = True) -> dict:
    data = {
        "id": shipment.id,
        "company_id": shipment.company_id,
        "number": shipment.number,
        "container_number": shipment.container_number,
        "packing_list_number": shipment.packing_list_number,
        "commercial_invoice_number": shipment.commercial_invoice_number,
        "customs_clearance_number": shipment.customs_clearance_number,
        "customs_declaration_number": shipment.customs_declaration_number,
        "supplier_id": shipment.supplier_id,
        "supplier_name_ar": getattr(shipment.supplier, "name_ar", None),
        "warehouse_id": shipment.warehouse_id,
        "arrival_date": shipment.arrival_date.isoformat(),
        "port_of_entry": shipment.port_of_entry,
        "carrier": shipment.carrier,
        "goods_value": shipment.goods_value,
        "freight_cost": shipment.freight_cost,
        "customs_duty": shipment.customs_duty,
        "clearance_fees": shipment.clearance_fees,
        "other_costs": shipment.other_costs,
        "landed_cost_total": shipment.landed_cost_total,
        "allocation_method": shipment.allocation_method,
        "status": shipment.status,
        "journal_id": shipment.journal_id,
    }
    if with_lines:
        data["lines"] = [
            {
                "id": line.id,
                "item_id": line.item_id,
                "item_code": getattr(line.item, "code", None),
                "quantity": line.quantity,
                "supplier_unit_cost": line.supplier_unit_cost,
                "line_goods_value": line.line_goods_value,
                "allocated_landed_cost": line.allocated_landed_cost,
                "landed_unit_cost": line.landed_unit_cost,
                "lot_number": line.lot_number,
                "expiry_date": line.expiry_date.isoformat() if line.expiry_date else None,
            }
            for line in shipment.lines
        ]
    return data


def _allocate(shipment: InboundShipment) -> None:
    """Value-based landed-cost allocation (IAS 2). Extra freight/customs/fees are
    distributed across lines in proportion to each line's goods value."""
    extra = money(
        Decimal(shipment.freight_cost) + Decimal(shipment.customs_duty)
        + Decimal(shipment.clearance_fees) + Decimal(shipment.other_costs)
    )
    goods_total = money(sum((Decimal(line.line_goods_value) for line in shipment.lines), Decimal("0")))
    running = Decimal("0")
    lines = list(shipment.lines)
    for index, line in enumerate(lines):
        if index == len(lines) - 1:
            share = money(extra - running)  # last line absorbs rounding
        else:
            base = Decimal(line.line_goods_value)
            share = money(extra * base / goods_total) if goods_total > 0 else Decimal("0")
            running += share
        line.allocated_landed_cost = share
        total_line_cost = money(Decimal(line.line_goods_value) + share)
        qty = Decimal(line.quantity)
        line.landed_unit_cost = (total_line_cost / qty).quantize(FOUR) if qty > 0 else Decimal("0")
    shipment.landed_cost_total = money(goods_total + extra)


# --------------------------------------------------------------------------- endpoints
@router.post("/inbound-shipments", status_code=201)
def create_shipment(data: ShipmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "inventory.receive")
    ensure_open_period(db, data.company_id, data.arrival_date)
    if data.allocation_method not in ALLOCATION_METHODS:
        raise HTTPException(422, f"Invalid allocation_method. Allowed: {sorted(ALLOCATION_METHODS)}")
    get_warehouse(db, data.company_id, data.warehouse_id)

    shipment = InboundShipment(
        company_id=data.company_id,
        number=_shipment_number(db, data.company_id, data.arrival_date),
        container_number=data.container_number.strip(),
        packing_list_number=data.packing_list_number.strip(),
        commercial_invoice_number=data.commercial_invoice_number.strip(),
        customs_clearance_number=data.customs_clearance_number,
        customs_declaration_number=data.customs_declaration_number,
        supplier_id=data.supplier_id,
        warehouse_id=data.warehouse_id,
        purchase_order_id=data.purchase_order_id,
        arrival_date=data.arrival_date,
        port_of_entry=data.port_of_entry,
        carrier=data.carrier,
        freight_cost=money(data.freight_cost),
        customs_duty=money(data.customs_duty),
        clearance_fees=money(data.clearance_fees),
        other_costs=money(data.other_costs),
        allocation_method=data.allocation_method,
        status="DRAFT",
        created_by=user.id,
    )
    goods_value = Decimal("0")
    for line_in in data.lines:
        item = get_item(db, data.company_id, line_in.item_id)
        line_value = money(Decimal(line_in.quantity) * Decimal(line_in.supplier_unit_cost))
        goods_value += line_value
        shipment.lines.append(InboundShipmentLine(
            item_id=item.id,
            quantity=quantity(line_in.quantity),
            supplier_unit_cost=Decimal(line_in.supplier_unit_cost).quantize(FOUR),
            line_goods_value=line_value,
            lot_number=line_in.lot_number,
            expiry_date=line_in.expiry_date,
        ))
    shipment.goods_value = money(goods_value)

    # Duplicate container guard (explicit friendly message before the DB constraint).
    dup = db.scalar(select(InboundShipment.id).where(
        InboundShipment.company_id == data.company_id,
        InboundShipment.container_number == shipment.container_number,
    ))
    if dup is not None:
        raise HTTPException(409, f"Container '{shipment.container_number}' already recorded for this company.")

    _allocate(shipment)
    shipment.status = "COSTED"
    db.add(shipment)
    db.flush()
    write_audit(db, action="INBOUND_SHIPMENT_CREATED", entity_type="INBOUND_SHIPMENT", entity_id=shipment.id,
                user_id=user.id, company_id=data.company_id,
                after={"number": shipment.number, "container": shipment.container_number, "landed_cost": str(shipment.landed_cost_total)})
    db.commit()
    return _serialize(shipment)


@router.get("/inbound-shipments")
def list_shipments(company_id: int, status: str | None = Query(default=None),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    query = select(InboundShipment).where(InboundShipment.company_id == company_id)
    if status:
        query = query.where(InboundShipment.status == status)
    query = query.order_by(InboundShipment.arrival_date.desc(), InboundShipment.id.desc())
    return [_serialize(s, with_lines=False) for s in db.scalars(query).all()]


@router.get("/inbound-shipments/{shipment_id}")
def get_shipment(shipment_id: int, company_id: int,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    shipment = db.scalar(select(InboundShipment).options(selectinload(InboundShipment.lines))
                         .where(InboundShipment.id == shipment_id, InboundShipment.company_id == company_id))
    if not shipment:
        raise HTTPException(404, "Inbound shipment not found")
    return _serialize(shipment)


@router.post("/inbound-shipments/{shipment_id}/receive")
def receive_shipment(shipment_id: int, company_id: int,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.receive")
    shipment = db.scalar(select(InboundShipment).options(selectinload(InboundShipment.lines))
                         .where(InboundShipment.id == shipment_id, InboundShipment.company_id == company_id))
    if not shipment:
        raise HTTPException(404, "Inbound shipment not found")
    if shipment.status == "RECEIVED":
        raise HTTPException(409, "Shipment already received")
    if shipment.status != "COSTED":
        raise HTTPException(409, "Shipment must be costed before receiving")
    ensure_open_period(db, company_id, shipment.arrival_date)

    inventory_account = get_account(db, company_id, "113010")
    payable_account = get_account(db, company_id, "211010")     # دائنون - قيمة البضاعة للمورد
    # Landed costs (freight/customs/fees) are an unpaid liability, not a contra-asset.
    # 217010 مصروفات مستحقة is the correct accrued-expenses liability account.
    clearing_account = get_account(db, company_id, "217010")    # مصروفات مستحقة - تكاليف واصلة

    journal_lines = []
    for line in shipment.lines:
        item = get_item(db, company_id, line.item_id)
        landed_total = money(Decimal(line.line_goods_value) + Decimal(line.allocated_landed_cost))
        db.add(StockMovement(
            company_id=company_id, warehouse_id=shipment.warehouse_id, item_id=item.id,
            movement_date=shipment.arrival_date, movement_type="RECEIPT",
            quantity=quantity(line.quantity), unit_cost=Decimal(line.landed_unit_cost),
            total_cost=landed_total, lot_number=line.lot_number, expiry_date=line.expiry_date,
            reference_type="INBOUND_SHIPMENT", reference_id=shipment.id,
            inbound_shipment_id=shipment.id, created_by=user.id,
        ))
        journal_lines.append({"account_id": inventory_account.id, "debit": landed_total, "credit": 0,
                              "description": f"{item.code} landed"})

    extra = money(Decimal(shipment.freight_cost) + Decimal(shipment.customs_duty)
                  + Decimal(shipment.clearance_fees) + Decimal(shipment.other_costs))
    if shipment.goods_value:
        journal_lines.append({"account_id": payable_account.id, "debit": 0, "credit": money(shipment.goods_value),
                              "description": f"Goods {shipment.commercial_invoice_number}"})
    if extra:
        journal_lines.append({"account_id": clearing_account.id, "debit": 0, "credit": extra,
                              "description": f"Landed costs {shipment.number}"})

    journal = create_posted_journal(
        db, company_id=company_id, user_id=user.id, posting_date=shipment.arrival_date,
        reference=shipment.number, description=f"Inbound shipment {shipment.number} / container {shipment.container_number}",
        lines=journal_lines,
    )
    shipment.status = "RECEIVED"
    shipment.received_by = user.id
    shipment.journal_id = journal.id
    write_audit(db, action="INBOUND_SHIPMENT_RECEIVED", entity_type="INBOUND_SHIPMENT", entity_id=shipment.id,
                user_id=user.id, company_id=company_id, before={"status": "COSTED"},
                after={"status": "RECEIVED", "journal": journal.number})
    db.commit()
    return {"id": shipment.id, "number": shipment.number, "status": shipment.status,
            "journal_number": journal.number, "landed_cost_total": shipment.landed_cost_total}


@router.post("/items/classify")
def classify_item(data: ItemClassificationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "inventory.manage")
    item = get_item(db, data.company_id, data.item_id)
    if data.item_type not in ITEM_TYPES:
        raise HTTPException(422, f"Invalid item_type. Allowed: {sorted(ITEM_TYPES)}")
    if data.item_type == "RAW_MATERIAL" and data.item_subtype and data.item_subtype not in RAW_MATERIAL_SUBTYPES:
        raise HTTPException(422, f"Invalid raw-material subtype. Allowed: {sorted(RAW_MATERIAL_SUBTYPES)}")
    if data.valuation_method is not None:
        if data.valuation_method not in VALUATION_METHODS:
            raise HTTPException(422, f"Invalid valuation_method. IAS 2 allows only: {sorted(VALUATION_METHODS)} (LIFO is prohibited).")
        before = item.valuation_method
        item.valuation_method = data.valuation_method
        write_audit(db, action="ITEM_VALUATION_CHANGED", entity_type="ITEM", entity_id=item.id,
                    user_id=user.id, company_id=data.company_id,
                    before={"valuation_method": before}, after={"valuation_method": data.valuation_method})
    if data.physical_issue_method is not None:
        if data.physical_issue_method not in PHYSICAL_ISSUE_METHODS:
            raise HTTPException(422, f"Invalid physical_issue_method. Allowed: {sorted(PHYSICAL_ISSUE_METHODS)}")
        item.physical_issue_method = data.physical_issue_method
    item.item_type = data.item_type
    item.item_subtype = data.item_subtype
    db.commit()
    return {"id": item.id, "code": item.code, "item_type": item.item_type, "item_subtype": item.item_subtype,
            "valuation_method": item.valuation_method, "physical_issue_method": item.physical_issue_method}


@router.get("/nrv-assessment")
def nrv_assessment(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """IAS 2 lower-of-cost-or-NRV report for the external auditor: for every item/warehouse
    holding stock, compare weighted-average cost to NRV and show the shortfall."""
    ensure_permission(db, user, company_id, "inventory.read")
    rows = db.execute(
        select(Item.id, Item.code, Item.name_ar, Item.nrv_per_unit, Warehouse.id, Warehouse.name_ar,
               func.coalesce(func.sum(StockMovement.quantity), 0),
               func.coalesce(func.sum(StockMovement.total_cost), 0))
        .join(StockMovement, StockMovement.item_id == Item.id)
        .join(Warehouse, Warehouse.id == StockMovement.warehouse_id)
        .where(Item.company_id == company_id)
        .group_by(Item.id, Warehouse.id).order_by(Item.code)
    ).all()
    result = []
    total_writedown = Decimal("0")
    for item_id, code, name_ar, nrv, wh_id, wh_name, qty, value in rows:
        qty = quantity(qty)
        if qty <= 0:
            continue
        value = money(value)
        unit_cost = (value / qty).quantize(FOUR) if qty else Decimal("0")
        nrv_unit = Decimal(nrv) if nrv is not None else None
        writedown = Decimal("0")
        if nrv_unit is not None and nrv_unit < unit_cost:
            writedown = money((unit_cost - nrv_unit) * qty)
            total_writedown += writedown
        result.append({
            "item_id": item_id, "item_code": code, "item_name_ar": name_ar,
            "warehouse_id": wh_id, "warehouse_name_ar": wh_name,
            "quantity": qty, "carrying_cost": value, "unit_cost": unit_cost,
            "nrv_per_unit": nrv_unit, "measured_at": "NRV" if writedown > 0 else "COST",
            "writedown_required": writedown,
        })
    return {"company_id": company_id, "as_of": date.today().isoformat(),
            "total_writedown_required": money(total_writedown), "lines": result}


@router.post("/nrv-writedown")
def nrv_writedown(data: NrvIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Record the IAS 2 write-down to the lower of cost or NRV for one item/warehouse.
    If nrv_per_unit is provided it is saved on the item; otherwise the stored value is used."""
    ensure_permission(db, user, data.company_id, "inventory.manage")
    item = get_item(db, data.company_id, data.item_id)
    get_warehouse(db, data.company_id, data.warehouse_id)
    write_date = data.write_date or date.today()
    ensure_open_period(db, data.company_id, write_date)

    if data.nrv_per_unit is not None:
        item.nrv_per_unit = Decimal(data.nrv_per_unit).quantize(FOUR)
    if item.nrv_per_unit is None:
        raise HTTPException(422, "No NRV set for this item. Provide nrv_per_unit.")

    qty = stock_balance(db, data.company_id, data.warehouse_id, data.item_id)
    if qty <= 0:
        raise HTTPException(422, "No stock on hand for this item/warehouse.")
    value = stock_value(db, data.company_id, data.warehouse_id, data.item_id)
    unit_cost = (money(value) / qty).quantize(FOUR) if qty else Decimal("0")
    nrv_unit = Decimal(item.nrv_per_unit)
    if nrv_unit >= unit_cost:
        return {"writedown": "0.00", "message": "NRV is not below cost; no write-down required.",
                "unit_cost": unit_cost, "nrv_per_unit": nrv_unit}

    writedown = money((unit_cost - nrv_unit) * qty)
    expense = get_account(db, data.company_id, data.expense_account_code)
    provision = get_account(db, data.company_id, data.provision_account_code)
    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=write_date,
        reference=f"NRV-{item.code}", description=f"Inventory NRV write-down {item.code}",
        lines=[{"account_id": expense.id, "debit": writedown, "credit": 0, "description": "NRV write-down"},
               {"account_id": provision.id, "debit": 0, "credit": writedown, "description": item.code}],
    )
    write_audit(db, action="INVENTORY_NRV_WRITEDOWN", entity_type="ITEM", entity_id=item.id,
                user_id=user.id, company_id=data.company_id,
                after={"unit_cost": str(unit_cost), "nrv": str(nrv_unit), "writedown": str(writedown), "journal": journal.number})
    db.commit()
    return {"item_code": item.code, "quantity": qty, "unit_cost": unit_cost, "nrv_per_unit": nrv_unit,
            "writedown": writedown, "journal_number": journal.number}
