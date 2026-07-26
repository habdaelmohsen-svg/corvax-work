from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (
    BankAccount, BillOfMaterial, Branch, CashierShift, DeliveryPlatform, GymCafeProductProfile, GymDepartment, GymMembershipState, KitchenTicket,
    KitchenTicketLine, Member, MembershipContract, MenuItem, MenuKitchenStation, PosOrder, PosOrderLine,
    RestaurantReservation, RestaurantTable, StockMovement, TaxCode, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, get_warehouse, money, quantity, stock_balance
from app.services.posting import create_posted_journal
from app.services.tax import calculate_line, get_tax_code

router = APIRouter(prefix="/pos", tags=["Restaurant POS"])


class PlatformIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    commission_rate: Decimal = Field(ge=0, le=100)


class MenuItemIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    inventory_item_id: int
    recipe_bom_id: int
    selling_price: Decimal = Field(gt=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tax_code: str | None = Field(default=None, max_length=30)


class PosLineIn(BaseModel):
    menu_item_id: int
    quantity: Decimal = Field(gt=0)


class PosOrderIn(BaseModel):
    company_id: int
    order_date: date
    warehouse_id: int
    payment_channel: str
    bank_account_id: int | None = None
    platform_id: int | None = None
    branch_id: int | None = None
    business_unit: str = "RESTAURANT"
    gym_department_id: int | None = None
    gym_member_id: int | None = None
    cost_center_id: int | None = None
    order_type: str = "TAKEAWAY"
    table_id: int | None = None
    reservation_id: int | None = None
    cashier_shift_id: int | None = None
    guest_count: int = Field(default=1, ge=1)
    customer_name: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=500)
    client_order_id: str | None = Field(default=None, max_length=120)
    source_device_id: str | None = Field(default=None, max_length=100)
    sync_status: str = "ONLINE"
    lines: list[PosLineIn] = Field(min_length=1)


class SettlementIn(BaseModel):
    settlement_date: date
    bank_account_id: int


def order_number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(PosOrder.id)).where(PosOrder.company_id == company_id)) or 0
    return f"POS-{company_id}-{year}-{count + 1:06d}"


@router.post("/platforms", status_code=201)
def create_platform(data: PlatformIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.manage")
    if db.scalar(select(DeliveryPlatform).where(DeliveryPlatform.company_id == data.company_id, DeliveryPlatform.code == data.code)):
        raise HTTPException(409, "Platform code already exists")
    row = DeliveryPlatform(**data.model_dump(), active=True)
    db.add(row); db.flush()
    write_audit(db, action="DELIVERY_PLATFORM_CREATED", entity_type="DELIVERY_PLATFORM", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "commission_rate": str(row.commission_rate)})
    db.commit()
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "commission_rate": row.commission_rate}


@router.get("/platforms")
def list_platforms(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(DeliveryPlatform).where(DeliveryPlatform.company_id == company_id, DeliveryPlatform.active.is_(True)).order_by(DeliveryPlatform.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "commission_rate": r.commission_rate} for r in rows]


@router.post("/menu", status_code=201)
def create_menu_item(data: MenuItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.manage")
    if db.scalar(select(MenuItem).where(MenuItem.company_id == data.company_id, MenuItem.code == data.code)):
        raise HTTPException(409, "Menu item code already exists")
    recipe = db.scalar(select(BillOfMaterial).where(BillOfMaterial.id == data.recipe_bom_id, BillOfMaterial.company_id == data.company_id, BillOfMaterial.status == "ACTIVE"))
    if not recipe: raise HTTPException(404, "Recipe BOM not found")
    if recipe.finished_item_id != data.inventory_item_id: raise HTTPException(422, "Menu item and recipe finished item must match")
    tax_code = get_tax_code(db, data.company_id, code=data.tax_code, direction="SALES", vat_rate=data.vat_rate, user_id=user.id)
    payload = data.model_dump(exclude={"tax_code"})
    payload["vat_rate"] = tax_code.rate
    payload["tax_code_id"] = tax_code.id
    row = MenuItem(**payload, active=True)
    db.add(row); db.flush()
    write_audit(db, action="MENU_ITEM_CREATED", entity_type="MENU_ITEM", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "selling_price": str(row.selling_price)})
    db.commit()
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "selling_price": row.selling_price, "vat_rate": row.vat_rate, "tax_code": row.tax_code.code if row.tax_code else None}


