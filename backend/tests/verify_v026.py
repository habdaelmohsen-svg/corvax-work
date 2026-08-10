from __future__ import annotations
import os, sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_DIR))
DB=Path('/tmp')/'verify_v026.db'; DB.unlink(missing_ok=True)
os.environ['DATABASE_URL']=f'sqlite:///{DB}'
os.environ['SEED_DEMO_DATA']='true'
os.environ['SECRET_KEY']='verification-secret-key-v026-long-enough'
os.environ['ENVIRONMENT']='testing'

from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import FiscalPeriod


def ok(r,s=200):
    assert r.status_code==s,(r.status_code,r.text)
    return r.json()

with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'}))
    h={'Authorization':f"Bearer {login['access_token']}"}
    health=ok(c.get('/health'))
    assert health['version']=='1.0.0-agreement-completion-rc27.4-r9.1'
    assert health.get("status") == "ok"

    with SessionLocal() as db:
        for p in db.query(FiscalPeriod).all(): p.status='OPEN'
        db.commit()

    years=ok(c.get('/api/v1/enterprise/companies/1/fiscal-years',headers=h))
    periods=ok(c.get(f"/api/v1/enterprise/fiscal-years/{years[0]['id']}/periods",headers=h))
    december=next(p for p in periods if p['number']==12)

    accrual=ok(c.post('/api/v1/accruals',headers=h,json={
        'company_id':1,'accrual_type':'EXPENSE_ACCRUAL',
        'name_ar':'كهرباء مستحقة نوفمبر','name_en':'November electricity accrual',
        'reference':'ELEC-NOV','accrual_date':'2026-11-30','amount':'5000',
        'debit_account_code':'613010','credit_account_code':'217010',
        'auto_reverse':True,'reversal_date':'2026-12-01'
    }),201)
    assert accrual['status']=='DRAFT'

    recurring=ok(c.post('/api/v1/accruals/recurring',headers=h,json={
        'company_id':1,'code':'MONTHLY-RENT','name_ar':'إثبات إيجار شهري','name_en':'Monthly rent accrual',
        'reference_prefix':'RENT','frequency':'MONTHLY','start_date':'2026-12-01','end_date':'2027-11-01',
        'lines':[
            {'account_code':'612010','debit':'1000','credit':'0'},
            {'account_code':'217010','debit':'0','credit':'1000'}
        ]
    }),201)
    assert recurring['next_run_date']=='2026-12-01'

    review=ok(c.post('/api/v1/period-close/review',headers=h,json={'company_id':1,'fiscal_period_id':december['id']}),201)
    checks={x['code']:x for x in review['checks']}
    assert checks['ACCRUALS_POSTED']['status']=='FAIL'
    assert checks['RECURRING_JOURNALS']['status']=='FAIL'

    posted=ok(c.post(f"/api/v1/accruals/{accrual['id']}/post",headers=h))
    assert posted['status']=='POSTED' and posted['journal_id']

    review=ok(c.post('/api/v1/period-close/review',headers=h,json={'company_id':1,'fiscal_period_id':december['id']}),201)
    checks={x['code']:x for x in review['checks']}
    assert checks['ACCRUALS_POSTED']['status']=='PASS'
    assert checks['ACCRUAL_REVERSALS']['status']=='FAIL'
    assert checks['RECURRING_JOURNALS']['status']=='FAIL'

    rev=ok(c.post('/api/v1/accruals/run-reversals',headers=h,json={'company_id':1,'as_of_date':'2026-12-31'}))
    assert rev['reversed_count']==1
    run=ok(c.post('/api/v1/accruals/recurring/run',headers=h,json={'company_id':1,'as_of_date':'2026-12-31'}))
    assert run['generated_count']==1

    review=ok(c.post('/api/v1/period-close/review',headers=h,json={'company_id':1,'fiscal_period_id':december['id']}),201)
    checks={x['code']:x for x in review['checks']}
    assert checks['ACCRUALS_POSTED']['status']=='PASS'
    assert checks['ACCRUAL_REVERSALS']['status']=='PASS'
    assert checks['RECURRING_JOURNALS']['status']=='PASS'

    rows=ok(c.get('/api/v1/accruals?company_id=1',headers=h))
    assert rows[0]['status']=='REVERSED' and rows[0]['reversal_journal_id']
    templates=ok(c.get('/api/v1/accruals/recurring?company_id=1',headers=h))
    assert len(templates[0]['runs'])==1 and templates[0]['next_run_date']=='2027-01-01'

    summary=ok(c.get('/api/v1/accruals/summary?company_id=1&as_of_date=2026-12-31',headers=h))
    assert summary['drafts']==0 and summary['due_reversals']==0 and summary['recurring_due']==0

    tb=ok(c.get('/api/v1/finance/trial-balance?company_id=1&end_date=2026-12-31',headers=h))
    rows_tb=tb['rows'] if isinstance(tb,dict) else tb
    total_debit=sum(Decimal(str(x['debit'])) for x in rows_tb)
    total_credit=sum(Decimal(str(x['credit'])) for x in rows_tb)
    assert total_debit==total_credit

    fs=ok(c.get('/api/v1/finance/statements?company_id=1&start_date=2026-01-01&end_date=2026-12-31&method=direct',headers=h))
    assert fs['financial_position']['balanced'] is True

    audit=ok(c.get('/api/v1/audit-log?company_id=1&limit=300',headers=h))
    actions={x['action'] for x in audit}
    assert {'ACCRUAL_CREATED','ACCRUAL_POSTED','ACCRUAL_REVERSAL_RUN','RECURRING_TEMPLATE_CREATED','RECURRING_JOURNAL_RUN'}.issubset(actions)

print('CORVAX v0.26 accruals and recurring journals: ALL VERIFICATIONS PASSED')
DB.unlink(missing_ok=True)
