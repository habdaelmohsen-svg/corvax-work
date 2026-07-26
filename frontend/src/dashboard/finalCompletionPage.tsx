import {useEffect, useMemo, useState} from 'react';
import {BarChart3, CheckCircle2, DatabaseBackup, Download, Factory, FileCheck2, RefreshCw, ShieldCheck} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, jsonHeaders, Kpi, MiniStatus, money, Panel, SummaryLine} from './ui';

type Tab='costing'|'planning'|'close'|'readiness';

async function json(url:string, init?:RequestInit){
  const response=await apiFetch(url,init);
  const payload=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(payload.detail||'Request failed');
  return payload;
}

async function download(url:string,filename:string){
  const response=await apiFetch(url);
  if(!response.ok)throw new Error((await response.json().catch(()=>({}))).detail||'Export failed');
  const blob=await response.blob();const link=document.createElement('a');const u=URL.createObjectURL(blob);
  link.href=u;link.download=filename;link.click();URL.revokeObjectURL(u);
}

export function FinalCompletionPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date().toISOString().slice(0,10);const year=today.slice(0,4);
  const [tab,setTab]=useState<Tab>('costing');const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);
  const [costRuns,setCostRuns]=useState<any[]>([]);const [scenarios,setScenarios]=useState<any[]>([]);
  const [closeRuns,setCloseRuns]=useState<any[]>([]);const [assessments,setAssessments]=useState<any[]>([]);
  const [fiscalYears,setFiscalYears]=useState<any[]>([]);const [periods,setPeriods]=useState<any[]>([]);
  const [cost,setCost]=useState({code:`COST-${year}-01`,period_start:`${year}-01-01`,period_end:today,posting_date:today,
    standard_output_quantity:'1000',actual_output_quantity:'950',mat1_std_qty:'500',mat1_actual_qty:'520',mat1_std_price:'10',mat1_actual_price:'11',
    mat2_std_qty:'250',mat2_actual_qty:'240',mat2_std_price:'6',mat2_actual_price:'5.5',standard_hours:'300',actual_hours:'330',standard_rate:'25',actual_rate:'27',
    standard_variable_rate:'8',actual_variable_rate:'9',standard_fixed_rate:'12',budgeted_fixed_overhead:'3600',actual_fixed_overhead:'3900',normal_capacity_hours:'400',productive_hours:'330',rework_cost:'300'});
  const [plan,setPlan]=useState({name:`Budget ${year}`,scenario_type:'BUDGET',account_code:'600000',amount:'100000',period_start:`${year}-01-01`,period_end:`${year}-12-31`});

  const load=async()=>{setBusy(true);setMessage('');try{
    const [c,s,cl,r,fy]=await Promise.all([
      json(`/api/v1/internal-completion/costing/runs?company_id=${companyId}`).catch(()=>[]),
      json(`/api/v1/internal-completion/planning/scenarios?company_id=${companyId}`).catch(()=>[]),
      json(`/api/v1/internal-completion/close/runs?company_id=${companyId}`).catch(()=>[]),
      json(`/api/v1/internal-completion/readiness/assessments?company_id=${companyId}`).catch(()=>[]),
      json(`/api/v1/enterprise/companies/${companyId}/fiscal-years`).catch(()=>[]),
    ]);setCostRuns(c);setScenarios(s);setCloseRuns(cl);setAssessments(r);setFiscalYears(fy);
    if(fy[0]?.id){setPeriods(await json(`/api/v1/enterprise/fiscal-years/${fy[0].id}/periods`).catch(()=>[]));}
  }catch(e:any){setMessage(e.message)}finally{setBusy(false)}};
  useEffect(()=>{load()},[companyId]);

  const post=async(url:string,body:any)=>{setBusy(true);setMessage('');try{await json(url,{method:'POST',headers:jsonHeaders(),body:JSON.stringify(body)});setMessage(ar?'تمت العملية بنجاح':'Operation completed');await load()}catch(e:any){setMessage(e.message)}finally{setBusy(false)}};

  const createCost=()=>post('/api/v1/internal-completion/costing/runs',{company_id:companyId,code:cost.code,period_start:cost.period_start,period_end:cost.period_end,posting_date:cost.posting_date,
    standard_output_quantity:Number(cost.standard_output_quantity),actual_output_quantity:Number(cost.actual_output_quantity),
    materials:[
      {code:'MAT-01',name_ar:'مادة خام 1',name_en:'Raw Material 1',standard_quantity:Number(cost.mat1_std_qty),actual_quantity:Number(cost.mat1_actual_qty),standard_price:Number(cost.mat1_std_price),actual_price:Number(cost.mat1_actual_price)},
      {code:'MAT-02',name_ar:'مادة خام 2',name_en:'Raw Material 2',standard_quantity:Number(cost.mat2_std_qty),actual_quantity:Number(cost.mat2_actual_qty),standard_price:Number(cost.mat2_std_price),actual_price:Number(cost.mat2_actual_price)},
    ],labor:{standard_hours:Number(cost.standard_hours),actual_hours:Number(cost.actual_hours),standard_rate:Number(cost.standard_rate),actual_rate:Number(cost.actual_rate)},
    overhead:{standard_variable_rate:Number(cost.standard_variable_rate),actual_variable_rate:Number(cost.actual_variable_rate),standard_fixed_rate:Number(cost.standard_fixed_rate),budgeted_fixed_overhead:Number(cost.budgeted_fixed_overhead),actual_fixed_overhead:Number(cost.actual_fixed_overhead),normal_capacity_hours:Number(cost.normal_capacity_hours),productive_hours:Number(cost.productive_hours)},
    joint_cost_total:0,joint_outputs:[],service_pools:[],rework_cost:Number(cost.rework_cost)});

  const createPlan=()=>{const fy=fiscalYears[0];if(!fy){setMessage(ar?'لا توجد سنة مالية':'No fiscal year');return}
    post('/api/v1/internal-completion/planning/scenarios',{company_id:companyId,fiscal_year_id:fy.id,name:plan.name,scenario_type:plan.scenario_type,horizon_start:fy.start_date,horizon_end:fy.end_date,assumptions:{source:'Final Internal UI'},commentary_ar:'سيناريو تخطيط تشغيلي',commentary_en:'Operational planning scenario',lines:[{account_code:plan.account_code,period_start:plan.period_start,period_end:plan.period_end,granularity:'ANNUAL',amount:Number(plan.amount),source_type:'MANUAL'}]})};
  const createClose=()=>{const period=periods.find((p:any)=>p.status==='OPEN')||periods[0];if(!period){setMessage(ar?'لا توجد فترة مالية':'No fiscal period');return}post('/api/v1/internal-completion/close/runs',{company_id:companyId,fiscal_period_id:period.id})};
  const createReadiness=()=>post('/api/v1/internal-completion/readiness/assessments',{company_id:companyId,environment_name:'INTERNAL',target_stage:'INTERNAL_RELEASE',evidence:{}});

  const latestCost=costRuns[0];const latestPlan=scenarios[0];const latestClose=closeRuns[0];const latestReady=assessments[0];
  const costLines=useMemo(()=>latestCost?.lines||[],[latestCost]);
  return <>
    <div className="page-title"><div><span>CORVAX FINAL INTERNAL</span><h2>{ar?'الإكمال الداخلي الموحد':'Unified Internal Completion'}</h2><p>{ar?'التكاليف والتخطيط والإقفال والجاهزية في بوابة واحدة':'Costing, planning, close and readiness in one controlled gate'}</p></div><button onClick={load} disabled={busy}><RefreshCw size={16}/>{ar?'تحديث':'Refresh'}</button></div>
    {message&&<div className="status-pill"><CheckCircle2 size={17}/>{message}</div>}
    <div className="workspace-tabs">
      {([['costing',ar?'التكاليف المتقدمة':'Advanced Costing'],['planning',ar?'الموازنة والتوقع':'Planning & Forecast'],['close',ar?'الإقفال الموحد':'Unified Close'],['readiness',ar?'الجاهزية':'Readiness']] as [Tab,string][]).map(([key,label])=><button className={tab===key?'active':''} onClick={()=>setTab(key)} key={key}>{label}</button>)}
    </div>

    {tab==='costing'&&<>
      <div className="kpis rich"><Kpi title={ar?'التكلفة المعيارية':'Standard cost'} value={money.format(Number(latestCost?.total_standard_cost||0))} trend={latestCost?.code||'—'} good/><Kpi title={ar?'التكلفة الفعلية':'Actual cost'} value={money.format(Number(latestCost?.total_actual_cost||0))} trend={latestCost?.status||'—'} good={Number(latestCost?.total_variance||0)<=0}/><Kpi title={ar?'إجمالي الانحراف':'Total variance'} value={money.format(Number(latestCost?.total_variance||0))} trend={ar?'موجب = غير مواتٍ':'Positive = unfavorable'} good={Number(latestCost?.total_variance||0)<=0}/><Kpi title={ar?'الطاقة العاطلة':'Idle capacity'} value={money.format(Number(latestCost?.idle_capacity_cost||0))} trend={ar?'تحليلي مستقل':'Separate analytical memo'} good={Number(latestCost?.idle_capacity_cost||0)===0}/></div>
      <Panel title={ar?'إنشاء تحليل تكلفة تفصيلي':'Create detailed cost analysis'} icon={<Factory size={18}/>}><div className="journal-form">
        {Object.entries(cost).map(([key,value])=><label key={key}>{key.split('_').join(' ')}<input type={key.includes('date')||key.includes('period')?'date':'text'} value={value} onChange={e=>setCost({...cost,[key]:e.target.value})}/></label>)}
      </div><div className="journal-footer"><span>{ar?'يشمل مزيج وعائد المواد والأجور والـOverhead والطاقة العاطلة وإعادة التشغيل.':'Includes material mix/yield, labor, overhead, idle capacity and rework.'}</span><button disabled={busy} onClick={createCost}>{ar?'إنشاء التحليل':'Create analysis'}</button></div></Panel>
      <Panel title={ar?'جسر الانحرافات':'Variance bridge'} icon={<BarChart3 size={18}/>}><div className="journal-footer"><span>{latestCost?.analysis_hash||'—'}</span><button onClick={()=>download(`/api/v1/internal-completion/costing/runs/export.csv?company_id=${companyId}`,'advanced_cost_variances.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير':'Export'}</button></div><DataTable headers={[ar?'الفئة':'Category',ar?'المكوّن':'Component',ar?'المبلغ':'Amount',ar?'الطبيعة':'Nature',ar?'الحساب':'Account']} rows={costLines.map((r:any)=>[r.category,r.component_code,money.format(Number(r.amount||0)),r.favorable?(ar?'مواتٍ':'Favorable'):(ar?'غير مواتٍ':'Unfavorable'),r.account_code||'Memo'])}/></Panel>
    </>}

    {tab==='planning'&&<><div className="three-columns"><MiniStatus icon={<BarChart3 size={20}/>} title={ar?'Budget':'Budget'} value={String(scenarios.filter((x:any)=>x.scenario_type==='BUDGET').length)} status={ar?'نسخ مضبوطة':'Controlled versions'}/><MiniStatus icon={<RefreshCw size={20}/>} title={ar?'Forecast':'Forecast'} value={String(scenarios.filter((x:any)=>x.scenario_type.includes('FORECAST')).length)} status={ar?'متجدد ومتدحرج':'Regular and rolling'}/><MiniStatus icon={<ShieldCheck size={20}/>} title={ar?'Frozen':'Frozen'} value={String(scenarios.filter((x:any)=>x.status==='FROZEN').length)} status={ar?'غير قابل للتعديل':'Locked baseline'}/></div>
      <Panel title={ar?'إنشاء سيناريو تخطيط':'Create planning scenario'} icon={<BarChart3 size={18}/>}><div className="journal-form"><label>{ar?'الاسم':'Name'}<input value={plan.name} onChange={e=>setPlan({...plan,name:e.target.value})}/></label><label>{ar?'النوع':'Type'}<select value={plan.scenario_type} onChange={e=>setPlan({...plan,scenario_type:e.target.value})}><option>BUDGET</option><option>FORECAST</option><option>ROLLING_FORECAST</option><option>STRESS</option></select></label><label>{ar?'الحساب':'Account'}<input value={plan.account_code} onChange={e=>setPlan({...plan,account_code:e.target.value})}/></label><label>{ar?'القيمة':'Amount'}<input type="number" value={plan.amount} onChange={e=>setPlan({...plan,amount:e.target.value})}/></label><label>{ar?'من':'From'}<input type="date" value={plan.period_start} onChange={e=>setPlan({...plan,period_start:e.target.value})}/></label><label>{ar?'إلى':'To'}<input type="date" value={plan.period_end} onChange={e=>setPlan({...plan,period_end:e.target.value})}/></label></div><div className="journal-footer"><span>{ar?'يقبل أبعاد الفرع ومركز التكلفة والقسم والمنتج عبر API.':'Supports branch, cost center, department and product dimensions through the API.'}</span><button disabled={busy} onClick={createPlan}>{ar?'إنشاء':'Create'}</button></div></Panel>
      <Panel title={ar?'سجل السيناريوهات':'Scenario register'} icon={<FileCheck2 size={18}/>}><DataTable headers={[ar?'الاسم':'Name',ar?'النوع':'Type',ar?'النسخة':'Version',ar?'الإجمالي':'Total',ar?'الحالة':'Status']} rows={scenarios.map((r:any)=>[r.name,r.scenario_type,String(r.version),money.format(Number(r.total||0)),r.status])}/></Panel>
    </>}

    {tab==='close'&&<><div className="kpis"><Kpi title={ar?'درجة آخر إقفال':'Latest close score'} value={String(latestClose?.score||0)} trend="/100" good={Number(latestClose?.blocker_count||0)===0}/><Kpi title={ar?'العوائق':'Blockers'} value={String(latestClose?.blocker_count||0)} trend={latestClose?.status||'—'} good={Number(latestClose?.blocker_count||0)===0}/><Kpi title={ar?'التحذيرات':'Warnings'} value={String(latestClose?.warning_count||0)} trend={ar?'تحتاج معالجة':'Need action'} good={Number(latestClose?.warning_count||0)===0}/><Kpi title={ar?'النسخ':'Versions'} value={String(closeRuns.length)} trend={ar?'أدلة محفوظة':'Evidence retained'} good/></div>
      <Panel title={ar?'تشغيل قائمة الإقفال الموحدة':'Run unified close checklist'} icon={<FileCheck2 size={18}/>}><SummaryLine label={ar?'الفترة المختارة':'Selected period'} value={(periods.find((p:any)=>p.status==='OPEN')||periods[0])?.name_ar||'—'}/><div className="journal-footer"><span>{ar?'يفحص الأستاذ والبنوك والمخزون والتصنيع والرواتب والضرائب والأصول والنسخ الاحتياطية.':'Checks GL, banks, inventory, manufacturing, payroll, tax, assets and backups.'}</span><button disabled={busy} onClick={createClose}>{ar?'تشغيل الفحص':'Run checklist'}</button></div></Panel>
      <Panel title={ar?'نتيجة آخر فحص':'Latest checklist result'} icon={<ShieldCheck size={18}/>}><DataTable headers={[ar?'المجال':'Area',ar?'الفحص':'Check',ar?'الحالة':'Status',ar?'القيمة الفعلية':'Actual',ar?'المالك':'Owner']} rows={(latestClose?.checks||[]).map((r:any)=>[r.category,ar?r.title_ar:r.title_en,r.status,r.actual_value||'—',r.owner||'—'])}/></Panel>
    </>}

    {tab==='readiness'&&<><div className="kpis rich"><Kpi title={ar?'درجة الجاهزية':'Readiness score'} value={String(latestReady?.score||0)} trend="/100" good={Number(latestReady?.blocker_count||0)===0}/><Kpi title={ar?'العوائق الداخلية':'Internal blockers'} value={String(latestReady?.blocker_count||0)} trend={latestReady?.target_stage||'—'} good={Number(latestReady?.blocker_count||0)===0}/><Kpi title={ar?'التحذيرات':'Warnings'} value={String(latestReady?.warning_count||0)} trend={latestReady?.database_dialect||'—'} good={Number(latestReady?.warning_count||0)===0}/><Kpi title={ar?'رأس الترحيل':'Migration head'} value={latestReady?.expected_migration_head||'—'} trend={ar?'نهائي داخلي':'Final internal'} good/></div>
      <Panel title={ar?'إنشاء تقييم جاهزية داخلي':'Create internal readiness assessment'} icon={<DatabaseBackup size={18}/>}><div className="journal-footer"><span>{ar?'يفصل العوائق الداخلية عن الاعتمادات الخارجية مثل ZATCA والبنوك والجهات الحكومية.':'Separates internal blockers from external credentials such as ZATCA, banks and government platforms.'}</span><button disabled={busy} onClick={createReadiness}>{ar?'تشغيل التقييم':'Run assessment'}</button></div></Panel>
      <Panel title={ar?'مصفوفة الأدلة':'Evidence matrix'} icon={<ShieldCheck size={18}/>}><div className="journal-footer"><span>{latestReady?.status||'—'}</span>{latestReady&&<button onClick={()=>download(`/api/v1/internal-completion/readiness/assessments/${latestReady.id}/export.csv`,'readiness_assessment.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير':'Export'}</button>}</div><DataTable headers={[ar?'الفئة':'Category',ar?'الفحص':'Check',ar?'إلزامي':'Mandatory',ar?'الحالة':'Status',ar?'الدليل':'Evidence']} rows={(latestReady?.checks||[]).map((r:any)=>[r.category,ar?r.title_ar:r.title_en,r.mandatory?(ar?'نعم':'Yes'):(ar?'لا':'No'),r.status,r.evidence_reference||'—'])}/></Panel>
    </>}
  </>;
}
