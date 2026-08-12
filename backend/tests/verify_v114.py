"""CORVAX RC14 gym operations completion end-to-end verification."""
from __future__ import annotations
import os, sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_DIR))
DB_PATH=Path('/tmp')/'verify_v114.db'; DB_PATH.unlink(missing_ok=True)
os.environ.update({
 'DATABASE_URL':f'sqlite:///{DB_PATH}', 'SECRET_KEY':'verification-secret-key-corvax-rc14',
 'SEED_DEMO_DATA':'true','AUTO_CREATE_SCHEMA':'true','TRUSTED_HOSTS':'testserver,localhost,127.0.0.1',
 'APP_VERSION':'1.0.0-agreement-completion-rc27.4-r9.4','ENABLE_RATE_LIMIT_TESTING':'true'})
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.core.security import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import BankAccount, Branch, Role, User, UserCompanyRole

PASSWORD='Corvax@123'; COMPANY_ID=2

def ok(r):
    assert r.status_code in {200,201,202}, r.text
    return r.json()
def login(c,email):
    r=c.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD}); assert r.status_code==200,r.text
    return {'Authorization':f"Bearer {r.json()['access_token']}"}
def setup_users_branches():
    with SessionLocal() as db:
        role=db.scalar(select(Role).where(Role.code=='SUPER_ADMIN')); assert role
        for email,name in [('rc14-reviewer@corvaxplatform.com','RC14 Reviewer'),('rc14-approver@corvaxplatform.com','RC14 Approver')]:
            u=db.scalar(select(User).where(User.email==email))
            if not u:
                u=User(name_ar=name,name_en=name,email=email,password_hash=hash_password(PASSWORD),active=True);db.add(u);db.flush()
                db.add(UserCompanyRole(user_id=u.id,company_id=COMPANY_ID,role_id=role.id))
        branches=db.scalars(select(Branch).where(Branch.company_id==COMPANY_ID).order_by(Branch.id)).all()
        assert branches
        if len(branches)<2:
            b=Branch(company_id=COMPANY_ID,code='GYM-RC14-B2',name_ar='فرع اختبار ثان',name_en='RC14 Second Branch',active=True)
            db.add(b)
        db.commit()

