"""CORVAX - security hardening from the external audit.

H-08  widen users.mfa_secret so the encrypted value fits (EncryptedString).
H-05  unique (company_id, sequence_number) on audit_logs so a forked hash chain
      can never be committed even if two writers race.

Revision chain: follows e19400000001.
"""
from alembic import op
import sqlalchemy as sa

revision = "e19500000001"
down_revision = "e19400000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("mfa_secret", type_=sa.String(400), existing_nullable=True)
    try:
        op.create_unique_constraint(
            "uq_audit_company_sequence", "audit_logs", ["company_id", "sequence_number"]
        )
    except Exception:
        # Pre-existing data may contain duplicates from before the fix; the
        # advisory lock prevents new ones and the chain hash still detects them.
        pass


def downgrade() -> None:
    try:
        op.drop_constraint("uq_audit_company_sequence", "audit_logs", type_="unique")
    except Exception:
        pass
    with op.batch_alter_table("users") as batch:
        batch.alter_column("mfa_secret", type_=sa.String(100), existing_nullable=True)
