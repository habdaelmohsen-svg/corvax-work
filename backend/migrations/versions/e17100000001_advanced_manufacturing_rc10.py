"""advanced manufacturing and costing rc10

Revision ID: e17100000001
Revises: e17000000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e17100000001"
down_revision = "e17000000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manufacturing_routings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("finished_item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("bom_id", sa.Integer(), sa.ForeignKey("bills_of_material.id"), nullable=False, index=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", "version", name="uq_mfg_routing_company_code_version"),
    )
    op.create_table(
        "manufacturing_routing_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("routing_id", sa.Integer(), sa.ForeignKey("manufacturing_routings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("operation_code", sa.String(40), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("work_center_id", sa.Integer(), sa.ForeignKey("work_centers.id"), nullable=False),
        sa.Column("setup_minutes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("run_minutes_per_unit", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("queue_minutes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("move_minutes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("standard_labor_rate", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("standard_overhead_rate", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("outside_processing_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("quality_gate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("routing_id", "sequence", name="uq_mfg_routing_operation_sequence"),
        sa.UniqueConstraint("routing_id", "operation_code", name="uq_mfg_routing_operation_code"),
    )
    op.create_table(
        "mrp_plan_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("planning_date", sa.Date(), nullable=False, index=True),
        sa.Column("horizon_end", sa.Date(), nullable=False),
        sa.Column("gross_demand", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_on_hand", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_scheduled_receipts", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_shortage", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_planned_supply", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="CALCULATED", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", name="uq_mrp_run_company_code"),
    )
    op.create_table(
        "mrp_demand_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("mrp_plan_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False, index=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("safety_stock", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="FORECAST"),
        sa.Column("source_reference", sa.String(100)),
    )
    op.create_table(
        "mrp_requirement_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("mrp_plan_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("parent_item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("bom_id", sa.Integer(), sa.ForeignKey("bills_of_material.id")),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date(), nullable=False, index=True),
        sa.Column("gross_requirement", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("on_hand", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("scheduled_receipts", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("safety_stock", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_requirement", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("planned_order_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("supply_type", sa.String(20), nullable=False, server_default="BUY"),
        sa.Column("action_message", sa.String(80), nullable=False, server_default="NONE"),
    )
    op.create_table(
        "production_operation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("routing_operation_id", sa.Integer(), sa.ForeignKey("manufacturing_routing_operations.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="PLANNED", index=True),
        sa.Column("planned_setup_minutes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("planned_run_minutes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("actual_setup_minutes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("actual_run_minutes", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("good_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("rejected_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("actual_labor_rate", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("actual_overhead_rate", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("started_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("production_order_id", "routing_operation_id", name="uq_production_order_routing_operation"),
    )
    op.create_table(
        "production_scrap_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False, index=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False, server_default="NORMAL"),
        sa.Column("disposition", sa.String(30), nullable=False, server_default="DISPOSE"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "production_cost_closes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("close_date", sa.Date(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cost_method", sa.String(20), nullable=False, server_default="STANDARD"),
        sa.Column("completed_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("standard_material_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("standard_labor_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("standard_overhead_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("standard_total_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("actual_material_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("actual_labor_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("actual_overhead_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("actual_total_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("material_price_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("material_usage_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("labor_rate_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("labor_efficiency_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("overhead_spending_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("overhead_volume_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("abnormal_scrap_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("residual_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("standard_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("actual_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="READY_FOR_REVIEW", index=True),
        sa.Column("analysis_hash", sa.String(64), nullable=False),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("production_order_id", "version", name="uq_production_cost_close_order_version"),
    )

    bind = op.get_bind()
    additions = [
        ("624010", "انحراف سعر المواد", "Material Price Variance"),
        ("624020", "انحراف استخدام المواد", "Material Usage Variance"),
        ("624030", "انحراف معدل العمل", "Labor Rate Variance"),
        ("624040", "انحراف كفاءة العمل", "Labor Efficiency Variance"),
        ("624050", "انحراف الإنفاق الصناعي", "Overhead Spending Variance"),
        ("624060", "انحراف حجم الإنتاج", "Overhead Volume Variance"),
        ("624070", "تكلفة الهالك غير الطبيعي", "Abnormal Scrap Cost"),
        ("624080", "فرق إقفال تكلفة الإنتاج", "Production Cost Close Residual"),
    ]
    companies = [row[0] for row in bind.execute(sa.text("SELECT id FROM companies")).fetchall()]
    for company_id in companies:
        parent = bind.execute(sa.text("SELECT id FROM accounts WHERE company_id=:cid AND code='600000'"), {"cid": company_id}).scalar()
        existing = {row[0] for row in bind.execute(sa.text("SELECT code FROM accounts WHERE company_id=:cid"), {"cid": company_id}).fetchall()}
        for code, name_ar, name_en in additions:
            if code not in existing and parent:
                bind.execute(sa.text("""
                    INSERT INTO accounts(company_id, code, name_ar, name_en, account_type, statement_group,
                                         parent_id, level, is_postable, is_cash, active)
                    VALUES (:company_id,:code,:name_ar,:name_en,'EXPENSE','COST_OF_REVENUE',:parent_id,2,1,0,1)
                """), {"company_id": company_id, "code": code, "name_ar": name_ar, "name_en": name_en, "parent_id": parent})


def downgrade():
    op.drop_table("production_cost_closes")
    op.drop_table("production_scrap_records")
    op.drop_table("production_operation_logs")
    op.drop_table("mrp_requirement_lines")
    op.drop_table("mrp_demand_lines")
    op.drop_table("mrp_plan_runs")
    op.drop_table("manufacturing_routing_operations")
    op.drop_table("manufacturing_routings")
