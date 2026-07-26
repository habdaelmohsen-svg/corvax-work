"""AR/AP invoice allocation and native aging RC18

Revision ID: e17800000001
Revises: e17700000001
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "e17800000001"
down_revision = "e17700000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_open_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ledger_type", sa.String(2), nullable=False),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.Integer()),
        sa.Column("document_number", sa.String(100), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("original_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="OPEN"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("notes", sa.String(500)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("ledger_type in ('AR','AP')", name="ck_open_item_ledger_type"),
        sa.CheckConstraint("original_amount > 0", name="ck_open_item_positive_amount"),
        sa.UniqueConstraint("company_id", "ledger_type", "source_type", "source_id", name="uq_open_item_source"),
        sa.UniqueConstraint("company_id", "ledger_type", "document_number", name="uq_open_item_document"),
    )
    for col in ("company_id", "ledger_type", "party_id", "source_type", "document_number", "document_date", "due_date", "status"):
        op.create_index(f"ix_financial_open_items_{col}", "financial_open_items", [col])

    op.create_table(
        "financial_settlement_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("open_item_id", sa.Integer(), sa.ForeignKey("financial_open_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id", ondelete="CASCADE")),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id", ondelete="CASCADE")),
        sa.Column("allocation_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reversed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("reversed_at", sa.DateTime()),
        sa.Column("reversal_reason", sa.String(500)),
        sa.CheckConstraint("amount > 0", name="ck_settlement_allocation_positive"),
        sa.CheckConstraint("(receipt_id is not null and payment_id is null) or (receipt_id is null and payment_id is not null)", name="ck_settlement_allocation_one_source"),
    )
    for col in ("company_id", "open_item_id", "receipt_id", "payment_id", "allocation_date"):
        op.create_index(f"ix_financial_settlement_allocations_{col}", "financial_settlement_allocations", [col])

    conn = op.get_bind()
    # Backfill every posted invoice so native aging starts complete after upgrade.
    conn.execute(sa.text("""
        insert into financial_open_items
        (company_id, ledger_type, party_id, source_type, source_id, document_number, document_date, due_date,
         original_amount, status, journal_id, created_by, created_at)
        select company_id, 'AR', customer_id, 'SALES_INVOICE', id, number, invoice_date, due_date,
               total, 'OPEN', journal_id, created_by, created_at
        from sales_invoices where status='POSTED'
    """))
    conn.execute(sa.text("""
        insert into financial_open_items
        (company_id, ledger_type, party_id, source_type, source_id, document_number, document_date, due_date,
         original_amount, status, journal_id, created_by, created_at)
        select company_id, 'AP', supplier_id, 'PURCHASE_INVOICE', id, number, invoice_date, due_date,
               total, 'OPEN', journal_id, created_by, created_at
        from purchase_invoices where status='POSTED'
    """))

    permissions = [
        ("finance.arap.read", "عرض أعمار العملاء والموردين", "View AR/AP aging"),
        ("finance.arap.allocate", "تخصيص التحصيلات والمدفوعات", "Allocate receipts and payments"),
        ("finance.arap.opening", "إدارة الأرصدة الافتتاحية التفصيلية", "Manage detailed opening balances"),
    ]
    for code, ar, en in permissions:
        if not conn.execute(sa.text("select id from permissions where code=:code"), {"code": code}).scalar():
            conn.execute(sa.text("insert into permissions(code,name_ar,name_en) values(:code,:ar,:en)"), {"code": code, "ar": ar, "en": en})
    role_map = {
        "CFO": [x[0] for x in permissions],
        "FINANCIAL_CONTROLLER": [x[0] for x in permissions],
        "ACCOUNTANT": [x[0] for x in permissions],
        "AUDITOR": ["finance.arap.read"],
    }
    for role_code, codes in role_map.items():
        role_id = conn.execute(sa.text("select id from roles where code=:code"), {"code": role_code}).scalar()
        if not role_id:
            continue
        for code in codes:
            permission_id = conn.execute(sa.text("select id from permissions where code=:code"), {"code": code}).scalar()
            if permission_id and not conn.execute(sa.text("select 1 from role_permissions where role_id=:r and permission_id=:p"), {"r": role_id, "p": permission_id}).scalar():
                conn.execute(sa.text("insert into role_permissions(role_id,permission_id) values(:r,:p)"), {"r": role_id, "p": permission_id})


def downgrade():
    op.drop_table("financial_settlement_allocations")
    op.drop_table("financial_open_items")
