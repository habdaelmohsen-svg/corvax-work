"""Read-only external sales mirrors.

DGTERA remains the source of truth. CORVAX imports final POS sales plus the
branch, product, customer, payment and service-channel dimensions carried by
those sales. The mirror deliberately has no inventory, COGS or journal-entry
side effects.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base
from app.models.types import EncryptedString


class DgteraConnection(Base):
    __tablename__ = "dgtera_connections"
    __table_args__ = (UniqueConstraint("company_id", name="uq_dgtera_connection_company"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False, default="DGTERA")
    base_url = Column(String(500), nullable=False)
    database_name = Column(EncryptedString(), nullable=False)
    login = Column(EncryptedString(), nullable=False)
    api_key = Column(EncryptedString(), nullable=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    import_mode = Column(String(30), nullable=False, default="SALES_ONLY")
    sync_interval_minutes = Column(Integer, nullable=False, default=5)
    timezone = Column(String(80), nullable=False, default="Asia/Riyadh")
    last_tested_at = Column(DateTime)
    last_sync_at = Column(DateTime)
    last_error = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DgteraBranch(Base):
    __tablename__ = "dgtera_branches"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_config_id", name="uq_dgtera_branch_external"),
    )

    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    external_config_id = Column(String(80), nullable=False)
    code = Column(String(30), nullable=False)
    name = Column(String(250), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    source_updated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DgteraProduct(Base):
    __tablename__ = "dgtera_products"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_product_id", name="uq_dgtera_product_external"),
    )

    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    external_product_id = Column(String(80), nullable=False)
    code = Column(String(80), nullable=False)
    barcode = Column(String(120))
    name = Column(String(300), nullable=False)
    external_category_id = Column(String(80))
    category_name = Column(String(250))
    list_price = Column(Numeric(18, 2), nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    source_updated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DgteraCustomer(Base):
    __tablename__ = "dgtera_customers"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_partner_id", name="uq_dgtera_customer_external"),
    )

    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    external_partner_id = Column(String(80), nullable=False)
    code = Column(String(80), nullable=False)
    name = Column(String(300), nullable=False)
    customer_kind = Column(String(30), nullable=False, default="CUSTOMER", index=True)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    source_updated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DgteraSalesOrder(Base):
    __tablename__ = "dgtera_sales_orders"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_order_id", name="uq_dgtera_sales_order_external"),
    )

    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    external_order_id = Column(String(80), nullable=False)
    external_order_name = Column(String(150), nullable=False, index=True)
    pos_reference = Column(String(180))
    external_session_id = Column(String(80))
    external_session_name = Column(String(150))
    sales_date = Column(Date, nullable=False, index=True)
    ordered_at_local = Column(DateTime, nullable=False, index=True)
    ordered_at_utc = Column(DateTime, nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    dgtera_branch_id = Column(Integer, ForeignKey("dgtera_branches.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("dgtera_customers.id"), index=True)
    party_id = Column(Integer, ForeignKey("parties.id"), index=True)
    sales_scope = Column(String(20), nullable=False, default="INTERNAL", index=True)
    service_mode = Column(String(20), nullable=False, default="TAKEAWAY", index=True)
    classification_source = Column(String(120), nullable=False)
    delivery_platform_id = Column(Integer, ForeignKey("delivery_platforms.id"), index=True)
    delivery_platform_name = Column(String(250))
    state = Column(String(30), nullable=False, index=True)
    subtotal = Column(Numeric(18, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    total = Column(Numeric(18, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(18, 2), nullable=False, default=0)
    amount_return = Column(Numeric(18, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(18, 2), nullable=False, default=0)
    line_total_difference = Column(Numeric(18, 2), nullable=False, default=0)
    source_hash = Column(String(64), nullable=False, index=True)
    source_payload = Column(EncryptedString(), nullable=False)
    imported_at = Column(DateTime, nullable=False, default=utc_now)
    source_updated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    lines = relationship("DgteraSalesOrderLine", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    payments = relationship("DgteraSalesPayment", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class DgteraSalesOrderLine(Base):
    __tablename__ = "dgtera_sales_order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "external_line_id", name="uq_dgtera_order_line_external"),
    )

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("dgtera_sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    external_line_id = Column(String(80), nullable=False)
    product_id = Column(Integer, ForeignKey("dgtera_products.id"), nullable=False, index=True)
    product_name = Column(String(300), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    discount_percent = Column(Numeric(8, 4), nullable=False, default=0)
    subtotal = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False)
    total = Column(Numeric(18, 2), nullable=False)
    source_tax_ids = Column(String(500))

    order = relationship("DgteraSalesOrder", back_populates="lines")


class DgteraSalesPayment(Base):
    __tablename__ = "dgtera_sales_payments"
    __table_args__ = (
        UniqueConstraint("order_id", "external_payment_id", name="uq_dgtera_payment_external"),
    )

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("dgtera_sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    external_payment_id = Column(String(80), nullable=False)
    external_method_id = Column(String(80))
    method_name = Column(String(250), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)

    order = relationship("DgteraSalesOrder", back_populates="payments")


class DgteraSyncRun(Base):
    __tablename__ = "dgtera_sync_runs"

    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("dgtera_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    window_label = Column(String(100), nullable=False, default="00:01-23:59 Asia/Riyadh")
    status = Column(String(30), nullable=False, default="RUNNING", index=True)
    source_orders = Column(Integer, nullable=False, default=0)
    inserted_orders = Column(Integer, nullable=False, default=0)
    updated_orders = Column(Integer, nullable=False, default=0)
    unchanged_orders = Column(Integer, nullable=False, default=0)
    source_total = Column(Numeric(18, 2), nullable=False, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime)

