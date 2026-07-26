from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class InternalCostRun(Base):
    __tablename__ = "internal_cost_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "code", "version", name="uq_internal_cost_run_company_code_version"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(60), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    posting_date = Column(Date, nullable=False, index=True)
    method = Column(String(30), nullable=False, default="STANDARD_VARIANCE")
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    standard_output_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    actual_output_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    normal_capacity_hours = Column(Numeric(18, 4), nullable=False, default=0)
    productive_hours = Column(Numeric(18, 4), nullable=False, default=0)
    budgeted_fixed_overhead = Column(Numeric(18, 2), nullable=False, default=0)
    actual_fixed_overhead = Column(Numeric(18, 2), nullable=False, default=0)
    joint_cost_total = Column(Numeric(18, 2), nullable=False, default=0)
    byproduct_credit_total = Column(Numeric(18, 2), nullable=False, default=0)
    rework_cost = Column(Numeric(18, 2), nullable=False, default=0)
    total_standard_cost = Column(Numeric(18, 2), nullable=False, default=0)
    total_actual_cost = Column(Numeric(18, 2), nullable=False, default=0)
    total_variance = Column(Numeric(18, 2), nullable=False, default=0)
    idle_capacity_cost = Column(Numeric(18, 2), nullable=False, default=0)
    under_over_absorption = Column(Numeric(18, 2), nullable=False, default=0)
    allocation_payload = Column(Text, nullable=False, default="{}")
    summary_payload = Column(Text, nullable=False, default="{}")
    analysis_hash = Column(String(64), nullable=False, index=True)
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

    lines = relationship("InternalCostVarianceLine", back_populates="run", cascade="all, delete-orphan", lazy="selectin")
    journal = relationship("JournalEntry")


class InternalCostVarianceLine(Base):
    __tablename__ = "internal_cost_variance_lines"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_internal_cost_variance_run_sequence"),
    )

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("internal_cost_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    category = Column(String(50), nullable=False, index=True)
    component_code = Column(String(80), nullable=False)
    description_ar = Column(String(500), nullable=False)
    description_en = Column(String(500), nullable=False)
    standard_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    actual_quantity = Column(Numeric(18, 4), nullable=False, default=0)
    standard_rate = Column(Numeric(18, 6), nullable=False, default=0)
    actual_rate = Column(Numeric(18, 6), nullable=False, default=0)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    favorable = Column(Boolean, nullable=False, default=False)
    posting_effect = Column(Boolean, nullable=False, default=True)
    account_code = Column(String(30))
    source_reference = Column(String(250))

    run = relationship("InternalCostRun", back_populates="lines")


class PlanningScenario(Base):
    __tablename__ = "planning_scenarios"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year_id", "name", "version", name="uq_planning_scenario_company_year_name_version"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year_id = Column(Integer, ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    scenario_type = Column(String(30), nullable=False, default="BUDGET", index=True)
    version = Column(Integer, nullable=False, default=1)
    base_scenario_id = Column(Integer, ForeignKey("planning_scenarios.id"))
    horizon_start = Column(Date, nullable=False)
    horizon_end = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    assumptions_payload = Column(Text, nullable=False, default="{}")
    commentary_ar = Column(Text, nullable=False, default="")
    commentary_en = Column(Text, nullable=False, default="")
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    frozen_at = Column(DateTime)

    lines = relationship("PlanningScenarioLine", back_populates="scenario", cascade="all, delete-orphan", lazy="selectin")
    base_scenario = relationship("PlanningScenario", remote_side=[id])


class PlanningScenarioLine(Base):
    __tablename__ = "planning_scenario_lines"

    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("planning_scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    granularity = Column(String(20), nullable=False, default="MONTHLY")
    branch_id = Column(Integer, ForeignKey("branches.id"), index=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), index=True)
    department_code = Column(String(60))
    product_item_id = Column(Integer, ForeignKey("items.id"), index=True)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    driver_name = Column(String(120))
    driver_value = Column(Numeric(18, 4))
    source_type = Column(String(30), nullable=False, default="MANUAL")
    note = Column(String(500))

    scenario = relationship("PlanningScenario", back_populates="lines")
    account = relationship("Account", lazy="joined")
    branch = relationship("Branch", lazy="joined")
    cost_center = relationship("CostCenter", lazy="joined")
    product_item = relationship("Item", lazy="joined")


class CloseOrchestrationRun(Base):
    __tablename__ = "close_orchestration_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_period_id", "version", name="uq_close_orchestration_company_period_version"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_period_id = Column(Integer, ForeignKey("fiscal_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    score = Column(Numeric(8, 2), nullable=False, default=0)
    blocker_count = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    checklist_hash = Column(String(64), nullable=False, index=True)
    summary_payload = Column(Text, nullable=False, default="{}")
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)
    closed_at = Column(DateTime)

    checks = relationship("CloseOrchestrationCheck", back_populates="run", cascade="all, delete-orphan", lazy="selectin")


class CloseOrchestrationCheck(Base):
    __tablename__ = "close_orchestration_checks"
    __table_args__ = (
        UniqueConstraint("run_id", "code", name="uq_close_orchestration_check_code"),
    )

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("close_orchestration_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    title_ar = Column(String(300), nullable=False)
    title_en = Column(String(300), nullable=False)
    severity = Column(String(20), nullable=False, default="MEDIUM")
    blocking = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False)
    expected_value = Column(String(250))
    actual_value = Column(String(250))
    variance = Column(Numeric(18, 2), nullable=False, default=0)
    owner = Column(String(150))
    evidence_reference = Column(String(700))
    details = Column(Text)
    checked_at = Column(DateTime, nullable=False, default=utc_now)

    run = relationship("CloseOrchestrationRun", back_populates="checks")


class ReadinessAssessment(Base):
    __tablename__ = "readiness_assessments"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    environment_name = Column(String(50), nullable=False, default="INTERNAL")
    target_stage = Column(String(30), nullable=False, default="INTERNAL_RELEASE")
    status = Column(String(30), nullable=False, default="READY_FOR_REVIEW", index=True)
    score = Column(Numeric(8, 2), nullable=False, default=0)
    blocker_count = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    expected_migration_head = Column(String(30), nullable=False)
    database_dialect = Column(String(30), nullable=False)
    evidence_payload = Column(Text, nullable=False, default="{}")
    summary_payload = Column(Text, nullable=False, default="{}")
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

    checks = relationship("ReadinessAssessmentCheck", back_populates="assessment", cascade="all, delete-orphan", lazy="selectin")


class ReadinessAssessmentCheck(Base):
    __tablename__ = "readiness_assessment_checks"
    __table_args__ = (
        UniqueConstraint("assessment_id", "code", name="uq_readiness_assessment_check_code"),
    )

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("readiness_assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    title_ar = Column(String(300), nullable=False)
    title_en = Column(String(300), nullable=False)
    mandatory = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False)
    evidence_reference = Column(String(700))
    details = Column(Text)
    checked_at = Column(DateTime, nullable=False, default=utc_now)

    assessment = relationship("ReadinessAssessment", back_populates="checks")


__all__ = [
    "InternalCostRun", "InternalCostVarianceLine", "PlanningScenario", "PlanningScenarioLine",
    "CloseOrchestrationRun", "CloseOrchestrationCheck", "ReadinessAssessment", "ReadinessAssessmentCheck",
]
