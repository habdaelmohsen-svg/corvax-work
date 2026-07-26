from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base
from app.models.types import EncryptedDecimal, EncryptedString

class GovernanceRisk(Base):
    __tablename__ = "governance_risks"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_governance_risk_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    category = Column(String(50), nullable=False, default="OPERATIONAL")
    likelihood = Column(Integer, nullable=False, default=1)
    impact = Column(Integer, nullable=False, default=1)
    inherent_score = Column(Integer, nullable=False, default=1)
    residual_score = Column(Integer, nullable=False, default=1)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(25), nullable=False, default="OPEN", index=True)
    mitigation_due_date = Column(Date)
    description = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

class GovernanceControl(Base):
    __tablename__ = "governance_controls"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_governance_control_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_id = Column(Integer, ForeignKey("governance_risks.id", ondelete="SET NULL"), index=True)
    code = Column(String(50), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    control_type = Column(String(30), nullable=False, default="PREVENTIVE")
    frequency = Column(String(30), nullable=False, default="MONTHLY")
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    design_status = Column(String(25), nullable=False, default="EFFECTIVE")
    operating_status = Column(String(25), nullable=False, default="NOT_TESTED")
    last_test_date = Column(Date)
    next_test_date = Column(Date)
    description = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class AuditEngagement(Base):
    __tablename__ = "audit_engagements"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_audit_engagement_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    audit_type = Column(String(30), nullable=False, default="INTERNAL")
    scope = Column(Text)
    status = Column(String(25), nullable=False, default="PLANNED", index=True)
    risk_rating = Column(String(20), nullable=False, default="MEDIUM")
    planned_start = Column(Date)
    planned_end = Column(Date)
    actual_start = Column(Date)
    actual_end = Column(Date)
    lead_auditor_id = Column(Integer, ForeignKey("users.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)

class AuditFinding(Base):
    __tablename__ = "audit_findings"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_audit_finding_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    engagement_id = Column(Integer, ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    severity = Column(String(20), nullable=False, default="MEDIUM", index=True)
    description = Column(Text, nullable=False)
    root_cause = Column(Text)
    recommendation = Column(Text)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(Date)
    status = Column(String(25), nullable=False, default="OPEN", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    closed_at = Column(DateTime)

class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id = Column(Integer, ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(Date)
    status = Column(String(25), nullable=False, default="OPEN", index=True)
    completion_percent = Column(Integer, nullable=False, default=0)
    evidence_reference = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime)

class ControlledDocument(Base):
    __tablename__ = "controlled_documents"
    __table_args__ = (UniqueConstraint("company_id", "code", "version", name="uq_controlled_document_version"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(60), nullable=False, index=True)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    document_type = Column(String(40), nullable=False, default="POLICY")
    version = Column(String(20), nullable=False, default="1.0")
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    effective_date = Column(Date)
    review_date = Column(Date)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    content_summary = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class ITAsset(Base):
    __tablename__ = "it_assets"
    __table_args__ = (UniqueConstraint("company_id", "asset_tag", name="uq_it_asset_company_tag"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_tag = Column(String(60), nullable=False, index=True)
    asset_type = Column(String(40), nullable=False)
    name = Column(String(250), nullable=False)
    serial_number = Column(String(120))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    assigned_user_id = Column(Integer, ForeignKey("users.id"))
    purchase_date = Column(Date)
    warranty_end = Column(Date)
    status = Column(String(25), nullable=False, default="IN_SERVICE", index=True)
    criticality = Column(String(20), nullable=False, default="MEDIUM")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class ServiceTicket(Base):
    __tablename__ = "service_tickets"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_service_ticket_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    category = Column(String(50), nullable=False, default="GENERAL")
    subject = Column(String(250), nullable=False)
    description = Column(Text)
    priority = Column(String(20), nullable=False, default="MEDIUM", index=True)
    status = Column(String(25), nullable=False, default="OPEN", index=True)
    requester_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignee_user_id = Column(Integer, ForeignKey("users.id"))
    opened_at = Column(DateTime, nullable=False, default=utc_now)
    due_at = Column(DateTime)
    resolved_at = Column(DateTime)
    resolution = Column(Text)

# -------------------- CRM and marketing v1.0 --------------------

class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_marketing_campaign_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(60), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    channel = Column(String(50), nullable=False, default="DIGITAL")
    budget = Column(Numeric(18, 2), nullable=False, default=0)
    actual_cost = Column(Numeric(18, 2), nullable=False, default=0)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(25), nullable=False, default="PLANNED", index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class CRMLead(Base):
    __tablename__ = "crm_leads"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_crm_lead_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("marketing_campaigns.id", ondelete="SET NULL"), index=True)
    source = Column(String(60), nullable=False, default="DIRECT")
    name = Column(String(250), nullable=False)
    email = Column(String(320))
    phone = Column(String(50))
    status = Column(String(25), nullable=False, default="NEW", index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    estimated_value = Column(Numeric(18, 2), nullable=False, default=0)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    converted_at = Column(DateTime)

class CRMOpportunity(Base):
    __tablename__ = "crm_opportunities"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_crm_opportunity_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("crm_leads.id", ondelete="SET NULL"), index=True)
    campaign_id = Column(Integer, ForeignKey("marketing_campaigns.id", ondelete="SET NULL"), index=True)
    customer_id = Column(Integer, ForeignKey("parties.id", ondelete="SET NULL"))
    title = Column(String(250), nullable=False)
    stage = Column(String(30), nullable=False, default="QUALIFICATION", index=True)
    probability = Column(Integer, nullable=False, default=10)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    expected_close_date = Column(Date)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    loss_reason = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    closed_at = Column(DateTime)

# -------------------- Financial assurance and Big Four-style certification v1.0 RC2 --------------------

class FinancialAssuranceRun(Base):
    __tablename__ = "financial_assurance_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_period_id", "scope", name="uq_assurance_company_period_scope"),
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_period_id = Column(Integer, ForeignKey("fiscal_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    scope = Column(String(30), nullable=False, default="MONTH_END")
    materiality_amount = Column(Numeric(18, 2), nullable=False)
    performance_materiality = Column(Numeric(18, 2), nullable=False)
    trivial_threshold = Column(Numeric(18, 2), nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    conclusion = Column(String(30), nullable=False, default="NOT_ASSESSED")
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    management_representation = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

class FinancialAssuranceCheck(Base):
    __tablename__ = "financial_assurance_checks"
    __table_args__ = (
        UniqueConstraint("assurance_run_id", "code", name="uq_assurance_check_code"),
    )
    id = Column(Integer, primary_key=True)
    assurance_run_id = Column(Integer, ForeignKey("financial_assurance_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    category = Column(String(40), nullable=False)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    status = Column(String(20), nullable=False)
    severity = Column(String(20), nullable=False, default="MEDIUM")
    blocking = Column(Boolean, nullable=False, default=False)
    metric_value = Column(Numeric(18, 2))
    threshold_value = Column(Numeric(18, 2))
    details = Column(Text)
    remediation_owner_id = Column(Integer, ForeignKey("users.id"))
    remediation_due_date = Column(Date)
    checked_at = Column(DateTime, nullable=False, default=utc_now)

class FinancialCertification(Base):
    __tablename__ = "financial_certifications"
    __table_args__ = (
        UniqueConstraint("assurance_run_id", "certification_role", name="uq_assurance_certification_role"),
    )
    id = Column(Integer, primary_key=True)
    assurance_run_id = Column(Integer, ForeignKey("financial_assurance_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    certification_role = Column(String(40), nullable=False)
    certification_status = Column(String(25), nullable=False, default="PENDING")
    statement_ar = Column(Text, nullable=False)
    statement_en = Column(Text, nullable=False)
    exceptions = Column(Text)
    certified_by = Column(Integer, ForeignKey("users.id"))
    certified_at = Column(DateTime)


# -------------------- Enterprise Quality Management System (QMS) v1.1 --------------------

__all__ = ['GovernanceRisk', 'GovernanceControl', 'AuditEngagement', 'AuditFinding', 'CorrectiveAction', 'ControlledDocument', 'ITAsset', 'ServiceTicket', 'MarketingCampaign', 'CRMLead', 'CRMOpportunity', 'FinancialAssuranceRun', 'FinancialAssuranceCheck', 'FinancialCertification']
