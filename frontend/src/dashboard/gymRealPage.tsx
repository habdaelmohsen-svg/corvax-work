import {useEffect, useState} from 'react';
import {Dumbbell, Plus, Users, CalendarClock, Lock, TrendingUp} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Gym operations: trainers, class types and sessions, lockers and PT packages.
//
// The accounting point that matters here is revenue recognition. A yearly
// membership or a ten-session PT package is NOT revenue on the day it is sold -
// it is deferred and released as the service is delivered. The screen states
// that plainly because getting it wrong inflates one month and empties the next.

type Branch={id:number;code:string;name_ar:string;name_en:string};
type Trainer={id:number;code:string;name_ar:string;name_en:string;commission_rate:number;active?:boolean};
type ClassType={id:number;code:string;name_ar:string;name_en:string;duration_minutes?:number;default_capacity?:number};
type Session={id:number;starts_at:string;capacity?:number;booked?:number;status?:string;
  class_type?:string;trainer?:string};
type Locker={id:number;code:string;status?:string;member?:string};
type Package={id:number;code:string;name_ar:string;name_en:string;sessions_count?:number;net_price?:number};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    const msg=typeof d==='string'?d:(d&&(d.message_ar||d.message_en))?(d.message_ar||d.message_en):JSON.stringify(d||x);
    throw new Error(msg);
  }
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(185px,1fr))',gap:12,padding:12} as const;

const localNow=()=>{
  const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset());
  return d.toISOString().slice(0,16);
};

