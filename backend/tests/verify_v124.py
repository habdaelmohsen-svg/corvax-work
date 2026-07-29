"""CORVAX RC24 Saudi zakat and corporate income tax engine verification."""
from __future__ import annotations
import os, sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_DIR))
DB_PATH=Path('/tmp')/'verify_v124.db';DB_PATH.unlink(missing_ok=True)
os.environ.update({'DATABASE_URL':f'sqlite:///{DB_PATH}','SECRET_KEY':'verification-secret-key-corvax-rc24-zakat-cit','SEED_DEMO_DATA':'true','AUTO_CREATE_SCHEMA':'true','TRUSTED_HOSTS':'testserver,localhost,127.0.0.1','APP_VERSION':'1.0.0-agreement-completion-rc27.4','ENABLE_RATE_LIMIT_TESTING':'true'})
import subprocess
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=True)
from fastapi.testclient import TestClient
from sqlalchemy import select,text
from app.db import SessionLocal
from app.main import app
from app.models import Account,JournalEntry,JournalLine,TaxLossCarryforward,ZakatIncomeTaxReturn,FiscalYear,FiscalPeriod
from app.services.posting import create_posted_journal

def D(v):return Decimal(str(v)).quantize(Decimal('0.01'))
def ok(r,status=200):assert r.status_code==status,r.text;return r.json()

