"""R9 operational efficiency, supplier control and assurance evidence.

Revision ID: e20500000001
Revises: e20400000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e20500000001"
down_revision = "e20400000001"
branch_labels = None
depends_on = None


PERMISSIONS = {
    "platform.view": ("عرض صحة النظام والرقابة التشغيلية", "View platform health and operational assurance"),
    "platform.manage": ("إدارة صحة النظام والتنبيهات", "Manage platform health and alerts"),
    "import.stage": ("إعداد واستعراض ملفات الاستيراد", "Stage and validate import files"),
    "import.approve": ("اعتماد ملفات الاستيراد المرحلية", "Approve staged import files"),
    "zatca.manage": ("إدارة جاهزية الفوترة الإلكترونية", "Manage e-invoicing readiness"),
}

ROLE_GRANTS = {
    "CFO": tuple(PERMISSIONS),
    "FINANCIAL_CONTROLLER": ("platform.view", "import.approve"),
    "AUDITOR": ("platform.view",),
    "IT_MANAGER": ("platform.view", "platform.manage", "import.stage"),
    "ACCOUNTANT": ("platform.view", "import.stage"),
    "QUALITY_MANAGER": ("platform.view",),
}


def _index(table: str, column: str) -> None:
    op.create_index(f"ix_{table}_{column}", table, [column])


def _seed_permissions() -> None:
    bind = op.get_bind()
    for code, (name_ar, name_en) in PERMISSIONS.items():
        bind.execute(sa.text(
            "INSERT INTO permissions (code,name_ar,name_en) "
            "SELECT :code,:ar,:en WHERE NOT EXISTS "
            "(SELECT 1 FROM permissions WHERE code=:code)"
        ), {"code": code, "ar": name_ar, "en": name_en})
    for role_code, codes in ROLE_GRANTS.items():
        for code in codes:
            bind.execute(sa.text(
                "INSERT INTO role_permissions (role_id,permission_id) "
                "SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code=:permission "
                "WHERE r.code=:role AND NOT EXISTS ("
                "SELECT 1 FROM role_permissions rp WHERE rp.role_id=r.id AND rp.permission_id=p.id)"
            ), {"role": role_code, "permission": code})
    # Preserve the meaning of wildcard roles after adding new permissions.
    for code in PERMISSIONS:
        bind.execute(sa.text(
            "INSERT INTO role_permissions (role_id,permission_id) "
            "SELECT DISTINCT rp.role_id,p_new.id FROM role_permissions rp "
            "JOIN permissions p_all ON p_all.id=rp.permission_id AND p_all.code='*' "
            "JOIN permissions p_new ON p_new.code=:code "
            "WHERE NOT EXISTS (SELECT 1 FROM role_permissions x "
            "WHERE x.role_id=rp.role_id AND x.permission_id=p_new.id)"
        ), {"code": code})


def upgrade() -> None:
    op.create_table(
        "supplier_procurement_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commercial_registration", sa.String(80)),
        sa.Column("contact_name", sa.String(160)),
        sa.Column("contact_email", sa.String(254)),
        sa.Column("contact_phone", sa.String(40)),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("delivery_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("price_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("rejection_rate", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("approved_iban", sa.String(1024)),
        sa.Column("pending_iban", sa.String(1024)),
        sa.Column("iban_status", sa.String(25), nullable=False, server_default="NOT_PROVIDED"),
        sa.Column("iban_change_risk", sa.String(20), nullable=False, server_default="NONE"),
        sa.Column("iban_change_requested_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("iban_change_requested_at", sa.DateTime()),
        sa.Column("iban_approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("iban_approved_at", sa.DateTime()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "supplier_id", name="uq_supplier_procurement_profile"),
    )
    for column in ("company_id", "supplier_id", "iban_status", "iban_change_risk"):
        _index("supplier_procurement_profiles", column)

    op.create_table(
        "mobile_receipt_inspections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goods_receipt_line_id", sa.Integer(), sa.ForeignKey("goods_receipt_lines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_line_id", sa.Integer(), sa.ForeignKey("purchase_order_lines.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("barcode_value", sa.String(160), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("rejected_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("lot_number", sa.String(80), nullable=False),
        sa.Column("production_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("storage_location", sa.String(120), nullable=False),
        sa.Column("evidence_metadata", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("quality_status", sa.String(24), nullable=False, server_default="ACCEPTED"),
        sa.Column("inspected_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("inspected_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("goods_receipt_line_id", name="uq_mobile_inspection_grn_line"),
    )
    for column in ("company_id", "goods_receipt_id", "purchase_order_line_id", "item_id"):
        _index("mobile_receipt_inspections", column)

    op.create_table(
        "r9_platform_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("details_json", sa.Text()),
        sa.Column("source_entity_type", sa.String(80)),
        sa.Column("source_entity_id", sa.String(80)),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("due_at", sa.DateTime()),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("resolution_notes", sa.Text()),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "fingerprint", name="uq_r9_alert_fingerprint"),
    )
    for column in ("company_id", "category", "severity", "status", "detected_at"):
        _index("r9_platform_alerts", column)

    op.create_table(
        "r9_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="STAGED"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_summary_json", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("validated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("validated_at", sa.DateTime()),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "file_sha256", "target_type", name="uq_r9_import_file_target"),
    )
    for column in ("company_id", "target_type", "status"):
        _index("r9_import_batches", column)

    op.create_table(
        "r9_import_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("r9_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("normalized_json", sa.Text()),
        sa.Column("validation_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("errors_json", sa.Text()),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_r9_import_batch_row"),
    )
    _index("r9_import_rows", "batch_id")
    _index("r9_import_rows", "validation_status")

    op.create_table(
        "r9_restore_drills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("backup_id", sa.Integer(), sa.ForeignKey("backup_records.id"), nullable=False),
        sa.Column("environment", sa.String(30), nullable=False, server_default="ISOLATED_TEST"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("integrity_check", sa.String(40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("performed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("performed_at", sa.DateTime(), nullable=False),
    )
    for column in ("company_id", "backup_id", "performed_at"):
        _index("r9_restore_drills", column)

    op.create_table(
        "r9_zatca_readiness",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("onboarding_status", sa.String(30), nullable=False, server_default="NOT_STARTED"),
        sa.Column("environment", sa.String(20), nullable=False, server_default="SANDBOX"),
        sa.Column("production_connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seller_identity_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("certificate_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("signing_key_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sdk_validation_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_validation_at", sa.DateTime()),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", name="uq_r9_zatca_readiness_company"),
    )
    _index("r9_zatca_readiness", "company_id")

    op.create_table(
        "r9_zatca_sandbox_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("invoice_uuid", sa.String(36), nullable=False),
        sa.Column("invoice_hash", sa.String(64), nullable=False),
        sa.Column("previous_invoice_hash", sa.String(64)),
        sa.Column("qr_metadata_base64", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(20), nullable=False),
        sa.Column("validation_errors_json", sa.Text()),
        sa.Column("submission_status", sa.String(30), nullable=False, server_default="NOT_SUBMITTED"),
        sa.Column("sandbox_correlation_id", sa.String(100)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "invoice_uuid", name="uq_r9_zatca_sandbox_uuid"),
    )
    _index("r9_zatca_sandbox_submissions", "company_id")

    _seed_permissions()


def downgrade() -> None:
    for table in (
        "r9_zatca_sandbox_submissions", "r9_zatca_readiness", "r9_restore_drills",
        "r9_import_rows", "r9_import_batches", "r9_platform_alerts",
        "mobile_receipt_inspections", "supplier_procurement_profiles",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for code in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id=:id"), {"id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id=:id"), {"id": permission_id})
