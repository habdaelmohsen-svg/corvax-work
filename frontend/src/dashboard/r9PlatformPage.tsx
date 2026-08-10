import {useEffect, useState} from 'react';
import {Activity, Database, FileCheck2, RefreshCw, ShieldCheck, Upload} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

type Health={service:any;database:any;errors:any;backup:any;restore_drill:any;generated_at:string};
type Alert={id:number;category:string;severity:string;title_ar:string;title_en:string;status:string;detected_at:string};
type ImportPreview={id:number;target_type:string;status:string;total_rows:number;valid_rows:number;invalid_rows:number;posted_to_master:boolean;rows:any[]};
type Readiness={onboarding_status:string;environment:string;production_connected:boolean;seller_identity_ready:boolean;certificate_configured:boolean;signing_key_configured:boolean;sdk_validation_ready:boolean};

async function request(url:string,init?:RequestInit){
  const response=await apiFetch(url,init); const body=await response.json().catch(()=>({}));
  if(!response.ok) throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body));
  return body;
}
const button={padding:'9px 14px',border:0,borderRadius:9,background:'var(--accent,#1e40af)',color:'#fff',fontWeight:700,cursor:'pointer'} as const;
const field={width:'100%',padding:9,borderRadius:9,border:'1px solid var(--border)',background:'var(--panel)',color:'var(--text)'} as const;

