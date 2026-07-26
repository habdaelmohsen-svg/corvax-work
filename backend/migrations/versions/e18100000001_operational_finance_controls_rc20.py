"""Import VAT, landed cost, cost rollup, perpetual inventory and budget analytics RC20

Revision ID: e18100000001
Revises: e17900000001
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "e18100000001"
down_revision = "e17900000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_declarations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("declaration_date", sa.Date(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id")),
        sa.Column("purchase_invoice_id", sa.Integer(), sa.ForeignKey("purchase_invoices.id")),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id")),
        sa.Column("origin_country", sa.String(3), nullable=False),
        sa.Column("customs_port", sa.String(120)),
        sa.Column("customs_reference", sa.String(120)),
        sa.Column("treatment", sa.String(30), nullable=False),
        sa.Column("customs_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("freight_insurance_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("customs_duty", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("excise_tax", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("other_customs_charges", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_base", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_rate", sa.Numeric(8, 4), nullable=False, server_default="15"),
        sa.Column("vat_due", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_collected_on_declaration", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_accounted_in_return", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("release_date", sa.Date()),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("posted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("posted_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_import_declaration_company_number"),
    )
    for col in ("company_id", "number", "declaration_date", "supplier_id", "purchase_invoice_id", "goods_receipt_id", "origin_country", "treatment", "status"):
        op.create_index(f"ix_import_declarations_{col}", "import_declarations", [col])

    op.create_table(
        "import_declaration_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("declaration_id", sa.Integer(), sa.ForeignKey("import_declarations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("hs_code", sa.String(30)),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("uom", sa.String(20), nullable=False, server_default="EA"),
        sa.Column("customs_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("customs_duty", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("excise_tax", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("other_charges", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_base", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_due", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_import_declaration_lines_declaration_id", "import_declaration_lines", ["declaration_id"])
    op.create_index("ix_import_declaration_lines_item_id", "import_declaration_lines", ["item_id"])

    op.create_table(
        "export_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sales_invoice_id", sa.Integer(), sa.ForeignKey("sales_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("export_declaration_number", sa.String(100), nullable=False),
        sa.Column("export_date", sa.Date(), nullable=False),
        sa.Column("destination_country", sa.String(3), nullable=False),
        sa.Column("exit_port", sa.String(120)),
        sa.Column("transport_document", sa.String(120), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "sales_invoice_id", name="uq_export_evidence_invoice"),
    )
    for col in ("company_id", "sales_invoice_id", "export_date", "status"):
        op.create_index(f"ix_export_evidence_{col}", "export_evidence", [col])

    op.create_table(
        "landed_cost_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id"), nullable=False),
        sa.Column("import_declaration_id", sa.Integer(), sa.ForeignKey("import_declarations.id")),
        sa.Column("allocation_method", sa.String(20), nullable=False, server_default="VALUE"),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("total_capitalizable_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_noncapitalizable_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("clearing_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("posted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("posted_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_landed_cost_company_number"),
    )
    for col in ("company_id", "number", "document_date", "goods_receipt_id", "import_declaration_id", "status"):
        op.create_index(f"ix_landed_cost_documents_{col}", "landed_cost_documents", [col])

    op.create_table(
        "landed_cost_charges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("landed_cost_id", sa.Integer(), sa.ForeignKey("landed_cost_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False),
        sa.Column("supplier_invoice_number", sa.String(100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("charge_type", sa.String(30), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("capitalizable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id"), nullable=False),
        sa.Column("purchase_invoice_id", sa.Integer(), sa.ForeignKey("purchase_invoices.id")),
    )
    op.create_index("ix_landed_cost_charges_landed_cost_id", "landed_cost_charges", ["landed_cost_id"])
    op.create_index("ix_landed_cost_charges_charge_type", "landed_cost_charges", ["charge_type"])

    op.create_table(
        "landed_cost_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("landed_cost_id", sa.Integer(), sa.ForeignKey("landed_cost_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goods_receipt_line_id", sa.Integer(), sa.ForeignKey("goods_receipt_lines.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("allocation_basis", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("allocated_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("unit_cost_increment", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("stock_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id")),
    )
    for col in ("landed_cost_id", "goods_receipt_line_id", "item_id"):
        op.create_index(f"ix_landed_cost_allocations_{col}", "landed_cost_allocations", [col])

    op.create_table(
        "cost_rollup_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("bom_id", sa.Integer(), sa.ForeignKey("bills_of_material.id"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("cost_basis", sa.String(20), nullable=False, server_default="STANDARD"),
        sa.Column("status", sa.String(25), nullable=False, server_default="READY_FOR_REVIEW"),
        sa.Column("direct_material_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("packaging_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("direct_labor_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("direct_expense_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("variable_overhead_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("fixed_overhead_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("current_standard_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("standard_cost_variance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("analysis_hash", sa.String(64), nullable=False),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_cost_rollup_company_number"),
    )
    for col in ("company_id", "number", "item_id", "as_of_date", "status"):
        op.create_index(f"ix_cost_rollup_snapshots_{col}", "cost_rollup_snapshots", [col])

    op.create_table(
        "cost_rollup_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("cost_rollup_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("parent_item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("line_type", sa.String(30), nullable=False),
        sa.Column("description_ar", sa.String(500), nullable=False),
        sa.Column("description_en", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("source_reference", sa.String(120)),
    )
    op.create_index("ix_cost_rollup_lines_snapshot_id", "cost_rollup_lines", ["snapshot_id"])
    op.create_index("ix_cost_rollup_lines_line_type", "cost_rollup_lines", ["line_type"])

    op.create_table(
        "inventory_counts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("count_date", sa.Date(), nullable=False),
        sa.Column("count_type", sa.String(20), nullable=False, server_default="FULL"),
        sa.Column("status", sa.String(25), nullable=False, server_default="FROZEN"),
        sa.Column("loss_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("gain_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_inventory_count_company_number"),
    )
    for col in ("company_id", "number", "warehouse_id", "count_date", "status"):
        op.create_index(f"ix_inventory_counts_{col}", "inventory_counts", [col])

    op.create_table(
        "inventory_count_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inventory_count_id", sa.Integer(), sa.ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("lot_number", sa.String(80), nullable=False, server_default=""),
        sa.Column("book_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("book_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("counted_quantity", sa.Numeric(18, 4)),
        sa.Column("variance_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("variance_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(500)),
        sa.UniqueConstraint("inventory_count_id", "item_id", "lot_number", name="uq_inventory_count_item_lot"),
    )
    op.create_index("ix_inventory_count_lines_inventory_count_id", "inventory_count_lines", ["inventory_count_id"])
    op.create_index("ix_inventory_count_lines_item_id", "inventory_count_lines", ["item_id"])

    op.create_table(
        "inventory_write_downs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("write_down_date", sa.Date(), nullable=False),
        sa.Column("reason_type", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("carrying_unit_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("nrv_unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("write_down_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="PENDING_APPROVAL"),
        sa.Column("expense_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("provision_account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_inventory_write_down_company_number"),
    )
    for col in ("company_id", "number", "warehouse_id", "item_id", "write_down_date", "reason_type", "status"):
        op.create_index(f"ix_inventory_write_downs_{col}", "inventory_write_downs", [col])

    op.create_table(
        "item_uom_conversions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_uom", sa.String(20), nullable=False),
        sa.Column("to_uom", sa.String(20), nullable=False),
        sa.Column("factor", sa.Numeric(18, 8), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("item_id", "from_uom", "to_uom", name="uq_item_uom_conversion"),
    )
    op.create_index("ix_item_uom_conversions_company_id", "item_uom_conversions", ["company_id"])
    op.create_index("ix_item_uom_conversions_item_id", "item_uom_conversions", ["item_id"])

    with op.batch_alter_table("work_centers") as batch:
        batch.add_column(sa.Column("direct_expense_rate", sa.Numeric(18, 4), nullable=False, server_default="0"))
        batch.add_column(sa.Column("variable_overhead_rate", sa.Numeric(18, 4), nullable=False, server_default="0"))
        batch.add_column(sa.Column("fixed_overhead_rate", sa.Numeric(18, 4), nullable=False, server_default="0"))

    conn = op.get_bind()
    conn.execute(sa.text("update work_centers set variable_overhead_rate=hourly_overhead_rate where variable_overhead_rate=0"))

    # Additional tax treatments. A foreign supplier invoice can carry no Saudi VAT while the
    # import declaration separately determines whether VAT is collected, accounted through the return,
    # suspended, or exempt.
    tax_defaults = [
        ("PFOR0", "فاتورة مورد أجنبي بدون ضريبة سعودية", "Foreign supplier invoice with no Saudi VAT", "PURCHASE", "FOREIGN_SUPPLIER", 0, "PURCHASE_FOREIGN_NO_SAUDI_VAT", 0, "O"),
        ("PIMPR15", "واردات ضريبتها محتسبة عبر الإقرار", "Imports VAT accounted through the VAT return", "PURCHASE", "IMPORTS_RETURN", 15, "PURCHASE_IMPORTS_THROUGH_RETURN", 100, "S"),
        ("PIMPS0", "واردات تحت تعليق جمركي", "Imports under customs suspension", "PURCHASE", "IMPORTS_SUSPENDED", 0, "PURCHASE_IMPORTS_SUSPENDED", 0, "O"),
        ("PIMPE", "واردات معفاة من ضريبة الاستيراد", "VAT-exempt imports", "PURCHASE", "IMPORTS_EXEMPT", 0, "PURCHASE_IMPORTS_EXEMPT", 0, "E"),
    ]
    companies = [row[0] for row in conn.execute(sa.text("select id from companies")).fetchall()]
    for company_id in companies:
        for code, ar, en, direction, category, rate, box, deductible, cat_code in tax_defaults:
            conn.execute(sa.text("""
                insert into tax_codes
                (company_id,code,name_ar,name_en,direction,category,rate,return_box,deductible_percent,
                 tax_category_code,effective_from,system_code,active,created_at)
                select :company_id,:code,:ar,:en,:direction,:category,:rate,:box,:deductible,:cat_code,
                       '2020-07-01',1,1,CURRENT_TIMESTAMP
                where not exists(select 1 from tax_codes where company_id=:company_id and code=:code)
            """), dict(company_id=company_id, code=code, ar=ar, en=en, direction=direction, category=category,
                       rate=rate, box=box, deductible=deductible, cat_code=cat_code))

    # Company-scoped accounts needed for import clearing, inventory provisions and physical-count adjustments.
    accounts = [
        ("119010", "تسوية التكاليف الواصلة", "Landed Cost Clearing", "ASSET", "CURRENT_ASSETS", "110000"),
        ("113020", "مخصص انخفاض المخزون", "Inventory Write-down Provision", "ASSET", "INVENTORY_PROVISION", "110000"),
        ("212020", "تسوية ضريبة الاستيراد", "Import VAT Clearing", "LIABILITY", "VAT", "210000"),
        ("424010", "أرباح فروق الجرد", "Inventory Count Gains", "REVENUE", "OTHER_INCOME", "400000"),
        ("624090", "خسائر فروق الجرد", "Inventory Count Losses", "EXPENSE", "COST_OF_REVENUE", "600000"),
        ("624100", "خسائر انخفاض وتقادم المخزون", "Inventory Obsolescence and NRV Losses", "EXPENSE", "COST_OF_REVENUE", "600000"),
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
    with op.batch_alter_table("work_centers") as batch:
        batch.drop_column("fixed_overhead_rate")
        batch.drop_column("variable_overhead_rate")
        batch.drop_column("direct_expense_rate")
    for table in (
        "item_uom_conversions", "inventory_write_downs", "inventory_count_lines", "inventory_counts",
        "cost_rollup_lines", "cost_rollup_snapshots", "landed_cost_allocations", "landed_cost_charges",
        "landed_cost_documents", "export_evidence", "import_declaration_lines", "import_declarations",
    ):
        op.drop_table(table)
