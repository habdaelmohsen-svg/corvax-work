import {useEffect, useMemo, useState} from 'react';
import {ArrowLeftRight, CheckCircle2, Download, FileCheck2, FileJson, ReceiptText, RotateCcw, Search, ShieldCheck, XCircle} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, MiniStatus, Panel, money} from './ui';

type NoteType='SALES'|'PURCHASE';
type InvoiceLine={id:number;description:string;quantity:number;remaining_quantity:number;unit_price:number;vat_rate:number;tax_code?:string;subtotal:number;vat_amount:number;total:number;item_id?:number;warehouse_id?:number;inventory_capable?:boolean};
type EligibleInvoice={id:number;number:string;invoice_date:string;party_code:string;party_name_ar:string;party_name_en:string;total:number;lines:InvoiceLine[]};
type CreditBalance={id:number;ledger_type:'AR'|'AP';party_id:number;party_code:string;party_name_ar:string;party_name_en:string;document_number:string;balance_date:string;original_amount:number;available_amount:number;status:string};
type OpenItem={id:number;ledger_type:'AR'|'AP';party_id:number;document_number:string;document_date:string;due_date:string;outstanding_amount:number;status:string};

async function json(url:string, init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
async function download(url:string,filename:string){
  const r=await apiFetch(url); if(!r.ok) throw new Error('Export failed');
  const blob=await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename; a.click(); URL.revokeObjectURL(a.href);
}

export function CreditNotesPage({ar,companyId,fixedType}:{ar:boolean;companyId:number;fixedType?:NoteType}){
  const [type,setType]=useState<NoteType>(fixedType||'SALES');
  const [notes,setNotes]=useState<any[]>([]); const [invoices,setInvoices]=useState<EligibleInvoice[]>([]); const [credits,setCredits]=useState<CreditBalance[]>([]);
  const [openItems,setOpenItems]=useState<OpenItem[]>([]);
  const [invoiceId,setInvoiceId]=useState(''); const [lineId,setLineId]=useState(''); const [qty,setQty]=useState('1');
  const [reasonCode,setReasonCode]=useState('RETURN'); const [reason,setReason]=useState(''); const [noteDate,setNoteDate]=useState(new Date().toISOString().slice(0,10));
  const [inventoryDisposition,setInventoryDisposition]=useState('NONE');
  const [noteSearch,setNoteSearch]=useState(''); const [rejectReason,setRejectReason]=useState('');
  const [applyTarget,setApplyTarget]=useState<Record<number,string>>({}); const [applyAmount,setApplyAmount]=useState<Record<number,string>>({});
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  const invoice=useMemo(()=>invoices.find(x=>String(x.id)===invoiceId),[invoices,invoiceId]);
  const line=useMemo(()=>invoice?.lines.find(x=>String(x.id)===lineId),[invoice,lineId]);
  const normalizedSearch=noteSearch.trim().toLowerCase();
  const visibleNotes=useMemo(()=>normalizedSearch?notes.filter(x=>[
    x.number,x.original_document_number,x.party_code,x.party_name_ar,x.party_name_en,x.status,x.reason_code,x.reason,
  ].some(value=>String(value??'').toLowerCase().includes(normalizedSearch))):notes,[notes,normalizedSearch]);
  const visibleCredits=useMemo(()=>normalizedSearch?credits.filter(x=>[
    x.document_number,x.party_code,x.party_name_ar,x.party_name_en,x.status,x.available_amount,
  ].some(value=>String(value??'').toLowerCase().includes(normalizedSearch))):credits,[credits,normalizedSearch]);
  const load=async()=>{
    try{
      const ledger=type==='SALES'?'AR':'AP';
      const [a,b,c,d]=await Promise.all([
        json(`/api/v1/credit-notes?company_id=${companyId}&note_type=${type}`),
        json(`/api/v1/credit-notes/eligible-invoices?company_id=${companyId}&note_type=${type}`),
        json(`/api/v1/credit-notes/credit-balances/open?company_id=${companyId}&ledger_type=${ledger}`),
        json(`/api/v1/subledgers/open-items?company_id=${companyId}&ledger_type=${ledger}`),
      ]);
      setNotes(Array.isArray(a)?a:[]); setInvoices(Array.isArray(b)?b:[]); setCredits(Array.isArray(c)?c:[]);
      setOpenItems(Array.isArray(d)?d:[]);
      if(!invoiceId&&b?.length){setInvoiceId(String(b[0].id));setLineId(String(b[0].lines?.[0]?.id||''));}
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{if(fixedType&&type!==fixedType)setType(fixedType)},[fixedType,type]);
  useEffect(()=>{setInvoiceId('');setLineId('');load()},[companyId,type]);
  useEffect(()=>{if(invoice?.lines?.length&&!invoice?.lines.some(x=>String(x.id)===lineId))setLineId(String(invoice.lines[0].id));},[invoice,lineId]);
  useEffect(()=>{
    setInventoryDisposition(type==='PURCHASE'&&line?.inventory_capable?'RETURN_TO_SUPPLIER':'NONE');
  },[type,lineId,line?.inventory_capable]);

  async function create(){
    if(!invoice||!line||!reason.trim()){setMessage(ar?'اختر الفاتورة والسطر وأدخل سبب المرتجع.':'Select an invoice and line, then enter the return reason.');return;}
    setBusy(true);setMessage('');
    try{
      const inventory=inventoryDisposition!=='NONE'&&line.item_id&&line.warehouse_id
        ? {item_id:line.item_id,warehouse_id:line.warehouse_id}
        : {};
      const payload={company_id:companyId,note_type:type,note_date:noteDate,original_invoice_id:invoice.id,reason_code:reasonCode,reason,
        lines:[{original_line_id:line.id,quantity:Number(qty),inventory_disposition:inventoryDisposition,...inventory}]};
      const x=await json('/api/v1/credit-notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      setMessage(`${ar?'تم إنشاء الإشعار':'Credit note created'}: ${x.number}`);setReason('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function action(id:number,action:'submit'|'approve-post'){
    setBusy(true);setMessage('');try{const x=await json(`/api/v1/credit-notes/documents/${id}/${action}`,{method:'POST'});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function reject(id:number){
    if(rejectReason.trim().length<3){setMessage(ar?'أدخل سبب رفض واضحًا من 3 أحرف على الأقل.':'Enter a rejection reason of at least 3 characters.');return;}
    setBusy(true);setMessage('');
    try{
      const x=await json(`/api/v1/credit-notes/documents/${id}/reject`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:rejectReason.trim()})});
      setMessage(ar?`تم رفض ${x.number} مع حفظ السبب في سجل التدقيق.`:`${x.number} rejected and the reason was recorded in the audit log.`);
      setRejectReason('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function applyCredit(balance:CreditBalance){
    const targetId=Number(applyTarget[balance.id]); const amount=Number(applyAmount[balance.id]);
    const item=openItems.find(x=>x.id===targetId&&x.party_id===balance.party_id&&x.ledger_type===balance.ledger_type);
    if(!item||!Number.isFinite(amount)||amount<=0){setMessage(ar?'اختر فاتورة مفتوحة وأدخل مبلغ تطبيق صحيحًا.':'Select an open invoice and enter a valid application amount.');return;}
    const applicationDate=[new Date().toISOString().slice(0,10),balance.balance_date,item.document_date].sort().slice(-1)[0];
    setBusy(true);setMessage('');
    try{
      const x=await json(`/api/v1/credit-notes/credit-balances/${balance.id}/apply`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({open_item_id:item.id,amount,application_date:applicationDate})});
      setMessage(ar?`طُبّق ${money.format(amount)} على ${item.document_number}؛ المتبقي ${money.format(Number(x.available_amount))}.`:`Applied ${money.format(amount)} to ${item.document_number}; remaining credit ${money.format(Number(x.available_amount))}.`);
      setApplyTarget(s=>({...s,[balance.id]:''}));setApplyAmount(s=>({...s,[balance.id]:''}));await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  const statusLabel=(status:string)=>ar?({DRAFT:'مسودة',PENDING_APPROVAL:'بانتظار الاعتماد',APPROVED_POSTED:'معتمد ومُرحّل',REJECTED:'مرفوض',OPEN:'مفتوح',PARTIAL:'مطبق جزئيًا'} as Record<string,string>)[status]||status:status.split('_').join(' ');
  const totalNotes=notes.reduce((s,x)=>s+Number(x.total||0),0); const vat=notes.reduce((s,x)=>s+Number(x.vat_amount||0),0); const openCredit=credits.reduce((s,x)=>s+Number(x.available_amount||0),0);
  return <>
    <div className="kpis rich">
      <Kpi title={ar?'إشعارات دائنة':'Credit notes'} value={String(notes.length)} trend={type} good/>
      <Kpi title={ar?'إجمالي المرتجعات':'Total returns'} value={money.format(totalNotes)} trend={ar?'شامل الضريبة':'VAT inclusive'} good/>
      <Kpi title={ar?'VAT المعكوسة':'Reversed VAT'} value={money.format(vat)} trend={ar?'في فترة الإشعار':'In credit-note period'} good/>
      <Kpi title={ar?'أرصدة دائنة مفتوحة':'Open party credits'} value={money.format(openCredit)} trend={ar?'قابلة للتطبيق أو الرد':'Apply or cash settle'} good={openCredit===0}/>
    </div>
    {!fixedType&&<div className="segmented"><button className={type==='SALES'?'active':''} onClick={()=>setType('SALES')}>{ar?'مرتجع مبيعات':'Sales returns'}</button><button className={type==='PURCHASE'?'active':''} onClick={()=>setType('PURCHASE')}>{ar?'مرتجع مشتريات':'Purchase returns'}</button></div>}
    <div className="two-columns wide-left">
      <Panel title={ar?'إنشاء إشعار دائن مرتبط بالفاتورة':'Create invoice-linked credit note'} icon={<RotateCcw size={18}/> }>
        <div className="journal-form" style={{gridTemplateColumns:'repeat(2,minmax(0,1fr))'}}>
          <label>{ar?'الفاتورة الأصلية':'Original invoice'}<select value={invoiceId} onChange={e=>{setInvoiceId(e.target.value);const inv=invoices.find(x=>String(x.id)===e.target.value);setLineId(String(inv?.lines?.[0]?.id||''))}} style={{display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9}}>{invoices.map(x=><option key={x.id} value={x.id}>{x.number} — {ar?x.party_name_ar:x.party_name_en}</option>)}</select></label>
          <label>{ar?'سطر الفاتورة':'Invoice line'}<select value={lineId} onChange={e=>setLineId(e.target.value)} style={{display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9}}>{(invoice?.lines||[]).map(x=><option key={x.id} value={x.id}>{x.description} — {ar?'المتاح':'Available'} {String(x.remaining_quantity)}</option>)}</select></label>
          <label>{ar?'تاريخ الإشعار':'Credit-note date'}<input type="date" value={noteDate} onChange={e=>setNoteDate(e.target.value)}/></label>
          <label>{ar?'الكمية المرتجعة':'Return quantity'}<input type="number" min="0.0001" max={line?.remaining_quantity||undefined} step="0.0001" value={qty} onChange={e=>setQty(e.target.value)}/></label>
          <label>{ar?'كود السبب':'Reason code'}<input value={reasonCode} onChange={e=>setReasonCode(e.target.value.toUpperCase())}/></label>
          <label>{ar?'سبب المرتجع':'Return reason'}<input value={reason} onChange={e=>setReason(e.target.value)} placeholder={ar?'سبب واضح وقابل للمراجعة':'Clear auditable reason'}/></label>
          <label>{ar?'أثر المخزون':'Inventory treatment'}<select value={inventoryDisposition} onChange={e=>setInventoryDisposition(e.target.value)}>
            <option value="NONE">{ar?'بدون حركة مخزون (تسوية سعر/خدمة)':'No stock movement (price/service adjustment)'}</option>
            {type==='PURCHASE'&&line?.inventory_capable&&<option value="RETURN_TO_SUPPLIER">{ar?'إرجاع فعلي للمورد وخصم المخزون':'Physical return to supplier and reduce stock'}</option>}
            {type==='SALES'&&line?.inventory_capable&&<option value="RETURN_TO_STOCK">{ar?'إعادة للمخزون المتاح':'Return to available stock'}</option>}
            {type==='SALES'&&line?.inventory_capable&&<option value="QUARANTINE">{ar?'إعادة إلى الحجر':'Return to quarantine'}</option>}
          </select></label>
        </div>
        <div className="journal-footer"><span>{message|| (ar?'يُنسخ كود الضريبة من السطر الأصلي ولا يمكن تجاوزه.':'Tax code is inherited from the original line and cannot be overridden.')}</span><button disabled={busy||!invoices.length} onClick={create}>{busy?(ar?'جارٍ التنفيذ...':'Processing...'):(ar?'إنشاء الإشعار':'Create credit note')}</button></div>
      </Panel>
      <Panel title={ar?'ضوابط المعالجة':'Control framework'} icon={<ShieldCheck size={18}/> }>
        <MiniStatus icon={<FileCheck2 size={18}/>} title={ar?'الربط الأصلي':'Original linkage'} value={ar?'إلزامي':'Required'} status={ar?'فاتورة وسطر وكود ضريبي':'Invoice, line and tax code'}/>
        <MiniStatus icon={<ArrowLeftRight size={18}/>} title={ar?'الفترة الضريبية':'VAT period'} value={ar?'تاريخ الإشعار':'Credit-note date'} status={ar?'يدعم المرتجع اللاحق':'Cross-period supported'}/>
        <MiniStatus icon={<CheckCircle2 size={18}/>} title="Maker–Checker" value={ar?'مفعّل':'Active'} status={ar?'المُعد لا يعتمد':'Maker cannot approve'}/>
      </Panel>
    </div>
    <Panel title={ar?'سجل الإشعارات الدائنة':'Credit-note register'} icon={<ReceiptText size={18}/> }>
      <div className="journal-footer" style={{gap:10,flexWrap:'wrap'}}>
        <span>{ar?'الإشعار المسودة يُرسل أولًا، ثم يعتمد أو يرفض بواسطة مستخدم مستقل.':'A draft is submitted, then approved or rejected by an independent user.'}</span>
        <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
          <Search size={16}/><input value={noteSearch} onChange={e=>setNoteSearch(e.target.value)} aria-label={ar?'بحث الإشعارات الدائنة':'Search credit notes'} placeholder={ar?'رقم، عميل، فاتورة أو حالة...':'Number, party, invoice, or status...'} style={{minWidth:230}}/>
          {noteSearch&&<button onClick={()=>setNoteSearch('')}>{ar?'مسح':'Clear'}</button>}
          <small>{visibleNotes.length}/{notes.length}</small>
          <button onClick={()=>download(`/api/v1/credit-notes/export/csv?company_id=${companyId}`,'credit_notes.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button>
        </div>
      </div>
      {notes.some(x=>x.status==='PENDING_APPROVAL')&&<div style={{padding:'0 12px 12px',display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
        <XCircle size={16}/><label style={{flex:'1 1 300px'}}>{ar?'سبب الرفض (يُحفظ في سجل التدقيق)':'Rejection reason (saved in the audit log)'}<input value={rejectReason} onChange={e=>setRejectReason(e.target.value)} maxLength={500} style={{display:'block',width:'100%',marginTop:5}}/></label>
      </div>}
      <DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'الفاتورة الأصلية':'Original invoice',ar?'الطرف':'Party',ar?'الصافي':'Net',ar?'VAT':'VAT',ar?'الإجمالي':'Total',ar?'الحالة والإجراء':'Status and action']} rows={visibleNotes.map(x=>[x.number,x.note_date,x.original_document_number,ar?x.party_name_ar:x.party_name_en,money.format(Number(x.subtotal)),money.format(Number(x.vat_amount)),money.format(Number(x.total)),<div key={x.id} style={{display:'flex',gap:5,alignItems:'center',flexWrap:'wrap'}}><strong>{statusLabel(x.status)}</strong>{x.status==='DRAFT'&&<button disabled={busy} onClick={()=>action(x.id,'submit')}>{ar?'إرسال':'Submit'}</button>}{x.status==='PENDING_APPROVAL'&&<><button disabled={busy} onClick={()=>action(x.id,'approve-post')}>{ar?'اعتماد وترحيل':'Approve & post'}</button><button disabled={busy||rejectReason.trim().length<3} onClick={()=>reject(x.id)} style={{background:'#b91c1c',color:'#fff'}}>{ar?'رفض':'Reject'}</button></>}{x.status==='APPROVED_POSTED'&&<button disabled={busy} onClick={()=>download(`/api/v1/credit-notes/documents/${x.id}/zatca-document`,`${x.number}-zatca.json`).then(()=>setMessage(ar?`تم تنزيل مستند ZATCA المنظم لـ ${x.number}.`:`Structured ZATCA document downloaded for ${x.number}.`)).catch(e=>setMessage(e.message))}><FileJson size={14}/>{ar?'ZATCA JSON':'ZATCA JSON'}</button>}</div>])}/>
    </Panel>
    <Panel title={ar?'الأرصدة الدائنة غير المطبقة':'Unapplied party credits'} icon={<ArrowLeftRight size={18}/> }>
      <DataTable headers={[ar?'الطرف':'Party',ar?'المصدر':'Source',ar?'التاريخ':'Date',ar?'الرصيد':'Balance',ar?'الحالة':'Status',ar?'تطبيق على فاتورة مفتوحة':'Apply to open invoice']} rows={visibleCredits.map(balance=>{
        const candidates=openItems.filter(item=>item.party_id===balance.party_id&&item.ledger_type===balance.ledger_type&&Number(item.outstanding_amount)>0);
        const selectedId=applyTarget[balance.id]||'';
        return [ar?balance.party_name_ar:balance.party_name_en,balance.document_number,balance.balance_date,money.format(Number(balance.available_amount||0)),statusLabel(balance.status),candidates.length?<div key={balance.id} style={{display:'grid',gap:6,minWidth:220}}><select aria-label={ar?`الفاتورة المفتوحة للرصيد ${balance.document_number}`:`Open invoice for ${balance.document_number}`} value={selectedId} onChange={e=>{const id=e.target.value;const item=candidates.find(x=>String(x.id)===id);setApplyTarget(s=>({...s,[balance.id]:id}));setApplyAmount(s=>({...s,[balance.id]:item?String(Math.min(Number(balance.available_amount),Number(item.outstanding_amount)).toFixed(2)):''}))}}><option value="">{ar?'اختر فاتورة...':'Select invoice...'}</option>{candidates.map(item=><option key={item.id} value={item.id}>{item.document_number} — {money.format(Number(item.outstanding_amount))}</option>)}</select><input type="number" min="0.01" step="0.01" max={Number(balance.available_amount)} aria-label={ar?`مبلغ تطبيق ${balance.document_number}`:`Application amount for ${balance.document_number}`} value={applyAmount[balance.id]||''} onChange={e=>setApplyAmount(s=>({...s,[balance.id]:e.target.value}))}/><button disabled={busy||!selectedId||Number(applyAmount[balance.id])<=0} onClick={()=>applyCredit(balance)}>{ar?'تطبيق الرصيد':'Apply credit'}</button></div>:<small>{ar?'لا توجد فاتورة مفتوحة مطابقة للطرف.':'No matching open invoice.'}</small>];
      })}/>
    </Panel>
  </>;
}
