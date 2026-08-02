"""R7 finance controls: bank SoD and lease cash/accrual timing.

Revision ID: e20200000001
Revises: e20100000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e20200000001"
down_revision = "e20100000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bank_statements") as batch:
        batch.add_column(sa.Column("matched_by", sa.Integer()))
        batch.add_column(sa.Column("matched_at", sa.DateTime()))
        batch.add_column(sa.Column("reconciled_by", sa.Integer()))
        batch.add_column(sa.Column("reconciled_at", sa.DateTime()))
        batch.create_foreign_key(
            "fk_bank_statements_matched_by_users",
            "users", ["matched_by"], ["id"],
        )
        batch.create_foreign_key(
            "fk_bank_statements_reconciled_by_users",
            "users", ["reconciled_by"], ["id"],
        )

    op.execute("""
        INSERT INTO permissions (code, name_ar, name_en)
        SELECT 'bank.statement.prepare', 'إعداد ومطابقة كشوف البنك', 'Prepare and match bank statements'
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'bank.statement.prepare')
    """)

    with op.batch_alter_table("lease_schedules") as batch:
        batch.add_column(sa.Column("period_end_date", sa.Date()))
        batch.add_column(sa.Column("cash_payment_date", sa.Date()))
        batch.add_column(sa.Column("accrual_status", sa.String(20), nullable=False, server_default="PENDING"))
        batch.add_column(sa.Column("cash_status", sa.String(20), nullable=False, server_default="NOT_APPLICABLE"))
        batch.add_column(sa.Column("accrual_journal_id", sa.Integer()))
        batch.add_column(sa.Column("cash_journal_id", sa.Integer()))
        batch.create_foreign_key(
            "fk_lease_schedules_accrual_journal",
            "journal_entries", ["accrual_journal_id"], ["id"],
        )
        batch.create_foreign_key(
            "fk_lease_schedules_cash_journal",
            "journal_entries", ["cash_journal_id"], ["id"],
        )
    op.execute("""
        UPDATE lease_schedules
        SET period_end_date = payment_date,
            cash_payment_date = CASE WHEN payment <> 0 THEN payment_date ELSE NULL END,
            accrual_status = status,
            cash_status = CASE
                WHEN payment = 0 THEN 'NOT_APPLICABLE'
                WHEN status = 'POSTED' THEN 'POSTED'
                ELSE 'PENDING'
            END,
            accrual_journal_id = journal_id,
            cash_journal_id = CASE WHEN payment <> 0 AND status = 'POSTED' THEN journal_id ELSE NULL END
    """)
    with op.batch_alter_table("lease_schedules") as batch:
        batch.alter_column("period_end_date", existing_type=sa.Date(), nullable=False)
        batch.create_index("ix_lease_schedules_period_end_date", ["period_end_date"])
        batch.create_index("ix_lease_schedules_cash_payment_date", ["cash_payment_date"])
        batch.create_index("ix_lease_schedules_accrual_status", ["accrual_status"])
        batch.create_index("ix_lease_schedules_cash_status", ["cash_status"])

    with op.batch_alter_table("goods_receipts") as batch:
        batch.add_column(sa.Column("purchase_invoice_id", sa.Integer()))
        batch.create_foreign_key(
            "fk_goods_receipts_purchase_invoice",
            "purchase_invoices", ["purchase_invoice_id"], ["id"],
        )
        batch.create_unique_constraint("uq_grn_purchase_invoice", ["purchase_invoice_id"])
        batch.create_index("ix_goods_receipts_purchase_invoice_id", ["purchase_invoice_id"])
    with op.batch_alter_table("purchase_invoice_lines") as batch:
        batch.add_column(sa.Column("item_id", sa.Integer()))
        batch.add_column(sa.Column("warehouse_id", sa.Integer()))
        batch.add_column(sa.Column("goods_receipt_line_id", sa.Integer()))
        batch.create_foreign_key("fk_purchase_invoice_lines_item", "items", ["item_id"], ["id"])
        batch.create_foreign_key("fk_purchase_invoice_lines_warehouse", "warehouses", ["warehouse_id"], ["id"])
        batch.create_foreign_key(
            "fk_purchase_invoice_lines_grn_line",
            "goods_receipt_lines", ["goods_receipt_line_id"], ["id"],
        )
        batch.create_unique_constraint("uq_purchase_invoice_lines_grn_line", ["goods_receipt_line_id"])
        batch.create_index("ix_purchase_invoice_lines_item_id", ["item_id"])
        batch.create_index("ix_purchase_invoice_lines_warehouse_id", ["warehouse_id"])
        batch.create_index("ix_purchase_invoice_lines_goods_receipt_line_id", ["goods_receipt_line_id"])
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'ACCOUNTANT' AND p.code = 'bank.statement.prepare'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE (
            (r.code IN ('ACCOUNTANT', 'SALES_MANAGER', 'CFO') AND p.code = 'masterdata.manage')
            OR (r.code = 'QUALITY_MANAGER' AND p.code = 'inventory.read')
        )
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
        WHERE EXISTS (
            SELECT 1 FROM roles r CROSS JOIN permissions p
            WHERE r.id = role_permissions.role_id
              AND p.id = role_permissions.permission_id
              AND (
                  (r.code IN ('ACCOUNTANT', 'SALES_MANAGER', 'CFO') AND p.code = 'masterdata.manage')
                  OR (r.code = 'QUALITY_MANAGER' AND p.code = 'inventory.read')
              )
        )
    """)
    with op.batch_alter_table("purchase_invoice_lines") as batch:
        batch.drop_index("ix_purchase_invoice_lines_goods_receipt_line_id")
        batch.drop_index("ix_purchase_invoice_lines_warehouse_id")
        batch.drop_index("ix_purchase_invoice_lines_item_id")
        batch.drop_constraint("uq_purchase_invoice_lines_grn_line", type_="unique")
        batch.drop_constraint("fk_purchase_invoice_lines_grn_line", type_="foreignkey")
        batch.drop_constraint("fk_purchase_invoice_lines_warehouse", type_="foreignkey")
        batch.drop_constraint("fk_purchase_invoice_lines_item", type_="foreignkey")
        batch.drop_column("goods_receipt_line_id")
        batch.drop_column("warehouse_id")
        batch.drop_column("item_id")
    with op.batch_alter_table("goods_receipts") as batch:
        batch.drop_index("ix_goods_receipts_purchase_invoice_id")
        batch.drop_constraint("uq_grn_purchase_invoice", type_="unique")
        batch.drop_constraint("fk_goods_receipts_purchase_invoice", type_="foreignkey")
        batch.drop_column("purchase_invoice_id")
    with op.batch_alter_table("lease_schedules") as batch:
        batch.drop_index("ix_lease_schedules_cash_status")
        batch.drop_index("ix_lease_schedules_accrual_status")
        batch.drop_index("ix_lease_schedules_cash_payment_date")
        batch.drop_index("ix_lease_schedules_period_end_date")
        batch.drop_constraint("fk_lease_schedules_cash_journal", type_="foreignkey")
        batch.drop_constraint("fk_lease_schedules_accrual_journal", type_="foreignkey")
        batch.drop_column("cash_journal_id")
        batch.drop_column("accrual_journal_id")
        batch.drop_column("cash_status")
        batch.drop_column("accrual_status")
        batch.drop_column("cash_payment_date")
        batch.drop_column("period_end_date")
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'bank.statement.prepare')
    """)
    op.execute("DELETE FROM permissions WHERE code = 'bank.statement.prepare'")
    with op.batch_alter_table("bank_statements") as batch:
        batch.drop_constraint("fk_bank_statements_reconciled_by_users", type_="foreignkey")
        batch.drop_constraint("fk_bank_statements_matched_by_users", type_="foreignkey")
        batch.drop_column("reconciled_at")
        batch.drop_column("reconciled_by")
        batch.drop_column("matched_at")
        batch.drop_column("matched_by")
