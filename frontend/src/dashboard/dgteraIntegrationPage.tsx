import {useEffect, useMemo, useState} from 'react';
import {Bike, Clock3, DatabaseZap, Link2, PackageSearch, Receipt, RefreshCw, Store, Users} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

type Status={
  configured:boolean;connected?:boolean;base_url?:string;active?:boolean;
  company_id?:number;connection_company_id?:number;inherited?:boolean;
  last_tested_at?:string|null;last_sync_at?:string|null;last_error?:string|null;
  timezone?:string;day_window?:string;sync_interval_minutes?:number;history?:HistoryStatus;
};
type HistoryStatus={start_date:string;target_end_date:string;earliest_imported_date?:string|null;covered_days:number;total_days:number;progress_percent:number;completed:boolean};
type Coverage={complete:boolean;requested_start_date:string;requested_end_date:string;earliest_imported_date?:string|null;target_end_date:string;progress_percent:number};
type SummaryRow={key:string;orders:number;quantity?:number;subtotal:number;vat:number;sales:number};
type ProductRow={key:string;code:string;quantity:number;subtotal:number;vat:number;sales:number};
type OrderLine={product:string;code:string;quantity:number;unit_price:number;discount_percent:number;subtotal:number;vat:number;total:number};
type Payment={method:string;amount:number};
type Order={
  id:number;external_order_id:string;order_name:string;pos_reference?:string|null;ordered_at:string;
  sales_date:string;branch:string;customer?:string|null;sales_scope:string;service_mode:string;
  classification_source:string;platform?:string|null;state:string;subtotal:number;vat:number;total:number;
  amount_paid:number;amount_return:number;discount:number;line_total_difference:number;
  lines:OrderLine[];payments:Payment[];
};
type Snapshot={
  mode:string;window:any;trusted_sales:boolean;totals:any|null;master_counts:any;branches:any[];
  branch_sales:SummaryRow[];scope_sales:SummaryRow[];service_sales:SummaryRow[];
  platform_sales:SummaryRow[];payment_channels:SummaryRow[];customer_sales:SummaryRow[];product_sales:ProductRow[];orders:Order[];
  coverage:Coverage;
  reconciliation:{
    available:boolean;strict:boolean;matched:boolean;source_orders:number;imported_orders:number;
    source_lines:number;imported_lines:number;source_payments:number;imported_payments:number;
    source_quantity:number;imported_quantity:number;source_subtotal:number;imported_subtotal:number;
    source_vat:number;imported_vat:number;source_total:number;imported_total:number;difference:number;
    checks:Record<string,boolean>;mismatch_count:number;mismatches:Array<{category:string;path:string;expected:string;actual:string}>;
    verification_hash?:string|null;oldest_verified_at?:string|null;last_verified_at?:string|null;days_verified:number;orders_verified_individually:boolean;
  };
};
type SyncRun={id:number;start_date:string;end_date:string;window:string;status:string;source_orders:number;inserted:number;updated:number;unchanged:number;source_total:number;error?:string|null;completed_at?:string|null};
type Period='DAY'|'WEEK'|'MONTH'|'YEAR';
type Metrics={orders:number;quantity:number;subtotal:number;vat:number;sales:number;refunds:number};
type Analytics={
  period:Period;as_of_date:string;windows:Record<'current'|'previous'|'next'|'prior_year',{start_date:string;end_date:string}>;
  metrics:Record<'current'|'previous'|'next'|'prior_year',Metrics|null>;
  coverage:Record<'current'|'previous'|'next'|'prior_year',Coverage>;
  comparison:{previous_change_percent:number|null;next_change_percent:number|null;prior_year_change_percent:number|null};
  branch_comparison:Array<{branch_id:number;branch:string;orders:number;quantity:number;subtotal:number;vat:number;sales:number;previous_sales:number;previous_change_percent:number|null;next_sales:number;next_change_percent:number|null;prior_year_sales:number;prior_year_change_percent:number|null}>;
  trend:Array<{key:string;orders:number;sales:number}>;history:HistoryStatus;
};
type DisplayFilters={startDate:string;endDate:string;branchId:string;scope:string;service:string};

