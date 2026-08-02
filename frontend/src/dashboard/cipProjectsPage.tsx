import {useEffect, useState} from 'react';
import {Building2, FileSignature, ClipboardCheck, Wallet, Receipt, ArrowRightLeft, AlertTriangle, Paperclip} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type Project={id:number;code:string;name_ar:string;name_en:string;budget_amount:number;capitalized_cost:number;expensed_cost:number;committed_contracts:number;start_date?:string;expected_completion_date?:string;ready_for_use_date?:string;branch_id?:number;cost_center_id?:number;status:string;fixed_asset_id?:number};
type Contract={id:number;number:string;project_id:number;party_name_ar?:string;title_ar:string;title_en:string;contract_type:string;contract_value:number;certified_value:number;remaining_value:number;vat_rate:number;retention_rate:number;status:string};
type Certificate={id:number;number:string;contract_id:number;contract_number?:string;certificate_date:string;work_value:number;vat_amount:number;retention_amount:number;net_payable:number;paid_amount:number;status:string;created_by:number;approved_by?:number};
type Party={id:number;name_ar:string;name_en:string;party_type:string};
type Bank={id:number;bank_name_ar?:string;name_ar?:string};
type Named={id:number;code:string;name_ar:string;name_en:string};
type AssetCategory=Named&{useful_life_months:number};
type Statement=any;

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    throw new Error(typeof d==='string'?d:(d&&d.message_ar)?d.message_ar:JSON.stringify(d||x));
  }
  return x;
}
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'5px 12px',borderRadius:8,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;

const CAP_CATS:[string,string,string][]=[['MATERIALS','مواد','Materials'],['DIRECT_LABOR','عمالة مباشرة','Direct labor'],['SITE_PREPARATION','تجهيز الموقع','Site preparation'],['ENGINEERING','إشراف هندسي','Engineering'],['PERMITS','تصاريح بناء','Permits'],['TRANSPORT_INSTALLATION','نقل وتركيب','Transport & install'],['TESTING','اختبار قبل التشغيل','Testing'],['BORROWING_COST','تكاليف اقتراض','Borrowing cost']];
const EXP_CATS:[string,string,string][]=[['FORMATION_COSTS','مصاريف تأسيس','Formation costs'],['TRAINING','تدريب','Training'],['ADMIN_OVERHEAD','مصاريف إدارية','Admin overhead'],['MARKETING','تسويق وافتتاح','Marketing'],['ABNORMAL_WASTE','هدر غير طبيعي','Abnormal waste'],['IDLE_TIME','توقف غير مخطط','Idle time'],['PRE_OPENING_LOSSES','خسائر تشغيل تجريبي','Pre-opening losses']];

