from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Session, selectinload

from app.api.pos import PosOrderIn, create_order, serialize_order
from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (
    BankAccount, Branch, CashierShift, DeliveryPlatform, Item, KitchenStation, KitchenTicket,
    KitchenTicketLine, MenuItem, MenuKitchenStation, OfflinePosTransaction, PlatformSettlementBatch,
    PlatformSettlementLine, PosControlLine, PosControlRequest, PosOrder, PosOrderLine,
    RestaurantReservation, RestaurantTable, RestaurantWasteRecord, StockMovement, User, Warehouse,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money, quantity, stock_balance
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/restaurant", tags=["Restaurant Operations RC13"])


class TableIn(BaseModel):
    company_id: int
    branch_id: int
    code: str = Field(min_length=1, max_length=30)
    name_ar: str = Field(min_length=1, max_length=150)
    name_en: str = Field(min_length=1, max_length=150)
    area: str | None = Field(default=None, max_length=80)
    capacity: int = Field(default=4, ge=1, le=50)


class TableStatusIn(BaseModel):
    status: str


class ReservationIn(BaseModel):
    company_id: int
    branch_id: int
    table_id: int | None = None
    customer_name: str = Field(min_length=1, max_length=200)
    mobile: str | None = Field(default=None, max_length=30)
    guest_count: int = Field(ge=1, le=100)
    reservation_at: datetime
    duration_minutes: int = Field(default=90, ge=15, le=480)
    notes: str | None = Field(default=None, max_length=500)


class ReservationStatusIn(BaseModel):
    status: str


class CashierShiftOpenIn(BaseModel):
    company_id: int
    branch_id: int
    bank_account_id: int
    business_date: date
    opening_balance: Decimal = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class CashierShiftCloseIn(BaseModel):
    counted_cash: Decimal = Field(ge=0)
    notes: str | None = Field(default=None, max_length=500)


class KitchenStationIn(BaseModel):
    company_id: int
    branch_id: int
    code: str = Field(min_length=1, max_length=30)
    name_ar: str = Field(min_length=1, max_length=150)
    name_en: str = Field(min_length=1, max_length=150)
    sequence: int = Field(default=1, ge=1)


class MenuStationIn(BaseModel):
    menu_item_id: int
    kitchen_station_id: int


class KitchenStatusIn(BaseModel):
    status: str


class ControlLineIn(BaseModel):
    pos_order_line_id: int
    quantity: Decimal = Field(gt=0)


class ControlRequestIn(BaseModel):
    request_type: str
    reason: str = Field(min_length=3, max_length=500)
    refund_bank_account_id: int | None = None
    restore_inventory: bool = False
    lines: list[ControlLineIn] = Field(default_factory=list)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SettlementBatchIn(BaseModel):
    company_id: int
    platform_id: int
    bank_account_id: int
    settlement_reference: str = Field(min_length=1, max_length=100)
    settlement_date: date
    period_start: date
    period_end: date
    order_ids: list[int] = Field(min_length=1)
    other_fees: Decimal = Field(default=0, ge=0)
    received_net: Decimal = Field(ge=0)


class WasteIn(BaseModel):
    company_id: int
    branch_id: int
    warehouse_id: int
    item_id: int
    waste_date: date
    quantity: Decimal = Field(gt=0)
    reason_code: str = Field(min_length=2, max_length=40)
    reason: str = Field(min_length=3, max_length=500)


class OfflineSyncIn(BaseModel):
    company_id: int
    device_id: str = Field(min_length=1, max_length=100)
    client_transaction_id: str = Field(min_length=1, max_length=120)
    order: PosOrderIn


def _number(db: Session, model, company_id: int, prefix: str) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{utc_now():%y%m}-{int(count) + 1:05d}"


def _branch(db: Session, company_id: int, branch_id: int) -> Branch:
    row = db.scalar(select(Branch).where(Branch.id == branch_id, Branch.company_id == company_id, Branch.active.is_(True)))
    if not row:
        raise HTTPException(404, "Branch not found")
    return row


def _table_dict(row: RestaurantTable) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "branch_id": row.branch_id, "code": row.code,
        "name_ar": row.name_ar, "name_en": row.name_en, "area": row.area, "capacity": row.capacity,
        "status": row.status, "active": row.active,
    }


def _reservation_dict(row: RestaurantReservation) -> dict:
    return {
        "id": row.id, "number": row.number, "branch_id": row.branch_id, "table_id": row.table_id,
        "table_code": row.table.code if row.table else None, "customer_name": row.customer_name,
        "mobile": row.mobile, "guest_count": row.guest_count, "reservation_at": row.reservation_at,
        "duration_minutes": row.duration_minutes, "status": row.status, "notes": row.notes,
    }