const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9,background:'var(--surface)',color:'var(--text)'} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(210px,1fr))',gap:12,padding:12} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const money2=(value:number,ar=false)=>new Intl.NumberFormat(ar?'ar-SA':'en-US',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value||0));
const pct=(value:number|null|undefined,ar=false)=>value==null?'—':`${new Intl.NumberFormat(ar?'ar-SA':'en-US',{minimumFractionDigits:1,maximumFractionDigits:1,signDisplay:'exceptZero'}).format(Number(value))}%`;
const localDateTime=(value?:string|null,ar=false)=>{
  if(!value)return ar?'لم تبدأ بعد':'Not started';
  const normalized=/Z$|[+-]\d\d:\d\d$/.test(value)?value:`${value}Z`;
  const parsed=new Date(normalized);if(Number.isNaN(parsed.getTime()))return String(value).replace('T',' ').slice(0,19);
  return new Intl.DateTimeFormat(ar?'ar-SA':'en-GB',{timeZone:'Asia/Riyadh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(parsed);
};

function riyadhToday(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Riyadh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const get=(type:string)=>parts.find(x=>x.type===type)?.value||'';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

const REQUEST_TIMEOUT_MS=30000;
async function json(url:string,init?:RequestInit){
  const controller=new AbortController();
  const timer=window.setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
  try{
    const r=await apiFetch(url,{...(init||{}),signal:controller.signal});
    const x=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
    return x;
  }catch(error:any){
    if(controller.signal.aborted)throw new Error(`DGTERA API request timed out after ${REQUEST_TIMEOUT_MS/1000} seconds`);
    throw error;
  }finally{window.clearTimeout(timer)}
}

const scopeLabel=(value:string,ar:boolean)=>value==='INTERNAL'?(ar?'مبيعات داخلية':'Internal sales'):(ar?'مبيعات خارجية':'External sales');
const serviceLabel=(value:string,ar:boolean)=>({
  DINE_IN:ar?'داخل المطعم':'Dine-in',
  TAKEAWAY:ar?'سفري / استلام':'Takeaway',
  DELIVERY:ar?'تطبيقات التوصيل':'Delivery apps',
}[value]||value);
const paymentLabel=(value:string,ar:boolean)=>({
  CASH:ar?'نقدي':'Cash',
  CARD:ar?'بطاقات / شبكة':'Card / POS',
  PLATFORM_CREDIT:ar?'آجل — ذمم تطبيقات التوصيل':'On account — delivery apps',
  OTHER:ar?'طريقة دفع أخرى':'Other payment method',
  UNCLASSIFIED:ar?'غير مصنف في DGTERA':'Unclassified in DGTERA',
}[value]||value);
const syncLabel=(value:string,ar:boolean)=>({
  COMPLETED:ar?'مكتملة':'Completed',
  ERROR:ar?'خطأ':'Error',
  RUNNING:ar?'جارية':'Running',
}[value]||value);

export function DgteraIntegrationPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=useMemo(riyadhToday,[]);
  const [status,setStatus]=useState<Status>({configured:false});
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [analytics,setAnalytics]=useState<Analytics|null>(null);
  const [runs,setRuns]=useState<SyncRun[]>([]);
  const [baseUrl,setBaseUrl]=useState('https://cheesehouse.dgtera.com');
  const [database,setDatabase]=useState('cheesehouse');
  const [login,setLogin]=useState('');const [apiKey,setApiKey]=useState('');
  const [startDate,setStartDate]=useState(today);const [endDate,setEndDate]=useState(today);
  const [compareDate,setCompareDate]=useState(today);const [period,setPeriod]=useState<Period>('DAY');
  const [branchId,setBranchId]=useState('');const [scope,setScope]=useState('');const [service,setService]=useState('');
  const [appliedFilters,setAppliedFilters]=useState<DisplayFilters>({startDate:today,endDate:today,branchId:'',scope:'',service:''});
  const [selectedOrder,setSelectedOrder]=useState<Order|null>(null);
  const [busy,setBusy]=useState(false);const [reportLoading,setReportLoading]=useState(false);const [msg,setMsg]=useState('');const [isError,setIsError]=useState(false);

  const load=async()=>{
    setReportLoading(true);
    try{
      const st=await json(`/api/v1/integrations/dgtera/status?company_id=${companyId}`);
      setStatus(st);if(st.base_url)setBaseUrl(st.base_url);
      if(!st.configured){setSnapshot(null);setAnalytics(null);setRuns([]);return;}
      const params=new URLSearchParams({company_id:String(companyId),start_date:appliedFilters.startDate,end_date:appliedFilters.endDate});
      if(appliedFilters.branchId)params.set('branch_id',appliedFilters.branchId);if(appliedFilters.scope)params.set('sales_scope',appliedFilters.scope);if(appliedFilters.service)params.set('service_mode',appliedFilters.service);
      const analyticsParams=new URLSearchParams({company_id:String(companyId),as_of_date:compareDate,period});
      if(appliedFilters.branchId)analyticsParams.set('branch_id',appliedFilters.branchId);if(appliedFilters.scope)analyticsParams.set('sales_scope',appliedFilters.scope);if(appliedFilters.service)analyticsParams.set('service_mode',appliedFilters.service);
      const [snapResult,comparisonResult,historyResult]=await Promise.allSettled([
        json(`/api/v1/integrations/dgtera/snapshot?${params.toString()}`),
        json(`/api/v1/integrations/dgtera/analytics?${analyticsParams.toString()}`),
        json(`/api/v1/integrations/dgtera/sync-runs?company_id=${companyId}&limit=30`),
      ]);
      if(historyResult.status==='fulfilled')setRuns(historyResult.value);else setRuns([]);
      if(snapResult.status==='fulfilled'){
        const snap=snapResult.value;
        setSnapshot(snap);
        setSelectedOrder(current=>current?snap.orders.find((x:Order)=>x.id===current.id)||null:null);
      }else{setSnapshot(null);setSelectedOrder(null)}
      if(comparisonResult.status==='fulfilled')setAnalytics(comparisonResult.value);else setAnalytics(null);
      const failures=[snapResult,comparisonResult,historyResult].filter(result=>result.status==='rejected') as PromiseRejectedResult[];
      if(failures.length)throw failures[0].reason;
    }finally{setReportLoading(false)}
  };

  const rejectStale=(e:any)=>{setSnapshot(null);setAnalytics(null);setMsg(String(e.message||e));setIsError(true)};
  useEffect(()=>{load().catch(rejectStale)},[companyId,appliedFilters,compareDate,period]);
  useEffect(()=>{
    const timer=window.setInterval(()=>load().catch(rejectStale),120000);
    return()=>window.clearInterval(timer);
  },[companyId,appliedFilters,compareDate,period]);

  const say=(text:string,error=false)=>{setMsg(text);setIsError(error)};
  const showSales=()=>{
    if(!startDate||!endDate){say(ar?'اختر تاريخ البداية والنهاية أولًا.':'Select both start and end dates first.',true);return;}
    if(endDate<startDate){say(ar?'تاريخ النهاية لا يمكن أن يسبق تاريخ البداية.':'End date cannot be before start date.',true);return;}
    setMsg('');setIsError(false);
    setAppliedFilters({startDate,endDate,branchId,scope,service});
  };
  const saveConnection=async()=>{
    if(status.inherited){
      say(ar?'هذا ربط مشترك بين القابضة والمطاعم، ويُدار من الشركة المالكة له حتى لا تتكرر المبيعات.':'This is a shared holding/restaurant connection and is managed by its owning company to prevent duplicate sales.',true);return;
    }
    if(!baseUrl||(!status.configured&&(!database||!login||!apiKey))){
      say(ar?'أكمل رابط DGTERA واسم قاعدة Odoo والمستخدم ومفتاح API.':'Complete the DGTERA URL, database, login and API key.',true);return;
    }
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,name:'DGTERA',base_url:baseUrl,active:true,timezone:'Asia/Riyadh'};
      if(database)body.database_name=database;if(login)body.login=login;if(apiKey)body.api_key=apiKey;
      const result=await json('/api/v1/integrations/dgtera/connection',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setApiKey('');
      const imported=result.initial_sync?.inserted||0,updated=result.initial_sync?.updated||0;
      say(ar?`تم التحقق والربط والمطابقة: أضيف ${imported} طلب وحُدّث ${updated}. ستتجدد البيانات كل دقيقتين.`:`Connected, synchronized and reconciled: ${imported} inserted, ${updated} updated. Refresh runs every 2 minutes.`);
      await load();
    }catch(e:any){say(String(e.message||e),true)}finally{setBusy(false)}
  };

  const totals=snapshot?.totals||{};
  const counts=snapshot?.master_counts||{};
  const reportComplete=snapshot?.coverage?.complete===true&&snapshot?.reconciliation?.matched===true;
  const currentMetrics=analytics?.metrics.current;
  const previousMetrics=analytics?.metrics.previous;
  const nextMetrics=analytics?.metrics.next;
  const priorYearMetrics=analytics?.metrics.prior_year;
  const periodComplete=(key:'current'|'previous'|'next'|'prior_year')=>analytics?.coverage?.[key]?.complete===true;
  const metricNet=(key:'current'|'previous'|'next'|'prior_year',metrics:Metrics|null|undefined)=>periodComplete(key)?Number(metrics?.subtotal||0):0;
  const metricMoney=(key:'current'|'previous'|'next'|'prior_year',value:number|undefined)=>periodComplete(key)?money2(Number(value||0),ar):'—';
  const metricCount=(key:'current'|'previous'|'next'|'prior_year',value:number|undefined)=>periodComplete(key)?String(value||0):'—';
  const comparisonMax=Math.max(1,metricNet('current',currentMetrics),metricNet('previous',previousMetrics),metricNet('next',nextMetrics),metricNet('prior_year',priorYearMetrics));
  const periodLabel=(value:Period)=>({DAY:ar?'يومي':'Daily',WEEK:ar?'أسبوعي':'Weekly',MONTH:ar?'شهري':'Monthly',YEAR:ar?'سنوي':'Yearly'}[value]);
  const windowText=(key:'current'|'previous'|'next'|'prior_year')=>{
    const w=analytics?.windows[key];if(!w)return '—';return w.start_date===w.end_date?w.start_date:`${w.start_date} → ${w.end_date}`;
  };
  return <>
    <div className="kpis">
      <Kpi title={ar?'صافي المبيعات':'Net sales'} value={reportComplete?money2(Number(totals.subtotal||0),ar):'—'} trend={ar?'دون الضريبة — الرقم الأساسي للتقارير':'Excluding VAT — primary report value'} good icon={<Receipt size={22}/>} tone="blue"/>
      <Kpi title={ar?'ضريبة المبيعات':'Sales VAT'} value={reportComplete?money2(Number(totals.vat||0),ar):'—'} trend={ar?'كما وردت من DGTERA':'As received from DGTERA'} good icon={<Store size={22}/>} tone="violet"/>
      <Kpi title={ar?'إجمالي المبيعات':'Gross sales'} value={reportComplete?money2(Number(totals.sales||0),ar):'—'} trend={ar?'شامل الضريبة':'Including VAT'} good icon={<Bike size={22}/>} tone="amber"/>
      <Kpi title={ar?'عدد الطلبات':'Orders'} value={reportComplete?String(totals.orders||0):'—'} trend="00:00–23:59:59" good icon={<DatabaseZap size={22}/>} tone="green"/>
    </div>

    {msg&&<div style={{padding:11,margin:'12px 0',borderRadius:9,lineHeight:1.8,background:isError?'#fee2e2':'#dcfce7',color:isError?'#991b1b':'#166534'}}>{msg}</div>}

    <Panel title={ar?'اتصال DGTERA الآلي':'Automatic DGTERA connection'} icon={<Link2 size={18}/>}>
      <div style={{padding:'10px 12px 0',fontSize:13,lineHeight:1.9,opacity:.9}}>
        {status.inherited
          ? (ar
            ? 'هذا هو ربط DGTERA المشترك بين الشركة القابضة وشركة المطاعم. تظهر المبيعات في الشركتين من السجل نفسه دون نسخ الطلبات أو مضاعفة الإجماليات.'
            : 'This DGTERA connection is shared by the holding and restaurant companies. Both workspaces read the same records without copying orders or doubling totals.')
          : (ar
            ? 'يحفظ CORVAX بيانات الاتصال مشفرة ويطابق اليوم مع تاريخ تقرير مبيعات الفروع في DGTERA كما هو، دون إزاحة زمنية. يبدأ من اليوم ثم يستكمل التاريخ تلقائيًا حتى 1 يناير 2025.'
            : 'CORVAX encrypts the connection and matches the DGTERA Branch Sales source-report date without a time-zone shift. It imports today first, then automatically backfills sales to 1 January 2025.')}
      </div>
      {!status.inherited&&<div style={grid}>
        <label>{ar?'رابط DGTERA':'DGTERA URL'}<input style={field} value={baseUrl} onChange={e=>setBaseUrl(e.target.value)}/></label>
        <label>{ar?'اسم قاعدة Odoo':'Odoo database'}<input style={field} value={database} onChange={e=>setDatabase(e.target.value)} placeholder={status.configured?(ar?'اتركه كما هو إن لم يتغير':'Leave unchanged'):''}/></label>
        <label>{ar?'مستخدم API للقراءة':'Read-only API login'}<input style={field} value={login} onChange={e=>setLogin(e.target.value)} autoComplete="off" placeholder={status.configured?(ar?'اتركه فارغًا للحفاظ عليه':'Leave blank to keep'):''}/></label>
        <label>{ar?'مفتاح API':'API key'}<input type="password" style={field} value={apiKey} onChange={e=>setApiKey(e.target.value)} autoComplete="new-password" placeholder={status.configured?'••••••••••••':''}/></label>
      </div>}
      <div style={{display:'flex',gap:12,padding:'0 12px 14px',alignItems:'center',flexWrap:'wrap'}}>
        {!status.inherited&&<button style={{...btn,opacity:busy?.6:1}} disabled={busy} onClick={saveConnection}>{ar?'حفظ وتفعيل الربط الآلي':'Save & activate automatic sync'}</button>}
        <span style={{fontSize:13,lineHeight:1.8}}>
          <Clock3 size={16}/> {ar?'يوم المبيعات: 00:00 إلى 23:59:59 حسب تاريخ تقرير DGTERA — تحديث ومطابقة تلقائية كل دقيقتين.':'Sales day: 00:00–23:59:59 by DGTERA source-report date — automatic refresh and reconciliation every 2 minutes.'}
        </span>
      </div>
      {status.configured&&<div style={{padding:'0 12px 14px',fontSize:13,lineHeight:1.8}}>
        {ar?'الحالة':'Status'}: <b>{status.connected?(ar?'متصل ويعمل تلقائيًا':'Connected and automatic'):(ar?'الاتصال يحتاج فحصًا':'Connection needs attention')}</b>
        {status.inherited&&<b style={{color:'#166534'}}> — {ar?'مشترك بين القابضة والمطاعم':'Shared by holding and restaurant'}</b>}
        {' — '}{ar?'آخر مزامنة بتوقيت الرياض':'Last sync (Riyadh)'}: {localDateTime(status.last_sync_at,ar)}
        {status.last_error&&<span style={{color:'#b91c1c'}}> — {status.last_error}</span>}
        {status.history&&<div style={{marginTop:10}}>
          <div style={{display:'flex',justifyContent:'space-between',gap:12,flexWrap:'wrap'}}>
            <b>{status.history.completed?(ar?'اكتمل تاريخ المبيعات من 2025':'Sales history from 2025 is complete'):(ar?'جارٍ استيراد تاريخ 2025 تلقائيًا':'Automatically importing 2025 history')}</b>
            <span>{money2(status.history.progress_percent,ar)}%</span>
          </div>
          <div style={{height:9,borderRadius:99,background:'#e5e7eb',overflow:'hidden',marginTop:6}}><div style={{height:'100%',width:`${Math.min(100,status.history.progress_percent)}%`,background:'#16a34a'}}/></div>
          <small>{ar?'أقدم تاريخ تم استيراده':'Earliest imported date'}: {status.history.earliest_imported_date||'—'} — {ar?'الهدف':'Target'}: {status.history.start_date}</small>
        </div>}
      </div>}
    </Panel>

    {status.configured&&<>
      {snapshot&&!reportComplete&&<div style={{padding:12,margin:'12px 0',borderRadius:10,background:snapshot.reconciliation?.mismatch_count?'#fee2e2':'#fef3c7',color:snapshot.reconciliation?.mismatch_count?'#991b1b':'#92400e',fontSize:13,lineHeight:1.9}}>
        <b>{snapshot.reconciliation?.mismatch_count?(ar?'⛔ فشلت المطابقة الصارمة':'⛔ Strict reconciliation failed'):(ar?'⏳ جارٍ استكمال الفترة من DGTERA':'⏳ Completing the selected period from DGTERA')}</b>
        {' — '}{ar?'تم إخفاء الإجماليات حتى تكتمل كل الأيام وتنجح مطابقة الطلبات والسطور والمدفوعات والصافي والضريبة والإجمالي دون أي فرق.':'Totals are hidden until every day is covered and orders, lines, payments, net, VAT and gross all reconcile with no difference.'}
        {snapshot.reconciliation?.mismatch_count?` ${ar?'عدد الفروقات':'Differences'}: ${snapshot.reconciliation.mismatch_count}`:` ${money2(Number(snapshot.coverage.progress_percent||0),ar)}%`}
        {!!snapshot.reconciliation?.mismatches?.length&&<div style={{marginTop:6}}>{snapshot.reconciliation.mismatches.slice(0,3).map((item,index)=><div key={`${item.path}-${index}`}><code>{item.path}</code>: {item.expected} ≠ {item.actual}</div>)}</div>}
      </div>}
      {reportComplete&&snapshot?.reconciliation?.available&&<div style={{padding:12,margin:'12px 0',borderRadius:10,background:snapshot.reconciliation.matched?'#dcfce7':'#fee2e2',color:snapshot.reconciliation.matched?'#166534':'#991b1b',fontSize:13,lineHeight:1.9}}>
        <b>{snapshot.reconciliation.matched?(ar?'✓ مطابقة صارمة 100% للفترة المستوردة':'✓ Strict 100% reconciliation for the imported period'):(ar?'⚠ يوجد فرق يحتاج مراجعة':'⚠ Reconciliation difference')}</b>
        {' — '}{ar?'الصافي':'Net'}: {money2(Number(snapshot.reconciliation.source_subtotal||0),ar)}
        {' — '}{ar?'الضريبة':'VAT'}: {money2(Number(snapshot.reconciliation.source_vat||0),ar)}
        {' — '}{ar?'الإجمالي':'Gross'}: {money2(Number(snapshot.reconciliation.source_total||0),ar)}
        {' — '}{ar?'الفرق':'Difference'}: {money2(Number(snapshot.reconciliation.difference||0),ar)}
        {' — '}{ar?'الطلبات':'Orders'}: {snapshot.reconciliation.imported_orders}/{snapshot.reconciliation.source_orders}
        {' — '}{ar?'السطور':'Lines'}: {snapshot.reconciliation.imported_lines}/{snapshot.reconciliation.source_lines}
        {' — '}{ar?'المدفوعات':'Payments'}: {snapshot.reconciliation.imported_payments}/{snapshot.reconciliation.source_payments}
        {' — '}{ar?'الكمية':'Quantity'}: {money2(Number(snapshot.reconciliation.imported_quantity||0),ar)}/{money2(Number(snapshot.reconciliation.source_quantity||0),ar)}
        <div><small>{ar?'آخر تحقق مباشر من المصدر':'Last live-source verification'}: {localDateTime(snapshot.reconciliation.last_verified_at,ar)} — {ar?'تم فحص كل طلب بصورة منفردة':'Every order was checked individually'} — SHA-256: {snapshot.reconciliation.verification_hash?.slice(0,16)}…</small></div>
      </div>}
      <Panel title={ar?'فترة عرض المبيعات':'Sales display period'} icon={<Clock3 size={18}/>}>
        <div style={grid}>
          <label>{ar?'من':'From'}<input type="date" min="2025-01-01" style={field} value={startDate} onChange={e=>setStartDate(e.target.value)}/></label>
          <label>{ar?'إلى':'To'}<input type="date" min="2025-01-01" style={field} value={endDate} onChange={e=>setEndDate(e.target.value)}/></label>
          <label>{ar?'الفرع':'Branch'}<select style={field} value={branchId} onChange={e=>setBranchId(e.target.value)}><option value="">{ar?'كل الفروع':'All branches'}</option>{(snapshot?.branches||[]).map(x=><option key={x.branch_id} value={x.branch_id}>{x.name}</option>)}</select></label>
          <label>{ar?'داخلي / خارجي':'Internal / external'}<select style={field} value={scope} onChange={e=>setScope(e.target.value)}><option value="">{ar?'الكل':'All'}</option><option value="INTERNAL">{ar?'داخلي':'Internal'}</option><option value="EXTERNAL">{ar?'خارجي':'External'}</option></select></label>
          <label>{ar?'نوع الخدمة':'Service mode'}<select style={field} value={service} onChange={e=>setService(e.target.value)}><option value="">{ar?'الكل':'All'}</option><option value="DINE_IN">{ar?'داخل المطعم':'Dine-in'}</option><option value="TAKEAWAY">{ar?'سفري / استلام':'Takeaway'}</option><option value="DELIVERY">{ar?'توصيل':'Delivery'}</option></select></label>
          <div style={{display:'flex',alignItems:'end'}}><button type="button" style={{...btn,width:'100%',opacity:reportLoading?.65:1}} disabled={reportLoading} onClick={showSales}>{reportLoading?(ar?'جارٍ عرض المبيعات…':'Loading sales…'):(ar?'عرض المبيعات':'Show sales')}</button></div>
        </div>
        <div style={{padding:'0 12px 12px',fontSize:13,opacity:.8}}>{ar?'الفترة المعروضة حاليًا':'Currently displayed period'}: <b>{appliedFilters.startDate} → {appliedFilters.endDate}</b></div>
      </Panel>

      <Panel title={ar?'مقارنة المبيعات اليومية والأسبوعية والشهرية والسنوية':'Daily, weekly, monthly and yearly sales comparison'} icon={<Receipt size={18}/> }>
        <div style={{...grid,alignItems:'end'}}>
          <label>{ar?'تاريخ المقارنة':'Comparison date'}<input type="date" min="2025-01-01" style={field} value={compareDate} onChange={e=>setCompareDate(e.target.value)}/></label>
          <label>{ar?'نوع الفترة':'Period'}<select style={field} value={period} onChange={e=>setPeriod(e.target.value as Period)}>
            <option value="DAY">{ar?'يومي':'Daily'}</option><option value="WEEK">{ar?'أسبوعي حتى التاريخ':'Week to date'}</option><option value="MONTH">{ar?'شهري حتى التاريخ':'Month to date'}</option><option value="YEAR">{ar?'سنوي حتى التاريخ':'Year to date'}</option>
          </select></label>
        </div>
        {analytics&&<>
          <div className="kpis" style={{padding:'0 12px 12px'}}>
            <Kpi title={`${periodLabel(period)} — ${ar?'صافي الحالي':'Current net'}`} value={periodComplete('current')?money2(Number(currentMetrics?.subtotal||0),ar):'—'} trend={periodComplete('current')?windowText('current'):(ar?'جارٍ استكمال الفترة':'Importing period')} good icon={<Receipt size={22}/>} tone="blue"/>
            <Kpi title={ar?'صافي الفترة السابقة':'Previous period net'} value={periodComplete('previous')?money2(Number(previousMetrics?.subtotal||0),ar):'—'} trend={periodComplete('previous')?`${windowText('previous')} • ${pct(analytics.comparison.previous_change_percent,ar)}`:(ar?'جارٍ استكمال الفترة':'Importing period')} good={(analytics.comparison.previous_change_percent||0)>=0} icon={<Clock3 size={22}/>} tone="violet"/>
            <Kpi title={ar?'صافي الفترة اللاحقة':'Next period net'} value={periodComplete('next')?money2(Number(nextMetrics?.subtotal||0),ar):'—'} trend={periodComplete('next')?`${windowText('next')} • ${pct(analytics.comparison.next_change_percent,ar)}`:(ar?'جارٍ استكمال الفترة':'Importing period')} good={(analytics.comparison.next_change_percent||0)>=0} icon={<Clock3 size={22}/>} tone="green"/>
            <Kpi title={ar?'نفس الفترة من 2025':'Same period in 2025'} value={periodComplete('prior_year')?money2(Number(priorYearMetrics?.subtotal||0),ar):'—'} trend={periodComplete('prior_year')?`${windowText('prior_year')} • ${pct(analytics.comparison.prior_year_change_percent,ar)}`:(ar?'جارٍ استكمال تاريخ 2025':'Importing 2025 history')} good={(analytics.comparison.prior_year_change_percent||0)>=0} icon={<Clock3 size={22}/>} tone="amber"/>
          </div>
          <div style={{padding:'2px 14px 16px',display:'grid',gap:10}}>
            {[
              {label:ar?'صافي الحالي':'Current net',value:metricNet('current',currentMetrics),complete:periodComplete('current'),color:'#2563eb'},
              {label:ar?'صافي الفترة السابقة':'Previous net',value:metricNet('previous',previousMetrics),complete:periodComplete('previous'),color:'#7c3aed'},
              {label:ar?'صافي الفترة اللاحقة':'Next net',value:metricNet('next',nextMetrics),complete:periodComplete('next'),color:'#16a34a'},
              {label:ar?'صافي 2025':'2025 net',value:metricNet('prior_year',priorYearMetrics),complete:periodComplete('prior_year'),color:'#d97706'},
            ].map(item=><div key={item.label} style={{display:'grid',gridTemplateColumns:'minmax(90px,150px) 1fr minmax(100px,150px)',gap:10,alignItems:'center',fontSize:13}}>
              <span>{item.label}</span><div style={{height:18,borderRadius:5,background:'#e5e7eb',overflow:'hidden'}}><div style={{height:'100%',width:`${Math.max(item.value?2:0,item.value/comparisonMax*100)}%`,background:item.color}}/></div><b>{item.complete?money2(item.value,ar):'—'}</b>
            </div>)}
          </div>
          <DataTable headers={[ar?'المقياس':'Metric',ar?'الحالي':'Current',ar?'الفترة السابقة':'Previous',ar?'الفترة اللاحقة':'Next',ar?'2025':'2025']} rows={[
            [ar?'صافي المبيعات دون الضريبة':'Net sales excl. VAT',metricMoney('current',currentMetrics?.subtotal),metricMoney('previous',previousMetrics?.subtotal),metricMoney('next',nextMetrics?.subtotal),metricMoney('prior_year',priorYearMetrics?.subtotal)],
            [ar?'الضريبة':'VAT',metricMoney('current',currentMetrics?.vat),metricMoney('previous',previousMetrics?.vat),metricMoney('next',nextMetrics?.vat),metricMoney('prior_year',priorYearMetrics?.vat)],
            [ar?'الإجمالي شامل الضريبة':'Gross incl. VAT',metricMoney('current',currentMetrics?.sales),metricMoney('previous',previousMetrics?.sales),metricMoney('next',nextMetrics?.sales),metricMoney('prior_year',priorYearMetrics?.sales)],
            [ar?'عدد الطلبات':'Orders',metricCount('current',currentMetrics?.orders),metricCount('previous',previousMetrics?.orders),metricCount('next',nextMetrics?.orders),metricCount('prior_year',priorYearMetrics?.orders)],
            [ar?'الكمية':'Quantity',metricMoney('current',currentMetrics?.quantity),metricMoney('previous',previousMetrics?.quantity),metricMoney('next',nextMetrics?.quantity),metricMoney('prior_year',priorYearMetrics?.quantity)],
          ]}/>
        </>}
      </Panel>

      <div className="kpis">
        <Kpi title={ar?'الفروع':'Branches'} value={String(counts.branches||0)} trend={ar?'أُنشئت من DGTERA':'From DGTERA'} good icon={<Store size={22}/>} tone="blue"/>
        <Kpi title={ar?'الأصناف':'Products'} value={String(counts.products||0)} trend={ar?'أكواد وأسعار المصدر':'Source codes & prices'} good icon={<PackageSearch size={22}/>} tone="violet"/>
        <Kpi title={ar?'العملاء':'Customers'} value={String(counts.customers||0)} trend={ar?'بما فيها شركات التوصيل':'Including delivery companies'} good icon={<Users size={22}/>} tone="green"/>
        <Kpi title={ar?'ضريبة المبيعات':'Sales VAT'} value={reportComplete?money2(Number(totals.vat||0),ar):'—'} trend={ar?'كما وردت من DGTERA':'As received from DGTERA'} good icon={<Receipt size={22}/>} tone="amber"/>
      </div>

      {analytics&&periodComplete('current')&&<Panel title={ar?`مقارنة صافي الفروع — ${periodLabel(period)}`:`Branch net comparison — ${periodLabel(period)}`} icon={<Store size={18}/> }>
        <DataTable headers={[ar?'الفرع':'Branch',ar?'الكمية':'Qty',ar?'صافي الحالي':'Current net',ar?'الضريبة':'VAT',ar?'السابق':'Previous',ar?'التغير':'Change',ar?'اللاحق':'Next',ar?'2025':'2025',ar?'التغير السنوي':'YoY change']} rows={analytics.branch_comparison.map(x=>[
          x.branch,money2(Number(x.quantity||0),ar),money2(Number(x.subtotal||0),ar),money2(Number(x.vat||0),ar),money2(Number(x.previous_sales||0),ar),pct(x.previous_change_percent,ar),money2(Number(x.next_sales||0),ar),money2(Number(x.prior_year_sales||0),ar),pct(x.prior_year_change_percent,ar),
        ])}/>
      </Panel>}

      <Panel title={ar?'المبيعات حسب الفرع':'Sales by branch'} icon={<Store size={18}/>}>
        <DataTable headers={[ar?'الفرع':'Branch',ar?'الطلبات':'Orders',ar?'الكمية':'Qty',ar?'المبيعات دون الضريبة':'Sales excl. VAT',ar?'الضريبة':'VAT',ar?'إجمالي المبيعات':'Total sales']} rows={(reportComplete?snapshot?.branch_sales||[]:[]).map(x=>[x.key,String(x.orders),money2(Number(x.quantity||0),ar),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.sales),ar)])}/>
      </Panel>

      <Panel title={ar?'تفصيل الداخلي والخارجي ونوع الخدمة':'Internal, external and service detail'} icon={<DatabaseZap size={18}/>}>
        <DataTable headers={[ar?'التصنيف':'Classification',ar?'الطلبات':'Orders',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={[
          ...(reportComplete?snapshot?.scope_sales||[]:[]).map(x=>[scopeLabel(x.key,ar),String(x.orders),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.sales),ar)]),
          ...(reportComplete?snapshot?.service_sales||[]:[]).map(x=>[serviceLabel(x.key,ar),String(x.orders),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.sales),ar)]),
        ]}/>
      </Panel>

      <Panel title={ar?'تصنيف التحصيل: نقدي وبطاقات وآجل التطبيقات':'Collection classification: cash, card and app receivables'} icon={<DatabaseZap size={18}/> }>
        <DataTable headers={[ar?'التصنيف':'Classification',ar?'الطلبات':'Orders',ar?'صافي المبيعات':'Net sales',ar?'الضريبة':'VAT',ar?'الإجمالي شامل الضريبة':'Gross incl. VAT']} rows={(reportComplete?snapshot?.payment_channels||[]:[]).map(x=>[
          paymentLabel(x.key,ar),String(x.orders),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.sales),ar),
        ])}/>
      </Panel>

      <Panel title={ar?'شركات ومنصات التوصيل':'Delivery companies and platforms'} icon={<Bike size={18}/>}> 
        <DataTable headers={[ar?'المنصة / العميل':'Platform / customer',ar?'الطلبات':'Orders',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={(reportComplete?snapshot?.platform_sales||[]:[]).map(x=>[x.key,String(x.orders),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.sales),ar)])}/>
      </Panel>

      <Panel title={ar?'العملاء':'Customers'} icon={<Users size={18}/>}>
        <DataTable headers={[ar?'العميل':'Customer',ar?'الطلبات':'Orders',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={(reportComplete?snapshot?.customer_sales||[]:[]).map(x=>[x.key,String(x.orders),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.sales),ar)])}/>
      </Panel>

      <Panel title={ar?'مبيعات الأصناف':'Product sales'} icon={<PackageSearch size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الصنف':'Product',ar?'الكمية':'Qty',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={(reportComplete?snapshot?.product_sales||[]:[]).map(x=>[x.code,x.key,money2(Number(x.quantity||0),ar),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.sales),ar)])}/>
      </Panel>

      <Panel title={ar?'طلبات DGTERA':'DGTERA orders'} icon={<Receipt size={18}/>}>
        <DataTable headers={[ar?'الطلب':'Order',ar?'الوقت':'Time',ar?'الفرع':'Branch',ar?'النوع':'Type',ar?'العميل / المنصة':'Customer / platform',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'الإجمالي':'Total',ar?'':'']} rows={(reportComplete?snapshot?.orders||[]:[]).map(x=>[
          x.pos_reference||x.order_name,String(x.ordered_at).replace('T',' ').slice(0,16),x.branch,
          `${scopeLabel(x.sales_scope,ar)} — ${serviceLabel(x.service_mode,ar)}`,
          x.platform||x.customer||(ar?'عميل نقدي':'Walk-in'),
          money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.total),ar),
          <button key={x.id} style={{...btn,padding:'6px 10px'}} onClick={()=>setSelectedOrder(x)}>{ar?'التفاصيل':'Details'}</button>,
        ])}/>
      </Panel>

      {selectedOrder&&<Panel title={ar?`تفاصيل الطلب ${selectedOrder.pos_reference||selectedOrder.order_name}`:`Order details ${selectedOrder.pos_reference||selectedOrder.order_name}`} icon={<Receipt size={18}/>}>
        <div style={{padding:12,fontSize:13,lineHeight:1.9}}>
          {ar?'الفرع':'Branch'}: <b>{selectedOrder.branch}</b> — {ar?'العميل':'Customer'}: <b>{selectedOrder.platform||selectedOrder.customer||(ar?'غير محدد في DGTERA':'Not set in DGTERA')}</b> — {ar?'الدفع':'Payments'}: <b>{selectedOrder.payments.map(x=>`${x.method} ${money2(Number(x.amount),ar)}`).join('، ')||'—'}</b>
        </div>
        <DataTable headers={[ar?'الكود':'Code',ar?'الصنف':'Product',ar?'الكمية':'Qty',ar?'سعر الوحدة':'Unit price',ar?'الخصم %':'Discount %',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'الإجمالي':'Total']} rows={selectedOrder.lines.map(x=>[x.code,x.product,money2(Number(x.quantity),ar),money2(Number(x.unit_price),ar),String(Number(x.discount_percent)),money2(Number(x.subtotal),ar),money2(Number(x.vat),ar),money2(Number(x.total),ar)])}/>
      </Panel>}

      <Panel title={ar?'سجل المزامنة الآلية':'Automatic synchronization log'} icon={<RefreshCw size={18}/>}>
        <DataTable headers={[ar?'الفترة':'Period',ar?'النافذة اليومية':'Daily window',ar?'المصدر':'Source',ar?'جديد':'Inserted',ar?'محدّث':'Updated',ar?'بدون تغيير':'Unchanged',ar?'الإجمالي':'Total',ar?'الحالة':'Status']} rows={runs.map(x=>[
          `${x.start_date} → ${x.end_date}`,x.window,String(x.source_orders),String(x.inserted),String(x.updated),String(x.unchanged),money2(Number(x.source_total),ar),syncLabel(x.status,ar),
        ])}/>
      </Panel>

      <div style={{padding:12,borderRadius:10,background:'#eff6ff',color:'#1e3a8a',fontSize:13,lineHeight:1.9}}>
        {ar
          ? 'الربط قراءة فقط ومخصص للمبيعات: لا يسحب قيودًا محاسبية أو مخزونًا أو تكلفة بضاعة. الفروع والأصناف والعملاء وطرق الدفع تأتي من الطلبات نفسها، وأي تعديل في DGTERA يُحدّث نفس الطلب في CORVAX من دون تكرار.'
          : 'This is a read-only sales mirror. It does not import journals, inventory or COGS. Branches, products, customers and payments come from the source orders, and source changes update the same CORVAX order without duplicates.'}
      </div>
    </>}
  </>;
}
