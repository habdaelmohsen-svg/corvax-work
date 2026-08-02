import {useEffect, useState} from 'react';
import {BadgeDollarSign, ReceiptText, Wallet, CheckCircle2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';
import {SalesCommissionsTab} from './salesCommissionsTab';

type Party={id:number;code:string;name_ar:string;name_en:string;party_type:string};
type Bank={id:number;code?:string;bank_name_ar?:string;name_ar?:string;gl_account_code?:string};
type Invoice={id:number;number?:string;invoice_date:string;customer_name_ar?:string;customer_name_en?:string;total?:number;subtotal?:number;vat_amount?:number;status:string};
type Receipt={id:number;number:string;receipt_date:string;party_name_ar:string;party_name_en:string;amount:number;allocated_amount:number;unapplied_amount:number;reference:string};
type OpenItem={id:number;document_number:string;due_date:string;party_name_ar?:string;party_name_en?:string;outstanding_amount:number;status:string};

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
  const [receipts,setReceipts]=useState<Receipt[]>([]); const [openItems,setOpenItems]=useState<OpenItem[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // invoice form
  const [customer,setCustomer]=useState(''); const [invDate,setInvDate]=useState(iso()); const [due,setDue]=useState(addDays(30));
  const [desc,setDesc]=useState(''); const [qty,setQty]=useState('1'); const [price,setPrice]=useState(''); const [vat,setVat]=useState('15');
  const [postImmediately,setPostImmediately]=useState(false);
  // receipt form
  const [rCustomer,setRCustomer]=useState(''); const [rBank,setRBank]=useState(''); const [rAmount,setRAmount]=useState('');
  const [receiptDate,setReceiptDate]=useState(iso()); const [receiptRef,setReceiptRef]=useState(''); const [autoAllocate,setAutoAllocate]=useState(true);
  // customer master data
  const [cCode,setCCode]=useState(''); const [cNameAr,setCNameAr]=useState(''); const [cNameEn,setCNameEn]=useState('');
  const [cVat,setCVat]=useState(''); const [cCredit,setCCredit]=useState('0');

  const load=async()=>{
    try{
      const [s,p,b,inv,rcpts,opens]=await Promise.all([
        json(`/api/v1/subledgers/summary?company_id=${companyId}`),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`),
        json(`/api/v1/subledgers/sales-invoices?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/receipts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/open-items?company_id=${companyId}&ledger_type=AR`).catch(()=>[]),
      ]);
      setSummary(s); setCustomers((p||[]).filter((x:Party)=>['CUSTOMER','BOTH'].includes(x.party_type))); setBanks(b||[]); setInvoices(inv||[]);
      setReceipts(rcpts||[]);setOpenItems(opens||[]);
      const c=(p||[]).filter((x:Party)=>['CUSTOMER','BOTH'].includes(x.party_type));
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
      if(postImmediately){await json(`/api/v1/subledgers/sales-invoices/${inv.id}/post`,{method:'POST'});}
      setMessage(postImmediately?(ar?'تم إنشاء فاتورة البيع وترحيلها':'Sales invoice created and posted'):(ar?'حُفظت الفاتورة كمسودة بانتظار المراجعة والترحيل':'Invoice saved as draft for review and posting'));
      setDesc('');setPrice('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const postInvoice=async(id:number)=>{setBusy(true);setMessage('');try{await json(`/api/v1/subledgers/sales-invoices/${id}/post`,{method:'POST'});setMessage(ar?'تم ترحيل الفاتورة وإنشاء القيد والذمة':'Invoice posted; journal and receivable created');await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}};
  const createReceipt=async()=>{
    if(!rCustomer||!rBank||!rAmount){setMessage(ar?'أكمل بيانات القبض':'Complete receipt fields');return;}
    setBusy(true);setMessage('');
    try{const receipt=await json('/api/v1/subledgers/receipts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,receipt_date:receiptDate,customer_id:Number(rCustomer),bank_account_id:Number(rBank),amount:Number(rAmount),reference:receiptRef.trim()||`UI-RCPT-${Date.now()}`})});
      const allocation=autoAllocate?await json(`/api/v1/subledgers/receipts/${receipt.id}/auto-allocate`,{method:'POST'}):receipt;
      setMessage(autoAllocate?(ar?`تم القبض وتخصيص ${fmt(Number(allocation.allocated_amount||0))}؛ غير مخصص ${fmt(Number(allocation.unapplied_amount||0))}`:`Receipt posted; ${fmt(Number(allocation.allocated_amount||0))} allocated, ${fmt(Number(allocation.unapplied_amount||0))} unapplied`):(ar?'تم تسجيل سند القبض دون تخصيص':'Receipt posted without allocation'));
      setRAmount('');setReceiptRef('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createCustomer=async()=>{
    if(!cCode.trim()||!cNameAr.trim()||!cNameEn.trim()){setMessage(ar?'أكمل كود واسم العميل':'Complete customer code and names');return;}
    setBusy(true);setMessage('');
    try{const row=await json('/api/v1/subledgers/parties',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,code:cCode.trim(),name_ar:cNameAr.trim(),name_en:cNameEn.trim(),party_type:'CUSTOMER',vat_number:cVat.trim()||null,credit_limit:Number(cCredit)||0})});
      setMessage(ar?`تم إنشاء العميل ${row.code}`:`Customer ${row.code} created`);setCCode('');setCNameAr('');setCNameEn('');setCVat('');setCCredit('0');await load();setCustomer(String(row.id));setRCustomer(String(row.id));
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

    <Panel title={ar?'عميل جديد':'New customer'} icon={<BadgeDollarSign size={18}/> }>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'كود العميل':'Customer code'}<input style={field} value={cCode} onChange={e=>setCCode(e.target.value)}/></label>
        <label>{ar?'الاسم بالعربية':'Arabic name'}<input style={field} value={cNameAr} onChange={e=>setCNameAr(e.target.value)}/></label>
        <label>{ar?'الاسم بالإنجليزية':'English name'}<input style={field} value={cNameEn} onChange={e=>setCNameEn(e.target.value)}/></label>
        <label>{ar?'الرقم الضريبي (15 رقمًا)':'VAT number (15 digits)'}<input style={field} inputMode="numeric" value={cVat} onChange={e=>setCVat(e.target.value)}/></label>
        <label>{ar?'الحد الائتماني':'Credit limit'}<input type="number" min="0" style={field} value={cCredit} onChange={e=>setCCredit(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createCustomer}>{ar?'إنشاء العميل':'Create customer'}</button></div>
    </Panel>

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
      <div style={{padding:'0 12px 8px'}}><label><input type="checkbox" checked={postImmediately} onChange={e=>setPostImmediately(e.target.checked)}/> {ar?'ترحيل فورًا (اتركها غير محددة لفصل المُعدّ عن المُرحّل)':'Post immediately (leave off to separate maker from poster)'}</label></div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createInvoice}>{postImmediately?(ar?'إنشاء وترحيل الفاتورة':'Create & post invoice'):(ar?'حفظ كمسودة':'Save draft')}</button></div>
    </Panel>

    <Panel title={ar?'سند قبض':'Customer receipt'} icon={<Wallet size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'العميل':'Customer'}<select style={field} value={rCustomer} onChange={e=>setRCustomer(e.target.value)}>{customers.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
        <label>{ar?'البنك':'Bank'}<select style={field} value={rBank} onChange={e=>setRBank(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{ar?(b.bank_name_ar||b.name_ar):(b.bank_name_ar||b.name_ar)}</option>)}</select></label>
        <label>{ar?'المبلغ':'Amount'}<input type="number" style={field} value={rAmount} onChange={e=>setRAmount(e.target.value)}/></label>
        <label>{ar?'تاريخ القبض':'Receipt date'}<input type="date" style={field} value={receiptDate} onChange={e=>setReceiptDate(e.target.value)}/></label>
        <label>{ar?'المرجع':'Reference'}<input style={field} value={receiptRef} onChange={e=>setReceiptRef(e.target.value)}/></label>
      </div>
      <div style={{padding:'0 12px 8px'}}><label><input type="checkbox" checked={autoAllocate} onChange={e=>setAutoAllocate(e.target.checked)}/> {ar?'تخصيص تلقائي على أقدم فواتير مفتوحة':'Auto-allocate to oldest open invoices'}</label></div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createReceipt}>{ar?'تسجيل القبض':'Post receipt'}</button></div>
    </Panel>

    <Panel title={ar?'فواتير البيع':'Sales invoices'} icon={<ReceiptText size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'العميل':'Customer',ar?'الإجمالي':'Total',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={invoices.map(i=>[i.number||String(i.id),i.invoice_date,ar?(i.customer_name_ar||'—'):(i.customer_name_en||'—'),fmt(Number(i.total||0)),i.status,i.status==='DRAFT'?<button key={i.id} style={btn} disabled={busy} onClick={()=>postInvoice(i.id)}>{ar?'ترحيل':'Post'}</button>:'✓'])}/>
    </Panel>
    <Panel title={ar?'الفواتير المفتوحة':'Open receivables'} icon={<ReceiptText size={18}/> }>
      <DataTable headers={[ar?'المستند':'Document',ar?'الاستحقاق':'Due',ar?'العميل':'Customer',ar?'الرصيد المفتوح':'Outstanding',ar?'الحالة':'Status']}
        rows={openItems.map(i=>[i.document_number,i.due_date,ar?(i.party_name_ar||'—'):(i.party_name_en||'—'),fmt(Number(i.outstanding_amount||0)),i.status])}/>
    </Panel>
    <Panel title={ar?'سندات القبض والتخصيص':'Receipts and allocation'} icon={<Wallet size={18}/> }>
      <DataTable headers={[ar?'السند':'Receipt',ar?'التاريخ':'Date',ar?'العميل':'Customer',ar?'المبلغ':'Amount',ar?'مخصص':'Allocated',ar?'غير مخصص':'Unapplied',ar?'المرجع':'Reference']}
        rows={receipts.map(r=>[r.number,r.receipt_date,ar?r.party_name_ar:r.party_name_en,fmt(Number(r.amount||0)),fmt(Number(r.allocated_amount||0)),fmt(Number(r.unapplied_amount||0)),r.reference])}/>
    </Panel>
  </>;
}