export function CipProjectsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'projects'|'contracts'|'certificates'|'costs'|'statement'|'capitalization'>('projects');
  const [projects,setProjects]=useState<Project[]>([]);
  const [contracts,setContracts]=useState<Contract[]>([]);
  const [certificates,setCertificates]=useState<Certificate[]>([]);
  const [parties,setParties]=useState<Party[]>([]);
  const [banks,setBanks]=useState<Bank[]>([]);
  const [branches,setBranches]=useState<Named[]>([]);
  const [centers,setCenters]=useState<Named[]>([]);
  const [assetCategories,setAssetCategories]=useState<AssetCategory[]>([]);
  const [costs,setCosts]=useState<any[]>([]);
  const [statement,setStatement]=useState<Statement|null>(null);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // project form
  const [pCode,setPCode]=useState(''); const [pNameAr,setPNameAr]=useState(''); const [pNameEn,setPNameEn]=useState('');
  const [pBudget,setPBudget]=useState('0'); const [pStart,setPStart]=useState(iso()); const [pExpected,setPExpected]=useState('');
  const [pDescription,setPDescription]=useState(''); const [pBranch,setPBranch]=useState(''); const [pCenter,setPCenter]=useState('');
  // contract form
  const [cProject,setCProject]=useState(''); const [cParty,setCParty]=useState(''); const [cTitleAr,setCTitleAr]=useState(''); const [cTitleEn,setCTitleEn]=useState(''); const [cValue,setCValue]=useState(''); const [cVat,setCVat]=useState('15'); const [cRetention,setCRetention]=useState('5'); const [cType,setCType]=useState('CONTRACTOR');
  // certificate form
  const [ctContract,setCtContract]=useState(''); const [ctDate,setCtDate]=useState(iso()); const [ctWork,setCtWork]=useState(''); const [ctInv,setCtInv]=useState('');
  // cost form
  const [csProject,setCsProject]=useState(''); const [csCat,setCsCat]=useState('MATERIALS'); const [csTreat,setCsTreat]=useState('CAPITALIZE'); const [csDesc,setCsDesc]=useState(''); const [csAmount,setCsAmount]=useState(''); const [csVat,setCsVat]=useState('0'); const [csAck,setCsAck]=useState(false);
  // payment form
  const [pyContract,setPyContract]=useState(''); const [pyCertificate,setPyCertificate]=useState('');
  const [pyAmount,setPyAmount]=useState(''); const [pyBank,setPyBank]=useState(''); const [pyKind,setPyKind]=useState('CERTIFICATE');
  // statement
  const [stContract,setStContract]=useState('');
  // capitalization
  const [capProject,setCapProject]=useState(''); const [capCategory,setCapCategory]=useState('');
  const [capDate,setCapDate]=useState(iso()); const [capLife,setCapLife]=useState('60'); const [capBank,setCapBank]=useState('');

  const load=async()=>{
    try{
      const [pr,ct,pc,pt,bk,br,cc,ac]=await Promise.all([
        json(`/api/v1/cip/projects?company_id=${companyId}`),
        json(`/api/v1/cip/contracts?company_id=${companyId}`),
        json(`/api/v1/cip/certificates?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/branches`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/cost-centers`).catch(()=>[]),
        json(`/api/v1/assets/categories?company_id=${companyId}`).catch(()=>[]),
      ]);
      setProjects(pr||[]); setContracts(ct||[]); setCertificates(pc||[]);setParties(pt||[]); setBanks(bk||[]);
      setBranches(br||[]);setCenters(cc||[]);setAssetCategories(ac||[]);
      if(!cProject&&pr?.length)setCProject(String(pr[0].id));
      if(!csProject&&pr?.length)setCsProject(String(pr[0].id));
      const sup=(pt||[]).filter((x:Party)=>x.party_type==='SUPPLIER');
      if(!cParty&&sup.length)setCParty(String(sup[0].id));
      if(!ctContract&&ct?.length)setCtContract(String(ct[0].id));
      if(!pyContract&&ct?.length)setPyContract(String(ct[0].id));
      if(!stContract&&ct?.length)setStContract(String(ct[0].id));
      if(!pyBank&&bk?.length)setPyBank(String(bk[0].id));
      if(!pBranch&&br?.length)setPBranch(String(br[0].id));
      if(!pCenter&&cc?.length)setPCenter(String(cc[0].id));
      const open=(pr||[]).find((x:Project)=>x.status!=='CAPITALIZED'&&Number(x.capitalized_cost)>0);
      if(!capProject&&open)setCapProject(String(open.id));
      if(!capCategory&&ac?.length){setCapCategory(String(ac[0].id));setCapLife(String(ac[0].useful_life_months||60));}
      if(!capBank&&bk?.length)setCapBank(String(bk[0].id));
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createProject=async()=>{
    if(!pCode.trim()||!pNameAr.trim()){setMessage(ar?'كود المشروع والاسم العربي إلزاميان':'Project code and Arabic name are required');return;}
    setBusy(true);setMessage('');
    try{const created=await json('/api/v1/cip/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,code:pCode,name_ar:pNameAr,name_en:pNameEn||pNameAr,description:pDescription||null,budget_amount:Number(pBudget),start_date:pStart||null,expected_completion_date:pExpected||null,branch_id:pBranch?Number(pBranch):null,cost_center_id:pCenter?Number(pCenter):null})});
      setMessage(ar?`تم إنشاء المشروع ${created.code} بنجاح وأصبح جاهزًا لإضافة عقد أو تكلفة`:`Project ${created.code} created and ready for contracts or costs`);setPCode('');setPNameAr('');setPNameEn('');setPDescription('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createContract=async()=>{
    if(!cProject||!cParty||!cValue){setMessage(ar?'أكمل بيانات العقد':'Complete contract fields');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/cip/contracts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,project_id:Number(cProject),party_id:Number(cParty),title_ar:cTitleAr||'عقد مقاولة',title_en:cTitleEn||'Contract',contract_type:cType,contract_value:Number(cValue),vat_rate:Number(cVat),retention_rate:Number(cRetention),signed_date:iso()})});
      setMessage(ar?`تم تسجيل العقد ${r.number} — لا قيد محاسبي حتى اعتماد أول مستخلص`:`Contract ${r.number} recorded — no journal until first certificate`);setCValue('');setCTitleAr('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createCertificate=async()=>{
    if(!ctContract||!ctWork){setMessage(ar?'اختر العقد وأدخل قيمة الأعمال':'Select contract and work value');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/cip/certificates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,contract_id:Number(ctContract),certificate_date:ctDate,work_value:Number(ctWork),supplier_invoice_number:ctInv||undefined})});
      setMessage(ar?`مستخلص ${r.number}: أعمال ${fmt(Number(r.work_value))} + ضريبة ${fmt(Number(r.vat_amount))} − محتجز ${fmt(Number(r.retention_amount))} = ${fmt(Number(r.net_payable))}`:`Certificate ${r.number}: net payable ${fmt(Number(r.net_payable))}`);
      setCtWork('');setCtInv('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const approveCertificate=async(id:number)=>{
    setBusy(true);setMessage('');
    try{const r=await json(`/api/v1/cip/certificates/${id}/approve?company_id=${companyId}`,{method:'POST'});
      setMessage(ar?`تم الاعتماد والترحيل (${r.journal_number})`:`Approved and posted (${r.journal_number})`);await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createCost=async()=>{
    if(!csProject||!csDesc||!csAmount){setMessage(ar?'أكمل بيانات التكلفة':'Complete cost fields');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/cip/costs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,project_id:Number(csProject),cost_date:iso(),category:csCat,treatment:csTreat,description_ar:csDesc,amount:Number(csAmount),vat_amount:Number(csVat),acknowledge_warning:csAck})});
      setMessage((r.warning?(ar?`⚠ ${r.warning} — `:`⚠ ${r.warning} — `):'')+(ar?`تم تسجيل التكلفة ${r.number} (${r.treatment==='CAPITALIZE'?'رسملة':'مصروف'})`:`Cost ${r.number} recorded (${r.treatment})`));
      setCsDesc('');setCsAmount('');setCsAck(false);await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createPayment=async()=>{
    if(!pyContract||!pyAmount||!pyBank){setMessage(ar?'أكمل بيانات الدفعة':'Complete payment fields');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/cip/payments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,contract_id:Number(pyContract),certificate_id:pyKind==='CERTIFICATE'&&pyCertificate?Number(pyCertificate):null,payment_date:iso(),amount:Number(pyAmount),payment_kind:pyKind,bank_account_id:Number(pyBank)})});
      setMessage(ar?`تم الصرف ${r.number} (${r.journal_number})`:`Paid ${r.number} (${r.journal_number})`);setPyAmount('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const loadStatement=async()=>{
    if(!stContract)return;
    setBusy(true);setMessage('');
    try{const r=await json(`/api/v1/cip/contracts/${stContract}/statement?company_id=${companyId}`);setStatement(r);}
    catch(e:any){setMessage(String(e.message||e));setStatement(null);}finally{setBusy(false);}
  };
  const loadCosts=async(projectId:string)=>{
    try{const r=await json(`/api/v1/cip/costs?company_id=${companyId}${projectId?`&project_id=${projectId}`:''}`);setCosts(r||[]);}catch{}
  };
  useEffect(()=>{if(tab==='costs')loadCosts(csProject);},[tab,csProject]);
  useEffect(()=>{if(tab==='statement')loadStatement();},[tab]);

  const capitalize=async()=>{
    if(!capProject||!capCategory||!capBank){setMessage(ar?'اختر المشروع وفئة الأصل والبنك':'Select project, asset category and bank');return;}
    setBusy(true);setMessage('');
    try{
      const r=await json(`/api/v1/cip/projects/${capProject}/capitalize`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,ready_for_use_date:capDate,asset_category_id:Number(capCategory),
          useful_life_months:Number(capLife),residual_value:0,depreciation_method:'STRAIGHT_LINE',bank_account_id:Number(capBank)})});
      setMessage(ar?`تمت رسملة المشروع في الأصل ${r.asset_number} وترحيل القيد ${r.journal_number}`:`Project capitalized into ${r.asset_number}; journal ${r.journal_number}`);
      setCapProject('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const suppliers=parties.filter(p=>p.party_type==='SUPPLIER');
  const totalCip=projects.reduce((s,p)=>s+Number(p.capitalized_cost||0),0);
  const totalExpensed=projects.reduce((s,p)=>s+Number(p.expensed_cost||0),0);
  const activeProjects=projects.filter(p=>p.status==='IN_PROGRESS'||p.status==='PLANNING').length;
  const isNonCap=EXP_CATS.some(c=>c[0]===csCat);

  return <>
    <div className="kpis">
      <Kpi title={ar?'المشروعات':'Projects'} value={String(projects.length)} trend={ar?`${activeProjects} نشط`:`${activeProjects} active`} good icon={<Building2 size={22}/>} tone="blue"/>
      <Kpi title={ar?'رصيد تحت التنفيذ':'CIP balance'} value={fmt(totalCip)} trend="155010" good icon={<ClipboardCheck size={22}/>} tone="violet"/>
      <Kpi title={ar?'مصروف على السنة':'Expensed'} value={fmt(totalExpensed)} trend={ar?'لا يُرسمل':'not capitalized'} good icon={<AlertTriangle size={22}/>} tone="amber"/>
      <Kpi title={ar?'العقود':'Contracts'} value={String(contracts.length)} trend="" good icon={<FileSignature size={22}/>} tone="green"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['projects',ar?'المشروعات':'Projects'],['contracts',ar?'العقود':'Contracts'],['certificates',ar?'المستخلصات والدفعات':'Certificates & Payments'],['costs',ar?'التكاليف':'Costs'],['statement',ar?'كشف حساب المقاول':'Contractor Statement'],['capitalization',ar?'الرسملة إلى أصل':'Capitalize to Asset']] as [typeof tab,string][]).map(([k,l])=>
        <button key={k} onClick={()=>setTab(k)} style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>
    {message&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14,lineHeight:1.7}}>{message}</div>}

    {tab==='projects'&&<>
      <Panel title={ar?'مشروع جديد':'New project'} icon={<Building2 size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
          <label>{ar?'كود المشروع':'Code'}<input style={field} value={pCode} onChange={e=>setPCode(e.target.value)} placeholder="PRJ-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={pNameAr} onChange={e=>setPNameAr(e.target.value)} placeholder={ar?'إنشاء هنجر':''}/></label>
          <label>{ar?'الاسم (إنجليزي - اختياري)':'Name (English - optional)'}<input style={field} value={pNameEn} onChange={e=>setPNameEn(e.target.value)}/></label>
          <label>{ar?'الميزانية المعتمدة':'Budget'}<input type="number" style={field} value={pBudget} onChange={e=>setPBudget(e.target.value)}/></label>
          <label>{ar?'تاريخ البدء':'Start date'}<input type="date" style={field} value={pStart} onChange={e=>setPStart(e.target.value)}/></label>
          <label>{ar?'تاريخ الإنجاز المتوقع':'Expected completion'}<input type="date" style={field} value={pExpected} onChange={e=>setPExpected(e.target.value)}/></label>
          <label>{ar?'الفرع':'Branch'}<select style={field} value={pBranch} onChange={e=>setPBranch(e.target.value)}><option value="">{ar?'بدون':'None'}</option>{branches.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}</select></label>
          <label>{ar?'مركز التكلفة':'Cost center'}<select style={field} value={pCenter} onChange={e=>setPCenter(e.target.value)}><option value="">{ar?'بدون':'None'}</option>{centers.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}</select></label>
          <label>{ar?'وصف المشروع':'Description'}<input style={field} value={pDescription} onChange={e=>setPDescription(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createProject}>{ar?'إنشاء المشروع':'Create project'}</button></div>
      </Panel>
      <Panel title={ar?'المشروعات تحت التنفيذ':'Projects under construction'} icon={<Building2 size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'الميزانية':'Budget',ar?'المرسمل':'Capitalized',ar?'المصروف':'Expensed',ar?'التعاقدات':'Committed',ar?'الحالة':'Status']}
          rows={projects.map(p=>[p.code,ar?p.name_ar:p.name_en,fmt(Number(p.budget_amount)),fmt(Number(p.capitalized_cost)),fmt(Number(p.expensed_cost)),fmt(Number(p.committed_contracts)),p.status])}/>
      </Panel>
    </>}

    {tab==='contracts'&&<>
      <Panel title={ar?'عقد مقاول / مورد جديد':'New contractor / supplier contract'} icon={<FileSignature size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.8,lineHeight:1.7}}>
          {ar?'تسجيل العقد لا يُنشئ قيدًا محاسبيًا — يُسجَّل كالتزام رأسمالي للمتابعة فقط. القيد والضريبة يظهران عند اعتماد أول مستخلص.':'Signing records a capital commitment only. The journal entry and VAT arise with the first approved certificate.'}
        </div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
          <label>{ar?'المشروع':'Project'}<select style={field} value={cProject} onChange={e=>setCProject(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.code} — {ar?p.name_ar:p.name_en}</option>)}</select></label>
          <label>{ar?'المقاول / المورد':'Contractor / Supplier'}<select style={field} value={cParty} onChange={e=>setCParty(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{ar?s.name_ar:s.name_en}</option>)}</select></label>
          <label>{ar?'النوع':'Type'}<select style={field} value={cType} onChange={e=>setCType(e.target.value)}><option value="CONTRACTOR">{ar?'مقاول':'Contractor'}</option><option value="SUPPLIER">{ar?'مورد':'Supplier'}</option><option value="CONSULTANT">{ar?'استشاري':'Consultant'}</option></select></label>
          <label>{ar?'عنوان العقد':'Title'}<input style={field} value={cTitleAr} onChange={e=>setCTitleAr(e.target.value)} placeholder={ar?'إنشاء هنجر':''}/></label>
          <label>{ar?'قيمة العقد (بدون ضريبة)':'Value (excl. VAT)'}<input type="number" style={field} value={cValue} onChange={e=>setCValue(e.target.value)}/></label>
          <label>{ar?'الضريبة %':'VAT %'}<input type="number" style={field} value={cVat} onChange={e=>setCVat(e.target.value)}/></label>
          <label>{ar?'المحتجز % (0 = بدون)':'Retention % (0 = none)'}<input type="number" style={field} value={cRetention} onChange={e=>setCRetention(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createContract}>{ar?'تسجيل العقد':'Record contract'}</button></div>
      </Panel>
      <Panel title={ar?'العقود':'Contracts'} icon={<FileSignature size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'المقاول':'Contractor',ar?'العنوان':'Title',ar?'قيمة العقد':'Value',ar?'منفّذ':'Certified',ar?'المتبقي':'Remaining',ar?'محتجز %':'Ret. %',ar?'الحالة':'Status']}
          rows={contracts.map(c=>[c.number,c.party_name_ar||'—',ar?c.title_ar:c.title_en,fmt(Number(c.contract_value)),fmt(Number(c.certified_value)),fmt(Number(c.remaining_value)),`${c.retention_rate}%`,c.status])}/>
      </Panel>
    </>}

    {tab==='certificates'&&<>
      <Panel title={ar?'مستخلص جديد':'New progress certificate'} icon={<ClipboardCheck size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
          <label>{ar?'العقد':'Contract'}<select style={field} value={ctContract} onChange={e=>setCtContract(e.target.value)}>{contracts.map(c=><option key={c.id} value={c.id}>{c.number} — {c.party_name_ar} ({ar?'متبقٍ':'rem.'} {fmt(Number(c.remaining_value))})</option>)}</select></label>
          <label>{ar?'تاريخ المستخلص':'Date'}<input type="date" style={field} value={ctDate} onChange={e=>setCtDate(e.target.value)}/></label>
          <label>{ar?'قيمة الأعمال (بدون ضريبة)':'Work value (excl. VAT)'}<input type="number" style={field} value={ctWork} onChange={e=>setCtWork(e.target.value)}/></label>
          <label>{ar?'رقم فاتورة المقاول':'Supplier invoice #'}<input style={field} value={ctInv} onChange={e=>setCtInv(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createCertificate}>{ar?'إنشاء المستخلص':'Create certificate'}</button></div>
      </Panel>
      <Panel title={ar?'صرف دفعة':'Make a payment'} icon={<Wallet size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
          <label>{ar?'العقد':'Contract'}<select style={field} value={pyContract} onChange={e=>setPyContract(e.target.value)}>{contracts.map(c=><option key={c.id} value={c.id}>{c.number} — {c.party_name_ar}</option>)}</select></label>
          <label>{ar?'نوع الدفعة':'Kind'}<select style={field} value={pyKind} onChange={e=>setPyKind(e.target.value)}><option value="CERTIFICATE">{ar?'سداد مستخلص':'Certificate payment'}</option><option value="RETENTION_RELEASE">{ar?'رد محتجز':'Retention release'}</option></select></label>
          {pyKind==='CERTIFICATE'&&<label>{ar?'المستخلص (اختياري)':'Certificate (optional)'}<select style={field} value={pyCertificate} onChange={e=>setPyCertificate(e.target.value)}><option value="">{ar?'سداد عام على العقد':'General contract payment'}</option>{certificates.filter(c=>c.contract_id===Number(pyContract)&&['APPROVED','PAID'].includes(c.status)).map(c=><option key={c.id} value={c.id}>{c.number} — {fmt(Number(c.net_payable)-Number(c.paid_amount))}</option>)}</select></label>}
          <label>{ar?'المبلغ':'Amount'}<input type="number" style={field} value={pyAmount} onChange={e=>setPyAmount(e.target.value)}/></label>
          <label>{ar?'البنك':'Bank'}<select style={field} value={pyBank} onChange={e=>setPyBank(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{b.bank_name_ar||b.name_ar}</option>)}</select></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createPayment}>{ar?'صرف':'Pay'}</button></div>
      </Panel>
      <Panel title={ar?'المستخلصات ودورة الاعتماد':'Certificates and approval flow'} icon={<ClipboardCheck size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'العقد':'Contract',ar?'التاريخ':'Date',ar?'الأعمال':'Work',ar?'الضريبة':'VAT',ar?'الصافي':'Net',ar?'الحالة':'Status',ar?'الإجراء':'Action']}
          rows={certificates.map(c=>[c.number,c.contract_number||`#${c.contract_id}`,c.certificate_date,fmt(Number(c.work_value)),fmt(Number(c.vat_amount)),fmt(Number(c.net_payable)),c.status,
            c.status==='DRAFT'?<button key={c.id} style={smallBtn} disabled={busy} onClick={()=>approveCertificate(c.id)}>{ar?'اعتماد وترحيل (مستخدم آخر)':'Approve & post (other user)'}</button>:'✓'])}/>
      </Panel>
    </>}

    {tab==='costs'&&<>
      <Panel title={ar?'تكلفة مشروع (مع تصنيف إجباري)':'Project cost (classification required)'} icon={<Receipt size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
          <label>{ar?'المشروع':'Project'}<select style={field} value={csProject} onChange={e=>setCsProject(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.code} — {ar?p.name_ar:p.name_en}</option>)}</select></label>
          <label>{ar?'بند التكلفة':'Category'}
            <select style={field} value={csCat} onChange={e=>{setCsCat(e.target.value);setCsTreat(EXP_CATS.some(c=>c[0]===e.target.value)?'EXPENSE':'CAPITALIZE');setCsAck(false);}}>
              <optgroup label={ar?'تُرسمل (تدخل تكلفة المشروع)':'Capitalizable'}>{CAP_CATS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</optgroup>
              <optgroup label={ar?'تُصرف (لا تدخل الأصل)':'Expensed'}>{EXP_CATS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</optgroup>
            </select></label>
          <label>{ar?'المعالجة':'Treatment'}<select style={field} value={csTreat} onChange={e=>setCsTreat(e.target.value)}><option value="CAPITALIZE">{ar?'رسملة':'Capitalize'}</option><option value="EXPENSE">{ar?'مصروف':'Expense'}</option></select></label>
          <label>{ar?'الوصف':'Description'}<input style={field} value={csDesc} onChange={e=>setCsDesc(e.target.value)}/></label>
          <label>{ar?'المبلغ':'Amount'}<input type="number" style={field} value={csAmount} onChange={e=>setCsAmount(e.target.value)}/></label>
          <label>{ar?'الضريبة':'VAT'}<input type="number" style={field} value={csVat} onChange={e=>setCsVat(e.target.value)}/></label>
        </div>
        {isNonCap&&csTreat==='CAPITALIZE'&&<div style={{margin:'0 12px 12px',padding:12,borderRadius:9,background:'#fef3c7',color:'#92400e',fontSize:13,lineHeight:1.8,display:'flex',gap:10,alignItems:'flex-start'}}>
          <AlertTriangle size={18} style={{flexShrink:0,marginTop:2}}/>
          <div>
            <b>{ar?'تحذير محاسبي':'Accounting warning'}</b><br/>
            {ar?'هذا البند لا يُرسمل عادةً حسب المعايير الدولية — يُحمّل على مصروفات العام. أنت تستطيع المتابعة، لكن القرار مسؤوليتك.':'This category is normally expensed under IFRS, not capitalized. You may proceed, but the decision is yours.'}
            <label style={{display:'flex',alignItems:'center',gap:8,marginTop:8,fontWeight:600}}>
              <input type="checkbox" checked={csAck} onChange={e=>setCsAck(e.target.checked)}/>{ar?'أفهم وأريد الرسملة رغم ذلك':'I understand and want to capitalize anyway'}
            </label>
          </div>
        </div>}
        <div style={{padding:'0 12px 12px'}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createCost}>{ar?'تسجيل التكلفة':'Record cost'}</button></div>
      </Panel>
      <Panel title={ar?'تكاليف المشروع':'Project costs'} icon={<Receipt size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'البند':'Category',ar?'المعالجة':'Treatment',ar?'الوصف':'Description',ar?'المبلغ':'Amount']}
          rows={costs.map(c=>[c.number,c.cost_date,c.category,c.treatment==='CAPITALIZE'?(ar?'رسملة':'Capitalize'):(ar?'مصروف':'Expense'),c.description_ar,fmt(Number(c.amount))])}/>
      </Panel>
    </>}

    {tab==='statement'&&<>
      <Panel title={ar?'كشف حساب المقاول':'Contractor statement'} icon={<ArrowRightLeft size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12,alignItems:'end'}}>
          <label>{ar?'العقد':'Contract'}<select style={field} value={stContract} onChange={e=>setStContract(e.target.value)}>{contracts.map(c=><option key={c.id} value={c.id}>{c.number} — {c.party_name_ar}</option>)}</select></label>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={loadStatement}>{ar?'عرض الكشف':'Show statement'}</button>
        </div>
      </Panel>
      {statement&&<>
        <Panel title={`${ar?'الملخص':'Summary'} — ${statement.contract.party_name_ar||''} (${statement.contract.number})`} icon={<ClipboardCheck size={18}/>}>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(240px,1fr))',gap:14,padding:14}}>
            <div style={{padding:14,borderRadius:10,background:'var(--panel-2, #f1f5f9)'}}>
              <div style={{fontWeight:700,marginBottom:8}}>{ar?'الأعمال':'Work'}</div>
              <div style={{fontSize:13,lineHeight:2}}>
                {ar?'قيمة العقد':'Contract value'}: <b>{fmt(Number(statement.contract.contract_value))}</b><br/>
                {ar?'المنفّذ':'Certified'}: <b>{fmt(Number(statement.work.certified_value))}</b><br/>
                {ar?'المتبقي للتنفيذ':'Remaining work'}: <b style={{color:'#1e40af'}}>{fmt(Number(statement.work.remaining_contract_value))}</b><br/>
                {ar?'نسبة الإنجاز':'Progress'}: <b>{Number(statement.work.progress_percent).toFixed(1)}%</b>
              </div>
            </div>
            <div style={{padding:14,borderRadius:10,background:'var(--panel-2, #f1f5f9)'}}>
              <div style={{fontWeight:700,marginBottom:8}}>{ar?'المستحقات':'Money'}</div>
              <div style={{fontSize:13,lineHeight:2}}>
                {ar?'ضريبة':'VAT'}: <b>{fmt(Number(statement.money.vat_total))}</b><br/>
                {ar?'إجمالي بالضريبة':'Gross'}: <b>{fmt(Number(statement.money.gross_certified))}</b><br/>
                {ar?'مدفوع':'Paid'}: <b>{fmt(Number(statement.money.paid))}</b><br/>
                {ar?'الرصيد المستحق':'Outstanding'}: <b style={{color:'#b45309'}}>{fmt(Number(statement.money.outstanding_balance))}</b>
              </div>
            </div>
            <div style={{padding:14,borderRadius:10,background:'var(--panel-2, #f1f5f9)'}}>
              <div style={{fontWeight:700,marginBottom:8}}>{ar?'المحتجز':'Retention'}</div>
              <div style={{fontSize:13,lineHeight:2}}>
                {ar?'محتجز لديك':'Held'}: <b style={{color:'#059669'}}>{fmt(Number(statement.money.retention_held))}</b><br/>
                {ar?'تم رده':'Released'}: <b>{fmt(Number(statement.money.retention_released))}</b><br/>
                {ar?'النسبة':'Rate'}: <b>{statement.contract.retention_rate}%</b>
              </div>
            </div>
          </div>
        </Panel>
        <Panel title={ar?'المستخلصات':'Certificates'} icon={<ClipboardCheck size={18}/>}>
          <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'الأعمال':'Work',ar?'الضريبة':'VAT',ar?'المحتجز':'Retention',ar?'صافي مستحق':'Net',ar?'مدفوع':'Paid',ar?'الحالة':'Status',ar?'إجراء':'Action']}
            rows={(statement.certificates||[]).map((c:any)=>[c.number,c.date,fmt(Number(c.work_value)),fmt(Number(c.vat_amount)),fmt(Number(c.retention_amount)),fmt(Number(c.net_payable)),fmt(Number(c.paid_amount)),c.status,'—'])}/>
        </Panel>
        <Panel title={ar?'الدفعات':'Payments'} icon={<Wallet size={18}/>}>
          <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المبلغ':'Amount',ar?'النوع':'Kind',ar?'المرجع':'Reference']}
            rows={(statement.payments||[]).map((p:any)=>[p.number,p.date,fmt(Number(p.amount)),p.kind==='RETENTION_RELEASE'?(ar?'رد محتجز':'Retention'):(ar?'سداد':'Payment'),p.reference||'—'])}/>
        </Panel>
      </>}
    </>}

    {tab==='capitalization'&&<>
      <Panel title={ar?'تحويل مشروع مكتمل إلى أصل ثابت':'Transfer completed project to a fixed asset'} icon={<ArrowRightLeft size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:.82,lineHeight:1.8}}>
          {ar?'لا تتم الرسملة إلا عند جاهزية الأصل للاستخدام. ينقل النظام رصيد 155010 إلى الأصل ويبدأ الإهلاك من تاريخ الجاهزية، ويمنع أي تكلفة أو مستخلص جديد بعد الرسملة.':'Capitalize only when ready for use. The system clears 155010 into the asset, starts depreciation at the ready date, and blocks later project costs or certificates.'}
        </div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(190px,1fr))',gap:12,padding:12}}>
          <label>{ar?'المشروع':'Project'}<select style={field} value={capProject} onChange={e=>setCapProject(e.target.value)}><option value="">{ar?'اختر':'Select'}</option>{projects.filter(p=>p.status!=='CAPITALIZED'&&Number(p.capitalized_cost)>0).map(p=><option key={p.id} value={p.id}>{p.code} — {ar?p.name_ar:p.name_en} ({fmt(Number(p.capitalized_cost))})</option>)}</select></label>
          <label>{ar?'فئة الأصل':'Asset category'}<select style={field} value={capCategory} onChange={e=>{setCapCategory(e.target.value);const c=assetCategories.find(x=>String(x.id)===e.target.value);if(c)setCapLife(String(c.useful_life_months))}}><option value="">{ar?'اختر':'Select'}</option>{assetCategories.map(c=><option key={c.id} value={c.id}>{c.code} — {ar?c.name_ar:c.name_en}</option>)}</select></label>
          <label>{ar?'تاريخ الجاهزية للاستخدام':'Ready-for-use date'}<input type="date" style={field} value={capDate} onChange={e=>setCapDate(e.target.value)}/></label>
          <label>{ar?'العمر الإنتاجي بالشهور':'Useful life (months)'}<input type="number" min="1" style={field} value={capLife} onChange={e=>setCapLife(e.target.value)}/></label>
          <label>{ar?'حساب البنك المرجعي':'Reference bank'}<select style={field} value={capBank} onChange={e=>setCapBank(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{b.bank_name_ar||b.name_ar||`#${b.id}`}</option>)}</select></label>
        </div>
        <div style={{padding:'0 12px 14px'}}><button style={btn} disabled={busy} onClick={capitalize}>{ar?'اعتماد الرسملة وإنشاء الأصل':'Capitalize and create asset'}</button></div>
      </Panel>
    </>}
  </>;
}
