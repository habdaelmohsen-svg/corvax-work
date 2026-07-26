"""VAT return classification and tax code matrix RC19

Revision ID: e17900000001
Revises: e17800000001
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "e17900000001"
down_revision = "e17800000001"
branch_labels = None
depends_on = None

DEFAULTS = [
    ("S15", "مبيعات محلية خاضعة 15%", "Standard-rated domestic sales 15%", "SALES", "STANDARD", 15, "SALES_STANDARD", 0, "S"),
    ("S0", "مبيعات محلية خاضعة بنسبة صفر", "Zero-rated domestic sales", "SALES", "ZERO_RATED", 0, "SALES_ZERO", 0, "Z"),
    ("SEX", "صادرات خاضعة بنسبة صفر", "Zero-rated exports", "SALES", "EXPORT", 0, "SALES_EXPORT", 0, "Z"),
    ("SE", "مبيعات معفاة", "Exempt sales", "SALES", "EXEMPT", 0, "SALES_EXEMPT", 0, "E"),
    ("SOOS", "مبيعات خارج نطاق الضريبة", "Out-of-scope sales", "SALES", "OUT_OF_SCOPE", 0, "SALES_OUT_OF_SCOPE", 0, "O"),
    ("P15", "مشتريات محلية خاضعة 15%", "Standard-rated domestic purchases 15%", "PURCHASE", "STANDARD", 15, "PURCHASE_STANDARD", 100, "S"),
    ("P0", "مشتريات خاضعة بنسبة صفر", "Zero-rated purchases", "PURCHASE", "ZERO_RATED", 0, "PURCHASE_ZERO", 0, "Z"),
    ("PE", "مشتريات معفاة", "Exempt purchases", "PURCHASE", "EXEMPT", 0, "PURCHASE_EXEMPT", 0, "E"),
    ("POOS", "مشتريات خارج نطاق الضريبة", "Out-of-scope purchases", "PURCHASE", "OUT_OF_SCOPE", 0, "PURCHASE_OUT_OF_SCOPE", 0, "O"),
    ("PIMP15", "واردات وضريبتها مسددة في الجمارك 15%", "Imports with VAT paid at customs 15%", "PURCHASE", "IMPORTS_CUSTOMS", 15, "PURCHASE_IMPORTS_CUSTOMS", 100, "S"),
    ("PRC15", "مشتريات خاضعة للاحتساب العكسي 15%", "Reverse-charge purchases 15%", "PURCHASE", "REVERSE_CHARGE", 15, "PURCHASE_REVERSE_CHARGE", 100, "S"),
    ("PND15", "مشتريات بضريبة غير قابلة للخصم 15%", "Purchases with non-deductible VAT 15%", "PURCHASE", "NON_DEDUCTIBLE", 15, "PURCHASE_NON_DEDUCTIBLE", 0, "S"),
]


def upgrade():
    op.create_table(
        "tax_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("rate", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("return_box", sa.String(50), nullable=False),
        sa.Column("deductible_percent", sa.Numeric(8, 4), nullable=False, server_default="100"),
        sa.Column("tax_category_code", sa.String(4), nullable=False, server_default="S"),
        sa.Column("exemption_reason_code", sa.String(20)),
        sa.Column("exemption_reason", sa.String(500)),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("system_code", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="uq_tax_code_company_code"),
    )
    for col in ("company_id", "code", "direction", "category", "return_box", "active"):
        op.create_index(f"ix_tax_codes_{col}", "tax_codes", [col])

    op.create_table(
        "vat_return_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vat_return_id", sa.Integer(), sa.ForeignKey("vat_return_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("box_code", sa.String(50), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_base", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("adjustment_tax", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("vat_return_id", "box_code", name="uq_vat_return_line_box"),
    )
    op.create_index("ix_vat_return_lines_vat_return_id", "vat_return_lines", ["vat_return_id"])
    op.create_index("ix_vat_return_lines_box_code", "vat_return_lines", ["box_code"])

    for table in ("sales_invoice_lines", "purchase_invoice_lines", "menu_items", "pos_order_lines"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("tax_code_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_tax_code", "tax_codes", ["tax_code_id"], ["id"])
            batch.create_index(f"ix_{table}_tax_code_id", ["tax_code_id"])

    additions = [
        sa.Column("submitted_by", sa.Integer(), nullable=True), sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True), sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("gl_output_vat", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("gl_input_vat", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("output_reconciliation_difference", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("input_reconciliation_difference", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("classification_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
    ]
    with op.batch_alter_table("vat_return_snapshots") as batch:
        for column in additions:
            batch.add_column(column)
        batch.create_foreign_key("fk_vat_return_submitted_by", "users", ["submitted_by"], ["id"])
        batch.create_foreign_key("fk_vat_return_approved_by", "users", ["approved_by"], ["id"])

    conn = op.get_bind()
    companies = [row[0] for row in conn.execute(sa.text("select id from companies")).fetchall()]
    for company_id in companies:
        for code, ar, en, direction, category, rate, box, deductible, cat_code in DEFAULTS:
            conn.execute(sa.text("""
                insert into tax_codes
                (company_id,code,name_ar,name_en,direction,category,rate,return_box,deductible_percent,
                 tax_category_code,effective_from,system_code,active,created_at)
                values(:company_id,:code,:ar,:en,:direction,:category,:rate,:box,:deductible,:cat_code,
                       '2020-07-01',1,1,CURRENT_TIMESTAMP)
            """), dict(company_id=company_id, code=code, ar=ar, en=en, direction=direction, category=category,
                       rate=rate, box=box, deductible=deductible, cat_code=cat_code))

    # Only legacy 15% lines are safely backfilled as standard-rated. Zero and other rates remain
    # unclassified so users must explicitly distinguish zero-rated, exempt, export and out-of-scope items.
    conn.execute(sa.text("""
        update sales_invoice_lines set tax_code_id=(
          select tc.id from tax_codes tc join sales_invoices si on si.company_id=tc.company_id
          where si.id=sales_invoice_lines.invoice_id and tc.code='S15' and sales_invoice_lines.vat_rate=15
        )
    """))
    conn.execute(sa.text("""
        update purchase_invoice_lines set tax_code_id=(
          select tc.id from tax_codes tc join purchase_invoices pi on pi.company_id=tc.company_id
          where pi.id=purchase_invoice_lines.invoice_id and tc.code='P15' and purchase_invoice_lines.vat_rate=15
        )
    """))
    conn.execute(sa.text("""
        update menu_items set tax_code_id=(
          select tc.id from tax_codes tc where tc.company_id=menu_items.company_id
          and tc.code='S15' and menu_items.vat_rate=15
        )
    """))
    conn.execute(sa.text("""
        update pos_order_lines set tax_code_id=(select tax_code_id from menu_items where menu_items.id=pos_order_lines.menu_item_id)
    """))


def downgrade():
    with op.batch_alter_table("vat_return_snapshots") as batch:
        batch.drop_constraint("fk_vat_return_approved_by", type_="foreignkey")
        batch.drop_constraint("fk_vat_return_submitted_by", type_="foreignkey")
        for col in ("generated_at", "classification_complete", "input_reconciliation_difference", "output_reconciliation_difference", "gl_input_vat", "gl_output_vat", "approved_at", "approved_by", "submitted_at", "submitted_by"):
            batch.drop_column(col)
    for table in ("pos_order_lines", "menu_items", "purchase_invoice_lines", "sales_invoice_lines"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_tax_code_id")
            batch.drop_constraint(f"fk_{table}_tax_code", type_="foreignkey")
            batch.drop_column("tax_code_id")
    op.drop_table("vat_return_lines")
    op.drop_table("tax_codes")
