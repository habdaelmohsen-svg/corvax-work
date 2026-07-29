import {useEffect, useState} from 'react';
import {Trash2, ShieldAlert, Eye, CheckCircle2, Lock} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

// Removing only rows explicitly registered by CORVAX as Demo.
// The destructive path is deliberately slow:
// preview -> exact phrase -> dry run -> short-lived authorization -> execute.

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    const msg = typeof d==='string' ? d
      : (d && (d.message_ar||d.message_en)) ? (d.message_ar||d.message_en)
      : JSON.stringify(d||x);
    throw new Error(msg);
  }
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const danger={...btn,background:'#b91c1c'} as const;

export function DataResetPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [preview,setPreview]=useState<any>(null);
  const [confirmation,setConfirmation]=useState('');
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  const [dryDone,setDryDone]=useState(false);
  const [authorizationToken,setAuthorizationToken]=useState('');

  const load=async()=>{
    setMsg('');setErr(false);
    try{
      const r=await json(`/api/v1/data-reset/preview?company_id=${companyId}`);
      setPreview(r); setDryDone(false); setAuthorizationToken(''); setConfirmation('');
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const run=async(dry:boolean)=>{
    setBusy(true);setMsg('');setErr(false);
    try{
      const r=await json('/api/v1/data-reset/execute',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,confirmation,dry_run:dry,
          authorization_token:dry?undefined:authorizationToken})});
      setMsg(ar?r.message_ar:r.message_en); setErr(false);
      if(dry){
        setAuthorizationToken(r.authorization_token||'');
        setDryDone(Boolean(r.authorization_token));
      } else { setDryDone(false); setAuthorizationToken(''); await load(); }
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };

  const phrase = preview?.confirmation_phrase || '';
  const matches = confirmation === phrase && phrase.length>0;
  const enabled = preview?.enabled;
  const rows = Object.entries(preview?.tables||{}) as [string,number][];
  const blockers = Object.entries(preview?.blocking_dependencies||{}) as [string,number][];

  return <>
    <div className="kpis">
      <Kpi title={ar?'صفوف ستُحذف':'Rows to remove'} value={String(preview?.total_rows ?? '—')} trend="" good={(preview?.total_rows||0)===0} icon={<Trash2 size={22}/>} tone="amber"/>
      <Kpi title={ar?'جداول متأثرة':'Tables'} value={String(rows.length)} trend="" good icon={<Eye size={22}/>} tone="blue"/>
      <Kpi title={ar?'صفوف يدوية محفوظة':'Manual rows kept'} value={String(preview?.preserved_unregistered_total ?? '—')} trend={ar?'لا تدخل في الحذف':'excluded'} good icon={<CheckCircle2 size={22}/>} tone="green"/>
      <Kpi title={ar?'الأداة':'Reset tool'} value={enabled?(ar?'مفعّلة':'Enabled'):(ar?'مقفلة':'Locked')} trend="ALLOW_DATA_RESET" good={!enabled} icon={<Lock size={22}/>} tone="violet"/>
    </div>

    {msg&&<div style={{padding:11,margin:'12px 0',borderRadius:9,fontSize:14,lineHeight:1.8,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    <Panel title={ar?'ما الذي سيُحذف وما الذي سيبقى':'What is removed and what is kept'} icon={<ShieldAlert size={18}/>}>
      <div style={{padding:'10px 14px',display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(260px,1fr))',gap:14}}>
        <div style={{padding:13,borderRadius:10,background:'#fef2f2',color:'#7f1d1d',lineHeight:1.9,fontSize:13}}>
          <b>{ar?'يُحذف — Demo المسجل فقط':'Removed — registered Demo only'}</b><br/>
          {ar
            ? 'فقط الصفوف التي أنشأها Seeder الموثوق وسجل رقمها الأساسي صراحةً في سجل Demo. لا يعتمد النظام على الاسم أو التاريخ أو المرجع لتخمين نوع البيانات.'
            : 'Only rows whose primary keys were explicitly registered by the trusted seeder. Names, dates and references are never used to guess that data is Demo.'}
        </div>
        <div style={{padding:13,borderRadius:10,background:'#f0fdf4',color:'#14532d',lineHeight:1.9,fontSize:13}}>
          <b>{ar?'يبقى — كل ما لم يُسجل Demo':'Kept — everything not registered as Demo'}</b><br/>
          {ar
            ? 'كل صف أدخل يدويًا أو أُنشئ تشغيليًا، إضافة إلى الشركات والفروع وشجرة الحسابات والمستخدمين والصلاحيات وسجل التدقيق.'
            : 'Every manually entered or operational row, plus companies, branches, chart of accounts, users, permissions and the audit log.'}
        </div>
      </div>
    </Panel>

    {!enabled&&<Panel title={ar?'الأداة مقفلة':'The tool is locked'} icon={<Lock size={18}/>}>
      <div style={{padding:14,fontSize:14,lineHeight:2}}>
        {preview?.production_blocked
          ? (ar?'هذه الأداة محظورة نهائيًا داخل بيئة Production، حتى لو تم تمرير متغيّر تفعيل لها.':'This tool is permanently blocked in Production, even if an enable flag is supplied.')
          : (ar
            ? <>الحذف معطّل افتراضيًا. يمكن تفعيله مؤقتًا في بيئة غير إنتاجية فقط عبر <code>ALLOW_DATA_RESET=true</code>، ثم إعادته إلى <code>false</code>.</>
            : <>Reset is disabled by default. It may be enabled temporarily only outside Production with <code>ALLOW_DATA_RESET=true</code>, then returned to <code>false</code>.</>)}
      </div>
    </Panel>}

    {blockers.length>0&&<Panel title={ar?'الحذف موقوف لحماية البيانات اليدوية':'Deletion blocked to protect manual data'} icon={<ShieldAlert size={18}/>}>
      <div style={{padding:14,color:'#991b1b',lineHeight:1.8}}>
        {ar?'توجد صفوف غير تجريبية تعتمد على بيانات Demo؛ لن يحذف النظام أي شيء حتى إزالة هذا الارتباط بصورة صحيحة.':'Unregistered rows depend on Demo records. Nothing can be deleted until that dependency is resolved safely.'}
      </div>
      <DataTable headers={[ar?'الارتباط':'Dependency',ar?'الصفوف':'Rows']} rows={blockers.map(([name,count])=>[name,String(count)])}/>
    </Panel>}

    <Panel title={ar?'صفوف Demo المسجلة التي ستُحذف':'Registered Demo rows to remove'} icon={<Eye size={18}/>}>
      {rows.length===0
        ? <div style={{padding:16,fontSize:14,opacity:0.8}}>{ar?'لا توجد بيانات Demo مسجلة في هذه الشركة — لا يوجد شيء مؤهل للحذف.':'No registered Demo data exists for this company — nothing is eligible for deletion.'}</div>
        : <DataTable headers={[ar?'الجدول':'Table',ar?'عدد الصفوف':'Rows']} rows={rows.map(([t,n])=>[t,String(n)])}/>}
    </Panel>

    {enabled&&rows.length>0&&blockers.length===0&&<Panel title={ar?'التنفيذ':'Execute'} icon={<Trash2 size={18}/>}>
      <div style={{padding:'6px 14px',fontSize:14,lineHeight:2,borderTop:'1px solid var(--border)'}}>
        <b>{ar?'الخطوة ١ — اكتب عبارة التأكيد كاملة:':'Step 1 — type the full confirmation phrase:'}</b><br/>
        {ar?'يجب أن تتطابق العبارة حرفيًا.':'It must match exactly.'}
        <div style={{marginTop:8,padding:'8px 12px',borderRadius:8,background:'var(--panel-2, #f1f5f9)',fontWeight:700,display:'inline-block'}}>{phrase}</div>
      </div>
      <div style={{padding:'0 14px 12px',maxWidth:420}}>
        <input style={field} value={confirmation} onChange={e=>{setConfirmation(e.target.value);setDryDone(false);setAuthorizationToken('')}}
          placeholder={ar?'اكتب عبارة التأكيد هنا':'Type the confirmation phrase'}/>
        {confirmation&&!matches&&<small style={{color:'#b91c1c'}}>{ar?'غير مطابق':'Does not match'}</small>}
        {matches&&<small style={{color:'#166534'}}>{ar?'✓ مطابق':'✓ matches'}</small>}
      </div>

      <div style={{padding:'12px 14px',fontSize:14,lineHeight:2,borderTop:'1px solid var(--border)'}}>
        <b>{ar?'الخطوة ٢ — فحص بلا حذف:':'Step 2 — dry run:'}</b><br/>
        {ar?'يثبت نطاق Demo ويصدر تفويضًا قصير العمر مرتبطًا بحسابك وهذه الشركة.':'Locks the Demo snapshot and issues a short-lived authorization bound to your account and this company.'}
      </div>
      <div style={{padding:'0 14px 12px'}}>
        <button style={{...btn,opacity:(busy||!matches)?0.6:1}} disabled={busy||!matches} onClick={()=>run(true)}>
          {ar?'تشغيل الفحص الآمن':'Run safe dry run'}
        </button>
      </div>

      <div style={{padding:'6px 14px 16px',borderTop:'1px solid var(--border)'}}>
        <div style={{fontSize:14,lineHeight:2,marginBottom:10}}>
          <b>{ar?'الخطوة ٣ — الحذف النهائي:':'Step 3 — delete for real:'}</b><br/>
          <span style={{color:'#b91c1c'}}>{ar?'لا رجعة في هذه الخطوة. التفويض يبطل إذا تغيّر نطاق Demo بعد الفحص.':'This cannot be undone. Authorization becomes invalid if the Demo snapshot changes after the dry run.'}</span>
        </div>
        <button style={{...danger,opacity:(busy||!matches||!dryDone||!authorizationToken)?0.5:1}}
          disabled={busy||!matches||!dryDone||!authorizationToken} onClick={()=>run(false)}>
          {ar?'حذف البيانات التجريبية نهائيًا':'Delete trial data permanently'}
        </button>
        {!dryDone&&<div style={{marginTop:8,fontSize:13,opacity:0.75}}>
          {ar?'شغّل التجربة أولًا لتفعيل هذا الزر.':'Run the dry run first to enable this button.'}
        </div>}
      </div>
    </Panel>}
  </>;
}
