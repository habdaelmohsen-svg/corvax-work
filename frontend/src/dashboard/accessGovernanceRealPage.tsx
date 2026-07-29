import {useEffect, useState} from 'react';
import {UserCheck, Plus, ScanSearch, ShieldAlert, CheckCircle2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

// Segregation of duties in practice: rules that name two permissions nobody may
// hold together, a scan that finds who holds both, and a decision on each
// conflict - mitigate with a compensating control, or remove the access.
//
// The previous screen fired samples with no inputs, so the rules could never be
// written and the scan could never be run.

type Rule={id:number;code:string;name_ar:string;name_en:string;permission_a:string;
  permission_b:string;severity:string;rationale?:string;active?:boolean};
type Conflict={id:number;user_id:number;user:string;rule_code:string;severity:string;
  permission_a:string;permission_b:string;status:string;mitigating_control?:string;remediation_due_date?:string};

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
const smallBtn={padding:'4px 11px',borderRadius:7,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(185px,1fr))',gap:12,padding:12} as const;

const SEVERITIES:[string,string][]=[['LOW','منخفضة'],['MEDIUM','متوسطة'],['HIGH','عالية'],['CRITICAL','حرجة']];

// Conflicts that matter in an accounting system, offered as one-click templates.
const TEMPLATES:{code:string;ar:string;en:string;a:string;b:string;sev:string;why:string}[]=[
  {code:'SOD-JE-APPROVE',ar:'إعداد القيود واعتمادها',en:'Post and approve journals',
   a:'finance.manage',b:'finance.approve',sev:'CRITICAL',
   why:'من يُعِدّ القيد لا يعتمده، وإلا أمكن ترحيل قيد وهمي بلا رقابة.'},
  {code:'SOD-PO-RECEIVE',ar:'إصدار أمر الشراء وإثبات الاستلام',en:'Raise and receive purchase orders',
   a:'inventory.manage',b:'inventory.receive',sev:'HIGH',
   why:'من يطلب البضاعة لا يشهد باستلامها، وإلا أمكن إثبات استلام لم يحدث.'},
  {code:'SOD-VENDOR-PAY',ar:'إنشاء مورد وصرف دفعة له',en:'Create supplier and pay it',
   a:'subledgers.manage',b:'banking.pay',sev:'CRITICAL',
   why:'من ينشئ المورد لا يصرف له، وإلا أمكن إنشاء مورد وهمي والدفع إليه.'},
  {code:'SOD-PAYROLL',ar:'إعداد الرواتب واعتمادها',en:'Prepare and approve payroll',
   a:'payroll.manage',b:'payroll.approve',sev:'CRITICAL',
   why:'من يُعِدّ المسيّر لا يعتمده، وإلا أمكن إضافة موظف وهمي.'},
  {code:'SOD-USER-ADMIN',ar:'منح الصلاحيات واستخدامها ماليًا',en:'Grant access and use it',
   a:'admin.users',b:'finance.manage',sev:'HIGH',
   why:'من يمنح الصلاحيات لا يملك صلاحية مالية، وإلا منح نفسه ما يشاء.'},
];

export function AccessGovernancePage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'conflicts'|'rules'>('conflicts');
  const [rules,setRules]=useState<Rule[]>([]);
  const [conflicts,setConflicts]=useState<Conflict[]>([]);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  const [code,setCode]=useState(''); const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [permA,setPermA]=useState(''); const [permB,setPermB]=useState('');
  const [sev,setSev]=useState('HIGH'); const [why,setWhy]=useState('');
  const [mitigation,setMitigation]=useState('');

  const load=async()=>{
    try{
      const [rl,cf]=await Promise.all([
        json(`/api/v1/access-governance/sod-rules?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/access-governance/conflicts?company_id=${companyId}`).catch(()=>[]),
      ]);
      setRules(Array.isArray(rl)?rl:[]); setConflicts(Array.isArray(cf)?cf:[]);
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};

  const useTemplate=(t:typeof TEMPLATES[0])=>{
    setCode(t.code);setNameAr(t.ar);setNameEn(t.en);setPermA(t.a);setPermB(t.b);setSev(t.sev);setWhy(t.why);
    setTab('rules');
  };

  const addRule=async()=>{
    if(!code||!nameAr||!nameEn||!permA||!permB||why.length<5){
      bad({message:ar?'أكمل البيانات — والمبرر ٥ أحرف على الأقل':'Complete the fields; the rationale needs 5+ characters'});return;}
    if(permA===permB){bad({message:ar?'الصلاحيتان متطابقتان':'The two permissions are identical'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/access-governance/sod-rules',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({code,name_ar:nameAr,name_en:nameEn,permission_a:permA,
          permission_b:permB,severity:sev,rationale:why})});
      ok(ar?`تمت إضافة القاعدة ${code} — شغّل الفحص لاكتشاف من يجمع بين الصلاحيتين`
           :`Rule ${code} added — run the scan to find who holds both`);
      setCode('');setNameAr('');setNameEn('');setPermA('');setPermB('');setWhy(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const scan=async()=>{
    setBusy(true);setMsg('');
    try{
      const r=await json(`/api/v1/access-governance/scan/${companyId}`,{method:'POST'});
      const n=Number(r.new_conflicts||0), t=Number(r.open_or_mitigated_conflicts||0);
      ok(ar?(n>0?`اكتُشف ${n} تعارضًا جديدًا. الإجمالي المفتوح ${t} — عالجها فورًا.`
                :`لا تعارضات جديدة. الإجمالي المفتوح ${t}.`)
           :(n>0?`${n} new conflicts found, ${t} open in total.`:`No new conflicts. ${t} open.`));
      setErr(n>0); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const mitigate=async(id:number)=>{
    if(!mitigation){bad({message:ar?'اكتب الضابط التعويضي في الحقل أعلى الجدول أولًا':'Enter the compensating control above the table first'});return;}
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/access-governance/conflicts/${id}/mitigate`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({mitigating_control:mitigation})});
      ok(ar?'سُجّل الضابط التعويضي — التعارض ما زال قائمًا لكنه مُراقَب':'Compensating control recorded — the conflict remains but is monitored');
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const resolve=async(id:number)=>{
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/access-governance/conflicts/${id}/resolve`,{method:'POST'});
      ok(ar?'أُغلق التعارض — تأكد أن الصلاحية أُزيلت فعلًا من المستخدم':'Conflict closed — make sure the access was actually removed');
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const open=conflicts.filter(c=>c.status==='OPEN').length;
  const mitigated=conflicts.filter(c=>c.status==='MITIGATED').length;
  const critical=conflicts.filter(c=>c.severity==='CRITICAL'&&c.status!=='RESOLVED').length;

  return <>
    <div className="kpis">
      <Kpi title={ar?'قواعد الفصل':'SoD rules'} value={String(rules.length)} trend="" good={rules.length>0} icon={<UserCheck size={22}/>} tone="blue"/>
      <Kpi title={ar?'تعارضات مفتوحة':'Open conflicts'} value={String(open)} trend="" good={open===0} icon={<ShieldAlert size={22}/>} tone={open>0?'amber':'green'}/>
      <Kpi title={ar?'تعارضات حرجة':'Critical'} value={String(critical)} trend="" good={critical===0} icon={<ShieldAlert size={22}/>} tone="violet"/>
      <Kpi title={ar?'مُخفّفة بضابط':'Mitigated'} value={String(mitigated)} trend={ar?'قائمة لكن مُراقَبة':'monitored'} good icon={<CheckCircle2 size={22}/>} tone="amber"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['conflicts',ar?'التعارضات':'Conflicts'],['rules',ar?'القواعد':'Rules']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>setTab(k)}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
      <button style={{...btn,background:'#7c3aed',opacity:busy?0.6:1}} disabled={busy} onClick={scan}>
        <ScanSearch size={15}/> {ar?'فحص الصلاحيات الآن':'Scan now'}
      </button>
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.9,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab==='conflicts'&&<>
      <Panel title={ar?'الضابط التعويضي':'Compensating control'} icon={<CheckCircle2 size={18}/>}>
        <div style={{padding:'10px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'أمامك خياران لكل تعارض: «تخفيف» بضابط تعويضي حين يتعذّر فصل المهام (فريق صغير مثلًا) — ويبقى التعارض قائمًا لكن مُراقَبًا. أو «إغلاق» بعد إزالة إحدى الصلاحيتين فعليًا من المستخدم.'
            : 'Two options per conflict: mitigate with a compensating control when separation is impractical (a small team), which keeps the conflict but monitors it; or resolve after actually removing one of the permissions.'}
        </div>
        <div style={{padding:12,maxWidth:560}}>
          <label>{ar?'وصف الضابط التعويضي':'Compensating control'}
            <input style={field} value={mitigation} onChange={e=>setMitigation(e.target.value)}
              placeholder={ar?'مراجعة شهرية من المدير المالي لكل القيود التي أعدّها هذا المستخدم':'Monthly review of all entries by this user'}/></label>
        </div>
      </Panel>
      <Panel title={ar?'التعارضات المكتشفة':'Detected conflicts'} icon={<ShieldAlert size={18}/>}>
        {conflicts.length===0
          ? <div style={{padding:16,fontSize:14,lineHeight:1.9}}>
              {ar?'لا توجد تعارضات مسجّلة. أضف قواعد الفصل من تبويب «القواعد» ثم اضغط «فحص الصلاحيات الآن».'
                 :'No conflicts recorded. Add rules then run the scan.'}
            </div>
          : <DataTable headers={[ar?'المستخدم':'User',ar?'القاعدة':'Rule',ar?'الخطورة':'Severity',
              ar?'الصلاحيتان':'Permissions',ar?'الحالة':'Status',ar?'إجراء':'Action']}
              rows={conflicts.map(c=>[c.user,c.rule_code,
                (SEVERITIES.find(s=>s[0]===c.severity)||[])[ar?1:0]||c.severity,
                `${c.permission_a} + ${c.permission_b}`,c.status,
                c.status==='RESOLVED'?'✓':
                <span key={c.id} style={{display:'flex',gap:5}}>
                  {c.status==='OPEN'&&<button style={smallBtn} disabled={busy} onClick={()=>mitigate(c.id)}>{ar?'تخفيف':'Mitigate'}</button>}
                  <button style={{...smallBtn,background:'#059669'}} disabled={busy} onClick={()=>resolve(c.id)}>{ar?'إغلاق':'Resolve'}</button>
                </span>])}/>}
      </Panel>
    </>}

    {tab==='rules'&&<>
      <Panel title={ar?'قواعد جاهزة — اضغط لتعبئتها':'Ready templates'} icon={<Plus size={18}/>}>
        <div style={{padding:'10px 12px',display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(260px,1fr))',gap:10}}>
          {TEMPLATES.map(t=>{
            const exists=rules.some(r=>r.code===t.code);
            return <button key={t.code} disabled={exists} onClick={()=>useTemplate(t)}
              style={{textAlign:'start',padding:12,borderRadius:10,cursor:exists?'default':'pointer',
                border:'1px solid var(--border)',background:exists?'var(--panel-2, #f1f5f9)':'transparent',
                opacity:exists?0.55:1,lineHeight:1.8}}>
              <div style={{fontWeight:700,fontSize:14}}>{ar?t.ar:t.en}</div>
              <div style={{fontSize:12,opacity:0.75,marginTop:4}}><code>{t.a}</code> + <code>{t.b}</code></div>
              <div style={{fontSize:12,opacity:0.85,marginTop:6}}>{ar?t.why:''}</div>
              {exists&&<div style={{fontSize:12,marginTop:6,color:'#166534'}}>{ar?'✓ مضافة':'✓ added'}</div>}
            </button>;
          })}
        </div>
      </Panel>
      <Panel title={ar?'قاعدة فصل مهام':'SoD rule'} icon={<UserCheck size={18}/>}>
        <div style={grid}>
          <label>{ar?'كود القاعدة':'Code'}<input style={field} value={code} onChange={e=>setCode(e.target.value)} placeholder="SOD-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
          <label>{ar?'الصلاحية الأولى':'Permission A'}<input style={field} value={permA} onChange={e=>setPermA(e.target.value)} placeholder="finance.manage"/></label>
          <label>{ar?'الصلاحية الثانية':'Permission B'}<input style={field} value={permB} onChange={e=>setPermB(e.target.value)} placeholder="finance.approve"/></label>
          <label>{ar?'الخطورة':'Severity'}<select style={field} value={sev} onChange={e=>setSev(e.target.value)}>
            {SEVERITIES.map(([v,a])=><option key={v} value={v}>{ar?a:v}</option>)}</select></label>
          <label style={{gridColumn:'1 / -1'}}>{ar?'المبرر — لماذا لا يجوز الجمع بينهما':'Rationale'}
            <input style={field} value={why} onChange={e=>setWhy(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addRule}>{ar?'إضافة القاعدة':'Add rule'}</button>
        </div>
      </Panel>
      <Panel title={ar?'القواعد المسجّلة':'Registered rules'} icon={<UserCheck size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'القاعدة':'Rule',ar?'الصلاحيتان':'Permissions',ar?'الخطورة':'Severity']}
          rows={rules.map(r=>[r.code,ar?r.name_ar:r.name_en,`${r.permission_a} + ${r.permission_b}`,
            (SEVERITIES.find(s=>s[0]===r.severity)||[])[ar?1:0]||r.severity])}/>
      </Panel>
    </>}
  </>;
}
