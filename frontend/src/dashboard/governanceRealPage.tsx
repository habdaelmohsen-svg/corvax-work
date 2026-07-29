import {useEffect, useState} from 'react';
import {ShieldAlert, Plus, ClipboardCheck, Search, TriangleAlert} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

// Risk register, the controls that answer each risk, and audit findings with a
// root cause. The previous screen fired samples and had no input fields.
//
// Risk score = likelihood x impact on a 1-5 scale, so 1..25. The bands below
// are the usual reading of that matrix.

type Risk={id:number;code:string;title_ar:string;title_en:string;category:string;
  likelihood:number;impact:number;inherent_score?:number;residual_score?:number;status?:string};
type Control={id:number;code:string;name_ar:string;name_en:string;control_type:string;
  frequency:string;design_status:string;operating_status:string};
type Finding={id:number;code:string;title_ar:string;title_en:string;severity:string;status?:string;root_cause?:string};
type Engagement={id:number;code?:string;title_ar?:string;name_ar?:string};

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

const CATEGORIES:[string,string,string][]=[
  ['OPERATIONAL','تشغيلي','Operational'],
  ['FINANCIAL','مالي','Financial'],
  ['COMPLIANCE','امتثال','Compliance'],
  ['STRATEGIC','استراتيجي','Strategic'],
  ['TECHNOLOGY','تقني','Technology'],
];
const CONTROL_TYPES:[string,string,string][]=[
  ['PREVENTIVE','وقائي — يمنع وقوع الخطر','Preventive'],
  ['DETECTIVE','كاشف — يكتشفه بعد وقوعه','Detective'],
  ['CORRECTIVE','تصحيحي — يعالج أثره','Corrective'],
];
const FREQUENCIES:[string,string][]=[['DAILY','يومي'],['WEEKLY','أسبوعي'],['MONTHLY','شهري'],['QUARTERLY','ربع سنوي'],['ANNUAL','سنوي']];
const SEVERITIES:[string,string][]=[['LOW','منخفضة'],['MEDIUM','متوسطة'],['HIGH','عالية'],['CRITICAL','حرجة']];

function band(score:number,ar:boolean){
  if(score>=20)return {label:ar?'حرج':'Critical',bg:'#fee2e2',fg:'#991b1b'};
  if(score>=12)return {label:ar?'عالٍ':'High',bg:'#fef3c7',fg:'#92400e'};
  if(score>=6)return {label:ar?'متوسط':'Medium',bg:'#e0f2fe',fg:'#075985'};
  return {label:ar?'منخفض':'Low',bg:'#dcfce7',fg:'#166534'};
}

