"""CORVAX RC25 fixed asset lifecycle engine.

Revision ID: e18600000001
Revises: e18500000001
"""
from alembic import op
import sqlalchemy as sa

revision = "e18600000001"
down_revision = "e18500000001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("fixed_assets") as batch:
        batch.add_column(sa.Column("accumulated_impairment", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("custodian_user_id", sa.Integer()))
        batch.add_column(sa.Column("held_for_sale_date", sa.Date()))
        batch.add_column(sa.Column("disposal_date", sa.Date()))
        batch.add_column(sa.Column("disposal_reference", sa.String(120)))
        batch.create_foreign_key("fk_fixed_assets_custodian_user_id_users", "users", ["custodian_user_id"], ["id"])

    op.create_table(
        "asset_lifecycle_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(60), nullable=False),
        sa.Column("transaction_type", sa.String(35), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="DRAFT"),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("reference", sa.String(150)),
        sa.Column("from_branch_id", sa.Integer(), sa.ForeignKey("branches.id")),
        sa.Column("to_branch_id", sa.Integer(), sa.ForeignKey("branches.id")),
        sa.Column("from_cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id")),
        sa.Column("to_cost_center_id", sa.Integer(), sa.ForeignKey("cost_centers.id")),
        sa.Column("from_custodian_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("to_custodian_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("disposal_percent", sa.Numeric(8, 4), nullable=False, server_default="100"),
        sa.Column("proceeds_net", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vat_rate", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id")),
        sa.Column("vat_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("proceeds_gross", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("disposed_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("disposed_accumulated_depreciation", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("disposed_accumulated_impairment", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("disposed_net_book_value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("gain_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("loss_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("recoverable_amount", sa.Numeric(18, 2)),
        sa.Column("fair_value_less_cost_to_sell", sa.Numeric(18, 2)),
        sa.Column("impairment_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("reversal_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id")),
        sa.Column("journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_asset_lifecycle_company_number"),
    )
    for col in ("company_id", "asset_id", "number", "transaction_type", "transaction_date", "status"):
        op.create_index(f"ix_asset_lifecycle_transactions_{col}", "asset_lifecycle_transactions", [col])

    conn = op.get_bind()
    accounts = [
        ("119020", "أصول محتفظ بها للبيع", "Assets Held for Sale", "ASSET", "CURRENT_ASSETS", "110000"),
        ("425010", "أرباح بيع واستبعاد الأصول", "Gain on Disposal of PPE", "REVENUE", "OTHER_INCOME", "400000"),
        ("426010", "عكس خسائر انخفاض الأصول", "Reversal of Asset Impairment", "REVENUE", "OTHER_INCOME", "400000"),
        ("626010", "خسائر بيع واستبعاد الأصول", "Loss on Disposal of PPE", "EXPENSE", "OPERATING_EXPENSES", "600000"),
    ]
    companies = [row[0] for row in conn.execute(sa.text("select id from companies"))]
    for company_id in companies:
        for code, ar, en, typ, group, parent_code in accounts:
            if conn.execute(sa.text("select 1 from accounts where company_id=:c and code=:code"), {"c": company_id, "code": code}).scalar():
                continue
            parent = conn.execute(sa.text("select id from accounts where company_id=:c and code=:p"), {"c": company_id, "p": parent_code}).scalar()
            conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
                values(:c,:code,:ar,:en,:typ,:grp,:parent,3,1,0,1)"""),
                {"c": company_id, "code": code, "ar": ar, "en": en, "typ": typ, "grp": group, "parent": parent})


def downgrade():
    conn = op.get_bind()
    for code in ("119020", "425010", "426010", "626010"):
        conn.execute(sa.text("delete from accounts where code=:code"), {"code": code})
    for col in ("company_id", "asset_id", "number", "transaction_type", "transaction_date", "status"):
        op.drop_index(f"ix_asset_lifecycle_transactions_{col}", table_name="asset_lifecycle_transactions")
    op.drop_table("asset_lifecycle_transactions")
    with op.batch_alter_table("fixed_assets") as batch:
        batch.drop_constraint("fk_fixed_assets_custodian_user_id_users", type_="foreignkey")
        batch.drop_column("disposal_reference")
        batch.drop_column("disposal_date")
        batch.drop_column("held_for_sale_date")
        batch.drop_column("custodian_user_id")
        batch.drop_column("accumulated_impairment")