@router.get("/menu")
def list_menu(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    rows = db.scalars(select(MenuItem).where(MenuItem.company_id == company_id, MenuItem.active.is_(True)).options(selectinload(MenuItem.recipe).selectinload(BillOfMaterial.lines)).order_by(MenuItem.code)).all()
    result = []
    for r in rows:
        recipe_cost = money(sum((line.quantity * line.component_item.standard_cost for line in r.recipe.lines), Decimal("0")) / r.recipe.output_quantity)
        result.append({"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "selling_price": r.selling_price, "vat_rate": r.vat_rate, "tax_code": r.tax_code.code if r.tax_code else None, "standard_food_cost": recipe_cost, "food_cost_percent": money(recipe_cost / r.selling_price * Decimal("100")) if r.selling_price else 0})
    return result


@router.post("/orders", status_code=201)
def create_order(data: PosOrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "pos.sell")
    if data.client_order_id:
        existing = db.scalar(select(PosOrder).where(PosOrder.company_id == data.company_id, PosOrder.client_order_id == data.client_order_id).options(selectinload(PosOrder.lines).selectinload(PosOrderLine.menu_item), selectinload(PosOrder.platform)))
        if existing:
            return serialize_order(existing, True)
    warehouse = get_warehouse(db, data.company_id, data.warehouse_id)
    branch = None
    if data.branch_id is not None:
        branch = db.scalar(select(Branch).where(Branch.id == data.branch_id, Branch.company_id == data.company_id, Branch.active.is_(True)))
        if not branch:
            raise HTTPException(404, "Branch not found")
    business_unit = data.business_unit.upper()
    if business_unit not in {"RESTAURANT", "GYM_CAFE"}:
        raise HTTPException(422, "Unsupported POS business unit")
    gym_department = None
    gym_member = None
    cost_center_id = data.cost_center_id
    if business_unit == "GYM_CAFE":
        if branch is None or data.gym_department_id is None:
            raise HTTPException(422, "Gym cafe orders require branch and cafe department")
        gym_department = db.scalar(select(GymDepartment).where(
            GymDepartment.id == data.gym_department_id, GymDepartment.company_id == data.company_id,
            GymDepartment.branch_id == data.branch_id, GymDepartment.department_type == "CAFE", GymDepartment.active.is_(True),
        ))
        if not gym_department:
            raise HTTPException(404, "Active gym cafe department not found")
        cost_center_id = gym_department.cost_center_id
        if data.gym_member_id is not None:
            gym_member = db.scalar(select(Member).where(Member.id == data.gym_member_id, Member.company_id == data.company_id, Member.active.is_(True)))
            if not gym_member:
                raise HTTPException(404, "Gym member not found")
            contract = db.scalar(select(MembershipContract).where(
                MembershipContract.company_id == data.company_id, MembershipContract.member_id == gym_member.id,
                MembershipContract.status.in_(["ACTIVE", "FROZEN"]), MembershipContract.start_date <= data.order_date, MembershipContract.end_date >= data.order_date,
            ).order_by(MembershipContract.id.desc()))
            if not contract:
                raise HTTPException(409, "Member has no active membership for cafe price")
            state = db.scalar(select(GymMembershipState).where(GymMembershipState.contract_id == contract.id))
            if contract.status == "FROZEN" or (state and state.freeze_start and state.freeze_end and state.freeze_start <= data.order_date <= state.freeze_end):
                raise HTTPException(409, "Frozen membership cannot use cafe member price")
            if state and state.branch_id and state.branch_id != data.branch_id:
                raise HTTPException(409, "Member belongs to a different branch")
    order_type = data.order_type.upper()
    if order_type not in {"DINE_IN", "TAKEAWAY", "DELIVERY"}:
        raise HTTPException(422, "Unsupported order type")
    if business_unit == "GYM_CAFE" and order_type == "DELIVERY":
        raise HTTPException(422, "Gym cafe delivery is not enabled in RC15")
    channel = data.payment_channel.upper()
    if channel == "DELIVERY":
        order_type = "DELIVERY"
    table = None
    reservation = None
    if order_type == "DINE_IN":
        if data.table_id is None or branch is None:
            raise HTTPException(422, "Dine-in orders require branch and table")
        table = db.scalar(select(RestaurantTable).where(RestaurantTable.id == data.table_id, RestaurantTable.company_id == data.company_id, RestaurantTable.branch_id == data.branch_id, RestaurantTable.active.is_(True)))
        if not table:
            raise HTTPException(404, "Restaurant table not found")
        if table.status not in {"AVAILABLE", "RESERVED"}:
            raise HTTPException(409, "Restaurant table is not available")
    if data.reservation_id is not None:
        reservation = db.scalar(select(RestaurantReservation).where(RestaurantReservation.id == data.reservation_id, RestaurantReservation.company_id == data.company_id))
        if not reservation:
            raise HTTPException(404, "Reservation not found")
        if reservation.status not in {"BOOKED", "SEATED"}:
            raise HTTPException(409, "Reservation is not active")
        if table and reservation.table_id and reservation.table_id != table.id:
            raise HTTPException(409, "Reservation is assigned to a different table")
    cashier_shift = None
    if data.cashier_shift_id is not None:
        cashier_shift = db.scalar(select(CashierShift).where(CashierShift.id == data.cashier_shift_id, CashierShift.company_id == data.company_id, CashierShift.status == "OPEN"))
        if not cashier_shift:
            raise HTTPException(404, "Open cashier shift not found")
        if branch and cashier_shift.branch_id != branch.id:
            raise HTTPException(409, "Cashier shift belongs to a different branch")
    if channel not in {"CASH", "CARD", "DELIVERY"}: raise HTTPException(422, "Unsupported payment channel")
    bank = None
    platform = None
    if channel in {"CASH", "CARD"}:
        bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id, BankAccount.active.is_(True)))
        if not bank: raise HTTPException(404, "Bank account not found")
    else:
        platform = db.scalar(select(DeliveryPlatform).where(DeliveryPlatform.id == data.platform_id, DeliveryPlatform.company_id == data.company_id, DeliveryPlatform.active.is_(True)))
        if not platform: raise HTTPException(404, "Delivery platform not found")
    menu_ids = [line.menu_item_id for line in data.lines]
    menu = db.scalars(select(MenuItem).where(MenuItem.company_id == data.company_id, MenuItem.id.in_(menu_ids), MenuItem.active.is_(True)).options(selectinload(MenuItem.recipe).selectinload(BillOfMaterial.lines))).all()
    menu_by_id = {row.id: row for row in menu}
    if len(menu_by_id) != len(set(menu_ids)): raise HTTPException(404, "Menu item not found")
    cafe_profiles = {}
    if business_unit == "GYM_CAFE":
        profiles = db.scalars(select(GymCafeProductProfile).where(
            GymCafeProductProfile.company_id == data.company_id, GymCafeProductProfile.branch_id == data.branch_id,
            GymCafeProductProfile.department_id == data.gym_department_id, GymCafeProductProfile.menu_item_id.in_(menu_ids),
            GymCafeProductProfile.active.is_(True),
        )).all()
        cafe_profiles = {row.menu_item_id: row for row in profiles}
        if len(cafe_profiles) != len(set(menu_ids)):
            raise HTTPException(422, "All gym cafe order items must have an active cafe product profile")
    number = order_number(db, data.company_id, data.order_date.year)
    subtotal = Decimal("0"); vat_total = Decimal("0"); food_cost = Decimal("0")
    order_lines = []
    component_usage: dict[int, dict] = {}
    for line_in in data.lines:
        item = menu_by_id[line_in.menu_item_id]
        qty = quantity(line_in.quantity)
        unit_price = item.selling_price
        if business_unit == "GYM_CAFE" and gym_member is not None and cafe_profiles[item.id].member_price is not None:
            unit_price = cafe_profiles[item.id].member_price
        tax_code = item.tax_code or get_tax_code(db, data.company_id, code=None, direction="SALES", vat_rate=Decimal(item.vat_rate), user_id=user.id)
        net = money(unit_price * qty); tax_calc = calculate_line(net, tax_code); vat = tax_calc["tax"]; total = tax_calc["document_total"]
        line_cost = Decimal("0")
        for recipe_line in item.recipe.lines:
            required = quantity(recipe_line.quantity / item.recipe.output_quantity * qty * (Decimal("1") + recipe_line.scrap_percent / Decimal("100")))
            available = stock_balance(db, data.company_id, warehouse.id, recipe_line.component_item_id)
            previous = component_usage.get(recipe_line.component_item_id, {}).get("quantity", Decimal("0"))
            if available < previous + required:
                raise HTTPException(422, f"Insufficient stock for component {recipe_line.component_item.code}")
            component_cost = money(required * recipe_line.component_item.standard_cost)
            usage = component_usage.setdefault(recipe_line.component_item_id, {"item": recipe_line.component_item, "quantity": Decimal("0"), "cost": Decimal("0")})
            usage["quantity"] += required; usage["cost"] += component_cost; line_cost += component_cost
        subtotal += net; vat_total += vat; food_cost += line_cost
        order_lines.append(PosOrderLine(menu_item_id=item.id, quantity=qty, unit_price=unit_price, net_amount=net, vat_amount=vat, tax_code_id=tax_code.id, total_amount=total, food_cost=money(line_cost)))
    subtotal = money(subtotal); vat_total = money(vat_total); total = money(subtotal + vat_total); food_cost = money(food_cost)
    revenue = get_account(db, data.company_id, "411010"); output_vat = get_account(db, data.company_id, "212010")
    debit_account_id = bank.gl_account_id if bank else get_account(db, data.company_id, "116010").id
    sale_journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.order_date, reference=number, description=f"POS sale {number}", lines=[{"account_id": debit_account_id, "debit": total, "credit": 0, "branch_id": data.branch_id, "cost_center_id": cost_center_id}, {"account_id": revenue.id, "debit": 0, "credit": subtotal, "branch_id": data.branch_id, "cost_center_id": cost_center_id}, {"account_id": output_vat.id, "debit": 0, "credit": vat_total, "branch_id": data.branch_id, "cost_center_id": cost_center_id}], cash_flow_activity="OPERATING" if bank else None, cash_flow_kind="CUSTOMER_RECEIPTS" if bank else None)
    cogs = get_account(db, data.company_id, "511010"); inventory = get_account(db, data.company_id, "113010")
    cogs_journal = create_posted_journal(db, company_id=data.company_id, user_id=user.id, posting_date=data.order_date, reference=number, description=f"POS food cost {number}", lines=[{"account_id": cogs.id, "debit": food_cost, "credit": 0, "branch_id": data.branch_id, "cost_center_id": cost_center_id}, {"account_id": inventory.id, "debit": 0, "credit": food_cost, "branch_id": data.branch_id, "cost_center_id": cost_center_id}])
    order = PosOrder(
        company_id=data.company_id, number=number, order_date=data.order_date, warehouse_id=warehouse.id,
        branch_id=data.branch_id, business_unit=business_unit, gym_department_id=data.gym_department_id if gym_department else None,
        gym_member_id=gym_member.id if gym_member else None, cost_center_id=cost_center_id, order_type=order_type, table_id=table.id if table else None,
        reservation_id=reservation.id if reservation else None, cashier_shift_id=cashier_shift.id if cashier_shift else None,
        guest_count=data.guest_count, customer_name=data.customer_name, notes=data.notes,
        client_order_id=data.client_order_id, source_device_id=data.source_device_id,
        sync_status=data.sync_status.upper(), payment_channel=channel, bank_account_id=bank.id if bank else None,
        platform_id=platform.id if platform else None, subtotal=subtotal, vat_amount=vat_total, total=total,
        food_cost=food_cost, status="PENDING_SETTLEMENT" if channel == "DELIVERY" else "SETTLED",
        sale_journal_id=sale_journal.id, cogs_journal_id=cogs_journal.id, created_by=user.id,
    )
    order.lines.extend(order_lines); db.add(order); db.flush()
    if table:
        table.status = "OCCUPIED"
    if reservation:
        from app.core.time import utc_now
        reservation.status = "SEATED"; reservation.seated_at = utc_now()
    station_links = db.scalars(select(MenuKitchenStation).where(MenuKitchenStation.menu_item_id.in_(menu_ids))).all()
    station_by_menu = {link.menu_item_id: link.kitchen_station_id for link in station_links}
    ticket_by_station = {}
    for order_line in order.lines:
        station_id = station_by_menu.get(order_line.menu_item_id)
        if station_id is None:
            continue
        ticket = ticket_by_station.get(station_id)
        if ticket is None:
            ticket = KitchenTicket(company_id=data.company_id, branch_id=data.branch_id or warehouse.branch_id, pos_order_id=order.id, kitchen_station_id=station_id, number=f"KDS-{order.id}-{station_id}", status="NEW")
            db.add(ticket); db.flush(); ticket_by_station[station_id] = ticket
        ticket.lines.append(KitchenTicketLine(pos_order_line_id=order_line.id, quantity=order_line.quantity, status="NEW"))
    for usage in component_usage.values():
        db.add(StockMovement(company_id=data.company_id, warehouse_id=warehouse.id, item_id=usage["item"].id, movement_date=data.order_date, movement_type="POS_CONSUMPTION", quantity=-quantity(usage["quantity"]), unit_cost=usage["item"].standard_cost, total_cost=-money(usage["cost"]), reference_type="POS_ORDER", reference_id=order.id, journal_id=cogs_journal.id, created_by=user.id))
    write_audit(db, action="POS_ORDER_POSTED", entity_type="POS_ORDER", entity_id=order.id, user_id=user.id, company_id=data.company_id, after={"number": number, "channel": channel, "total": str(total), "food_cost": str(food_cost), "gross_margin": str(money(subtotal-food_cost))})
    db.commit()
    return serialize_order(order, True)


