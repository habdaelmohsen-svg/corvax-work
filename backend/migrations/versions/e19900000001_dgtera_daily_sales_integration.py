"""DGTERA automatic sales-only mirror.

Revision ID: e19900000001
Revises: e19800000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e19900000001"
down_revision = "e19800000001"
branch_labels = None
depends_on = None


def _index(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "dgtera_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("database_name", sa.Text(), nullable=False),
        sa.Column("login", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("import_mode", sa.String(30), nullable=False, server_default="SALES_ONLY"),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Riyadh"),
        sa.Column("last_tested_at", sa.DateTime()),
        sa.Column("last_sync_at", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", name="uq_dgtera_connection_company"),
    )
    _index("dgtera_connections", "company_id", "active")

    op.create_table(
        "dgtera_branches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_config_id", sa.String(80), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_updated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_config_id", name="uq_dgtera_branch_external"),
    )
    _index("dgtera_branches", "connection_id", "company_id", "branch_id")

    op.create_table(
        "dgtera_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_product_id", sa.String(80), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("barcode", sa.String(120)),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("external_category_id", sa.String(80)),
        sa.Column("category_name", sa.String(250)),
        sa.Column("list_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_updated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_product_id", name="uq_dgtera_product_external"),
    )
    _index("dgtera_products", "connection_id", "company_id")

    op.create_table(
        "dgtera_customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_partner_id", sa.String(80), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("customer_kind", sa.String(30), nullable=False, server_default="CUSTOMER"),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_updated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_partner_id", name="uq_dgtera_customer_external"),
    )
    _index("dgtera_customers", "connection_id", "company_id", "customer_kind", "party_id")

    op.create_table(
        "dgtera_sales_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_order_id", sa.String(80), nullable=False),
        sa.Column("external_order_name", sa.String(150), nullable=False),
        sa.Column("pos_reference", sa.String(180)),
        sa.Column("external_session_id", sa.String(80)),
        sa.Column("external_session_name", sa.String(150)),
        sa.Column("sales_date", sa.Date(), nullable=False),
        sa.Column("ordered_at_local", sa.DateTime(), nullable=False),
        sa.Column("ordered_at_utc", sa.DateTime(), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("dgtera_branch_id", sa.Integer(), sa.ForeignKey("dgtera_branches.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("dgtera_customers.id")),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id")),
        sa.Column("sales_scope", sa.String(20), nullable=False, server_default="INTERNAL"),
        sa.Column("service_mode", sa.String(20), nullable=False, server_default="TAKEAWAY"),
        sa.Column("classification_source", sa.String(120), nullable=False),
        sa.Column("delivery_platform_id", sa.Integer(), sa.ForeignKey("delivery_platforms.id")),
        sa.Column("delivery_platform_name", sa.String(250)),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("amount_paid", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("amount_return", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("line_total_difference", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("source_payload", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_order_id", name="uq_dgtera_sales_order_external"),
    )
    _index(
        "dgtera_sales_orders", "connection_id", "company_id", "external_order_name",
        "sales_date", "ordered_at_local", "branch_id", "dgtera_branch_id", "customer_id",
        "party_id", "sales_scope", "service_mode", "delivery_platform_id", "state", "source_hash",
    )

    op.create_table(
        "dgtera_sales_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dgtera_sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_line_id", sa.String(80), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("dgtera_products.id"), nullable=False),
        sa.Column("product_name", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("discount_percent", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("total", sa.Numeric(18, 2), nullable=False),
        sa.Column("source_tax_ids", sa.String(500)),
        sa.UniqueConstraint("order_id", "external_line_id", name="uq_dgtera_order_line_external"),
    )
    _index("dgtera_sales_order_lines", "order_id", "product_id")

    op.create_table(
        "dgtera_sales_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dgtera_sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_payment_id", sa.String(80), nullable=False),
        sa.Column("external_method_id", sa.String(80)),
        sa.Column("method_name", sa.String(250), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("order_id", "external_payment_id", name="uq_dgtera_payment_external"),
    )
    _index("dgtera_sales_payments", "order_id")

    op.create_table(
        "dgtera_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("window_label", sa.String(100), nullable=False, server_default="00:01-23:59 Asia/Riyadh"),
        sa.Column("status", sa.String(30), nullable=False, server_default="RUNNING"),
        sa.Column("source_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
    )
    _index("dgtera_sync_runs", "connection_id", "company_id", "start_date", "end_date", "status")


def downgrade() -> None:
    op.drop_table("dgtera_sync_runs")
    op.drop_table("dgtera_sales_payments")
    op.drop_table("dgtera_sales_order_lines")
    op.drop_table("dgtera_sales_orders")
    op.drop_table("dgtera_customers")
    op.drop_table("dgtera_products")
    op.drop_table("dgtera_branches")
    op.drop_table("dgtera_connections")

