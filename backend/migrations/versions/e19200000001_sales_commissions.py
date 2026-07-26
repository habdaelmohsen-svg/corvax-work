"""CORVAX RC27.4 H11 - sales commissions.

Creates commission_beneficiaries and commission_accruals, and ensures the two
commission GL accounts exist for every company:
  * 627010 - مصروف عمولات المبيعات / Sales Commission Expense (EXPENSE)
  * 217030 - عمولات مبيعات مستحقة / Sales Commissions Payable (LIABILITY)

Revision chain: follows the H10 head e19100000001.
"""
from alembic import op
import sqlalchemy as sa


revision = "e19200000001"
down_revision = "e19100000001"
branch_labels = None
depends_on = None


COMMISSION_ACCOUNTS = [
    # code, name_ar, name_en, account_type, statement_group, parent_code
    ("627010", "مصروف عمولات المبيعات", "Sales Commission Expense", "EXPENSE", "OPERATING_EXPENSES", "600000"),
    ("217030", "عمولات مبيعات مستحقة", "Sales Commissions Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000"),
]


def upgrade() -> None:
    op.create_table(
        "commission_beneficiaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("beneficiary_type", sa.String(20), nullable=False, server_default="SALES_REP"),
        sa.Column("default_basis", sa.String(20), nullable=False, server_default="PERCENTAGE"),
        sa.Column("default_rate", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("phone", sa.String(30)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "code", name="uq_commission_beneficiary_company_code"),
    )
    op.create_table(
        "commission_accruals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("beneficiary_id", sa.Integer(), sa.ForeignKey("commission_beneficiaries.id"), nullable=False, index=True),
        sa.Column("sales_invoice_id", sa.Integer(), sa.ForeignKey("sales_invoices.id"), nullable=False, index=True),
        sa.Column("basis", sa.String(20), nullable=False, server_default="PERCENTAGE"),
        sa.Column("rate", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("invoice_base_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("collected_ratio", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("payable_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING", index=True),
        sa.Column("accrual_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("paid_journal_id", sa.Integer(), sa.ForeignKey("journal_entries.id")),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Ensure the two commission GL accounts exist for every company.
    conn = op.get_bind()
    companies = [row[0] for row in conn.execute(sa.text("SELECT id FROM companies"))]
    for company_id in companies:
        for code, name_ar, name_en, acc_type, group, parent_code in COMMISSION_ACCOUNTS:
            exists = conn.execute(
                sa.text("SELECT 1 FROM accounts WHERE company_id = :cid AND code = :code"),
                {"cid": company_id, "code": code},
            ).first()
            if exists:
                continue
            parent = conn.execute(
                sa.text("SELECT id FROM accounts WHERE company_id = :cid AND code = :pcode"),
                {"cid": company_id, "pcode": parent_code},
            ).first()
            parent_id = parent[0] if parent else None
            conn.execute(
                sa.text(
                    "INSERT INTO accounts (company_id, code, name_ar, name_en, account_type, statement_group, parent_id, level, is_postable, is_cash, active) "
                    "VALUES (:cid, :code, :nar, :nen, :atype, :grp, :pid, 3, true, false, true)"
                ),
                {"cid": company_id, "code": code, "nar": name_ar, "nen": name_en, "atype": acc_type, "grp": group, "pid": parent_id},
            )


def downgrade() -> None:
    op.drop_table("commission_accruals")
    op.drop_table("commission_beneficiaries")
    conn = op.get_bind()
    for code, *_ in COMMISSION_ACCOUNTS:
        conn.execute(sa.text("DELETE FROM accounts WHERE code = :code"), {"code": code})
