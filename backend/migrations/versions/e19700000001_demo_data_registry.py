"""Add an explicit registry for safely removable demonstration records.

Revision ID: e19700000001
Revises: e19600000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e19700000001"
down_revision = "e19600000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_data_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_id", sa.String(100), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="SYSTEM_SEED"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "table_name",
            "record_id",
            name="uq_demo_data_record_identity",
        ),
    )
    op.create_index(
        "ix_demo_data_records_company_id",
        "demo_data_records",
        ["company_id"],
    )
    op.create_index(
        "ix_demo_data_records_table_name",
        "demo_data_records",
        ["table_name"],
    )

    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'data.reset'")
    ).scalar()
    if permission_id is None:
        connection.execute(
            sa.text(
                "INSERT INTO permissions (code, name_ar, name_en) "
                "VALUES ('data.reset', 'حذف بيانات العرض التجريبي', "
                "'Delete registered demo data')"
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'data.reset'")
    ).scalar()
    if permission_id is not None:
        connection.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id = :permission_id"
            ),
            {"permission_id": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM permissions WHERE id = :permission_id"),
            {"permission_id": permission_id},
        )
    op.drop_index(
        "ix_demo_data_records_table_name",
        table_name="demo_data_records",
    )
    op.drop_index(
        "ix_demo_data_records_company_id",
        table_name="demo_data_records",
    )
    op.drop_table("demo_data_records")
