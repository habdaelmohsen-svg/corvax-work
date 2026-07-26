import {useEffect, useState} from 'react';
import {Scale, FileText, Gavel, BadgeCheck, AlertTriangle} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type Contract={id:number;number:string;title_ar:string;title_en:string;contract_type:string;counterparty_ar?:string;start_date?:string;end_date?:string;value:number;auto_renew:boolean;status:string};
type Case={id:number;number:string;title_ar:string;title_en:string;case_type:string;counterparty_ar?:string;court_ar?:string;filing_date?:string;hearing_date?:string;claim_amount:number;status:string};
type License={id:number;name_ar:string;name_en:string;license_type:string;license_number:string;issuer_ar?:string;issue_date?:string;expiry_date?:string;status:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;

const CONTRACT_TYPES:[string,string,string][]=[['SUPPLIER','مورد','Supplier'],['CUSTOMER','عميل','Customer'],['LEASE','إيجار','Lease'],['EMPLOYMENT','توظيف','Employment'],['SERVICE','خدمة','Service'],['NDA','سرية','NDA'],['OTHER','أخرى','Other']];
const CASE_TYPES:[string,string,string][]=[['COMMERCIAL','تجارية','Commercial'],['LABOR','عمالية','Labor'],['REGULATORY','تنظيمية','Regulatory'],['TAX','ضريبية','Tax'],['OTHER','أخرى','Other']];
const LICENSE_TYPES:[string,string,string][]=[['COMMERCIAL_REGISTRATION','سجل تجاري','Commercial registration'],['MUNICIPAL','رخصة بلدية','Municipal'],['FOOD_SAFETY','سلامة غذاء','Food safety'],['CIVIL_DEFENSE','دفاع مدني','Civil defense'],['OTHER','أخرى','Other']];

export function LegalPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'contracts'|'cases'|'licenses'>('contracts');
  const [contracts,setContracts]=useState<Contract[]>([]);
  const [cases,setCases]=useState<Case[]>([]);
  const [licenses,setLicenses]=useState<License[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // contract
  const [cTitleAr,setCTitleAr]=useState(''); const [cTitleEn,setCTitleEn]=useState(''); const [cType,setCType]=useState('SUPPLIER'); const [cParty,setCParty]=useState(''); const [cStart,setCStart]=useState(''); const [cEnd,setCEnd]=useState(''); const [cValue,setCValue]=useState('0'); const [cRenew,setCRenew]=useState(false);
  // case
  const [kTitleAr,setKTitleAr]=useState(''); const [kTitleEn,setKTitleEn]=useState(''); const [kType,setKType]=useState('COMMERCIAL'); const [kParty,setKParty]=useState(''); const [kCourt,setKCourt]=useState(''); const [kFiling,setKFiling]=useState(''); const [kHearing,setKHearing]=useState(''); const [kClaim,setKClaim]=useState('0');
  // license
  const [lNameAr,setLNameAr]=useState(''); const [lNameEn,setLNameEn]=useState(''); const [lType,setLType]=useState('COMMERCIAL_REGISTRATION'); const [lNumber,setLNumber]=useState(''); const [lIssuer,setLIssuer]=useState(''); const [lIssue,setLIssue]=useState(''); const [lExpiry,setLExpiry]=useState('');

  const load=async()=>{
    try{
      const [c,k,l]=await Promise.all([
        json(`/api/v1/departments/legal/contracts?company_id=${companyId}`),
        json(`/api/v1/departments/legal/cases?company_id=${companyId}`),
        json(`/api/v1/departments/legal/licenses?company_id=${companyId}`),
      ]);
      setContracts(c||[]); setCases(k||[]); setLicenses(l||[]);
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createContract=async()=>{
    if(!cTitleAr||!cTitleEn){setMessage(ar?'العنوانان إلزاميان':'Titles required');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/departments/legal/contracts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,title_ar:cTitleAr,title_en:cTitleEn,contract_type:cType,counterparty_ar:cParty||undefined,start_date:cStart||undefined,end_date:cEnd||undefined,value:Number(cValue),auto_renew:cRenew})});
      setMessage(ar?`تم إنشاء العقد ${r.number}`:`Contract ${r.number} created`);setCTitleAr('');setCTitleEn('');setCParty('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createCase=async()=>{
    if(!kTitleAr||!kTitleEn){setMessage(ar?'العنوانان إلزاميان':'Titles required');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/departments/legal/cases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,title_ar:kTitleAr,title_en:kTitleEn,case_type:kType,counterparty_ar:kParty||undefined,court_ar:kCourt||undefined,filing_date:kFiling||undefined,hearing_date:kHearing||undefined,claim_amount:Number(kClaim)})});
      setMessage(ar?`تم تسجيل القضية ${r.number}`:`Case ${r.number} filed`);setKTitleAr('');setKTitleEn('');setKParty('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createLicense=async()=>{
    if(!lNameAr||!lNameEn||!lNumber){setMessage(ar?'الاسمان والرقم إلزامية':'Names and number required');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/departments/legal/licenses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,name_ar:lNameAr,name_en:lNameEn,license_type:lType,license_number:lNumber,issuer_ar:lIssuer||undefined,issue_date:lIssue||undefined,expiry_date:lExpiry||undefined})});
      setMessage(ar?`تمت إضافة الرخصة (${r.status})`:`License added (${r.status})`);setLNameAr('');setLNameEn('');setLNumber('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const label=(list:[string,string,string][],v:string)=>{const f=list.find(x=>x[0]===v);return f?(ar?f[1]:f[2]):v;};
  const activeContracts=contracts.filter(c=>c.status==='ACTIVE').length;
  const openCases=cases.filter(c=>c.status==='OPEN'||c.status==='IN_PROGRESS').length;
  const expiringLicenses=licenses.filter(l=>l.status==='EXPIRING_SOON'||l.status==='EXPIRED').length;

  const statusBadge=(s:string)=>{
    const map:any={VALID:['✓',ar?'سارية':'Valid'],EXPIRING_SOON:['⚠',ar?'قريبة الانتهاء':'Expiring soon'],EXPIRED:['✗',ar?'منتهية':'Expired']};
    return map[s]?`${map[s][0]} ${map[s][1]}`:s;
  };

  return <>
    <div className="kpis">
      <Kpi title={ar?'العقود':'Contracts'} value={String(contracts.length)} trend={ar?`${activeContracts} سارية`:`${activeContracts} active`} good icon={<FileText size={22}/>} tone="blue"/>
      <Kpi title={ar?'القضايا المفتوحة':'Open cases'} value={String(openCases)} trend="" good={openCases===0} icon={<Gavel size={22}/>} tone="amber"/>
      <Kpi title={ar?'التراخيص':'Licenses'} value={String(licenses.length)} trend="" good icon={<BadgeCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'تراخيص تحتاج انتباه':'Licenses to renew'} value={String(expiringLicenses)} trend="" good={expiringLicenses===0} icon={<AlertTriangle size={22}/>} tone="violet"/>
    </div>
    <div style={{display:'flex',gap:8,margin:'14px 0'}}>
      {([['contracts',ar?'العقود':'Contracts'],['cases',ar?'القضايا':'Cases'],['licenses',ar?'التراخيص':'Licenses']] as [typeof tab,string][]).map(([k,l])=>
        <button key={k} onClick={()=>setTab(k)} style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>
    {message&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {tab==='contracts'&&<>
      <Panel title={ar?'عقد جديد':'New contract'} icon={<FileText size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'العنوان (عربي)':'Title (Arabic)'}<input style={field} value={cTitleAr} onChange={e=>setCTitleAr(e.target.value)}/></label>
          <label>{ar?'العنوان (إنجليزي)':'Title (English)'}<input style={field} value={cTitleEn} onChange={e=>setCTitleEn(e.target.value)}/></label>
          <label>{ar?'النوع':'Type'}<select style={field} value={cType} onChange={e=>setCType(e.target.value)}>{CONTRACT_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'الطرف الآخر':'Counterparty'}<input style={field} value={cParty} onChange={e=>setCParty(e.target.value)}/></label>
          <label>{ar?'البداية':'Start'}<input type="date" style={field} value={cStart} onChange={e=>setCStart(e.target.value)}/></label>
          <label>{ar?'النهاية':'End'}<input type="date" style={field} value={cEnd} onChange={e=>setCEnd(e.target.value)}/></label>
          <label>{ar?'القيمة':'Value'}<input type="number" style={field} value={cValue} onChange={e=>setCValue(e.target.value)}/></label>
          <label style={{display:'flex',alignItems:'center',gap:8,marginTop:24}}><input type="checkbox" checked={cRenew} onChange={e=>setCRenew(e.target.checked)}/>{ar?'تجديد تلقائي':'Auto-renew'}</label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createContract}>{ar?'إنشاء العقد':'Create contract'}</button></div>
      </Panel>
      <Panel title={ar?'العقود':'Contracts'} icon={<FileText size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'العنوان':'Title',ar?'النوع':'Type',ar?'الطرف الآخر':'Counterparty',ar?'النهاية':'End',ar?'القيمة':'Value',ar?'الحالة':'Status']}
          rows={contracts.map(c=>[c.number,ar?c.title_ar:c.title_en,label(CONTRACT_TYPES,c.contract_type),c.counterparty_ar||'—',c.end_date||'—',fmt(Number(c.value)),c.status])}/>
      </Panel>
    </>}

    {tab==='cases'&&<>
      <Panel title={ar?'قضية جديدة':'New case'} icon={<Gavel size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'العنوان (عربي)':'Title (Arabic)'}<input style={field} value={kTitleAr} onChange={e=>setKTitleAr(e.target.value)}/></label>
          <label>{ar?'العنوان (إنجليزي)':'Title (English)'}<input style={field} value={kTitleEn} onChange={e=>setKTitleEn(e.target.value)}/></label>
          <label>{ar?'النوع':'Type'}<select style={field} value={kType} onChange={e=>setKType(e.target.value)}>{CASE_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'الطرف الآخر':'Counterparty'}<input style={field} value={kParty} onChange={e=>setKParty(e.target.value)}/></label>
          <label>{ar?'المحكمة':'Court'}<input style={field} value={kCourt} onChange={e=>setKCourt(e.target.value)}/></label>
          <label>{ar?'تاريخ الرفع':'Filing date'}<input type="date" style={field} value={kFiling} onChange={e=>setKFiling(e.target.value)}/></label>
          <label>{ar?'تاريخ الجلسة':'Hearing date'}<input type="date" style={field} value={kHearing} onChange={e=>setKHearing(e.target.value)}/></label>
          <label>{ar?'قيمة المطالبة':'Claim amount'}<input type="number" style={field} value={kClaim} onChange={e=>setKClaim(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createCase}>{ar?'تسجيل القضية':'File case'}</button></div>
      </Panel>
      <Panel title={ar?'القضايا':'Cases'} icon={<Gavel size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'العنوان':'Title',ar?'النوع':'Type',ar?'المحكمة':'Court',ar?'الجلسة':'Hearing',ar?'المطالبة':'Claim',ar?'الحالة':'Status']}
          rows={cases.map(c=>[c.number,ar?c.title_ar:c.title_en,label(CASE_TYPES,c.case_type),c.court_ar||'—',c.hearing_date||'—',fmt(Number(c.claim_amount)),c.status])}/>
      </Panel>
    </>}

    {tab==='licenses'&&<>
      <Panel title={ar?'رخصة جديدة':'New license'} icon={<BadgeCheck size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={lNameAr} onChange={e=>setLNameAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={lNameEn} onChange={e=>setLNameEn(e.target.value)}/></label>
          <label>{ar?'النوع':'Type'}<select style={field} value={lType} onChange={e=>setLType(e.target.value)}>{LICENSE_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'رقم الرخصة':'License number'}<input style={field} value={lNumber} onChange={e=>setLNumber(e.target.value)}/></label>
          <label>{ar?'الجهة المصدرة':'Issuer'}<input style={field} value={lIssuer} onChange={e=>setLIssuer(e.target.value)}/></label>
          <label>{ar?'تاريخ الإصدار':'Issue date'}<input type="date" style={field} value={lIssue} onChange={e=>setLIssue(e.target.value)}/></label>
          <label>{ar?'تاريخ الانتهاء':'Expiry date'}<input type="date" style={field} value={lExpiry} onChange={e=>setLExpiry(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createLicense}>{ar?'إضافة الرخصة':'Add license'}</button></div>
      </Panel>
      <Panel title={ar?'التراخيص والسجلات':'Licenses & registrations'} icon={<BadgeCheck size={18}/>}>
        <DataTable headers={[ar?'الاسم':'Name',ar?'النوع':'Type',ar?'الرقم':'Number',ar?'الجهة':'Issuer',ar?'الانتهاء':'Expiry',ar?'الحالة':'Status']}
          rows={licenses.map(l=>[ar?l.name_ar:l.name_en,label(LICENSE_TYPES,l.license_type),l.license_number,l.issuer_ar||'—',l.expiry_date||'—',statusBadge(l.status)])}/>
      </Panel>
    </>}
  </>;
}
