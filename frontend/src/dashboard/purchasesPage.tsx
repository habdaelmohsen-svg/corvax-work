import {useEffect, useState} from 'react';
import {ShoppingCart, ReceiptText, Wallet, CheckCircle2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';
import {ProcurementWorkflowTab} from './procurementWorkflowTab';

type Party={id:number;code:string;name_ar:string;name_en:string;party_type:string};
type Bank={id:number;bank_name_ar?:string;name_ar?:string};
type Invoice={id:number;number?:string;invoice_date:string;supplier_name_ar?:string;supplier_name_en?:string;supplier_invoice_number?:string;total?:number;status:string};
type Payment={id:number;number:string;payment_date:string;party_name_ar:string;party_name_en:string;amount:number;allocated_amount:number;unapplied_amount:number;reference:string};
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

export function PurchasesPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [mainTab,setMainTab]=useState<'workflow'|'invoices'>('workflow');
  const [summary,setSummary]=useState<any>(null);
  const [suppliers,setSuppliers]=useState<Party[]>([]);
  const [banks,setBanks]=useState<Bank[]>([]);
  const [invoices,setInvoices]=useState<Invoice[]>([]);
  const [payments,setPayments]=useState<Payment[]>([]); const [openItems,setOpenItems]=useState<OpenItem[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // invoice form
  const [supplier,setSupplier]=useState(''); const [invDate,setInvDate]=useState(iso()); const [due,setDue]=useState(addDays(30));
  const [supplierInv,setSupplierInv]=useState(''); const [desc,setDesc]=useState(''); const [qty,setQty]=useState('1'); const [price,setPrice]=useState(''); const [vat,setVat]=useState('15'); const [account,setAccount]=useState('613010');
  const [postImmediately,setPostImmediately]=useState(false);
  // payment form
  const [pSupplier,setPSupplier]=useState(''); const [pBank,setPBank]=useState(''); const [pAmount,setPAmount]=useState('');
  const [paymentDate,setPaymentDate]=useState(iso()); const [paymentRef,setPaymentRef]=useState(''); const [autoAllocate,setAutoAllocate]=useState(true);
  const [query,setQuery]=useState('');

  const load=async()=>{
    try{
      const [s,p,b,inv,pays,opens]=await Promise.all([
        json(`/api/v1/subledgers/summary?company_id=${companyId}`),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`),
        json(`/api/v1/subledgers/purchase-invoices?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/payments?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/open-items?company_id=${companyId}&ledger_type=AP`).catch(()=>[]),
      ]);
      setSummary(s); setSuppliers((p||[]).filter((x:Party)=>['SUPPLIER','BOTH'].includes(x.party_type))); setBanks(b||[]); setInvoices(inv||[]);
      setPayments(pays||[]);setOpenItems(opens||[]);
      const sup=(p||[]).filter((x:Party)=>['SUPPLIER','BOTH'].includes(x.party_type));
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
      if(postImmediately)await json(`/api/v1/subledgers/purchase-invoices/${inv.id}/post`,{method:'POST'});
      setMessage(postImmediately?(ar?'تم إنشاء فاتورة الشراء وترحيلها':'Purchase invoice created and posted'):(ar?'حُفظت الفاتورة كمسودة للمراجعة':'Invoice saved as draft for review'));setDesc('');setPrice('');setSupplierInv('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const postInvoice=async(id:number)=>{setBusy(true);setMessage('');try{await json(`/api/v1/subledgers/purchase-invoices/${id}/post`,{method:'POST'});setMessage(ar?'تم ترحيل الفاتورة وإنشاء القيد وذمة المورد':'Invoice posted; journal and payable created');await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}};
  const createPayment=async()=>{
    if(!pSupplier||!pBank||!pAmount){setMessage(ar?'أكمل بيانات السداد':'Complete payment fields');return;}
    setBusy(true);setMessage('');
    try{const payment=await json('/api/v1/subledgers/payments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,payment_date:paymentDate,supplier_id:Number(pSupplier),bank_account_id:Number(pBank),amount:Number(pAmount),reference:paymentRef.trim()||`UI-PAY-${Date.now()}`})});
      const allocation=autoAllocate?await json(`/api/v1/subledgers/payments/${payment.id}/auto-allocate`,{method:'POST'}):payment;
      setMessage(autoAllocate?(ar?`تم السداد وتخصيص ${fmt(Number(allocation.allocated_amount||0))}؛ غير مخصص ${fmt(Number(allocation.unapplied_amount||0))}`:`Payment posted; ${fmt(Number(allocation.allocated_amount||0))} allocated, ${fmt(Number(allocation.unapplied_amount||0))} unapplied`):(ar?'تم تسجيل السداد دون تخصيص':'Payment posted without allocation'));setPAmount('');setPaymentRef('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const normalized=query.trim().toLowerCase();
  const shownInvoices=invoices.filter(i=>!normalized||[i.number,i.supplier_invoice_number,i.supplier_name_ar,i.supplier_name_en,i.status].some(x=>String(x||'').toLowerCase().includes(normalized)));
  const shownOpen=openItems.filter(i=>!normalized||[i.document_number,i.party_name_ar,i.party_name_en,i.status].some(x=>String(x||'').toLowerCase().includes(normalized)));
  const shownPayments=payments.filter(i=>!normalized||[i.number,i.reference,i.party_name_ar,i.party_name_en].some(x=>String(x||'').toLowerCase().includes(normalized)));

  const tabs=<div style={{display:'flex',gap:8,margin:'4px 0 14px'}}><button data-testid="purchases-workflow-tab" style={{...btn,background:mainTab==='workflow'?'var(--accent, #1e40af)':'transparent',color:mainTab==='workflow'?'#fff':'var(--text)',border:'1px solid var(--border)'}} onClick={()=>setMainTab('workflow')}>{ar?'طلب شراء وRFQ':'PR & RFQ'}</button><button data-testid="purchases-invoices-tab" style={{...btn,background:mainTab==='invoices'?'var(--accent, #1e40af)':'transparent',color:mainTab==='invoices'?'#fff':'var(--text)',border:'1px solid var(--border)'}} onClick={()=>setMainTab('invoices')}>{ar?'الفواتير والسداد':'Invoices & payments'}</button></div>;
  if(mainTab==='workflow')return <>{tabs}<ProcurementWorkflowTab ar={ar} companyId={companyId}/></>;

  return <>
    {tabs}
    <div className="kpis">
      <Kpi title={ar?'ذمم الموردين':'Accounts payable'} value={summary?fmt(Number(summary.accounts_payable)):'—'} trend="AP" good icon={<ReceiptText size={22}/>} tone="blue"/>
      <Kpi title={ar?'فواتير الشراء':'Purchase invoices'} value={summary?String(summary.purchase_invoices):'—'} trend="" good icon={<ShoppingCart size={22}/>} tone="green"/>
      <Kpi title={ar?'سندات الصرف':'Payments'} value={summary?String(summary.payments):'—'} trend="" good icon={<Wallet size={22}/>} tone="violet"/>
      <Kpi title={ar?'رصيد البنك':'Bank balance'} value={summary?fmt(Number(summary.cash_balance)):'—'} trend="GL" good icon={<CheckCircle2 size={22}/>} tone="amber"/>
    </div>
    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}
    <div style={{margin:'0 0 12px'}}><label>{ar?'بحث في الفواتير والسدادات':'Search invoices and payments'}<input data-testid="purchase-search" style={field} value={query} onChange={e=>setQuery(e.target.value)} placeholder={ar?'رقم مستند، مورد، مرجع، حالة':'Document, supplier, reference, status'}/></label><span data-testid="purchase-search-count">{shownInvoices.length}/{invoices.length}</span></div>

    <Panel title={ar?'فاتورة شراء جديدة':'New purchase invoice'} icon={<ShoppingCart size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'المورد':'Supplier'}<select data-testid="purchase-invoice-supplier" style={field} value={supplier} onChange={e=>setSupplier(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{ar?s.name_ar:s.name_en}</option>)}</select></label>
        <label>{ar?'رقم فاتورة المورد':'Supplier invoice #'}<input data-testid="purchase-supplier-invoice" style={field} value={supplierInv} onChange={e=>setSupplierInv(e.target.value)}/></label>
        <label>{ar?'تاريخ الفاتورة':'Invoice date'}<input data-testid="purchase-invoice-date" type="date" style={field} value={invDate} onChange={e=>setInvDate(e.target.value)}/></label>
        <label>{ar?'تاريخ الاستحقاق':'Due date'}<input data-testid="purchase-invoice-due" type="date" style={field} value={due} onChange={e=>setDue(e.target.value)}/></label>
        <label>{ar?'الوصف':'Description'}<input data-testid="purchase-invoice-description" style={field} value={desc} onChange={e=>setDesc(e.target.value)}/></label>
        <label>{ar?'الكمية':'Quantity'}<input data-testid="purchase-invoice-quantity" type="number" style={field} value={qty} onChange={e=>setQty(e.target.value)}/></label>
        <label>{ar?'سعر الوحدة':'Unit price'}<input data-testid="purchase-invoice-price" type="number" style={field} value={price} onChange={e=>setPrice(e.target.value)}/></label>
        <label>{ar?'الضريبة %':'VAT %'}<input data-testid="purchase-invoice-vat" type="number" style={field} value={vat} onChange={e=>setVat(e.target.value)}/></label>
      </div>
      <div style={{padding:'0 12px 8px'}}><label><input data-testid="purchase-post-immediately" type="checkbox" checked={postImmediately} onChange={e=>setPostImmediately(e.target.checked)}/> {ar?'ترحيل فورًا (اتركها غير محددة لفصل المُعدّ عن المُرحّل)':'Post immediately (leave off to separate maker from poster)'}</label></div>
      <div style={{padding:12}}><button data-testid="purchase-invoice-create" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createInvoice}>{postImmediately?(ar?'إنشاء وترحيل':'Create & post'):(ar?'حفظ كمسودة':'Save draft')}</button></div>
    </Panel>

    <Panel title={ar?'سند صرف':'Supplier payment'} icon={<Wallet size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'المورد':'Supplier'}<select data-testid="payment-supplier" style={field} value={pSupplier} onChange={e=>setPSupplier(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{ar?s.name_ar:s.name_en}</option>)}</select></label>
        <label>{ar?'البنك':'Bank'}<select data-testid="payment-bank" style={field} value={pBank} onChange={e=>setPBank(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{b.bank_name_ar||b.name_ar}</option>)}</select></label>
        <label>{ar?'المبلغ':'Amount'}<input data-testid="payment-amount" type="number" style={field} value={pAmount} onChange={e=>setPAmount(e.target.value)}/></label>
        <label>{ar?'تاريخ السداد':'Payment date'}<input data-testid="payment-date" type="date" style={field} value={paymentDate} onChange={e=>setPaymentDate(e.target.value)}/></label>
        <label>{ar?'المرجع':'Reference'}<input data-testid="payment-reference" style={field} value={paymentRef} onChange={e=>setPaymentRef(e.target.value)}/></label>
      </div>
      <div style={{padding:'0 12px 8px'}}><label><input data-testid="payment-auto-allocate" type="checkbox" checked={autoAllocate} onChange={e=>setAutoAllocate(e.target.checked)}/> {ar?'تخصيص تلقائي على أقدم فواتير المورد المفتوحة':'Auto-allocate to oldest supplier invoices'}</label></div>
      <div style={{padding:12}}><button data-testid="payment-create" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createPayment}>{ar?'تسجيل الصرف':'Post payment'}</button></div>
    </Panel>

    <Panel title={ar?'فواتير الشراء':'Purchase invoices'} icon={<ReceiptText size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المورد':'Supplier',ar?'فاتورة المورد':'Supplier inv.',ar?'الإجمالي':'Total',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={shownInvoices.map(i=>[i.number||String(i.id),i.invoice_date,ar?(i.supplier_name_ar||'—'):(i.supplier_name_en||'—'),i.supplier_invoice_number||'—',fmt(Number(i.total||0)),<span data-testid={`purchase-invoice-status-${i.id}`}>{i.status}</span>,i.status==='DRAFT'?<button data-testid={`purchase-invoice-post-${i.id}`} key={i.id} style={btn} disabled={busy} onClick={()=>postInvoice(i.id)}>{ar?'ترحيل':'Post'}</button>:'✓'])}/>
    </Panel>
    <Panel title={ar?'فواتير الموردين المفتوحة':'Open supplier invoices'} icon={<ReceiptText size={18}/> }>
      <DataTable headers={[ar?'المستند':'Document',ar?'الاستحقاق':'Due',ar?'المورد':'Supplier',ar?'الرصيد المفتوح':'Outstanding',ar?'الحالة':'Status']} rows={shownOpen.map(i=>[i.document_number,i.due_date,ar?(i.party_name_ar||'—'):(i.party_name_en||'—'),fmt(Number(i.outstanding_amount||0)),i.status])}/>
    </Panel>
    <Panel title={ar?'سندات الصرف والتخصيص':'Payments and allocation'} icon={<Wallet size={18}/> }>
      <DataTable headers={[ar?'السند':'Payment',ar?'التاريخ':'Date',ar?'المورد':'Supplier',ar?'المبلغ':'Amount',ar?'مخصص':'Allocated',ar?'غير مخصص':'Unapplied',ar?'المرجع':'Reference']} rows={shownPayments.map(p=>[p.number,p.payment_date,ar?p.party_name_ar:p.party_name_en,fmt(Number(p.amount||0)),fmt(Number(p.allocated_amount||0)),fmt(Number(p.unapplied_amount||0)),p.reference])}/>
    </Panel>
  </>;
}
