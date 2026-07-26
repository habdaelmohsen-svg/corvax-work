"""CORVAX RC27.4 H13 - Construction in Progress (CIP) projects + central attachments.

Accounting design (agreed with the owner, aligned with IAS 16 / IAS 23 / IAS 38):

  * Signing a contract creates NO journal entry. It is a capital commitment used for
    tracking only. This keeps VAT correct (VAT arises with the certificate/invoice,
    not with the signature) and avoids inflating the balance sheet with work not done.

  * A progress certificate (مستخلص) is what creates the obligation:
        Dr  Construction in Progress        (net work value)
        Dr  VAT input                       (VAT on the certificate)
            Cr  Contractors payable         (net + VAT - retention)
            Cr  Retention payable           (retention %, a real liability)

  * Payment settles the payable only. Retention is released separately after the
    warranty period.

  * Costs are classified CAPITALIZE vs EXPENSE. The system warns loudly on
    non-capitalizable categories (formation costs, training, admin overhead,
    abnormal waste, pre-opening marketing) but leaves the final decision to the
    user, as requested.

  * On completion the accumulated CIP balance is capitalized into a FixedAsset and
    depreciation starts. Capitalization stops when the asset is READY for use, not
    when it is actually used.

Attachments are central: any document anywhere in the platform (invoice, contract,
receipt, payment voucher, certificate) can carry files. Storage is hybrid - small
files inline in the database, larger ones delegated to external object storage.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.db import Base


# ============================================================ CENTRAL ATTACHMENTS
class Attachment(Base):
    """A file attached to any entity in the system.

    entity_type/entity_id form a soft polymorphic link (e.g. 'CIP_CONTRACT', 'SALES_INVOICE',
    'RECEIPT', 'PAYMENT', 'PROGRESS_CERTIFICATE'). Storage is hybrid:
      * storage_kind='DB'       -> bytes held in `content` (good for small scans/PDFs)
      * storage_kind='EXTERNAL' -> `external_url` points at S3/R2 and `content` is null
    """
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    file_name = Column(String(300), nullable=False)
    content_type = Column(String(120), nullable=False, default="application/octet-stream")
    size_bytes = Column(Integer, nullable=False, default=0)
    storage_kind = Column(String(20), nullable=False, default="DB")  # DB / EXTERNAL
    content = Column(LargeBinary)          # populated when storage_kind='DB'
    external_url = Column(String(600))     # populated when storage_kind='EXTERNAL'
    checksum_sha256 = Column(String(64))
    description_ar = Column(String(300))
    description_en = Column(String(300))
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


# ============================================================ CIP PROJECTS
class CipProject(Base):
    """A capital project under construction (e.g. building a hangar)."""
    __tablename__ = "cip_projects"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_cip_project_company_code"),)
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    name_ar = Column(String(250), nullable=False)
    name_en = Column(String(250), nullable=False)
    description = Column(Text)
    budget_amount = Column(Numeric(18, 2), nullable=False, default=0)
    start_date = Column(Date)
    expected_completion_date = Column(Date)
    ready_for_use_date = Column(Date)  # capitalization stops here (IAS 16.20)
    # Running totals, maintained by the service layer.
    capitalized_cost = Column(Numeric(18, 2), nullable=False, default=0)   # sits in CIP account
    expensed_cost = Column(Numeric(18, 2), nullable=False, default=0)      # charged to P&L
    status = Column(String(20), nullable=False, default="PLANNING", index=True)
    # PLANNING / IN_PROGRESS / READY / CAPITALIZED / CANCELLED
    fixed_asset_id = Column(Integer, ForeignKey("fixed_assets.id"))  # set after transfer
    capitalization_journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class CipContract(Base):
    """A contract with a contractor or supplier for a project.

    Signing does NOT post a journal entry - it is a capital commitment. The contract
    is the anchor for the contractor statement (كشف حساب المقاول).
    """
    __tablename__ = "cip_contracts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("cip_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False, index=True)  # contractor/supplier
    title_ar = Column(String(250), nullable=False)
    title_en = Column(String(250), nullable=False)
    contract_type = Column(String(30), nullable=False, default="CONTRACTOR")  # CONTRACTOR / SUPPLIER / CONSULTANT
    contract_value = Column(Numeric(18, 2), nullable=False, default=0)  # net of VAT
    vat_rate = Column(Numeric(6, 2), nullable=False, default=15)
    retention_rate = Column(Numeric(6, 2), nullable=False, default=0)   # 0 = no retention
    warranty_end_date = Column(Date)
    signed_date = Column(Date)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    # ACTIVE / COMPLETED / TERMINATED
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    project = relationship("CipProject", lazy="joined")


class CipProgressCertificate(Base):
    """A progress certificate (مستخلص) - the event that creates the obligation."""
    __tablename__ = "cip_progress_certificates"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("cip_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    certificate_date = Column(Date, nullable=False)
    work_value = Column(Numeric(18, 2), nullable=False)      # net work executed this certificate
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    retention_amount = Column(Numeric(18, 2), nullable=False, default=0)
    net_payable = Column(Numeric(18, 2), nullable=False, default=0)  # work + vat - retention
    paid_amount = Column(Numeric(18, 2), nullable=False, default=0)
    supplier_invoice_number = Column(String(80))
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT / APPROVED / PAID / CANCELLED
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    contract = relationship("CipContract", lazy="joined")


class CipCost(Base):
    """A direct project cost that does not come through a contract certificate.

    Every cost must be explicitly classified. The API warns when the chosen category
    is not capitalizable under IAS 16/38, but the user keeps the final say.
    """
    __tablename__ = "cip_costs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("cip_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(String(40), nullable=False, index=True)
    cost_date = Column(Date, nullable=False)
    category = Column(String(40), nullable=False)
    # capitalizable: MATERIALS, DIRECT_LABOR, SITE_PREPARATION, ENGINEERING, PERMITS,
    #                TRANSPORT_INSTALLATION, TESTING, BORROWING_COST
    # expense:       FORMATION_COSTS, TRAINING, ADMIN_OVERHEAD, MARKETING,
    #                ABNORMAL_WASTE, IDLE_TIME, PRE_OPENING_LOSSES
    treatment = Column(String(20), nullable=False, default="CAPITALIZE")  # CAPITALIZE / EXPENSE
    description_ar = Column(String(300), nullable=False)
    description_en = Column(String(300))
    amount = Column(Numeric(18, 2), nullable=False)
    vat_amount = Column(Numeric(18, 2), nullable=False, default=0)
    party_id = Column(Integer, ForeignKey("parties.id"))
    expense_account_code = Column(String(30))  # used when treatment='EXPENSE'
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    warning_acknowledged = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class CipPayment(Base):
    """A payment made against a progress certificate or a retention release."""
    __tablename__ = "cip_payments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("cip_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    certificate_id = Column(Integer, ForeignKey("cip_progress_certificates.id"))
    number = Column(String(40), nullable=False, index=True)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    payment_kind = Column(String(20), nullable=False, default="CERTIFICATE")  # CERTIFICATE / RETENTION_RELEASE / ADVANCE
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    reference = Column(String(120))
    journal_id = Column(Integer, ForeignKey("journal_entries.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


__all__ = [
    "Attachment",
    "CipProject", "CipContract", "CipProgressCertificate", "CipCost", "CipPayment",
]
