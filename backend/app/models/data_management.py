from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.core.time import utc_now
from app.db import Base


class DemoDataRecord(Base):
    """Registry of rows that CORVAX itself created as demonstration data.

    Deletion code must never infer that a row is a demo from its name, date,
    reference, or creator.  Only rows registered here by a trusted seeding/demo
    workflow are eligible for the controlled demo-data purge.
    """

    __tablename__ = "demo_data_records"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "table_name",
            "record_id",
            name="uq_demo_data_record_identity",
        ),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    table_name = Column(String(100), nullable=False, index=True)
    record_id = Column(String(100), nullable=False)
    source = Column(String(50), nullable=False, default="SYSTEM_SEED")
    created_at = Column(DateTime, nullable=False, default=utc_now)
