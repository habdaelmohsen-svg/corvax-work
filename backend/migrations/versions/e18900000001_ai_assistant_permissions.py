"""Add read-only CORVAX AI Assistant permissions.

Revision ID: e18900000001
Revises: e18800000001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e18900000001"
down_revision = "e18800000001"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("ai.assistant.use", "استخدام مساعد كورفاكس", "Use CORVAX AI Assistant"),
    ("ai.assistant.data", "استعلام بيانات الشركة عبر المساعد", "Query company data through the assistant"),
    ("ai.assistant.analysis", "تحليل بيانات الشركة عبر المساعد", "Analyze company data through the assistant"),
    ("ai.assistant.admin", "إدارة إعدادات مساعد كورفاكس", "Administer CORVAX AI Assistant"),
)


def upgrade() -> None:
    connection = op.get_bind()
    for code, name_ar, name_en in PERMISSIONS:
        permission_id = connection.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}).scalar()
        if permission_id is None:
            connection.execute(sa.text("INSERT INTO permissions (code, name_ar, name_en) VALUES (:code, :name_ar, :name_en)"), {"code": code, "name_ar": name_ar, "name_en": name_en})
            permission_id = connection.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}).scalar_one()
        wildcard_roles = connection.execute(sa.text("SELECT DISTINCT rp.role_id FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id WHERE p.code = '*'" )).scalars().all()
        for role_id in wildcard_roles:
            exists = connection.execute(sa.text("SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id"), {"role_id": role_id, "permission_id": permission_id}).scalar()
            if not exists:
                connection.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"), {"role_id": role_id, "permission_id": permission_id})


def downgrade() -> None:
    connection = op.get_bind()
    for code, _, _ in reversed(PERMISSIONS):
        permission_id = connection.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}).scalar()
        if permission_id is not None:
            connection.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            connection.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
