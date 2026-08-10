from __future__ import annotations
import os, sys
from pathlib import Path
BACKEND_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(BACKEND_DIR))
DB=Path('/tmp')/'verify_v022.db'; DB.unlink(missing_ok=True)
os.environ['DATABASE_URL']=f'sqlite:///{DB}'; os.environ['SEED_DEMO_DATA']='true'; os.environ['SECRET_KEY']='verification-secret-key-v022-long-enough'; os.environ['ENVIRONMENT']='testing'
from fastapi.testclient import TestClient
from app.main import app

def ok(r,s=200): assert r.status_code==s,(r.status_code,r.text); return r.json()
with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'})); h={'Authorization':f"Bearer {login['access_token']}"}
    assert ok(c.get('/health'))['version']== '1.0.0-agreement-completion-rc27.4-r9'
    a=ok(c.post('/api/v1/risk-maintenance/maintenance/assets',headers=h,json={'company_id':1,'code':'MIX-01','name_ar':'خلاط 1','name_en':'Mixer 1','production_line':'Sauce','criticality':'HIGH'}),201)
    plan=ok(c.post('/api/v1/risk-maintenance/maintenance/plans',headers=h,json={'company_id':1,'asset_id':a['id'],'code':'PM-MIX-30','description':'Monthly inspection','interval_days':30,'next_due_date':'2026-07-01','priority':'HIGH'}),201)
    gen=ok(c.post('/api/v1/risk-maintenance/maintenance/plans/generate-due?company_id=1&as_of_date=2026-07-12',headers=h)); assert gen['generated_count']==1
    wo_id=gen['work_orders'][0]['id']
    part=ok(c.post('/api/v1/risk-maintenance/maintenance/spare-parts',headers=h,json={'company_id':1,'code':'BRG-6204','name_ar':'رولمان بلي','name_en':'Bearing','unit':'EA','quantity_on_hand':'5','reorder_level':'4','average_cost':'125'}),201)
    issue=ok(c.post(f'/api/v1/risk-maintenance/maintenance/work-orders/{wo_id}/issue-part',headers=h,json={'spare_part_id':part['id'],'quantity':'2'})); assert float(issue['issued_cost'])==250 and float(issue['remaining_quantity'])==3
    ok(c.post(f'/api/v1/risk-maintenance/maintenance/work-orders/{wo_id}/start',headers=h))
    done=ok(c.post(f'/api/v1/risk-maintenance/maintenance/work-orders/{wo_id}/complete',headers=h,json={'downtime_minutes':20,'labor_cost':'150','parts_cost':'0'})); assert float(done['total_cost'])==400
    cal=ok(c.post('/api/v1/risk-maintenance/maintenance/calibrations',headers=h,json={'company_id':1,'asset_id':a['id'],'instrument_code':'TEMP-01','calibration_date':'2026-06-01','next_due_date':'2026-07-01','result':'PASS','certificate_reference':'CERT-1'}),201); assert cal['result']=='PASS'
    alerts=ok(c.get('/api/v1/risk-maintenance/maintenance/alerts?company_id=1&as_of_date=2026-07-12',headers=h)); assert len(alerts['low_stock_parts'])==1 and len(alerts['due_calibrations'])==1
print('CORVAX v0.22 maintenance control: ALL VERIFICATIONS PASSED')
