from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


class TaxCode(Base):
    __tablename__ = "tax_codes"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_tax_code_company_code"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    direction = Column(String(12), nullable=False, index=True)  # SALES / PURCHASE / BOTH
    category = Column(String(30), nullable=False, index=True)
    rate = Column(Numeric(8, 4), nullable=False, default=0)
    return_box = Column(String(50), nullable=False, index=True)
    deductible_percent = Column(Numeric(8, 4), nullable=False, default=100)
    tax_category_code = Column(String(4), nullable=False, default="S")  # ZATCA S/Z/E/O
    exemption_reason_code = Column(String(20))
    exemption_reason = Column(String(500))
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    system_code = Column(Boolean, nullable=False, default=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=utc_now)


class VatReturnLine(Base):
    __tablename__ = "vat_return_lines"
    __table_args__ = (UniqueConstraint("vat_return_id", "box_code", name="uq_vat_return_line_box"),)

    id = Column(Integer, primary_key=True)
    vat_return_id = Column(Integer, ForeignKey("vat_return_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    box_code = Column(String(50), nullable=False, index=True)
    name_ar = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=False)
    base_amount = Column(Numeric(18, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(18, 2), nullable=False, default=0)
    adjustment_base = Column(Numeric(18, 2), nullable=False, default=0)
    adjustment_tax = Column(Numeric(18, 2), nullable=False, default=0)
    transaction_count = Column(Integer, nullable=False, default=0)
    details_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utc_now)

    vat_return = relationship("VatReturnSnapshot", back_populates="lines")


__all__ = ["TaxCode", "VatReturnLine"]
