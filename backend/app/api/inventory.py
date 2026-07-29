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
    Account, BankAccount, Budget, BudgetLine, FiscalPeriod, FiscalYear, GoodsReceipt, GoodsReceiptLine,
    Item, JournalEntry, Party, PurchaseInvoice, PurchaseInvoiceLine, PurchaseOrder, PurchaseOrderLine,
    StockMovement, User, Warehouse,
)
from app.services.audit import write_audit
from app.services.operations import get_account, get_item, get_warehouse, money, quantity, stock_balance, stock_value
from app.services.ar_ap import ensure_purchase_invoice_open_item
from app.services.posting import create_posted_journal, ensure_open_period

router = APIRouter(prefix="/inventory", tags=["inventory and procurement"])


class WarehouseIn(BaseModel):
    company_id: int
    branch_id: int | None = None
    code: str = Field(min_length=2, max_length=30)
    name_ar: str
    name_en: str
    warehouse_type: str = "GENERAL"




# ------------------------------------------------- item and warehouse taxonomy
# THREE PROBLEMS THIS CLOSES
#   1. The seeder writes FINISHED_GOOD while a screen offered FINISHED, so two
#      spellings of the same thing coexisted and any filter on type missed rows.
#   2. Nothing validated these columns, so any free text was stored - "raw",
#      "Raw Material" and RAW_MATERIAL would all be different types.
#   3. The type carried no behaviour: a SERVICE line could take a stock movement
#      and end up with a balance, which is meaningless.

ITEM_TYPES = {
    "RAW_MATERIAL",    # poultry, spices, oils
    "FINISHED_GOOD",   # what you sell (the seeded spelling; FINISHED is aliased)
    "PACKAGING",       # cartons, bags, labels
    "INVENTORY",       # general stock: spare parts, supplies
    "CONSUMABLE",      # used up, not counted
    "SERVICE",         # no physical stock at all
}

# Historic or shorthand spellings mapped onto the canonical value.
ITEM_TYPE_ALIASES = {
    "FINISHED": "FINISHED_GOOD",
    "FINISHED_GOODS": "FINISHED_GOOD",
    "RAW": "RAW_MATERIAL",
    "RAW_MATERIALS": "RAW_MATERIAL",
    "PACK": "PACKAGING",
    "STOCK": "INVENTORY",
    "GENERAL": "INVENTORY",
}

# Types that hold a countable balance. SERVICE and CONSUMABLE do not, so they are
# refused on stock movements instead of silently building a meaningless balance.
STOCKED_ITEM_TYPES = {"RAW_MATERIAL", "FINISHED_GOOD", "PACKAGING", "INVENTORY"}

WAREHOUSE_TYPES = {
    "MAIN",             # general store
    "RAW",              # raw materials only
    "FINISHED",         # finished goods only
    "RAW_AND_FINISHED", # both (the seeded manufacturing default)
    "COLD",             # chilled, 0 to 4 C
    "FROZEN",           # frozen, -18 C or below
    "QUARANTINE",       # received, awaiting inspection - not available to sell
    "TRANSIT",          # in transit between sites
    "TAX_WAREHOUSE",    # licensed excise-tax suspension warehouse
}

WAREHOUSE_TYPE_ALIASES = {
    "GENERAL": "MAIN",
    "CHILLED": "COLD",
    "FINISHED_GOODS": "FINISHED",
}


def normalise_item_type(value: str) -> str:
    """Canonical item type, or a 422 naming the accepted values."""
    raw = (value or "").strip().upper().replace(" ", "_").replace("-", "_")
    raw = ITEM_TYPE_ALIASES.get(raw, raw)
    if raw not in ITEM_TYPES:
        raise HTTPException(
            422,
            {
                "message_ar": f"نوع صنف غير معروف: {value}. المسموح: {sorted(ITEM_TYPES)}",
                "message_en": f"Unknown item type: {value}. Allowed: {sorted(ITEM_TYPES)}",
            },
        )
    return raw


def normalise_warehouse_type(value: str) -> str:
    """Canonical warehouse type, or a 422 naming the accepted values."""
    raw = (value or "").strip().upper().replace(" ", "_").replace("-", "_")
    raw = WAREHOUSE_TYPE_ALIASES.get(raw, raw)
    if raw not in WAREHOUSE_TYPES:
        raise HTTPException(
            422,
            {
                "message_ar": f"نوع مستودع غير معروف: {value}. المسموح: {sorted(WAREHOUSE_TYPES)}",
                "message_en": f"Unknown warehouse type: {value}. Allowed: {sorted(WAREHOUSE_TYPES)}",
            },
        )
    return raw


