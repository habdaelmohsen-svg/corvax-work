from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"
    __table_args__ = (UniqueConstraint("company_id", "branch_id", "code", name="uq_restaurant_table_branch_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(150), nullable=False)
    name_en = Column(String(150), nullable=False)
    area = Column(String(80))
    capacity = Column(Integer, nullable=False, default=4)
    status = Column(String(25), nullable=False, default="AVAILABLE", index=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class RestaurantReservation(Base):
    __tablename__ = "restaurant_reservations"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_restaurant_reservation_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    table_id = Column(Integer, ForeignKey("restaurant_tables.id"), index=True)
    number = Column(String(50), nullable=False, index=True)
    customer_name = Column(String(200), nullable=False)
    mobile = Column(String(30))
    guest_count = Column(Integer, nullable=False)
    reservation_at = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False, default=90)
    status = Column(String(25), nullable=False, default="BOOKED", index=True)
    notes = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    seated_at = Column(DateTime)
    completed_at = Column(DateTime)

    table = relationship("RestaurantTable", lazy="joined")


class CashierShift(Base):
    __tablename__ = "cashier_shifts"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_cashier_shift_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    number = Column(String(50), nullable=False, index=True)
    business_date = Column(Date, nullable=False, index=True)
    opening_balance = Column(Numeric(18, 2), nullable=False, default=0)
    cash_sales = Column(Numeric(18, 2), nullable=False, default=0)
    cash_refunds = Column(Numeric(18, 2), nullable=False, default=0)
    expected_cash = Column(Numeric(18, 2), nullable=False, default=0)
    counted_cash = Column(Numeric(18, 2))
    variance = Column(Numeric(18, 2))
    status = Column(String(30), nullable=False, default="OPEN", index=True)
    notes = Column(String(500))
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    closed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    opened_at = Column(DateTime, nullable=False, default=utc_now)
    submitted_at = Column(DateTime)
    approved_at = Column(DateTime)


class KitchenStation(Base):
    __tablename__ = "kitchen_stations"
    __table_args__ = (UniqueConstraint("company_id", "branch_id", "code", name="uq_kitchen_station_branch_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_ar = Column(String(150), nullable=False)
    name_en = Column(String(150), nullable=False)
    sequence = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)


class MenuKitchenStation(Base):
    __tablename__ = "menu_kitchen_stations"
    __table_args__ = (UniqueConstraint("menu_item_id", name="uq_menu_kitchen_station_menu_item"),)

    id = Column(Integer, primary_key=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True)
    kitchen_station_id = Column(Integer, ForeignKey("kitchen_stations.id", ondelete="CASCADE"), nullable=False, index=True)

    station = relationship("KitchenStation", lazy="joined")


class KitchenTicket(Base):
    __tablename__ = "kitchen_tickets"
    __table_args__ = (UniqueConstraint("pos_order_id", "kitchen_station_id", name="uq_kitchen_ticket_order_station"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    pos_order_id = Column(Integer, ForeignKey("pos_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    kitchen_station_id = Column(Integer, ForeignKey("kitchen_stations.id"), nullable=False, index=True)
    number = Column(String(60), nullable=False, unique=True, index=True)
    priority = Column(Integer, nullable=False, default=0)
    status = Column(String(25), nullable=False, default="NEW", index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    accepted_at = Column(DateTime)
    started_at = Column(DateTime)
    ready_at = Column(DateTime)
    served_at = Column(DateTime)

    station = relationship("KitchenStation", lazy="joined")
    order = relationship("PosOrder", lazy="joined")
    lines = relationship("KitchenTicketLine", back_populates="ticket", cascade="all, delete-orphan", lazy="selectin")


class KitchenTicketLine(Base):
    __tablename__ = "kitchen_ticket_lines"

    id = Column(Integer, primary_key=True)
    kitchen_ticket_id = Column(Integer, ForeignKey("kitchen_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    pos_order_line_id = Column(Integer, ForeignKey("pos_order_lines.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    status = Column(String(25), nullable=False, default="NEW", index=True)
    notes = Column(String(500))

    ticket = relationship("KitchenTicket", back_populates="lines")
    order_line = relationship("PosOrderLine", lazy="joined")


class PosControlRequest(Base):
    __tablename__ = "pos_control_requests"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_pos_control_request_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    pos_order_id = Column(Integer, ForeignKey("pos_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    request_type = Column(String(20), nullable=False, index=True)
    reason = Column(String(500), nullable=False)
    refund_bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"))
    restore_inventory = Column(Boolean, nullable=False, default=False)
    refund_net = Column(Numeric(18, 2), nullable=False, default=0)
    refund_vat = Column(Numeric(18, 2), nullable=False, default=0)
    refund_total = Column(Numeric(18, 2), nullable=False, default=0)
    restored_food_cost = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(30), nullable=False, default="SUBMITTED", index=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    rejected_by = Column(Integer, ForeignKey("users.id"))
    reversal_sale_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    reversal_cogs_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)
    rejected_at = Column(DateTime)
    rejection_reason = Column(String(500))

    order = relationship("PosOrder", lazy="joined")
    lines = relationship("PosControlLine", back_populates="request", cascade="all, delete-orphan", lazy="selectin")


class PosControlLine(Base):
    __tablename__ = "pos_control_lines"

    id = Column(Integer, primary_key=True)
    control_request_id = Column(Integer, ForeignKey("pos_control_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    pos_order_line_id = Column(Integer, ForeignKey("pos_order_lines.id"), nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    refund_net = Column(Numeric(18, 2), nullable=False)
    refund_vat = Column(Numeric(18, 2), nullable=False)
    refund_total = Column(Numeric(18, 2), nullable=False)
    restored_food_cost = Column(Numeric(18, 2), nullable=False)

    request = relationship("PosControlRequest", back_populates="lines")
    order_line = relationship("PosOrderLine", lazy="joined")


class PlatformSettlementBatch(Base):
    __tablename__ = "platform_settlement_batches"
    __table_args__ = (UniqueConstraint("company_id", "settlement_reference", name="uq_platform_settlement_reference"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    platform_id = Column(Integer, ForeignKey("delivery_platforms.id"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    settlement_reference = Column(String(100), nullable=False, index=True)
    settlement_date = Column(Date, nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    gross_sales = Column(Numeric(18, 2), nullable=False)
    commission_amount = Column(Numeric(18, 2), nullable=False)
    other_fees = Column(Numeric(18, 2), nullable=False, default=0)
    expected_net = Column(Numeric(18, 2), nullable=False)
    received_net = Column(Numeric(18, 2), nullable=False)
    variance = Column(Numeric(18, 2), nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime)
    approved_at = Column(DateTime)

    platform = relationship("DeliveryPlatform", lazy="joined")
    lines = relationship("PlatformSettlementLine", back_populates="batch", cascade="all, delete-orphan", lazy="selectin")


class PlatformSettlementLine(Base):
    __tablename__ = "platform_settlement_lines"
    __table_args__ = (UniqueConstraint("pos_order_id", name="uq_platform_settlement_order"),)

    id = Column(Integer, primary_key=True)
    settlement_batch_id = Column(Integer, ForeignKey("platform_settlement_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    pos_order_id = Column(Integer, ForeignKey("pos_orders.id"), nullable=False, index=True)
    gross_amount = Column(Numeric(18, 2), nullable=False)
    commission_amount = Column(Numeric(18, 2), nullable=False)
    expected_net = Column(Numeric(18, 2), nullable=False)

    batch = relationship("PlatformSettlementBatch", back_populates="lines")
    order = relationship("PosOrder", lazy="joined")


class RestaurantWasteRecord(Base):
    __tablename__ = "restaurant_waste_records"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_restaurant_waste_number"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    number = Column(String(60), nullable=False, index=True)
    waste_date = Column(Date, nullable=False, index=True)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit_cost = Column(Numeric(18, 4), nullable=False)
    total_cost = Column(Numeric(18, 2), nullable=False)
    reason_code = Column(String(40), nullable=False)
    reason = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="SUBMITTED", index=True)
    prepared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    approved_at = Column(DateTime)

    item = relationship("Item", lazy="joined")


class OfflinePosTransaction(Base):
    __tablename__ = "offline_pos_transactions"
    __table_args__ = (UniqueConstraint("company_id", "device_id", "client_transaction_id", name="uq_offline_pos_client_transaction"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), nullable=False, index=True)
    client_transaction_id = Column(String(120), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    status = Column(String(25), nullable=False, default="PENDING", index=True)
    pos_order_id = Column(Integer, ForeignKey("pos_orders.id"))
    conflict_reason = Column(String(500))
    received_at = Column(DateTime, nullable=False, default=utc_now)
    processed_at = Column(DateTime)


__all__ = [
    "RestaurantTable", "RestaurantReservation", "CashierShift", "KitchenStation", "MenuKitchenStation",
    "KitchenTicket", "KitchenTicketLine", "PosControlRequest", "PosControlLine",
    "PlatformSettlementBatch", "PlatformSettlementLine", "RestaurantWasteRecord", "OfflinePosTransaction",
]
