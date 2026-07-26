"""CORVAX RC27.4 H9 - strict inventory traceability, landed cost and NRV.

Adds:
  * inbound_shipments  - container / packing-list / commercial-invoice / customs-clearance tracking
  * inbound_shipment_lines - per-item landed cost allocation
  * items.item_subtype, items.nrv_per_unit, items.physical_issue_method (columns)
  * stock_movements.inbound_shipment_id (traceability link)

Revision chain: follows the H6 head e18900000001.
"""
from alembic import op
import sqlalchemy as sa


revision = "e19000000001"
down_revision = "e18900000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_shipments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(length=40), nullable=False, index=True),
        sa.Column("container_number", sa.String(length=60), nullable=False),
        sa.Column("packing_list_number", sa.String(length=60), nullable=False),
        sa.Column("commercial_invoice_number", sa.String(length=60), nullable=False),
        sa.Column("customs_clearance_number", sa.String(length=60), nullable=True),
        sa.Column("customs_declaration_number", sa.String(length=60), nullable=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=True),
        sa.Column("arrival_date", sa.Date(), nullable=False),
        sa.Column("port_of_entry", sa.String(length=120), nullable=True),
        sa.Column("carrier", sa.String(length=120), nullable=True),
        sa.Column("goods_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("freight_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("customs_duty", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("clearance_fees", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("other_costs", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("landed_cost_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("allocation_method", sa.String(length=20), nullable=False, server_default="VALUE"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "number", name="uq_inbound_shipment_company_number"),
        sa.UniqueConstraint("company_id", "container_number", name="uq_inbound_shipment_container"),
    )
    op.create_table(
        "inbound_shipment_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inbound_shipment_id", sa.Integer(), sa.ForeignKey("inbound_shipments.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("supplier_unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_goods_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("allocated_landed_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("landed_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("lot_number", sa.String(length=80), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
    )
    # Plain column additions. On SQLite, add_column with a simple (non-FK) column does
    # not trigger a table rebuild, so existing unnamed constraints are left untouched.
    op.add_column("items", sa.Column("item_subtype", sa.String(length=40), nullable=True))
    op.add_column("items", sa.Column("nrv_per_unit", sa.Numeric(18, 4), nullable=True))
    op.add_column("items", sa.Column("physical_issue_method", sa.String(length=10), nullable=False, server_default="FEFO"))
    # The traceability link is stored as a plain integer id (no DB-level FK) to avoid a
    # SQLite batch rebuild of stock_movements; the relationship is enforced in the app layer.
    op.add_column("stock_movements", sa.Column("inbound_shipment_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_movements", "inbound_shipment_id")
    op.drop_column("items", "physical_issue_method")
    op.drop_column("items", "nrv_per_unit")
    op.drop_column("items", "item_subtype")
    op.drop_table("inbound_shipment_lines")
    op.drop_table("inbound_shipments")
