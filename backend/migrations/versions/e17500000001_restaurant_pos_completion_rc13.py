"""Restaurant operations and POS completion RC13

Revision ID: e17500000001
Revises: e17400000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e17500000001"
down_revision = "e17400000001"
branch_labels = None
depends_on = None

PERMISSIONS = {
    "pos.tables.manage": ("إدارة طاولات المطعم", "Manage restaurant tables"),
    "pos.reservations.manage": ("إدارة حجوزات المطعم", "Manage restaurant reservations"),
    "pos.shifts.manage": ("إدارة ورديات الكاشير", "Manage cashier shifts"),
    "pos.shifts.approve": ("اعتماد إقفال ورديات الكاشير", "Approve cashier shift close"),
    "pos.kds.manage": ("إدارة شاشة المطبخ", "Manage kitchen display system"),
    "pos.controls.request": ("طلب إلغاء أو مرتجع نقطة البيع", "Request POS void or return"),
    "pos.controls.approve": ("اعتماد إلغاء أو مرتجع نقطة البيع", "Approve POS void or return"),
    "pos.settlements.manage": ("إعداد ومراجعة تسويات منصات التوصيل", "Prepare and review platform settlements"),
    "pos.settlements.approve": ("اعتماد تسويات منصات التوصيل", "Approve platform settlements"),
    "pos.waste.manage": ("إعداد سجلات هدر المطعم", "Prepare restaurant waste records"),
    "pos.waste.approve": ("اعتماد هدر المطعم", "Approve restaurant waste"),
    "pos.offline.sync": ("مزامنة مبيعات نقطة البيع دون اتصال", "Sync offline POS sales"),
}

ROLE_PERMISSIONS = {
    "RESTAURANT_MANAGER": [
        "company.read", "masterdata.read", "inventory.read", "pos.read", "pos.manage", "pos.sell", "pos.settle",
        "pos.tables.manage", "pos.reservations.manage", "pos.shifts.manage", "pos.kds.manage",
        "pos.controls.request", "pos.settlements.manage", "pos.waste.manage", "pos.offline.sync", "audit.read",
    ],
    "CFO": ["pos.shifts.approve", "pos.controls.approve", "pos.settlements.approve", "pos.waste.approve"],
    "FINANCIAL_CONTROLLER": ["pos.settlements.manage", "pos.controls.approve", "pos.waste.approve", "pos.shifts.approve"],
    "ACCOUNTANT": ["pos.controls.request", "pos.settlements.manage", "pos.waste.manage", "pos.offline.sync"],
    "SALES_MANAGER": ["pos.tables.manage", "pos.reservations.manage", "pos.kds.manage"],
    "AUDITOR": ["pos.settlements.manage"],
}


def _seed_access() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT id FROM roles WHERE code='RESTAURANT_MANAGER'")).scalar() is None:
        bind.execute(sa.text("INSERT INTO roles(code,name_ar,name_en) VALUES ('RESTAURANT_MANAGER','مدير المطعم','Restaurant Manager')"))
    for code, (name_ar, name_en) in PERMISSIONS.items():
        if bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar() is None:
            bind.execute(sa.text("INSERT INTO permissions(code,name_ar,name_en) VALUES (:code,:ar,:en)"), {"code": code, "ar": name_ar, "en": name_en})
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        rid = bind.execute(sa.text("SELECT id FROM roles WHERE code=:code"), {"code": role_code}).scalar()
        if rid is None:
            continue
        for permission_code in permission_codes:
            pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": permission_code}).scalar()
            if pid is None:
                continue
            if bind.execute(sa.text("SELECT 1 FROM role_permissions WHERE role_id=:r AND permission_id=:p"), {"r": rid, "p": pid}).scalar() is None:
                bind.execute(sa.text("INSERT INTO role_permissions(role_id,permission_id) VALUES (:r,:p)"), {"r": rid, "p": pid})


def upgrade():
    op.create_table(
        "restaurant_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False), sa.Column("name_ar", sa.String(150), nullable=False),
        sa.Column("name_en", sa.String(150), nullable=False), sa.Column("area", sa.String(80)),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("status", sa.String(25), nullable=False, server_default="AVAILABLE", index=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "branch_id", "code", name="uq_restaurant_table_branch_code"),
    )
    op.create_table(
        "restaurant_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("restaurant_tables.id"), index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True), sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("mobile", sa.String(30)), sa.Column("guest_count", sa.Integer(), nullable=False),
        sa.Column("reservation_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("status", sa.String(25), nullable=False, server_default="BOOKED", index=True),
        sa.Column("notes", sa.String(500)), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("seated_at", sa.DateTime()), sa.Column("completed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_restaurant_reservation_number"),
    )
    op.create_table(
        "cashier_shifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id"), nullable=False),
        sa.Column("number", sa.String(50), nullable=False, index=True), sa.Column("business_date", sa.Date(), nullable=False, index=True),
        sa.Column("opening_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("cash_sales", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("cash_refunds", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("expected_cash", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("counted_cash", sa.Numeric(18, 2)), sa.Column("variance", sa.Numeric(18, 2)),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN", index=True),
        sa.Column("notes", sa.String(500)), sa.Column("opened_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("closed_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("opened_at", sa.DateTime(), nullable=False), sa.Column("submitted_at", sa.DateTime()), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_cashier_shift_number"),
    )
    op.create_table(
        "kitchen_stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False), sa.Column("name_ar", sa.String(150), nullable=False),
        sa.Column("name_en", sa.String(150), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("company_id", "branch_id", "code", name="uq_kitchen_station_branch_code"),
    )
    op.create_table(
        "menu_kitchen_stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("menu_item_id", sa.Integer(), sa.ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kitchen_station_id", sa.Integer(), sa.ForeignKey("kitchen_stations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.UniqueConstraint("menu_item_id", name="uq_menu_kitchen_station_menu_item"),
    )
    with op.batch_alter_table("pos_orders") as batch:
        batch.add_column(sa.Column("order_type", sa.String(20), nullable=False, server_default="TAKEAWAY"))
        batch.add_column(sa.Column("table_id", sa.Integer()))
        batch.add_column(sa.Column("reservation_id", sa.Integer()))
        batch.add_column(sa.Column("cashier_shift_id", sa.Integer()))
        batch.add_column(sa.Column("guest_count", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("customer_name", sa.String(200)))
        batch.add_column(sa.Column("notes", sa.String(500)))
        batch.add_column(sa.Column("client_order_id", sa.String(120)))
        batch.add_column(sa.Column("source_device_id", sa.String(100)))
        batch.add_column(sa.Column("sync_status", sa.String(20), nullable=False, server_default="ONLINE"))
        batch.create_foreign_key("fk_pos_order_table", "restaurant_tables", ["table_id"], ["id"])
        batch.create_foreign_key("fk_pos_order_reservation", "restaurant_reservations", ["reservation_id"], ["id"])
        batch.create_foreign_key("fk_pos_order_cashier_shift", "cashier_shifts", ["cashier_shift_id"], ["id"])
        batch.create_unique_constraint("uq_pos_order_client_order", ["company_id", "client_order_id"])
        batch.create_index("ix_pos_orders_order_type", ["order_type"])
        batch.create_index("ix_pos_orders_cashier_shift_id", ["cashier_shift_id"])
        batch.create_index("ix_pos_orders_sync_status", ["sync_status"])
    op.create_table(
        "kitchen_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pos_order_id", sa.Integer(), sa.ForeignKey("pos_orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kitchen_station_id", sa.Integer(), sa.ForeignKey("kitchen_stations.id"), nullable=False, index=True),
        sa.Column("number", sa.String(60), nullable=False, unique=True, index=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(25), nullable=False, server_default="NEW", index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("accepted_at", sa.DateTime()),
        sa.Column("started_at", sa.DateTime()), sa.Column("ready_at", sa.DateTime()), sa.Column("served_at", sa.DateTime()),
        sa.UniqueConstraint("pos_order_id", "kitchen_station_id", name="uq_kitchen_ticket_order_station"),
    )
    op.create_table(
        "kitchen_ticket_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kitchen_ticket_id", sa.Integer(), sa.ForeignKey("kitchen_tickets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pos_order_line_id", sa.Integer(), sa.ForeignKey("pos_order_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="NEW", index=True),
        sa.Column("notes", sa.String(500)),
    )
    op.create_table(
        "pos_control_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pos_order_id", sa.Integer(), sa.ForeignKey("pos_orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(60), nullable=False, index=True), sa.Column("request_type", sa.String(20), nullable=False, index=True),
        sa.Column("reason", sa.String(500), nullable=False), sa.Column("refund_bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id")),
        sa.Column("restore_inventory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("refund_net", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refund_vat", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("refund_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("restored_food_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="SUBMITTED", index=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("rejected_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("reversal_sale_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("reversal_cogs_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("approved_at", sa.DateTime()),
        sa.Column("rejected_at", sa.DateTime()), sa.Column("rejection_reason", sa.String(500)),
        sa.UniqueConstraint("company_id", "number", name="uq_pos_control_request_number"),
    )
    op.create_table(
        "pos_control_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_request_id", sa.Integer(), sa.ForeignKey("pos_control_requests.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pos_order_line_id", sa.Integer(), sa.ForeignKey("pos_order_lines.id"), nullable=False, index=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False), sa.Column("refund_net", sa.Numeric(18, 2), nullable=False),
        sa.Column("refund_vat", sa.Numeric(18, 2), nullable=False), sa.Column("refund_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("restored_food_cost", sa.Numeric(18, 2), nullable=False),
    )
    op.create_table(
        "platform_settlement_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("platform_id", sa.Integer(), sa.ForeignKey("delivery_platforms.id"), nullable=False, index=True),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id"), nullable=False),
        sa.Column("settlement_reference", sa.String(100), nullable=False, index=True),
        sa.Column("settlement_date", sa.Date(), nullable=False, index=True), sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False), sa.Column("gross_sales", sa.Numeric(18, 2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("other_fees", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("expected_net", sa.Numeric(18, 2), nullable=False), sa.Column("received_net", sa.Numeric(18, 2), nullable=False),
        sa.Column("variance", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("reviewed_at", sa.DateTime()), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "settlement_reference", name="uq_platform_settlement_reference"),
    )
    op.create_table(
        "platform_settlement_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("settlement_batch_id", sa.Integer(), sa.ForeignKey("platform_settlement_batches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("pos_order_id", sa.Integer(), sa.ForeignKey("pos_orders.id"), nullable=False, index=True),
        sa.Column("gross_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(18, 2), nullable=False), sa.Column("expected_net", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("pos_order_id", name="uq_platform_settlement_order"),
    )
    op.create_table(
        "restaurant_waste_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("number", sa.String(60), nullable=False, index=True), sa.Column("waste_date", sa.Date(), nullable=False, index=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False), sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False), sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="SUBMITTED", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_restaurant_waste_number"),
    )
    op.create_table(
        "offline_pos_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("device_id", sa.String(100), nullable=False, index=True),
        sa.Column("client_transaction_id", sa.String(120), nullable=False, index=True),
        sa.Column("payload_json", sa.Text(), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="PENDING", index=True),
        sa.Column("pos_order_id", sa.Integer(), sa.ForeignKey("pos_orders.id")), sa.Column("conflict_reason", sa.String(500)),
        sa.Column("received_at", sa.DateTime(), nullable=False), sa.Column("processed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "device_id", "client_transaction_id", name="uq_offline_pos_client_transaction"),
    )
    _seed_access()


def downgrade():
    for table in [
        "offline_pos_transactions", "restaurant_waste_records", "platform_settlement_lines", "platform_settlement_batches",
        "pos_control_lines", "pos_control_requests", "kitchen_ticket_lines", "kitchen_tickets",
    ]:
        op.drop_table(table)
    with op.batch_alter_table("pos_orders") as batch:
        batch.drop_index("ix_pos_orders_sync_status")
        batch.drop_index("ix_pos_orders_cashier_shift_id")
        batch.drop_index("ix_pos_orders_order_type")
        batch.drop_constraint("uq_pos_order_client_order", type_="unique")
        batch.drop_constraint("fk_pos_order_cashier_shift", type_="foreignkey")
        batch.drop_constraint("fk_pos_order_reservation", type_="foreignkey")
        batch.drop_constraint("fk_pos_order_table", type_="foreignkey")
        for name in ["sync_status", "source_device_id", "client_order_id", "notes", "customer_name", "guest_count", "cashier_shift_id", "reservation_id", "table_id", "order_type"]:
            batch.drop_column(name)
    for table in ["menu_kitchen_stations", "kitchen_stations", "cashier_shifts", "restaurant_reservations", "restaurant_tables"]:
        op.drop_table(table)
