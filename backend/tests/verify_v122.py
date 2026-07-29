"""CORVAX RC22 Saudi withholding tax engine verification."""
from __future__ import annotations
import os, sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_DIR))
DB_PATH=Path('/tmp')/'verify_v122.db';DB_PATH.unlink(missing_ok=True)
os.environ.update({'DATABASE_URL':f'sqlite:///{DB_PATH}','SECRET_KEY':'verification-secret-key-corvax-rc22-withholding','SEED_DEMO_DATA':'true','AUTO_CREATE_SCHEMA':'true','TRUSTED_HOSTS':'testserver,localhost,127.0.0.1','APP_VERSION':'1.0.0-agreement-completion-rc27.4','ENABLE_RATE_LIMIT_TESTING':'true'})
from fastapi.testclient import TestClient
from sqlalchemy import select,func,text
from app.db import SessionLocal
from app.main import app
from app.models import Account,JournalEntry,JournalLine,Payment,WithholdingTaxTransaction

def D(v):return Decimal(str(v)).quantize(Decimal('0.01'))
def ok(r,status=200):assert r.status_code==status,r.text;return r.json()

def main():
  with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'}));admin={'Authorization':f"Bearer {login['access_token']}"}
    assert ok(c.get('/health'))['version']=='1.0.0-agreement-completion-rc27.4'
    ok(c.post('/api/v1/admin/users',headers=admin,json={'name_ar':'مراجع الاستقطاع','name_en':'WHT Approver','email':'rc22.approver@corvaxplatform.com','password':'Rc22Approver@123','require_password_change':False,'memberships':[{'company_id':1,'role_code':'SUPER_ADMIN'}]}),201)
    al=ok(c.post('/api/v1/auth/login',json={'email':'rc22.approver@corvaxplatform.com','password':'Rc22Approver@123'}));approver={'Authorization':f"Bearer {al['access_token']}"}
    parties=ok(c.get('/api/v1/subledgers/parties?company_id=1&party_type=SUPPLIER',headers=admin));supplier=parties[0]
    banks=ok(c.get('/api/v1/subledgers/bank-accounts?company_id=1',headers=admin));bank=banks[0]
    cats=ok(c.get('/api/v1/withholding-tax/categories?company_id=1',headers=admin));tech=next(x for x in cats if x['code']=='TECHNICAL_CONSULTING');other=next(x for x in cats if x['code']=='OTHER_KSA_SOURCE_SERVICES')
    profile=ok(c.post('/api/v1/withholding-tax/beneficiaries',headers=admin,json={'company_id':1,'party_id':supplier['id'],'country_code':'ARE','tax_residency_country':'ARE','foreign_tax_id':'AE-TRN-7788','non_resident':True,'permanent_establishment_in_ksa':False,'related_party':False,'beneficial_owner_confirmed':True,'treaty_country_code':'ARE','residency_certificate_number':'TRC-AE-2026','residency_certificate_expiry':'2026-12-31'}),201)
    pi=ok(c.post('/api/v1/subledgers/purchase-invoices',headers=admin,json={'company_id':1,'invoice_date':'2026-07-10','due_date':'2026-07-31','supplier_id':supplier['id'],'supplier_invoice_number':'UAE-CONS-100','lines':[{'description':'Technical consulting services','account_code':'613010','quantity':1,'unit_price':100000,'tax_code':'PFOR0'}]}),201)
    ok(c.post(f"/api/v1/subledgers/purchase-invoices/{pi['id']}/post",headers=admin))
    tx=ok(c.post('/api/v1/withholding-tax/transactions',headers=admin,json={'company_id':1,'payment_date':'2026-07-15','beneficiary_profile_id':profile['id'],'category_id':tech['id'],'amount':100000,'bank_account_id':bank['id'],'purchase_invoice_id':pi['id'],'gross_up':False,'source_in_ksa':True,'dta_relief_method':'STATUTORY','description':'Technical consulting payment','reference':'WIRE-TECH-01'}),201)
    assert D(tx['withholding_amount'])==D(5000) and D(tx['net_cash_amount'])==D(95000) and D(tx['applied_rate'])==D(5)
    ok(c.post(f"/api/v1/withholding-tax/transactions/{tx['id']}/submit",headers=admin))
    assert c.post(f"/api/v1/withholding-tax/transactions/{tx['id']}/approve-post",headers=admin).status_code==409
    tx=ok(c.post(f"/api/v1/withholding-tax/transactions/{tx['id']}/approve-post",headers=approver));assert tx['status']=='APPROVED_POSTED'
    aging=ok(c.get('/api/v1/subledgers/aging?company_id=1&ledger_type=AP&as_of_date=2026-07-15',headers=admin));assert D(aging['gross_open_items'])==0
    with SessionLocal() as db:
      payment=db.get(Payment,tx['payment_id']);assert D(payment.amount)==D(100000) and D(payment.net_cash_amount)==D(95000) and D(payment.withholding_tax_amount)==D(5000)
      wht_account=db.scalar(select(Account).where(Account.company_id==1,Account.code=='218010'))
      credit=db.scalar(select(func.coalesce(func.sum(JournalLine.credit),0)).where(JournalLine.journal_id==tx['journal_id'],JournalLine.account_id==wht_account.id));assert D(credit)==D(5000)
    # Direct treaty relief is blocked without a valid approval reference.
    blocked=c.post('/api/v1/withholding-tax/transactions',headers=admin,json={'company_id':1,'payment_date':'2026-07-16','beneficiary_profile_id':profile['id'],'category_id':other['id'],'amount':20000,'bank_account_id':bank['id'],'debit_account_code':'613010','source_in_ksa':True,'dta_relief_method':'DIRECT_RELIEF','treaty_rate':3,'dta_reference':'MISSING','description':'Other service treaty payment'})
    assert blocked.status_code==422
    profile=ok(c.post('/api/v1/withholding-tax/beneficiaries',headers=admin,json={'company_id':1,'party_id':supplier['id'],'country_code':'ARE','tax_residency_country':'ARE','foreign_tax_id':'AE-TRN-7788','non_resident':True,'permanent_establishment_in_ksa':False,'related_party':False,'beneficial_owner_confirmed':True,'treaty_country_code':'ARE','residency_certificate_number':'TRC-AE-2026','residency_certificate_expiry':'2026-12-31','treaty_relief_approval_reference':'ZATCA-DTA-APP-77','treaty_relief_approval_expiry':'2026-12-31'}),201)
    tx2=ok(c.post('/api/v1/withholding-tax/transactions',headers=admin,json={'company_id':1,'payment_date':'2026-07-16','beneficiary_profile_id':profile['id'],'category_id':other['id'],'amount':20000,'bank_account_id':bank['id'],'debit_account_code':'613010','source_in_ksa':True,'dta_relief_method':'DIRECT_RELIEF','treaty_rate':3,'dta_reference':'ZATCA-DTA-APP-77','description':'Other service with approved treaty relief'}),201)
    assert D(tx2['withholding_amount'])==D(600) and D(tx2['statutory_rate'])==D(15) and D(tx2['applied_rate'])==D(3)
    ok(c.post(f"/api/v1/withholding-tax/transactions/{tx2['id']}/submit",headers=admin));ok(c.post(f"/api/v1/withholding-tax/transactions/{tx2['id']}/approve-post",headers=approver))
    ret=ok(c.post('/api/v1/withholding-tax/returns',headers=admin,json={'company_id':1,'period_start':'2026-07-01','period_end':'2026-07-31'}),201)
    assert D(ret['gross_payments'])==D(120000) and D(ret['tax_withheld'])==D(5600) and D(ret['reconciliation_difference'])==0 and str(ret['due_date'])=='2026-08-10'
    ok(c.post(f"/api/v1/withholding-tax/returns/{ret['id']}/submit",headers=admin))
    assert c.post(f"/api/v1/withholding-tax/returns/{ret['id']}/approve",headers=admin).status_code==409
    ret=ok(c.post(f"/api/v1/withholding-tax/returns/{ret['id']}/approve",headers=approver));assert ret['status']=='APPROVED'
    before=ok(c.get(f"/api/v1/withholding-tax/transactions/{tx['id']}/certificate",headers=admin));assert not before['eligible']
    ret=ok(c.post(f"/api/v1/withholding-tax/returns/{ret['id']}/pay",headers=admin,json={'bank_account_id':bank['id'],'payment_date':'2026-07-31','sadad_invoice_number':'SADAD-WHT-202607','payment_reference':'BANK-WHT-5600'}));assert ret['status']=='PAID'
    cert=ok(c.get(f"/api/v1/withholding-tax/transactions/{tx['id']}/certificate",headers=admin));assert cert['eligible'] and cert['return_number']==ret['number'] and D(cert['tax_withheld'])==D(5000)
    csv1=c.get('/api/v1/withholding-tax/export/transactions.csv?company_id=1',headers=admin);assert csv1.status_code==200 and csv1.content.startswith(b'\xef\xbb\xbf') and b'TECHNICAL_CONSULTING' in csv1.content
    csv2=c.get('/api/v1/withholding-tax/export/returns.csv?company_id=1',headers=admin);assert csv2.status_code==200 and b'SADAD-WHT-202607' in csv2.content
    with SessionLocal() as db:
      assert not db.execute(select(JournalEntry.id).where(JournalEntry.total_debit!=JournalEntry.total_credit)).all()
      assert not db.execute(text('PRAGMA foreign_key_check')).all()
  print('CORVAX v1.0 RC22 withholding tax: ALL VERIFICATIONS PASSED')
  DB_PATH.unlink(missing_ok=True)
if __name__=='__main__':main()
