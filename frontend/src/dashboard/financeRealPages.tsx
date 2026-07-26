import {useEffect, useState} from 'react';
import {Building2, CalendarRange, Receipt, ClipboardCheck, Play, Plus} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Real working screens replacing the previous demo pages.
// The old versions posted hard-coded sample data with frozen dates
// (e.g. "أصل تجريبي", acquisition_date '2026-07-12'). These take real input.

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    throw new Error(typeof d==='string'?d:(Array.isArray(d)?d.map((i:any)=>i.msg||JSON.stringify(i)).join(' | '):JSON.stringify(d||x)));
  }
  return x;
}
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const monthEnd=()=>{const d=new Date();return iso(new Date(d.getFullYear(),d.getMonth()+1,0));};
const addYear=(n=1)=>{const d=new Date();d.setFullYear(d.getFullYear()+n);return iso(d);};
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const ghost={padding:'9px 16px',borderRadius:9,border:'1px solid var(--border)',background:'transparent',color:'var(--text)',cursor:'pointer',fontWeight:600} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12} as const;

type Bank={id:number;bank_name_ar?:string;name_ar?:string};
type Account={code:string;name_ar:string;name_en:string;is_postable:boolean;active:boolean};
type Dim={id:number;code:string;name_ar:string;name_en:string};

