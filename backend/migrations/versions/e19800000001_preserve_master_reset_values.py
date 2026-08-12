"""Preserve asset and lease master cards during UAT value reset.

Revision ID: e19800000001
Revises: e19700000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e19800000001"
down_revision = "e19700000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch:
        batch.alter_column(
            "logo_url",
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=True,
        )
    with op.batch_alter_table("fixed_assets") as batch:
        batch.alter_column(
            "acquisition_journal_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch.alter_column(
            "bank_account_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
    with op.batch_alter_table("lease_contracts") as batch:
        batch.alter_column(
            "initial_journal_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("lease_contracts") as batch:
        batch.alter_column(
            "initial_journal_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
    with op.batch_alter_table("fixed_assets") as batch:
        batch.alter_column(
            "bank_account_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch.alter_column(
            "acquisition_journal_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
    with op.batch_alter_table("companies") as batch:
        batch.alter_column(
            "logo_url",
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=True,
        )
