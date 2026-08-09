"""Add optional supplier context to purchase requisitions.

Revision ID: e20400000001
Revises: e20300000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e20400000001"
down_revision = "e20300000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_requisitions") as batch:
        batch.add_column(sa.Column("suggested_supplier_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_purchase_requisition_suggested_supplier",
            "parties",
            ["suggested_supplier_id"],
            ["id"],
        )
        batch.create_index(
            "ix_purchase_requisitions_suggested_supplier_id",
            ["suggested_supplier_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("purchase_requisitions") as batch:
        batch.drop_index("ix_purchase_requisitions_suggested_supplier_id")
        batch.drop_constraint("fk_purchase_requisition_suggested_supplier", type_="foreignkey")
        batch.drop_column("suggested_supplier_id")
