import {useEffect, useState} from 'react';
import {CheckCircle2, Download, FileCheck2, Scale, Upload, XCircle} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type Validation = {
  valid:boolean;
  summary:{rows:number;total_debit:number;total_credit:number;difference:number;errors:number;gl_lines:number;ar_lines:number;ap_lines:number;inventory_lines:number};
  global_errors:string[];
  rows:{line_number:number;line_type:string;account_code:string;party_code?:string;item_code?:string;warehouse_code?:string;debit:number;credit:number;errors:string[];warnings:string[]}[];
};
type Batch = {
  id:number;opening_date:string;version:number;source_system:string;source_filename:string;status:string;
  total_debit:number;total_credit:number;line_count:number;validation_hash:string;journal_id?:number;
};

async function json(url:string,init?:RequestInit){
  const response=await apiFetch(url,init);
  const payload=await response.json().catch(()=>({}));
  if(!response.ok){
    const detail=payload.detail;
    const message=typeof detail==='string'?detail
      :detail?.message_ar||detail?.message_en||detail?.global_errors?.join(' | ')
      ||JSON.stringify(detail||payload);
    throw new Error(message);
  }
  return payload;
}
async function download(url:string,filename:string){
  const response=await apiFetch(url);
  if(!response.ok)throw new Error('Export failed');
  const blob=await response.blob();
  const anchor=document.createElement('a');
  anchor.href=URL.createObjectURL(blob);anchor.download=filename;anchor.click();
  URL.revokeObjectURL(anchor.href);
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,display:'inline-flex',alignItems:'center',gap:7} as const;
const today=new Date().toISOString().slice(0,10);