function useCommon(companyId:number){
  const [banks,setBanks]=useState<Bank[]>([]);
  const [accounts,setAccounts]=useState<Account[]>([]);
  const [branches,setBranches]=useState<Dim[]>([]);
  const [costCenters,setCostCenters]=useState<Dim[]>([]);
  useEffect(()=>{(async()=>{
    try{
      const [b,ch,br,cc]=await Promise.all([
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/chart-of-accounts`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/branches`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/cost-centers`).catch(()=>[]),
      ]);
      setBanks(Array.isArray(b)?b:[]);
      const rows:Account[]=Array.isArray(ch)?ch:[];
      setAccounts(rows.filter(a=>a.is_postable&&a.active));
      setBranches(Array.isArray(br)?br:[]); setCostCenters(Array.isArray(cc)?cc:[]);
    }catch{}
  })()},[companyId]);
  return {banks,accounts,branches,costCenters};
}
const bankName=(b:Bank)=>b.bank_name_ar||b.name_ar||`#${b.id}`;

// ==================================================== FIXED ASSETS (IAS 16)
export function AssetsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const {banks,branches,costCenters}=useCommon(companyId);
  const [categories,setCategories]=useState<any[]>([]);
  const [assets,setAssets]=useState<any[]>([]);
  const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [catId,setCatId]=useState(''); const [acqDate,setAcqDate]=useState(iso());
  const [svcDate,setSvcDate]=useState(iso()); const [cost,setCost]=useState('');
  const [residual,setResidual]=useState('0'); const [life,setLife]=useState('60');
  const [bankId,setBankId]=useState(''); const [branchId,setBranchId]=useState(''); const [ccId,setCcId]=useState('');
  const [depDate,setDepDate]=useState(monthEnd());

  const load=async()=>{
    try{
      const [c,a,s]=await Promise.all([
        json(`/api/v1/assets/categories?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/assets?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/assets/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setCategories(Array.isArray(c)?c:[]); setAssets(Array.isArray(a)?a:[]); setSummary(s);
      if(!catId&&c?.length)setCatId(String(c[0].id));
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{if(!bankId&&banks.length)setBankId(String(banks[0].id));},[banks]);

  const create=async()=>{
    if(!nameAr||!nameEn||!catId||!cost||!bankId){setMsg(ar?'أكمل الحقول الإلزامية':'Complete required fields');return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,name_ar:nameAr,name_en:nameEn,category_id:Number(catId),
        acquisition_date:acqDate,in_service_date:svcDate,cost:Number(cost),
        residual_value:Number(residual)||0,useful_life_months:Number(life),bank_account_id:Number(bankId)};
      if(branchId)body.branch_id=Number(branchId);
      if(ccId)body.cost_center_id=Number(ccId);
      const r=await json('/api/v1/assets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تمت رسملة الأصل ${r.asset_number||r.id}`:`Asset ${r.asset_number||r.id} capitalized`);
      setNameAr('');setNameEn('');setCost('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const runDep=async()=>{
    setBusy(true);setMsg('');
    try{const r=await json('/api/v1/assets/depreciation/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,as_of_date:depDate})});
      setMsg(ar?`تم ترحيل إهلاك بقيمة ${fmt(Number(r.depreciation_amount||0))}`:`Depreciation ${fmt(Number(r.depreciation_amount||0))} posted`);await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  return <>
    <div className="kpis">
      <Kpi title={ar?'عدد الأصول':'Assets'} value={String(assets.length)} trend="" good icon={<Building2 size={22}/>} tone="blue"/>
      <Kpi title={ar?'التكلفة':'Cost'} value={summary?fmt(Number(summary.total_cost||0)):'—'} trend="" good icon={<Building2 size={22}/>} tone="violet"/>
      <Kpi title={ar?'مجمع الإهلاك':'Accum. depreciation'} value={summary?fmt(Number(summary.accumulated_depreciation||0)):'—'} trend="" good icon={<CalendarRange size={22}/>} tone="amber"/>
      <Kpi title={ar?'القيمة الدفترية':'Net book value'} value={summary?fmt(Number(summary.net_book_value||0)):'—'} trend="IAS 16" good icon={<ClipboardCheck size={22}/>} tone="green"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'رسملة أصل ثابت جديد':'Capitalize a new fixed asset'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
        <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
        <label>{ar?'الفئة':'Category'}<select style={field} value={catId} onChange={e=>setCatId(e.target.value)}>{categories.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
        <label>{ar?'تاريخ الاقتناء':'Acquisition date'}<input type="date" style={field} value={acqDate} onChange={e=>setAcqDate(e.target.value)}/></label>
        <label>{ar?'تاريخ التشغيل':'In-service date'}<input type="date" style={field} value={svcDate} onChange={e=>setSvcDate(e.target.value)}/></label>
        <label>{ar?'التكلفة':'Cost'}<input type="number" style={field} value={cost} onChange={e=>setCost(e.target.value)}/></label>
        <label>{ar?'القيمة المتبقية':'Residual value'}<input type="number" style={field} value={residual} onChange={e=>setResidual(e.target.value)}/></label>
        <label>{ar?'العمر الإنتاجي (شهر)':'Useful life (months)'}<input type="number" style={field} value={life} onChange={e=>setLife(e.target.value)}/></label>
        <label>{ar?'البنك (مصدر الدفع)':'Bank'}<select style={field} value={bankId} onChange={e=>setBankId(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{bankName(b)}</option>)}</select></label>
        <label>{ar?'الفرع (اختياري)':'Branch (optional)'}<select style={field} value={branchId} onChange={e=>setBranchId(e.target.value)}><option value="">—</option>{branches.map(b=><option key={b.id} value={b.id}>{ar?b.name_ar:b.name_en}</option>)}</select></label>
        <label>{ar?'مركز التكلفة (اختياري)':'Cost center (optional)'}<select style={field} value={ccId} onChange={e=>setCcId(e.target.value)}><option value="">—</option>{costCenters.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'رسملة الأصل':'Capitalize asset'}</button></div>
    </Panel>

    <Panel title={ar?'تشغيل الإهلاك الشهري':'Run monthly depreciation'} icon={<Play size={18}/>}>
      <div style={{...grid,alignItems:'end'}}>
        <label>{ar?'حتى تاريخ':'As of date'}<input type="date" style={field} value={depDate} onChange={e=>setDepDate(e.target.value)}/></label>
        <button style={{...ghost,opacity:busy?0.6:1}} disabled={busy} onClick={runDep}>{ar?'ترحيل الإهلاك':'Post depreciation'}</button>
      </div>
    </Panel>

    <Panel title={ar?'سجل الأصول':'Asset register'} icon={<Building2 size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'الاسم':'Name',ar?'التكلفة':'Cost',ar?'مجمع الإهلاك':'Accum.',ar?'القيمة الدفترية':'NBV',ar?'الحالة':'Status']}
        rows={assets.map((a:any)=>[a.asset_number||a.id,ar?a.name_ar:a.name_en,fmt(Number(a.cost||0)),fmt(Number(a.accumulated_depreciation||0)),fmt(Number(a.net_book_value||0)),a.status])}/>
    </Panel>
  </>;
}

// ==================================================== LEASES (IFRS 16)
export function LeasesPage({ar,companyId}:{ar:boolean;companyId:number}){
  const {banks}=useCommon(companyId);
  const [leases,setLeases]=useState<any[]>([]); const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [start,setStart]=useState(iso()); const [end,setEnd]=useState(addYear(1));
  const [amount,setAmount]=useState(''); const [freq,setFreq]=useState('1');
  const [timing,setTiming]=useState('ARREARS'); const [rate,setRate]=useState('5');
  const [bankId,setBankId]=useState(''); const [runDate,setRunDate]=useState(monthEnd());

  const load=async()=>{
    try{
      const [l,s]=await Promise.all([
        json(`/api/v1/leases?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/leases/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setLeases(Array.isArray(l)?l:[]); setSummary(s);
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{if(!bankId&&banks.length)setBankId(String(banks[0].id));},[banks]);

  const create=async()=>{
    if(!nameAr||!nameEn||!amount||!bankId){setMsg(ar?'أكمل الحقول الإلزامية':'Complete required fields');return;}
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/leases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        company_id:companyId,name_ar:nameAr,name_en:nameEn,commencement_date:start,end_date:end,
        payment_amount:Number(amount),payment_frequency_months:Number(freq),payment_timing:timing,
        annual_discount_rate:Number(rate)/100,bank_account_id:Number(bankId)})});
      setMsg(ar?`تم إنشاء عقد الإيجار ${r.id||''} — أصل حق الاستخدام والالتزام مُثبتان`:`Lease created — ROU asset and liability recognised`);
      setNameAr('');setNameEn('');setAmount('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const post=async()=>{
    setBusy(true);setMsg('');
    try{const r=await json('/api/v1/leases/post-schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,as_of_date:runDate})});
      setMsg(ar?`تم ترحيل ${r.posted_count||0} فترة`:`${r.posted_count||0} period(s) posted`);await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  return <>
    <div className="kpis">
      <Kpi title={ar?'العقود':'Leases'} value={String(leases.length)} trend="IFRS 16" good icon={<CalendarRange size={22}/>} tone="blue"/>
      <Kpi title={ar?'أصل حق الاستخدام':'ROU asset'} value={summary?fmt(Number(summary.rou_asset||summary.total_rou||0)):'—'} trend="" good icon={<Building2 size={22}/>} tone="violet"/>
      <Kpi title={ar?'التزام الإيجار':'Lease liability'} value={summary?fmt(Number(summary.lease_liability||summary.total_liability||0)):'—'} trend="" good icon={<Receipt size={22}/>} tone="amber"/>
      <Kpi title={ar?'فترات مرحّلة':'Posted periods'} value={summary?String(summary.posted_periods||0):'—'} trend="" good icon={<ClipboardCheck size={22}/>} tone="green"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'عقد إيجار جديد':'New lease contract'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
        <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
        <label>{ar?'تاريخ البدء':'Commencement'}<input type="date" style={field} value={start} onChange={e=>setStart(e.target.value)}/></label>
        <label>{ar?'تاريخ الانتهاء':'End date'}<input type="date" style={field} value={end} onChange={e=>setEnd(e.target.value)}/></label>
        <label>{ar?'قيمة الدفعة':'Payment amount'}<input type="number" style={field} value={amount} onChange={e=>setAmount(e.target.value)}/></label>
        <label>{ar?'كل كم شهر':'Every N months'}<input type="number" min="1" max="12" style={field} value={freq} onChange={e=>setFreq(e.target.value)}/></label>
        <label>{ar?'توقيت الدفع':'Payment timing'}<select style={field} value={timing} onChange={e=>setTiming(e.target.value)}><option value="ARREARS">{ar?'نهاية الفترة':'In arrears'}</option><option value="ADVANCE">{ar?'بداية الفترة':'In advance'}</option></select></label>
        <label>{ar?'معدل الخصم السنوي %':'Annual discount rate %'}<input type="number" step="0.1" style={field} value={rate} onChange={e=>setRate(e.target.value)}/></label>
        <label>{ar?'البنك':'Bank'}<select style={field} value={bankId} onChange={e=>setBankId(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{bankName(b)}</option>)}</select></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'إنشاء العقد':'Create lease'}</button></div>
    </Panel>

    <Panel title={ar?'ترحيل جداول الإيجار':'Post lease schedules'} icon={<Play size={18}/>}>
      <div style={{...grid,alignItems:'end'}}>
        <label>{ar?'حتى تاريخ':'As of date'}<input type="date" style={field} value={runDate} onChange={e=>setRunDate(e.target.value)}/></label>
        <button style={{...ghost,opacity:busy?0.6:1}} disabled={busy} onClick={post}>{ar?'ترحيل':'Post schedules'}</button>
      </div>
    </Panel>

    <Panel title={ar?'عقود الإيجار':'Lease contracts'} icon={<CalendarRange size={18}/>}>
      <DataTable headers={[ar?'الاسم':'Name',ar?'البدء':'Start',ar?'الانتهاء':'End',ar?'الدفعة':'Payment',ar?'الحالة':'Status']}
        rows={leases.map((l:any)=>[ar?l.name_ar:l.name_en,l.commencement_date,l.end_date,fmt(Number(l.payment_amount||0)),l.status||'ACTIVE'])}/>
    </Panel>
  </>;
}

// ==================================================== PREPAIDS
export function PrepaidsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const {banks,accounts,branches}=useCommon(companyId);
  const [rows,setRows]=useState<any[]>([]); const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState(''); const [supplier,setSupplier]=useState('');
  const [payDate,setPayDate]=useState(iso()); const [svcStart,setSvcStart]=useState(iso()); const [svcEnd,setSvcEnd]=useState(addYear(1));
  const [net,setNet]=useState(''); const [vat,setVat]=useState('15');
  const [expAcc,setExpAcc]=useState('613010'); const [bankId,setBankId]=useState(''); const [branchId,setBranchId]=useState('');
  const [amortDate,setAmortDate]=useState(monthEnd());

  const load=async()=>{
    try{
      const [p,s]=await Promise.all([
        json(`/api/v1/prepaids?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/prepaids/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setRows(Array.isArray(p)?p:[]); setSummary(s);
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{if(!bankId&&banks.length)setBankId(String(banks[0].id));},[banks]);

  const create=async()=>{
    if(!nameAr||!nameEn||!net||!bankId){setMsg(ar?'أكمل الحقول الإلزامية':'Complete required fields');return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,name_ar:nameAr,name_en:nameEn,payment_date:payDate,
        service_start_date:svcStart,service_end_date:svcEnd,net_amount:Number(net),vat_rate:Number(vat),
        expense_account_code:expAcc,bank_account_id:Number(bankId)};
      if(supplier)body.supplier_name=supplier;
      if(branchId)body.branch_id=Number(branchId);
      const r=await json('/api/v1/prepaids',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تم تسجيل المصروف المقدم ${r.id||''}`:`Prepaid ${r.id||''} recorded`);
      setNameAr('');setNameEn('');setNet('');setSupplier('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const amortize=async()=>{
    setBusy(true);setMsg('');
    try{const r=await json('/api/v1/prepaids/amortize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,as_of_date:amortDate})});
      setMsg(ar?`تم إطفاء ${fmt(Number(r.amortized_amount||r.total||0))}`:`Amortized ${fmt(Number(r.amortized_amount||r.total||0))}`);await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  return <>
    <div className="kpis">
      <Kpi title={ar?'المصروفات المقدمة':'Prepaids'} value={String(rows.length)} trend="" good icon={<Receipt size={22}/>} tone="blue"/>
      <Kpi title={ar?'الرصيد غير المطفأ':'Unamortized'} value={summary?fmt(Number(summary.unamortized||summary.balance||0)):'—'} trend="117010" good icon={<Receipt size={22}/>} tone="violet"/>
      <Kpi title={ar?'المطفأ':'Amortized'} value={summary?fmt(Number(summary.amortized||0)):'—'} trend="" good icon={<ClipboardCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'الإجمالي':'Total'} value={summary?fmt(Number(summary.total||0)):'—'} trend="" good icon={<CalendarRange size={22}/>} tone="amber"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'مصروف مقدم جديد':'New prepaid expense'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
        <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
        <label>{ar?'المورد':'Supplier'}<input style={field} value={supplier} onChange={e=>setSupplier(e.target.value)}/></label>
        <label>{ar?'تاريخ الدفع':'Payment date'}<input type="date" style={field} value={payDate} onChange={e=>setPayDate(e.target.value)}/></label>
        <label>{ar?'بداية الخدمة':'Service start'}<input type="date" style={field} value={svcStart} onChange={e=>setSvcStart(e.target.value)}/></label>
        <label>{ar?'نهاية الخدمة':'Service end'}<input type="date" style={field} value={svcEnd} onChange={e=>setSvcEnd(e.target.value)}/></label>
        <label>{ar?'المبلغ الصافي':'Net amount'}<input type="number" style={field} value={net} onChange={e=>setNet(e.target.value)}/></label>
        <label>{ar?'الضريبة %':'VAT %'}<input type="number" style={field} value={vat} onChange={e=>setVat(e.target.value)}/></label>
        <label>{ar?'حساب المصروف':'Expense account'}<select style={field} value={expAcc} onChange={e=>setExpAcc(e.target.value)}>{accounts.filter(a=>a.code.startsWith('6')).map(a=><option key={a.code} value={a.code}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}</select></label>
        <label>{ar?'البنك':'Bank'}<select style={field} value={bankId} onChange={e=>setBankId(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{bankName(b)}</option>)}</select></label>
        <label>{ar?'الفرع (اختياري)':'Branch (optional)'}<select style={field} value={branchId} onChange={e=>setBranchId(e.target.value)}><option value="">—</option>{branches.map(b=><option key={b.id} value={b.id}>{ar?b.name_ar:b.name_en}</option>)}</select></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'تسجيل المصروف المقدم':'Record prepaid'}</button></div>
    </Panel>

    <Panel title={ar?'تشغيل الإطفاء':'Run amortization'} icon={<Play size={18}/>}>
      <div style={{...grid,alignItems:'end'}}>
        <label>{ar?'حتى تاريخ':'As of date'}<input type="date" style={field} value={amortDate} onChange={e=>setAmortDate(e.target.value)}/></label>
        <button style={{...ghost,opacity:busy?0.6:1}} disabled={busy} onClick={amortize}>{ar?'إطفاء':'Amortize'}</button>
      </div>
    </Panel>

    <Panel title={ar?'المصروفات المقدمة':'Prepaid expenses'} icon={<Receipt size={18}/>}>
      <DataTable headers={[ar?'الاسم':'Name',ar?'الدفع':'Paid',ar?'من':'From',ar?'إلى':'To',ar?'المبلغ':'Amount',ar?'الحالة':'Status']}
        rows={rows.map((p:any)=>[ar?p.name_ar:p.name_en,p.payment_date,p.service_start_date,p.service_end_date,fmt(Number(p.net_amount||0)),p.status||'ACTIVE'])}/>
    </Panel>
  </>;
}

// ==================================================== ACCRUALS
export function AccrualsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const {accounts,branches,costCenters}=useCommon(companyId);
  const [rows,setRows]=useState<any[]>([]); const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState(''); const [reference,setReference]=useState('');
  const [accDate,setAccDate]=useState(monthEnd()); const [amount,setAmount]=useState('');
  const [debitAcc,setDebitAcc]=useState('613010'); const [creditAcc,setCreditAcc]=useState('217010');
  const [autoRev,setAutoRev]=useState(true); const [revDate,setRevDate]=useState('');
  const [branchId,setBranchId]=useState(''); const [ccId,setCcId]=useState('');
  const [runDate,setRunDate]=useState(monthEnd());

  const load=async()=>{
    try{
      const [a,s]=await Promise.all([
        json(`/api/v1/accruals?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/accruals/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setRows(Array.isArray(a)?a:[]); setSummary(s);
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const create=async()=>{
    if(!nameAr||!nameEn||!amount){setMsg(ar?'أكمل الحقول الإلزامية':'Complete required fields');return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,name_ar:nameAr,name_en:nameEn,accrual_date:accDate,
        amount:Number(amount),debit_account_code:debitAcc,credit_account_code:creditAcc,auto_reverse:autoRev};
      if(reference)body.reference=reference;
      if(autoRev&&revDate)body.reversal_date=revDate;
      if(branchId)body.branch_id=Number(branchId);
      if(ccId)body.cost_center_id=Number(ccId);
      const r=await json('/api/v1/accruals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تم تسجيل الاستحقاق ${r.id||''}`:`Accrual ${r.id||''} recorded`);
      setNameAr('');setNameEn('');setAmount('');setReference('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const post=async(id:number)=>{
    setBusy(true);setMsg('');
    try{await json(`/api/v1/accruals/${id}/post`,{method:'POST'});setMsg(ar?'تم ترحيل الاستحقاق':'Accrual posted');await load();}
    catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const runRev=async()=>{
    setBusy(true);setMsg('');
    try{const r=await json('/api/v1/accruals/run-reversals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,as_of_date:runDate})});
      setMsg(ar?`تم عكس ${r.reversed_count||0} استحقاق`:`${r.reversed_count||0} accrual(s) reversed`);await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const expenseAccounts=accounts.filter(a=>a.code.startsWith('6')||a.code.startsWith('5'));
  const liabilityAccounts=accounts.filter(a=>a.code.startsWith('2'));

  return <>
    <div className="kpis">
      <Kpi title={ar?'الاستحقاقات':'Accruals'} value={String(rows.length)} trend="" good icon={<ClipboardCheck size={22}/>} tone="blue"/>
      <Kpi title={ar?'قائمة':'Outstanding'} value={summary?fmt(Number(summary.outstanding||0)):'—'} trend="217010" good icon={<Receipt size={22}/>} tone="amber"/>
      <Kpi title={ar?'مرحّلة':'Posted'} value={summary?String(summary.posted_count||0):String(rows.filter((r:any)=>r.status==='POSTED').length)} trend="" good icon={<ClipboardCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'معكوسة':'Reversed'} value={summary?String(summary.reversed_count||0):'—'} trend="" good icon={<CalendarRange size={22}/>} tone="violet"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'استحقاق جديد':'New accrual'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
        <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
        <label>{ar?'المرجع':'Reference'}<input style={field} value={reference} onChange={e=>setReference(e.target.value)}/></label>
        <label>{ar?'تاريخ الاستحقاق':'Accrual date'}<input type="date" style={field} value={accDate} onChange={e=>setAccDate(e.target.value)}/></label>
        <label>{ar?'المبلغ':'Amount'}<input type="number" style={field} value={amount} onChange={e=>setAmount(e.target.value)}/></label>
        <label>{ar?'حساب مدين (مصروف)':'Debit account'}<select style={field} value={debitAcc} onChange={e=>setDebitAcc(e.target.value)}>{expenseAccounts.map(a=><option key={a.code} value={a.code}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}</select></label>
        <label>{ar?'حساب دائن (التزام)':'Credit account'}<select style={field} value={creditAcc} onChange={e=>setCreditAcc(e.target.value)}>{liabilityAccounts.map(a=><option key={a.code} value={a.code}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}</select></label>
        <label>{ar?'الفرع (اختياري)':'Branch'}<select style={field} value={branchId} onChange={e=>setBranchId(e.target.value)}><option value="">—</option>{branches.map(b=><option key={b.id} value={b.id}>{ar?b.name_ar:b.name_en}</option>)}</select></label>
        <label>{ar?'مركز التكلفة (اختياري)':'Cost center'}<select style={field} value={ccId} onChange={e=>setCcId(e.target.value)}><option value="">—</option>{costCenters.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
        <label style={{display:'flex',alignItems:'center',gap:8,marginTop:24}}><input type="checkbox" checked={autoRev} onChange={e=>setAutoRev(e.target.checked)}/>{ar?'عكس تلقائي':'Auto reverse'}</label>
        {autoRev&&<label>{ar?'تاريخ العكس':'Reversal date'}<input type="date" style={field} value={revDate} onChange={e=>setRevDate(e.target.value)}/></label>}
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'تسجيل الاستحقاق':'Record accrual'}</button></div>
    </Panel>

    <Panel title={ar?'تشغيل عكس الاستحقاقات':'Run accrual reversals'} icon={<Play size={18}/>}>
      <div style={{...grid,alignItems:'end'}}>
        <label>{ar?'حتى تاريخ':'As of date'}<input type="date" style={field} value={runDate} onChange={e=>setRunDate(e.target.value)}/></label>
        <button style={{...ghost,opacity:busy?0.6:1}} disabled={busy} onClick={runRev}>{ar?'عكس':'Run reversals'}</button>
      </div>
    </Panel>

    <Panel title={ar?'الاستحقاقات':'Accruals'} icon={<ClipboardCheck size={18}/>}>
      <DataTable headers={[ar?'الاسم':'Name',ar?'التاريخ':'Date',ar?'المبلغ':'Amount',ar?'مدين':'Debit',ar?'دائن':'Credit',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={rows.map((a:any)=>[ar?a.name_ar:a.name_en,a.accrual_date,fmt(Number(a.amount||0)),a.debit_account_code,a.credit_account_code,a.status,
          a.status==='DRAFT'?<button key={a.id} style={{...btn,padding:'4px 10px',fontSize:12}} disabled={busy} onClick={()=>post(a.id)}>{ar?'ترحيل':'Post'}</button>:'—'])}/>
    </Panel>
  </>;
}
