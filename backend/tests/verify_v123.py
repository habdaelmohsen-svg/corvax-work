"""CORVAX RC23 Saudi excise tax engine verification."""
from __future__ import annotations
import os, sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_DIR))
DB_PATH=Path('/tmp')/'verify_v123.db';DB_PATH.unlink(missing_ok=True)
os.environ.update({'DATABASE_URL':f'sqlite:///{DB_PATH}','SECRET_KEY':'verification-secret-key-corvax-rc23-excise','SEED_DEMO_DATA':'true','AUTO_CREATE_SCHEMA':'true','TRUSTED_HOSTS':'testserver,localhost,127.0.0.1','APP_VERSION':'1.0.0-agreement-completion-rc27.4-r9.3','ENABLE_RATE_LIMIT_TESTING':'true'})
from fastapi.testclient import TestClient
from sqlalchemy import select,func,text
from app.db import SessionLocal
from app.main import app
from app.models import Account,ExciseMovement,ExciseTaxReturn,JournalEntry,JournalLine

def D(v):return Decimal(str(v)).quantize(Decimal('0.01'))
def ok(r,status=200):assert r.status_code==status,r.text;return r.json()

def main():
  with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'}));admin={'Authorization':f"Bearer {login['access_token']}"}
    assert ok(c.get('/health'))['version']=='1.0.0-agreement-completion-rc27.4-r9.3'
    ok(c.post('/api/v1/admin/users',headers=admin,json={'name_ar':'مراجع الانتقائية','name_en':'Excise Approver','email':'rc23.approver@corvaxplatform.com','password':'Rc23Approver@123','require_password_change':False,'memberships':[{'company_id':1,'role_code':'SUPER_ADMIN'}]}),201)
    al=ok(c.post('/api/v1/auth/login',json={'email':'rc23.approver@corvaxplatform.com','password':'Rc23Approver@123'}));approver={'Authorization':f"Bearer {al['access_token']}"}
    with SessionLocal() as db:
      db.execute(text("update fiscal_periods set status='OPEN'"));db.commit()
    wh1=ok(c.post('/api/v1/inventory/warehouses',headers=admin,json={'company_id':1,'code':'EXW-A','name_ar':'مستودع انتقائي أ','name_en':'Excise Warehouse A','warehouse_type':'TAX_WAREHOUSE'}),201)
    wh2=ok(c.post('/api/v1/inventory/warehouses',headers=admin,json={'company_id':1,'code':'EXW-B','name_ar':'مستودع انتقائي ب','name_en':'Excise Warehouse B','warehouse_type':'TAX_WAREHOUSE'}),201)
    p1=ok(c.post('/api/v1/excise-tax/warehouse-profiles',headers=admin,json={'company_id':1,'warehouse_id':wh1['id'],'license_number':'EX-LIC-A-2026','license_start_date':'2026-07-01','license_expiry_date':'2026-12-31','permitted_activities':'PRODUCE,STORE,RECEIVE,SEND','bank_guarantee_amount':50000,'estimated_monthly_excise_value':500000}),201)
    p2=ok(c.post('/api/v1/excise-tax/warehouse-profiles',headers=admin,json={'company_id':1,'warehouse_id':wh2['id'],'license_number':'EX-LIC-B-2026','license_start_date':'2026-07-01','license_expiry_date':'2026-12-31','permitted_activities':'STORE,RECEIVE,SEND','bank_guarantee_amount':10000,'estimated_monthly_excise_value':100000}),201)
    assert p1['guarantee_indicator_sufficient'] and p2['guarantee_indicator_sufficient']
    item=ok(c.post('/api/v1/inventory/items',headers=admin,json={'company_id':1,'code':'SODA-330','name_ar':'مشروب غازي 330 مل','name_en':'Soft Drink 330ml','item_type':'FINISHED_GOOD','uom':'EA','standard_cost':5,'reorder_level':10}),201)
    cats=ok(c.get('/api/v1/excise-tax/categories?company_id=1',headers=admin));soft=next(x for x in cats if x['code']=='SOFT_DRINK');energy=next(x for x in cats if x['code']=='ENERGY_DRINK')
    assert D(soft['statutory_rate'])==D(50) and D(energy['statutory_rate'])==D(100)
    product=ok(c.post('/api/v1/excise-tax/products',headers=admin,json={'company_id':1,'item_id':item['id'],'category_id':soft['id'],'hs_code':'220210','zatca_registration_reference':'EX-PROD-001','registered_retail_price':20,'indicative_price':18,'package_quantity':1,'package_uom':'EA'}),201)
    assert D(product['taxable_unit_value'])==D(20)
    banks=ok(c.get('/api/v1/subledgers/bank-accounts?company_id=1',headers=admin));bank=banks[0]
    def movement(payload):
      x=ok(c.post('/api/v1/excise-tax/movements',headers=admin,json=payload),201);ok(c.post(f"/api/v1/excise-tax/movements/{x['id']}/submit",headers=admin));assert c.post(f"/api/v1/excise-tax/movements/{x['id']}/approve-post",headers=admin).status_code==409;return ok(c.post(f"/api/v1/excise-tax/movements/{x['id']}/approve-post",headers=approver))
    prod=movement({'company_id':1,'movement_date':'2026-07-05','event_type':'PRODUCTION','product_id':product['id'],'warehouse_profile_id':p1['id'],'quantity':1000,'tax_settlement_method':'SUSPENDED','description':'Production into tax suspension'})
    assert D(prod['excise_amount'])==0 and prod['journal_id'] is None
    tr=movement({'company_id':1,'movement_date':'2026-07-10','event_type':'TRANSFER_SUSPENDED','product_id':product['id'],'warehouse_profile_id':p1['id'],'destination_warehouse_profile_id':p2['id'],'quantity':100,'tax_settlement_method':'SUSPENDED','description':'Suspended transfer between licensed warehouses'})
    assert tr['journal_id'] is None
    rel=movement({'company_id':1,'movement_date':'2026-07-20','event_type':'RELEASE_CONSUMPTION','product_id':product['id'],'warehouse_profile_id':p1['id'],'quantity':200,'tax_settlement_method':'PAYABLE','debit_account_code':'624120','description':'Release soft drinks for local consumption'})
    assert D(rel['taxable_value'])==D(4000) and D(rel['excise_amount'])==D(2000) and rel['journal_id']
    imp=movement({'company_id':1,'movement_date':'2026-08-05','event_type':'IMPORT_RECEIPT','product_id':product['id'],'warehouse_profile_id':p1['id'],'quantity':50,'tax_settlement_method':'CUSTOMS_PAID','customs_declaration_number':'CD-EX-2026-01','customs_excise_paid':500,'debit_account_code':'113010','bank_account_id':bank['id'],'description':'Imported soft drinks with excise paid at customs'})
    assert D(imp['excise_amount'])==D(500) and D(imp['customs_excise_paid'])==D(500) and imp['journal_id']
    stock=ok(c.get('/api/v1/excise-tax/stock?company_id=1&as_of=2026-08-31',headers=admin));rows={x['warehouse_code']:x for x in stock['rows']};assert D(rows['EXW-A']['quantity'])==D(750) and D(rows['EXW-B']['quantity'])==D(100)
    insufficient=c.post('/api/v1/excise-tax/movements',headers=admin,json={'company_id':1,'movement_date':'2026-08-20','event_type':'RELEASE_CONSUMPTION','product_id':product['id'],'warehouse_profile_id':p2['id'],'quantity':101,'tax_settlement_method':'PAYABLE','debit_account_code':'624120','description':'Attempt excessive release'});assert insufficient.status_code==201
    ix=insufficient.json();ok(c.post(f"/api/v1/excise-tax/movements/{ix['id']}/submit",headers=admin));assert c.post(f"/api/v1/excise-tax/movements/{ix['id']}/approve-post",headers=approver).status_code==409
    ret=ok(c.post('/api/v1/excise-tax/returns',headers=admin,json={'company_id':1,'period_start':'2026-07-01','period_end':'2026-08-31'}),201)
    assert D(ret['taxable_value'])==D(5000) and D(ret['gross_excise'])==D(2500) and D(ret['customs_paid'])==D(500) and D(ret['tax_payable'])==D(2000) and D(ret['reconciliation_difference'])==0 and str(ret['due_date'])=='2026-09-30'
    ok(c.post(f"/api/v1/excise-tax/returns/{ret['id']}/submit",headers=admin));assert c.post(f"/api/v1/excise-tax/returns/{ret['id']}/approve",headers=admin).status_code==409;ret=ok(c.post(f"/api/v1/excise-tax/returns/{ret['id']}/approve",headers=approver));assert ret['status']=='APPROVED'
    ret=ok(c.post(f"/api/v1/excise-tax/returns/{ret['id']}/pay",headers=admin,json={'bank_account_id':bank['id'],'payment_date':'2026-09-10','sadad_invoice_number':'SADAD-EX-20260708','payment_reference':'BANK-EX-2000'}));assert ret['status']=='PAID'
    csv1=c.get('/api/v1/excise-tax/export/movements.csv?company_id=1',headers=admin);assert csv1.status_code==200 and csv1.content.startswith(b'\xef\xbb\xbf') and b'RELEASE_CONSUMPTION' in csv1.content
    csv2=c.get('/api/v1/excise-tax/export/returns.csv?company_id=1',headers=admin);assert csv2.status_code==200 and b'SADAD-EX-20260708' in csv2.content
    csv3=c.get('/api/v1/excise-tax/export/stock.csv?company_id=1&as_of=2026-08-31',headers=admin);assert csv3.status_code==200 and b'EXW-A' in csv3.content
    with SessionLocal() as db:
      liability=db.scalar(select(Account).where(Account.company_id==1,Account.code=='218020'));assert liability
      release=db.get(ExciseMovement,rel['id']);credit=db.scalar(select(func.coalesce(func.sum(JournalLine.credit),0)).where(JournalLine.journal_id==release.journal_id,JournalLine.account_id==liability.id));assert D(credit)==D(2000)
      assert not db.execute(select(JournalEntry.id).where(JournalEntry.total_debit!=JournalEntry.total_credit)).all()
      assert not db.execute(text('PRAGMA foreign_key_check')).all()
  print('CORVAX v1.0 RC23 excise tax: ALL VERIFICATIONS PASSED')
  DB_PATH.unlink(missing_ok=True)
if __name__=='__main__':main()