def main():
  with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'}));admin={'Authorization':f"Bearer {login['access_token']}"}
    assert ok(c.get('/health'))['version']=='1.0.0-agreement-completion-rc27.4'
    from app.core.migration_head import expected_migration_head
    assert ok(c.get('/health/ready'))['migration_head']==expected_migration_head()
    ok(c.post('/api/v1/admin/users',headers=admin,json={'name_ar':'مراجع الزكاة والضريبة','name_en':'Zakat CIT Approver','email':'rc24.approver@corvaxplatform.com','password':'Rc24Approver@123','require_password_change':False,'memberships':[{'company_id':1,'role_code':'SUPER_ADMIN'}]}),201)
    al=ok(c.post('/api/v1/auth/login',json={'email':'rc24.approver@corvaxplatform.com','password':'Rc24Approver@123'}));approver={'Authorization':f"Bearer {al['access_token']}"}
    with SessionLocal() as db:
      db.execute(text("update fiscal_periods set status='OPEN'"))
      db.execute(text('delete from journal_lines'));db.execute(text('delete from journal_entries'));db.execute(text('delete from journal_sequences'))
      fy27=FiscalYear(company_id=1,name='2027',start_date=date(2027,1,1),end_date=date(2027,12,31),status='OPEN')
      fy27.periods.append(FiscalPeriod(number=4,name_ar='أبريل 2027',name_en='April 2027',start_date=date(2027,4,1),end_date=date(2027,4,30),status='OPEN'))
      db.add(fy27);db.commit()
      ac={x.code:x for x in db.scalars(select(Account).where(Account.company_id==1)).all()}
      create_posted_journal(db,company_id=1,user_id=1,posting_date=date(2026,12,1),reference='RC24-BASE',description='Controlled RC24 tax simulation',lines=[
        {'account_id':ac['111010'].id,'debit':1000000,'credit':0}, {'account_id':ac['411010'].id,'debit':0,'credit':1000000},
        {'account_id':ac['611010'].id,'debit':300000,'credit':0}, {'account_id':ac['111010'].id,'debit':0,'credit':300000},
        {'account_id':ac['151010'].id,'debit':500000,'credit':0}, {'account_id':ac['311010'].id,'debit':0,'credit':500000},
      ]);db.commit()
    profile=ok(c.post('/api/v1/zakat-income-tax/profiles',headers=admin,json={'company_id':1,'zakat_registration_number':'ZAKAT-001','cit_registration_number':'CIT-001','return_basis':'MIXED','saudi_gcc_ownership_percent':60,'non_saudi_ownership_percent':40,'zakat_rate_hijri':2.5,'hijri_year_days':354,'income_tax_rate':20,'tax_loss_utilization_cap_percent':25,'zakat_method':'FINANCING_SOURCES_LESS_DEDUCTIBLE_ASSETS','minimum_zakat_amount':0,'notes':'Controlled test'}),201)
    assert D(profile['saudi_gcc_ownership_percent'])==D(60)
    loss=ok(c.post('/api/v1/zakat-income-tax/losses',headers=admin,json={'company_id':1,'origin_year':2025,'original_amount':100000,'evidence_reference':'ASSESSMENT-2025','notes':'Approved tax loss'}),201)
    ret=ok(c.post('/api/v1/zakat-income-tax/returns',headers=admin,json={'company_id':1,'period_start':'2026-01-01','period_end':'2026-12-31','zakat_credits':100,'cit_credits':4000,'notes':'RC24 annual return'}),201)
    assert str(ret['due_date'])=='2027-04-30' and D(ret['accounting_profit_before_zakat_tax'])==D(700000)
    def adj(payload):
      return ok(c.post(f"/api/v1/zakat-income-tax/returns/{ret['id']}/adjustments",headers=admin,json=payload),201)
    ret=adj({'regime':'CIT','direction':'ADD','code':'NON_DEDUCTIBLE_EXPENSE','description_ar':'مصروف غير جائز','description_en':'Non-deductible expense','amount':50000,'source_account_code':'611010','evidence_reference':'TAX-WP-01','recurring':False})
    ret=adj({'regime':'CIT','direction':'DEDUCT','code':'EXEMPT_INCOME','description_ar':'دخل معفى','description_en':'Exempt income','amount':10000,'source_account_code':'411010','evidence_reference':'TAX-WP-02','recurring':False})
    ret=adj({'regime':'ZAKAT','direction':'ADD','code':'OTHER_FINANCING_SOURCE','description_ar':'مصدر تمويل مضاف','description_en':'Additional financing source','amount':100000,'evidence_reference':'ZAKAT-WP-01','recurring':False})
    ret=adj({'regime':'ZAKAT','direction':'DEDUCT','code':'QUALIFYING_DEDUCTION','description_ar':'حسم زكوي مؤيد','description_en':'Supported zakat deduction','amount':20000,'evidence_reference':'ZAKAT-WP-02','recurring':False})
    assert D(ret['adjusted_taxable_profit'])==D(740000)
    assert D(ret['cit_base_before_losses'])==D(296000)
    assert D(ret['tax_losses_utilized'])==D(74000)
    assert D(ret['income_tax_base'])==D(222000)
    assert D(ret['gross_income_tax'])==D(44400) and D(ret['income_tax_payable'])==D(40400)
    assert D(ret['gross_zakat_base'])==D(80000) and D(ret['zakat_base'])==D(48000)
    expected_rate=D(Decimal('2.5')*Decimal(365)/Decimal(354));assert D(ret['zakat_rate'])==expected_rate
    assert D(ret['gross_zakat'])==D(Decimal('48000')*Decimal(str(ret['zakat_rate']))/Decimal(100))
    ok(c.post(f"/api/v1/zakat-income-tax/returns/{ret['id']}/submit",headers=admin))
    assert c.post(f"/api/v1/zakat-income-tax/returns/{ret['id']}/approve-post",headers=admin).status_code==409
    ret=ok(c.post(f"/api/v1/zakat-income-tax/returns/{ret['id']}/approve-post",headers=approver));assert ret['status']=='APPROVED' and D(ret['reconciliation_difference'])==0 and ret['accrual_journal_id']
    banks=ok(c.get('/api/v1/subledgers/bank-accounts?company_id=1',headers=admin));bank=banks[0]
    ret=ok(c.post(f"/api/v1/zakat-income-tax/returns/{ret['id']}/pay",headers=admin,json={'bank_account_id':bank['id'],'payment_date':'2027-04-15','sadad_invoice_number':'SADAD-ZT-2026','payment_reference':'PAY-ZT-2026'}));assert ret['status']=='PAID' and D(ret['gl_payable'])==0 and D(ret['reconciliation_difference'])==0
    losses=ok(c.get('/api/v1/zakat-income-tax/losses?company_id=1',headers=admin));assert D(losses[0]['utilized_amount'])==D(74000) and D(losses[0]['available_amount'])==D(26000)
    csv1=c.get('/api/v1/zakat-income-tax/export/returns.csv?company_id=1',headers=admin);assert csv1.status_code==200 and csv1.content.startswith(b'\xef\xbb\xbf') and b'SADAD' not in csv1.content
    csv2=c.get('/api/v1/zakat-income-tax/export/adjustments.csv?company_id=1',headers=admin);assert csv2.status_code==200 and b'NON_DEDUCTIBLE_EXPENSE' in csv2.content
    with SessionLocal() as db:
      row=db.get(ZakatIncomeTaxReturn,ret['id']);assert row and row.payment_journal_id
      l=db.scalar(select(TaxLossCarryforward).where(TaxLossCarryforward.company_id==1));assert D(l.utilized_amount)==D(74000)
      assert not db.execute(select(JournalEntry.id).where(JournalEntry.total_debit!=JournalEntry.total_credit)).all()
      assert not db.execute(text('PRAGMA foreign_key_check')).all()
  print('CORVAX v1.0 RC24 zakat and CIT: ALL VERIFICATIONS PASSED')
  DB_PATH.unlink(missing_ok=True)
if __name__=='__main__':main()
