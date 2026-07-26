from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import CRMLead, CRMOpportunity, MarketingCampaign, User
from app.services.audit import write_audit

router = APIRouter(prefix="/crm", tags=["crm and marketing"])


class CampaignIn(BaseModel):
    company_id: int
    code: str = Field(min_length=2, max_length=60)
    name_ar: str = Field(min_length=2, max_length=250)
    name_en: str = Field(min_length=2, max_length=250)
    channel: str = "DIGITAL"
    budget: Decimal = Field(default=Decimal("0"), ge=0)
    start_date: date | None = None
    end_date: date | None = None
    owner_user_id: int | None = None


class LeadIn(BaseModel):
    company_id: int
    campaign_id: int | None = None
    source: str = "DIRECT"
    name: str = Field(min_length=2, max_length=250)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    owner_user_id: int | None = None
    estimated_value: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class ConvertLeadIn(BaseModel):
    title: str = Field(min_length=2, max_length=250)
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    probability: int = Field(default=25, ge=0, le=100)
    expected_close_date: date | None = None
    owner_user_id: int | None = None


class OpportunityUpdate(BaseModel):
    stage: str
    probability: int = Field(ge=0, le=100)
    amount: Decimal = Field(ge=0)
    expected_close_date: date | None = None
    loss_reason: str | None = None


def _next_number(db: Session, model, company_id: int, prefix: str) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{utc_now():%y%m}-{int(count)+1:05d}"


def _lead_dict(row: CRMLead) -> dict:
    return {
        "id": row.id,
        "number": row.number,
        "campaign_id": row.campaign_id,
        "source": row.source,
        "name": row.name,
        "email": row.email,
        "phone": row.phone,
        "status": row.status,
        "owner_user_id": row.owner_user_id,
        "estimated_value": row.estimated_value,
        "created_at": row.created_at,
        "converted_at": row.converted_at,
    }


def _opportunity_dict(row: CRMOpportunity) -> dict:
    weighted = Decimal(row.amount or 0) * Decimal(row.probability or 0) / Decimal(100)
    return {
        "id": row.id,
        "number": row.number,
        "lead_id": row.lead_id,
        "campaign_id": row.campaign_id,
        "title": row.title,
        "stage": row.stage,
        "probability": row.probability,
        "amount": row.amount,
        "weighted_amount": weighted.quantize(Decimal("0.01")),
        "expected_close_date": row.expected_close_date,
        "owner_user_id": row.owner_user_id,
        "loss_reason": row.loss_reason,
        "created_at": row.created_at,
        "closed_at": row.closed_at,
    }


@router.get("/summary")
def summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "crm.read")
    leads = db.scalar(select(func.count(CRMLead.id)).where(CRMLead.company_id == company_id)) or 0
    new_leads = db.scalar(select(func.count(CRMLead.id)).where(CRMLead.company_id == company_id, CRMLead.status == "NEW")) or 0
    opportunities = db.scalars(select(CRMOpportunity).where(CRMOpportunity.company_id == company_id)).all()
    open_opportunities = [row for row in opportunities if row.stage not in {"WON", "LOST"}]
    pipeline = sum((Decimal(row.amount or 0) for row in open_opportunities), Decimal("0"))
    weighted = sum((Decimal(row.amount or 0) * Decimal(row.probability or 0) / Decimal(100) for row in open_opportunities), Decimal("0"))
    won = sum((Decimal(row.amount or 0) for row in opportunities if row.stage == "WON"), Decimal("0"))
    campaigns = db.scalars(select(MarketingCampaign).where(MarketingCampaign.company_id == company_id)).all()
    campaign_budget = sum((Decimal(row.budget or 0) for row in campaigns), Decimal("0"))
    campaign_cost = sum((Decimal(row.actual_cost or 0) for row in campaigns), Decimal("0"))
    return {
        "company_id": company_id,
        "leads": leads,
        "new_leads": new_leads,
        "open_opportunities": len(open_opportunities),
        "pipeline_amount": pipeline.quantize(Decimal("0.01")),
        "weighted_pipeline": weighted.quantize(Decimal("0.01")),
        "won_amount": won.quantize(Decimal("0.01")),
        "campaigns": len(campaigns),
        "campaign_budget": campaign_budget.quantize(Decimal("0.01")),
        "campaign_actual_cost": campaign_cost.quantize(Decimal("0.01")),
        "engine": "LEAD_CAMPAIGN_OPPORTUNITY_PIPELINE",
    }


@router.post("/campaigns", status_code=201)
def create_campaign(data: CampaignIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "crm.manage")
    if data.start_date and data.end_date and data.end_date < data.start_date:
        raise HTTPException(422, "Campaign end date cannot precede start date")
    if db.scalar(select(MarketingCampaign).where(MarketingCampaign.company_id == data.company_id, MarketingCampaign.code == data.code)):
        raise HTTPException(409, "Campaign code already exists")
    row = MarketingCampaign(
        company_id=data.company_id,
        code=data.code.upper(),
        name_ar=data.name_ar,
        name_en=data.name_en,
        channel=data.channel.upper(),
        budget=data.budget,
        start_date=data.start_date,
        end_date=data.end_date,
        owner_user_id=data.owner_user_id,
        created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="MARKETING_CAMPAIGN_CREATED", entity_type="MARKETING_CAMPAIGN", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"code": row.code, "channel": row.channel, "budget": row.budget})
    db.commit()
    return {"id": row.id, "code": row.code, "status": row.status, "budget": row.budget}


