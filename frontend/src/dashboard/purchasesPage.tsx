import {useEffect, useState} from 'react';
import {ShoppingCart, ReceiptText, Wallet, CheckCircle2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type Party={id:number;code:string;name_ar:string;name_en:string;party_type:string};
type Bank={id:number;bank_name_ar?:string;name_ar?:string};
type Invoice={id:number;number?:string;invoice_date:string;supplier_name_ar?:string;supplier_name_en?:string;supplier_invoice_number?:string;total?:number;status:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const addDays=(n:number)=>{const d=new Date();d.setDate(d.getDate()+n);return iso(d);};

export function PurchasesPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [summary,setSummary]=useState<any>(null);
  const [suppliers,setSuppliers]=useState<Party[]>([]);
  const [banks,setBanks]=useState<Bank[]>([]);
  const [invoices,setInvoices]=useState<Invoice[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // invoice form
  const [supplier,setSupplier]=useState(''); const [invDate,setInvDate]=useState(iso()); const [due,setDue]=useState(addDays(30));
  const [supplierInv,setSupplierInv]=useState(''); const [desc,setDesc]=useState(''); const [qty,setQty]=useState('1'); const [price,setPrice]=useState(''); const [vat,setVat]=useState('15'); const [account,setAccount]=useState('613010');
  // payment form
  const [pSupplier,setPSupplier]=useState(''); const [pBank,setPBank]=useState(''); const [pAmount,setPAmount]=useState('');

  const load=async()=>{
    try{
      const [s,p,b,inv]=await Promise.all([
        json(`/api/v1/subledgers/summary?company_id=${companyId}`),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`),
        json(`/api/v1/subledgers/purchase-invoices?company_id=${companyId}`).catch(()=>[]),
      ]);
      setSummary(s); setSuppliers((p||[]).filter((x:Party)=>x.party_type==='SUPPLIER')); setBanks(b||[]); setInvoices(inv||[]);
      const sup=(p||[]).filter((x:Party)=>x.party_type==='SUPPLIER');
      if(!supplier&&sup.length){setSupplier(String(sup[0].id));setPSupplier(String(sup[0].id));}
      if(!pBank&&b?.length)setPBank(String(b[0].id));
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createInvoice=async()=>{
    if(!supplier||!price){setMessage(ar?'اختر المورد وأدخل السعر':'Select supplier and price');return;}
    setBusy(true);setMessage('');
    try{
      const inv=await json('/api/v1/subledgers/purchase-invoices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,invoice_date:invDate,due_date:due,supplier_id:Number(supplier),supplier_invoice_number:supplierInv||`UI-${Date.now()}`,lines:[{description:desc||'Purchase',account_code:account,quantity:Number(qty),unit_price:Number(price),vat_rate:Number(vat)}]})});
      await json(`/api/v1/subledgers/purchase-invoices/${inv.id}/post`,{method:'POST'});
      setMessage(ar?'تم إنشاء فاتورة الشراء وترحيلها':'Purchase invoice created and posted');setDesc('');setPrice('');setSupplierInv('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createPayment=async()=>{
    if(!pSupplier||!pBank||!pAmount){setMessage(ar?'أكمل بيانات السداد':'Complete payment fields');return;}
    setBusy(true);setMessage('');
    try{await json('/api/v1/subledgers/payments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,payment_date:iso(),supplier_id:Number(pSupplier),bank_account_id:Number(pBank),amount:Number(pAmount),reference:'UI-PAY'})});
      setMessage(ar?'تم تسجيل سند الصرف':'Payment posted');setPAmount('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  return <>
    <div className="kpis">
      <Kpi title={ar?'ذمم الموردين':'Accounts payable'} value={summary?fmt(Number(summary.accounts_payable)):'—'} trend="AP" good icon={<ReceiptText size={22}/>} tone="blue"/>
      <Kpi title={ar?'فواتير الشراء':'Purchase invoices'} value={summary?String(summary.purchase_invoices):'—'} trend="" good icon={<ShoppingCart size={22}/>} tone="green"/>
      <Kpi title={ar?'سندات الصرف':'Payments'} value={summary?String(summary.payments):'—'} trend="" good icon={<Wallet size={22}/>} tone="violet"/>
      <Kpi title={ar?'رصيد البنك':'Bank balance'} value={summary?fmt(Number(summary.cash_balance)):'—'} trend="GL" good icon={<CheckCircle2 size={22}/>} tone="amber"/>
    </div>
    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    <Panel title={ar?'فاتورة شراء جديدة':'New purchase invoice'} icon={<ShoppingCart size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'المورد':'Supplier'}<select style={field} value={supplier} onChange={e=>setSupplier(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{ar?s.name_ar:s.name_en}</option>)}</select></label>
        <label>{ar?'رقم فاتورة المورد':'Supplier invoice #'}<input style={field} value={supplierInv} onChange={e=>setSupplierInv(e.target.value)}/></label>
        <label>{ar?'تاريخ الفاتورة':'Invoice date'}<input type="date" style={field} value={invDate} onChange={e=>setInvDate(e.target.value)}/></label>
        <label>{ar?'تاريخ الاستحقاق':'Due date'}<input type="date" style={field} value={due} onChange={e=>setDue(e.target.value)}/></label>
        <label>{ar?'الوصف':'Description'}<input style={field} value={desc} onChange={e=>setDesc(e.target.value)}/></label>
        <label>{ar?'الكمية':'Quantity'}<input type="number" style={field} value={qty} onChange={e=>setQty(e.target.value)}/></label>
        <label>{ar?'سعر الوحدة':'Unit price'}<input type="number" style={field} value={price} onChange={e=>setPrice(e.target.value)}/></label>
        <label>{ar?'الضريبة %':'VAT %'}<input type="number" style={field} value={vat} onChange={e=>setVat(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createInvoice}>{ar?'إنشاء وترحيل الفاتورة':'Create & post invoice'}</button></div>
    </Panel>

    <Panel title={ar?'سند صرف':'Supplier payment'} icon={<Wallet size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'المورد':'Supplier'}<select style={field} value={pSupplier} onChange={e=>setPSupplier(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{ar?s.name_ar:s.name_en}</option>)}</select></label>
        <label>{ar?'البنك':'Bank'}<select style={field} value={pBank} onChange={e=>setPBank(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{b.bank_name_ar||b.name_ar}</option>)}</select></label>
        <label>{ar?'المبلغ':'Amount'}<input type="number" style={field} value={pAmount} onChange={e=>setPAmount(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createPayment}>{ar?'تسجيل الصرف':'Post payment'}</button></div>
    </Panel>

    <Panel title={ar?'فواتير الشراء':'Purchase invoices'} icon={<ReceiptText size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المورد':'Supplier',ar?'فاتورة المورد':'Supplier inv.',ar?'الإجمالي':'Total',ar?'الحالة':'Status']}
        rows={invoices.map(i=>[i.number||String(i.id),i.invoice_date,ar?(i.supplier_name_ar||'—'):(i.supplier_name_en||'—'),i.supplier_invoice_number||'—',fmt(Number(i.total||0)),i.status])}/>
    </Panel>
  </>;
}