export function AuditPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'risks'|'controls'|'findings'>('risks');
  const [risks,setRisks]=useState<Risk[]>([]);
  const [controls,setControls]=useState<Control[]>([]);
  const [findings,setFindings]=useState<Finding[]>([]);
  const [engagements,setEngagements]=useState<Engagement[]>([]);
  const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  // risk
  const [rCode,setRCode]=useState(''); const [rAr,setRAr]=useState(''); const [rEn,setREn]=useState('');
  const [rCat,setRCat]=useState('OPERATIONAL'); const [rLike,setRLike]=useState('3'); const [rImp,setRImp]=useState('3');
  const [rDesc,setRDesc]=useState('');
  // control
  const [cCode,setCCode]=useState(''); const [cAr,setCAr]=useState(''); const [cEn,setCEn]=useState('');
  const [cRisk,setCRisk]=useState(''); const [cType,setCType]=useState('PREVENTIVE'); const [cFreq,setCFreq]=useState('MONTHLY');
  // finding
  const [fEng,setFEng]=useState(''); const [fCode,setFCode]=useState(''); const [fAr,setFAr]=useState(''); const [fEn,setFEn]=useState('');
  const [fSev,setFSev]=useState('MEDIUM'); const [fDesc,setFDesc]=useState(''); const [fRoot,setFRoot]=useState(''); const [fRec,setFRec]=useState('');

  const load=async()=>{
    try{
      const [rk,ct,fd,en,sm]=await Promise.all([
        json(`/api/v1/governance/risks?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/governance/controls?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/governance/findings?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/governance/audits?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/governance/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setRisks(Array.isArray(rk)?rk:[]); setControls(Array.isArray(ct)?ct:[]);
      setFindings(Array.isArray(fd)?fd:[]); setEngagements(Array.isArray(en)?en:[]); setSummary(sm);
      if(!fEng&&en?.length)setFEng(String(en[0].id));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};

  const addRisk=async()=>{
    if(!rCode||!rAr||!rEn){bad({message:ar?'الكود والعنوانان إلزامية':'Code and both titles are required'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,code:rCode,title_ar:rAr,title_en:rEn,category:rCat,
        likelihood:Number(rLike),impact:Number(rImp)};
      if(rDesc)body.description=rDesc;
      await json('/api/v1/governance/risks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const sc=Number(rLike)*Number(rImp); const b=band(sc,ar);
      ok(ar?`تم تسجيل الخطر بدرجة ${sc} (${b.label}) — أضف ضابطًا يعالجه`
           :`Risk logged at ${sc} (${b.label}) — now add a control`);
      setRCode('');setRAr('');setREn('');setRDesc(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addControl=async()=>{
    if(!cCode||!cAr||!cEn){bad({message:ar?'أكمل بيانات الضابط':'Complete the control'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,code:cCode,name_ar:cAr,name_en:cEn,
        control_type:cType,frequency:cFreq,design_status:'EFFECTIVE',operating_status:'NOT_TESTED'};
      if(cRisk)body.risk_id=Number(cRisk);
      await json('/api/v1/governance/controls',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(ar?'تم تسجيل الضابط':'Control registered');
      setCCode('');setCAr('');setCEn(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addFinding=async()=>{
    if(!fEng||!fCode||!fAr||!fEn||fDesc.length<2){bad({message:ar?'أكمل البيانات واختر مهمة المراجعة':'Complete the fields and pick an engagement'});return;}
    if(!fRoot){bad({message:ar?'السبب الجذري إلزامي — بدونه تتكرر الملاحظة':'A root cause is required, otherwise the finding repeats'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/governance/findings',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,engagement_id:Number(fEng),code:fCode,
          title_ar:fAr,title_en:fEn,severity:fSev,description:fDesc,root_cause:fRoot,recommendation:fRec})});
      ok(ar?'تم تسجيل الملاحظة':'Finding recorded');
      setFCode('');setFAr('');setFEn('');setFDesc('');setFRoot('');setFRec(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const score=(r:Risk)=>Number(r.inherent_score||Number(r.likelihood||0)*Number(r.impact||0));
  const critical=risks.filter(r=>score(r)>=20).length;
  const high=risks.filter(r=>{const s=score(r);return s>=12&&s<20;}).length;
  const untested=controls.filter(c=>c.operating_status==='NOT_TESTED').length;
  const openFindings=findings.filter(f=>f.status!=='CLOSED').length;

  return <>
    <div className="kpis">
      <Kpi title={ar?'المخاطر المسجّلة':'Risks'} value={String(risks.length)} trend={`${critical} ${ar?'حرجة':'critical'}`} good={critical===0} icon={<ShieldAlert size={22}/>} tone={critical>0?'amber':'blue'}/>
      <Kpi title={ar?'مخاطر عالية':'High risks'} value={String(high)} trend="" good={high===0} icon={<TriangleAlert size={22}/>} tone="violet"/>
      <Kpi title={ar?'الضوابط':'Controls'} value={String(controls.length)} trend={`${untested} ${ar?'بلا اختبار':'untested'}`} good={untested===0} icon={<ClipboardCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'ملاحظات مفتوحة':'Open findings'} value={String(openFindings)} trend="" good={openFindings===0} icon={<Search size={22}/>} tone="amber"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['risks',ar?'سجل المخاطر':'Risk register'],['controls',ar?'الضوابط':'Controls'],
         ['findings',ar?'ملاحظات المراجعة':'Audit findings']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>setTab(k)}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.9,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab==='risks'&&<>
      <Panel title={ar?'تسجيل خطر':'Register a risk'} icon={<Plus size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'الدرجة = الاحتمالية × الأثر، من ١ إلى ٢٥. ما درجته ٢٠ فأكثر يحتاج معالجة فورية، و١٢-١٦ خطة بموعد، وما دون ذلك مراقبة. لا تسجّل خطرًا بلا ضابط يعالجه.'
            : 'Score = likelihood x impact, 1..25. Twenty and above needs immediate action, 12-16 a dated plan, below that monitoring. A risk without a control is just a note.'}
        </div>
        <div style={grid}>
          <label>{ar?'كود الخطر':'Code'}<input style={field} value={rCode} onChange={e=>setRCode(e.target.value)} placeholder="RSK-001"/></label>
          <label>{ar?'العنوان (عربي)':'Title (Arabic)'}<input style={field} value={rAr} onChange={e=>setRAr(e.target.value)} placeholder={ar?'عطل غرفة التبريد':''}/></label>
          <label>{ar?'العنوان (إنجليزي)':'Title (English)'}<input style={field} value={rEn} onChange={e=>setREn(e.target.value)}/></label>
          <label>{ar?'التصنيف':'Category'}<select style={field} value={rCat} onChange={e=>setRCat(e.target.value)}>
            {CATEGORIES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'الاحتمالية (١-٥)':'Likelihood'}<input type="number" min="1" max="5" style={field} value={rLike} onChange={e=>setRLike(e.target.value)}/></label>
          <label>{ar?'الأثر (١-٥)':'Impact'}<input type="number" min="1" max="5" style={field} value={rImp} onChange={e=>setRImp(e.target.value)}/></label>
          <label>{ar?'الوصف':'Description'}<input style={field} value={rDesc} onChange={e=>setRDesc(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px',display:'flex',alignItems:'center',gap:14,flexWrap:'wrap'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addRisk}>{ar?'تسجيل الخطر':'Register'}</button>
          {(()=>{const sc=Number(rLike)*Number(rImp); const b=band(sc,ar);
            return <span style={{padding:'6px 12px',borderRadius:999,background:b.bg,color:b.fg,fontWeight:700,fontSize:13}}>
              {ar?`الدرجة ${sc} — ${b.label}`:`Score ${sc} — ${b.label}`}</span>;})()}
        </div>
      </Panel>
      <Panel title={ar?'سجل المخاطر':'Risk register'} icon={<ShieldAlert size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الخطر':'Risk',ar?'التصنيف':'Category',
          ar?'الاحتمالية':'Likelihood',ar?'الأثر':'Impact',ar?'الدرجة':'Score',ar?'المستوى':'Band']}
          rows={risks.map(r=>{const s=score(r); const b=band(s,ar);
            return [r.code,ar?r.title_ar:r.title_en,r.category,String(r.likelihood),String(r.impact),String(s),
              <span key={r.id} style={{padding:'2px 9px',borderRadius:999,background:b.bg,color:b.fg,fontWeight:700,fontSize:12}}>{b.label}</span>];})}/>
      </Panel>
    </>}

    {tab==='controls'&&<>
      <Panel title={ar?'تسجيل ضابط':'Register a control'} icon={<Plus size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'الوقائي يمنع الخطر قبل وقوعه، والكاشف يكتشفه بعده، والتصحيحي يعالج أثره. اربط كل ضابط بالخطر الذي يعالجه ليظهر أي خطر بقي بلا حماية.'
            : 'Preventive stops the risk, detective finds it afterwards, corrective repairs the damage. Link each control to its risk so uncovered risks stand out.'}
        </div>
        <div style={grid}>
          <label>{ar?'كود الضابط':'Code'}<input style={field} value={cCode} onChange={e=>setCCode(e.target.value)} placeholder="CTL-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={cAr} onChange={e=>setCAr(e.target.value)} placeholder={ar?'قياس حرارة الغرف كل ساعتين':''}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={cEn} onChange={e=>setCEn(e.target.value)}/></label>
          <label>{ar?'الخطر المرتبط':'Linked risk'}<select style={field} value={cRisk} onChange={e=>setCRisk(e.target.value)}>
            <option value="">{ar?'— بلا ربط —':'— none —'}</option>
            {risks.map(r=><option key={r.id} value={r.id}>{r.code} — {ar?r.title_ar:r.title_en}</option>)}</select></label>
          <label>{ar?'نوع الضابط':'Type'}<select style={field} value={cType} onChange={e=>setCType(e.target.value)}>
            {CONTROL_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'التكرار':'Frequency'}<select style={field} value={cFreq} onChange={e=>setCFreq(e.target.value)}>
            {FREQUENCIES.map(([v,a])=><option key={v} value={v}>{ar?a:v}</option>)}</select></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addControl}>{ar?'تسجيل الضابط':'Register'}</button>
        </div>
      </Panel>
      <Panel title={ar?'الضوابط':'Controls'} icon={<ClipboardCheck size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الضابط':'Control',ar?'النوع':'Type',ar?'التكرار':'Frequency',ar?'التصميم':'Design',ar?'التشغيل':'Operating']}
          rows={controls.map(c=>[c.code,ar?c.name_ar:c.name_en,
            (CONTROL_TYPES.find(t=>t[0]===c.control_type)||[])[ar?1:2]?.split(' —')[0]||c.control_type,
            (FREQUENCIES.find(f=>f[0]===c.frequency)||[])[ar?1:0]||c.frequency,
            c.design_status,c.operating_status])}/>
      </Panel>
    </>}

    {tab==='findings'&&<>
      <Panel title={ar?'تسجيل ملاحظة':'Record a finding'} icon={<Plus size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'السبب الجذري إلزامي هنا. ملاحظة «خطأ في القيد» بلا سبب جذري تتكرر كل شهر، أما «خطأ لعدم وجود مراجعة قبل الترحيل» فتقود إلى ضابط يمنع التكرار.'
            : 'The root cause is mandatory. "Posting error" repeats forever; "posting error because no review existed before posting" leads to a control.'}
        </div>
        {engagements.length===0
          ? <div style={{padding:16,fontSize:14,lineHeight:1.9}}>
              {ar?'لا توجد مهام مراجعة بعد. الملاحظة تُسجَّل ضمن مهمة مراجعة — أنشئ مهمة أولًا.'
                 :'No audit engagements yet. A finding belongs to an engagement — create one first.'}
            </div>
          : <>
            <div style={grid}>
              <label>{ar?'مهمة المراجعة':'Engagement'}<select style={field} value={fEng} onChange={e=>setFEng(e.target.value)}>
                {engagements.map(e=><option key={e.id} value={e.id}>{e.code||e.title_ar||e.name_ar||`#${e.id}`}</option>)}</select></label>
              <label>{ar?'كود الملاحظة':'Code'}<input style={field} value={fCode} onChange={e=>setFCode(e.target.value)} placeholder="FND-001"/></label>
              <label>{ar?'العنوان (عربي)':'Title (Arabic)'}<input style={field} value={fAr} onChange={e=>setFAr(e.target.value)}/></label>
              <label>{ar?'العنوان (إنجليزي)':'Title (English)'}<input style={field} value={fEn} onChange={e=>setFEn(e.target.value)}/></label>
              <label>{ar?'الخطورة':'Severity'}<select style={field} value={fSev} onChange={e=>setFSev(e.target.value)}>
                {SEVERITIES.map(([v,a])=><option key={v} value={v}>{ar?a:v}</option>)}</select></label>
              <label>{ar?'الوصف':'Description'}<input style={field} value={fDesc} onChange={e=>setFDesc(e.target.value)}/></label>
              <label>{ar?'السبب الجذري':'Root cause'}<input style={field} value={fRoot} onChange={e=>setFRoot(e.target.value)}
                placeholder={ar?'لماذا حدث؟ لا ماذا حدث':'why, not what'}/></label>
              <label>{ar?'التوصية':'Recommendation'}<input style={field} value={fRec} onChange={e=>setFRec(e.target.value)}/></label>
            </div>
            <div style={{padding:'0 12px 14px'}}>
              <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addFinding}>{ar?'تسجيل الملاحظة':'Record'}</button>
            </div>
          </>}
      </Panel>
      <Panel title={ar?'الملاحظات':'Findings'} icon={<Search size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الملاحظة':'Finding',ar?'الخطورة':'Severity',ar?'السبب الجذري':'Root cause',ar?'الحالة':'Status']}
          rows={findings.map(f=>[f.code,ar?f.title_ar:f.title_en,
            (SEVERITIES.find(s=>s[0]===f.severity)||[])[ar?1:0]||f.severity,
            f.root_cause||'—',f.status||'OPEN'])}/>
      </Panel>
    </>}
  </>;
}
