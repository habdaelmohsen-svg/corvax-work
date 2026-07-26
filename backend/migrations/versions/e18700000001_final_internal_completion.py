"""CORVAX Final Internal Completion.

Revision ID: e18700000001
Revises: e18600000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e18700000001"
down_revision = "e18600000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "internal_cost_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(30), nullable=False, server_default="STANDARD_VARIANCE"),
        sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW"),
        sa.Column("standard_output_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("actual_output_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("normal_capacity_hours", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("productive_hours", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("budgeted_fixed_overhead", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("actual_fixed_overhead", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("joint_cost_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("byproduct_credit_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("rework_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_standard_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_actual_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("idle_capacity_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("under_over_absorption", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("allocation_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("summary_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("analysis_hash", sa.String(64), nullable=False),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", "version", name="uq_internal_cost_run_company_code_version"),
    )
    for col in ("company_id", "code", "period_start", "period_end", "posting_date", "status", "analysis_hash"):
        op.create_index(f"ix_internal_cost_runs_{col}", "internal_cost_runs", [col])

    op.create_table(
        "internal_cost_variance_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("internal_cost_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("component_code", sa.String(80), nullable=False),
        sa.Column("description_ar", sa.String(500), nullable=False),
        sa.Column("description_en", sa.String(500), nullable=False),
        sa.Column("standard_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("actual_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("standard_rate", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("actual_rate", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("favorable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("posting_effect", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("account_code", sa.String(30)),
        sa.Column("source_reference", sa.String(250)),
        sa.UniqueConstraint("run_id", "sequence", name="uq_internal_cost_variance_run_sequence"),
    )
    op.create_index("ix_internal_cost_variance_lines_run_id", "internal_cost_variance_lines", ["run_id"])
    op.create_index("ix_internal_cost_variance_lines_category", "internal_cost_variance_lines", ["category"])

    op.create_table(
        "planning_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fiscal_year_id", sa.Integer(), sa.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("scenario_type", sa.String(30), nullable=False, server_default="BUDGET"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("base_scenario_id", sa.Integer(), sa.ForeignKey("planning_scenarios.id")),
        sa.Column("horizon_start", sa.Date(), nullable=False),
        sa.Column("horizon_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("assumptions_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("commentary_ar", sa.Text(), nullable=False, server_default=""),
        sa.Column("commentary_en", sa.Text(), nullable=False, server_default=""),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("frozen_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "fiscal_year_id", "name", "version", name="uq_planning_scenario_company_year_name_version"),
    )
    for col in ("company_id", "fiscal_year_id", "scenario_type", "status"):
        op.create_index(f"ix_planning_scenarios_{col}", "planning_scenarios", [col])

    op.create_table(
        "planning_scenario_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("planning_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("granularity", sa.String(20), nullable=False, server_default="MONTHLY"),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id")),
        sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id")),
        sa.Column("department_code", sa.String(60)),
        sa.Column("product_item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("driver_name", sa.String(120)),
        sa.Column("driver_value", sa.Numeric(18, 4)),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="MANUAL"),
        sa.Column("note", sa.String(500)),
    )
    for col in ("scenario_id", "account_id", "period_start", "period_end", "branch_id", "cost_center_id", "product_item_id"):
        op.create_index(f"ix_planning_scenario_lines_{col}", "planning_scenario_lines", [col])

    op.create_table(
        "close_orchestration_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fiscal_period_id", sa.Integer(), sa.ForeignKey("fiscal_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW"),
        sa.Column("score", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("blocker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checklist_hash", sa.String(64), nullable=False),
        sa.Column("summary_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("closed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "fiscal_period_id", "version", name="uq_close_orchestration_company_period_version"),
    )
    for col in ("company_id", "fiscal_period_id", "status", "checklist_hash"):
        op.create_index(f"ix_close_orchestration_runs_{col}", "close_orchestration_runs", [col])

    op.create_table(
        "close_orchestration_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("close_orchestration_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("title_ar", sa.String(300), nullable=False),
        sa.Column("title_en", sa.String(300), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expected_value", sa.String(250)),
        sa.Column("actual_value", sa.String(250)),
        sa.Column("variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("owner", sa.String(150)),
        sa.Column("evidence_reference", sa.String(700)),
        sa.Column("details", sa.Text()),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("run_id", "code", name="uq_close_orchestration_check_code"),
    )
    op.create_index("ix_close_orchestration_checks_run_id", "close_orchestration_checks", ["run_id"])
    op.create_index("ix_close_orchestration_checks_category", "close_orchestration_checks", ["category"])

    op.create_table(
        "readiness_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("environment_name", sa.String(50), nullable=False, server_default="INTERNAL"),
        sa.Column("target_stage", sa.String(30), nullable=False, server_default="INTERNAL_RELEASE"),
        sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW"),
        sa.Column("score", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("blocker_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_migration_head", sa.String(30), nullable=False),
        sa.Column("database_dialect", sa.String(30), nullable=False),
        sa.Column("evidence_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("summary_payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
    )
    for col in ("company_id", "status"):
        op.create_index(f"ix_readiness_assessments_{col}", "readiness_assessments", [col])

    op.create_table(
        "readiness_assessment_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("readiness_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("title_ar", sa.String(300), nullable=False),
        sa.Column("title_en", sa.String(300), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence_reference", sa.String(700)),
        sa.Column("details", sa.Text()),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("assessment_id", "code", name="uq_readiness_assessment_check_code"),
    )
    op.create_index("ix_readiness_assessment_checks_assessment_id", "readiness_assessment_checks", ["assessment_id"])
    op.create_index("ix_readiness_assessment_checks_category", "readiness_assessment_checks", ["category"])

    conn = op.get_bind()
    accounts = [
        ("624120", "انحراف مزيج المواد", "Material Mix Variance"),
        ("624130", "انحراف عائد المواد", "Material Yield Variance"),
        ("624140", "انحراف كفاءة التكاليف الصناعية المتغيرة", "Variable Overhead Efficiency Variance"),
        ("624150", "انحراف موازنة التكاليف الصناعية الثابتة", "Fixed Overhead Budget Variance"),
        ("624160", "تكلفة الطاقة العاطلة", "Idle Capacity Cost"),
        ("624170", "تكلفة إعادة التشغيل", "Rework Cost"),
        ("624180", "انحراف توزيع أقسام الخدمات", "Service Department Allocation Variance"),
    ]
    companies = [row[0] for row in conn.execute(sa.text("select id from companies"))]
    for company_id in companies:
        parent = conn.execute(sa.text("select id from accounts where company_id=:c and code='600000'"), {"c": company_id}).scalar()
        for code, ar, en in accounts:
            exists = conn.execute(sa.text("select 1 from accounts where company_id=:c and code=:code"), {"c": company_id, "code": code}).scalar()
            if exists:
                continue
            conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
                values(:c,:code,:ar,:en,'EXPENSE','COST_OF_REVENUE',:parent,3,1,0,1)"""),
                {"c": company_id, "code": code, "ar": ar, "en": en, "parent": parent})


def downgrade():
    conn = op.get_bind()
    for code in ("624120", "624130", "624140", "624150", "624160", "624170", "624180"):
        conn.execute(sa.text("delete from accounts where code=:code"), {"code": code})
    for table in (
        "readiness_assessment_checks", "readiness_assessments",
        "close_orchestration_checks", "close_orchestration_runs",
        "planning_scenario_lines", "planning_scenarios",
        "internal_cost_variance_lines", "internal_cost_runs",
    ):
        op.drop_table(table)
