from __future__ import annotations
import os, sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_DIR))
DB=Path('/tmp')/'verify_v024.db'; DB.unlink(missing_ok=True)
os.environ['DATABASE_URL']=f'sqlite:///{DB}'
os.environ['SEED_DEMO_DATA']='true'
os.environ['SECRET_KEY']='verification-secret-key-v024-long-enough'
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
    assert health['version']=='1.0.0-agreement-completion-rc27.4-r9'

    # Open 2026 periods for the year-end verification scenario.
    with SessionLocal() as db:
        for p in db.query(FiscalPeriod).all():
            p.status='OPEN'
        db.commit()

    bank=ok(c.get('/api/v1/banking/accounts?company_id=1',headers=h))[0]
    prepaid=ok(c.post('/api/v1/prepaids',headers=h,json={
        'company_id':1,
        'name_ar':'اشتراك شركة مكافحة حشرات',
        'name_en':'Pest Control Annual Subscription',
        'supplier_name':'Pest Control Co.',
        'payment_date':'2026-03-01',
        'service_start_date':'2026-03-01',
        'service_end_date':'2027-02-28',
        'net_amount':'12000',
        'vat_rate':'15',
        'allocation_method':'MONTHLY_STRAIGHT_LINE',
        'expense_account_code':'613010',
        'prepaid_account_code':'117010',
        'bank_account_id':bank['id'],
    }),201)
    assert len(prepaid['schedules'])==12
    assert all(Decimal(str(x['amount']))==Decimal('1000.00') for x in prepaid['schedules'])
    assert Decimal(str(prepaid['remaining_amount']))==Decimal('12000.00')

    years=ok(c.get('/api/v1/enterprise/companies/1/fiscal-years',headers=h))
    periods=ok(c.get(f"/api/v1/enterprise/fiscal-years/{years[0]['id']}/periods",headers=h))
    december=next(p for p in periods if p['number']==12)
    review=ok(c.post('/api/v1/period-close/review',headers=h,json={'company_id':1,'fiscal_period_id':december['id']}),201)
    prepaid_check=next(x for x in review['checks'] if x['code']=='PREPAID_AMORTIZATION')
    assert prepaid_check['status']=='FAIL' and prepaid_check['details']['count']==10

    run=ok(c.post('/api/v1/prepaids/amortize',headers=h,json={'company_id':1,'as_of_date':'2026-12-31'}))
    assert run['posted_count']==10
    assert Decimal(str(run['amortized_amount']))==Decimal('10000.00')

    rows=ok(c.get('/api/v1/prepaids?company_id=1',headers=h))
    row=rows[0]
    assert Decimal(str(row['amortized_amount']))==Decimal('10000.00')
    assert Decimal(str(row['remaining_amount']))==Decimal('2000.00')
    assert row['status']=='ACTIVE'
    assert sum(1 for x in row['schedules'] if x['status']=='POSTED')==10
    assert sum(1 for x in row['schedules'] if x['status']=='PENDING')==2

    summary=ok(c.get('/api/v1/prepaids/summary?company_id=1&as_of_date=2026-12-31',headers=h))
    assert Decimal(str(summary['remaining']))==Decimal('2000.00')
    assert summary['due_unposted']==0
    review=ok(c.post('/api/v1/period-close/review',headers=h,json={'company_id':1,'fiscal_period_id':december['id']}),201)
    prepaid_check=next(x for x in review['checks'] if x['code']=='PREPAID_AMORTIZATION')
    assert prepaid_check['status']=='PASS' and prepaid_check['details']['count']==0

    # Prepaid balance must be included in current assets and statements must remain balanced.
    fs=ok(c.get('/api/v1/finance/statements?company_id=1&start_date=2026-01-01&end_date=2026-12-31&method=direct',headers=h))
    assert fs['financial_position']['balanced'] is True

    audit=ok(c.get('/api/v1/audit-log?company_id=1&limit=200',headers=h))
    actions={x['action'] for x in audit}
    assert {'PREPAID_EXPENSE_CREATED','PREPAID_AMORTIZATION_RUN'}.issubset(actions)

print('CORVAX v0.24 prepaid expenses: ALL VERIFICATIONS PASSED')
DB.unlink(missing_ok=True)