export function R9PlatformPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'health'|'alerts'|'imports'|'zatca'>('health');
  const [health,setHealth]=useState<Health|null>(null); const [alerts,setAlerts]=useState<Alert[]>([]);
  const [readiness,setReadiness]=useState<Readiness|null>(null); const [preview,setPreview]=useState<ImportPreview|null>(null);
  const [batchId,setBatchId]=useState(''); const [target,setTarget]=useState('SUPPLIERS'); const [file,setFile]=useState<File|null>(null);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);

  const load=async()=>{
    const [h,a,z]=await Promise.all([
      request(`/api/v1/r9-platform/health?company_id=${companyId}`),
      request(`/api/v1/r9-platform/alerts?company_id=${companyId}`).catch(()=>[]),
      request(`/api/v1/r9-platform/zatca/readiness?company_id=${companyId}`).catch(()=>null),
    ]); setHealth(h); setAlerts(a); setReadiness(z);
  };
  useEffect(()=>{load().catch(e=>setMessage(e.message))},[companyId]);
  const act=async(fn:()=>Promise<any>,ok:string)=>{setBusy(true);setMessage('');try{const result=await fn();setMessage(ok);await load();return result}catch(e:any){setMessage(e.message||String(e))}finally{setBusy(false)}};
  const scan=()=>act(()=>request(`/api/v1/r9-platform/controls/scan?company_id=${companyId}`,{method:'POST'}),ar?'اكتمل الفحص الرقابي':'Control scan completed');
  const resolve=(id:number)=>act(()=>request(`/api/v1/r9-platform/alerts/${id}/resolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resolution_notes:ar?'تم تنفيذ الضابط والتحقق من دليل المعالجة':'Control performed and remediation evidence verified'})}),ar?'تم إغلاق التنبيه مع تسجيل الأثر':'Alert closed with audit evidence');
  const stage=()=>act(async()=>{if(!file)throw new Error(ar?'اختر ملف XLSX':'Select an XLSX file');const form=new FormData();form.append('file',file);const r=await request(`/api/v1/r9-platform/imports/stage?company_id=${companyId}&target_type=${target}`,{method:'POST',body:form});setBatchId(String(r.id));return r},ar?'تم الحفظ في منطقة التجهيز فقط — لم تُرحّل بيانات':'Staged only — no records posted');
  const inspect=()=>act(async()=>{const r=await request(`/api/v1/r9-platform/imports/${batchId}`);setPreview(r);return r},ar?'تم تحميل المعاينة':'Preview loaded');
  const validate=()=>act(async()=>{const r=await request(`/api/v1/r9-platform/imports/${batchId}/validate`,{method:'POST'});await inspect();return r},ar?'اكتمل التحقق':'Validation completed');
  const approve=()=>act(async()=>{const r=await request(`/api/v1/r9-platform/imports/${batchId}/approve`,{method:'POST'});await inspect();return r},ar?'اعتمدت منطقة التجهيز فقط — الترحيل يحتاج إجراء مستقل':'Staging approved — posting remains a separate controlled action');
  const saveReadiness=()=>act(()=>request(`/api/v1/r9-platform/zatca/readiness?company_id=${companyId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(readiness)}),ar?'حُفظت حالة الجاهزية الاختبارية':'Sandbox readiness saved');

  const tabs:[typeof tab,string][]=[['health',ar?'صحة النظام':'Health'],['alerts',ar?'الرقابة والتنبيهات':'Controls & alerts'],['imports',ar?'استيراد مضبوط':'Controlled import'],['zatca',ar?'جاهزية ZATCA':'ZATCA readiness']];
  return <>
    <div className="kpis">
      <Kpi title={ar?'حالة الخدمة':'Service'} value={health?.service?.status||'—'} trend={health?.service?.version||''} good={health?.service?.status==='UP'} icon={<Activity size={21}/>} tone="green"/>
      <Kpi title={ar?'قاعدة البيانات':'Database'} value={health?.database?.status||'—'} trend={health?.database?.migration_head||''} good={health?.database?.status==='UP'} icon={<Database size={21}/>} tone="blue"/>
      <Kpi title={ar?'تنبيهات مفتوحة':'Open alerts'} value={String(health?.errors?.open_control_alerts??'—')} trend={ar?'تحتاج مسؤولًا ودليل إغلاق':'ownership and evidence required'} good={(health?.errors?.open_control_alerts||0)===0} icon={<ShieldCheck size={21}/>} tone="amber"/>
      <Kpi title={ar?'اختبار الاستعادة':'Restore drill'} value={health?.restore_drill?.last_status||'—'} trend={health?.restore_drill?.environment||''} good={health?.restore_drill?.last_status==='PASSED'} icon={<RefreshCw size={21}/>} tone="violet"/>
    </div>
    <div style={{display:'flex',gap:8,flexWrap:'wrap',margin:'14px 0'}}>{tabs.map(([key,label])=><button key={key} style={{...button,background:tab===key?'var(--accent,#1e40af)':'transparent',color:tab===key?'#fff':'var(--text)',border:'1px solid var(--border)'}} onClick={()=>setTab(key)}>{label}</button>)}</div>
    {message&&<div style={{padding:11,borderRadius:9,marginBottom:12,background:'var(--panel-2,#eef2ff)'}}>{message}</div>}

    {tab==='health'&&<Panel title={ar?'مؤشرات تشغيلية بلا أسرار':'Secret-free operational metrics'} icon={<Activity size={18}/>}>
      <DataTable headers={[ar?'المؤشر':'Metric',ar?'القيمة':'Value']} rows={[
        [ar?'بيئة التشغيل':'Environment',health?.service?.environment||'—'],[ar?'نوع قاعدة البيانات':'Database driver',health?.database?.driver||'—'],
        [ar?'آخر نسخة احتياطية':'Latest backup',health?.backup?.last_status||'—'],[ar?'آخر تحقق':'Last verification',health?.backup?.last_verified_at||'—'],
        [ar?'أحداث فشل خلال 24 ساعة':'Failed events (24h)',String(health?.errors?.failed_audit_events_24h??'—')],
      ]}/>
    </Panel>}

    {tab==='alerts'&&<Panel title={ar?'فحص الضوابط وفصل المهام':'Control and SoD scan'} icon={<ShieldCheck size={18}/>}>
      <div style={{padding:12}}><button style={button} disabled={busy} onClick={scan}>{ar?'تشغيل الفحص الآن':'Run scan now'}</button></div>
      <DataTable headers={[ar?'الفئة':'Category',ar?'الخطورة':'Severity',ar?'التنبيه':'Alert',ar?'الحالة':'Status',ar?'إجراء':'Action']} rows={alerts.map(a=>[a.category,a.severity,ar?a.title_ar:a.title_en,a.status,a.status==='RESOLVED'?'✓':<button style={button} disabled={busy} onClick={()=>resolve(a.id)}>{ar?'إغلاق بدليل':'Resolve with evidence'}</button>])}/>
    </Panel>}

    {tab==='imports'&&<>
      <Panel title={ar?'رفع إلى منطقة تجهيز معزولة':'Upload to isolated staging'} icon={<Upload size={18}/>}><div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(210px,1fr))',gap:10,padding:12}}>
        <select style={field} value={target} onChange={e=>setTarget(e.target.value)}>{['SUPPLIERS','CUSTOMERS','ITEMS','OPENING_BALANCES'].map(x=><option key={x}>{x}</option>)}</select>
        <input style={field} type="file" accept=".xlsx" onChange={e=>setFile(e.target.files?.[0]||null)}/><button style={button} disabled={busy} onClick={stage}>{ar?'تجهيز فقط':'Stage only'}</button>
        <input style={field} value={batchId} onChange={e=>setBatchId(e.target.value)} placeholder={ar?'رقم الدفعة':'Batch ID'}/><button style={button} disabled={!batchId||busy} onClick={validate}>{ar?'تحقق':'Validate'}</button><button style={button} disabled={!batchId||busy} onClick={approve}>{ar?'اعتماد التجهيز':'Approve staging'}</button><button style={button} disabled={!batchId||busy} onClick={inspect}>{ar?'معاينة':'Preview'}</button>
      </div></Panel>
      {preview&&<Panel title={ar?'نتيجة الدفعة — لا يوجد ترحيل مباشر':'Batch result — no direct posting'} icon={<FileCheck2 size={18}/>}><DataTable headers={[ar?'الحالة':'Status',ar?'الكل':'Total',ar?'صحيح':'Valid',ar?'مرفوض':'Invalid',ar?'رُحّل؟':'Posted?']} rows={[[preview.status,String(preview.total_rows),String(preview.valid_rows),String(preview.invalid_rows),preview.posted_to_master?(ar?'نعم':'Yes'):(ar?'لا':'No')]]}/></Panel>}
    </>}

    {tab==='zatca'&&<Panel title={ar?'سجل الجاهزية — بيئة اختبار فقط':'Readiness register — sandbox only'} icon={<ShieldCheck size={18}/>}>
      <div style={{padding:12,lineHeight:1.9}}><strong>{ar?'تنبيه: هذه الشاشة لا تثبت الربط الإنتاجي أو قبول الفاتورة من الهيئة.':'This screen does not prove production connectivity or ZATCA acceptance.'}</strong>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:10,marginTop:12}}>
        <select style={field} value={readiness?.onboarding_status||'NOT_STARTED'} onChange={e=>setReadiness({...readiness!,onboarding_status:e.target.value})}>{['NOT_STARTED','PREPARING','SANDBOX_READY','SANDBOX_TESTED'].map(x=><option key={x}>{x}</option>)}</select>
        {([['seller_identity_ready',ar?'بيانات البائع جاهزة':'Seller identity ready'],['certificate_configured',ar?'الشهادة مهيأة':'Certificate configured'],['signing_key_configured',ar?'مفتاح التوقيع مهيأ':'Signing key configured'],['sdk_validation_ready',ar?'فحص SDK جاهز':'SDK validation ready']] as [keyof Readiness,string][]).map(([key,label])=><label key={key}><input type="checkbox" checked={Boolean(readiness?.[key])} onChange={e=>setReadiness({...readiness!,[key]:e.target.checked})}/> {label}</label>)}
        <button style={button} disabled={!readiness||busy} onClick={saveReadiness}>{ar?'حفظ حالة الاختبار':'Save sandbox status'}</button>
      </div></div>
    </Panel>}
  </>;
}
