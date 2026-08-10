"""R9 operational assurance, controlled import, and ZATCA-readiness records.

These tables deliberately store evidence and staged data only.  They never contain
database credentials, signing keys, CSIDs, OTPs, or production ZATCA responses.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.time import utc_now
from app.db import Base


class R9PlatformAlert(Base):
    __tablename__ = "r9_platform_alerts"
    __table_args__ = (UniqueConstraint("company_id", "fingerprint", name="uq_r9_alert_fingerprint"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False)
    category = Column(String(30), nullable=False, index=True)
    severity = Column(String(12), nullable=False, index=True)
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    details_json = Column(Text)
    source_entity_type = Column(String(80))
    source_entity_id = Column(String(80))
    status = Column(String(20), nullable=False, default="OPEN", index=True)
    assigned_to = Column(Integer, ForeignKey("users.id"))
    due_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolution_notes = Column(Text)
    resolved_at = Column(DateTime)
    detected_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now)


class R9ImportBatch(Base):
    __tablename__ = "r9_import_batches"
    __table_args__ = (UniqueConstraint("company_id", "file_sha256", "target_type", name="uq_r9_import_file_target"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type = Column(String(40), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_sha256 = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="STAGED", index=True)
    total_rows = Column(Integer, nullable=False, default=0)
    valid_rows = Column(Integer, nullable=False, default=0)
    invalid_rows = Column(Integer, nullable=False, default=0)
    validation_summary_json = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    validated_by = Column(Integer, ForeignKey("users.id"))
    validated_at = Column(DateTime)
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)


class R9ImportRow(Base):
    __tablename__ = "r9_import_rows"
    __table_args__ = (UniqueConstraint("batch_id", "row_number", name="uq_r9_import_batch_row"),)

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("r9_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    payload_json = Column(Text, nullable=False)
    normalized_json = Column(Text)
    validation_status = Column(String(20), nullable=False, default="PENDING", index=True)
    errors_json = Column(Text)


class R9RestoreDrill(Base):
    __tablename__ = "r9_restore_drills"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    backup_id = Column(Integer, ForeignKey("backup_records.id"), nullable=False, index=True)
    environment = Column(String(30), nullable=False, default="ISOLATED_TEST")
    status = Column(String(20), nullable=False)
    integrity_check = Column(String(40), nullable=False)
    notes = Column(Text, nullable=False)
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    performed_at = Column(DateTime, nullable=False, default=utc_now, index=True)


class R9ZatcaReadiness(Base):
    __tablename__ = "r9_zatca_readiness"
    __table_args__ = (UniqueConstraint("company_id", name="uq_r9_zatca_readiness_company"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    onboarding_status = Column(String(30), nullable=False, default="NOT_STARTED")
    environment = Column(String(20), nullable=False, default="SANDBOX")
    production_connected = Column(Boolean, nullable=False, default=False)
    seller_identity_ready = Column(Boolean, nullable=False, default=False)
    certificate_configured = Column(Boolean, nullable=False, default=False)
    signing_key_configured = Column(Boolean, nullable=False, default=False)
    sdk_validation_ready = Column(Boolean, nullable=False, default=False)
    last_validation_at = Column(DateTime)
    notes = Column(Text)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=utc_now)


class R9ZatcaSandboxSubmission(Base):
    __tablename__ = "r9_zatca_sandbox_submissions"
    __table_args__ = (UniqueConstraint("company_id", "invoice_uuid", name="uq_r9_zatca_sandbox_uuid"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(40), nullable=False)
    source_id = Column(String(80), nullable=False)
    invoice_uuid = Column(String(36), nullable=False)
    invoice_hash = Column(String(64), nullable=False)
    previous_invoice_hash = Column(String(64))
    qr_metadata_base64 = Column(Text, nullable=False)
    validation_status = Column(String(20), nullable=False)
    validation_errors_json = Column(Text)
    submission_status = Column(String(30), nullable=False, default="NOT_SUBMITTED")
    sandbox_correlation_id = Column(String(100))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


__all__ = [
    "R9PlatformAlert", "R9ImportBatch", "R9ImportRow", "R9RestoreDrill",
    "R9ZatcaReadiness", "R9ZatcaSandboxSubmission",
]
