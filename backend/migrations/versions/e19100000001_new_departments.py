"""CORVAX RC27.4 H10 - new departments: maintenance, fleet/logistics, legal affairs.

Revision chain: follows the H9 head e19000000001.
"""
from alembic import op
import sqlalchemy as sa


revision = "e19100000001"
down_revision = "e19000000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plate_number", sa.String(30), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("vehicle_type", sa.String(30), nullable=False, server_default="REFRIGERATED_TRUCK"),
        sa.Column("make", sa.String(80)),
        sa.Column("model", sa.String(80)),
        sa.Column("year", sa.Integer()),
        sa.Column("is_refrigerated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("odometer_km", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "fleet_drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("license_number", sa.String(60), nullable=False),
        sa.Column("license_expiry", sa.Date()),
        sa.Column("phone", sa.String(30)),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "fleet_trips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("fleet_vehicles.id"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("fleet_drivers.id"), nullable=False),
        sa.Column("trip_date", sa.Date(), nullable=False),
        sa.Column("origin_ar", sa.String(200)),
        sa.Column("origin_en", sa.String(200)),
        sa.Column("destination_ar", sa.String(200)),
        sa.Column("destination_en", sa.String(200)),
        sa.Column("purpose", sa.String(30), nullable=False, server_default="DELIVERY"),
        sa.Column("distance_km", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("fuel_cost", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("cargo_description_ar", sa.String(300)),
        sa.Column("cargo_description_en", sa.String(300)),
        sa.Column("cargo_temperature", sa.Numeric(6, 2)),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "legal_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("contract_type", sa.String(30), nullable=False, server_default="SUPPLIER"),
        sa.Column("counterparty_ar", sa.String(200)),
        sa.Column("counterparty_en", sa.String(200)),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "legal_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(40), nullable=False, index=True),
        sa.Column("title_ar", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("case_type", sa.String(30), nullable=False, server_default="COMMERCIAL"),
        sa.Column("counterparty_ar", sa.String(200)),
        sa.Column("counterparty_en", sa.String(200)),
        sa.Column("court_ar", sa.String(200)),
        sa.Column("court_en", sa.String(200)),
        sa.Column("filing_date", sa.Date()),
        sa.Column("hearing_date", sa.Date()),
        sa.Column("claim_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "legal_licenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("license_type", sa.String(40), nullable=False, server_default="COMMERCIAL_REGISTRATION"),
        sa.Column("license_number", sa.String(80), nullable=False),
        sa.Column("issuer_ar", sa.String(200)),
        sa.Column("issuer_en", sa.String(200)),
        sa.Column("issue_date", sa.Date()),
        sa.Column("expiry_date", sa.Date(), index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="VALID"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "legal_licenses", "legal_cases", "legal_contracts",
        "fleet_trips", "fleet_drivers", "fleet_vehicles",
    ):
        op.drop_table(table)
