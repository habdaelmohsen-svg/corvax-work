"""VAT return form profile, controlled adjustments, and HR setup.

Revision ID: e20100000001
Revises: e19900000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e20100000001"
down_revision = "e19900000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch:
        batch.add_column(sa.Column("zatca_distinguished_number", sa.Text()))
        batch.add_column(sa.Column("tax_account_number", sa.Text()))
        batch.add_column(sa.Column("taxpayer_identity_number", sa.Text()))
        batch.add_column(sa.Column("registered_address", sa.Text()))
    with op.batch_alter_table("vat_return_snapshots") as batch:
        batch.add_column(sa.Column("prior_period_correction", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("carried_forward_vat", sa.Numeric(18, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("adjustment_reason", sa.Text()))
        batch.add_column(sa.Column("adjustments_updated_by", sa.Integer()))
        batch.add_column(sa.Column("adjustments_updated_at", sa.DateTime()))
        batch.create_foreign_key(
            "fk_vat_return_adjustments_updated_by_users",
            "users", ["adjustments_updated_by"], ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("vat_return_snapshots") as batch:
        batch.drop_constraint("fk_vat_return_adjustments_updated_by_users", type_="foreignkey")
        batch.drop_column("adjustments_updated_at")
        batch.drop_column("adjustments_updated_by")
        batch.drop_column("adjustment_reason")
        batch.drop_column("carried_forward_vat")
        batch.drop_column("prior_period_correction")
    with op.batch_alter_table("companies") as batch:
        batch.drop_column("registered_address")
        batch.drop_column("taxpayer_identity_number")
        batch.drop_column("tax_account_number")
        batch.drop_column("zatca_distinguished_number")
