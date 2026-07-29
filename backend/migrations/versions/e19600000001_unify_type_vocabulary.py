"""CORVAX - unify legacy item and warehouse type spellings.

WHY
    The same concept was stored under several spellings. The seeder wrote
    FINISHED_GOOD while an older screen sent FINISHED; warehouses were created as
    GENERAL although the vocabulary calls that MAIN. Any report or filter that
    grouped by type therefore split one thing into two, and a stock policy keyed
    on "cold storage" would miss rows spelled CHILLED.

    backend/app/api/inventory.py now validates both columns on write. This
    migration brings the rows written BEFORE that guard onto the same vocabulary.

WHAT IT DOES
    Renames values only. No row is added, removed or re-linked, and no quantity,
    cost or account changes. A warehouse called GENERAL becomes MAIN and keeps
    its code, name, branch, stock and history.

UNRECOGNISED VALUES
    Anything outside the vocabulary is parked as MAIN (warehouses) or INVENTORY
    (items) rather than left invalid, because the write guard would otherwise
    refuse every later edit of that row. Both are the neutral "general" option,
    so nothing is silently reclassified as cold storage or as a service.

REVERSIBILITY
    downgrade() restores the two spellings that actually shipped in the seeder
    (GENERAL, FINISHED). Values that were already canonical are left alone.
"""
from alembic import op
import sqlalchemy as sa

revision = "e19600000001"
down_revision = "e19500000001"
branch_labels = None
depends_on = None


# old spelling -> canonical spelling
WAREHOUSE_RENAMES = {
    "GENERAL": "MAIN",
    "CHILLED": "COLD",
    "FINISHED_GOODS": "FINISHED",
    "RAW_MATERIALS": "RAW",
    "TRANSIT_WAREHOUSE": "TRANSIT",
}
WAREHOUSE_VALID = {
    "MAIN", "RAW", "FINISHED", "RAW_AND_FINISHED",
    "COLD", "FROZEN", "QUARANTINE", "TRANSIT",
}

ITEM_RENAMES = {
    "FINISHED": "FINISHED_GOOD",
    "FINISHED_GOODS": "FINISHED_GOOD",
    "RAW": "RAW_MATERIAL",
    "RAW_MATERIALS": "RAW_MATERIAL",
    "PACK": "PACKAGING",
    "STOCK": "INVENTORY",
    "GENERAL": "INVENTORY",
}
ITEM_VALID = {
    "RAW_MATERIAL", "FINISHED_GOOD", "PACKAGING",
    "INVENTORY", "CONSUMABLE", "SERVICE",
}


def _has(table: str) -> bool:
    return table in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()

    if _has("warehouses"):
        # Normalise case and separators first so "cold storage" and Cold-Storage
        # do not survive as distinct values.
        bind.execute(
            sa.text(
                "UPDATE warehouses SET warehouse_type = "
                "UPPER(REPLACE(REPLACE(TRIM(warehouse_type), ' ', '_'), '-', '_')) "
                "WHERE warehouse_type IS NOT NULL"
            )
        )
        for old, new in WAREHOUSE_RENAMES.items():
            bind.execute(
                sa.text("UPDATE warehouses SET warehouse_type = :new WHERE warehouse_type = :old"),
                {"new": new, "old": old},
            )
        # Park anything still unknown on the neutral value.
        bind.execute(
            sa.text(
                "UPDATE warehouses SET warehouse_type = 'MAIN' "
                "WHERE warehouse_type IS NULL OR warehouse_type NOT IN :valid"
            ).bindparams(sa.bindparam("valid", expanding=True)),
            {"valid": sorted(WAREHOUSE_VALID)},
        )

    if _has("items"):
        bind.execute(
            sa.text(
                "UPDATE items SET item_type = "
                "UPPER(REPLACE(REPLACE(TRIM(item_type), ' ', '_'), '-', '_')) "
                "WHERE item_type IS NOT NULL"
            )
        )
        for old, new in ITEM_RENAMES.items():
            bind.execute(
                sa.text("UPDATE items SET item_type = :new WHERE item_type = :old"),
                {"new": new, "old": old},
            )
        bind.execute(
            sa.text(
                "UPDATE items SET item_type = 'INVENTORY' "
                "WHERE item_type IS NULL OR item_type NOT IN :valid"
            ).bindparams(sa.bindparam("valid", expanding=True)),
            {"valid": sorted(ITEM_VALID)},
        )


def downgrade() -> None:
    """Restore the spellings the seeder used before the vocabulary was fixed."""
    bind = op.get_bind()
    if _has("warehouses"):
        bind.execute(sa.text("UPDATE warehouses SET warehouse_type = 'GENERAL' WHERE warehouse_type = 'MAIN'"))
    if _has("items"):
        bind.execute(sa.text("UPDATE items SET item_type = 'FINISHED' WHERE item_type = 'FINISHED_GOOD'"))
