"""R7 controlled procurement: requisition, RFQ, quotations and PO award.

Revision ID: e20300000001
Revises: e20200000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e20300000001"
down_revision = "e20200000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_requisitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column("needed_by", sa.Date(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("department", sa.String(120), nullable=False),
        sa.Column("justification", sa.String(500), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("estimated_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("rejected_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("rejected_at", sa.DateTime()),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "number", name="uq_pr_company_number"),
    )
    op.create_index("ix_purchase_requisitions_company_id", "purchase_requisitions", ["company_id"])
    op.create_index("ix_purchase_requisitions_number", "purchase_requisitions", ["number"])
    op.create_index("ix_purchase_requisitions_request_date", "purchase_requisitions", ["request_date"])
    op.create_index("ix_purchase_requisitions_status", "purchase_requisitions", ["status"])

    op.create_table(
        "purchase_requisition_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requisition_id", sa.Integer(), sa.ForeignKey("purchase_requisitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("estimated_unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("specifications", sa.String(500)),
    )
    op.create_index("ix_purchase_requisition_lines_requisition_id", "purchase_requisition_lines", ["requisition_id"])

    op.create_table(
        "requests_for_quotation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("requisition_id", sa.Integer(), sa.ForeignKey("purchase_requisitions.id"), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issued_at", sa.DateTime()),
        sa.Column("awarded_quotation_id", sa.Integer()),
        sa.Column("award_reason", sa.String(500)),
        sa.Column("awarded_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("awarded_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "number", name="uq_rfq_company_number"),
        sa.UniqueConstraint("requisition_id", name="uq_rfq_requisition"),
    )
    op.create_index("ix_requests_for_quotation_company_id", "requests_for_quotation", ["company_id"])
    op.create_index("ix_requests_for_quotation_number", "requests_for_quotation", ["number"])
    op.create_index("ix_requests_for_quotation_requisition_id", "requests_for_quotation", ["requisition_id"])
    op.create_index("ix_requests_for_quotation_status", "requests_for_quotation", ["status"])

    op.create_table(
        "rfq_suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.UniqueConstraint("rfq_id", "supplier_id", name="uq_rfq_supplier"),
    )
    op.create_index("ix_rfq_suppliers_rfq_id", "rfq_suppliers", ["rfq_id"])

    op.create_table(
        "rfq_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requisition_line_id", sa.Integer(), sa.ForeignKey("purchase_requisition_lines.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("specifications", sa.String(500)),
        sa.UniqueConstraint("rfq_id", "requisition_line_id", name="uq_rfq_requisition_line"),
    )
    op.create_index("ix_rfq_lines_rfq_id", "rfq_lines", ["rfq_id"])

    op.create_table(
        "supplier_quotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.Column("supplier_reference", sa.String(100), nullable=False),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payment_terms", sa.String(250)),
        sa.Column("status", sa.String(25), nullable=False, server_default="SUBMITTED"),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "number", name="uq_supplier_quote_company_number"),
        sa.UniqueConstraint("rfq_id", "supplier_id", name="uq_supplier_quote_rfq_supplier"),
    )
    op.create_index("ix_supplier_quotations_company_id", "supplier_quotations", ["company_id"])
    op.create_index("ix_supplier_quotations_number", "supplier_quotations", ["number"])
    op.create_index("ix_supplier_quotations_rfq_id", "supplier_quotations", ["rfq_id"])
    op.create_index("ix_supplier_quotations_status", "supplier_quotations", ["status"])

    op.create_table(
        "supplier_quotation_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("supplier_quotations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rfq_line_id", sa.Integer(), sa.ForeignKey("rfq_lines.id"), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("vat_rate", sa.Numeric(8, 4), nullable=False, server_default="15"),
        sa.Column("line_subtotal", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("quotation_id", "rfq_line_id", name="uq_supplier_quote_rfq_line"),
    )
    op.create_index("ix_supplier_quotation_lines_quotation_id", "supplier_quotation_lines", ["quotation_id"])

    with op.batch_alter_table("requests_for_quotation") as batch:
        batch.create_foreign_key("fk_rfq_awarded_quotation", "supplier_quotations", ["awarded_quotation_id"], ["id"])
    with op.batch_alter_table("purchase_orders") as batch:
        batch.add_column(sa.Column("source_requisition_id", sa.Integer()))
        batch.add_column(sa.Column("source_quotation_id", sa.Integer()))
        batch.create_foreign_key("fk_po_source_requisition", "purchase_requisitions", ["source_requisition_id"], ["id"])
        batch.create_foreign_key("fk_po_source_quotation", "supplier_quotations", ["source_quotation_id"], ["id"])
        batch.create_index("ix_purchase_orders_source_requisition_id", ["source_requisition_id"])
        batch.create_index("ix_purchase_orders_source_quotation_id", ["source_quotation_id"])


def downgrade() -> None:
    with op.batch_alter_table("purchase_orders") as batch:
        batch.drop_index("ix_purchase_orders_source_quotation_id")
        batch.drop_index("ix_purchase_orders_source_requisition_id")
        batch.drop_constraint("fk_po_source_quotation", type_="foreignkey")
        batch.drop_constraint("fk_po_source_requisition", type_="foreignkey")
        batch.drop_column("source_quotation_id")
        batch.drop_column("source_requisition_id")
    with op.batch_alter_table("requests_for_quotation") as batch:
        batch.drop_constraint("fk_rfq_awarded_quotation", type_="foreignkey")
    op.drop_table("supplier_quotation_lines")
    op.drop_table("supplier_quotations")
    op.drop_table("rfq_lines")
    op.drop_table("rfq_suppliers")
    op.drop_table("requests_for_quotation")
    op.drop_table("purchase_requisition_lines")
    op.drop_table("purchase_requisitions")