def main():
  with TestClient(app) as c:
    setup_users_branches()
    admin=login(c,'admin@corvaxplatform.com'); reviewer=login(c,'rc14-reviewer@corvaxplatform.com'); approver=login(c,'rc14-approver@corvaxplatform.com')
    aj={**admin,'Content-Type':'application/json'}; rj={**reviewer,'Content-Type':'application/json'}
    with SessionLocal() as db:
      branches=db.scalars(select(Branch).where(Branch.company_id==COMPANY_ID,Branch.active.is_(True)).order_by(Branch.id)).all()
      bank=db.scalar(select(BankAccount).where(BankAccount.company_id==COMPANY_ID,BankAccount.active.is_(True)))
      assert len(branches)>=2 and bank
      b1,b2,bank_id=branches[0].id,branches[1].id,bank.id

    plan=ok(c.post('/api/v1/revenue-recognition/plans',headers=aj,json={'company_id':COMPANY_ID,'code':'RC14-ANNUAL','name_ar':'سنوي اختبار','name_en':'RC14 Annual','duration_months':12,'net_price':'1200','vat_rate':'15'}))
    premium=ok(c.post('/api/v1/revenue-recognition/plans',headers=aj,json={'company_id':COMPANY_ID,'code':'RC14-PREM','name_ar':'مميز','name_en':'RC14 Premium','duration_months':12,'net_price':'1800','vat_rate':'15'}))
    members=[]; contracts=[]
    for i in range(1,4):
      m=ok(c.post('/api/v1/revenue-recognition/members',headers=aj,json={'company_id':COMPANY_ID,'member_number':f'RC14-M{i}','name_ar':f'عضو {i}','name_en':f'RC14 Member {i}','mobile':f'050000000{i}'}));members.append(m)
      ct=ok(c.post('/api/v1/revenue-recognition/contracts',headers=aj,json={'company_id':COMPANY_ID,'member_id':m['id'],'plan_id':plan['id'],'start_date':'2026-07-01','bank_account_id':bank_id,'branch_id':b1}));contracts.append(ct)

    upgrade=ok(c.post('/api/v1/gym/membership-modifications',headers=aj,json={'company_id':COMPANY_ID,'contract_id':contracts[0]['id'],'modification_type':'UPGRADE','effective_date':'2026-07-05','new_plan_id':premium['id'],'adjustment_net':'600','bank_account_id':bank_id,'reason':'RC14 upgrade verification'}))
    assert c.post(f"/api/v1/gym/membership-modifications/{upgrade['id']}/approve",headers=admin).status_code==409
    up=ok(c.post(f"/api/v1/gym/membership-modifications/{upgrade['id']}/approve",headers=reviewer)); assert up['status']=='APPROVED_POSTED'

    freeze=ok(c.post('/api/v1/gym/membership-modifications',headers=aj,json={'company_id':COMPANY_ID,'contract_id':contracts[0]['id'],'modification_type':'FREEZE','effective_date':'2026-07-09','freeze_start':'2026-07-10','freeze_end':'2026-07-12','reason':'Travel freeze verification'}))
    ok(c.post(f"/api/v1/gym/membership-modifications/{freeze['id']}/approve",headers=reviewer))
    denied=ok(c.post('/api/v1/gym/access-records',headers=aj,json={'company_id':COMPANY_ID,'branch_id':b1,'member_id':members[0]['id'],'occurred_at':'2026-07-11T10:00:00','direction':'IN','method':'QR'})); assert denied['status']=='DENIED' and denied['reason']=='MEMBERSHIP_FROZEN'
    granted=ok(c.post('/api/v1/gym/access-records',headers=aj,json={'company_id':COMPANY_ID,'branch_id':b1,'member_id':members[0]['id'],'occurred_at':'2026-07-13T10:00:00','direction':'IN','method':'QR'})); assert granted['status']=='GRANTED'

    trainer=ok(c.post('/api/v1/gym/trainers',headers=aj,json={'company_id':COMPANY_ID,'branch_id':b1,'code':'TR-RC14','name_ar':'مدرب اختبار','name_en':'RC14 Trainer','commission_rate':'20'}))
    ctype=ok(c.post('/api/v1/gym/class-types',headers=aj,json={'company_id':COMPANY_ID,'code':'YOGA-RC14','name_ar':'يوغا','name_en':'RC14 Yoga','duration_minutes':60,'default_capacity':1}))
    session=ok(c.post('/api/v1/gym/class-sessions',headers=aj,json={'company_id':COMPANY_ID,'branch_id':b1,'class_type_id':ctype['id'],'trainer_id':trainer['id'],'starts_at':'2026-07-14T18:00:00','capacity':1,'waitlist_enabled':True}))
    book1=ok(c.post(f"/api/v1/gym/class-sessions/{session['id']}/book",headers=aj,json={'member_id':members[0]['id'],'contract_id':contracts[0]['id']})); assert book1['status']=='BOOKED'
    book2=ok(c.post(f"/api/v1/gym/class-sessions/{session['id']}/book",headers=aj,json={'member_id':members[1]['id'],'contract_id':contracts[1]['id']})); assert book2['status']=='WAITLISTED'
    cancelled=ok(c.post(f"/api/v1/gym/class-bookings/{book1['id']}/cancel",headers=admin)); assert cancelled['promoted_booking_id']==book2['id']
    attended=ok(c.post(f"/api/v1/gym/class-bookings/{book2['id']}/attendance",headers=aj,json={'status':'ATTENDED'})); assert attended['status']=='ATTENDED'

    package=ok(c.post('/api/v1/gym/pt-packages',headers=aj,json={'company_id':COMPANY_ID,'code':'PT-RC14','name_ar':'تدريب شخصي','name_en':'RC14 PT','sessions_count':4,'validity_days':90,'net_price':'400','vat_rate':'15'}))
    sale=ok(c.post('/api/v1/gym/pt-sales',headers=aj,json={'company_id':COMPANY_ID,'branch_id':b1,'member_id':members[0]['id'],'membership_contract_id':contracts[0]['id'],'package_id':package['id'],'trainer_id':trainer['id'],'bank_account_id':bank_id,'sale_date':'2026-07-13'}))
    pts=ok(c.post('/api/v1/gym/pt-sessions',headers=aj,json={'pt_sale_id':sale['id'],'session_at':'2026-07-14T14:00:00','notes':'RC14 test'}))
    completed=ok(c.post(f"/api/v1/gym/pt-sessions/{pts['id']}/complete",headers=admin)); assert Decimal(str(completed['revenue_amount']))==Decimal('100.00') and Decimal(str(completed['commission_amount']))==Decimal('20.00')
    batch=ok(c.post('/api/v1/gym/commission-batches',headers=aj,json={'company_id':COMPANY_ID,'trainer_id':trainer['id'],'bank_account_id':bank_id,'period_start':'2026-07-01','period_end':'2026-07-31'}))
    assert c.post(f"/api/v1/gym/commission-batches/{batch['id']}/review",headers=admin).status_code==409
    reviewed=ok(c.post(f"/api/v1/gym/commission-batches/{batch['id']}/review",headers=reviewer)); assert reviewed['status']=='REVIEWED'
    assert c.post(f"/api/v1/gym/commission-batches/{batch['id']}/approve",headers=reviewer).status_code==409
    paid=ok(c.post(f"/api/v1/gym/commission-batches/{batch['id']}/approve",headers=approver)); assert paid['status']=='APPROVED_POSTED'

    locker=ok(c.post('/api/v1/gym/lockers',headers=aj,json={'company_id':COMPANY_ID,'branch_id':b1,'code':'L-RC14-01'}))
    assignment=ok(c.post('/api/v1/gym/locker-assignments',headers=aj,json={'locker_id':locker['id'],'member_id':members[0]['id'],'contract_id':contracts[0]['id'],'start_date':'2026-07-13','deposit_amount':'50'})); assert assignment['status']=='ACTIVE'
    transfer=ok(c.post('/api/v1/gym/branch-transfers',headers=aj,json={'company_id':COMPANY_ID,'member_id':members[0]['id'],'contract_id':contracts[0]['id'],'to_branch_id':b2,'transfer_date':'2026-07-15','reason':'RC14 branch transfer'}))
    assert c.post(f"/api/v1/gym/branch-transfers/{transfer['id']}/approve",headers=admin).status_code==409
    moved=ok(c.post(f"/api/v1/gym/branch-transfers/{transfer['id']}/approve",headers=reviewer)); assert moved['released_lockers']==1
    new_access=ok(c.post('/api/v1/gym/access-records',headers=aj,json={'company_id':COMPANY_ID,'branch_id':b2,'member_id':members[0]['id'],'occurred_at':'2026-07-16T10:00:00'})); assert new_access['status']=='GRANTED'

    cancel=ok(c.post('/api/v1/gym/membership-modifications',headers=aj,json={'company_id':COMPANY_ID,'contract_id':contracts[1]['id'],'modification_type':'CANCEL','effective_date':'2026-07-16','refund_method':'CREDIT','reason':'RC14 cancellation credit'}))
    cancel=ok(c.post(f"/api/v1/gym/membership-modifications/{cancel['id']}/approve",headers=reviewer)); assert cancel['status']=='APPROVED_POSTED'
    ledger=ok(c.get(f"/api/v1/gym/member-ledger?company_id={COMPANY_ID}&member_id={members[1]['id']}",headers=admin)); assert Decimal(str(ledger['credit_available']))==Decimal('1380.00')
    replacement=ok(c.post('/api/v1/revenue-recognition/contracts',headers=aj,json={'company_id':COMPANY_ID,'member_id':members[1]['id'],'plan_id':plan['id'],'start_date':'2026-07-17','bank_account_id':bank_id,'branch_id':b1}))
    extension=ok(c.post('/api/v1/gym/membership-modifications',headers=aj,json={'company_id':COMPANY_ID,'contract_id':replacement['id'],'modification_type':'EXTENSION','effective_date':'2026-07-18','extension_days':30,'adjustment_net':'100','credit_used':'115','payment_method':'CREDIT','reason':'RC14 extension using credit'}))
    extension=ok(c.post(f"/api/v1/gym/membership-modifications/{extension['id']}/approve",headers=reviewer)); assert extension['status']=='APPROVED_POSTED'

    summary=ok(c.get(f'/api/v1/gym/summary?company_id={COMPANY_ID}',headers=admin)); assert summary['contracts']>=3 and summary['denied_access_records']>=1 and summary['scheduled_classes']>=1
    rev=ok(c.get(f'/api/v1/revenue-recognition/summary?company_id={COMPANY_ID}',headers=admin)); assert Decimal(str(rev['reconciliation_difference']))==Decimal('0.00'),rev
    print('CORVAX v1.0 RC14 gym operations completion: ALL VERIFICATIONS PASSED')

if __name__=='__main__': main()