def guard_stocked_item(item) -> None:
    """Refuse a stock movement on a type that has no physical balance."""
    kind = (getattr(item, "item_type", "") or "").upper()
    kind = ITEM_TYPE_ALIASES.get(kind, kind)
    if kind not in STOCKED_ITEM_TYPES:
        raise HTTPException(
            422,
            {
                "message_ar": (
                    f"الصنف {item.code} من نوع {kind} ولا يُتابع رصيده، فلا تُسجَّل عليه حركة مخزون. "
                    "الخدمات والمستهلكات تُحمَّل على حساب مصروف مباشرة."
                ),
                "message_en": (
                    f"{item.code} is a {kind} item with no tracked balance, so it cannot take a "
                    "stock movement. Services and consumables post straight to an expense account."
                ),
            },
        )


class ItemIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=40)
    name_ar: str
    name_en: str
    item_type: str = "INVENTORY"
    uom: str = "EA"
    standard_cost: Decimal = Field(ge=0)
    reorder_level: Decimal = Field(ge=0, default=0)
    inventory_account_code: str = "113010"
    cogs_account_code: str = "511010"
    revenue_account_code: str = "411010"


class POLineIn(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    vat_rate: Decimal = Field(ge=0, le=100, default=15)


class POIn(BaseModel):
    company_id: int
    order_date: date
    expected_receipt_date: date | None = None
    supplier_id: int
    warehouse_id: int
    lines: list[POLineIn] = Field(min_length=1)


class ReceiptLineIn(BaseModel):
    purchase_order_line_id: int
    quantity: Decimal = Field(gt=0)
    lot_number: str | None = None
    expiry_date: date | None = None


class ReceiptIn(BaseModel):
    receipt_date: date
    lines: list[ReceiptLineIn] = Field(min_length=1)


class SupplierInvoiceIn(BaseModel):
    invoice_date: date
    due_date: date
    supplier_invoice_number: str = Field(min_length=1, max_length=100)


class IssueIn(BaseModel):
    company_id: int
    warehouse_id: int
    item_id: int
    issue_date: date
    quantity: Decimal = Field(gt=0)
    reference: str = Field(min_length=1, max_length=100)
    lot_number: str | None = None


class TransferIn(BaseModel):
    company_id: int
    source_warehouse_id: int
    destination_warehouse_id: int
    item_id: int
    transfer_date: date
    quantity: Decimal = Field(gt=0)
    reference: str


def _doc_number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{count + 1:05d}"


def _supplier(db: Session, company_id: int, supplier_id: int) -> Party:
    row = db.scalar(select(Party).where(Party.id == supplier_id, Party.company_id == company_id, Party.party_type.in_(["SUPPLIER", "BOTH"])))
    if not row:
        raise HTTPException(404, "Supplier not found")
    return row


@router.post("/warehouses", status_code=201)
def create_warehouse(data: WarehouseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "inventory.manage")
    if db.scalar(select(Warehouse).where(Warehouse.company_id == data.company_id, Warehouse.code == data.code)):
        raise HTTPException(409, "Warehouse code already exists")
    payload = data.model_dump()
    # Normalise before persisting: model_dump bypasses any per-field handling, so
    # an unknown type would otherwise be stored verbatim.
    payload["warehouse_type"] = normalise_warehouse_type(payload.get("warehouse_type", "MAIN"))
    row = Warehouse(**payload, active=True)
    db.add(row); db.flush()
    write_audit(db, action="WAREHOUSE_CREATED", entity_type="WAREHOUSE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code})
    db.commit()
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "warehouse_type": row.warehouse_type}


@router.get("/warehouses")
def list_warehouses(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, Warehouse)
    query = select(Warehouse).where(Warehouse.company_id == company_id, Warehouse.active.is_(True))
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.order_by(Warehouse.code)).all()
    return [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "warehouse_type": r.warehouse_type, "branch_id": r.branch_id} for r in rows]


