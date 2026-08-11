import {useEffect, useState} from 'react';
import {BadgeDollarSign, ReceiptText, Wallet, CheckCircle2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';
import {SalesCommissionsTab} from './salesCommissionsTab';

type Party={id:number;code:string;name_ar:string;name_en:string;party_type:string};
type Bank={id:number;code?:string;bank_name_ar?:string;name_ar?:string;gl_account_code?:string};
type Invoice={id:number;number?:string;invoice_date:string;customer_name_ar?:string;customer_name_en?:string;total?:number;subtotal?:number;vat_amount?:number;status:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const addDays=(n:number)=>{const d=new Date();d.setDate(d.getDate()+n);return iso(d);};

export function SalesPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [mainTab,setMainTab]=useState<'sales'|'commissions'>('sales');
  const [summary,setSummary]=useState<any>(null);
  const [customers,setCustomers]=useState<Party[]>([]);
  const [banks,setBanks]=useState<Bank[]>([]);
  const [invoices,setInvoices]=useState<Invoice[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // invoice form
  const [customer,setCustomer]=useState(''); const [invDate,setInvDate]=useState(iso()); const [due,setDue]=useState(addDays(30));
  const [desc,setDesc]=useState(''); const [qty,setQty]=useState('1'); const [price,setPrice]=useState(''); const [vat,setVat]=useState('15');
  // receipt form
  const [rCustomer,setRCustomer]=useState(''); const [rBank,setRBank]=useState(''); const [rAmount,setRAmount]=useState('');

  const load=async()=>{
    try{
      const [s,p,b,inv]=await Promise.all([
        json(`/api/v1/subledgers/summary?company_id=${companyId}`),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`),
        json(`/api/v1/subledgers/sales-invoices?company_id=${companyId}`).catch(()=>[]),
      ]);
      setSummary(s); setCustomers((p||[]).filter((x:Party)=>x.party_type==='CUSTOMER')); setBanks(b||[]); setInvoices(inv||[]);
      const c=(p||[]).filter((x:Party)=>x.party_type==='CUSTOMER');
      if(!customer&&c.length){setCustomer(String(c[0].id));setRCustomer(String(c[0].id));}
      if(!rBank&&b?.length)setRBank(String(b[0].id));
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createInvoice=async()=>{
    if(!customer||!price){setMessage(ar?'اختر العميل وأدخل السعر':'Select customer and price');return;}
    setBusy(true);setMessage('');
    try{
      const inv=await json('/api/v1/subledgers/sales-invoices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,invoice_date:invDate,due_date:due,customer_id:Number(customer),reference:'UI-SALE',lines:[{description:desc||'Sale',account_code:'411010',quantity:Number(qty),unit_price:Number(price),vat_rate:Number(vat)}]})});
      await json(`/api/v1/subledgers/sales-invoices/${inv.id}/post`,{method:'POST'});
      setMessage(ar?'تم إنشاء فاتورة البيع وترحيلها':'Sales invoice created and posted');setDesc('');setPrice('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createReceipt=async()=>{
    if(!rCustomer||!rBank||!rAmount){setMessage(ar?'أكمل بيانات القبض':'Complete receipt fields');return;}
    setBusy(true);setMessage('');
    try{await json('/api/v1/subledgers/receipts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,receipt_date:iso(),customer_id:Number(rCustomer),bank_account_id:Number(rBank),amount:Number(rAmount),reference:'UI-RCPT'})});
      setMessage(ar?'تم تسجيل سند القبض':'Receipt posted');setRAmount('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const _tabBtn=(k:'sales'|'commissions',l:string)=>(<button key={k} onClick={()=>setMainTab(k)} style={{padding:'9px 16px',borderRadius:9,border:'1px solid var(--border)',background:mainTab===k?'var(--accent, #1e40af)':'transparent',color:mainTab===k?'#fff':'var(--text)',cursor:'pointer',fontWeight:600}}>{l}</button>);
  if(mainTab==='commissions'){
    return <>
      <div style={{display:'flex',gap:8,margin:'4px 0 14px'}}>{_tabBtn('sales',ar?'المبيعات':'Sales')}{_tabBtn('commissions',ar?'العمولات':'Commissions')}</div>
      <SalesCommissionsTab ar={ar} companyId={companyId}/>
    </>;
  }
  return <>
    <div style={{display:'flex',gap:8,margin:'4px 0 14px'}}>{_tabBtn('sales',ar?'المبيعات':'Sales')}{_tabBtn('commissions',ar?'العمولات':'Commissions')}</div>
    <div className="kpis">
      <Kpi title={ar?'ذمم العملاء':'Accounts receivable'} value={summary?fmt(Number(summary.accounts_receivable)):'—'} trend="AR" good icon={<ReceiptText size={22}/>} tone="blue"/>
      <Kpi title={ar?'فواتير البيع':'Sales invoices'} value={summary?String(summary.sales_invoices):'—'} trend="" good icon={<BadgeDollarSign size={22}/>} tone="green"/>
      <Kpi title={ar?'سندات القبض':'Receipts'} value={summary?String(summary.receipts):'—'} trend="" good icon={<Wallet size={22}/>} tone="violet"/>
      <Kpi title={ar?'رصيد البنك':'Bank balance'} value={summary?fmt(Number(summary.cash_balance)):'—'} trend="GL" good icon={<CheckCircle2 size={22}/>} tone="amber"/>
    </div>
    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    <Panel title={ar?'فاتورة بيع جديدة':'New sales invoice'} icon={<BadgeDollarSign size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'العميل':'Customer'}<select style={field} value={customer} onChange={e=>setCustomer(e.target.value)}>{customers.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
        <label>{ar?'تاريخ الفاتورة':'Invoice date'}<input type="date" style={field} value={invDate} onChange={e=>setInvDate(e.target.value)}/></label>
        <label>{ar?'تاريخ الاستحقاق':'Due date'}<input type="date" style={field} value={due} onChange={e=>setDue(e.target.value)}/></label>
        <label>{ar?'الوصف':'Description'}<input style={field} value={desc} onChange={e=>setDesc(e.target.value)}/></label>
        <label>{ar?'الكمية':'Quantity'}<input type="number" style={field} value={qty} onChange={e=>setQty(e.target.value)}/></label>
        <label>{ar?'سعر الوحدة':'Unit price'}<input type="number" style={field} value={price} onChange={e=>setPrice(e.target.value)}/></label>
        <label>{ar?'الضريبة %':'VAT %'}<input type="number" style={field} value={vat} onChange={e=>setVat(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createInvoice}>{ar?'إنشاء وترحيل الفاتورة':'Create & post invoice'}</button></div>
    </Panel>

    <Panel title={ar?'سند قبض':'Customer receipt'} icon={<Wallet size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'العميل':'Customer'}<select style={field} value={rCustomer} onChange={e=>setRCustomer(e.target.value)}>{customers.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
        <label>{ar?'البنك':'Bank'}<select style={field} value={rBank} onChange={e=>setRBank(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{ar?(b.bank_name_ar||b.name_ar):(b.bank_name_ar||b.name_ar)}</option>)}</select></label>
        <label>{ar?'المبلغ':'Amount'}<input type="number" style={field} value={rAmount} onChange={e=>setRAmount(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createReceipt}>{ar?'تسجيل القبض':'Post receipt'}</button></div>
    </Panel>

    <Panel title={ar?'فواتير البيع':'Sales invoices'} icon={<ReceiptText size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'العميل':'Customer',ar?'الإجمالي':'Total',ar?'الحالة':'Status']}
        rows={invoices.map(i=>[i.number||String(i.id),i.invoice_date,ar?(i.customer_name_ar||'—'):(i.customer_name_en||'—'),fmt(Number(i.total||0)),i.status])}/>
    </Panel>
  </>;
}