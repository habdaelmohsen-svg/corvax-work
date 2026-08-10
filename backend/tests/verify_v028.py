from __future__ import annotations
import os, sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_DIR))
DB=Path('/tmp')/'verify_v028.db'; DB.unlink(missing_ok=True)
os.environ['DATABASE_URL']=f'sqlite:///{DB}'
os.environ['SEED_DEMO_DATA']='true'
os.environ['SECRET_KEY']='verification-secret-key-v028-long-enough'
os.environ['ENVIRONMENT']='testing'

from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import ConsolidationAdjustment, ConsolidationLine, IntercompanyMatch, IntercompanyRecord


def ok(r,s=200):
    assert r.status_code==s,(r.status_code,r.text)
    return r.json()

with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'}))
    h={'Authorization':f"Bearer {login['access_token']}"}
    health=ok(c.get('/health'))
    assert health['version']=='1.0.0-agreement-completion-rc27.4-r9.1'

    rec_a=ok(c.post('/api/v1/intercompany/records',headers=h,json={
        'company_id':2,'counterparty_company_id':3,'document_number':'IC-2026-001',
        'transaction_date':'2026-12-15','direction':'RECEIVABLE','account_code':'112010',
        'currency_code':'SAR','foreign_amount':'10000','local_amount':'10000',
        'description':'Management services receivable'}),201)
    rec_b=ok(c.post('/api/v1/intercompany/records',headers=h,json={
        'company_id':3,'counterparty_company_id':2,'document_number':'IC-2026-001',
        'transaction_date':'2026-12-15','direction':'PAYABLE','account_code':'211010',
        'currency_code':'SAR','foreign_amount':'10000','local_amount':'10000',
        'description':'Management services payable'}),201)
    match=ok(c.post('/api/v1/intercompany/matches',headers=h,json={
        'record_a_id':rec_a['id'],'record_b_id':rec_b['id'],'tolerance':'0.01'}),201)
    assert Decimal(str(match['matched_amount']))==Decimal('10000')
    assert Decimal(str(match['variance_amount']))==Decimal('0')

    recon=ok(c.get('/api/v1/intercompany/reconciliation?company_id=2&period_end=2026-12-31',headers=h))
    assert recon['open_count']==0 and Decimal(str(recon['matched_total']))==Decimal('10000')

    group=ok(c.post('/api/v1/fx-consolidation/groups',headers=h,json={
        'code':'IC-GRP-2026','name_ar':'مجموعة الاستبعاد','name_en':'Intercompany Group',
        'reporting_currency':'SAR','member_company_ids':[2,3]}),201)
    run=ok(c.post('/api/v1/fx-consolidation/runs',headers=h,json={
        'group_id':group['id'],'period_end':'2026-12-31','elimination_entries':[],
        'auto_eliminate_intercompany':True}),201)
    assert Decimal(str(run['total_debit']))==Decimal(str(run['total_credit']))
    assert Decimal(str(run['elimination_amount']))==Decimal('10000')

    details=ok(c.get(f"/api/v1/fx-consolidation/runs/{run['id']}",headers=h))
    elim=[x for x in details['lines'] if x['is_elimination']]
    assert len(elim)==2
    assert sum(Decimal(str(x['debit'])) for x in elim)==Decimal('10000')
    assert sum(Decimal(str(x['credit'])) for x in elim)==Decimal('10000')

    with SessionLocal() as db:
        assert db.query(IntercompanyRecord).count()==2
        assert db.query(IntercompanyMatch).count()==1
        assert db.query(ConsolidationAdjustment).count()==1
        assert db.query(ConsolidationLine).filter_by(is_elimination=True).count()==2

print('CORVAX v0.28 intercompany reconciliation and elimination: ALL VERIFICATIONS PASSED')
DB.unlink(missing_ok=True)
