from __future__ import annotations
import os, sys
from pathlib import Path
BACKEND_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(BACKEND_DIR))
DB=BACKEND_DIR/'data'/'verify_v020.db'; DB.unlink(missing_ok=True)
os.environ['DATABASE_URL']=f'sqlite:///{DB}'; os.environ['SEED_DEMO_DATA']='true'; os.environ['SECRET_KEY']='verification-secret-key-v020-long-enough'; os.environ['ENVIRONMENT']='testing'
from fastapi.testclient import TestClient
from app.main import app

def ok(r,s=200): assert r.status_code==s,(r.status_code,r.text); return r.json()
with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'})); h={'Authorization':f"Bearer {login['access_token']}"}
    assert ok(c.get('/health'))['version']== '1.0.0-agreement-completion-rc27.3'
    p=ok(c.post('/api/v1/risk-maintenance/ifrs9/portfolios',headers=h,json={'company_id':1,'code':'TRADE','name_ar':'العملاء','name_en':'Trade receivables','buckets':[{'min_days':0,'max_days':30,'loss_rate':'0.01'},{'min_days':31,'max_days':90,'loss_rate':'0.05'},{'min_days':91,'max_days':None,'loss_rate':'0.20'}]}),201)
    ok(c.post('/api/v1/risk-maintenance/ifrs9/exposures',headers=h,json={'company_id':1,'portfolio_id':p['id'],'reference':'INV-1','customer_name':'Customer A','due_date':'2026-06-01','gross_amount':'10000','carrying_amount':'10000'}),201)
    run=ok(c.post('/api/v1/risk-maintenance/ifrs9/runs',headers=h,json={'company_id':1,'portfolio_id':p['id'],'as_of_date':'2026-07-12','post_journal':False}),201)
    assert float(run['expected_credit_loss'])==500.0
    a=ok(c.post('/api/v1/risk-maintenance/maintenance/assets',headers=h,json={'company_id':1,'code':'LINE-01','name_ar':'خط 1','name_en':'Line 1','production_line':'Burger','criticality':'HIGH'}),201)
    wo=ok(c.post('/api/v1/risk-maintenance/maintenance/work-orders',headers=h,json={'company_id':1,'asset_id':a['id'],'work_type':'CORRECTIVE','priority':'HIGH','description':'Motor issue'}),201)
    ok(c.post(f"/api/v1/risk-maintenance/maintenance/work-orders/{wo['id']}/start",headers=h))
    done=ok(c.post(f"/api/v1/risk-maintenance/maintenance/work-orders/{wo['id']}/complete",headers=h,json={'downtime_minutes':45,'labor_cost':'300','parts_cost':'700'}))
    assert float(done['total_cost'])==1000.0
    dash=ok(c.get('/api/v1/risk-maintenance/maintenance/dashboard?company_id=1',headers=h)); assert dash['completed_work_orders']==1 and dash['downtime_minutes']==45
print('CORVAX v0.20 IFRS 9 and maintenance: ALL VERIFICATIONS PASSED')
