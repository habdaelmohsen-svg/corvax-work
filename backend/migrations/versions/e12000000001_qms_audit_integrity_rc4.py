"""enterprise qms and audit integrity rc4

Revision ID: e12000000001
Revises: e11000000001
"""
from alembic import op
import sqlalchemy as sa
import hashlib
import json
from datetime import datetime

revision = "e12000000001"
down_revision = "e11000000001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("audit_logs") as batch:
        batch.add_column(sa.Column("sequence_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("previous_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("record_hash", sa.String(64), nullable=True))
        batch.create_index("ix_audit_logs_sequence_number", ["sequence_number"], unique=False)
        batch.create_index("ix_audit_logs_record_hash", ["record_hash"], unique=True)

    # Establish a deterministic chain for existing audit rows at migration time.
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, company_id, user_id, action, entity_type, entity_id, before_json, after_json, created_at
        FROM audit_logs ORDER BY company_id, created_at, id
    """)).mappings().all()
    state = {}
    for row in rows:
        key = row["company_id"]
        sequence, previous_hash = state.get(key, (0, None))
        sequence += 1
        created_at = row["created_at"]
        created_text = created_at.isoformat(timespec="microseconds") if hasattr(created_at, "isoformat") else datetime.fromisoformat(str(created_at)).isoformat(timespec="microseconds")
        payload = {
            "company_id": key, "sequence_number": sequence, "previous_hash": previous_hash or "GENESIS",
            "user_id": row["user_id"], "action": row["action"], "entity_type": row["entity_type"],
            "entity_id": str(row["entity_id"]), "before_json": row["before_json"], "after_json": row["after_json"],
            "created_at": created_text,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        bind.execute(sa.text("""
            UPDATE audit_logs SET sequence_number=:seq, previous_hash=:prev, record_hash=:hash WHERE id=:id
        """), {"seq": sequence, "prev": previous_hash, "hash": record_hash, "id": row["id"]})
        state[key] = (sequence, record_hash)

    op.create_table(
        "quality_objectives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False, index=True),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("metric_name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False, server_default="PERCENT"),
        sa.Column("baseline_value", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("target_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("current_value", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("frequency", sa.String(20), nullable=False, server_default="MONTHLY"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", name="uq_quality_objective_company_code"),
    )
    op.create_table(
        "quality_inspection_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False, index=True),
        sa.Column("name_ar", sa.String(250), nullable=False),
        sa.Column("name_en", sa.String(250), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("inspection_stage", sa.String(30), nullable=False),
        sa.Column("sampling_method", sa.String(30), nullable=False, server_default="FIXED"),
        sa.Column("sample_size", sa.Numeric(18, 4), nullable=False, server_default="1"),
        sa.Column("acceptance_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejection_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("specification", sa.Text()),
        sa.Column("test_method", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "code", name="uq_quality_plan_company_code"),
    )
    op.create_table(
        "quality_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True),
        sa.Column("action_type", sa.String(20), nullable=False, server_default="CORRECTIVE"),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("root_cause_method", sa.String(30), nullable=False, server_default="5_WHY"),
        sa.Column("root_cause", sa.Text()),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN", index=True),
        sa.Column("effectiveness_result", sa.String(20)),
        sa.Column("effectiveness_notes", sa.Text()),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("verified_at", sa.DateTime()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "number", name="uq_quality_action_company_number"),
    )
    op.create_table(
        "customer_quality_complaints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True),
        sa.Column("received_date", sa.Date(), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("parties.id")),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("lot_number", sa.String(80)),
        sa.Column("channel", sa.String(30), nullable=False, server_default="DIRECT"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("immediate_containment", sa.Text()),
        sa.Column("root_cause", sa.Text()),
        sa.Column("resolution", sa.Text()),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN", index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("closed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_quality_complaint_company_number"),
    )
    op.create_table(
        "supplier_quality_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("parties.id"), nullable=False, index=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("quality_score", sa.Numeric(8, 2), nullable=False),
        sa.Column("delivery_score", sa.Numeric(8, 2), nullable=False),
        sa.Column("documentation_score", sa.Numeric(8, 2), nullable=False),
        sa.Column("overall_score", sa.Numeric(8, 2), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.Column("evaluated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "supplier_id", "period_start", "period_end", name="uq_supplier_quality_period"),
    )
    op.create_table(
        "quality_management_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.String(50), nullable=False, index=True),
        sa.Column("review_date", sa.Date(), nullable=False, index=True),
        sa.Column("scope", sa.String(250), nullable=False),
        sa.Column("inputs_summary", sa.Text(), nullable=False),
        sa.Column("decisions", sa.Text()),
        sa.Column("improvement_opportunities", sa.Text()),
        sa.Column("resource_needs", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT", index=True),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("company_id", "number", name="uq_quality_management_review_number"),
    )

    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=bind)
    roles = sa.Table("roles", meta, autoload_with=bind)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=bind)
    defs = {
        "quality.objectives": ("إدارة أهداف الجودة", "Manage quality objectives"),
        "quality.plans": ("إدارة خطط الفحص", "Manage inspection plans"),
        "quality.capa": ("إدارة الإجراءات التصحيحية والوقائية", "Manage CAPA"),
        "quality.complaints": ("إدارة شكاوى الجودة", "Manage quality complaints"),
        "quality.suppliers": ("تقييم جودة الموردين", "Evaluate supplier quality"),
        "quality.review": ("إدارة مراجعة الإدارة للجودة", "Manage quality management review"),
        "audit.verify_integrity": ("التحقق من سلامة سجل المراجعة", "Verify audit-log integrity"),
    }
    pids = {}
    for code, (ar, en) in defs.items():
        pid = bind.execute(sa.select(permissions.c.id).where(permissions.c.code == code)).scalar()
        if pid is None:
            result = bind.execute(permissions.insert().values(code=code, name_ar=ar, name_en=en))
            pid = result.inserted_primary_key[0]
        pids[code] = pid
    grants = {
        "QUALITY_MANAGER": list(defs.keys()),
        "CFO": ["quality.objectives", "quality.review", "audit.verify_integrity"],
        "AUDITOR": ["quality.review", "audit.verify_integrity"],
        "FINANCIAL_CONTROLLER": ["audit.verify_integrity"],
    }
    for role_code, codes in grants.items():
        rid = bind.execute(sa.select(roles.c.id).where(roles.c.code == role_code)).scalar()
        if rid is None:
            continue
        for code in codes:
            exists = bind.execute(sa.select(role_permissions.c.role_id).where(role_permissions.c.role_id == rid, role_permissions.c.permission_id == pids[code])).scalar()
            if exists is None:
                bind.execute(role_permissions.insert().values(role_id=rid, permission_id=pids[code]))


def downgrade():
    op.drop_table("quality_management_reviews")
    op.drop_table("supplier_quality_evaluations")
    op.drop_table("customer_quality_complaints")
    op.drop_table("quality_actions")
    op.drop_table("quality_inspection_plans")
    op.drop_table("quality_objectives")
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_index("ix_audit_logs_record_hash")
        batch.drop_index("ix_audit_logs_sequence_number")
        batch.drop_column("record_hash")
        batch.drop_column("previous_hash")
        batch.drop_column("sequence_number")
