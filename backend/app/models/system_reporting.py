from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.time import utc_now
from app.db import Base


class VatReportingProfile(Base):
    """Company-level VAT reporting choices used by the unified report period picker."""

    __tablename__ = "vat_reporting_profiles"
    __table_args__ = (UniqueConstraint("company_id", name="uq_vat_reporting_profile_company"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    filing_frequency = Column(String(12), nullable=False, default="QUARTERLY")
    return_layout_version = Column(String(50), nullable=False, default="ZATCA_STANDARD")
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class SystemReportRun(Base):
    """Tamper-evident audit record for every generated system report."""

    __tablename__ = "system_report_runs"

    id = Column(Integer, primary_key=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_code = Column(String(20), nullable=False, index=True)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    filters_json = Column(Text, nullable=False, default="{}")
    row_count = Column(Integer, nullable=False, default=0)
    result_sha256 = Column(String(64), nullable=False, index=True)
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    generated_at = Column(DateTime, nullable=False, default=utc_now, index=True)


__all__ = ["VatReportingProfile", "SystemReportRun"]
