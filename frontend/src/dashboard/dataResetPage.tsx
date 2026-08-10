import {useEffect, useState} from 'react';
import {Trash2, ShieldAlert, Eye, CheckCircle2, Lock, DatabaseZap} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

// System-wide UAT preparation.  The destructive path is deliberately gated:
// preview -> exact phrase -> dry run -> short-lived authorization -> execute.

async function json(url:string,init?:RequestInit){
  const response=await apiFetch(url,init); const payload=await response.json().catch(()=>({}));
  if(!response.ok){
    const detail=payload.detail;
    const message=typeof detail==='string' ? detail
      : (detail&&(detail.message_ar||detail.message_en)) ? detail.message_ar||detail.message_en
      : Array.isArray(detail) ? detail.map((item:any)=>item.msg||JSON.stringify(item)).join(' | ')
      : JSON.stringify(detail||payload);
    throw new Error(message);
  }
  return payload;
}

const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const danger={...btn,background:'#b91c1c'} as const;

export function DataResetPage({ar,companyId:_companyId}:{ar:boolean;companyId:number}){
  const [preview,setPreview]=useState<any>(null);
  const [confirmation,setConfirmation]=useState('');
  const [message,setMessage]=useState('');
  const [error,setError]=useState(false);
  const [busy,setBusy]=useState(false);
  const [dryDone,setDryDone]=useState(false);
  const [authorizationToken,setAuthorizationToken]=useState('');

  const load=async(clearStatus=true)=>{
    if(clearStatus){setMessage(''); setError(false)}
    try{
      const result=await json('/api/v1/data-reset/uat-preview');
      setPreview(result); setDryDone(false); setAuthorizationToken(''); setConfirmation('');
    }catch(caught:any){setMessage(String(caught.message||caught));setError(true)}
  };
  useEffect(()=>{void load()},[]);

  const run=async(dry:boolean)=>{
    setBusy(true); setMessage(''); setError(false);
    try{
      const result=await json('/api/v1/data-reset/uat-execute',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({confirmation,dry_run:dry,authorization_token:dry?undefined:authorizationToken}),
      });
      const successMessage=ar?result.message_ar:result.message_en;
      setMessage(successMessage);
      if(dry){setAuthorizationToken(result.authorization_token||'');setDryDone(Boolean(result.authorization_token))}
      else {
        setDryDone(false);setAuthorizationToken('');
        await load(false);
      }
    }catch(caught:any){setMessage(String(caught.message||caught));setError(true)}
    finally{setBusy(false)}
  };

  const phrase=preview?.confirmation_phrase||'';
  const matches=confirmation === phrase && phrase.length>0;
  const enabled=Boolean(preview?.enabled);
  const rows=Object.entries(preview?.tables||{}) as [string,number][];
  const preserved=preview?.preserved||{};

  return <>
    <div className="kpis">
      <Kpi title={ar?'صفوف ستُحذف':'Rows to remove'} value={String(preview?.total_rows??'—')} trend={ar?'جميع الشركات':'all companies'} good={(preview?.total_rows||0)===0} icon={<Trash2 size={22}/>} tone="amber"/>
      <Kpi title={ar?'جداول بها بيانات':'Non-empty tables'} value={String(preview?.tables_affected??'—')} trend={`${preview?.target_table_count??'—'} ${ar?'جدولًا مفحوصًا':'checked'}`} good icon={<Eye size={22}/>} tone="blue"/>
      <Kpi title={ar?'الشركات المحفوظة':'Companies retained'} value={String(preserved.companies??'—')} trend={ar?'لن تُحذف':'kept'} good icon={<CheckCircle2 size={22}/>} tone="green"/>
      <Kpi title={ar?'حسابات الدخول المحفوظة':'Users retained'} value={String(preserved.users??'—')} trend={enabled?(ar?'UAT مفعّل':'UAT enabled'):(ar?'الأداة مقفلة':'locked')} good={enabled} icon={<Lock size={22}/>} tone="violet"/>
    </div>

    {message&&<div style={{padding:11,margin:'12px 0',borderRadius:9,fontSize:14,lineHeight:1.8,
      background:error?'#fee2e2':'#dcfce7',color:error?'#991b1b':'#166534'}}>{message}</div>}

    <Panel title={ar?'تهيئة UAT الشاملة — ما الذي سيُحذف وما الذي سيبقى':'Full UAT preparation — removed vs retained'} icon={<DatabaseZap size={18}/> }>
      <div style={{padding:'10px 14px',display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(280px,1fr))',gap:14}}>
        <div style={{padding:13,borderRadius:10,background:'#fef2f2',color:'#7f1d1d',lineHeight:1.9,fontSize:13}}>
          <b>{ar?'يُحذف — كل بيانات التشغيل والتجربة':'Removed — all operational and test data'}</b><br/>
          {ar
            ? 'الحركات والقيود والمخزون والعملاء والموردون والأصناف والموظفون والرواتب والمشتريات والمبيعات والتصنيع والنادي والمطاعم والضرائب، في جميع الشركات.'
            : 'Transactions, journals, inventory, parties, items, employees, payroll, purchasing, sales, manufacturing, gym, restaurant and tax data across every company.'}
        </div>
        <div style={{padding:13,borderRadius:10,background:'#f0fdf4',color:'#14532d',lineHeight:1.9,fontSize:13}}>
          <b>{ar?'يبقى — أساس النظام والوصول':'Retained — system and access foundation'}</b><br/>
          {ar
            ? 'الشركات والفروع ودليل الحسابات ومراكز التكلفة والفترات المالية والمستخدمون والأدوار والصلاحيات وكلمات المرور وسجل التدقيق وسجل النسخ الاحتياطية.'
            : 'Companies, branches, chart of accounts, cost centers, fiscal periods, users, roles, permissions, password history, audit history and backup history.'}
        </div>
      </div>
    </Panel>

    {!enabled&&<Panel title={ar?'الأداة مقفلة':'The tool is locked'} icon={<Lock size={18}/> }>
      <div style={{padding:14,fontSize:14,lineHeight:2}}>
        {preview?.production_blocked
          ? (ar?'تهيئة UAT الشاملة محظورة في Production. يجب نشر خدمة الاختبار ببيئة UAT صريحة.':'Full UAT reset is blocked in Production. The test service must explicitly run as UAT.')
          : (ar?'الأداة تحتاج ENVIRONMENT=uat وALLOW_DATA_RESET=true، ولا تعمل لحساب غير مدير النظام.':'The tool requires ENVIRONMENT=uat and ALLOW_DATA_RESET=true, and only a system administrator may use it.')}
      </div>
    </Panel>}

    <Panel title={ar?'تفاصيل البيانات التي ستُمسح':'Operational data to be removed'} icon={<Eye size={18}/> }>
      {rows.length===0
        ? <div style={{padding:16,fontSize:14,opacity:0.8}}>{ar?'لا توجد بيانات تشغيل أو تجربة متبقية. النظام جاهز لإدخال بيانات UAT.':'No operational/test data remains. The system is ready for UAT data entry.'}</div>
        : <DataTable headers={[ar?'الجدول':'Table',ar?'عدد الصفوف':'Rows']} rows={rows.map(([table,count])=>[table,String(count)])}/>} 
    </Panel>

    {enabled&&rows.length>0&&<Panel title={ar?'التنفيذ المحمي':'Protected execution'} icon={<ShieldAlert size={18}/> }>
      <div style={{padding:'8px 14px',fontSize:14,lineHeight:2,color:'#991b1b',background:'#fff7ed'}}>
        <b>{ar?'تنبيه مهم:':'Important:'}</b>{' '}
        {ar?'هذه العملية شاملة لكل الشركات ولا يمكن التراجع عنها من داخل النظام. تأكد أنك تعمل على corvax-test وليس النظام الإنتاجي.':'This affects every company and cannot be undone in-app. Confirm that this is corvax-test, not production.'}
      </div>
      <div style={{padding:'10px 14px',fontSize:14,lineHeight:2,borderTop:'1px solid var(--border)'}}>
        <b>{ar?'الخطوة ١ — اكتب العبارة كاملة:':'Step 1 — type the full phrase:'}</b>
        <div style={{marginTop:8,padding:'8px 12px',borderRadius:8,background:'var(--panel-2, #f1f5f9)',fontWeight:700,display:'inline-block'}}>{phrase}</div>
      </div>
      <div style={{padding:'0 14px 12px',maxWidth:520}}>
        <input style={field} value={confirmation} onChange={(event)=>{setConfirmation(event.target.value);setDryDone(false);setAuthorizationToken('')}} placeholder={ar?'اكتب عبارة التأكيد هنا':'Type the confirmation phrase'}/>
        {confirmation&&!matches&&<small style={{color:'#b91c1c'}}>{ar?'غير مطابق':'Does not match'}</small>}
        {matches&&<small style={{color:'#166534'}}>{ar?'✓ مطابق':'✓ matches'}</small>}
      </div>

      <div style={{padding:'12px 14px',fontSize:14,lineHeight:2,borderTop:'1px solid var(--border)'}}>
        <b>{ar?'الخطوة ٢ — معاينة آمنة بلا حذف':'Step 2 — safe dry run'}</b><br/>
        {ar?'يثبت عدد الصفوف والجداول ويصدر تفويضًا مدته 10 دقائق مرتبطًا بحسابك.':'Locks the row/table snapshot and issues a 10-minute authorization bound to your account.'}
      </div>
      <div style={{padding:'0 14px 12px'}}><button style={{...btn,opacity:(busy||!matches)?0.6:1}} disabled={busy||!matches} onClick={()=>void run(true)}>{ar?'تشغيل المعاينة الآمنة':'Run safe dry run'}</button></div>

      <div style={{padding:'10px 14px 16px',borderTop:'1px solid var(--border)'}}>
        <b style={{fontSize:14}}>{ar?'الخطوة ٣ — المسح النهائي':'Step 3 — final reset'}</b><br/>
        <button style={{...danger,marginTop:10,opacity:(busy||!matches||!dryDone||!authorizationToken)?0.5:1}}
          disabled={busy||!matches||!dryDone||!authorizationToken} onClick={()=>void run(false)}>
          {ar?'مسح بيانات التشغيل وبدء UAT':'Clear operational data and start UAT'}
        </button>
        {!dryDone&&<div style={{marginTop:8,fontSize:13,opacity:0.75}}>{ar?'نفّذ المعاينة الآمنة أولًا لتفعيل الزر.':'Run the safe dry run first to enable this button.'}</div>}
      </div>
    </Panel>}
  </>;
}
