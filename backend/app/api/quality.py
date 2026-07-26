from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import Item, NonConformance, QualityInspection, User
from app.services.audit import write_audit
from app.services.operations import get_item, money, quantity

router = APIRouter(prefix="/quality", tags=["quality and inspection"])


class InspectionIn(BaseModel):
    company_id: int
    inspection_date: date
    inspection_type: str
    reference_type: str
    reference_id: int
    item_id: int | None = None
    lot_number: str | None = None
    inspected_quantity: Decimal = Field(gt=0)
    accepted_quantity: Decimal = Field(ge=0)
    rejected_quantity: Decimal = Field(ge=0)
    notes: str | None = None
    severity: str = "MEDIUM"


class NCRUpdateIn(BaseModel):
    root_cause: str = Field(min_length=2)
    corrective_action: str = Field(min_length=2)
    due_date: date | None = None
    status: str = "IN_PROGRESS"


def _number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{count + 1:05d}"


@router.post("/inspections", status_code=201)
def create_inspection(data: InspectionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "quality.manage")
    inspected=quantity(data.inspected_quantity);accepted=quantity(data.accepted_quantity);rejected=quantity(data.rejected_quantity)
    if accepted+rejected!=inspected:raise HTTPException(422,"Accepted plus rejected quantity must equal inspected quantity")
    if data.item_id:get_item(db,data.company_id,data.item_id)
    result="PASS" if rejected==0 else "FAIL" if accepted==0 else "PARTIAL"
    inspection=QualityInspection(company_id=data.company_id,number=_number(db,QualityInspection,data.company_id,"QI",data.inspection_date.year),inspection_date=data.inspection_date,inspection_type=data.inspection_type.upper(),reference_type=data.reference_type.upper(),reference_id=data.reference_id,item_id=data.item_id,lot_number=data.lot_number,inspected_quantity=inspected,accepted_quantity=accepted,rejected_quantity=rejected,result=result,notes=data.notes,created_by=user.id)
    db.add(inspection);db.flush();ncr=None
    if rejected>0:
        ncr=NonConformance(company_id=data.company_id,number=_number(db,NonConformance,data.company_id,"NCR",data.inspection_date.year),inspection_id=inspection.id,severity=data.severity.upper(),description=f"Rejected {rejected} of {inspected} during {data.inspection_type}",owner_user_id=user.id,due_date=None,status="OPEN")
        db.add(ncr);db.flush()
    write_audit(db,action="QUALITY_INSPECTION_RECORDED",entity_type="QUALITY_INSPECTION",entity_id=inspection.id,user_id=user.id,company_id=data.company_id,after={"number":inspection.number,"result":inspection.result,"rejected":str(rejected),"ncr":ncr.number if ncr else None})
    db.commit();return {"id":inspection.id,"number":inspection.number,"result":inspection.result,"inspected_quantity":inspection.inspected_quantity,"accepted_quantity":inspection.accepted_quantity,"rejected_quantity":inspection.rejected_quantity,"ncr":{"id":ncr.id,"number":ncr.number,"status":ncr.status} if ncr else None}


@router.get("/inspections")
def list_inspections(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"quality.read")
    rows=db.scalars(select(QualityInspection).where(QualityInspection.company_id==company_id).order_by(QualityInspection.inspection_date.desc(),QualityInspection.id.desc())).all()
    return [{"id":r.id,"number":r.number,"inspection_date":r.inspection_date,"inspection_type":r.inspection_type,"reference_type":r.reference_type,"reference_id":r.reference_id,"item_id":r.item_id,"item_code":r.item.code if r.item else None,"lot_number":r.lot_number,"inspected_quantity":r.inspected_quantity,"accepted_quantity":r.accepted_quantity,"rejected_quantity":r.rejected_quantity,"result":r.result,"notes":r.notes} for r in rows]


@router.get("/ncrs")
def list_ncrs(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"quality.read")
    rows=db.scalars(select(NonConformance).where(NonConformance.company_id==company_id).order_by(NonConformance.id.desc())).all()
    return [{"id":r.id,"number":r.number,"inspection_id":r.inspection_id,"severity":r.severity,"description":r.description,"root_cause":r.root_cause,"corrective_action":r.corrective_action,"due_date":r.due_date,"status":r.status} for r in rows]


@router.patch("/ncrs/{ncr_id}")
def update_ncr(ncr_id:int,data:NCRUpdateIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ncr=db.get(NonConformance,ncr_id)
    if not ncr:raise HTTPException(404,"Non-conformance not found")
    ensure_permission(db,user,ncr.company_id,"quality.manage")
    status=data.status.upper()
    if status not in {"OPEN","IN_PROGRESS","VERIFIED","CLOSED"}:raise HTTPException(422,"Invalid NCR status")
    before={"status":ncr.status,"root_cause":ncr.root_cause,"corrective_action":ncr.corrective_action}
    ncr.root_cause=data.root_cause;ncr.corrective_action=data.corrective_action;ncr.due_date=data.due_date;ncr.status=status
    write_audit(db,action="NCR_UPDATED",entity_type="NON_CONFORMANCE",entity_id=ncr.id,user_id=user.id,company_id=ncr.company_id,before=before,after={"status":ncr.status,"root_cause":ncr.root_cause,"corrective_action":ncr.corrective_action})
    db.commit();return {"id":ncr.id,"number":ncr.number,"status":ncr.status}


@router.get("/summary")
def quality_summary(company_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"quality.read")
    inspections=db.scalars(select(QualityInspection).where(QualityInspection.company_id==company_id)).all();ncrs=db.scalars(select(NonConformance).where(NonConformance.company_id==company_id)).all()
    inspected=sum((Decimal(r.inspected_quantity) for r in inspections),Decimal("0"));accepted=sum((Decimal(r.accepted_quantity) for r in inspections),Decimal("0"));rejected=sum((Decimal(r.rejected_quantity) for r in inspections),Decimal("0"))
    return {"inspections":len(inspections),"pass":sum(1 for r in inspections if r.result=="PASS"),"partial":sum(1 for r in inspections if r.result=="PARTIAL"),"fail":sum(1 for r in inspections if r.result=="FAIL"),"inspected_quantity":quantity(inspected),"accepted_quantity":quantity(accepted),"rejected_quantity":quantity(rejected),"acceptance_rate":money(accepted/inspected*100) if inspected else Decimal("0"),"open_ncrs":sum(1 for r in ncrs if r.status!="CLOSED"),"closed_ncrs":sum(1 for r in ncrs if r.status=="CLOSED")}
