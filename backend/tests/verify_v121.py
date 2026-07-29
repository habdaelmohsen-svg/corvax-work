"""CORVAX RC21 sales/purchase returns, credit notes and VAT adjustment verification."""
from __future__ import annotations
import os, sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(BACKEND_DIR))
DB_PATH=Path('/tmp')/'verify_v121.db'; DB_PATH.unlink(missing_ok=True)
os.environ.update({
 'DATABASE_URL':f'sqlite:///{DB_PATH}','SECRET_KEY':'verification-secret-key-corvax-rc21-credit-notes',
 'SEED_DEMO_DATA':'true','AUTO_CREATE_SCHEMA':'true','TRUSTED_HOSTS':'testserver,localhost,127.0.0.1',
 'APP_VERSION':'1.0.0-agreement-completion-rc27.4','ENABLE_RATE_LIMIT_TESTING':'true',
})
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.db import SessionLocal
from app.main import app
from app.models import Account, FiscalPeriod, Item, Party, StockMovement, Warehouse, JournalEntry, JournalLine, PartyCreditBalance
from app.services.posting import create_posted_journal

def D(v): return Decimal(str(v)).quantize(Decimal('0.01'))
def ok(r,status=200): assert r.status_code==status,r.text; return r.json()

def main():
  with TestClient(app) as c:
    login=ok(c.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'})); admin={'Authorization':f"Bearer {login['access_token']}"}
    assert ok(c.get('/health'))['version']=='1.0.0-agreement-completion-rc27.4'
    u=ok(c.post('/api/v1/admin/users',headers=admin,json={'name_ar':'مراجع مرتجعات','name_en':'Returns Approver','email':'rc21.approver@corvaxplatform.com','password':'Rc21Approver@123','require_password_change':False,'memberships':[{'company_id':1,'role_code':'SUPER_ADMIN'}]}),201)
    al=ok(c.post('/api/v1/auth/login',json={'email':'rc21.approver@corvaxplatform.com','password':'Rc21Approver@123'})); approver={'Authorization':f"Bearer {al['access_token']}"}
    with SessionLocal() as db:
      for p in db.query(FiscalPeriod).all(): p.status='OPEN'
      customer=db.scalar(select(Party).where(Party.company_id==1,Party.party_type.in_(['CUSTOMER','BOTH'])))
      supplier=db.scalar(select(Party).where(Party.company_id==1,Party.party_type.in_(['SUPPLIER','BOTH'])))
      wh=db.scalar(select(Warehouse).where(Warehouse.company_id==1))
      inv=db.scalar(select(Account).where(Account.company_id==1,Account.code=='113010')); cogs=db.scalar(select(Account).where(Account.company_id==1,Account.code=='511010')); rev=db.scalar(select(Account).where(Account.company_id==1,Account.code=='411010'))
      item=Item(company_id=1,code='RC21-ITEM',name_ar='صنف مرتجعات',name_en='Returns item',item_type='INVENTORY',uom='EA',standard_cost=120,inventory_account_id=inv.id,cogs_account_id=cogs.id,revenue_account_id=rev.id)
      db.add(item);db.flush()
      customer_id,supplier_id,wh_id,item_id=customer.id,supplier.id,wh.id,item.id
      bank_id=db.execute(select(__import__('app.models',fromlist=['BankAccount']).BankAccount.id).where(__import__('app.models',fromlist=['BankAccount']).BankAccount.company_id==1)).scalar_one()
      db.commit()

    # July sales invoice, then August partial and final credit notes.
    si=ok(c.post('/api/v1/subledgers/sales-invoices',headers=admin,json={'company_id':1,'invoice_date':'2026-07-10','due_date':'2026-08-10','customer_id':customer_id,'reference':'RC21-SALE','lines':[{'description':'10 units','account_code':'411010','quantity':10,'unit_price':100,'tax_code':'S15'}]}),201)
    ok(c.post(f"/api/v1/subledgers/sales-invoices/{si['id']}/post",headers=admin))
    eligible_sales=ok(c.get('/api/v1/credit-notes/eligible-invoices?company_id=1&note_type=SALES',headers=admin))
    eligible_invoice=next(x for x in eligible_sales if x['id']==si['id'])
    assert eligible_invoice['lines'] and D(eligible_invoice['lines'][0]['remaining_quantity'])==Decimal('10.00')
    with SessionLocal() as db:
      line_id=db.execute(select(__import__('app.models',fromlist=['SalesInvoiceLine']).SalesInvoiceLine.id).where(__import__('app.models',fromlist=['SalesInvoiceLine']).SalesInvoiceLine.invoice_id==si['id'])).scalar_one()
    scn1=ok(c.post('/api/v1/credit-notes',headers=admin,json={'company_id':1,'note_type':'SALES','note_date':'2026-08-05','original_invoice_id':si['id'],'reason_code':'RETURN','reason':'Partial customer return','lines':[{'original_line_id':line_id,'quantity':4,'item_id':item_id,'warehouse_id':wh_id,'inventory_disposition':'RETURN_TO_STOCK'}]}),201)
    assert D(scn1['subtotal'])==D(400) and D(scn1['vat_amount'])==D(60) and D(scn1['total'])==D(460)
    ok(c.post(f"/api/v1/credit-notes/documents/{scn1['id']}/submit",headers=admin))
    assert c.post(f"/api/v1/credit-notes/documents/{scn1['id']}/approve-post",headers=admin).status_code==409
    scn1=ok(c.post(f"/api/v1/credit-notes/documents/{scn1['id']}/approve-post",headers=approver))
    assert scn1['status']=='APPROVED_POSTED' and D(scn1['unapplied_credit'])==0
    aging=ok(c.get('/api/v1/subledgers/aging?company_id=1&ledger_type=AR&as_of_date=2026-08-05',headers=admin))
    assert D(aging['gross_open_items'])==D(690) and D(aging['reconciliation_difference'])==0

    # Pay the remaining invoice, then return the remaining units: creates customer credit.
    receipt=ok(c.post('/api/v1/subledgers/receipts',headers=admin,json={'company_id':1,'receipt_date':'2026-08-06','customer_id':customer_id,'bank_account_id':bank_id,'amount':690,'reference':'RC21-RECEIPT','allocations':[{'open_item_id':aging['details'][0]['id'],'amount':690}]}),201)
    scn2=ok(c.post('/api/v1/credit-notes',headers=admin,json={'company_id':1,'note_type':'SALES','note_date':'2026-08-08','original_invoice_id':si['id'],'reason_code':'FINAL_RETURN','reason':'Remaining customer return','lines':[{'original_line_id':line_id,'quantity':6,'item_id':item_id,'warehouse_id':wh_id,'inventory_disposition':'QUARANTINE'}]}),201)
    ok(c.post(f"/api/v1/credit-notes/documents/{scn2['id']}/submit",headers=admin)); scn2=ok(c.post(f"/api/v1/credit-notes/documents/{scn2['id']}/approve-post",headers=approver))
    assert D(scn2['unapplied_credit'])==D(690)
    credits=ok(c.get('/api/v1/credit-notes/credit-balances/open?company_id=1&ledger_type=AR',headers=admin)); assert len(credits)==1 and D(credits[0]['available_amount'])==D(690)
    cash=ok(c.post(f"/api/v1/credit-notes/credit-balances/{credits[0]['id']}/cash-settle",headers=admin,json={'bank_account_id':bank_id,'amount':690,'settlement_date':'2026-08-09','reference':'RC21-CUSTOMER-REFUND'}))
    assert D(cash['available_amount'])==0
    ar=ok(c.get('/api/v1/subledgers/aging?company_id=1&ledger_type=AR&as_of_date=2026-08-09',headers=admin)); assert D(ar['reconciliation_difference'])==0

    # Correct receipt-first flow: receipt/landed cost capitalizes inventory,
    # while the supplier invoice clears GRNI instead of debiting inventory.
    with SessionLocal() as db:
      accounts={row.code:row for row in db.scalars(select(Account).where(Account.company_id==1)).all()}
      receipt_journal=create_posted_journal(db,company_id=1,user_id=1,posting_date=date(2026,7,12),reference='RC21-GRN-001',description='Receipt plus paid landed cost',lines=[
        {'account_id':accounts['113010'].id,'debit':1200,'credit':0},
        {'account_id':accounts['214010'].id,'debit':0,'credit':1000},
        {'account_id':accounts['111010'].id,'debit':0,'credit':200},
      ])
      db.add(StockMovement(company_id=1,warehouse_id=wh_id,item_id=item_id,movement_date=date(2026,7,12),movement_type='PURCHASE_RECEIPT',quantity=10,unit_cost=120,total_cost=1200,reference_type='GOODS_RECEIPT',reference_id=None,journal_id=receipt_journal.id,created_by=1))
      db.commit()
    pi=ok(c.post('/api/v1/subledgers/purchase-invoices',headers=admin,json={'company_id':1,'invoice_date':'2026-07-12','due_date':'2026-08-12','supplier_id':supplier_id,'supplier_invoice_number':'SUP-RC21-001','lines':[{'description':'10 purchased units','account_code':'214010','quantity':10,'unit_price':100,'tax_code':'P15'}]}),201)
    ppost=ok(c.post(f"/api/v1/subledgers/purchase-invoices/{pi['id']}/post",headers=admin))
    with SessionLocal() as db:
      pline_id=db.execute(select(__import__('app.models',fromlist=['PurchaseInvoiceLine']).PurchaseInvoiceLine.id).where(__import__('app.models',fromlist=['PurchaseInvoiceLine']).PurchaseInvoiceLine.invoice_id==pi['id'])).scalar_one()
    ap_before=ok(c.get('/api/v1/subledgers/aging?company_id=1&ledger_type=AP&as_of_date=2026-08-09',headers=admin))
    pcn=ok(c.post('/api/v1/credit-notes',headers=admin,json={'company_id':1,'note_type':'PURCHASE','note_date':'2026-08-10','original_invoice_id':pi['id'],'reason_code':'SUPPLIER_RETURN','reason':'Return damaged purchase to supplier','external_reference':'SUP-CN-778','lines':[{'original_line_id':pline_id,'quantity':4,'item_id':item_id,'warehouse_id':wh_id,'inventory_disposition':'RETURN_TO_SUPPLIER'}]}),201)
    ok(c.post(f"/api/v1/credit-notes/documents/{pcn['id']}/submit",headers=admin)); pcn=ok(c.post(f"/api/v1/credit-notes/documents/{pcn['id']}/approve-post",headers=approver))
    assert D(pcn['subtotal'])==D(400) and D(pcn['vat_amount'])==D(60) and pcn['external_reference']=='SUP-CN-778'
    ap=ok(c.get('/api/v1/subledgers/aging?company_id=1&ledger_type=AP&as_of_date=2026-08-10',headers=admin)); assert D(ap['gross_open_items'])==D(690) and D(ap['reconciliation_difference'])==D(ap_before['reconciliation_difference'])
    with SessionLocal() as db:
      movement=db.scalar(select(StockMovement).where(StockMovement.reference_type=='CREDIT_NOTE',StockMovement.reference_id==pcn['id']))
      assert D(movement.quantity)==D(-4) and D(movement.total_cost)==D(-480)
      loss=db.scalar(select(func.coalesce(func.sum(JournalLine.debit),0)).join(Account,Account.id==JournalLine.account_id).where(JournalLine.journal_id==pcn['journal_id'],Account.code=='624110'))
      assert D(loss)==D(80)

    # Export credit note reverses the same export box only after approved export evidence.
    export_si=ok(c.post('/api/v1/subledgers/sales-invoices',headers=admin,json={'company_id':1,'invoice_date':'2026-07-20','due_date':'2026-08-20','customer_id':customer_id,'reference':'RC21-EXPORT','lines':[{'description':'Export sale','account_code':'411010','quantity':1,'unit_price':300,'tax_code':'SEX'}]}),201)
    ok(c.post(f"/api/v1/subledgers/sales-invoices/{export_si['id']}/post",headers=admin))
    evidence=ok(c.post('/api/v1/operational-controls/exports/evidence',headers=admin,json={'company_id':1,'sales_invoice_id':export_si['id'],'export_declaration_number':'EXP-RC21-001','export_date':'2026-07-21','destination_country':'BRA','exit_port':'Jeddah','transport_document':'BL-RC21-001','evidence':{'exit_confirmation':True}}),201)
    ok(c.post(f"/api/v1/operational-controls/exports/evidence/{evidence['id']}/submit",headers=admin)); ok(c.post(f"/api/v1/operational-controls/exports/evidence/{evidence['id']}/approve",headers=approver))
    with SessionLocal() as db:
      export_line_id=db.execute(select(__import__('app.models',fromlist=['SalesInvoiceLine']).SalesInvoiceLine.id).where(__import__('app.models',fromlist=['SalesInvoiceLine']).SalesInvoiceLine.invoice_id==export_si['id'])).scalar_one()
    export_cn=ok(c.post('/api/v1/credit-notes',headers=admin,json={'company_id':1,'note_type':'SALES','note_date':'2026-08-11','original_invoice_id':export_si['id'],'reason_code':'EXPORT_CANCEL','reason':'Cancelled export order','lines':[{'original_line_id':export_line_id,'quantity':1,'inventory_disposition':'NONE'}]}),201)
    ok(c.post(f"/api/v1/credit-notes/documents/{export_cn['id']}/submit",headers=admin)); ok(c.post(f"/api/v1/credit-notes/documents/{export_cn['id']}/approve-post",headers=approver))

    # July contains invoices; August contains exact negative adjustments, including a later-period return.
    july=ok(c.post('/api/v1/compliance/vat-return',headers=admin,json={'company_id':1,'period_start':'2026-07-01','period_end':'2026-07-31'}),201)
    jb={x['box_code']:x for x in july['lines']}; assert D(jb['SALES_STANDARD']['tax_amount'])==D(150) and D(jb['PURCHASE_STANDARD']['tax_amount'])==D(150) and D(jb['SALES_EXPORT']['base_amount'])==D(300)
    aug=ok(c.post('/api/v1/compliance/vat-return',headers=admin,json={'company_id':1,'period_start':'2026-08-01','period_end':'2026-08-31'}),201)
    ab={x['box_code']:x for x in aug['lines']}
    assert D(ab['SALES_STANDARD']['base_amount'])==D(-1000) and D(ab['SALES_STANDARD']['tax_amount'])==D(-150)
    assert D(ab['PURCHASE_STANDARD']['base_amount'])==D(-400) and D(ab['PURCHASE_STANDARD']['tax_amount'])==D(-60)
    assert D(ab['SALES_EXPORT']['base_amount'])==D(-300)
    assert D(aug['output_reconciliation_difference'])==0 and D(aug['input_reconciliation_difference'])==0
    z=ok(c.get(f"/api/v1/credit-notes/documents/{scn1['id']}/zatca-document",headers=admin)); assert z['document_type_code']=='381' and z['billing_reference']['invoice_number']==si['number']
    csvr=c.get('/api/v1/credit-notes/export/csv?company_id=1',headers=admin); assert csvr.status_code==200 and csvr.content.startswith(b'\xef\xbb\xbf') and b'SUP-CN-778' in csvr.content

    # All journals remain balanced and FK integrity is intact.
    with SessionLocal() as db:
      bad=db.execute(select(JournalEntry.id).where(JournalEntry.total_debit!=JournalEntry.total_credit)).all(); assert not bad
      fk=db.execute(__import__('sqlalchemy').text('PRAGMA foreign_key_check')).all(); assert not fk
  print('CORVAX v1.0 RC21 credit notes and VAT adjustments: ALL VERIFICATIONS PASSED')
  DB_PATH.unlink(missing_ok=True)
if __name__=='__main__': main()
