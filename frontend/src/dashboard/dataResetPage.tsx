import {useEffect, useState} from 'react';
import {AlertTriangle, CheckCircle2, Database, Eye, Lock, Trash2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

async function json(url:string,init?:RequestInit){
  const response=await apiFetch(url,init);
  const payload=await response.json().catch(()=>({}));
  if(!response.ok){
    const detail=payload.detail;
    const message=typeof detail==='string'?detail:detail?.message_ar||detail?.message_en||JSON.stringify(detail||payload);
    throw new Error(message);
  }
  return payload;
}

const field={display:'block',width:'100%',marginTop:7,padding:10,border:'1px solid var(--border)',borderRadius:9} as const;
const primary={padding:'10px 17px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:700} as const;
const danger={...primary,background:'#b91c1c'} as const;

export function DataResetPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [preview,setPreview]=useState<any>(null);
  const [confirmation,setConfirmation]=useState('');
  const [backupAcknowledged,setBackupAcknowledged]=useState(false);
  const [authorizationToken,setAuthorizationToken]=useState('');
  const [message,setMessage]=useState('');
  const [error,setError]=useState(false);
  const [busy,setBusy]=useState(false);

  const load=async(preserveMessage=false)=>{
    if(!preserveMessage){setMessage('');setError(false)}
    try{
      const result=await json(`/api/v1/uat-reset/preview?company_id=${companyId}`);
      setPreview(result);
      setAuthorizationToken('');
    }catch(e:any){setMessage(String(e.message||e));setError(true)}
  };
  useEffect(()=>{load()},[companyId]);

  const run=async(dryRun:boolean)=>{
    setBusy(true);setMessage('');setError(false);
    try{
      const result=await json('/api/v1/uat-reset/execute',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          company_id:companyId,
          confirmation,
          backup_acknowledged:backupAcknowledged,
          dry_run:dryRun,
          authorization_token:dryRun?undefined:authorizationToken,
        }),
      });
      setMessage(ar?result.message_ar:result.message_en);
      if(dryRun)setAuthorizationToken(result.authorization_token||'');
      else{
        setConfirmation('');setBackupAcknowledged(false);setAuthorizationToken('');
        await load(true);
      }
    }catch(e:any){setMessage(String(e.message||e));setError(true)}finally{setBusy(false)}
  };

  const phrase=preview?.confirmation_phrase||'';
  const matches=confirmation===phrase&&phrase.length>0;
  const enabled=Boolean(preview?.enabled);
  const rows=Object.entries(preview?.tables||{}) as [string,number][];
  const canPreview=enabled&&matches&&backupAcknowledged&&!busy;
  const canDelete=canPreview&&Boolean(authorizationToken);

  return <>
    <Panel title={ar?'مسح الحركات والقيم التجريبية':'Clear trial transactions and values'} icon={<Trash2 size={20}/>}>
      <div style={{padding:16,background:'#fff7ed',color:'#9a3412',lineHeight:1.9,fontWeight:600}}>
        <AlertTriangle size={18} style={{verticalAlign:'middle',marginInlineEnd:7}}/>
        {ar
          ? 'هذا الإجراء يحذف الحركات والأرصدة التجريبية فقط في جميع الشركات. تبقى بطاقات العملاء والموردين والأصناف والموظفين والمستودعات والبنوك والسيارات والآلات والأصول.'
          : 'This removes trial transactions and balances only across all companies. Customer, supplier, item, employee, warehouse, bank, vehicle, machine, and asset master cards remain.'}
      </div>
    </Panel>

    <div className="kpis">
      <Kpi title={ar?'صفوف حركات ستُحذف':'Transaction rows to delete'} value={String(preview?.transaction_rows??'—')} trend={ar?'كل الشركات':'all companies'} good={(preview?.transaction_rows||0)===0} icon={<Trash2 size={22}/>} tone="amber"/>
      <Kpi title={ar?'جداول بها بيانات':'Populated tables'} value={String(rows.length)} trend={ar?'بيانات أعمال':'business data'} good icon={<Database size={22}/>} tone="blue"/>
      <Kpi title={ar?'بطاقات أصول تُصفّر':'Asset cards reset to zero'} value={String(preview?.assets_to_reset??'—')} trend={ar?'البطاقة تبقى':'cards remain'} good icon={<CheckCircle2 size={22}/>} tone="green"/>
      <Kpi title={ar?'حالة الحذف':'Reset status'} value={enabled?(ar?'جاهز':'Ready'):(ar?'مقفول':'Locked')} trend="UAT only" good={enabled} icon={<Lock size={22}/>} tone="violet"/>
    </div>

    {message&&<div role="alert" style={{padding:12,margin:'12px 0',borderRadius:9,lineHeight:1.8,
      background:error?'#fee2e2':'#dcfce7',color:error?'#991b1b':'#166534'}}>{message}</div>}

    <Panel title={ar?'ما الذي يُحذف وما الذي يبقى':'Deletion boundary'} icon={<Eye size={18}/>}>
      <div style={{padding:14,display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(280px,1fr))',gap:12,lineHeight:1.9}}>
        <div style={{padding:13,borderRadius:10,background:'#fef2f2',color:'#7f1d1d'}}>
          <b>{ar?'يُحذف':'Deleted'}</b><br/>
          {ar?'الفواتير والقيود وسندات القبض والصرف وحركات المخزون والرواتب والتصنيع والحجوزات والتشغيل والضرائب. تُصفّر قيمة الأصل ومجمع الإهلاك وصافي القيمة مع بقاء بطاقة الأصل.':'Invoices, journals, receipts, payments, stock, payroll, production, bookings, operations, and tax activity. Asset cost, accumulated depreciation, and NBV reset to zero while the asset card remains.'}
        </div>
        <div style={{padding:13,borderRadius:10,background:'#f0fdf4',color:'#14532d'}}>
          <b>{ar?'يبقى':'Preserved'}</b><br/>
          {ar?'الشركات والفروع وشجرة الحسابات، والعملاء والموردون والأصناف والمستودعات والموظفون والبنوك والسيارات والآلات وبطاقات الأصول، والمستخدمون والصلاحيات وسجل التدقيق.':'Companies, branches, chart of accounts, customers, suppliers, items, warehouses, employees, banks, vehicles, machines, asset cards, users, permissions, and audit trail.'}
        </div>
      </div>
    </Panel>

    {!enabled&&<Panel title={ar?'الزر موجود لكن التنفيذ مقفول':'The button is visible but execution is locked'} icon={<Lock size={18}/> }>
      <div style={{padding:14,lineHeight:2}}>
        {ar?'فعّل في خدمة UAT فقط: ENVIRONMENT=uat و ALLOW_DATA_RESET=true. الإنتاج يرفض الحذف حتى لو ضُبط المتغير بالخطأ.':'Enable only in UAT with ENVIRONMENT=uat and ALLOW_DATA_RESET=true. Production always refuses this operation.'}
      </div>
    </Panel>}

    <Panel title={ar?'معاينة الحركات والقيم التي ستُمسح':'Preview transactions and values'} icon={<Database size={18}/> }>
      {rows.length===0&&!preview?.total_value_records?<div style={{padding:16}}>{ar?'لا توجد حركات أو قيم تجريبية؛ بيانات التأسيس جاهزة.':'No trial transactions or values remain; master data is ready.'}</div>:
        <DataTable headers={[ar?'الجدول':'Table',ar?'الصفوف':'Rows']} rows={rows.map(([table,count])=>[table,String(count)])}/>} 
    </Panel>

    {(rows.length>0||preview?.total_value_records>0)&&<Panel title={ar?'تنفيذ مسح الحركات والقيم':'Run transaction/value reset'} icon={<Trash2 size={18}/> }>
      <div style={{padding:14,lineHeight:2,maxWidth:720}}>
        <b>{ar?'1. اكتب عبارة التأكيد حرفيًا:':'1. Type the exact confirmation phrase:'}</b>
        <div style={{margin:'8px 0',padding:'8px 12px',borderRadius:8,background:'var(--panel-2, #f1f5f9)',fontWeight:800}}>{phrase}</div>
        <input style={field} value={confirmation} onChange={e=>{setConfirmation(e.target.value);setAuthorizationToken('')}} placeholder={ar?'اكتب العبارة هنا':'Type the phrase here'}/>
        <label style={{display:'flex',gap:9,alignItems:'flex-start',margin:'14px 0'}}>
          <input type="checkbox" checked={backupAcknowledged} onChange={e=>{setBackupAcknowledged(e.target.checked);setAuthorizationToken('')}} style={{marginTop:6}}/>
          <span>{ar?'أفهم أن الحذف غير قابل للتراجع من الشاشة، وقد أخذت نسخة احتياطية أو أقبل بدء UAT من جديد.':'I understand this cannot be undone from the UI and I have a backup or accept a fresh UAT start.'}</span>
        </label>
        <button style={{...primary,opacity:canPreview?1:.5}} disabled={!canPreview} onClick={()=>run(true)}>
          {ar?'2. معاينة آمنة وتفعيل زر الحذف':'2. Safe preview and unlock delete'}
        </button>
        <button style={{...danger,opacity:canDelete?1:.5,marginInlineStart:10}} disabled={!canDelete} onClick={()=>run(false)}>
          {ar?'3. مسح الحركات والقيم التجريبية الآن':'3. Clear trial transactions and values now'}
        </button>
        {!authorizationToken&&<div style={{marginTop:9,fontSize:13,opacity:.75}}>{ar?'زر الحذف النهائي يظهر هنا ويُفعّل بعد نجاح المعاينة الآمنة.':'The final delete button is here and unlocks after a successful safe preview.'}</div>}
      </div>
    </Panel>}
  </>;
}
