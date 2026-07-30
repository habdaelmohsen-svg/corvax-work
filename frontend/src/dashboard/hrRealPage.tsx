import {useEffect, useState} from 'react';
import {Users, Plus, Wallet, ShieldCheck, FileSpreadsheet, CheckCircle2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Employees, the payroll policy, and the payroll run through its full control
// chain. The previous screen had no input fields at all - it only fired samples.
//
// The run is deliberately hard to push through, and that is correct:
//   an approved policy must exist, then calculate -> review -> approve -> post,
//   each step by a DIFFERENT user, and payment needs an accepted WPS batch.

type Emp={id:number;employee_number:string;name_ar:string;name_en:string;nationality_group:string;
  basic_salary:number;housing_allowance:number;other_allowance:number;has_iban:boolean;iban_masked?:string;
  salary_bank_code?:string;branch_id?:number;cost_center_id?:number;active?:boolean};
type Run={id:number;period_year:number;period_month:number;status:string;
  total_gross?:number;total_net?:number;payment_date?:string};
type Bank={id:number;bank_name_ar?:string;name_ar?:string};
type Named={id:number;code:string;name_ar:string;name_en:string;active?:boolean};
type Shift=Named&{start_time:string;end_time:string};
type ReadinessEmployee={employee_id:number;employee_number:string;name_ar:string;name_en:string;
  ready:boolean;blockers:string[];warnings:string[]};
type Readiness={ready:boolean;global_blockers:string[];employee_blockers:number;warnings:number;
  ready_employees:number;total_employees:number;employees:ReadinessEmployee[]};
type Wps={id:number;batch_number:string;execution_date:string;status:string;total_amount:number;line_count:number};

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

const MONTHS=['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];

export function HrPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'employees'|'linking'|'payroll'|'policy'>('employees');
  const [emps,setEmps]=useState<Emp[]>([]);
  const [runs,setRuns]=useState<Run[]>([]);
  const [banks,setBanks]=useState<Bank[]>([]);
  const [branches,setBranches]=useState<Named[]>([]);
  const [centers,setCenters]=useState<Named[]>([]);
  const [shifts,setShifts]=useState<Shift[]>([]);
  const [readiness,setReadiness]=useState<Readiness|null>(null);
  const [wps,setWps]=useState<Wps[]>([]);
  const [policy,setPolicy]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  // employee
  const [eNo,setENo]=useState(''); const [eAr,setEAr]=useState(''); const [eEn,setEEn]=useState('');
  const [eNat,setENat]=useState('SAUDI'); const [eId,setEId]=useState(''); const [eHire,setEHire]=useState(iso());
  const [eBasic,setEBasic]=useState(''); const [eHouse,setEHouse]=useState(''); const [eOther,setEOther]=useState('0');
  const [eIban,setEIban]=useState(''); const [eBankCode,setEBankCode]=useState('');
  const [eBranch,setEBranch]=useState(''); const [eCenter,setECenter]=useState(''); const [eShift,setEShift]=useState('');
  const [eEmployeeGosi,setEEmployeeGosi]=useState('9.75');
  const [eEmployerGosi,setEEmployerGosi]=useState('11.75');
  // payroll linkage for existing employees
  const [lEmp,setLEmp]=useState(''); const [lBranch,setLBranch]=useState('');
  const [lCenter,setLCenter]=useState(''); const [lShift,setLShift]=useState('');
  const [lIban,setLIban]=useState(''); const [lBankCode,setLBankCode]=useState('');
  const [lFrom,setLFrom]=useState(iso());
  const [wpsRefs,setWpsRefs]=useState<Record<number,string>>({});
  // run
  const now=new Date();
  const [rYear,setRYear]=useState(String(now.getFullYear()));
  const [rMonth,setRMonth]=useState(String(now.getMonth()+1));
  const [rPayDate,setRPayDate]=useState(iso());
  const [rBank,setRBank]=useState('');
  // policy
  const [pDays,setPDays]=useState('30'); const [pHours,setPHours]=useState('8');
  const [pGosi,setPGosi]=useState('BASIC_HOUSING'); const [pThreshold,setPThreshold]=useState('95');
  const [pThree,setPThree]=useState(true);

  const load=async()=>{
    try{
      const [e,r,b,p,br,cc,sh,rd,wb]=await Promise.all([
        json(`/api/v1/payroll/employees?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/payroll/runs?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/hr-payroll/policies?company_id=${companyId}`).catch(()=>null),
        json(`/api/v1/enterprise/companies/${companyId}/branches`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/cost-centers`).catch(()=>[]),
        json(`/api/v1/hr/shifts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/payroll/readiness?company_id=${companyId}&period_year=${rYear}&period_month=${rMonth}`).catch(()=>null),
        json(`/api/v1/hr-payroll/wps?company_id=${companyId}`).catch(()=>[]),
      ]);
      setEmps(Array.isArray(e)?e:[]); setRuns(Array.isArray(r)?r:[]); setBanks(Array.isArray(b)?b:[]);
      setBranches(Array.isArray(br)?br.filter((x:any)=>x.active!==false):[]);
      setCenters(Array.isArray(cc)?cc.filter((x:any)=>x.active!==false):[]);
      setShifts(Array.isArray(sh)?sh:[]); setReadiness(rd&&typeof rd==='object'?rd:null);
      setWps(Array.isArray(wb)?wb:[]);
      setPolicy(p&&!Array.isArray(p)?p:(Array.isArray(p)?p[0]:null));
      if(!rBank&&b?.length)setRBank(String(b[0].id));
      if(!eBranch&&br?.length)setEBranch(String(br[0].id));
      if(!eCenter&&cc?.length)setECenter(String(cc[0].id));
      if(!eShift&&sh?.length)setEShift(String(sh[0].id));
      if(!lEmp&&e?.length)setLEmp(String(e[0].id));
      if(!lBranch&&br?.length)setLBranch(String(br[0].id));
      if(!lCenter&&cc?.length)setLCenter(String(cc[0].id));
      if(!lShift&&sh?.length)setLShift(String(sh[0].id));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId,rYear,rMonth]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};

  // Starting suggestions only. The new Saudi system phases pension rates by
  // coverage cohort, so the payroll operator must confirm the employee's
  // actual GOSI rates instead of relying on a hard-coded legal rate.
  const gosiFor=(nat:string)=> nat==='SAUDI' ? {employee:9.75,employer:11.75} : {employee:0,employer:2};

  const createEmployee=async()=>{
    if(!eNo||!eAr||!eEn||!eBasic||!eIban||!eBankCode||!eBranch||!eCenter||!eShift){
      bad({message:ar
        ?'الرقم والاسمان والراتب والآيبان ورمز البنك والفرع ومركز التكلفة والوردية إلزامية'
        :'Number, names, salary, IBAN, bank code, branch, cost center and shift are required'});return;
    }
    setBusy(true);setMsg('');
    try{
      const g={employee:Number(eEmployeeGosi),employer:Number(eEmployerGosi)};
      if(g.employee<0||g.employee>100||g.employer<0||g.employer>100)throw new Error(ar?'نسب التأمينات غير صحيحة':'Invalid GOSI rates');
      const body:any={company_id:companyId,employee_number:eNo,name_ar:eAr,name_en:eEn,
        nationality_group:eNat,hire_date:eHire,basic_salary:Number(eBasic),
        housing_allowance:Number(eHouse)||0,other_allowance:Number(eOther)||0,
        employee_gosi_rate:g.employee,employer_gosi_rate:g.employer,
        iban:eIban,salary_bank_code:eBankCode,branch_id:Number(eBranch),cost_center_id:Number(eCenter)};
      if(eId)body.national_id=eId;
      const employee=await json('/api/v1/payroll/employees',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      await json(`/api/v1/payroll/employees/${employee.id}/payroll-link`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,branch_id:Number(eBranch),cost_center_id:Number(eCenter),
          shift_id:Number(eShift),effective_from:eHire,iban:eIban,salary_bank_code:eBankCode})});
      ok(ar?`تم تسجيل الموظف ${eNo} — التأمينات ${g.employer}% منشأة و${g.employee}% موظف`
           :`Employee ${eNo} created — GOSI ${g.employer}% employer / ${g.employee}% employee`);
      setENo('');setEAr('');setEEn('');setEBasic('');setEHouse('');setEIban('');setEBankCode(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const selectLinkEmployee=(employeeId:string)=>{
    setLEmp(employeeId);
    const employee=emps.find(x=>String(x.id)===employeeId);
    if(employee?.branch_id)setLBranch(String(employee.branch_id));
    if(employee?.cost_center_id)setLCenter(String(employee.cost_center_id));
    setLBankCode(employee?.salary_bank_code||'');
    setLIban('');
  };

  const linkEmployee=async()=>{
    if(!lEmp||!lBranch||!lCenter||!lShift){
      bad({message:ar?'اختر الموظف والفرع ومركز التكلفة والوردية':'Select employee, branch, cost center and shift'});return;
    }
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/payroll/employees/${lEmp}/payroll-link`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,branch_id:Number(lBranch),cost_center_id:Number(lCenter),
          shift_id:Number(lShift),effective_from:lFrom,iban:lIban||null,salary_bank_code:lBankCode||null})});
      ok(ar?'تم ربط الموظف بالرواتب وتحديث فحص الجاهزية':'Employee linked to payroll; readiness refreshed');
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const savePolicy=async()=>{
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/hr-payroll/policies',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,salary_day_basis:Number(pDays),
          standard_daily_hours:Number(pHours),gosi_basis:pGosi,
          attendance_completeness_threshold:Number(pThreshold),
          require_three_user_approval:pThree,
          late_deduction_enabled:true,absence_deduction_enabled:true,overtime_basis:'BASIC'})});
      ok(ar?'تم حفظ السياسة — اعتمدها قبل تشغيل أي مسيّر رواتب':'Policy saved — approve it before running payroll');
      if(r?.id){
        try{
          await json(`/api/v1/hr-payroll/policies/${r.id}/approve`,{method:'POST'});
          ok(ar?'تم حفظ السياسة واعتمادها':'Policy saved and approved');
        }catch(e:any){
          ok(ar?`تم الحفظ. الاعتماد يحتاج مستخدمًا آخر: ${String(e.message||e)}`
                :`Saved. Approval needs another user: ${String(e.message||e)}`);
        }
      }
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const createRun=async()=>{
    if(!rBank){bad({message:ar?'اختر الحساب البنكي':'Pick a bank account'});return;}
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/payroll/runs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,period_year:Number(rYear),period_month:Number(rMonth),
          payment_date:rPayDate,bank_account_id:Number(rBank)})});
      ok(ar?`تم احتساب مسيّر ${MONTHS[Number(rMonth)-1]} — يحتاج مراجعة ثم اعتمادًا من شخصين مختلفين`
           :`Run calculated — needs review then approval by two different users`);
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const step=async(id:number,action:'review'|'approve'|'pay')=>{
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/payroll/runs/${id}/${action}`,{method:'POST'});
      const t:any={review:ar?'تمت المراجعة':'Reviewed',approve:ar?'تم الاعتماد':'Approved',
        pay:ar?'تم الصرف':'Paid'};
      ok(t[action]); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const generateWps=async(id:number)=>{
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/hr-payroll/wps/${id}/generate`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId})});
      ok(ar?'تم توليد ملف حماية الأجور — ارفعه لبنكك أو بوابة الوزارة، ثم سجّل القبول قبل الصرف'
           :'WPS file generated — upload it, then record acceptance before paying');
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const recordWpsAcceptance=async(batch:Wps)=>{
    const reference=(wpsRefs[batch.id]||'').trim();
    if(!reference){bad({message:ar?'أدخل مرجع قبول البنك أو منصة حماية الأجور':'Enter the bank/WPS acceptance reference'});return;}
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/hr-payroll/wps/${batch.id}/response`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({status:'ACCEPTED',response_reference:reference,
          response_message:'Acceptance recorded from official bank/WPS response',lines:[]})});
      ok(ar?'تم تسجيل القبول الخارجي؛ أصبح الصرف متاحًا للمسيّر المرتبط':'External acceptance recorded; payment is now available');
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const downloadWps=async(batch:Wps)=>{
    try{
      const response=await apiFetch(`/api/v1/hr-payroll/wps/${batch.id}/file`);
      if(!response.ok)throw new Error(ar?'تعذر تنزيل ملف حماية الأجور':'Could not download WPS file');
      const blob=await response.blob(); const url=URL.createObjectURL(blob);
      const a=document.createElement('a'); a.href=url; a.download=`${batch.batch_number}.txt`; a.click();
      URL.revokeObjectURL(url);
    }catch(e){bad(e);}
  };

  const totalPayroll=emps.reduce((s,e)=>s+Number(e.basic_salary||0)+Number(e.housing_allowance||0)+Number(e.other_allowance||0),0);
  const noIban=emps.filter(e=>!e.has_iban).length;
  const saudis=emps.filter(e=>e.nationality_group==='SAUDI').length;
  const saudization=emps.length?Math.round(saudis/emps.length*100):0;
  const blockerLabel=(code:string)=>{
    const labels:Record<string,[string,string]>={
      APPROVED_PAYROLL_POLICY_REQUIRED:['يلزم اعتماد سياسة الرواتب','Approved payroll policy required'],
      NO_ACTIVE_EMPLOYEES:['لا يوجد موظفون نشطون','No active employees'],
      MISSING_IBAN:['الآيبان ناقص','IBAN missing'],
      MISSING_SALARY_BANK_CODE:['رمز البنك ناقص','Salary bank code missing'],
      MISSING_BRANCH:['الفرع ناقص','Branch missing'],
      MISSING_COST_CENTER:['مركز التكلفة ناقص','Cost center missing'],
      MISSING_SHIFT_ASSIGNMENT:['ربط الوردية ناقص','Shift assignment missing'],
      NO_APPROVED_ACTIVE_CONTRACT:['لا يوجد عقد نشط معتمد','No approved active contract'],
    };
    return labels[code]?.[ar?0:1]||code;
  };

  return <>
    <div className="kpis">
      <Kpi title={ar?'الموظفون':'Employees'} value={String(emps.length)} trend="" good icon={<Users size={22}/>} tone="blue"/>
      <Kpi title={ar?'إجمالي الرواتب':'Monthly payroll'} value={fmt(totalPayroll)} trend="" good icon={<Wallet size={22}/>} tone="violet"/>
      <Kpi title={ar?'نسبة السعودة':'Saudization'} value={`${saudization}%`} trend={`${saudis}/${emps.length}`} good icon={<ShieldCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'بلا آيبان':'Missing IBAN'} value={String(noIban)} trend={ar?'يمنع حماية الأجور':'blocks WPS'} good={noIban===0} icon={<FileSpreadsheet size={22}/>} tone="amber"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['employees',ar?'الموظفون':'Employees'],['payroll',ar?'مسيّر الرواتب':'Payroll runs'],
         ['linking',ar?'ربط الموظفين':'Employee linking'],
         ['policy',ar?'سياسة الرواتب':'Policy']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>setTab(k)}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.9,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab==='employees'&&<>
      <Panel title={ar?'موظف جديد':'New employee'} icon={<Plus size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'يعرض النظام نسبًا ابتدائية قابلة للتعديل؛ يجب مطابقتها مع فئة اشتراك الموظف في التأمينات لأن نظام ١٤٤٥هـ يرفع فرع المعاشات تدريجيًا للمشمولين الجدد. والآيبان ورمز البنك والربط التنظيمي شروط قبل الاحتساب.'
            : 'The screen suggests editable starting rates. Confirm each employee’s GOSI coverage cohort because the 1445H system phases pension rates for newly covered workers. IBAN, bank code and organisational links are required before calculation.'}
        </div>
        <div style={grid}>
          <label>{ar?'الرقم الوظيفي':'Employee no.'}<input style={field} value={eNo} onChange={e=>setENo(e.target.value)} placeholder="EMP-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={eAr} onChange={e=>setEAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={eEn} onChange={e=>setEEn(e.target.value)}/></label>
          <label>{ar?'الجنسية':'Nationality'}<select style={field} value={eNat} onChange={e=>{
            const nat=e.target.value; const g=gosiFor(nat); setENat(nat);
            setEEmployeeGosi(String(g.employee));setEEmployerGosi(String(g.employer));
          }}>
            <option value="SAUDI">{ar?'سعودي':'Saudi'}</option>
            <option value="NON_SAUDI">{ar?'غير سعودي':'Non-Saudi'}</option>
          </select></label>
          <label>{ar?'الهوية أو الإقامة':'ID / Iqama'}<input style={field} value={eId} onChange={e=>setEId(e.target.value)}/></label>
          <label>{ar?'تاريخ التعيين':'Hire date'}<input type="date" style={field} value={eHire} onChange={e=>setEHire(e.target.value)}/></label>
          <label>{ar?'الراتب الأساسي':'Basic salary'}<input type="number" style={field} value={eBasic}
            onChange={e=>{setEBasic(e.target.value); if(!eHouse&&e.target.value)setEHouse(String(Math.round(Number(e.target.value)*0.25)));}}/></label>
          <label>{ar?'بدل السكن':'Housing'}<input type="number" style={field} value={eHouse} onChange={e=>setEHouse(e.target.value)}/>
            <small style={{opacity:0.7}}>{ar?'٢٥٪ من الأساسي عادةً':'usually 25% of basic'}</small></label>
          <label>{ar?'بدلات أخرى':'Other allowances'}<input type="number" style={field} value={eOther} onChange={e=>setEOther(e.target.value)}/></label>
          <label>{ar?'نسبة الموظف بالتأمينات %':'Employee GOSI %'}<input type="number" min="0" max="100" step="0.01" style={field} value={eEmployeeGosi} onChange={e=>setEEmployeeGosi(e.target.value)}/></label>
          <label>{ar?'نسبة المنشأة بالتأمينات %':'Employer GOSI %'}<input type="number" min="0" max="100" step="0.01" style={field} value={eEmployerGosi} onChange={e=>setEEmployerGosi(e.target.value)}/></label>
          <label>{ar?'الآيبان':'IBAN'}<input style={field} value={eIban} onChange={e=>setEIban(e.target.value)} placeholder="SA00 0000 0000 0000 0000 0000"/></label>
          <label>{ar?'رمز البنك للرواتب':'Salary bank code'}<input style={field} value={eBankCode} onChange={e=>setEBankCode(e.target.value)} placeholder="RJHI"/></label>
          <label>{ar?'الفرع':'Branch'}<select style={field} value={eBranch} onChange={e=>setEBranch(e.target.value)}>
            <option value="">{ar?'اختر':'Select'}</option>{branches.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}
          </select></label>
          <label>{ar?'مركز التكلفة':'Cost center'}<select style={field} value={eCenter} onChange={e=>setECenter(e.target.value)}>
            <option value="">{ar?'اختر':'Select'}</option>{centers.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}
          </select></label>
          <label>{ar?'الوردية':'Shift'}<select style={field} value={eShift} onChange={e=>setEShift(e.target.value)}>
            <option value="">{ar?'اختر':'Select'}</option>{shifts.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}
          </select></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createEmployee}>{ar?'تسجيل الموظف':'Create employee'}</button>
        </div>
      </Panel>
      <Panel title={ar?'الموظفون':'Employees'} icon={<Users size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'الاسم':'Name',ar?'الجنسية':'Nationality',ar?'الأساسي':'Basic',
          ar?'السكن':'Housing',ar?'الإجمالي':'Gross',ar?'آيبان':'IBAN',ar?'الربط':'Link']}
          rows={emps.map(e=>[e.employee_number,ar?e.name_ar:e.name_en,
            e.nationality_group==='SAUDI'?(ar?'سعودي':'Saudi'):(ar?'غير سعودي':'Non-Saudi'),
            fmt(Number(e.basic_salary||0)),fmt(Number(e.housing_allowance||0)),
            fmt(Number(e.basic_salary||0)+Number(e.housing_allowance||0)+Number(e.other_allowance||0)),
            e.has_iban?(e.iban_masked||'✓'):(ar?'ناقص':'missing'),
            <button key={e.id} style={smallBtn} onClick={()=>{selectLinkEmployee(String(e.id));setTab('linking')}}>
              {ar?'إعداد':'Configure'}
            </button>])}/>
      </Panel>
    </>}

    {tab==='linking'&&<>
      <Panel title={ar?'ربط الموظف باحتساب الرواتب':'Link employee to payroll'} icon={<ShieldCheck size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'اربط كل موظف بفرع ومركز تكلفة ووردية، وأكمل الآيبان ورمز البنك. يحتسب النظام الحضور والاستقطاعات والإضافي على الوردية، ويحمل مصروف الرواتب على مركز التكلفة.'
            : 'Link every employee to a branch, cost center and shift, then complete IBAN and bank code. Attendance, deductions and overtime use the shift; payroll expense uses the cost center.'}
        </div>
        <div style={grid}>
          <label>{ar?'الموظف':'Employee'}<select style={field} value={lEmp} onChange={e=>selectLinkEmployee(e.target.value)}>
            <option value="">{ar?'اختر':'Select'}</option>{emps.map(x=><option key={x.id} value={x.id}>{x.employee_number} — {ar?x.name_ar:x.name_en}</option>)}
          </select></label>
          <label>{ar?'الفرع':'Branch'}<select style={field} value={lBranch} onChange={e=>setLBranch(e.target.value)}>
            <option value="">{ar?'اختر':'Select'}</option>{branches.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}
          </select></label>
          <label>{ar?'مركز التكلفة':'Cost center'}<select style={field} value={lCenter} onChange={e=>setLCenter(e.target.value)}>
            <option value="">{ar?'اختر':'Select'}</option>{centers.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}
          </select></label>
          <label>{ar?'الوردية':'Shift'}<select style={field} value={lShift} onChange={e=>setLShift(e.target.value)}>
            <option value="">{ar?'اختر':'Select'}</option>{shifts.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}
          </select></label>
          <label>{ar?'ساري من':'Effective from'}<input type="date" style={field} value={lFrom} onChange={e=>setLFrom(e.target.value)}/></label>
          <label>{ar?'آيبان جديد (اختياري)':'New IBAN (optional)'}<input style={field} value={lIban} onChange={e=>setLIban(e.target.value)} placeholder="SA00 0000 0000 0000 0000 0000"/></label>
          <label>{ar?'رمز البنك':'Salary bank code'}<input style={field} value={lBankCode} onChange={e=>setLBankCode(e.target.value)} placeholder="RJHI"/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={linkEmployee}>{ar?'حفظ الربط':'Save linkage'}</button>
        </div>
      </Panel>
      <Panel title={ar?'فحص جاهزية الموظفين':'Employee readiness check'} icon={<CheckCircle2 size={18}/>}>
        <DataTable headers={[ar?'الموظف':'Employee',ar?'الحالة':'Status',ar?'الموانع':'Blockers',ar?'تنبيهات':'Warnings']}
          rows={(readiness?.employees||[]).map(e=>[
            `${e.employee_number} — ${ar?e.name_ar:e.name_en}`,
            e.ready?(ar?'جاهز':'Ready'):(ar?'غير جاهز':'Not ready'),
            e.blockers.map(blockerLabel).join('، ')||'—',
            e.warnings.map(blockerLabel).join('، ')||'—',
          ])}/>
      </Panel>
    </>}

    {tab==='payroll'&&<>
      <Panel title={ar?'احتساب مسيّر رواتب':'Calculate a payroll run'} icon={<Wallet size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'الدورة: احتساب ← مراجعة ← اعتماد وترحيل تلقائي ← ملف حماية الأجور ← تسجيل قبول البنك ← صرف. المُعِدّ والمراجع والمعتمِد ثلاثة مستخدمين مختلفين.'
            : 'Flow: calculate -> review -> approve and auto-post -> WPS file -> record bank acceptance -> pay. Preparer, reviewer and approver are three different users.'}
        </div>
        <div style={{margin:'10px 12px 0',padding:10,borderRadius:9,
          background:readiness?.ready?'#dcfce7':'#fff7ed',color:readiness?.ready?'#166534':'#9a3412',fontSize:13,lineHeight:1.8}}>
          {readiness?.ready
            ? (ar?`جاهز للاحتساب: ${readiness.ready_employees}/${readiness.total_employees} موظفين`
                 :`Ready to calculate: ${readiness.ready_employees}/${readiness.total_employees} employees`)
            : (ar
                ? `غير جاهز: ${(readiness?.global_blockers||[]).map(blockerLabel).join('، ')||`${readiness?.employee_blockers||0} موانع لدى الموظفين`}`
                : `Not ready: ${(readiness?.global_blockers||[]).map(blockerLabel).join(', ')||`${readiness?.employee_blockers||0} employee blockers`}`)}
          {!readiness?.ready&&<button style={{...smallBtn,marginInlineStart:8}} onClick={()=>setTab('linking')}>{ar?'عرض التفاصيل':'View details'}</button>}
        </div>
        <div style={grid}>
          <label>{ar?'السنة':'Year'}<input type="number" style={field} value={rYear} onChange={e=>setRYear(e.target.value)}/></label>
          <label>{ar?'الشهر':'Month'}<select style={field} value={rMonth} onChange={e=>setRMonth(e.target.value)}>
            {MONTHS.map((m,i)=><option key={i} value={i+1}>{ar?m:String(i+1)}</option>)}</select></label>
          <label>{ar?'تاريخ الصرف':'Payment date'}<input type="date" style={field} value={rPayDate} onChange={e=>setRPayDate(e.target.value)}/></label>
          <label>{ar?'الحساب البنكي':'Bank account'}<select style={field} value={rBank} onChange={e=>setRBank(e.target.value)}>
            {banks.map(b=><option key={b.id} value={b.id}>{b.bank_name_ar||b.name_ar||`#${b.id}`}</option>)}</select></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:(busy||!readiness?.ready)?0.55:1}} disabled={busy||!readiness?.ready} onClick={createRun}>{ar?'احتساب المسيّر':'Calculate'}</button>
        </div>
      </Panel>
      <Panel title={ar?'المسيّرات':'Payroll runs'} icon={<Wallet size={18}/>}>
        <DataTable headers={[ar?'الفترة':'Period',ar?'الإجمالي':'Gross',ar?'الصافي':'Net',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={runs.map(r=>[`${ar?MONTHS[(r.period_month||1)-1]:r.period_month} ${r.period_year}`,
            fmt(Number(r.total_gross||0)),fmt(Number(r.total_net||0)),r.status,
            <span key={r.id} style={{display:'flex',gap:5,flexWrap:'wrap'}}>
              {r.status==='CALCULATED'&&<button style={smallBtn} disabled={busy} onClick={()=>step(r.id,'review')}>{ar?'مراجعة':'Review'}</button>}
              {r.status==='REVIEWED'&&<button style={smallBtn} disabled={busy} onClick={()=>step(r.id,'approve')}>{ar?'اعتماد':'Approve'}</button>}
              {['POSTED','APPROVED_POSTED'].includes(r.status)&&<>
                <button style={{...smallBtn,background:'#7c3aed'}} disabled={busy} onClick={()=>generateWps(r.id)}>{ar?'ملف الأجور':'WPS'}</button>
                <button style={{...smallBtn,background:'#b45309'}} disabled={busy} onClick={()=>step(r.id,'pay')}>{ar?'صرف':'Pay'}</button>
              </>}
              {r.status==='PAID'&&<span style={{fontSize:12}}>✓</span>}
            </span>])}/>
      </Panel>
      <Panel title={ar?'دفعات حماية الأجور':'WPS batches'} icon={<FileSpreadsheet size={18}/>}>
        <DataTable headers={[ar?'الدفعة':'Batch',ar?'التاريخ':'Date',ar?'المبلغ':'Amount',ar?'الحالة':'Status',ar?'مرجع القبول':'Acceptance reference']}
          rows={wps.map(batch=>[
            <button key={batch.id} style={{...smallBtn,background:'#475569'}} onClick={()=>downloadWps(batch)}>{batch.batch_number}</button>,
            batch.execution_date,fmt(Number(batch.total_amount||0)),batch.status,
            batch.status==='ACCEPTED'
              ? '✓'
              : <span key={batch.id} style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                  <input style={{...field,marginTop:0,padding:5,width:150}} value={wpsRefs[batch.id]||''}
                    onChange={e=>setWpsRefs(x=>({...x,[batch.id]:e.target.value}))}
                    placeholder={ar?'مرجع رسمي':'official reference'}/>
                  <button style={smallBtn} disabled={busy} onClick={()=>recordWpsAcceptance(batch)}>{ar?'تسجيل القبول':'Record acceptance'}</button>
                </span>,
          ])}/>
      </Panel>
    </>}

    {tab==='policy'&&<>
      <Panel title={ar?'سياسة الرواتب':'Payroll policy'} icon={<ShieldCheck size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'السياسة شرط لتشغيل أي مسيّر. تحدد أساس احتساب اليوم، وساعات العمل، ووعاء التأمينات، والحد الأدنى لاكتمال الحضور قبل السماح بالاحتساب.'
            : 'A policy is required before any run. It sets the day basis, standard hours, the GOSI base and the minimum attendance completeness.'}
        </div>
        <div style={grid}>
          <label>{ar?'أيام الشهر للاحتساب':'Salary day basis'}<input type="number" style={field} value={pDays} onChange={e=>setPDays(e.target.value)}/>
            <small style={{opacity:0.7}}>{ar?'٣٠ يومًا هو المعتاد':'30 is standard'}</small></label>
          <label>{ar?'ساعات اليوم':'Daily hours'}<input type="number" style={field} value={pHours} onChange={e=>setPHours(e.target.value)}/></label>
          <label>{ar?'وعاء التأمينات':'GOSI base'}<select style={field} value={pGosi} onChange={e=>setPGosi(e.target.value)}>
            <option value="BASIC_HOUSING">{ar?'الأساسي + السكن (النظامي)':'Basic + housing'}</option>
            <option value="BASIC">{ar?'الأساسي فقط':'Basic only'}</option>
            <option value="GROSS">{ar?'الإجمالي':'Gross'}</option>
          </select></label>
          <label>{ar?'حد اكتمال الحضور %':'Attendance threshold %'}<input type="number" min="0" max="100" style={field} value={pThreshold} onChange={e=>setPThreshold(e.target.value)}/></label>
          <label style={{display:'flex',alignItems:'center',gap:8,marginTop:26}}>
            <input type="checkbox" checked={pThree} onChange={e=>setPThree(e.target.checked)}/>
            {ar?'اشتراط ثلاثة مستخدمين للاعتماد':'Require three-user approval'}
          </label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={savePolicy}>{ar?'حفظ السياسة':'Save policy'}</button>
        </div>
      </Panel>
      <Panel title={ar?'السياسة الحالية':'Current policy'} icon={<CheckCircle2 size={18}/>}>
        {policy
          ? <DataTable headers={[ar?'البند':'Setting',ar?'القيمة':'Value']}
              rows={[
                [ar?'أيام الاحتساب':'Day basis',String(policy.salary_day_basis??'—')],
                [ar?'ساعات اليوم':'Daily hours',String(policy.standard_daily_hours??'—')],
                [ar?'وعاء التأمينات':'GOSI base',String(policy.gosi_basis??'—')],
                [ar?'حد الحضور':'Attendance threshold',String(policy.attendance_completeness_threshold??'—')],
                [ar?'الحالة':'Status',policy.approved?(ar?'معتمدة':'Approved'):(ar?'بانتظار الاعتماد':'Pending approval')],
              ]}/>
          : <div style={{padding:16,fontSize:14,lineHeight:1.9}}>
              {ar?'لا توجد سياسة بعد. احفظ سياسة أولًا — بدونها لن يقبل النظام احتساب أي مسيّر رواتب.'
                 :'No policy yet. Save one first - payroll runs are refused without an approved policy.'}
            </div>}
      </Panel>
    </>}
  </>;
}