@router.post("/orders/{order_id}/settle")
def settle_delivery_order(order_id: int, data: SettlementIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.scalar(select(PosOrder).where(PosOrder.id == order_id).options(selectinload(PosOrder.platform)))
    if not order: raise HTTPException(404, "POS order not found")
    ensure_permission(db, user, order.company_id, "pos.settle")
    if order.payment_channel != "DELIVERY" or order.status != "PENDING_SETTLEMENT": raise HTTPException(409, "Order is not pending delivery settlement")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == order.company_id, BankAccount.active.is_(True)))
    if not bank: raise HTTPException(404, "Bank account not found")
    commission = money(order.total * order.platform.commission_rate / Decimal("100")); net = money(order.total - commission)
    receivable = get_account(db, order.company_id, "116010"); commission_expense = get_account(db, order.company_id, "616010")
    journal = create_posted_journal(db, company_id=order.company_id, user_id=user.id, posting_date=data.settlement_date, reference=order.number, description=f"Delivery platform settlement {order.number}", lines=[{"account_id": bank.gl_account_id, "debit": net, "credit": 0}, {"account_id": commission_expense.id, "debit": commission, "credit": 0}, {"account_id": receivable.id, "debit": 0, "credit": order.total}], cash_flow_activity="OPERATING", cash_flow_kind="CUSTOMER_RECEIPTS")
    order.status = "SETTLED"; order.settlement_journal_id = journal.id
    write_audit(db, action="DELIVERY_ORDER_SETTLED", entity_type="POS_ORDER", entity_id=order.id, user_id=user.id, company_id=order.company_id, after={"platform": order.platform.code, "gross": str(order.total), "commission": str(commission), "net": str(net), "journal": journal.number})
    db.commit()
    return {**serialize_order(order), "commission": commission, "net_settlement": net, "settlement_journal": journal.number}


