"""Comprehensive system reporting center.

Revision ID: e19800000001
Revises: e19700000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e19800000001"
down_revision = "e19700000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column("entry_origin", sa.String(20), nullable=False, server_default="SYSTEM"),
    )
    op.create_index("ix_journal_entries_entry_origin", "journal_entries", ["entry_origin"])
    op.create_table(
        "vat_reporting_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filing_frequency", sa.String(12), nullable=False, server_default="QUARTERLY"),
        sa.Column("return_layout_version", sa.String(50), nullable=False, server_default="ZATCA_STANDARD"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", name="uq_vat_reporting_profile_company"),
    )
    op.create_index("ix_vat_reporting_profiles_company_id", "vat_reporting_profiles", ["company_id"], unique=True)
    op.create_table(
        "system_report_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_code", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("generated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
    )
    for index_name, columns in (
        ("ix_system_report_runs_company_id", ["company_id"]),
        ("ix_system_report_runs_report_code", ["report_code"]),
        ("ix_system_report_runs_period_start", ["period_start"]),
        ("ix_system_report_runs_period_end", ["period_end"]),
        ("ix_system_report_runs_result_sha256", ["result_sha256"]),
        ("ix_system_report_runs_generated_by", ["generated_by"]),
        ("ix_system_report_runs_generated_at", ["generated_at"]),
    ):
        op.create_index(index_name, "system_report_runs", columns)
    bind = op.get_bind()
    for code, name_ar, name_en in (
        ("reports.read", "عرض مركز التقارير الشامل", "View comprehensive reporting center"),
        ("reports.export", "تصدير تقارير النظام", "Export system reports"),
        ("reports.tax.configure", "إدارة إعدادات تقارير الضريبة", "Manage tax reporting settings"),
    ):
        if bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar() is None:
            bind.execute(
                sa.text("INSERT INTO permissions (code,name_ar,name_en) VALUES (:code,:ar,:en)"),
                {"code": code, "ar": name_ar, "en": name_en},
            )
    for role_code, permission_codes in {
        "FINANCIAL_CONTROLLER": ("reports.read", "reports.export", "reports.tax.configure"),
        "CFO": ("reports.read", "reports.export", "reports.tax.configure"),
        "ACCOUNTANT": ("reports.read", "reports.export"),
        "AUDITOR": ("reports.read", "reports.export"),
    }.items():
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE code=:code"), {"code": role_code}).scalar()
        if role_id is None:
            continue
        for permission_code in permission_codes:
            permission_id = bind.execute(
                sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": permission_code}
            ).scalar()
            exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM role_permissions "
                    "WHERE role_id=:role_id AND permission_id=:permission_id"
                ),
                {"role_id": role_id, "permission_id": permission_id},
            ).scalar()
            if exists is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id,permission_id) "
                        "VALUES (:role_id,:permission_id)"
                    ),
                    {"role_id": role_id, "permission_id": permission_id},
                )


def downgrade() -> None:
    bind = op.get_bind()
    for code in ("reports.read", "reports.export", "reports.tax.configure"):
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id=:pid"), {"pid": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id=:pid"), {"pid": permission_id})
    for index_name in (
        "ix_system_report_runs_generated_at",
        "ix_system_report_runs_generated_by",
        "ix_system_report_runs_result_sha256",
        "ix_system_report_runs_period_end",
        "ix_system_report_runs_period_start",
        "ix_system_report_runs_report_code",
        "ix_system_report_runs_company_id",
    ):
        op.drop_index(index_name, table_name="system_report_runs")
    op.drop_table("system_report_runs")
    op.drop_index("ix_vat_reporting_profiles_company_id", table_name="vat_reporting_profiles")
    op.drop_table("vat_reporting_profiles")
    op.drop_index("ix_journal_entries_entry_origin", table_name="journal_entries")
    op.drop_column("journal_entries", "entry_origin")
