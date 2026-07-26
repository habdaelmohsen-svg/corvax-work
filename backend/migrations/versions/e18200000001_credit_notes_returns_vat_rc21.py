"""Sales and purchase returns, credit notes and VAT adjustments RC21

Revision ID: e18200000001
Revises: e18100000001
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "e18200000001"
down_revision = "e18100000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "credit_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("note_date", sa.Date(), nullable=False),
        sa.Column("note_type", sa.String(12), nullable=False),
        sa.Column("original_sales_invoice_id", sa.Integer(), sa.ForeignKey("sales_invoices.id")),
        sa.Column("original_purchase_invoice_id", sa.Integer(), sa.ForeignKey("purchase_invoices.id")),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.Column("reason_code", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("external_reference", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("subtotal", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("vat_amount", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("unapplied_credit", sa.Numeric(18,2), nullable=False, server_default="0"),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("zatca_uuid", sa.String(80), nullable=False),
        sa.Column("original_document_number", sa.String(100), nullable=False),
        sa.Column("original_document_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.CheckConstraint("note_type in ('SALES','PURCHASE')", name="ck_credit_note_type"),
        sa.UniqueConstraint("company_id", "number", name="uq_credit_note_company_number"),
        sa.UniqueConstraint("zatca_uuid", name="uq_credit_note_zatca_uuid"),
    )
    for col in ("company_id","number","note_date","note_type","original_sales_invoice_id","original_purchase_invoice_id","party_id","reason_code","status","zatca_uuid"):
        op.create_index(f"ix_credit_notes_{col}", "credit_notes", [col])

    op.create_table(
        "credit_note_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credit_note_id", sa.Integer(), sa.ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_sales_invoice_line_id", sa.Integer(), sa.ForeignKey("sales_invoice_lines.id")),
        sa.Column("original_purchase_invoice_line_id", sa.Integer(), sa.ForeignKey("purchase_invoice_lines.id")),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(18,4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18,4), nullable=False),
        sa.Column("subtotal", sa.Numeric(18,2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("total", sa.Numeric(18,2), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id")),
        sa.Column("inventory_disposition", sa.String(25), nullable=False, server_default="NONE"),
        sa.Column("unit_cost", sa.Numeric(18,6), nullable=False, server_default="0"),
        sa.Column("inventory_value", sa.Numeric(18,2), nullable=False, server_default="0"),
    )
    for col in ("credit_note_id","original_sales_invoice_line_id","original_purchase_invoice_line_id","tax_code_id","item_id","warehouse_id"):
        op.create_index(f"ix_credit_note_lines_{col}", "credit_note_lines", [col])

    op.create_table(
        "credit_note_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credit_note_id", sa.Integer(), sa.ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("open_item_id", sa.Integer(), sa.ForeignKey("financial_open_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18,2), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("credit_note_id", "open_item_id", name="uq_credit_note_open_item"),
    )
    for col in ("company_id","credit_note_id","open_item_id","application_date"):
        op.create_index(f"ix_credit_note_applications_{col}", "credit_note_applications", [col])

    op.create_table(
        "party_credit_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ledger_type", sa.String(2), nullable=False),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="CREDIT_NOTE"),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_number", sa.String(100), nullable=False),
        sa.Column("balance_date", sa.Date(), nullable=False),
        sa.Column("original_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("available_amount", sa.Numeric(18,2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("ledger_type in ('AR','AP')", name="ck_party_credit_ledger_type"),
        sa.UniqueConstraint("source_id", name="uq_party_credit_source"),
    )
    for col in ("company_id","ledger_type","party_id","source_id","document_number","balance_date","status"):
        op.create_index(f"ix_party_credit_balances_{col}", "party_credit_balances", [col])

    conn = op.get_bind()
    companies = [r[0] for r in conn.execute(sa.text("select id from companies")).fetchall()]
    accounts = [
        ("424020", "أرباح مرتجعات المشتريات", "Purchase Return Cost Gains", "REVENUE", "OTHER_INCOME", "400000"),
        ("624110", "خسائر تكاليف مرتجعات المشتريات", "Purchase Return Unrecovered Costs", "EXPENSE", "COST_OF_REVENUE", "600000"),
    ]
    for company_id in companies:
        for code, ar, en, account_type, statement_group, parent_code in accounts:
            conn.execute(sa.text("""
                insert into accounts
                (company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
                select :company_id,:code,:ar,:en,:account_type,:statement_group,
                       (select id from accounts where company_id=:company_id and code=:parent_code),3,1,0,1
                where not exists(select 1 from accounts where company_id=:company_id and code=:code)
            """), dict(company_id=company_id, code=code, ar=ar, en=en, account_type=account_type,
                       statement_group=statement_group, parent_code=parent_code))


def downgrade():
    op.drop_table("party_credit_balances")
    op.drop_table("credit_note_applications")
    op.drop_table("credit_note_lines")
    op.drop_table("credit_notes")
