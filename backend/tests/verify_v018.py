from __future__ import annotations
import os, sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v018.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["SECRET_KEY"] = "verification-secret-key-v018-long-enough"
os.environ["ENVIRONMENT"] = "testing"

from fastapi.testclient import TestClient
from app.main import app

def ok(r, status=200):
    assert r.status_code == status, (r.status_code, r.text)
    return r.json()

with TestClient(app) as client:
    login = ok(client.post('/api/v1/auth/login', json={'email':'admin@corvaxplatform.com','password':'Corvax@123'}))
    h = {'Authorization': f"Bearer {login['access_token']}"}
    assert ok(client.get('/health'))['version'] == '1.0.0-agreement-completion-rc27.4-r9'
    ok(client.post('/api/v1/fx-consolidation/rates', headers=h, json={
        'company_id':1,'currency_code':'USD','rate_date':'2026-07-12','rate':'3.75','source':'SAMA_REFERENCE'}), 201)
    ok(client.post('/api/v1/fx-consolidation/balances', headers=h, json={
        'company_id':1,'account_code':'112010','currency_code':'USD','foreign_amount':'1000',
        'carrying_amount':'3700','last_rate':'3.70'}), 201)
    rv = ok(client.post('/api/v1/fx-consolidation/revaluations', headers=h, json={
        'company_id':1,'revaluation_date':'2026-07-12','gain_account_code':'411010','loss_account_code':'613010'}), 201)
    assert float(rv['total_gain']) == 50.0 and float(rv['total_loss']) == 0.0
    group = ok(client.post('/api/v1/fx-consolidation/groups', headers=h, json={
        'code':'CORVAX-GRP','name_ar':'مجموعة نيكسورا','name_en':'CORVAX Group',
        'reporting_currency':'SAR','member_company_ids':[1,2,3,4]}), 201)
    run = ok(client.post('/api/v1/fx-consolidation/runs', headers=h, json={
        'group_id':group['id'],'period_end':'2026-07-12','elimination_entries':[]}), 201)
    assert float(run['total_debit']) == float(run['total_credit'])
    details = ok(client.get(f"/api/v1/fx-consolidation/runs/{run['id']}", headers=h))
    assert details['lines'] and all('account_code' in x for x in details['lines'])
print('CORVAX v0.18 FX and consolidation: ALL VERIFICATIONS PASSED')
