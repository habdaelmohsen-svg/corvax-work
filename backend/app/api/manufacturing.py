from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    BillOfMaterial, BillOfMaterialLine, Item, ProductionOrder, ProductionRun, StockMovement,
    User, Warehouse, WorkCenter,
)
from app.services.audit import write_audit
from app.services.operations import get_account, get_item, get_warehouse, money, quantity, stock_balance, stock_value
from app.services.posting import create_posted_journal, ensure_open_period

router = APIRouter(prefix="/manufacturing", tags=["manufacturing and costing"])


class WorkCenterIn(BaseModel):
    company_id: int
    code: str
    name_ar: str
    name_en: str
    hourly_labor_rate: Decimal = Field(ge=0)
    hourly_overhead_rate: Decimal = Field(ge=0)


class BOMLineIn(BaseModel):
    component_item_id: int
    quantity: Decimal = Field(gt=0)
    scrap_percent: Decimal = Field(ge=0, le=100, default=0)


class BOMIn(BaseModel):
    company_id: int
    code: str
    version: int = Field(default=1, ge=1)
    finished_item_id: int
    output_quantity: Decimal = Field(gt=0)
    work_center_id: int | None = None
    standard_hours: Decimal = Field(ge=0, default=0)
    lines: list[BOMLineIn] = Field(min_length=1)


class ProductionOrderIn(BaseModel):
    company_id: int
    order_date: date
    bom_id: int
    warehouse_id: int
    planned_quantity: Decimal = Field(gt=0)


class CompleteOrderIn(BaseModel):
    completion_date: date
    completed_quantity: Decimal = Field(gt=0)
    actual_hours: Decimal = Field(ge=0)
    lot_number: str | None = None
    expiry_date: date | None = None


class RunIn(BaseModel):
    run_date: date
    planned_minutes: Decimal = Field(gt=0)
    downtime_minutes: Decimal = Field(ge=0)
    ideal_cycle_seconds: Decimal = Field(gt=0)
    total_units: Decimal = Field(gt=0)
    good_units: Decimal = Field(ge=0)


def _number(db: Session, company_id: int, year: int) -> str:
    count = db.scalar(select(func.count(ProductionOrder.id)).where(ProductionOrder.company_id == company_id)) or 0
    return f"MO-{company_id}-{year}-{count + 1:05d}"


@router.post("/work-centers", status_code=201)
def create_work_center(data: WorkCenterIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "manufacturing.manage")
    if db.scalar(select(WorkCenter).where(WorkCenter.company_id==data.company_id,WorkCenter.code==data.code)):
        raise HTTPException(409,"Work center code already exists")
    row=WorkCenter(**data.model_dump(),active=True);db.add(row);db.flush()
    write_audit(db,action="WORK_CENTER_CREATED",entity_type="WORK_CENTER",entity_id=row.id,user_id=user.id,company_id=data.company_id,after={"code":row.code})
    db.commit();return {"id":row.id,"code":row.code,"name_ar":row.name_ar,"name_en":row.name_en,"hourly_labor_rate":row.hourly_labor_rate,"hourly_overhead_rate":row.hourly_overhead_rate}


@router.get("/work-centers")
def list_work_centers(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"manufacturing.read")
    rows=db.scalars(select(WorkCenter).where(WorkCenter.company_id==company_id,WorkCenter.active.is_(True)).order_by(WorkCenter.code)).all()
    return [{"id":r.id,"code":r.code,"name_ar":r.name_ar,"name_en":r.name_en,"hourly_labor_rate":r.hourly_labor_rate,"hourly_overhead_rate":r.hourly_overhead_rate} for r in rows]