@router.post("/items", status_code=201)
def create_item(data: ItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "inventory.manage")
    if db.scalar(select(Item).where(Item.company_id == data.company_id, Item.code == data.code)):
        raise HTTPException(409, "Item code already exists")
    inventory_account = get_account(db, data.company_id, data.inventory_account_code)
    cogs_account = get_account(db, data.company_id, data.cogs_account_code)
    revenue_account = get_account(db, data.company_id, data.revenue_account_code)
    row = Item(
        company_id=data.company_id, code=data.code, name_ar=data.name_ar, name_en=data.name_en,
        item_type=normalise_item_type(data.item_type), uom=data.uom, valuation_method="WEIGHTED_AVERAGE",
        standard_cost=data.standard_cost, reorder_level=data.reorder_level,
        inventory_account_id=inventory_account.id, cogs_account_id=cogs_account.id, revenue_account_id=revenue_account.id,
        active=True,
    )
    db.add(row); db.flush()
    write_audit(db, action="ITEM_CREATED", entity_type="ITEM", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code})
    db.commit()
    return {"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "standard_cost": row.standard_cost}


@router.get("/items")
def list_items(company_id: int, warehouse_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    rows = db.scalars(select(Item).where(Item.company_id == company_id, Item.active.is_(True)).order_by(Item.code)).all()
    result=[]
    for r in rows:
        balance = stock_balance(db, company_id, warehouse_id, r.id) if warehouse_id else quantity(db.scalar(select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(StockMovement.company_id==company_id, StockMovement.item_id==r.id)) or 0)
        value = stock_value(db, company_id, warehouse_id, r.id)
        result.append({"id":r.id,"code":r.code,"name_ar":r.name_ar,"name_en":r.name_en,"item_type":r.item_type,"uom":r.uom,"balance":balance,"value":value,"reorder_level":r.reorder_level,"low_stock":balance<=r.reorder_level})
    return result


@router.post("/purchase-orders", status_code=201)
def create_purchase_order(data: POIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "procurement.manage")
    ensure_open_period(db, data.company_id, data.order_date)
    supplier = _supplier(db, data.company_id, data.supplier_id)
    warehouse = get_warehouse(db, data.company_id, data.warehouse_id)
    po = PurchaseOrder(company_id=data.company_id, number=_doc_number(db, PurchaseOrder, data.company_id, "PO", data.order_date.year), order_date=data.order_date, expected_receipt_date=data.expected_receipt_date, supplier_id=supplier.id, warehouse_id=warehouse.id, status="DRAFT", created_by=user.id)
    subtotal=Decimal("0"); vat=Decimal("0")
    for source in data.lines:
        item=get_item(db,data.company_id,source.item_id)
        guard_stocked_item(item)  # services and consumables hold no balance
        line_sub=money(source.quantity*source.unit_price); line_vat=money(line_sub*source.vat_rate/Decimal("100"))
        po.lines.append(PurchaseOrderLine(item_id=item.id,quantity=quantity(source.quantity),unit_price=source.unit_price,vat_rate=source.vat_rate,received_quantity=0,invoiced_quantity=0))
        subtotal+=line_sub;vat+=line_vat
    po.subtotal=money(subtotal);po.vat_amount=money(vat);po.total=money(subtotal+vat)
    db.add(po);db.flush()
    write_audit(db,action="PURCHASE_ORDER_CREATED",entity_type="PURCHASE_ORDER",entity_id=po.id,user_id=user.id,company_id=data.company_id,after={"number":po.number,"total":str(po.total),"status":po.status})
    db.commit()
    return {"id":po.id,"number":po.number,"status":po.status,"subtotal":po.subtotal,"vat_amount":po.vat_amount,"total":po.total,"lines":[{"id":line.id,"item_id":line.item_id,"quantity":line.quantity,"unit_price":line.unit_price,"vat_rate":line.vat_rate} for line in po.lines]}


@router.post("/purchase-orders/{po_id}/approve")
def approve_purchase_order(po_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    po=db.scalar(select(PurchaseOrder).where(PurchaseOrder.id==po_id).options(selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.item)))
    if not po:raise HTTPException(404,"Purchase order not found")
    ensure_permission(db,user,po.company_id,"procurement.approve")
    if po.status!="DRAFT":raise HTTPException(409,"Only draft purchase orders can be approved")
    po.status="APPROVED";po.approved_by=user.id
    # Commit the net value against an approved budget line when the dimension exists.
    period = db.scalar(select(FiscalPeriod).join(FiscalYear).where(FiscalYear.company_id==po.company_id,FiscalPeriod.start_date<=po.order_date,FiscalPeriod.end_date>=po.order_date))
    if period:
        for line in po.lines:
            budget_line=db.scalar(select(BudgetLine).join(Budget).where(Budget.company_id==po.company_id,Budget.status=="APPROVED",BudgetLine.account_id==line.item.inventory_account_id,BudgetLine.period_number==period.number))
            if budget_line:budget_line.committed_amount=money(budget_line.committed_amount+line.quantity*line.unit_price)
    write_audit(db,action="PURCHASE_ORDER_APPROVED",entity_type="PURCHASE_ORDER",entity_id=po.id,user_id=user.id,company_id=po.company_id,before={"status":"DRAFT"},after={"status":"APPROVED"})
    db.commit();return {"id":po.id,"number":po.number,"status":po.status}


@router.post("/purchase-orders/{po_id}/receive",status_code=201)
def receive_purchase_order(po_id:int,data:ReceiptIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    po=db.scalar(select(PurchaseOrder).where(PurchaseOrder.id==po_id).options(selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.item)))
    if not po:raise HTTPException(404,"Purchase order not found")
    ensure_permission(db,user,po.company_id,"inventory.receive")
    if po.status not in {"APPROVED","PARTIALLY_RECEIVED"}:raise HTTPException(409,"Purchase order is not available for receipt")
    ensure_open_period(db,po.company_id,data.receipt_date)
    source_by_id={line.id:line for line in po.lines}; receipt_lines=[]; journal_lines=[]; total=Decimal("0")
    for source in data.lines:
        po_line=source_by_id.get(source.purchase_order_line_id)
        if not po_line:raise HTTPException(422,"Purchase order line does not belong to this order")
        remaining=quantity(po_line.quantity-po_line.received_quantity);received=quantity(source.quantity)
        guard_stocked_item(po_line.item)  # a service line must not raise stock
        if received>remaining:raise HTTPException(422,f"Receipt exceeds remaining quantity for item {po_line.item.code}")
        line_total=money(received*po_line.unit_price);total+=line_total
        receipt_lines.append((po_line,received,line_total,source))
        journal_lines.append({"account_id":po_line.item.inventory_account_id,"debit":line_total,"credit":0,"description":po_line.item.name_en})
    grni=get_account(db,po.company_id,"214010")
    journal_lines.append({"account_id":grni.id,"debit":0,"credit":money(total),"description":po.number})
    journal=create_posted_journal(db,company_id=po.company_id,user_id=user.id,posting_date=data.receipt_date,reference=po.number,description=f"Goods receipt for {po.number}",lines=journal_lines)
    grn=GoodsReceipt(company_id=po.company_id,number=_doc_number(db,GoodsReceipt,po.company_id,"GRN",data.receipt_date.year),receipt_date=data.receipt_date,purchase_order_id=po.id,warehouse_id=po.warehouse_id,status="POSTED",total_cost=money(total),journal_id=journal.id,created_by=user.id)
    db.add(grn);db.flush()
    for po_line,received,line_total,source in receipt_lines:
        po_line.received_quantity=quantity(po_line.received_quantity+received)
        grn.lines.append(GoodsReceiptLine(purchase_order_line_id=po_line.id,item_id=po_line.item_id,quantity=received,unit_cost=po_line.unit_price,lot_number=source.lot_number,expiry_date=source.expiry_date))
        db.add(StockMovement(company_id=po.company_id,warehouse_id=po.warehouse_id,item_id=po_line.item_id,movement_date=data.receipt_date,movement_type="RECEIPT",quantity=received,unit_cost=po_line.unit_price,total_cost=line_total,lot_number=source.lot_number,expiry_date=source.expiry_date,reference_type="GOODS_RECEIPT",reference_id=grn.id,journal_id=journal.id,created_by=user.id))
    po.status="RECEIVED" if all(quantity(line.received_quantity)>=quantity(line.quantity) for line in po.lines) else "PARTIALLY_RECEIVED"
    write_audit(db,action="GOODS_RECEIPT_POSTED",entity_type="GOODS_RECEIPT",entity_id=grn.id,user_id=user.id,company_id=po.company_id,after={"number":grn.number,"total_cost":str(grn.total_cost),"journal":journal.number})
    db.commit();return {"id":grn.id,"number":grn.number,"status":grn.status,"total_cost":grn.total_cost,"journal_number":journal.number,"po_status":po.status}


@router.post("/goods-receipts/{grn_id}/supplier-invoice",status_code=201)
def invoice_goods_receipt(grn_id:int,data:SupplierInvoiceIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    grn=db.scalar(select(GoodsReceipt).where(GoodsReceipt.id==grn_id).options(selectinload(GoodsReceipt.lines),selectinload(GoodsReceipt.purchase_order).selectinload(PurchaseOrder.lines)))
    if not grn:raise HTTPException(404,"Goods receipt not found")
    po=grn.purchase_order
    ensure_permission(db,user,grn.company_id,"procurement.invoice")
    ensure_open_period(db,grn.company_id,data.invoice_date)
    grni=get_account(db,grn.company_id,"214010");input_vat=get_account(db,grn.company_id,"114010");ap=get_account(db,grn.company_id,"211010")
    subtotal=money(grn.total_cost)
    vat=money(sum((line.quantity*next(p.vat_rate for p in po.lines if p.id==line.purchase_order_line_id)*line.unit_cost/Decimal("100") for line in grn.lines),Decimal("0")))
    total=money(subtotal+vat)
    invoice=PurchaseInvoice(company_id=grn.company_id,number=_doc_number(db,PurchaseInvoice,grn.company_id,"PI",data.invoice_date.year),invoice_date=data.invoice_date,due_date=data.due_date,supplier_id=po.supplier_id,supplier_invoice_number=data.supplier_invoice_number,status="POSTED",subtotal=subtotal,vat_amount=vat,total=total,created_by=user.id)
    invoice.lines.append(PurchaseInvoiceLine(description=f"Matched to {grn.number}",expense_account_id=grni.id,quantity=1,unit_price=subtotal,vat_rate=vat/subtotal*100 if subtotal else 0,subtotal=subtotal,vat_amount=vat,total=total))
    journal=create_posted_journal(db,company_id=grn.company_id,user_id=user.id,posting_date=data.invoice_date,reference=invoice.number,description=f"Supplier invoice matched to {grn.number}",lines=[{"account_id":grni.id,"debit":subtotal,"credit":0},{"account_id":input_vat.id,"debit":vat,"credit":0},{"account_id":ap.id,"debit":0,"credit":total}])
    invoice.journal_id=journal.id;db.add(invoice);db.flush();ensure_purchase_invoice_open_item(db,invoice)
    for grn_line in grn.lines:
        po_line=next(line for line in po.lines if line.id==grn_line.purchase_order_line_id);po_line.invoiced_quantity=quantity(po_line.invoiced_quantity+grn_line.quantity)
    po.status="INVOICED" if all(quantity(line.invoiced_quantity)>=quantity(line.received_quantity) for line in po.lines) else po.status
    write_audit(db,action="THREE_WAY_MATCH_POSTED",entity_type="PURCHASE_INVOICE",entity_id=invoice.id,user_id=user.id,company_id=grn.company_id,after={"invoice":invoice.number,"grn":grn.number,"po":po.number,"journal":journal.number})
    db.commit();return {"id":invoice.id,"number":invoice.number,"status":invoice.status,"total":invoice.total,"journal_number":journal.number,"match_status":"PO_GRN_INVOICE_MATCHED"}


@router.post("/issues",status_code=201)
def issue_stock(data:IssueIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,data.company_id,"inventory.issue")
    item=get_item(db,data.company_id,data.item_id);get_warehouse(db,data.company_id,data.warehouse_id)
    available=stock_balance(db,data.company_id,data.warehouse_id,data.item_id);qty=quantity(data.quantity)
    if qty>available:raise HTTPException(422,f"Insufficient stock. Available: {available}")
    value=stock_value(db,data.company_id,data.warehouse_id,data.item_id);unit_cost=money(value/available) if available else money(item.standard_cost);total=money(qty*unit_cost)
    journal=create_posted_journal(db,company_id=data.company_id,user_id=user.id,posting_date=data.issue_date,reference=data.reference,description=f"Inventory issue {item.code}",lines=[{"account_id":item.cogs_account_id,"debit":total,"credit":0},{"account_id":item.inventory_account_id,"debit":0,"credit":total}])
    movement=StockMovement(company_id=data.company_id,warehouse_id=data.warehouse_id,item_id=item.id,movement_date=data.issue_date,movement_type="ISSUE",quantity=-qty,unit_cost=unit_cost,total_cost=-total,lot_number=data.lot_number,reference_type="ISSUE",reference_id=None,journal_id=journal.id,created_by=user.id)
    db.add(movement);db.flush();write_audit(db,action="STOCK_ISSUED",entity_type="STOCK_MOVEMENT",entity_id=movement.id,user_id=user.id,company_id=data.company_id,after={"item":item.code,"quantity":str(qty),"cost":str(total)})
    db.commit();return {"movement_id":movement.id,"quantity":qty,"unit_cost":unit_cost,"total_cost":total,"journal_number":journal.number,"remaining":stock_balance(db,data.company_id,data.warehouse_id,item.id)}


@router.post("/transfers",status_code=201)
def transfer_stock(data:TransferIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,data.company_id,"inventory.transfer")
    if data.source_warehouse_id==data.destination_warehouse_id:raise HTTPException(422,"Source and destination warehouses must differ")
    item=get_item(db,data.company_id,data.item_id);get_warehouse(db,data.company_id,data.source_warehouse_id);get_warehouse(db,data.company_id,data.destination_warehouse_id)
    qty=quantity(data.quantity);available=stock_balance(db,data.company_id,data.source_warehouse_id,item.id)
    if qty>available:raise HTTPException(422,f"Insufficient stock. Available: {available}")
    value=stock_value(db,data.company_id,data.source_warehouse_id,item.id);unit_cost=money(value/available) if available else money(item.standard_cost);total=money(qty*unit_cost)
    out=StockMovement(company_id=data.company_id,warehouse_id=data.source_warehouse_id,item_id=item.id,movement_date=data.transfer_date,movement_type="TRANSFER_OUT",quantity=-qty,unit_cost=unit_cost,total_cost=-total,reference_type="TRANSFER",created_by=user.id)
    db.add(out);db.flush();incoming=StockMovement(company_id=data.company_id,warehouse_id=data.destination_warehouse_id,item_id=item.id,movement_date=data.transfer_date,movement_type="TRANSFER_IN",quantity=qty,unit_cost=unit_cost,total_cost=total,reference_type="TRANSFER",reference_id=out.id,created_by=user.id)
    db.add(incoming);db.flush();out.reference_id=incoming.id
    write_audit(db,action="STOCK_TRANSFERRED",entity_type="STOCK_MOVEMENT",entity_id=out.id,user_id=user.id,company_id=data.company_id,after={"item":item.code,"quantity":str(qty),"source":data.source_warehouse_id,"destination":data.destination_warehouse_id})
    db.commit();return {"out_movement_id":out.id,"in_movement_id":incoming.id,"quantity":qty,"unit_cost":unit_cost,"total_cost":total}


@router.get("/stock-summary")
def stock_summary(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"inventory.read")
    rows=db.execute(select(Item.id,Item.code,Item.name_ar,Item.name_en,Item.uom,Item.reorder_level,Warehouse.id,Warehouse.code,Warehouse.name_ar,Warehouse.name_en,func.coalesce(func.sum(StockMovement.quantity),0),func.coalesce(func.sum(StockMovement.total_cost),0)).join(StockMovement,StockMovement.item_id==Item.id).join(Warehouse,Warehouse.id==StockMovement.warehouse_id).where(Item.company_id==company_id).group_by(Item.id,Warehouse.id).order_by(Item.code,Warehouse.code)).all()
    return [{"item_id":r[0],"item_code":r[1],"item_name_ar":r[2],"item_name_en":r[3],"uom":r[4],"reorder_level":r[5],"warehouse_id":r[6],"warehouse_code":r[7],"warehouse_name_ar":r[8],"warehouse_name_en":r[9],"quantity":quantity(r[10]),"value":money(r[11]),"low_stock":quantity(r[10])<=r[5]} for r in rows]


@router.get("/purchase-orders")
def list_purchase_orders(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"inventory.read")
    rows=db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id==company_id).options(selectinload(PurchaseOrder.lines)).order_by(PurchaseOrder.id.desc())).all()
    return [{"id":r.id,"number":r.number,"order_date":r.order_date,"supplier":r.supplier.name_en,"warehouse":r.warehouse.name_en,"status":r.status,"subtotal":r.subtotal,"vat_amount":r.vat_amount,"total":r.total,"received_percent":money(sum((line.received_quantity for line in r.lines),Decimal("0"))/sum((line.quantity for line in r.lines),Decimal("1"))*100),"lines":[{"id":line.id,"item_id":line.item_id,"quantity":line.quantity,"received_quantity":line.received_quantity,"invoiced_quantity":line.invoiced_quantity} for line in r.lines]} for r in rows]