@router.get("/campaigns")
def list_campaigns(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "crm.read")
    rows = db.scalars(select(MarketingCampaign).where(MarketingCampaign.company_id == company_id).order_by(MarketingCampaign.created_at.desc())).all()
    return [{"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "channel": row.channel, "budget": row.budget, "actual_cost": row.actual_cost, "start_date": row.start_date, "end_date": row.end_date, "status": row.status} for row in rows]


@router.post("/leads", status_code=201)
def create_lead(data: LeadIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "crm.manage")
    if data.campaign_id:
        campaign = db.get(MarketingCampaign, data.campaign_id)
        if not campaign or campaign.company_id != data.company_id:
            raise HTTPException(404, "Marketing campaign not found")
    row = CRMLead(
        company_id=data.company_id,
        number=_next_number(db, CRMLead, data.company_id, "LEAD"),
        campaign_id=data.campaign_id,
        source=data.source.upper(),
        name=data.name,
        email=str(data.email).lower() if data.email else None,
        phone=data.phone,
        owner_user_id=data.owner_user_id,
        estimated_value=data.estimated_value,
        notes=data.notes,
        created_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="CRM_LEAD_CREATED", entity_type="CRM_LEAD", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"number": row.number, "source": row.source, "estimated_value": row.estimated_value})
    db.commit()
    return _lead_dict(row)


@router.get("/leads")
def list_leads(company_id: int, status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "crm.read")
    query = select(CRMLead).where(CRMLead.company_id == company_id)
    if status:
        query = query.where(CRMLead.status == status.upper())
    rows = db.scalars(query.order_by(CRMLead.created_at.desc())).all()
    return [_lead_dict(row) for row in rows]


@router.post("/leads/{lead_id}/convert", status_code=201)
def convert_lead(lead_id: int, data: ConvertLeadIn, company_id: int = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "crm.manage")
    lead = db.get(CRMLead, lead_id)
    if not lead or lead.company_id != company_id:
        raise HTTPException(404, "Lead not found")
    if lead.status == "CONVERTED":
        raise HTTPException(409, "Lead is already converted")
    row = CRMOpportunity(
        company_id=company_id,
        number=_next_number(db, CRMOpportunity, company_id, "OPP"),
        lead_id=lead.id,
        campaign_id=lead.campaign_id,
        title=data.title,
        stage="QUALIFICATION",
        probability=data.probability,
        amount=data.amount,
        expected_close_date=data.expected_close_date,
        owner_user_id=data.owner_user_id or lead.owner_user_id,
        created_by=user.id,
    )
    lead.status = "CONVERTED"; lead.converted_at = utc_now()
    db.add(row); db.flush()
    write_audit(db, action="CRM_LEAD_CONVERTED", entity_type="CRM_OPPORTUNITY", entity_id=row.id, user_id=user.id, company_id=company_id, after={"lead_id": lead.id, "number": row.number, "amount": row.amount, "probability": row.probability})
    db.commit()
    return _opportunity_dict(row)


@router.get("/opportunities")
def list_opportunities(company_id: int, stage: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "crm.read")
    query = select(CRMOpportunity).where(CRMOpportunity.company_id == company_id)
    if stage:
        query = query.where(CRMOpportunity.stage == stage.upper())
    rows = db.scalars(query.order_by(CRMOpportunity.expected_close_date, CRMOpportunity.created_at.desc())).all()
    return [_opportunity_dict(row) for row in rows]


@router.patch("/opportunities/{opportunity_id}")
def update_opportunity(opportunity_id: int, data: OpportunityUpdate, company_id: int = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "crm.manage")
    row = db.get(CRMOpportunity, opportunity_id)
    if not row or row.company_id != company_id:
        raise HTTPException(404, "Opportunity not found")
    stage = data.stage.upper()
    if stage not in {"QUALIFICATION", "PROPOSAL", "NEGOTIATION", "WON", "LOST"}:
        raise HTTPException(422, "Unsupported opportunity stage")
    if stage == "LOST" and not data.loss_reason:
        raise HTTPException(422, "Loss reason is required")
    before = {"stage": row.stage, "probability": row.probability, "amount": row.amount}
    row.stage = stage; row.probability = data.probability; row.amount = data.amount; row.expected_close_date = data.expected_close_date; row.loss_reason = data.loss_reason
    if stage in {"WON", "LOST"}:
        row.closed_at = utc_now()
    write_audit(db, action="CRM_OPPORTUNITY_UPDATED", entity_type="CRM_OPPORTUNITY", entity_id=row.id, user_id=user.id, company_id=company_id, before=before, after={"stage": row.stage, "probability": row.probability, "amount": row.amount, "loss_reason": row.loss_reason})
    db.commit()
    return _opportunity_dict(row)
