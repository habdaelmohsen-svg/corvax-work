from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
admin = (ROOT / 'backend/app/api/admin.py').read_text()
roles = (ROOT / 'backend/app/api/roles.py').read_text()
render = (ROOT / 'render.yaml').read_text()
assert '_protect_global_user_change' in admin
assert 'Only SUPER_ADMIN can perform global changes on a multi-company user' in admin
assert 'Only SUPER_ADMIN can assign the SUPER_ADMIN role' in admin
assert 'Role.code != "SUPER_ADMIN"' in roles
for expected in ('ENVIRONMENT\n        value: production','SEED_DEMO_DATA\n        value: false','FORCE_HTTPS\n        value: true','DOCS_ENABLED\n        value: false','ENFORCE_SENSITIVE_ROLE_MFA\n        value: true','PAYROLL_STRICT_WORKFLOW\n        value: true'):
    assert expected in render
print('verify_admin_tenant_hardening: PASSED')