export function GymPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'overview'|'trainers'|'classes'|'lockers'>('overview');
  const [branches,setBranches]=useState<Branch[]>([]);
  const [trainers,setTrainers]=useState<Trainer[]>([]);
  const [classTypes,setClassTypes]=useState<ClassType[]>([]);
  const [sessions,setSessions]=useState<Session[]>([]);
  const [lockers,setLockers]=useState<Locker[]>([]);
  const [packages,setPackages]=useState<Package[]>([]);
  const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  const [branch,setBranch]=useState('');
  // trainer
  const [tCode,setTCode]=useState(''); const [tAr,setTAr]=useState(''); const [tEn,setTEn]=useState(''); const [tRate,setTRate]=useState('10');
  // class type + session
  const [ctCode,setCtCode]=useState(''); const [ctAr,setCtAr]=useState(''); const [ctEn,setCtEn]=useState('');
  const [ctMin,setCtMin]=useState('60'); const [ctCap,setCtCap]=useState('20');
  const [sType,setSType]=useState(''); const [sTrainer,setSTrainer]=useState(''); const [sStart,setSStart]=useState(localNow());
  const [sCap,setSCap]=useState('');
  // locker
  const [lCode,setLCode]=useState('');

  const load=async()=>{
    try{
      const [br,tr,ct,ss,lk,pk,sm]=await Promise.all([
        json(`/api/v1/enterprise/companies/${companyId}/branches`).catch(()=>[]),
        json(`/api/v1/gym/trainers?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/class-types?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/class-sessions?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/lockers?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/pt-packages?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setBranches(Array.isArray(br)?br:[]); setTrainers(Array.isArray(tr)?tr:[]);
      setSessions(Array.isArray(ss)?ss:[]);
      setClassTypes(Array.isArray(ct)?ct:[]);
      setLockers(Array.isArray(lk)?lk:[]); setPackages(Array.isArray(pk)?pk:[]); setSummary(sm);
      if(!branch&&br?.length)setBranch(String(br[0].id));
      if(!sType&&Array.isArray(ct)&&ct.length)setSType(String(ct[0].id));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};
  const needBranch=()=>{if(!branch){bad({message:ar?'اختر الفرع أولًا':'Pick a branch first'});return true;}return false;};

  const addTrainer=async()=>{
    if(needBranch())return;
    if(!tCode||!tAr||!tEn){bad({message:ar?'أكمل بيانات المدرب':'Complete the trainer'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/gym/trainers',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,branch_id:Number(branch),code:tCode,
          name_ar:tAr,name_en:tEn,commission_rate:Number(tRate)||0})});
      ok(ar?`تم تسجيل المدرب ${tAr} بعمولة ${tRate}% — تُستحق عند تنفيذ الجلسة لا عند بيع الباقة`
           :`Trainer added at ${tRate}% — commission accrues when the session is delivered`);
      setTCode('');setTAr('');setTEn(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addClassType=async()=>{
    if(!ctCode||!ctAr||!ctEn){bad({message:ar?'أكمل بيانات نوع الحصة':'Complete the class type'});return;}
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/gym/class-types',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,code:ctCode,name_ar:ctAr,name_en:ctEn,
          duration_minutes:Number(ctMin)||60,default_capacity:Number(ctCap)||20})});
      ok(ar?'تم إنشاء نوع الحصة':'Class type created');
      setCtCode('');setCtAr('');setCtEn('');
      if(r?.id&&!sType)setSType(String(r.id));
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addSession=async()=>{
    if(needBranch())return;
    if(!sType||!sStart){bad({message:ar?'اختر نوع الحصة ووقتها':'Pick a class type and time'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,branch_id:Number(branch),class_type_id:Number(sType),
        starts_at:new Date(sStart).toISOString(),waitlist_enabled:true};
      if(sTrainer)body.trainer_id=Number(sTrainer);
      if(sCap)body.capacity=Number(sCap);
      await json('/api/v1/gym/class-sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(ar?'تم جدولة الحصة':'Session scheduled'); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addLocker=async()=>{
    if(needBranch())return;
    if(!lCode){bad({message:ar?'أدخل رقم الخزانة':'Enter a locker code'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/gym/lockers',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,branch_id:Number(branch),code:lCode})});
      ok(ar?`تمت إضافة الخزانة ${lCode}`:`Locker ${lCode} added`);
      setLCode(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const freeLockers=lockers.filter(l=>!l.member&&l.status!=='OCCUPIED').length;
  const upcoming=sessions.filter(s=>new Date(s.starts_at)>new Date()).length;

  return <>
    <div className="kpis">
      <Kpi title={ar?'المدربون':'Trainers'} value={String(trainers.length)} trend="" good icon={<Users size={22}/>} tone="blue"/>
      <Kpi title={ar?'حصص قادمة':'Upcoming classes'} value={String(upcoming)} trend={`${sessions.length} ${ar?'إجمالًا':'total'}`} good icon={<CalendarClock size={22}/>} tone="violet"/>
      <Kpi title={ar?'خزائن متاحة':'Free lockers'} value={String(freeLockers)} trend={`${lockers.length} ${ar?'إجمالًا':'total'}`} good={freeLockers>0} icon={<Lock size={22}/>} tone="green"/>
      <Kpi title={ar?'إيراد الفترة':'Period revenue'} value={summary?fmt(Number(summary.revenue||summary.total_revenue||0)):'—'} trend="" good icon={<TrendingUp size={22}/>} tone="amber"/>
    </div>

    <Panel title={ar?'الفرع':'Branch'} icon={<Dumbbell size={18}/>}>
      <div style={{padding:12,maxWidth:420}}>
        <label>{ar?'اختر الفرع — كل ما تنشئه يخصّه':'Branch — everything you create belongs to it'}
          <select style={field} value={branch} onChange={e=>setBranch(e.target.value)}>
            <option value="">{ar?'اختر...':'Select...'}</option>
            {branches.map(b=><option key={b.id} value={b.id}>{b.code} — {ar?b.name_ar:b.name_en}</option>)}
          </select></label>
      </div>
    </Panel>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['overview',ar?'نظرة عامة':'Overview'],['trainers',ar?'المدربون':'Trainers'],
         ['classes',ar?'الحصص':'Classes'],['lockers',ar?'الخزائن':'Lockers']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>setTab(k)}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.9,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab==='overview'&&<>
      <Panel title={ar?'الاعتراف بالإيراد — القاعدة المحاسبية':'Revenue recognition'} icon={<TrendingUp size={18}/>}>
        <div style={{padding:14,fontSize:14,lineHeight:2}}>
          {ar
            ? <>العضوية السنوية وباقة التدريب الشخصي <b>ليست إيرادًا يوم بيعها</b>. عند القبض تُسجَّل <b>إيرادات مؤجلة</b> (التزام)، ثم يُعترف بجزء منها شهريًا أو مع كل جلسة مُنفَّذة.
              <br/><br/>
              <b>لماذا؟</b> لأنك لم تقدّم الخدمة بعد. الاعتراف الكامل عند البيع <b>يضخّم إيراد الشهر ويفرغ الأشهر التالية</b>، فتظهر أرباح غير حقيقية ثم انهيار مفاجئ.
              <br/><br/>
              <b>وعمولة المدرب</b> تُستحق عند <b>تنفيذ</b> الجلسة لا عند بيع الباقة — وإلا دفعت عمولة على خدمة لم تُقدَّم.</>
            : <>A yearly membership or a PT package is not revenue on the sale date. Cash creates deferred revenue, released monthly or per delivered session. Recognising it all at once inflates one month and empties the next. Trainer commission accrues on delivery, not on sale.</>}
        </div>
      </Panel>
      <Panel title={ar?'مؤشرات تستحق المتابعة':'Metrics that matter'} icon={<Dumbbell size={18}/>}>
        <DataTable headers={[ar?'المؤشر':'Metric',ar?'المعادلة':'Formula',ar?'المعيار':'Benchmark']}
          rows={[
            [ar?'نسبة التجديد':'Renewal rate',ar?'المجدّدون ÷ المنتهية عضويتهم':'renewed / expired',ar?'أعلى من ٧٠٪':'> 70%'],
            [ar?'معدل الحضور':'Attendance',ar?'الزيارات ÷ عدد الأعضاء':'visits / members',ar?'يقيس التفاعل':'engagement'],
            [ar?'الإيراد لكل عضو':'Revenue per member',ar?'الإيراد ÷ الأعضاء':'revenue / members','—'],
            [ar?'إشغال الحصص':'Class fill rate',ar?'المحجوز ÷ السعة':'booked / capacity',ar?'أعلى من ٦٥٪':'> 65%'],
          ]}/>
        <div style={{padding:'0 14px 16px',fontSize:13,lineHeight:1.9,opacity:0.9}}>
          {ar?'⚠ نسبة تجديد منخفضة مع إيراد مرتفع تعني نموذجًا هشًّا: تعتمد على أعضاء جدد لتعويض المتسربين.'
             :'⚠ Low renewal with high revenue is a fragile model: new members are covering churn.'}
        </div>
      </Panel>
    </>}

    {tab==='trainers'&&<>
      <Panel title={ar?'مدرب جديد':'New trainer'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={tCode} onChange={e=>setTCode(e.target.value)} placeholder="TRN-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={tAr} onChange={e=>setTAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={tEn} onChange={e=>setTEn(e.target.value)}/></label>
          <label>{ar?'نسبة العمولة %':'Commission %'}<input type="number" step="0.5" style={field} value={tRate} onChange={e=>setTRate(e.target.value)}/>
            <small style={{opacity:0.75}}>{ar?'تُستحق عند تنفيذ الجلسة':'accrues on delivery'}</small></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addTrainer}>{ar?'تسجيل المدرب':'Add trainer'}</button>
        </div>
      </Panel>
      <Panel title={ar?'المدربون':'Trainers'} icon={<Users size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'العمولة':'Commission']}
          rows={trainers.map(t=>[t.code,ar?t.name_ar:t.name_en,`${t.commission_rate}%`])}/>
      </Panel>
    </>}

    {tab==='classes'&&<>
      <Panel title={ar?'نوع حصة جديد':'New class type'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={ctCode} onChange={e=>setCtCode(e.target.value)} placeholder="CLS-YOGA"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={ctAr} onChange={e=>setCtAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={ctEn} onChange={e=>setCtEn(e.target.value)}/></label>
          <label>{ar?'المدة (دقيقة)':'Duration (min)'}<input type="number" style={field} value={ctMin} onChange={e=>setCtMin(e.target.value)}/></label>
          <label>{ar?'السعة الافتراضية':'Default capacity'}<input type="number" style={field} value={ctCap} onChange={e=>setCtCap(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addClassType}>{ar?'إنشاء النوع':'Create type'}</button>
        </div>
      </Panel>
      <Panel title={ar?'جدولة حصة':'Schedule a session'} icon={<CalendarClock size={18}/>}>
        {classTypes.length===0
          ? <div style={{padding:16,fontSize:14}}>{ar?'أنشئ نوع حصة أولًا.':'Create a class type first.'}</div>
          : <>
            <div style={grid}>
              <label>{ar?'نوع الحصة':'Class type'}<select style={field} value={sType} onChange={e=>setSType(e.target.value)}>
                {classTypes.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
              <label>{ar?'المدرب':'Trainer'}<select style={field} value={sTrainer} onChange={e=>setSTrainer(e.target.value)}>
                <option value="">{ar?'— بلا مدرب —':'— none —'}</option>
                {trainers.map(t=><option key={t.id} value={t.id}>{ar?t.name_ar:t.name_en}</option>)}</select></label>
              <label>{ar?'وقت البدء':'Starts at'}<input type="datetime-local" style={field} value={sStart} onChange={e=>setSStart(e.target.value)}/></label>
              <label>{ar?'السعة (اختياري)':'Capacity'}<input type="number" style={field} value={sCap} onChange={e=>setSCap(e.target.value)}/></label>
            </div>
            <div style={{padding:'0 12px 14px'}}>
              <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addSession}>{ar?'جدولة':'Schedule'}</button>
            </div>
          </>}
      </Panel>
      <Panel title={ar?'الحصص':'Sessions'} icon={<CalendarClock size={18}/>}>
        <DataTable headers={[ar?'النوع':'Type',ar?'المدرب':'Trainer',ar?'الوقت':'Starts',ar?'السعة':'Capacity',ar?'الحالة':'Status']}
          rows={sessions.map(s=>[s.class_type||'—',s.trainer||'—',
            (s.starts_at||'').replace('T',' ').slice(0,16),String(s.capacity??'—'),s.status||'—'])}/>
      </Panel>
    </>}

    {tab==='lockers'&&<>
      <Panel title={ar?'خزانة جديدة':'New locker'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'رقم الخزانة':'Locker code'}<input style={field} value={lCode} onChange={e=>setLCode(e.target.value)} placeholder="L-101"/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addLocker}>{ar?'إضافة':'Add'}</button>
        </div>
      </Panel>
      <Panel title={ar?'الخزائن':'Lockers'} icon={<Lock size={18}/>}>
        <DataTable headers={[ar?'الرقم':'Code',ar?'الحالة':'Status',ar?'العضو':'Member']}
          rows={lockers.map(l=>[l.code,l.status||(ar?'متاحة':'Free'),l.member||'—'])}/>
      </Panel>
      <Panel title={ar?'باقات التدريب الشخصي':'PT packages'} icon={<Dumbbell size={18}/>}>
        {packages.length>0
          ? <DataTable headers={[ar?'الكود':'Code',ar?'الباقة':'Package',ar?'الجلسات':'Sessions',ar?'السعر':'Price']}
              rows={packages.map(p=>[p.code,ar?p.name_ar:p.name_en,String(p.sessions_count??'—'),fmt(Number(p.net_price||0))])}/>
          : <div style={{padding:16,fontSize:14,lineHeight:1.9,opacity:0.85}}>
              {ar?'لا توجد باقات تدريب شخصي نشطة لهذه الشركة.'
                 :'There are no active PT packages for this company.'}
            </div>}
        <div style={{padding:'0 14px 16px',fontSize:13,lineHeight:1.9,opacity:0.9}}>
          {ar?'الباقة تُباع مقدمًا وتُستهلك بالجلسة — إيرادها مؤجل يُعترف به مع كل جلسة مُنفَّذة.'
             :'A package is sold upfront and consumed per session; its revenue is deferred and released on delivery.'}
        </div>
      </Panel>
    </>}
  </>;
}
