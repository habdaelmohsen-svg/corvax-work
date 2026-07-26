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

class QualityObjective(Base):
    __tablename__ = "quality_objectives"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_quality_objective_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    metric_name = Column(String(200), nullable=False)
    unit = Column(String(30), nullable=False, default="PERCENT")
    baseline_value = Column(Numeric(18, 4), nullable=False, default=0)
    target_value = Column(Numeric(18, 4), nullable=False)
    current_value = Column(Numeric(18, 4), nullable=False, default=0)
    frequency = Column(String(20), nullable=False, default="MONTHLY")
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)

class QualityInspectionPlan(Base):
    __tablename__ = "quality_inspection_plans"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_quality_plan_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"))
    inspection_stage = Column(String(30), nullable=False)
    sampling_method = Column(String(30), nullable=False, default="FIXED")
    sample_size = Column(Numeric(18, 4), nullable=False, default=1)
    acceptance_number = Column(Integer, nullable=False, default=0)
    rejection_number = Column(Integer, nullable=False, default=1)
    specification = Column(Text)
    test_method = Column(Text)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    item = relationship("Item", lazy="joined")

class QualityAction(Base):
    __tablename__ = "quality_actions"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_quality_action_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    action_type = Column(String(20), nullable=False, default="CORRECTIVE")
    source_type = Column(String(30), nullable=False)
    source_id = Column(Integer, nullable=False)
    title = Column(String(250), nullable=False)
    description = Column(Text, nullable=False)
    root_cause_method = Column(String(30), nullable=False, default="5_WHY")
    root_cause = Column(Text)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    effectiveness_result = Column(String(20))
    effectiveness_notes = Column(Text)
    verified_by = Column(Integer, ForeignKey("users.id"))
    verified_at = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class CustomerQualityComplaint(Base):
    __tablename__ = "customer_quality_complaints"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_quality_complaint_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    received_date = Column(Date, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("parties.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    lot_number = Column(String(80))
    channel = Column(String(30), nullable=False, default="DIRECT")
    severity = Column(String(20), nullable=False, default="MEDIUM")
    description = Column(Text, nullable=False)
    immediate_containment = Column(Text)
    root_cause = Column(Text)
    resolution = Column(Text)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(Date)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    closed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    closed_at = Column(DateTime)
    customer = relationship("Party", foreign_keys=[customer_id], lazy="joined")
    item = relationship("Item", lazy="joined")

class SupplierQualityEvaluation(Base):
    __tablename__ = "supplier_quality_evaluations"
    __table_args__ = (UniqueConstraint("company_id", "supplier_id", "period_start", "period_end", name="uq_supplier_quality_period"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    quality_score = Column(Numeric(8, 2), nullable=False)
    delivery_score = Column(Numeric(8, 2), nullable=False)
    documentation_score = Column(Numeric(8, 2), nullable=False)
    overall_score = Column(Numeric(8, 2), nullable=False)
    classification = Column(String(20), nullable=False)
    approved = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    evaluated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    supplier = relationship("Party", lazy="joined")

class QualityManagementReview(Base):
    __tablename__ = "quality_management_reviews"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_quality_management_review_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    review_date = Column(Date, nullable=False, index=True)
    scope = Column(String(250), nullable=False)
    inputs_summary = Column(Text, nullable=False)
    decisions = Column(Text)
    improvement_opportunities = Column(Text)
    resource_needs = Column(Text)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)

# -------------------- Food Safety, HACCP, COA and Recall v1.0 RC5 --------------------

class HACCPPlan(Base):
    __tablename__ = "haccp_plans"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_haccp_plan_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    product_item_id = Column(Integer, ForeignKey("items.id"))
    process_scope = Column(Text, nullable=False)
    intended_use = Column(Text)
    target_consumer = Column(String(250))
    version = Column(Integer, nullable=False, default=1)
    effective_from = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    product_item = relationship("Item", lazy="joined")
    hazards = relationship("HACCPHazard", back_populates="plan", cascade="all, delete-orphan", lazy="selectin")

class HACCPHazard(Base):
    __tablename__ = "haccp_hazards"
    __table_args__ = (UniqueConstraint("plan_id", "step_number", "hazard_type", name="uq_haccp_hazard_step_type"),)
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("haccp_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    process_step = Column(String(250), nullable=False)
    hazard_type = Column(String(20), nullable=False)
    hazard_description = Column(Text, nullable=False)
    likelihood = Column(Integer, nullable=False)
    severity = Column(Integer, nullable=False)
    risk_score = Column(Integer, nullable=False)
    significant = Column(Boolean, nullable=False, default=False)
    preventive_controls = Column(Text, nullable=False)
    is_ccp = Column(Boolean, nullable=False, default=False)
    critical_limit = Column(String(250))
    monitoring_method = Column(Text)
    monitoring_frequency = Column(String(100))
    corrective_action = Column(Text)
    verification_method = Column(Text)
    records_required = Column(Text)
    active = Column(Boolean, nullable=False, default=True)
    plan = relationship("HACCPPlan", back_populates="hazards")
    monitoring_logs = relationship("HACCPMonitoringLog", back_populates="hazard", cascade="all, delete-orphan")

class HACCPMonitoringLog(Base):
    __tablename__ = "haccp_monitoring_logs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    hazard_id = Column(Integer, ForeignKey("haccp_hazards.id", ondelete="CASCADE"), nullable=False, index=True)
    monitored_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    measured_value = Column(String(100), nullable=False)
    within_critical_limit = Column(Boolean, nullable=False)
    deviation_details = Column(Text)
    immediate_correction = Column(Text)
    corrective_action_id = Column(Integer, ForeignKey("quality_actions.id"))
    status = Column(String(20), nullable=False, default="RECORDED", index=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    verified_by = Column(Integer, ForeignKey("users.id"))
    verified_at = Column(DateTime)
    hazard = relationship("HACCPHazard", back_populates="monitoring_logs", lazy="joined")

class CertificateOfAnalysis(Base):
    __tablename__ = "certificates_of_analysis"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_coa_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    lot_number = Column(String(80), nullable=False, index=True)
    issue_date = Column(Date, nullable=False, index=True)
    expiry_date = Column(Date)
    specification_version = Column(String(50), nullable=False)
    test_results_json = Column(Text, nullable=False)
    conclusion = Column(String(20), nullable=False, default="PASS")
    remarks = Column(Text)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    item = relationship("Item", lazy="joined")

class ProductRecall(Base):
    __tablename__ = "product_recalls"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_recall_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    recall_date = Column(Date, nullable=False, index=True)
    recall_class = Column(String(20), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    lot_number = Column(String(80), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    scope = Column(Text, nullable=False)
    quantity_distributed = Column(Numeric(18, 4), nullable=False, default=0)
    quantity_recovered = Column(Numeric(18, 4), nullable=False, default=0)
    quantity_disposed = Column(Numeric(18, 4), nullable=False, default=0)
    effectiveness_percent = Column(Numeric(8, 2), nullable=False, default=0)
    status = Column(String(25), nullable=False, default="DRAFT", index=True)
    initiated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    closed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    closed_at = Column(DateTime)
    item = relationship("Item", lazy="joined")
    lines = relationship("ProductRecallLine", back_populates="recall", cascade="all, delete-orphan", lazy="selectin")

class ProductRecallLine(Base):
    __tablename__ = "product_recall_lines"
    id = Column(Integer, primary_key=True)
    recall_id = Column(Integer, ForeignKey("product_recalls.id", ondelete="CASCADE"), nullable=False, index=True)
    party_id = Column(Integer, ForeignKey("parties.id"))
    location = Column(String(250), nullable=False)
    quantity_distributed = Column(Numeric(18, 4), nullable=False, default=0)
    quantity_recovered = Column(Numeric(18, 4), nullable=False, default=0)
    contact_status = Column(String(30), nullable=False, default="PENDING")
    evidence_reference = Column(String(250))
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=utc_now)
    recall = relationship("ProductRecall", back_populates="lines")
    party = relationship("Party", lazy="joined")


# -------------------- Access Governance, SoD and Certification v1.0 RC5 --------------------

class SoDRule(Base):
    __tablename__ = "sod_rules"
    __table_args__ = (UniqueConstraint("code", name="uq_sod_rule_code"),)
    id = Column(Integer, primary_key=True)
    code = Column(String(60), nullable=False, index=True)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    permission_a = Column(String(100), nullable=False)
    permission_b = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False, default="HIGH")
    rationale = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

class SoDConflict(Base):
    __tablename__ = "sod_conflicts"
    __table_args__ = (UniqueConstraint("company_id", "user_id", "rule_id", "status", name="uq_sod_conflict_open_state"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("sod_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    mitigating_control = Column(Text)
    remediation_due_date = Column(Date)
    detected_at = Column(DateTime, nullable=False, default=utc_now)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolved_at = Column(DateTime)
    rule = relationship("SoDRule", lazy="joined")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")

class AccessReviewCampaign(Base):
    __tablename__ = "access_review_campaigns"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_access_review_company_number"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(50), nullable=False, index=True)
    name = Column(String(250), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    scope = Column(String(30), nullable=False, default="ALL_USERS")
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    items = relationship("AccessReviewItem", back_populates="campaign", cascade="all, delete-orphan", lazy="selectin")

class AccessReviewItem(Base):
    __tablename__ = "access_review_items"
    __table_args__ = (UniqueConstraint("campaign_id", "membership_id", name="uq_access_review_membership"),)
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("access_review_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    membership_id = Column(Integer, ForeignKey("user_company_roles.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    conflict_count = Column(Integer, nullable=False, default=0)
    decision = Column(String(20), nullable=False, default="PENDING", index=True)
    reviewer_notes = Column(Text)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    campaign = relationship("AccessReviewCampaign", back_populates="items")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    role = relationship("Role", lazy="joined")

# -------------------- Advanced financial reporting RC6 --------------------

__all__ = ['QualityObjective', 'QualityInspectionPlan', 'QualityAction', 'CustomerQualityComplaint', 'SupplierQualityEvaluation', 'QualityManagementReview', 'HACCPPlan', 'HACCPHazard', 'HACCPMonitoringLog', 'CertificateOfAnalysis', 'ProductRecall', 'ProductRecallLine', 'SoDRule', 'SoDConflict', 'AccessReviewCampaign', 'AccessReviewItem']
