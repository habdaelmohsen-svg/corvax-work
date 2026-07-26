"""audit remediation rc11

Revision ID: e17200000001
Revises: e17100000001
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

from app.core.crypto import decrypt_text, encrypt_text

revision = "e17200000001"
down_revision = "e17100000001"
branch_labels = None
depends_on = None


def _alter_sensitive_to_text() -> None:
    specs = {
        "companies": [("vat_number", sa.String(30)), ("commercial_registration", sa.String(30))],
        "parties": [("vat_number", sa.String(30))],
        "bank_accounts": [("iban", sa.String(50))],
        "employees": [
            ("iban", sa.String(50)),
            ("basic_salary", sa.Numeric(18, 2)),
            ("housing_allowance", sa.Numeric(18, 2)),
            ("other_allowance", sa.Numeric(18, 2)),
        ],
        "payroll_lines": [
            ("basic_salary", sa.Numeric(18, 2)),
            ("housing_allowance", sa.Numeric(18, 2)),
            ("other_allowance", sa.Numeric(18, 2)),
            ("gross_salary", sa.Numeric(18, 2)),
            ("net_salary", sa.Numeric(18, 2)),
        ],
    }
    for table, columns in specs.items():
        with op.batch_alter_table(table, recreate="auto") as batch:
            for name, old_type in columns:
                batch.alter_column(name, existing_type=old_type, type_=sa.Text(), existing_nullable=True if name in {"iban", "vat_number", "commercial_registration"} else False)


def _encrypt_existing_values() -> None:
    bind = op.get_bind()
    table_columns = {
        "companies": ["vat_number", "commercial_registration"],
        "parties": ["vat_number"],
        "bank_accounts": ["iban"],
        "employees": ["iban", "basic_salary", "housing_allowance", "other_allowance"],
        "payroll_lines": ["basic_salary", "housing_allowance", "other_allowance", "gross_salary", "net_salary"],
    }
    for table, columns in table_columns.items():
        rows = bind.execute(sa.text(f"SELECT id, {', '.join(columns)} FROM {table}")).mappings().all()
        for row in rows:
            updates = {}
            for column in columns:
                value = row[column]
                if value is not None and str(value) != "" and not str(value).startswith("enc:v1:"):
                    updates[column] = encrypt_text(format(value, "f") if isinstance(value, Decimal) else str(value))
            if updates:
                setters = ", ".join(f"{name}=:{name}" for name in updates)
                bind.execute(sa.text(f"UPDATE {table} SET {setters} WHERE id=:id"), {**updates, "id": row["id"]})


def _decrypt_existing_values() -> None:
    bind = op.get_bind()
    table_columns = {
        "companies": ["vat_number", "commercial_registration"],
        "parties": ["vat_number"],
        "bank_accounts": ["iban"],
        "employees": ["iban", "basic_salary", "housing_allowance", "other_allowance"],
        "payroll_lines": ["basic_salary", "housing_allowance", "other_allowance", "gross_salary", "net_salary"],
    }
    for table, columns in table_columns.items():
        rows = bind.execute(sa.text(f"SELECT id, {', '.join(columns)} FROM {table}")).mappings().all()
        for row in rows:
            updates = {}
            for column in columns:
                value = row[column]
                if value is not None and str(value).startswith("enc:v1:"):
                    updates[column] = decrypt_text(str(value))
            if updates:
                setters = ", ".join(f"{name}=:{name}" for name in updates)
                bind.execute(sa.text(f"UPDATE {table} SET {setters} WHERE id=:id"), {**updates, "id": row["id"]})


def upgrade():
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("job_type", sa.String(50), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="QUEUED", index=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_reference", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("locked_by", sa.String(100)),
        sa.Column("locked_at", sa.DateTime()),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "job_type", "idempotency_key", name="uq_background_job_idempotency"),
    )
    op.create_table(
        "journal_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False, index=True),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "fiscal_year", name="uq_journal_sequence_company_year"),
    )
    bind = op.get_bind()
    maxima: dict[tuple[int, int], int] = defaultdict(int)
    for company_id, number, entry_date in bind.execute(sa.text("SELECT company_id, number, entry_date FROM journal_entries")).fetchall():
        year = entry_date.year if hasattr(entry_date, "year") else int(str(entry_date)[:4])
        try:
            suffix = int(str(number).rsplit("-", 1)[-1])
        except (TypeError, ValueError):
            suffix = 0
        maxima[(int(company_id), year)] = max(maxima[(int(company_id), year)], suffix)
    for (company_id, year), last_number in maxima.items():
        bind.execute(sa.text(
            "INSERT INTO journal_sequences(company_id,fiscal_year,last_number,updated_at) VALUES (:c,:y,:n,:u)"
        ), {"c": company_id, "y": year, "n": last_number, "u": datetime.now(timezone.utc).replace(tzinfo=None)})

    with op.batch_alter_table("user_sessions") as batch:
        batch.add_column(sa.Column("refresh_token_hash", sa.String(64)))
        batch.add_column(sa.Column("refresh_expires_at", sa.DateTime()))
        batch.add_column(sa.Column("rotated_at", sa.DateTime()))
        batch.add_column(sa.Column("revoke_reason", sa.String(100)))
        batch.add_column(sa.Column("parent_session_id", sa.String(64)))
        batch.create_foreign_key("fk_user_session_parent", "user_sessions", ["parent_session_id"], ["id"])
        batch.create_unique_constraint("uq_user_session_refresh_hash", ["refresh_token_hash"])
        batch.create_index("ix_user_sessions_refresh_expires_at", ["refresh_expires_at"])

    op.create_table(
        "supplier_item_planning",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lot_sizing_policy", sa.String(20), nullable=False, server_default="LFL"),
        sa.Column("minimum_order_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("order_multiple", sa.Numeric(18, 4), nullable=False, server_default="1"),
        sa.Column("fixed_order_quantity", sa.Numeric(18, 4)),
        sa.Column("eoq_annual_demand", sa.Numeric(18, 4)),
        sa.Column("eoq_order_cost", sa.Numeric(18, 4)),
        sa.Column("eoq_holding_cost", sa.Numeric(18, 4)),
        sa.Column("preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "supplier_id", "item_id", name="uq_supplier_item_planning"),
    )
    op.create_table(
        "work_center_calendar_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("work_center_id", sa.Integer(), sa.ForeignKey("work_centers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("work_date", sa.Date(), nullable=False, index=True),
        sa.Column("shift_code", sa.String(30), nullable=False, server_default="DAY"),
        sa.Column("available_minutes", sa.Numeric(18, 2), nullable=False, server_default="480"),
        sa.Column("reserved_minutes", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("work_center_id", "work_date", name="uq_work_center_calendar_day"),
    )

    with op.batch_alter_table("purchase_orders") as batch:
        batch.add_column(sa.Column("expected_receipt_date", sa.Date()))
        batch.create_index("ix_purchase_orders_expected_receipt_date", ["expected_receipt_date"])

    with op.batch_alter_table("mrp_plan_runs") as batch:
        batch.add_column(sa.Column("execution_mode", sa.String(20), nullable=False, server_default="BACKGROUND"))
        batch.add_column(sa.Column("background_job_id", sa.String(64)))
        batch.add_column(sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="100"))
        batch.create_foreign_key("fk_mrp_plan_background_job", "background_jobs", ["background_job_id"], ["id"])
    with op.batch_alter_table("mrp_requirement_lines") as batch:
        batch.add_column(sa.Column("production_receipts", sa.Numeric(18, 4), nullable=False, server_default="0"))
        batch.add_column(sa.Column("purchase_receipts", sa.Numeric(18, 4), nullable=False, server_default="0"))
        batch.add_column(sa.Column("planned_receipt_date", sa.Date()))
        batch.add_column(sa.Column("planned_release_date", sa.Date()))
        batch.add_column(sa.Column("supplier_id", sa.Integer()))
        batch.add_column(sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("lot_sizing_policy", sa.String(20), nullable=False, server_default="LFL"))
        batch.add_column(sa.Column("capacity_status", sa.String(25), nullable=False, server_default="NOT_APPLICABLE"))
        batch.create_foreign_key("fk_mrp_requirement_supplier", "parties", ["supplier_id"], ["id"])
    op.create_table(
        "mrp_capacity_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("mrp_plan_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("requirement_line_id", sa.Integer(), sa.ForeignKey("mrp_requirement_lines.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("work_center_id", sa.Integer(), sa.ForeignKey("work_centers.id"), nullable=False, index=True),
        sa.Column("operation_sequence", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False, index=True),
        sa.Column("allocated_minutes", sa.Numeric(18, 2), nullable=False),
        sa.Column("capacity_status", sa.String(20), nullable=False, server_default="ALLOCATED"),
    )

    _alter_sensitive_to_text()
    _encrypt_existing_values()


def downgrade():
    _decrypt_existing_values()
    # Restore legacy SQL types after plaintext backfill.
    with op.batch_alter_table("payroll_lines", recreate="auto") as batch:
        for name in ("basic_salary", "housing_allowance", "other_allowance", "gross_salary", "net_salary"):
            batch.alter_column(name, existing_type=sa.Text(), type_=sa.Numeric(18, 2), existing_nullable=False)
    with op.batch_alter_table("employees", recreate="auto") as batch:
        batch.alter_column("iban", existing_type=sa.Text(), type_=sa.String(50), existing_nullable=True)
        for name in ("basic_salary", "housing_allowance", "other_allowance"):
            batch.alter_column(name, existing_type=sa.Text(), type_=sa.Numeric(18, 2), existing_nullable=False)
    with op.batch_alter_table("bank_accounts", recreate="auto") as batch:
        batch.alter_column("iban", existing_type=sa.Text(), type_=sa.String(50), existing_nullable=True)
    with op.batch_alter_table("parties", recreate="auto") as batch:
        batch.alter_column("vat_number", existing_type=sa.Text(), type_=sa.String(30), existing_nullable=True)
    with op.batch_alter_table("companies", recreate="auto") as batch:
        batch.alter_column("vat_number", existing_type=sa.Text(), type_=sa.String(30), existing_nullable=True)
        batch.alter_column("commercial_registration", existing_type=sa.Text(), type_=sa.String(30), existing_nullable=True)

    with op.batch_alter_table("purchase_orders") as batch:
        batch.drop_index("ix_purchase_orders_expected_receipt_date")
        batch.drop_column("expected_receipt_date")
    op.drop_table("mrp_capacity_allocations")
    with op.batch_alter_table("mrp_requirement_lines") as batch:
        batch.drop_constraint("fk_mrp_requirement_supplier", type_="foreignkey")
        for name in ("capacity_status", "lot_sizing_policy", "lead_time_days", "supplier_id", "planned_release_date", "planned_receipt_date", "purchase_receipts", "production_receipts"):
            batch.drop_column(name)
    with op.batch_alter_table("mrp_plan_runs") as batch:
        batch.drop_constraint("fk_mrp_plan_background_job", type_="foreignkey")
        batch.drop_column("progress_percent")
        batch.drop_column("background_job_id")
        batch.drop_column("execution_mode")
    op.drop_table("work_center_calendar_days")
    op.drop_table("supplier_item_planning")
    with op.batch_alter_table("user_sessions") as batch:
        batch.drop_index("ix_user_sessions_refresh_expires_at")
        batch.drop_constraint("uq_user_session_refresh_hash", type_="unique")
        batch.drop_constraint("fk_user_session_parent", type_="foreignkey")
        batch.drop_column("parent_session_id")
        batch.drop_column("revoke_reason")
        batch.drop_column("rotated_at")
        batch.drop_column("refresh_expires_at")
        batch.drop_column("refresh_token_hash")
    op.drop_table("journal_sequences")
    op.drop_table("background_jobs")
