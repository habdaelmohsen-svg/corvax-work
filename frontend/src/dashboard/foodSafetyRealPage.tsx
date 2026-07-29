import {useEffect, useState} from 'react';
import {ShieldCheck, Plus, AlertTriangle, Thermometer, CheckCircle2, FileText} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

// HACCP in practice: a plan per product, hazards per process step, critical
// control points with limits, and a monitoring log that records every reading.
// The previous screen had no input fields at all - it only fired sample data.

type Plan={id:number;code:string;name_ar:string;name_en:string;version:number;status:string;
  effective_from:string;hazards?:Hazard[]};
type Hazard={id:number;step_number:number;process_step:string;hazard_type:string;
  hazard_description:string;likelihood:number;severity:number;is_ccp:boolean;
  critical_limit?:string;monitoring_frequency?:string};
type Item={id:number;code:string;name_ar:string;name_en:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    const msg=typeof d==='string'?d:(d&&(d.message_ar||d.message_en))?(d.message_ar||d.message_en):JSON.stringify(d||x);
    throw new Error(msg);
  }
  return x;
}
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'4px 11px',borderRadius:7,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(185px,1fr))',gap:12,padding:12} as const;

const HAZARD_TYPES:[string,string,string][]=[
  ['BIOLOGICAL','بيولوجي — بكتيريا وفيروسات','Biological'],
  ['CHEMICAL','كيميائي — بقايا مطهرات وأدوية','Chemical'],
  ['PHYSICAL','فيزيائي — معادن وزجاج وعظام','Physical'],
  ['ALLERGEN','مسبب حساسية','Allergen'],
];

