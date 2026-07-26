import os
DB_PATH = '/tmp/corvax_branch_scope_security.db'
try:
    os.remove(DB_PATH)
except FileNotFoundError:
    pass
os.environ['DATABASE_URL'] = f'sqlite:///{DB_PATH}'
os.environ.setdefault('SEED_DEMO_DATA', 'false')
os.environ.setdefault('AUTO_CREATE_SCHEMA', 'false')

from sqlalchemy import delete
from app.db import engine
from app.models import Base
Base.metadata.create_all(bind=engine)
from app.db import SessionLocal
from app.dependencies import allowed_branch_ids, ensure_branch_access
from app.models import Branch, Company, Role, User, UserCompanyRole

with SessionLocal() as db:
    # Isolated records with high deterministic IDs.
    for model in (UserCompanyRole, User, Role, Branch, Company):
        try:
            db.execute(delete(model).where(model.id >= 900000))
        except Exception:
            pass
    c1 = Company(id=900001, code='TST1', name_ar='شركة 1', name_en='Company 1')
    c2 = Company(id=900002, code='TST2', name_ar='شركة 2', name_en='Company 2')
    b1 = Branch(id=900011, company=c1, code='B1', name_ar='فرع 1', name_en='Branch 1')
    b2 = Branch(id=900012, company=c1, code='B2', name_ar='فرع 2', name_en='Branch 2')
    b3 = Branch(id=900021, company=c2, code='B3', name_ar='فرع 3', name_en='Branch 3')
    role = Role(id=900001, code='TST_ROLE', name_ar='اختبار', name_en='Test')
    restricted = User(id=900001, name_ar='مقيد', name_en='Restricted', email='restricted@test.local', password_hash='x')
    full = User(id=900002, name_ar='كامل', name_en='Full', email='full@test.local', password_hash='x')
    m1 = UserCompanyRole(user=restricted, company=c1, role=role, branch_scope='SELECTED', branches=[b1])
    m2 = UserCompanyRole(user=full, company=c1, role=role, branch_scope='ALL')
    db.add_all([c1, c2, b1, b2, b3, role, restricted, full, m1, m2])
    db.commit()

    assert allowed_branch_ids(db, restricted, c1.id) == {b1.id}
    assert allowed_branch_ids(db, full, c1.id) == {b1.id, b2.id}
    ensure_branch_access(db, restricted, c1.id, b1.id)
    try:
        ensure_branch_access(db, restricted, c1.id, b2.id)
    except Exception as exc:
        assert getattr(exc, 'status_code', None) == 403
    else:
        raise AssertionError('Restricted user accessed an unauthorized branch')
    try:
        ensure_branch_access(db, restricted, c1.id, b3.id)
    except Exception as exc:
        assert getattr(exc, 'status_code', None) == 422
    else:
        raise AssertionError('Cross-company branch was accepted')

print('verify_branch_scope_security: PASSED')
