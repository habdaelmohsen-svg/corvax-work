import {useEffect, useMemo, useState} from 'react';
import {ArrowLeftRight, CheckCircle2, Download, FileCheck2, ReceiptText, RotateCcw, ShieldCheck} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, MiniStatus, Panel, money} from './ui';

type NoteType='SALES'|'PURCHASE';
type InvoiceLine={id:number;description:string;quantity:number;remaining_quantity:number;unit_price:number;vat_rate:number;tax_code?:string;subtotal:number;vat_amount:number;total:number};
type EligibleInvoice={id:number;number:string;invoice_date:string;party_code:string;party_name_ar:string;party_name_en:string;total:number;lines:InvoiceLine[]};

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
  const [notes,setNotes]=useState<any[]>([]); const [invoices,setInvoices]=useState<EligibleInvoice[]>([]); const [credits,setCredits]=useState<any[]>([]);
  const [invoiceId,setInvoiceId]=useState(''); const [lineId,setLineId]=useState(''); const [qty,setQty]=useState('1');
  const [reasonCode,setReasonCode]=useState('RETURN'); const [reason,setReason]=useState(''); const [noteDate,setNoteDate]=useState(new Date().toISOString().slice(0,10));
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  const invoice=useMemo(()=>invoices.find(x=>String(x.id)===invoiceId),[invoices,invoiceId]);
  const line=useMemo(()=>invoice?.lines.find(x=>String(x.id)===lineId),[invoice,lineId]);
  const load=async()=>{
    try{
      const [a,b,c]=await Promise.all([
        json(`/api/v1/credit-notes?company_id=${companyId}&note_type=${type}`),
        json(`/api/v1/credit-notes/eligible-invoices?company_id=${companyId}&note_type=${type}`),
        json(`/api/v1/credit-notes/credit-balances/open?company_id=${companyId}&ledger_type=${type==='SALES'?'AR':'AP'}`),
      ]);
      setNotes(Array.isArray(a)?a:[]); setInvoices(Array.isArray(b)?b:[]); setCredits(Array.isArray(c)?c:[]);
      if(!invoiceId&&b?.length){setInvoiceId(String(b[0].id));setLineId(String(b[0].lines?.[0]?.id||''));}
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{if(fixedType&&type!==fixedType)setType(fixedType)},[fixedType,type]);
  useEffect(()=>{setInvoiceId('');setLineId('');load()},[companyId,type]);
  useEffect(()=>{if(invoice?.lines?.length&&!invoice?.lines.some(x=>String(x.id)===lineId))setLineId(String(invoice.lines[0].id));},[invoice,lineId]);

  async function create(){
    if(!invoice||!line||!reason.trim()){setMessage(ar?'اختر الفاتورة والسطر وأدخل سبب المرتجع.':'Select an invoice and line, then enter the return reason.');return;}
    setBusy(true);setMessage('');
    try{
      const payload={company_id:companyId,note_type:type,note_date:noteDate,original_invoice_id:invoice.id,reason_code:reasonCode,reason,
        lines:[{original_line_id:line.id,quantity:Number(qty),inventory_disposition:'NONE'}]};
      const x=await json('/api/v1/credit-notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      setMessage(`${ar?'تم إنشاء الإشعار':'Credit note created'}: ${x.number}`);setReason('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function action(id:number,action:'submit'|'approve-post'){
    setBusy(true);setMessage('');try{const x=await json(`/api/v1/credit-notes/documents/${id}/${action}`,{method:'POST'});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
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
      <div className="journal-footer"><span>{ar?'الإشعار المسودة يُرسل أولًا، ثم يعتمد ويرحل بواسطة مستخدم مستقل.':'Draft is submitted first, then approved and posted by an independent user.'}</span><button onClick={()=>download(`/api/v1/credit-notes/export/csv?company_id=${companyId}`,'credit_notes.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>
      <DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'الفاتورة الأصلية':'Original invoice',ar?'النوع':'Type',ar?'الصافي':'Net',ar?'VAT':'VAT',ar?'الإجمالي':'Total',ar?'الحالة/الإجراء':'Status / action']} rows={notes.map(x=>[x.number,x.note_date,x.original_document_number,x.note_type,money.format(Number(x.subtotal)),money.format(Number(x.vat_amount)),money.format(Number(x.total)),<span key={x.id}>{x.status}{x.status==='DRAFT'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>action(x.id,'submit')}>{ar?'إرسال':'Submit'}</button>}{x.status==='PENDING_APPROVAL'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>action(x.id,'approve-post')}>{ar?'اعتماد وترحيل':'Approve & post'}</button>}</span>])}/>
    </Panel>
    <Panel title={ar?'الأرصدة الدائنة غير المطبقة':'Unapplied party credits'} icon={<ArrowLeftRight size={18}/> }>
      <DataTable headers={[ar?'الطرف':'Party',ar?'المصدر':'Source',ar?'التاريخ':'Date',ar?'الرصيد':'Balance',ar?'الحالة':'Status']} rows={credits.map(x=>[ar?x.party_name_ar:x.party_name_en,x.document_number,x.balance_date,money.format(Number(x.available_amount||0)),x.status])}/>
    </Panel>
  </>;
}