export function FoodSafetyPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'plans'|'hazards'|'monitor'>('plans');
  const [plans,setPlans]=useState<Plan[]>([]);
  const [items,setItems]=useState<Item[]>([]);
  const [dash,setDash]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  // plan
  const [pCode,setPCode]=useState(''); const [pAr,setPAr]=useState(''); const [pEn,setPEn]=useState('');
  const [pItem,setPItem]=useState(''); const [pScope,setPScope]=useState(''); const [pUse,setPUse]=useState('');
  const [pFrom,setPFrom]=useState(iso());
  // hazard
  const [hPlan,setHPlan]=useState(''); const [hStep,setHStep]=useState('1'); const [hProcess,setHProcess]=useState('');
  const [hType,setHType]=useState('BIOLOGICAL'); const [hDesc,setHDesc]=useState('');
  const [hLike,setHLike]=useState('3'); const [hSev,setHSev]=useState('4');
  const [hControls,setHControls]=useState(''); const [hCcp,setHCcp]=useState(true);
  const [hLimit,setHLimit]=useState(''); const [hMethod,setHMethod]=useState(''); const [hFreq,setHFreq]=useState('');
  const [hAction,setHAction]=useState('');
  const [hVerify,setHVerify]=useState('');
  // monitoring
  const [mHazard,setMHazard]=useState(''); const [mValue,setMValue]=useState('');
  const [mWithin,setMWithin]=useState(true); const [mDeviation,setMDeviation]=useState(''); const [mCorrection,setMCorrection]=useState('');

  const load=async()=>{
    try{
      const [p,i,d]=await Promise.all([
        json(`/api/v1/food-safety/haccp-plans?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/items?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/food-safety/dashboard?company_id=${companyId}`).catch(()=>null),
      ]);
      setPlans(Array.isArray(p)?p:[]); setItems(Array.isArray(i)?i:[]); setDash(d);
      if(!hPlan&&p?.length)setHPlan(String(p[0].id));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};

  const createPlan=async()=>{
    if(!pCode||!pAr||!pEn||pScope.length<5){bad({message:ar?'أكمل البيانات — نطاق العملية ٥ أحرف على الأقل':'Complete the fields'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,code:pCode,name_ar:pAr,name_en:pEn,
        process_scope:pScope,effective_from:pFrom,version:1};
      if(pItem)body.product_item_id=Number(pItem);
      if(pUse)body.intended_use=pUse;
      const r=await json('/api/v1/food-safety/haccp-plans',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(ar?`تم إنشاء الخطة ${r.code||pCode} — أضف المخاطر ثم اعتمدها`:`Plan ${r.code||pCode} created — add hazards then approve`);
      setPCode('');setPAr('');setPEn('');setPScope(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const approvePlan=async(id:number)=>{
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/food-safety/haccp-plans/${id}/approve`,{method:'POST'});
      ok(ar?'تم اعتماد الخطة — صارت سارية':'Plan approved and in force'); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addHazard=async()=>{
    if(!hPlan||hProcess.length<2||hDesc.length<5||hControls.length<3){
      bad({message:ar?'أكمل الخطوة والوصف والضوابط':'Complete step, description and controls'});return;}
    // The backend refuses a CCP unless ALL five fields are present.
    if(hCcp&&!(hLimit&&hMethod&&hFreq&&hAction&&hVerify)){
      bad({message:ar
        ?'نقطة التحكم الحرجة تحتاج الخمسة: الحد الحرج، طريقة المراقبة، التكرار، الإجراء التصحيحي، وطريقة التحقق.'
        :'A CCP needs all five: critical limit, monitoring method, frequency, corrective action and verification method.'});
      return;}
    setBusy(true);setMsg('');
    try{
      const body:any={step_number:Number(hStep),process_step:hProcess,hazard_type:hType,
        hazard_description:hDesc,likelihood:Number(hLike),severity:Number(hSev),
        preventive_controls:hControls,is_ccp:hCcp};
      if(hCcp){
        body.critical_limit=hLimit;
        body.monitoring_method=hMethod;
        body.monitoring_frequency=hFreq;
        body.corrective_action=hAction;
        body.verification_method=hVerify;
      }
      await json(`/api/v1/food-safety/haccp-plans/${hPlan}/hazards`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(ar?`تمت إضافة الخطر${hCcp?' كنقطة تحكم حرجة':''}`:`Hazard added${hCcp?' as a CCP':''}`);
      setHProcess('');setHDesc('');setHControls('');setHLimit('');setHVerify(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const record=async()=>{
    if(!mHazard||!mValue){bad({message:ar?'اختر النقطة وأدخل القراءة':'Pick a CCP and enter the reading'});return;}
    if(!mWithin&&!mCorrection){bad({message:ar?'الانحراف يتطلب إجراءً تصحيحيًا فوريًا':'A deviation requires an immediate correction'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={measured_value:mValue,within_critical_limit:mWithin};
      if(!mWithin){body.deviation_details=mDeviation;body.immediate_correction=mCorrection;}
      await json(`/api/v1/food-safety/haccp-hazards/${mHazard}/monitor`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(mWithin?(ar?'تم تسجيل القراءة — ضمن الحد':'Reading recorded — within limit')
                :(ar?'⚠ سُجّل انحراف. اعزل المنتج المتأثر وقيّم صلاحيته قبل الإفراج.':'⚠ Deviation logged. Isolate the affected product and assess it before release.'));
      setMValue('');setMDeviation('');setMCorrection('');setMWithin(true); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const allHazards:Hazard[]=plans.flatMap(p=>(p.hazards||[]).map(h=>({...h})));
  const ccps=allHazards.filter(h=>h.is_ccp);
  const approved=plans.filter(p=>p.status==='APPROVED'||p.status==='ACTIVE').length;
  const risk=(h:Hazard)=>Number(h.likelihood||0)*Number(h.severity||0);

  return <>
    <div className="kpis">
      <Kpi title={ar?'خطط HACCP':'HACCP plans'} value={String(plans.length)} trend="" good icon={<ShieldCheck size={22}/>} tone="blue"/>
      <Kpi title={ar?'خطط معتمدة':'Approved'} value={String(approved)} trend="" good={approved>0} icon={<CheckCircle2 size={22}/>} tone="green"/>
      <Kpi title={ar?'نقاط تحكم حرجة':'CCPs'} value={String(ccps.length)} trend="" good icon={<Thermometer size={22}/>} tone="amber"/>
      <Kpi title={ar?'انحرافات مفتوحة':'Open deviations'} value={String(dash?.open_deviations ?? 0)} trend="" good={(dash?.open_deviations||0)===0} icon={<AlertTriangle size={22}/>} tone="violet"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['plans',ar?'الخطط':'Plans'],['hazards',ar?'المخاطر ونقاط التحكم':'Hazards & CCPs'],
         ['monitor',ar?'سجل المراقبة':'Monitoring log']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>setTab(k)}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.9,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab==='plans'&&<>
      <Panel title={ar?'خطة HACCP جديدة':'New HACCP plan'} icon={<Plus size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'خطة لكل منتج أو خط إنتاج. بعد إنشائها أضف مخاطر كل خطوة، وحدّد أيها نقطة تحكم حرجة بحد رقمي واضح، ثم اعتمدها لتصبح سارية.'
            : 'One plan per product or line. Add the hazards of each step, mark which are critical control points with a measurable limit, then approve it.'}
        </div>
        <div style={grid}>
          <label>{ar?'كود الخطة':'Plan code'}<input style={field} value={pCode} onChange={e=>setPCode(e.target.value)} placeholder="HACCP-CHK-01"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={pAr} onChange={e=>setPAr(e.target.value)} placeholder={ar?'خطة دجاج مبرّد':''}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={pEn} onChange={e=>setPEn(e.target.value)}/></label>
          <label>{ar?'المنتج (اختياري)':'Product'}<select style={field} value={pItem} onChange={e=>setPItem(e.target.value)}>
            <option value="">—</option>
            {items.map(i=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
          <label>{ar?'نطاق العملية':'Process scope'}<input style={field} value={pScope} onChange={e=>setPScope(e.target.value)}
            placeholder={ar?'من الاستلام حتى الشحن':'Receipt to dispatch'}/></label>
          <label>{ar?'الاستخدام المقصود':'Intended use'}<input style={field} value={pUse} onChange={e=>setPUse(e.target.value)}
            placeholder={ar?'للطهي قبل الاستهلاك':''}/></label>
          <label>{ar?'ساري من':'Effective from'}<input type="date" style={field} value={pFrom} onChange={e=>setPFrom(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createPlan}>{ar?'إنشاء الخطة':'Create plan'}</button>
        </div>
      </Panel>
      <Panel title={ar?'الخطط':'Plans'} icon={<FileText size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'الإصدار':'Ver',ar?'ساري من':'From',ar?'المخاطر':'Hazards',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={plans.map(p=>[p.code,ar?p.name_ar:p.name_en,String(p.version),p.effective_from,
            String((p.hazards||[]).length),p.status,
            p.status==='DRAFT'
              ? <button key={p.id} style={smallBtn} disabled={busy} onClick={()=>approvePlan(p.id)}>{ar?'اعتماد':'Approve'}</button>
              : '✓'])}/>
      </Panel>
    </>}

    {tab==='hazards'&&<>
      <Panel title={ar?'إضافة خطر لخطوة':'Add a hazard to a step'} icon={<AlertTriangle size={18}/>}>
        <div style={grid}>
          <label>{ar?'الخطة':'Plan'}<select style={field} value={hPlan} onChange={e=>setHPlan(e.target.value)}>
            {plans.map(p=><option key={p.id} value={p.id}>{p.code} — {ar?p.name_ar:p.name_en}</option>)}</select></label>
          <label>{ar?'رقم الخطوة':'Step no.'}<input type="number" min="1" style={field} value={hStep} onChange={e=>setHStep(e.target.value)}/></label>
          <label>{ar?'اسم الخطوة':'Process step'}<input style={field} value={hProcess} onChange={e=>setHProcess(e.target.value)}
            placeholder={ar?'استلام الدجاج الطازج':''}/></label>
          <label>{ar?'نوع الخطر':'Hazard type'}<select style={field} value={hType} onChange={e=>setHType(e.target.value)}>
            {HAZARD_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'وصف الخطر':'Description'}<input style={field} value={hDesc} onChange={e=>setHDesc(e.target.value)}
            placeholder={ar?'نمو السالمونيلا عند ارتفاع الحرارة':''}/></label>
          <label>{ar?'الاحتمالية (١-٥)':'Likelihood'}<input type="number" min="1" max="5" style={field} value={hLike} onChange={e=>setHLike(e.target.value)}/></label>
          <label>{ar?'الأثر (١-٥)':'Severity'}<input type="number" min="1" max="5" style={field} value={hSev} onChange={e=>setHSev(e.target.value)}/></label>
          <label>{ar?'الضوابط الوقائية':'Preventive controls'}<input style={field} value={hControls} onChange={e=>setHControls(e.target.value)}
            placeholder={ar?'قياس حرارة كل شحنة عند البوابة':''}/></label>
          <label style={{display:'flex',alignItems:'center',gap:8,marginTop:26}}>
            <input type="checkbox" checked={hCcp} onChange={e=>setHCcp(e.target.checked)}/>
            <b>{ar?'نقطة تحكم حرجة (CCP)':'Critical control point'}</b>
          </label>
        </div>
        {hCcp&&<div style={{margin:'0 12px 12px',padding:12,borderRadius:9,background:'#fef3c7',color:'#92400e'}}>
          <div style={{fontSize:13,lineHeight:1.9,marginBottom:8}}>
            {ar?'النقطة الحرجة تحتاج الخمسة كلها: حد قابل للقياس، طريقة مراقبة، تكرار، إجراء تصحيحي، وطريقة تحقق. النظام يرفضها ناقصة.'
               :'A CCP needs all five: a measurable limit, monitoring method, frequency, corrective action and verification. The system refuses an incomplete one.'}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:10}}>
            <label>{ar?'الحد الحرج':'Critical limit'}<input style={field} value={hLimit} onChange={e=>setHLimit(e.target.value)}
              placeholder={ar?'٠ إلى ٤ درجات مئوية':'0 to 4 °C'}/></label>
            <label>{ar?'طريقة المراقبة':'Monitoring method'}<input style={field} value={hMethod} onChange={e=>setHMethod(e.target.value)}
              placeholder={ar?'مقياس حرارة معايَر':''}/></label>
            <label>{ar?'التكرار':'Frequency'}<input style={field} value={hFreq} onChange={e=>setHFreq(e.target.value)}
              placeholder={ar?'كل شحنة / كل ساعتين':''}/></label>
            <label>{ar?'الإجراء التصحيحي':'Corrective action'}<input style={field} value={hAction} onChange={e=>setHAction(e.target.value)}
              placeholder={ar?'عزل الشحنة وتقييمها':''}/></label>
            <label>{ar?'طريقة التحقق':'Verification method'}<input style={field} value={hVerify} onChange={e=>setHVerify(e.target.value)}
              placeholder={ar?'مراجعة السجلات أسبوعيًا ومعايرة الأجهزة':'Weekly record review and calibration'}/></label>
          </div>
        </div>}
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addHazard}>{ar?'إضافة الخطر':'Add hazard'}</button>
        </div>
      </Panel>
      <Panel title={ar?'المخاطر ونقاط التحكم':'Hazards and CCPs'} icon={<AlertTriangle size={18}/>}>
        <DataTable headers={[ar?'الخطوة':'Step',ar?'العملية':'Process',ar?'النوع':'Type',ar?'الوصف':'Description',
          ar?'الدرجة':'Risk',ar?'حرجة؟':'CCP',ar?'الحد':'Limit']}
          rows={allHazards.map(h=>[String(h.step_number),h.process_step,h.hazard_type,h.hazard_description,
            `${risk(h)}`,h.is_ccp?(ar?'نعم':'Yes'):(ar?'لا':'No'),h.critical_limit||'—'])}/>
      </Panel>
    </>}

    {tab==='monitor'&&<>
      <Panel title={ar?'تسجيل قراءة مراقبة':'Record a monitoring reading'} icon={<Thermometer size={18}/>}>
        {ccps.length===0
          ? <div style={{padding:16,fontSize:14,lineHeight:1.9}}>
              {ar?'لا توجد نقاط تحكم حرجة بعد. أضف المخاطر وحدّد أيها حرجة أولًا.':'No CCPs yet. Add hazards and mark the critical ones first.'}
            </div>
          : <>
            <div style={grid}>
              <label>{ar?'نقطة التحكم':'Control point'}<select style={field} value={mHazard} onChange={e=>setMHazard(e.target.value)}>
                <option value="">{ar?'اختر...':'Select...'}</option>
                {ccps.map(h=><option key={h.id} value={h.id}>{h.process_step} — {h.critical_limit||''}</option>)}</select></label>
              <label>{ar?'القراءة الفعلية':'Measured value'}<input style={field} value={mValue} onChange={e=>setMValue(e.target.value)}
                placeholder={ar?'٣٫٥ درجة':'3.5 °C'}/></label>
              <label style={{display:'flex',alignItems:'center',gap:8,marginTop:26}}>
                <input type="checkbox" checked={mWithin} onChange={e=>setMWithin(e.target.checked)}/>
                {ar?'ضمن الحد الحرج':'Within the critical limit'}
              </label>
            </div>
            {!mWithin&&<div style={{margin:'0 12px 12px',padding:12,borderRadius:9,background:'#fee2e2',color:'#991b1b'}}>
              <div style={{fontSize:13,lineHeight:1.9,marginBottom:8}}>
                <b>{ar?'انحراف عن الحد الحرج':'Deviation from the critical limit'}</b><br/>
                {ar?'اعزل المنتج المتأثر فورًا، وسجّل الإجراء، ثم قيّم صلاحيته قبل أي إفراج.'
                   :'Isolate the affected product immediately, log the action, then assess it before any release.'}
              </div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:10}}>
                <label>{ar?'تفاصيل الانحراف':'Deviation details'}<input style={field} value={mDeviation} onChange={e=>setMDeviation(e.target.value)}/></label>
                <label>{ar?'الإجراء الفوري':'Immediate correction'}<input style={field} value={mCorrection} onChange={e=>setMCorrection(e.target.value)}/></label>
              </div>
            </div>}
            <div style={{padding:'0 12px 14px'}}>
              <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={record}>{ar?'تسجيل القراءة':'Record reading'}</button>
            </div>
          </>}
      </Panel>
      <Panel title={ar?'نقاط التحكم الحرجة السارية':'Active control points'} icon={<ShieldCheck size={18}/>}>
        <DataTable headers={[ar?'الخطوة':'Step',ar?'الحد الحرج':'Critical limit',ar?'التكرار':'Frequency']}
          rows={ccps.map(h=>[h.process_step,h.critical_limit||'—',h.monitoring_frequency||'—'])}/>
      </Panel>
    </>}
  </>;
}