@router.post("/boms",status_code=201)
def create_bom(data:BOMIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,data.company_id,"manufacturing.manage")
    if db.scalar(select(BillOfMaterial).where(BillOfMaterial.company_id==data.company_id,BillOfMaterial.code==data.code,BillOfMaterial.version==data.version)):
        raise HTTPException(409,"BOM version already exists")
    finished=get_item(db,data.company_id,data.finished_item_id)
    if data.work_center_id and not db.scalar(select(WorkCenter).where(WorkCenter.id==data.work_center_id,WorkCenter.company_id==data.company_id)):
        raise HTTPException(404,"Work center not found")
    bom=BillOfMaterial(company_id=data.company_id,code=data.code,version=data.version,finished_item_id=finished.id,output_quantity=quantity(data.output_quantity),work_center_id=data.work_center_id,standard_hours=data.standard_hours,status="ACTIVE")
    component_ids=set()
    for source in data.lines:
        component=get_item(db,data.company_id,source.component_item_id)
        if component.id==finished.id:raise HTTPException(422,"Finished item cannot be its own component")
        if component.id in component_ids:raise HTTPException(422,"Duplicate component in BOM")
        component_ids.add(component.id);bom.lines.append(BillOfMaterialLine(component_item_id=component.id,quantity=quantity(source.quantity),scrap_percent=source.scrap_percent))
    db.add(bom);db.flush()
    write_audit(db,action="BOM_CREATED",entity_type="BOM",entity_id=bom.id,user_id=user.id,company_id=data.company_id,after={"code":bom.code,"version":bom.version,"finished_item":finished.code,"components":len(bom.lines)})
    db.commit();return {"id":bom.id,"code":bom.code,"version":bom.version,"finished_item":finished.code,"output_quantity":bom.output_quantity,"standard_hours":bom.standard_hours,"status":bom.status}


@router.get("/boms")
def list_boms(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"manufacturing.read")
    rows=db.scalars(select(BillOfMaterial).where(BillOfMaterial.company_id==company_id).options(selectinload(BillOfMaterial.lines).selectinload(BillOfMaterialLine.component_item)).order_by(BillOfMaterial.code,BillOfMaterial.version.desc())).all()
    return [{"id":r.id,"code":r.code,"version":r.version,"finished_item_id":r.finished_item_id,"finished_item_code":r.finished_item.code,"finished_item_name_ar":r.finished_item.name_ar,"finished_item_name_en":r.finished_item.name_en,"output_quantity":r.output_quantity,"standard_hours":r.standard_hours,"work_center":r.work_center.name_en if r.work_center else None,"status":r.status,"lines":[{"component_item_id":l.component_item_id,"component_code":l.component_item.code,"component_name_ar":l.component_item.name_ar,"component_name_en":l.component_item.name_en,"quantity":l.quantity,"scrap_percent":l.scrap_percent} for l in r.lines]} for r in rows]


@router.post("/orders",status_code=201)
def create_production_order(data:ProductionOrderIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,data.company_id,"manufacturing.manage")
    ensure_open_period(db,data.company_id,data.order_date)
    bom=db.scalar(select(BillOfMaterial).where(BillOfMaterial.id==data.bom_id,BillOfMaterial.company_id==data.company_id,BillOfMaterial.status=="ACTIVE").options(selectinload(BillOfMaterial.lines)))
    if not bom:raise HTTPException(404,"Active BOM not found")
    warehouse=get_warehouse(db,data.company_id,data.warehouse_id)
    factor=Decimal(str(data.planned_quantity))/Decimal(str(bom.output_quantity))
    shortages=[]
    for line in bom.lines:
        required=quantity(factor*line.quantity*(Decimal("1")+line.scrap_percent/Decimal("100")))
        available=stock_balance(db,data.company_id,warehouse.id,line.component_item_id)
        if required>available:shortages.append({"item_id":line.component_item_id,"required":required,"available":available})
    if shortages:raise HTTPException(422,detail={"message":"Insufficient components","shortages":shortages})
    order=ProductionOrder(company_id=data.company_id,number=_number(db,data.company_id,data.order_date.year),order_date=data.order_date,bom_id=bom.id,warehouse_id=warehouse.id,planned_quantity=quantity(data.planned_quantity),planned_hours=money(bom.standard_hours*factor),status="RELEASED",created_by=user.id)
    db.add(order);db.flush();write_audit(db,action="PRODUCTION_ORDER_RELEASED",entity_type="PRODUCTION_ORDER",entity_id=order.id,user_id=user.id,company_id=data.company_id,after={"number":order.number,"planned_quantity":str(order.planned_quantity),"bom":bom.code})
    db.commit();return {"id":order.id,"number":order.number,"status":order.status,"planned_quantity":order.planned_quantity,"planned_hours":order.planned_hours}