@router.post("/tables", status_code=201)
def create_table(data: TableIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.tables.manage")
    _branch(db, data.company_id, data.branch_id)
    if db.scalar(select(RestaurantTable).where(RestaurantTable.company_id == data.company_id, RestaurantTable.branch_id == data.branch_id, RestaurantTable.code == data.code)):
        raise HTTPException(409, "Table code already exists")
    row = RestaurantTable(**data.model_dump(), status="AVAILABLE", active=True)
    db.add(row); db.flush()
    write_audit(db, action="RESTAURANT_TABLE_CREATED", entity_type="RESTAURANT_TABLE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "capacity": row.capacity})
    db.commit()
    return _table_dict(row)


@router.get("/tables")
def list_tables(company_id: int, branch_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    query = select(RestaurantTable).where(RestaurantTable.company_id == company_id, RestaurantTable.active.is_(True)).where(branch_scope_condition(db, user, company_id, RestaurantTable) if branch_scope_condition(db, user, company_id, RestaurantTable) is not None else sa_true())
    if branch_id is not None:
        query = query.where(RestaurantTable.branch_id == branch_id)
    rows = db.scalars(query.order_by(RestaurantTable.branch_id, RestaurantTable.code)).all()
    return [_table_dict(r) for r in rows]


@router.patch("/tables/{table_id}/status")
def update_table_status(table_id: int, data: TableStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(RestaurantTable, table_id)
    if not row:
        raise HTTPException(404, "Table not found")
    ensure_permission(db, user, row.company_id, "pos.tables.manage")
    status = data.status.upper()
    if status not in {"AVAILABLE", "RESERVED", "OCCUPIED", "OUT_OF_SERVICE"}:
        raise HTTPException(422, "Unsupported table status")
    row.status = status
    write_audit(db, action="RESTAURANT_TABLE_STATUS_CHANGED", entity_type="RESTAURANT_TABLE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": status})
    db.commit()
    return _table_dict(row)


@router.post("/reservations", status_code=201)
def create_reservation(data: ReservationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.reservations.manage")
    _branch(db, data.company_id, data.branch_id)
    table = None
    if data.table_id is not None:
        table = db.scalar(select(RestaurantTable).where(RestaurantTable.id == data.table_id, RestaurantTable.company_id == data.company_id, RestaurantTable.branch_id == data.branch_id, RestaurantTable.active.is_(True)))
        if not table:
            raise HTTPException(404, "Table not found")
        if data.guest_count > table.capacity:
            raise HTTPException(422, "Guest count exceeds table capacity")
        requested_end = data.reservation_at + timedelta(minutes=data.duration_minutes)
        reservations = db.scalars(select(RestaurantReservation).where(RestaurantReservation.table_id == table.id, RestaurantReservation.status.in_(["BOOKED", "SEATED"]))).all()
        for existing in reservations:
            existing_end = existing.reservation_at + timedelta(minutes=existing.duration_minutes)
            if data.reservation_at < existing_end and requested_end > existing.reservation_at:
                raise HTTPException(409, "Table has an overlapping reservation")
    row = RestaurantReservation(
        company_id=data.company_id, branch_id=data.branch_id, table_id=data.table_id,
        number=_number(db, RestaurantReservation, data.company_id, "RES"), customer_name=data.customer_name,
        mobile=data.mobile, guest_count=data.guest_count, reservation_at=data.reservation_at,
        duration_minutes=data.duration_minutes, status="BOOKED", notes=data.notes, created_by=user.id,
    )
    db.add(row); db.flush()
    if table and table.status == "AVAILABLE":
        table.status = "RESERVED"
    write_audit(db, action="RESTAURANT_RESERVATION_CREATED", entity_type="RESTAURANT_RESERVATION", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": row.number, "guest_count": row.guest_count})
    db.commit()
    return _reservation_dict(row)


@router.get("/reservations")
def list_reservations(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    query = select(RestaurantReservation).where(RestaurantReservation.company_id == company_id).options(selectinload(RestaurantReservation.table))
    if status:
        query = query.where(RestaurantReservation.status == status.upper())
    rows = db.scalars(query.order_by(RestaurantReservation.reservation_at.desc())).all()
    return [_reservation_dict(r) for r in rows]


@router.patch("/reservations/{reservation_id}/status")
def update_reservation_status(reservation_id: int, data: ReservationStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(RestaurantReservation, reservation_id)
    if not row:
        raise HTTPException(404, "Reservation not found")
    ensure_permission(db, user, row.company_id, "pos.reservations.manage")
    status = data.status.upper()
    if status not in {"BOOKED", "SEATED", "COMPLETED", "CANCELLED", "NO_SHOW"}:
        raise HTTPException(422, "Unsupported reservation status")
    row.status = status
    if status == "SEATED":
        row.seated_at = utc_now()
        if row.table:
            row.table.status = "OCCUPIED"
    elif status in {"COMPLETED", "CANCELLED", "NO_SHOW"}:
        row.completed_at = utc_now()
        if row.table and row.table.status != "OUT_OF_SERVICE":
            row.table.status = "AVAILABLE"
    db.commit()
    return _reservation_dict(row)


@router.post("/cashier-shifts/open", status_code=201)
def open_cashier_shift(data: CashierShiftOpenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.shifts.manage")
    _branch(db, data.company_id, data.branch_id)
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not bank:
        raise HTTPException(404, "Bank account not found")
    existing = db.scalar(select(CashierShift).where(CashierShift.company_id == data.company_id, CashierShift.branch_id == data.branch_id, CashierShift.opened_by == user.id, CashierShift.status == "OPEN"))
    if existing:
        raise HTTPException(409, "User already has an open cashier shift")
    row = CashierShift(
        company_id=data.company_id, branch_id=data.branch_id, bank_account_id=data.bank_account_id,
        number=_number(db, CashierShift, data.company_id, "SHIFT"), business_date=data.business_date,
        opening_balance=money(data.opening_balance), expected_cash=money(data.opening_balance),
        status="OPEN", notes=data.notes, opened_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="CASHIER_SHIFT_OPENED", entity_type="CASHIER_SHIFT", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": row.number, "opening_balance": str(row.opening_balance)})
    db.commit()
    return _shift_dict(row)


def _cash_refunds(db: Session, shift_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(PosControlRequest.refund_total), 0))
        .join(PosOrder, PosOrder.id == PosControlRequest.pos_order_id)
        .where(PosOrder.cashier_shift_id == shift_id, PosOrder.payment_channel == "CASH", PosControlRequest.status == "APPROVED_POSTED")
    )
    return money(value or 0)


def _shift_dict(row: CashierShift) -> dict:
    return {
        "id": row.id, "number": row.number, "branch_id": row.branch_id, "business_date": row.business_date,
        "opening_balance": row.opening_balance, "cash_sales": row.cash_sales, "cash_refunds": row.cash_refunds,
        "expected_cash": row.expected_cash, "counted_cash": row.counted_cash, "variance": row.variance,
        "status": row.status, "notes": row.notes, "opened_by": row.opened_by, "closed_by": row.closed_by,
        "approved_by": row.approved_by,
    }


@router.get("/cashier-shifts")
def list_cashier_shifts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(CashierShift).where(CashierShift.company_id == company_id).where(branch_scope_condition(db, user, company_id, CashierShift) if branch_scope_condition(db, user, company_id, CashierShift) is not None else sa_true()).order_by(CashierShift.id.desc()).where(branch_scope_condition(db, user, company_id, CashierShift) if branch_scope_condition(db, user, company_id, CashierShift) is not None else sa_true())).all()
    return [_shift_dict(r) for r in rows]


@router.post("/cashier-shifts/{shift_id}/submit-close")
def submit_cashier_close(shift_id: int, data: CashierShiftCloseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CashierShift, shift_id)
    if not row:
        raise HTTPException(404, "Cashier shift not found")
    ensure_permission(db, user, row.company_id, "pos.shifts.manage")
    if row.status != "OPEN":
        raise HTTPException(409, "Cashier shift is not open")
    if row.opened_by != user.id:
        raise HTTPException(403, "Only the opening cashier may submit the shift")
    cash_sales = db.scalar(select(func.coalesce(func.sum(PosOrder.total), 0)).where(PosOrder.cashier_shift_id == row.id, PosOrder.payment_channel == "CASH", PosOrder.status.notin_(["VOIDED", "REFUNDED"]))) or 0
    refunds = _cash_refunds(db, row.id)
    row.cash_sales = money(cash_sales); row.cash_refunds = refunds
    row.expected_cash = money(row.opening_balance + row.cash_sales - refunds)
    row.counted_cash = money(data.counted_cash); row.variance = money(row.counted_cash - row.expected_cash)
    row.notes = data.notes or row.notes; row.closed_by = user.id; row.submitted_at = utc_now(); row.status = "CLOSING_SUBMITTED"
    write_audit(db, action="CASHIER_SHIFT_CLOSE_SUBMITTED", entity_type="CASHIER_SHIFT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"expected": str(row.expected_cash), "counted": str(row.counted_cash), "variance": str(row.variance)})
    db.commit()
    return _shift_dict(row)


@router.post("/cashier-shifts/{shift_id}/approve")
def approve_cashier_close(shift_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CashierShift, shift_id)
    if not row:
        raise HTTPException(404, "Cashier shift not found")
    ensure_permission(db, user, row.company_id, "pos.shifts.approve")
    if row.status != "CLOSING_SUBMITTED":
        raise HTTPException(409, "Cashier shift is not awaiting approval")
    if user.id in {row.opened_by, row.closed_by}:
        raise HTTPException(409, "Maker-checker violation")
    if row.variance and row.variance != 0 and not row.notes:
        raise HTTPException(422, "Variance requires documented notes")
    row.status = "CLOSED_WITH_VARIANCE" if row.variance else "CLOSED"
    row.approved_by = user.id; row.approved_at = utc_now()
    db.commit()
    return _shift_dict(row)


@router.post("/kitchen/stations", status_code=201)
def create_kitchen_station(data: KitchenStationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.kds.manage")
    _branch(db, data.company_id, data.branch_id)
    if db.scalar(select(KitchenStation).where(KitchenStation.company_id == data.company_id, KitchenStation.branch_id == data.branch_id, KitchenStation.code == data.code)):
        raise HTTPException(409, "Kitchen station code already exists")
    row = KitchenStation(**data.model_dump(), active=True)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "sequence": row.sequence}


@router.get("/kitchen/stations")
def list_kitchen_stations(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(KitchenStation).where(KitchenStation.company_id == company_id, KitchenStation.active.is_(True)).order_by(KitchenStation.sequence, KitchenStation.code).where(branch_scope_condition(db, user, company_id, KitchenStation) if branch_scope_condition(db, user, company_id, KitchenStation) is not None else sa_true())).all()
    return [{"id": r.id, "branch_id": r.branch_id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "sequence": r.sequence} for r in rows]


@router.post("/kitchen/menu-station")
def assign_menu_station(data: MenuStationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    menu = db.get(MenuItem, data.menu_item_id); station = db.get(KitchenStation, data.kitchen_station_id)
    if not menu or not station or menu.company_id != station.company_id:
        raise HTTPException(404, "Menu item or kitchen station not found")
    ensure_permission(db, user, menu.company_id, "pos.kds.manage")
    row = db.scalar(select(MenuKitchenStation).where(MenuKitchenStation.menu_item_id == menu.id))
    if row:
        row.kitchen_station_id = station.id
    else:
        row = MenuKitchenStation(menu_item_id=menu.id, kitchen_station_id=station.id); db.add(row)
    db.commit()
    return {"menu_item_id": menu.id, "kitchen_station_id": station.id}


def _ticket_dict(row: KitchenTicket) -> dict:
    return {
        "id": row.id, "number": row.number, "order_id": row.pos_order_id,
        "order_number": row.order.number if row.order else None, "station_id": row.kitchen_station_id,
        "station_code": row.station.code if row.station else None, "status": row.status,
        "priority": row.priority, "created_at": row.created_at,
        "lines": [{"id": line.id, "menu_item": line.order_line.menu_item.code, "name_ar": line.order_line.menu_item.name_ar, "name_en": line.order_line.menu_item.name_en, "quantity": line.quantity, "status": line.status} for line in row.lines],
    }


@router.get("/kitchen/tickets")
def list_kitchen_tickets(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    query = select(KitchenTicket).where(KitchenTicket.company_id == company_id).where(branch_scope_condition(db, user, company_id, KitchenTicket) if branch_scope_condition(db, user, company_id, KitchenTicket) is not None else sa_true()).options(selectinload(KitchenTicket.lines).selectinload(KitchenTicketLine.order_line).selectinload(PosOrderLine.menu_item))
    if status:
        query = query.where(KitchenTicket.status == status.upper())
    rows = db.scalars(query.order_by(KitchenTicket.priority.desc(), KitchenTicket.created_at)).all()
    return [_ticket_dict(r) for r in rows]


@router.patch("/kitchen/tickets/{ticket_id}/status")
def update_kitchen_ticket(ticket_id: int, data: KitchenStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(KitchenTicket).where(KitchenTicket.id == ticket_id).options(selectinload(KitchenTicket.lines)))
    if not row:
        raise HTTPException(404, "Kitchen ticket not found")
    ensure_permission(db, user, row.company_id, "pos.kds.manage")
    status = data.status.upper()
    transitions = {"NEW": "ACCEPTED", "ACCEPTED": "PREPARING", "PREPARING": "READY", "READY": "SERVED"}
    if status == "CANCELLED":
        if row.status in {"READY", "SERVED"}:
            raise HTTPException(409, "Prepared or served ticket cannot be cancelled")
    elif transitions.get(row.status) != status:
        raise HTTPException(409, f"Invalid KDS transition from {row.status} to {status}")
    row.status = status
    now = utc_now()
    if status == "ACCEPTED": row.accepted_at = now
    elif status == "PREPARING": row.started_at = now
    elif status == "READY": row.ready_at = now
    elif status == "SERVED": row.served_at = now
    for line in row.lines:
        line.status = status
    db.commit()
    return _ticket_dict(row)


@router.post("/orders/{order_id}/complete-service")
def complete_table_service(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(PosOrder, order_id)
    if not order:
        raise HTTPException(404, "POS order not found")
    ensure_permission(db, user, order.company_id, "pos.sell")
    open_tickets = db.scalar(select(func.count(KitchenTicket.id)).where(KitchenTicket.pos_order_id == order.id, KitchenTicket.status.notin_(["SERVED", "CANCELLED"]))) or 0
    if open_tickets:
        raise HTTPException(409, "Kitchen tickets are not complete")
    if order.table_id:
        table = db.get(RestaurantTable, order.table_id)
        if table and table.status != "OUT_OF_SERVICE": table.status = "AVAILABLE"
    if order.reservation_id:
        reservation = db.get(RestaurantReservation, order.reservation_id)
        if reservation:
            reservation.status = "COMPLETED"; reservation.completed_at = utc_now()
    db.commit()
    return {"order_id": order.id, "service_status": "COMPLETED", "table_released": bool(order.table_id)}


def _control_dict(row: PosControlRequest) -> dict:
    return {
        "id": row.id, "number": row.number, "order_id": row.pos_order_id, "order_number": row.order.number if row.order else None,
        "request_type": row.request_type, "restore_inventory": row.restore_inventory, "reason": row.reason,
        "refund_net": row.refund_net, "refund_vat": row.refund_vat, "refund_total": row.refund_total,
        "restored_food_cost": row.restored_food_cost, "status": row.status, "requested_by": row.requested_by,
        "approved_by": row.approved_by, "rejection_reason": row.rejection_reason,
        "lines": [{"pos_order_line_id": x.pos_order_line_id, "quantity": x.quantity, "refund_total": x.refund_total, "restored_food_cost": x.restored_food_cost} for x in row.lines],
    }


@router.post("/orders/{order_id}/controls", status_code=201)
def create_control_request(order_id: int, data: ControlRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.scalar(select(PosOrder).where(PosOrder.id == order_id).options(selectinload(PosOrder.lines).selectinload(PosOrderLine.menu_item)))
    if not order:
        raise HTTPException(404, "POS order not found")
    ensure_permission(db, user, order.company_id, "pos.controls.request")
    request_type = data.request_type.upper()
    if request_type not in {"VOID", "RETURN"}:
        raise HTTPException(422, "Unsupported control request type")
    if order.status in {"VOIDED", "REFUNDED"}:
        raise HTTPException(409, "Order has already been fully reversed")
    requested = {line.pos_order_line_id: quantity(line.quantity) for line in data.lines}
    if request_type == "VOID" and not requested:
        requested = {line.id: quantity(line.quantity) for line in order.lines}
    if not requested:
        raise HTTPException(422, "Return lines are required")
    order_line_by_id = {line.id: line for line in order.lines}
    approved_rows = db.execute(
        select(PosControlLine.pos_order_line_id, func.coalesce(func.sum(PosControlLine.quantity), 0))
        .join(PosControlRequest, PosControlRequest.id == PosControlLine.control_request_id)
        .where(PosControlRequest.pos_order_id == order.id, PosControlRequest.status == "APPROVED_POSTED")
        .group_by(PosControlLine.pos_order_line_id)
    ).all()
    already = {line_id: quantity(value) for line_id, value in approved_rows}
    control = PosControlRequest(
        company_id=order.company_id, pos_order_id=order.id, number=_number(db, PosControlRequest, order.company_id, "PCR"),
        request_type=request_type, reason=data.reason, refund_bank_account_id=data.refund_bank_account_id,
        restore_inventory=data.restore_inventory, status="SUBMITTED", requested_by=user.id,
    )
    refund_net = Decimal("0"); refund_vat = Decimal("0"); refund_total = Decimal("0"); restore_cost = Decimal("0")
    for line_id, qty in requested.items():
        original = order_line_by_id.get(line_id)
        if not original:
            raise HTTPException(404, "POS order line not found")
        remaining = quantity(original.quantity - already.get(line_id, Decimal("0")))
        if qty > remaining:
            raise HTTPException(422, "Requested quantity exceeds refundable quantity")
        ratio = qty / original.quantity
        line_net = money(original.net_amount * ratio); line_vat = money(original.vat_amount * ratio)
        line_total = money(line_net + line_vat); line_cost = money(original.food_cost * ratio) if data.restore_inventory else Decimal("0")
        control.lines.append(PosControlLine(pos_order_line_id=line_id, quantity=qty, refund_net=line_net, refund_vat=line_vat, refund_total=line_total, restored_food_cost=line_cost))
        refund_net += line_net; refund_vat += line_vat; refund_total += line_total; restore_cost += line_cost
    control.refund_net = money(refund_net); control.refund_vat = money(refund_vat); control.refund_total = money(refund_total); control.restored_food_cost = money(restore_cost)
    db.add(control); db.flush()
    write_audit(db, action="POS_CONTROL_REQUESTED", entity_type="POS_CONTROL_REQUEST", entity_id=control.id, user_id=user.id, company_id=order.company_id, after={"type": request_type, "refund_total": str(control.refund_total), "restore_inventory": data.restore_inventory})
    db.commit()
    return _control_dict(control)


@router.get("/controls")
def list_controls(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(PosControlRequest).where(PosControlRequest.company_id == company_id).options(selectinload(PosControlRequest.lines), selectinload(PosControlRequest.order)).order_by(PosControlRequest.id.desc())).all()
    return [_control_dict(r) for r in rows]


@router.post("/controls/{control_id}/reject")
def reject_control(control_id: int, data: RejectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(PosControlRequest, control_id)
    if not row:
        raise HTTPException(404, "Control request not found")
    ensure_permission(db, user, row.company_id, "pos.controls.approve")
    if row.status != "SUBMITTED": raise HTTPException(409, "Control request is not submitted")
    if row.requested_by == user.id: raise HTTPException(409, "Maker-checker violation")
    row.status = "REJECTED"; row.rejected_by = user.id; row.rejected_at = utc_now(); row.rejection_reason = data.reason
    db.commit()
    return _control_dict(row)


@router.post("/controls/{control_id}/approve")
def approve_control(control_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(PosControlRequest).where(PosControlRequest.id == control_id).options(selectinload(PosControlRequest.lines).selectinload(PosControlLine.order_line).selectinload(PosOrderLine.menu_item), selectinload(PosControlRequest.order)))
    if not row:
        raise HTTPException(404, "Control request not found")
    ensure_permission(db, user, row.company_id, "pos.controls.approve")
    if row.status != "SUBMITTED": raise HTTPException(409, "Control request is not submitted")
    if row.requested_by == user.id: raise HTTPException(409, "Maker-checker violation")
    order = row.order
    refund_account_id = None
    if row.refund_bank_account_id:
        bank = db.scalar(select(BankAccount).where(BankAccount.id == row.refund_bank_account_id, BankAccount.company_id == row.company_id, BankAccount.active.is_(True)))
        if not bank: raise HTTPException(404, "Refund bank account not found")
        refund_account_id = bank.gl_account_id
    elif order.payment_channel in {"CASH", "CARD"} and order.bank_account_id:
        bank = db.get(BankAccount, order.bank_account_id); refund_account_id = bank.gl_account_id if bank else None
    elif order.payment_channel == "DELIVERY" and order.status == "PENDING_SETTLEMENT":
        refund_account_id = get_account(db, row.company_id, "116010").id
    if refund_account_id is None:
        raise HTTPException(422, "Refund bank account is required")
    revenue = get_account(db, row.company_id, "411010"); output_vat = get_account(db, row.company_id, "212010")
    sale_reversal = create_posted_journal(
        db, company_id=row.company_id, user_id=user.id, posting_date=date.today(), reference=row.number,
        description=f"POS {row.request_type.lower()} {order.number}",
        lines=[
            {"account_id": revenue.id, "debit": row.refund_net, "credit": 0, "branch_id": order.branch_id},
            {"account_id": output_vat.id, "debit": row.refund_vat, "credit": 0, "branch_id": order.branch_id},
            {"account_id": refund_account_id, "debit": 0, "credit": row.refund_total, "branch_id": order.branch_id},
        ],
        cash_flow_activity="OPERATING" if order.payment_channel in {"CASH", "CARD"} else None,
        cash_flow_kind="CUSTOMER_REFUNDS" if order.payment_channel in {"CASH", "CARD"} else None,
    )
    cogs_reversal = None
    if row.restore_inventory and row.restored_food_cost > 0:
        inventory = get_account(db, row.company_id, "113010"); cogs = get_account(db, row.company_id, "511010")
        cogs_reversal = create_posted_journal(
            db, company_id=row.company_id, user_id=user.id, posting_date=date.today(), reference=row.number,
            description=f"POS inventory restoration {order.number}",
            lines=[
                {"account_id": inventory.id, "debit": row.restored_food_cost, "credit": 0, "branch_id": order.branch_id},
                {"account_id": cogs.id, "debit": 0, "credit": row.restored_food_cost, "branch_id": order.branch_id},
            ],
        )
        for control_line in row.lines:
            menu = control_line.order_line.menu_item
            for recipe_line in menu.recipe.lines:
                restored_qty = quantity(recipe_line.quantity / menu.recipe.output_quantity * control_line.quantity)
                restored_cost = money(restored_qty * recipe_line.component_item.standard_cost)
                db.add(StockMovement(
                    company_id=row.company_id, warehouse_id=order.warehouse_id, item_id=recipe_line.component_item_id,
                    movement_date=date.today(), movement_type="POS_RETURN_RESTORE", quantity=restored_qty,
                    unit_cost=recipe_line.component_item.standard_cost, total_cost=restored_cost,
                    reference_type="POS_CONTROL_REQUEST", reference_id=row.id, journal_id=cogs_reversal.id, created_by=user.id,
                ))
    previous_refunded = db.scalar(select(func.coalesce(func.sum(PosControlRequest.refund_total), 0)).where(PosControlRequest.pos_order_id == order.id, PosControlRequest.status == "APPROVED_POSTED")) or 0
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now()
    row.reversal_sale_journal_id = sale_reversal.id; row.reversal_cogs_journal_id = cogs_reversal.id if cogs_reversal else None
    total_refunded = money(previous_refunded + row.refund_total)
    if total_refunded >= order.total:
        order.status = "VOIDED" if row.request_type == "VOID" else "REFUNDED"
        if order.table_id:
            table = db.get(RestaurantTable, order.table_id)
            if table and table.status != "OUT_OF_SERVICE": table.status = "AVAILABLE"
        for ticket in db.scalars(select(KitchenTicket).where(KitchenTicket.pos_order_id == order.id, KitchenTicket.status.in_(["NEW", "ACCEPTED", "PREPARING"]))).all():
            if row.restore_inventory: ticket.status = "CANCELLED"
    else:
        order.status = "PARTIALLY_REFUNDED"
    write_audit(db, action="POS_CONTROL_APPROVED_POSTED", entity_type="POS_CONTROL_REQUEST", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status, "refund_total": str(row.refund_total)})
    db.commit()
    return _control_dict(row)


def _settlement_dict(row: PlatformSettlementBatch) -> dict:
    return {
        "id": row.id, "settlement_reference": row.settlement_reference, "platform": row.platform.code if row.platform else None,
        "settlement_date": row.settlement_date, "period_start": row.period_start, "period_end": row.period_end,
        "gross_sales": row.gross_sales, "commission_amount": row.commission_amount, "other_fees": row.other_fees,
        "expected_net": row.expected_net, "received_net": row.received_net, "variance": row.variance,
        "status": row.status, "line_count": len(row.lines), "prepared_by": row.prepared_by,
        "reviewed_by": row.reviewed_by, "approved_by": row.approved_by,
    }


@router.post("/settlements", status_code=201)
def create_settlement_batch(data: SettlementBatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.settlements.manage")
    if data.period_end < data.period_start: raise HTTPException(422, "Invalid settlement period")
    platform = db.scalar(select(DeliveryPlatform).where(DeliveryPlatform.id == data.platform_id, DeliveryPlatform.company_id == data.company_id, DeliveryPlatform.active.is_(True)))
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
    if not platform or not bank: raise HTTPException(404, "Platform or bank account not found")
    if db.scalar(select(PlatformSettlementBatch).where(PlatformSettlementBatch.company_id == data.company_id, PlatformSettlementBatch.settlement_reference == data.settlement_reference)):
        raise HTTPException(409, "Settlement reference already exists")
    orders = db.scalars(select(PosOrder).where(PosOrder.id.in_(data.order_ids), PosOrder.company_id == data.company_id).options(selectinload(PosOrder.platform))).all()
    if len(orders) != len(set(data.order_ids)): raise HTTPException(404, "One or more POS orders were not found")
    batch = PlatformSettlementBatch(
        company_id=data.company_id, platform_id=platform.id, bank_account_id=bank.id,
        settlement_reference=data.settlement_reference, settlement_date=data.settlement_date,
        period_start=data.period_start, period_end=data.period_end, gross_sales=0, commission_amount=0,
        other_fees=money(data.other_fees), expected_net=0, received_net=money(data.received_net), variance=0,
        status="DRAFT", prepared_by=user.id,
    )
    gross = Decimal("0"); commission = Decimal("0")
    for order in orders:
        if order.payment_channel != "DELIVERY" or order.platform_id != platform.id or order.status != "PENDING_SETTLEMENT":
            raise HTTPException(409, "Orders must be pending settlements for the selected platform")
        if not (data.period_start <= order.order_date <= data.period_end):
            raise HTTPException(422, "Order date is outside the settlement period")
        line_commission = money(order.total * platform.commission_rate / Decimal("100")); line_net = money(order.total - line_commission)
        batch.lines.append(PlatformSettlementLine(pos_order_id=order.id, gross_amount=order.total, commission_amount=line_commission, expected_net=line_net))
        gross += order.total; commission += line_commission
    batch.gross_sales = money(gross); batch.commission_amount = money(commission)
    batch.expected_net = money(batch.gross_sales - batch.commission_amount - batch.other_fees)
    batch.variance = money(batch.received_net - batch.expected_net)
    db.add(batch); db.flush()
    write_audit(db, action="PLATFORM_SETTLEMENT_PREPARED", entity_type="PLATFORM_SETTLEMENT", entity_id=batch.id, user_id=user.id, company_id=data.company_id, after={"reference": batch.settlement_reference, "variance": str(batch.variance)})
    db.commit()
    return _settlement_dict(batch)


@router.get("/settlements")
def list_settlements(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(PlatformSettlementBatch).where(PlatformSettlementBatch.company_id == company_id).options(selectinload(PlatformSettlementBatch.lines), selectinload(PlatformSettlementBatch.platform)).order_by(PlatformSettlementBatch.id.desc())).all()
    return [_settlement_dict(r) for r in rows]


@router.post("/settlements/{batch_id}/review")
def review_settlement(batch_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(PlatformSettlementBatch).where(PlatformSettlementBatch.id == batch_id).options(selectinload(PlatformSettlementBatch.lines)))
    if not row: raise HTTPException(404, "Settlement batch not found")
    ensure_permission(db, user, row.company_id, "pos.settlements.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Settlement batch is not draft")
    if row.prepared_by == user.id: raise HTTPException(409, "Maker-checker violation")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit()
    return _settlement_dict(row)


@router.post("/settlements/{batch_id}/approve")
def approve_settlement(batch_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(PlatformSettlementBatch).where(PlatformSettlementBatch.id == batch_id).options(selectinload(PlatformSettlementBatch.lines).selectinload(PlatformSettlementLine.order), selectinload(PlatformSettlementBatch.platform)))
    if not row: raise HTTPException(404, "Settlement batch not found")
    ensure_permission(db, user, row.company_id, "pos.settlements.approve")
    if row.status != "REVIEWED": raise HTTPException(409, "Settlement batch is not reviewed")
    if user.id in {row.prepared_by, row.reviewed_by}: raise HTTPException(409, "Three-user segregation violation")
    if row.variance != 0: raise HTTPException(422, "Settlement variance must be zero before approval")
    bank = db.get(BankAccount, row.bank_account_id)
    receivable = get_account(db, row.company_id, "116010"); commission_expense = get_account(db, row.company_id, "616010")
    journal = create_posted_journal(
        db, company_id=row.company_id, user_id=user.id, posting_date=row.settlement_date,
        reference=row.settlement_reference, description=f"Platform settlement {row.settlement_reference}",
        lines=[
            {"account_id": bank.gl_account_id, "debit": row.received_net, "credit": 0},
            {"account_id": commission_expense.id, "debit": money(row.commission_amount + row.other_fees), "credit": 0},
            {"account_id": receivable.id, "debit": 0, "credit": row.gross_sales},
        ], cash_flow_activity="OPERATING", cash_flow_kind="CUSTOMER_RECEIPTS",
    )
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.journal_id = journal.id
    for line in row.lines:
        line.order.status = "SETTLED"; line.order.settlement_journal_id = journal.id
    write_audit(db, action="PLATFORM_SETTLEMENT_APPROVED_POSTED", entity_type="PLATFORM_SETTLEMENT", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"journal": journal.number, "received_net": str(row.received_net)})
    db.commit()
    return _settlement_dict(row)


def _waste_dict(row: RestaurantWasteRecord) -> dict:
    return {
        "id": row.id, "number": row.number, "waste_date": row.waste_date, "branch_id": row.branch_id,
        "warehouse_id": row.warehouse_id, "item_id": row.item_id, "item_code": row.item.code if row.item else None,
        "quantity": row.quantity, "unit_cost": row.unit_cost, "total_cost": row.total_cost,
        "reason_code": row.reason_code, "reason": row.reason, "status": row.status,
        "prepared_by": row.prepared_by, "approved_by": row.approved_by,
    }


@router.post("/waste", status_code=201)
def create_waste(data: WasteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.waste.manage")
    _branch(db, data.company_id, data.branch_id)
    warehouse = db.scalar(select(Warehouse).where(Warehouse.id == data.warehouse_id, Warehouse.company_id == data.company_id, Warehouse.active.is_(True)))
    item = db.scalar(select(Item).where(Item.id == data.item_id, Item.company_id == data.company_id, Item.active.is_(True)))
    if not warehouse or not item: raise HTTPException(404, "Warehouse or item not found")
    qty = quantity(data.quantity); available = stock_balance(db, data.company_id, warehouse.id, item.id)
    if available < qty: raise HTTPException(422, "Insufficient stock for waste record")
    row = RestaurantWasteRecord(
        company_id=data.company_id, branch_id=data.branch_id, warehouse_id=warehouse.id, item_id=item.id,
        number=_number(db, RestaurantWasteRecord, data.company_id, "WST"), waste_date=data.waste_date,
        quantity=qty, unit_cost=item.standard_cost, total_cost=money(qty * item.standard_cost),
        reason_code=data.reason_code.upper(), reason=data.reason, status="SUBMITTED", prepared_by=user.id,
    )
    db.add(row); db.commit(); db.refresh(row)
    return _waste_dict(row)


@router.get("/waste")
def list_waste(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(RestaurantWasteRecord).where(RestaurantWasteRecord.company_id == company_id).options(selectinload(RestaurantWasteRecord.item)).order_by(RestaurantWasteRecord.id.desc()).where(branch_scope_condition(db, user, company_id, RestaurantWasteRecord) if branch_scope_condition(db, user, company_id, RestaurantWasteRecord) is not None else sa_true())).all()
    return [_waste_dict(r) for r in rows]


@router.post("/waste/{waste_id}/approve")
def approve_waste(waste_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(RestaurantWasteRecord).where(RestaurantWasteRecord.id == waste_id).options(selectinload(RestaurantWasteRecord.item)))
    if not row: raise HTTPException(404, "Waste record not found")
    ensure_permission(db, user, row.company_id, "pos.waste.approve")
    if row.status != "SUBMITTED": raise HTTPException(409, "Waste record is not submitted")
    if row.prepared_by == user.id: raise HTTPException(409, "Maker-checker violation")
    if stock_balance(db, row.company_id, row.warehouse_id, row.item_id) < row.quantity:
        raise HTTPException(422, "Insufficient stock for waste posting")
    waste_expense = get_account(db, row.company_id, "624070"); inventory = get_account(db, row.company_id, "113010")
    journal = create_posted_journal(
        db, company_id=row.company_id, user_id=user.id, posting_date=row.waste_date, reference=row.number,
        description=f"Restaurant waste {row.number}",
        lines=[
            {"account_id": waste_expense.id, "debit": row.total_cost, "credit": 0, "branch_id": row.branch_id},
            {"account_id": inventory.id, "debit": 0, "credit": row.total_cost, "branch_id": row.branch_id},
        ],
    )
    db.add(StockMovement(
        company_id=row.company_id, warehouse_id=row.warehouse_id, item_id=row.item_id,
        movement_date=row.waste_date, movement_type="RESTAURANT_WASTE", quantity=-row.quantity,
        unit_cost=row.unit_cost, total_cost=-row.total_cost, reference_type="RESTAURANT_WASTE",
        reference_id=row.id, journal_id=journal.id, created_by=user.id,
    ))
    row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.journal_id = journal.id
    write_audit(db, action="RESTAURANT_WASTE_APPROVED_POSTED", entity_type="RESTAURANT_WASTE", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"total_cost": str(row.total_cost), "journal": journal.number})
    db.commit()
    return _waste_dict(row)


@router.post("/offline/sync")
def sync_offline_transaction(data: OfflineSyncIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.offline.sync")
    if data.order.company_id != data.company_id:
        raise HTTPException(422, "Order company does not match sync company")
    canonical = json.dumps(data.order.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.scalar(select(OfflinePosTransaction).where(OfflinePosTransaction.company_id == data.company_id, OfflinePosTransaction.device_id == data.device_id, OfflinePosTransaction.client_transaction_id == data.client_transaction_id))
    if existing:
        if existing.payload_hash != payload_hash:
            existing.status = "CONFLICT"; existing.conflict_reason = "Same client transaction ID has a different payload"; db.commit()
            raise HTTPException(409, existing.conflict_reason)
        if existing.status == "PROCESSED" and existing.pos_order_id:
            order = db.scalar(select(PosOrder).where(PosOrder.id == existing.pos_order_id).options(selectinload(PosOrder.lines).selectinload(PosOrderLine.menu_item), selectinload(PosOrder.platform)))
            return {"queue_id": existing.id, "status": existing.status, "order": serialize_order(order, True)}
        txn = existing
    else:
        txn = OfflinePosTransaction(company_id=data.company_id, device_id=data.device_id, client_transaction_id=data.client_transaction_id, payload_json=canonical, payload_hash=payload_hash, status="PENDING")
        db.add(txn); db.commit(); db.refresh(txn)
    order_payload = data.order.model_copy(update={"client_order_id": data.client_transaction_id, "source_device_id": data.device_id, "sync_status": "OFFLINE_SYNCED"})
    try:
        create_order(order_payload, user=user, db=db)
        order = db.scalar(select(PosOrder).where(PosOrder.company_id == data.company_id, PosOrder.client_order_id == data.client_transaction_id).options(selectinload(PosOrder.lines).selectinload(PosOrderLine.menu_item), selectinload(PosOrder.platform)))
        txn = db.get(OfflinePosTransaction, txn.id); txn.status = "PROCESSED"; txn.pos_order_id = order.id; txn.processed_at = utc_now(); txn.conflict_reason = None; db.commit()
        return {"queue_id": txn.id, "status": txn.status, "order": serialize_order(order, True)}
    except HTTPException as exc:
        txn = db.get(OfflinePosTransaction, txn.id); txn.status = "CONFLICT" if exc.status_code in {409, 422} else "FAILED"; txn.conflict_reason = str(exc.detail); db.commit()
        raise


@router.get("/offline/queue")
def list_offline_queue(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(OfflinePosTransaction).where(OfflinePosTransaction.company_id == company_id).order_by(OfflinePosTransaction.id.desc())).all()
    return [{"id": r.id, "device_id": r.device_id, "client_transaction_id": r.client_transaction_id, "status": r.status, "pos_order_id": r.pos_order_id, "conflict_reason": r.conflict_reason, "received_at": r.received_at, "processed_at": r.processed_at} for r in rows]


@router.get("/summary")
def restaurant_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    tables = db.scalars(select(RestaurantTable).where(RestaurantTable.company_id == company_id, RestaurantTable.active.is_(True))).all()
    tickets = db.scalars(select(KitchenTicket).where(KitchenTicket.company_id == company_id)).all()
    shifts = db.scalars(select(CashierShift).where(CashierShift.company_id == company_id)).all()
    settlements = db.scalars(select(PlatformSettlementBatch).where(PlatformSettlementBatch.company_id == company_id)).all()
    waste = db.scalar(select(func.coalesce(func.sum(RestaurantWasteRecord.total_cost), 0)).where(RestaurantWasteRecord.company_id == company_id, RestaurantWasteRecord.status == "APPROVED_POSTED")) or 0
    reservations = db.scalar(select(func.count(RestaurantReservation.id)).where(RestaurantReservation.company_id == company_id, RestaurantReservation.status.in_(["BOOKED", "SEATED"]))) or 0
    controls = db.scalar(select(func.count(PosControlRequest.id)).where(PosControlRequest.company_id == company_id, PosControlRequest.status == "SUBMITTED")) or 0
    return {
        "tables": len(tables), "available_tables": sum(1 for r in tables if r.status == "AVAILABLE"),
        "occupied_tables": sum(1 for r in tables if r.status == "OCCUPIED"), "active_reservations": reservations,
        "open_cashier_shifts": sum(1 for r in shifts if r.status in {"OPEN", "CLOSING_SUBMITTED"}),
        "kds_open_tickets": sum(1 for r in tickets if r.status not in {"SERVED", "CANCELLED"}),
        "pending_control_requests": controls,
        "settlement_variances": money(sum((abs(r.variance) for r in settlements if r.status != "APPROVED_POSTED"), Decimal("0"))),
        "approved_waste_cost": money(waste),
    }
