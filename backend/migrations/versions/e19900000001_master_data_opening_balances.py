"""Master-data imports, item categories, and controlled opening balances.

Revision ID: e19900000001
Revises: e19800000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e19900000001"
down_revision = "e19800000001"
branch_labels = None
depends_on = None


def _permission(bind, code: str, name_ar: str, name_en: str) -> int:
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
    if permission_id is None:
        bind.execute(
            sa.text("INSERT INTO permissions (code,name_ar,name_en) VALUES (:code,:ar,:en)"),
            {"code": code, "ar": name_ar, "en": name_en},
        )
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar_one()
    return int(permission_id)


def upgrade() -> None:
    op.create_table(
        "item_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("item_categories.id")),
        sa.Column("default_item_type", sa.String(30), nullable=False, server_default="INVENTORY"),
        sa.Column("inventory_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("cogs_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("revenue_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("valuation_method", sa.String(30), nullable=False, server_default="WEIGHTED_AVERAGE"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_item_category_company_code"),
    )
    op.create_index("ix_item_categories_company_id", "item_categories", ["company_id"])
    op.create_index("ix_item_categories_code", "item_categories", ["code"])
    with op.batch_alter_table("items") as batch:
        batch.add_column(sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("item_categories.id", name="fk_items_category_id_item_categories"),
        ))

    op.create_table(
        "opening_balance_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_system", sa.String(120), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("total_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("validation_hash", sa.String(64), nullable=False),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("posted_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "opening_date", "version", name="uq_opening_balance_batch_version"),
    )
    for name, columns in (
        ("ix_opening_balance_batches_company_id", ["company_id"]),
        ("ix_opening_balance_batches_opening_date", ["opening_date"]),
        ("ix_opening_balance_batches_status", ["status"]),
    ):
        op.create_index(name, "opening_balance_batches", columns)

    op.create_table(
        "opening_balance_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("opening_balance_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("line_type", sa.String(20), nullable=False, server_default="GL"),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id")),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id")),
        sa.Column("reference_code", sa.String(100)),
        sa.Column("document_date", sa.Date()),
        sa.Column("due_date", sa.Date()),
        sa.Column("quantity", sa.Numeric(18, 4)),
        sa.Column("unit_cost", sa.Numeric(18, 4)),
        sa.Column("lot_number", sa.String(80)),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("description", sa.String(500)),
        sa.UniqueConstraint("batch_id", "line_number", name="uq_opening_balance_batch_line"),
    )
    op.create_index("ix_opening_balance_lines_batch_id", "opening_balance_lines", ["batch_id"])
    op.create_index("ix_opening_balance_lines_line_type", "opening_balance_lines", ["line_type"])

    bind = op.get_bind()
    permissions = {
        "finance.opening.read": ("عرض الأرصدة الافتتاحية", "View opening balances"),
        "finance.opening.manage": ("استيراد وإعداد الأرصدة الافتتاحية", "Prepare opening balances"),
        "finance.opening.approve": ("اعتماد وترحيل الأرصدة الافتتاحية", "Approve opening balances"),
        "masterdata.import": ("استيراد البيانات الرئيسية", "Import master data"),
    }
    ids = {code: _permission(bind, code, ar, en) for code, (ar, en) in permissions.items()}
    for role_code, codes in {
        "CFO": tuple(permissions),
        "FINANCIAL_CONTROLLER": tuple(permissions),
        "ACCOUNTANT": ("finance.opening.read", "finance.opening.manage", "masterdata.import"),
        "AUDITOR": ("finance.opening.read",),
    }.items():
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE code=:code"), {"code": role_code}).scalar()
        if role_id is None:
            continue
        for code in codes:
            exists = bind.execute(
                sa.text("SELECT 1 FROM role_permissions WHERE role_id=:rid AND permission_id=:pid"),
                {"rid": role_id, "pid": ids[code]},
            ).scalar()
            if exists is None:
                bind.execute(
                    sa.text("INSERT INTO role_permissions (role_id,permission_id) VALUES (:rid,:pid)"),
                    {"rid": role_id, "pid": ids[code]},
                )

    # Help is safe for every company role. Data and analysis remain explicitly controlled.
    ai_use = _permission(bind, "ai.assistant.use", "استخدام مساعد كورفاكس", "Use CORVAX AI Assistant")
    for role_id in bind.execute(sa.text("SELECT id FROM roles")).scalars().all():
        if bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_id=:rid AND permission_id=:pid"),
            {"rid": role_id, "pid": ai_use},
        ).scalar() is None:
            bind.execute(
                sa.text("INSERT INTO role_permissions (role_id,permission_id) VALUES (:rid,:pid)"),
                {"rid": role_id, "pid": ai_use},
            )


def downgrade() -> None:
    bind = op.get_bind()
    for code in (
        "finance.opening.read", "finance.opening.manage",
        "finance.opening.approve", "masterdata.import",
    ):
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id=:pid"), {"pid": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id=:pid"), {"pid": permission_id})
    op.drop_index("ix_opening_balance_lines_line_type", table_name="opening_balance_lines")
    op.drop_index("ix_opening_balance_lines_batch_id", table_name="opening_balance_lines")
    op.drop_table("opening_balance_lines")
    op.drop_index("ix_opening_balance_batches_status", table_name="opening_balance_batches")
    op.drop_index("ix_opening_balance_batches_opening_date", table_name="opening_balance_batches")
    op.drop_index("ix_opening_balance_batches_company_id", table_name="opening_balance_batches")
    op.drop_table("opening_balance_batches")
    with op.batch_alter_table("items") as batch:
        batch.drop_column("category_id")
    op.drop_index("ix_item_categories_code", table_name="item_categories")
    op.drop_index("ix_item_categories_company_id", table_name="item_categories")
    op.drop_table("item_categories")
