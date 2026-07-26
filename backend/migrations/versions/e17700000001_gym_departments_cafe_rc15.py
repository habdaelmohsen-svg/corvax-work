"""gym departments facilities and cafe rc15

Revision ID: e17700000001
Revises: e17600000001
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "e17700000001"
down_revision = "e17600000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gym_departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("department_type", sa.String(30), nullable=False, index=True),
        sa.Column("cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id"), nullable=False),
        sa.Column("revenue_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("booking_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "branch_id", "code", name="uq_gym_department_branch_code"),
    )
    op.create_table(
        "gym_department_plan_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("membership_plans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("access_mode", sa.String(20), nullable=False, server_default="INCLUDED", index=True),
        sa.Column("monthly_visit_limit", sa.Integer()),
        sa.Column("advance_booking_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("guest_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("plan_id", "department_id", name="uq_gym_plan_department_access"),
    )
    op.create_table(
        "gym_facilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("facility_type", sa.String(30), nullable=False, index=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("slot_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("hourly_rate", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_rate", sa.Numeric(8, 4), nullable=False, server_default="15"),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE", index=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(500)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("department_id", "code", name="uq_gym_facility_department_code"),
    )
    op.create_table(
        "gym_facility_bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(60), nullable=False, index=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("gym_facilities.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="SET NULL"), index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id", ondelete="SET NULL"), index=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("ends_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("participants", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("access_mode", sa.String(20), nullable=False, server_default="PAY_PER_USE"),
        sa.Column("net_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id")),
        sa.Column("status", sa.String(25), nullable=False, server_default="SUBMITTED", index=True),
        sa.Column("notes", sa.String(500)),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("cancelled_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("sale_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("refund_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("cancelled_at", sa.DateTime()),
        sa.Column("cancellation_reason", sa.String(500)),
        sa.UniqueConstraint("company_id", "number", name="uq_gym_facility_booking_number"),
    )
    op.create_table(
        "gym_department_access_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("membership_contracts.id", ondelete="SET NULL"), index=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("direction", sa.String(10), nullable=False, server_default="IN"),
        sa.Column("method", sa.String(20), nullable=False, server_default="QR"),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("reason", sa.String(500)),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "gym_cafe_product_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("gym_departments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("menu_item_id", sa.Integer(), sa.ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category", sa.String(30), nullable=False, index=True),
        sa.Column("product_type", sa.String(30), nullable=False, index=True),
        sa.Column("member_price", sa.Numeric(18, 2)),
        sa.Column("calories", sa.Numeric(10, 2)),
        sa.Column("protein_g", sa.Numeric(10, 2)),
        sa.Column("carbs_g", sa.Numeric(10, 2)),
        sa.Column("fat_g", sa.Numeric(10, 2)),
        sa.Column("sugar_g", sa.Numeric(10, 2)),
        sa.Column("caffeine_mg", sa.Numeric(10, 2)),
        sa.Column("allergens", sa.Text()),
        sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "branch_id", "menu_item_id", name="uq_gym_cafe_branch_menu_item"),
    )
    with op.batch_alter_table("pos_orders") as batch:
        batch.add_column(sa.Column("business_unit", sa.String(20), nullable=False, server_default="RESTAURANT"))
        batch.add_column(sa.Column("gym_department_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("gym_member_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("cost_center_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_pos_order_gym_department", "gym_departments", ["gym_department_id"], ["id"])
        batch.create_foreign_key("fk_pos_order_gym_member", "members", ["gym_member_id"], ["id"])
        batch.create_foreign_key("fk_pos_order_cost_center", "cost_centers", ["cost_center_id"], ["id"])
        batch.create_index("ix_pos_orders_business_unit", ["business_unit"])
        batch.create_index("ix_pos_orders_gym_department_id", ["gym_department_id"])
        batch.create_index("ix_pos_orders_gym_member_id", ["gym_member_id"])
        batch.create_index("ix_pos_orders_cost_center_id", ["cost_center_id"])
    with op.batch_alter_table("gym_trainers") as batch:
        batch.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_gym_trainer_department", "gym_departments", ["department_id"], ["id"])
        batch.create_index("ix_gym_trainers_department_id", ["department_id"])
    with op.batch_alter_table("gym_class_types") as batch:
        batch.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_gym_class_type_department", "gym_departments", ["department_id"], ["id"])
        batch.create_index("ix_gym_class_types_department_id", ["department_id"])
    with op.batch_alter_table("gym_class_sessions") as batch:
        batch.add_column(sa.Column("facility_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_gym_class_session_facility", "gym_facilities", ["facility_id"], ["id"])
        batch.create_index("ix_gym_class_sessions_facility_id", ["facility_id"])


def downgrade():
    with op.batch_alter_table("gym_class_sessions") as batch:
        batch.drop_index("ix_gym_class_sessions_facility_id")
        batch.drop_constraint("fk_gym_class_session_facility", type_="foreignkey")
        batch.drop_column("facility_id")
    with op.batch_alter_table("gym_class_types") as batch:
        batch.drop_index("ix_gym_class_types_department_id")
        batch.drop_constraint("fk_gym_class_type_department", type_="foreignkey")
        batch.drop_column("department_id")
    with op.batch_alter_table("gym_trainers") as batch:
        batch.drop_index("ix_gym_trainers_department_id")
        batch.drop_constraint("fk_gym_trainer_department", type_="foreignkey")
        batch.drop_column("department_id")
    with op.batch_alter_table("pos_orders") as batch:
        batch.drop_index("ix_pos_orders_cost_center_id")
        batch.drop_index("ix_pos_orders_gym_member_id")
        batch.drop_index("ix_pos_orders_gym_department_id")
        batch.drop_index("ix_pos_orders_business_unit")
        batch.drop_constraint("fk_pos_order_cost_center", type_="foreignkey")
        batch.drop_constraint("fk_pos_order_gym_member", type_="foreignkey")
        batch.drop_constraint("fk_pos_order_gym_department", type_="foreignkey")
        batch.drop_column("cost_center_id")
        batch.drop_column("gym_member_id")
        batch.drop_column("gym_department_id")
        batch.drop_column("business_unit")
    op.drop_table("gym_cafe_product_profiles")
    op.drop_table("gym_department_access_records")
    op.drop_table("gym_facility_bookings")
    op.drop_table("gym_facilities")
    op.drop_table("gym_department_plan_access")
    op.drop_table("gym_departments")
