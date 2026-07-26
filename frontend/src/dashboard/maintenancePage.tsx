import {useEffect, useState} from 'react';
import {Wrench, ClipboardList, AlertTriangle, CheckCircle2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Maintenance backend already exists at /risk-maintenance/maintenance/... (create/start/complete).
// H10 added the missing GET list endpoints at /departments/maintenance/... and this UI.
type Asset={id:number;code:string;name_ar:string;name_en:string;production_line?:string;meter_hours:number;criticality:string;status:string};
type WorkOrder={id:number;number:string;asset_name_ar?:string;work_type:string;priority:string;description:string;labor_cost:number;parts_cost:number;total_cost:number;downtime_minutes:number;status:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;

const CRITICALITY:[string,string,string][]=[['LOW','منخفضة','Low'],['MEDIUM','متوسطة','Medium'],['HIGH','عالية','High'],['CRITICAL','حرجة','Critical']];
const WORK_TYPES:[string,string,string][]=[['PREVENTIVE','وقائية','Preventive'],['CORRECTIVE','تصحيحية','Corrective'],['INSPECTION','فحص','Inspection'],['CALIBRATION','معايرة','Calibration']];

export function MaintenancePage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'assets'|'orders'>('assets');
  const [assets,setAssets]=useState<Asset[]>([]);
  const [orders,setOrders]=useState<WorkOrder[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  const [code,setCode]=useState(''); const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [line,setLine]=useState(''); const [crit,setCrit]=useState('MEDIUM');
  const [woAsset,setWoAsset]=useState(''); const [woType,setWoType]=useState('CORRECTIVE'); const [woPriority,setWoPriority]=useState('MEDIUM'); const [woDesc,setWoDesc]=useState('');
  const [cDowntime,setCDowntime]=useState('0'); const [cLabor,setCLabor]=useState('0'); const [cParts,setCParts]=useState('0');

  const load=async()=>{
    try{
      const [a,o]=await Promise.all([
        json(`/api/v1/departments/maintenance/assets?company_id=${companyId}`),
        json(`/api/v1/departments/maintenance/work-orders?company_id=${companyId}`),
      ]);
      setAssets(a||[]); setOrders(o||[]);
      if(!woAsset&&a?.length)setWoAsset(String(a[0].id));
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createAsset=async()=>{
    if(!code||!nameAr||!nameEn){setMessage(ar?'الكود والاسمان إلزامية':'Code and names required');return;}
    setBusy(true);setMessage('');
    try{await json('/api/v1/risk-maintenance/maintenance/assets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,code,name_ar:nameAr,name_en:nameEn,production_line:line||undefined,criticality:crit})});
      setMessage(ar?'تم إضافة الأصل':'Asset added');setCode('');setNameAr('');setNameEn('');setLine('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createOrder=async()=>{
    if(!woAsset||!woDesc){setMessage(ar?'اختر الأصل وأدخل الوصف':'Select asset and description');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/risk-maintenance/maintenance/work-orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,asset_id:Number(woAsset),work_type:woType,priority:woPriority,description:woDesc})});
      setMessage(ar?`تم إنشاء أمر العمل ${r.number}`:`Work order ${r.number} created`);setWoDesc('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const startOrder=async(id:number)=>{
    setBusy(true);setMessage('');
    try{await json(`/api/v1/risk-maintenance/maintenance/work-orders/${id}/start`,{method:'POST'});setMessage(ar?'بدأ التنفيذ':'Started');await load();}
    catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const completeOrder=async(id:number)=>{
    setBusy(true);setMessage('');
    try{await json(`/api/v1/risk-maintenance/maintenance/work-orders/${id}/complete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({downtime_minutes:Number(cDowntime),labor_cost:Number(cLabor),parts_cost:Number(cParts)})});
      setMessage(ar?'اكتمل أمر العمل':'Completed');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const label=(list:[string,string,string][],v:string)=>{const f=list.find(x=>x[0]===v);return f?(ar?f[1]:f[2]):v;};
  const openOrders=orders.filter(o=>o.status!=='COMPLETED'&&o.status!=='CANCELLED').length;
  const criticalAssets=assets.filter(a=>a.criticality==='CRITICAL').length;
  const totalCost=orders.reduce((s,o)=>s+Number(o.total_cost||0),0);

  return <>
    <div className="kpis">
      <Kpi title={ar?'الأصول':'Assets'} value={String(assets.length)} trend="" good icon={<Wrench size={22}/>} tone="blue"/>
      <Kpi title={ar?'أوامر عمل مفتوحة':'Open work orders'} value={String(openOrders)} trend="" good={openOrders===0} icon={<ClipboardList size={22}/>} tone="amber"/>
      <Kpi title={ar?'أصول حرجة':'Critical assets'} value={String(criticalAssets)} trend="" good icon={<AlertTriangle size={22}/>} tone="violet"/>
      <Kpi title={ar?'تكلفة الصيانة':'Maintenance cost'} value={fmt(totalCost)} trend="" good icon={<CheckCircle2 size={22}/>} tone="green"/>
    </div>
    <div style={{display:'flex',gap:8,margin:'14px 0'}}>
      {([['assets',ar?'الأصول':'Assets'],['orders',ar?'أوامر العمل':'Work orders']] as [typeof tab,string][]).map(([k,l])=>
        <button key={k} onClick={()=>setTab(k)} style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>
    {message&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {tab==='assets'&&<>
      <Panel title={ar?'أصل صيانة جديد':'New maintenance asset'} icon={<Wrench size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'الكود':'Code'}<input style={field} value={code} onChange={e=>setCode(e.target.value)}/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
          <label>{ar?'خط الإنتاج':'Production line'}<input style={field} value={line} onChange={e=>setLine(e.target.value)}/></label>
          <label>{ar?'الأهمية':'Criticality'}<select style={field} value={crit} onChange={e=>setCrit(e.target.value)}>{CRITICALITY.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createAsset}>{ar?'إضافة الأصل':'Add asset'}</button></div>
      </Panel>
      <Panel title={ar?'الأصول المسجّلة':'Registered assets'} icon={<ClipboardList size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'خط الإنتاج':'Line',ar?'ساعات التشغيل':'Meter hrs',ar?'الأهمية':'Criticality',ar?'الحالة':'Status']}
          rows={assets.map(a=>[a.code,ar?a.name_ar:a.name_en,a.production_line||'—',fmt(Number(a.meter_hours)),label(CRITICALITY,a.criticality),a.status])}/>
      </Panel>
    </>}

    {tab==='orders'&&<>
      <Panel title={ar?'أمر عمل جديد':'New work order'} icon={<ClipboardList size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'الأصل':'Asset'}<select style={field} value={woAsset} onChange={e=>setWoAsset(e.target.value)}>{assets.map(a=><option key={a.id} value={a.id}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}</select></label>
          <label>{ar?'نوع العمل':'Work type'}<select style={field} value={woType} onChange={e=>setWoType(e.target.value)}>{WORK_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'الأولوية':'Priority'}<select style={field} value={woPriority} onChange={e=>setWoPriority(e.target.value)}>{CRITICALITY.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'الوصف':'Description'}<input style={field} value={woDesc} onChange={e=>setWoDesc(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createOrder}>{ar?'إنشاء أمر العمل':'Create work order'}</button></div>
      </Panel>
      <Panel title={ar?'إكمال أمر عمل (التكلفة والتوقف)':'Complete work order (cost & downtime)'} icon={<CheckCircle2 size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',gap:12,padding:12}}>
          <label>{ar?'دقائق التوقف':'Downtime (min)'}<input type="number" style={field} value={cDowntime} onChange={e=>setCDowntime(e.target.value)}/></label>
          <label>{ar?'تكلفة العمالة':'Labor cost'}<input type="number" style={field} value={cLabor} onChange={e=>setCLabor(e.target.value)}/></label>
          <label>{ar?'تكلفة القطع':'Parts cost'}<input type="number" style={field} value={cParts} onChange={e=>setCParts(e.target.value)}/></label>
        </div>
      </Panel>
      <Panel title={ar?'أوامر العمل':'Work orders'} icon={<Wrench size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'الأصل':'Asset',ar?'النوع':'Type',ar?'الوصف':'Description',ar?'التكلفة':'Cost',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={orders.map(o=>[o.number,o.asset_name_ar||'—',label(WORK_TYPES,o.work_type),o.description,fmt(Number(o.total_cost)),o.status,
            o.status==='OPEN'?<button key={o.id} style={{...btn,padding:'5px 12px'}} disabled={busy} onClick={()=>startOrder(o.id)}>{ar?'بدء':'Start'}</button>:
            o.status==='IN_PROGRESS'?<button key={o.id} style={{...btn,padding:'5px 12px'}} disabled={busy} onClick={()=>completeOrder(o.id)}>{ar?'إكمال':'Complete'}</button>:'✓'])}/>
      </Panel>
    </>}
  </>;
}