@router.get("/orders")
def list_orders(company_id: int, business_unit: str = "RESTAURANT", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, PosOrder)
    query = select(PosOrder).where(PosOrder.company_id == company_id, PosOrder.business_unit == business_unit.upper())
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.options(selectinload(PosOrder.lines).selectinload(PosOrderLine.menu_item), selectinload(PosOrder.platform)).order_by(PosOrder.id.desc())).all()
    return [serialize_order(r, True) for r in rows]


@router.get("/summary")
def pos_summary(company_id: int, business_unit: str = "RESTAURANT", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "pos.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, PosOrder)
    query = select(PosOrder).where(PosOrder.company_id == company_id, PosOrder.business_unit == business_unit.upper())
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query).all()
    sales = money(sum((r.subtotal for r in rows), Decimal("0"))); food_cost = money(sum((r.food_cost for r in rows), Decimal("0")))
    return {"orders": len(rows), "net_sales": sales, "vat": money(sum((r.vat_amount for r in rows), Decimal("0"))), "food_cost": food_cost, "gross_profit": money(sales-food_cost), "food_cost_percent": money(food_cost/sales*Decimal("100")) if sales else 0, "pending_settlements": sum(1 for r in rows if r.status == "PENDING_SETTLEMENT")}


def serialize_order(order: PosOrder, include_lines: bool = False) -> dict:
    data = {"id": order.id, "number": order.number, "order_date": order.order_date, "business_unit": order.business_unit, "gym_department_id": order.gym_department_id, "gym_member_id": order.gym_member_id, "cost_center_id": order.cost_center_id, "order_type": order.order_type, "branch_id": order.branch_id, "table_id": order.table_id, "reservation_id": order.reservation_id, "cashier_shift_id": order.cashier_shift_id, "guest_count": order.guest_count, "customer_name": order.customer_name, "client_order_id": order.client_order_id, "sync_status": order.sync_status, "payment_channel": order.payment_channel, "platform": order.platform.code if order.platform else None, "subtotal": order.subtotal, "vat_amount": order.vat_amount, "total": order.total, "food_cost": order.food_cost, "gross_profit": money(order.subtotal-order.food_cost), "status": order.status}
    if include_lines:
        data["lines"] = [{"id": line.id, "menu_item_id": line.menu_item_id, "menu_item": line.menu_item.code, "name_ar": line.menu_item.name_ar, "name_en": line.menu_item.name_en, "quantity": line.quantity, "unit_price": line.unit_price, "net_amount": line.net_amount, "vat_amount": line.vat_amount, "total_amount": line.total_amount, "food_cost": line.food_cost} for line in order.lines]
    return data