@router.post("/orders/{order_id}/issue-materials")
def issue_materials(order_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    order=db.scalar(select(ProductionOrder).where(ProductionOrder.id==order_id).options(selectinload(ProductionOrder.bom).selectinload(BillOfMaterial.lines).selectinload(BillOfMaterialLine.component_item)))
    if not order:raise HTTPException(404,"Production order not found")
    ensure_permission(db,user,order.company_id,"manufacturing.issue")
    if order.status!="RELEASED":raise HTTPException(409,"Materials can only be issued for a released order")
    factor=Decimal(order.planned_quantity)/Decimal(order.bom.output_quantity);wip=get_account(db,order.company_id,"115010");journal_lines=[];movement_rows=[];total=Decimal("0")
    for line in order.bom.lines:
        required=quantity(factor*line.quantity*(Decimal("1")+line.scrap_percent/Decimal("100")));available=stock_balance(db,order.company_id,order.warehouse_id,line.component_item_id)
        if required>available:raise HTTPException(422,f"Insufficient stock for {line.component_item.code}. Available: {available}")
        value=stock_value(db,order.company_id,order.warehouse_id,line.component_item_id);unit_cost=money(value/available) if available else money(line.component_item.standard_cost);line_cost=money(required*unit_cost);total+=line_cost
        journal_lines.extend([{"account_id":wip.id,"debit":line_cost,"credit":0,"description":f"WIP {order.number}"},{"account_id":line.component_item.inventory_account_id,"debit":0,"credit":line_cost,"description":line.component_item.code}])
        movement_rows.append((line,required,unit_cost,line_cost))
    journal=create_posted_journal(db,company_id=order.company_id,user_id=user.id,posting_date=order.order_date,reference=order.number,description=f"Material issue for {order.number}",lines=journal_lines)
    for line,required,unit_cost,line_cost in movement_rows:
        db.add(StockMovement(company_id=order.company_id,warehouse_id=order.warehouse_id,item_id=line.component_item_id,movement_date=order.order_date,movement_type="PRODUCTION_ISSUE",quantity=-required,unit_cost=unit_cost,total_cost=-line_cost,reference_type="PRODUCTION_ORDER",reference_id=order.id,journal_id=journal.id,created_by=user.id))
    order.material_cost=money(total);order.total_cost=money(total);order.issue_journal_id=journal.id;order.status="IN_PROCESS"
    write_audit(db,action="PRODUCTION_MATERIALS_ISSUED",entity_type="PRODUCTION_ORDER",entity_id=order.id,user_id=user.id,company_id=order.company_id,after={"material_cost":str(order.material_cost),"journal":journal.number})
    db.commit();return {"id":order.id,"number":order.number,"status":order.status,"material_cost":order.material_cost,"journal_number":journal.number}


@router.post("/orders/{order_id}/complete")
def complete_order(order_id:int,data:CompleteOrderIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    order=db.scalar(select(ProductionOrder).where(ProductionOrder.id==order_id).options(selectinload(ProductionOrder.bom)))
    if not order:raise HTTPException(404,"Production order not found")
    ensure_permission(db,user,order.company_id,"manufacturing.complete")
    if order.status!="IN_PROCESS":raise HTTPException(409,"Order must be in process")
    if quantity(data.completed_quantity)>quantity(order.planned_quantity):raise HTTPException(422,"Completed quantity cannot exceed planned quantity")
    ensure_open_period(db,order.company_id,data.completion_date)
    wc=order.bom.work_center;hours=Decimal(str(data.actual_hours));labor=money(hours*(wc.hourly_labor_rate if wc else Decimal("0")));overhead=money(hours*(wc.hourly_overhead_rate if wc else Decimal("0")));total=money(order.material_cost+labor+overhead)
    wip=get_account(db,order.company_id,"115010");labor_absorb=get_account(db,order.company_id,"611010");overhead_absorb=get_account(db,order.company_id,"615010");finished=order.bom.finished_item
    lines=[]
    if labor:lines.extend([{"account_id":wip.id,"debit":labor,"credit":0},{"account_id":labor_absorb.id,"debit":0,"credit":labor}])
    if overhead:lines.extend([{"account_id":wip.id,"debit":overhead,"credit":0},{"account_id":overhead_absorb.id,"debit":0,"credit":overhead}])
    lines.extend([{"account_id":finished.inventory_account_id,"debit":total,"credit":0},{"account_id":wip.id,"debit":0,"credit":total}])
    journal=create_posted_journal(db,company_id=order.company_id,user_id=user.id,posting_date=data.completion_date,reference=order.number,description=f"Production completion {order.number}",lines=lines)
    qty=quantity(data.completed_quantity);unit_cost=money(total/qty)
    movement=StockMovement(company_id=order.company_id,warehouse_id=order.warehouse_id,item_id=finished.id,movement_date=data.completion_date,movement_type="PRODUCTION_RECEIPT",quantity=qty,unit_cost=unit_cost,total_cost=total,lot_number=data.lot_number,expiry_date=data.expiry_date,reference_type="PRODUCTION_ORDER",reference_id=order.id,journal_id=journal.id,created_by=user.id)
    db.add(movement);order.completed_quantity=qty;order.actual_hours=hours;order.labor_cost=labor;order.overhead_cost=overhead;order.total_cost=total;order.completion_journal_id=journal.id;order.status="COMPLETED"
    write_audit(db,action="PRODUCTION_ORDER_COMPLETED",entity_type="PRODUCTION_ORDER",entity_id=order.id,user_id=user.id,company_id=order.company_id,after={"completed_quantity":str(qty),"material_cost":str(order.material_cost),"labor_cost":str(labor),"overhead_cost":str(overhead),"total_cost":str(total),"unit_cost":str(unit_cost),"journal":journal.number})
    db.commit();return {"id":order.id,"number":order.number,"status":order.status,"completed_quantity":order.completed_quantity,"material_cost":order.material_cost,"labor_cost":order.labor_cost,"overhead_cost":order.overhead_cost,"total_cost":order.total_cost,"unit_cost":unit_cost,"journal_number":journal.number}


@router.post("/orders/{order_id}/runs",status_code=201)
def record_run(order_id:int,data:RunIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    order=db.get(ProductionOrder,order_id)
    if not order:raise HTTPException(404,"Production order not found")
    ensure_permission(db,user,order.company_id,"manufacturing.manage")
    if data.downtime_minutes>=data.planned_minutes:raise HTTPException(422,"Downtime must be less than planned time")
    if data.good_units>data.total_units:raise HTTPException(422,"Good units cannot exceed total units")
    operating=Decimal(str(data.planned_minutes-data.downtime_minutes));availability=Decimal(str(operating/data.planned_minutes));performance=Decimal(str((data.ideal_cycle_seconds*data.total_units)/(operating*Decimal("60"))));quality=Decimal(str(data.good_units/data.total_units));oee=availability*performance*quality
    run=ProductionRun(company_id=order.company_id,production_order_id=order.id,run_date=data.run_date,planned_minutes=data.planned_minutes,downtime_minutes=data.downtime_minutes,ideal_cycle_seconds=data.ideal_cycle_seconds,total_units=data.total_units,good_units=data.good_units,availability=money(availability*100),performance=money(performance*100),quality=money(quality*100),oee=money(oee*100),created_by=user.id)
    db.add(run);db.flush();write_audit(db,action="OEE_RUN_RECORDED",entity_type="PRODUCTION_RUN",entity_id=run.id,user_id=user.id,company_id=order.company_id,after={"order":order.number,"availability":str(run.availability),"performance":str(run.performance),"quality":str(run.quality),"oee":str(run.oee)})
    db.commit();return {"id":run.id,"production_order":order.number,"availability":run.availability,"performance":run.performance,"quality":run.quality,"oee":run.oee}


@router.get("/orders")
def list_orders(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"manufacturing.read")
    rows=db.scalars(select(ProductionOrder).where(ProductionOrder.company_id==company_id).options(selectinload(ProductionOrder.bom)).order_by(ProductionOrder.id.desc())).all()
    return [{"id":r.id,"number":r.number,"order_date":r.order_date,"bom":r.bom.code,"finished_item":r.bom.finished_item.name_en,"planned_quantity":r.planned_quantity,"completed_quantity":r.completed_quantity,"planned_hours":r.planned_hours,"actual_hours":r.actual_hours,"status":r.status,"material_cost":r.material_cost,"labor_cost":r.labor_cost,"overhead_cost":r.overhead_cost,"total_cost":r.total_cost} for r in rows]


@router.get("/oee")
def oee_summary(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"manufacturing.read")
    rows=db.scalars(select(ProductionRun).where(ProductionRun.company_id==company_id).order_by(ProductionRun.run_date.desc(),ProductionRun.id.desc())).all()
    if not rows:return {"runs":0,"availability":0,"performance":0,"quality":0,"oee":0,"history":[]}
    def avg(field):return money(sum((Decimal(getattr(r,field)) for r in rows),Decimal("0"))/len(rows))
    return {"runs":len(rows),"availability":avg("availability"),"performance":avg("performance"),"quality":avg("quality"),"oee":avg("oee"),"history":[{"id":r.id,"date":r.run_date,"order_id":r.production_order_id,"availability":r.availability,"performance":r.performance,"quality":r.quality,"oee":r.oee} for r in rows[:20]]}