export function OpeningBalancesPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [file,setFile]=useState<File|null>(null);
  const [openingDate,setOpeningDate]=useState(today);
  const [sourceSystem,setSourceSystem]=useState('LEGACY_SYSTEM');
  const [validation,setValidation]=useState<Validation|null>(null);
  const [batches,setBatches]=useState<Batch[]>([]);
  const [message,setMessage]=useState('');
  const [error,setError]=useState(false);
  const [busy,setBusy]=useState(false);

  const load=async()=>{
    try{
      const rows=await json(`/api/v1/opening-balances?company_id=${companyId}`);
      setBatches(Array.isArray(rows)?rows:[]);
    }catch(e:any){setMessage(String(e.message||e));setError(true);}
  };
  useEffect(()=>{load()},[companyId]);
  const form=()=>{
    if(!file)throw new Error(ar?'اختر ملف Excel أولًا':'Choose an Excel file first');
    const body=new FormData();body.append('file',file);return body;
  };
  const validate=async()=>{
    setBusy(true);setMessage('');setError(false);setValidation(null);
    try{
      const result=await json(`/api/v1/opening-balances/validate?company_id=${companyId}`,{method:'POST',body:form()});
      setValidation(result);
      setMessage(result.valid
        ?(ar?'نجحت المطابقة. الملف متوازن وكل الحسابات والبيانات المساندة صحيحة.':'Validation passed. The file is balanced and reconciled.')
        :(ar?'فشل الفحص. أصلح الأخطاء الظاهرة قبل الاستيراد.':'Validation failed. Correct the listed errors.'));
      setError(!result.valid);
    }catch(e:any){setMessage(String(e.message||e));setError(true);}
    finally{setBusy(false);}
  };
  const importBatch=async()=>{
    if(!validation?.valid){setMessage(ar?'نفّذ فحص المطابقة بنجاح أولًا':'Run a successful validation first');setError(true);return;}
    setBusy(true);setMessage('');setError(false);
    try{
      const url=`/api/v1/opening-balances/import?company_id=${companyId}&opening_date=${openingDate}&source_system=${encodeURIComponent(sourceSystem)}`;
      const result=await json(url,{method:'POST',body:form()});
      setMessage(ar?`تم إنشاء الدفعة رقم ${result.id} كمسودة. أرسلها للاعتماد.`:`Draft batch ${result.id} created. Submit it for approval.`);
      setFile(null);setValidation(null);await load();
    }catch(e:any){setMessage(String(e.message||e));setError(true);}
    finally{setBusy(false);}
  };
  const action=async(id:number,kind:'submit'|'approve-post')=>{
    setBusy(true);setMessage('');setError(false);
    try{
      const result=await json(`/api/v1/opening-balances/${id}/${kind}`,{method:'POST'});
      setMessage(kind==='submit'
        ?(ar?'تم الإرسال للاعتماد. يجب أن يعتمد مستخدم مستقل.':'Submitted. An independent user must approve.')
        :(ar?`تم الترحيل بالقيد ${result.journal_number}`:`Posted as ${result.journal_number}`));
      await load();
    }catch(e:any){setMessage(String(e.message||e));setError(true);}
    finally{setBusy(false);}
  };
  const latest=batches[0];
  const statusLabel=(status:string)=>({
    DRAFT:ar?'مسودة':'Draft',PENDING_APPROVAL:ar?'بانتظار الاعتماد':'Pending approval',POSTED:ar?'مرحّلة':'Posted',
  } as Record<string,string>)[status]||status;

  return <>
    <div className="kpis">
      <Kpi title={ar?'دفعات الاستيراد':'Import batches'} value={String(batches.length)} trend="" good icon={<Upload size={22}/>} tone="blue"/>
      <Kpi title={ar?'آخر حالة':'Latest status'} value={latest?statusLabel(latest.status):'—'} trend={latest?.opening_date||''} good={latest?.status==='POSTED'} icon={<FileCheck2 size={22}/>} tone="violet"/>
      <Kpi title={ar?'إجمالي المدين':'Total debit'} value={validation?fmt(Number(validation.summary.total_debit)):fmt(Number(latest?.total_debit||0))} trend="" good icon={<Scale size={22}/>} tone="green"/>
      <Kpi title={ar?'فرق المطابقة':'Reconciliation difference'} value={fmt(Number(validation?.summary.difference||0))} trend={validation?.valid?(ar?'متوازن':'Balanced'):(ar?'يتطلب فحصًا':'Needs validation')} good={!!validation?.valid} icon={validation?.valid?<CheckCircle2 size={22}/>:<XCircle size={22}/>} tone="amber"/>
    </div>

    {message&&<div style={{padding:11,marginBottom:12,borderRadius:9,lineHeight:1.8,
      background:error?'#fee2e2':'#dcfce7',color:error?'#991b1b':'#166534'}}>{message}</div>}

    <Panel title={ar?'استيراد ومطابقة الأرصدة الافتتاحية':'Import and reconcile opening balances'} icon={<Upload size={18}/>}>
      <div style={{padding:'8px 12px',fontSize:13,lineHeight:1.9,color:'var(--muted)'}}>
        {ar
          ? 'النظام لا يكتفي بتساوي المدين والدائن: يطابق الحساب مع شجرة الحسابات، ويربط أرصدة العملاء والموردين بأعمار الديون، ويربط كميات المخزون بالصنف والمستودع. لا تُدخل حساب العملاء أو الموردين أو المخزون كسطر GL عادي.'
          : 'The system checks more than debit equals credit: it matches the chart, creates AR/AP open items, and links inventory quantities to items and warehouses. Control accounts cannot be imported as ordinary GL rows.'}
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(210px,1fr))',gap:12,padding:12}}>
        <label>{ar?'تاريخ الافتتاح':'Opening date'}<input type="date" style={field} value={openingDate} onChange={e=>setOpeningDate(e.target.value)}/></label>
        <label>{ar?'اسم النظام القديم':'Legacy system'}<input style={field} value={sourceSystem} onChange={e=>setSourceSystem(e.target.value)}/></label>
        <label>{ar?'ملف الأرصدة (.xlsx)':'Opening file (.xlsx)'}<input type="file" accept=".xlsx" style={field}
          onChange={e=>{setFile(e.target.files?.[0]||null);setValidation(null);}}/></label>
      </div>
      <div style={{display:'flex',gap:8,flexWrap:'wrap',padding:'0 12px 14px'}}>
        <button style={{...btn,background:'#475569'}} onClick={()=>download(`/api/v1/opening-balances/template.xlsx?company_id=${companyId}`,'CORVAX_Opening_Balances.xlsx').catch(e=>{setMessage(e.message);setError(true)})}><Download size={16}/>{ar?'تنزيل نموذج Excel':'Download template'}</button>
        <button style={btn} disabled={busy||!file} onClick={validate}><FileCheck2 size={16}/>{ar?'فحص ومطابقة':'Validate & match'}</button>
        <button style={{...btn,background:'#059669',opacity:validation?.valid?1:.5}} disabled={busy||!validation?.valid} onClick={importBatch}><Upload size={16}/>{ar?'استيراد كمسودة':'Import draft'}</button>
      </div>
    </Panel>

    {validation&&<Panel title={ar?'نتيجة المطابقة قبل الترحيل':'Pre-posting validation result'} icon={validation.valid?<CheckCircle2 size={18}/>:<XCircle size={18}/>}>
      <div style={{padding:'0 0 10px',fontSize:13}}>
        {ar?'السطور':'Rows'}: {validation.summary.rows} · GL {validation.summary.gl_lines} · AR {validation.summary.ar_lines} · AP {validation.summary.ap_lines} · Inventory {validation.summary.inventory_lines}
      </div>
      <DataTable headers={[ar?'السطر':'Row',ar?'النوع':'Type',ar?'الحساب':'Account',ar?'المرجع':'Reference',ar?'مدين':'Debit',ar?'دائن':'Credit',ar?'النتيجة':'Result']}
        rows={validation.rows.map(row=>[
          String(row.line_number),row.line_type,row.account_code,row.party_code||row.item_code||row.warehouse_code||'—',
          fmt(Number(row.debit)),fmt(Number(row.credit)),
          row.errors.length?<span style={{color:'#b91c1c'}}>{row.errors.join(' | ')}</span>:<span style={{color:'#047857'}}>✓</span>,
        ])}/>
    </Panel>}

    <Panel title={ar?'سجل الأرصدة الافتتاحية':'Opening-balance register'} icon={<FileCheck2 size={18}/>}>
      <DataTable headers={[ar?'التاريخ':'Date',ar?'النسخة':'Version',ar?'المصدر':'Source',ar?'السطور':'Lines',ar?'الإجمالي':'Total',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={batches.map(batch=>[
          batch.opening_date,`V${batch.version}`,batch.source_system,String(batch.line_count),fmt(Number(batch.total_debit)),statusLabel(batch.status),
          <span key={batch.id} style={{display:'flex',gap:6}}>
            {batch.status==='DRAFT'&&<button style={btn} disabled={busy} onClick={()=>action(batch.id,'submit')}>{ar?'إرسال':'Submit'}</button>}
            {batch.status==='PENDING_APPROVAL'&&<button style={{...btn,background:'#059669'}} disabled={busy} onClick={()=>action(batch.id,'approve-post')}>{ar?'اعتماد وترحيل':'Approve & post'}</button>}
            {batch.status==='POSTED'&&<span>✓ JV #{batch.journal_id}</span>}
          </span>,
        ])}/>
    </Panel>
  </>;
}
