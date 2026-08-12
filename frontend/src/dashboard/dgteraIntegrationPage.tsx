import {useEffect, useMemo, useState} from 'react';
import {Bike, Clock3, DatabaseZap, Link2, PackageSearch, Receipt, RefreshCw, Store, Users} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type Status={
  configured:boolean;connected?:boolean;base_url?:string;active?:boolean;
  last_tested_at?:string|null;last_sync_at?:string|null;last_error?:string|null;
  timezone?:string;day_window?:string;sync_interval_minutes?:number;
};
type SummaryRow={key:string;orders:number;subtotal:number;vat:number;sales:number};
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
  mode:string;window:any;totals:any;master_counts:any;branches:any[];
  branch_sales:SummaryRow[];scope_sales:SummaryRow[];service_sales:SummaryRow[];
  platform_sales:SummaryRow[];customer_sales:SummaryRow[];product_sales:ProductRow[];orders:Order[];
};
type SyncRun={id:number;start_date:string;end_date:string;window:string;status:string;source_orders:number;inserted:number;updated:number;unchanged:number;source_total:number;error?:string|null;completed_at?:string|null};

const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9,background:'var(--surface)',color:'var(--text)'} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(210px,1fr))',gap:12,padding:12} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;

function riyadhToday(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Riyadh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const get=(type:string)=>parts.find(x=>x.type===type)?.value||'';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init);const x=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}

const scopeLabel=(value:string,ar:boolean)=>value==='INTERNAL'?(ar?'مبيعات داخلية':'Internal sales'):(ar?'مبيعات خارجية':'External sales');
const serviceLabel=(value:string,ar:boolean)=>({
  DINE_IN:ar?'داخل المطعم':'Dine-in',
  TAKEAWAY:ar?'سفري / استلام':'Takeaway',
  DELIVERY:ar?'تطبيقات التوصيل':'Delivery apps',
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
  const [runs,setRuns]=useState<SyncRun[]>([]);
  const [baseUrl,setBaseUrl]=useState('https://cheesehouse.dgtera.com');
  const [database,setDatabase]=useState('cheesehouse');
  const [login,setLogin]=useState('');const [apiKey,setApiKey]=useState('');
  const [startDate,setStartDate]=useState(today);const [endDate,setEndDate]=useState(today);
  const [branchId,setBranchId]=useState('');const [scope,setScope]=useState('');const [service,setService]=useState('');
  const [selectedOrder,setSelectedOrder]=useState<Order|null>(null);
  const [busy,setBusy]=useState(false);const [msg,setMsg]=useState('');const [isError,setIsError]=useState(false);

  const load=async()=>{
    const st=await json(`/api/v1/integrations/dgtera/status?company_id=${companyId}`).catch(()=>({configured:false}));
    setStatus(st);if(st.base_url)setBaseUrl(st.base_url);
    if(!st.configured){setSnapshot(null);setRuns([]);return;}
    const params=new URLSearchParams({company_id:String(companyId),start_date:startDate,end_date:endDate});
    if(branchId)params.set('branch_id',branchId);if(scope)params.set('sales_scope',scope);if(service)params.set('service_mode',service);
    const [snap,history]=await Promise.all([
      json(`/api/v1/integrations/dgtera/snapshot?${params.toString()}`),
      json(`/api/v1/integrations/dgtera/sync-runs?company_id=${companyId}&limit=30`).catch(()=>[]),
    ]);
    setSnapshot(snap);setRuns(history);setSelectedOrder(current=>current? snap.orders.find((x:Order)=>x.id===current.id)||null:null);
  };

  useEffect(()=>{load().catch(e=>{setMsg(String(e.message||e));setIsError(true)})},[companyId,startDate,endDate,branchId,scope,service]);
  useEffect(()=>{
    const timer=window.setInterval(()=>load().catch(()=>{}),60000);
    return()=>window.clearInterval(timer);
  },[companyId,startDate,endDate,branchId,scope,service]);

  const say=(text:string,error=false)=>{setMsg(text);setIsError(error)};
  const saveConnection=async()=>{
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
      say(ar?`تم التحقق والربط تلقائيًا: أضيف ${imported} طلب وحُدّث ${updated}. ستتجدد البيانات كل 5 دقائق.`:`Connected and synchronized automatically: ${imported} inserted, ${updated} updated. Refresh runs every 5 minutes.`);
      await load();
    }catch(e:any){say(String(e.message||e),true)}finally{setBusy(false)}
  };

  const totals=snapshot?.totals||{};
  const counts=snapshot?.master_counts||{};
  return <>
    <div className="kpis">
      <Kpi title={ar?'إجمالي المبيعات':'Total sales'} value={snapshot?fmt(Number(totals.sales||0)):'—'} trend={ar?'من DGTERA فقط':'DGTERA sales only'} good icon={<Receipt size={22}/>} tone="blue"/>
      <Kpi title={ar?'المبيعات الداخلية':'Internal sales'} value={snapshot?fmt(Number(totals.internal_sales||0)):'—'} trend={ar?'مطعم + سفري':'Dine-in + takeaway'} good icon={<Store size={22}/>} tone="violet"/>
      <Kpi title={ar?'المبيعات الخارجية':'External sales'} value={snapshot?fmt(Number(totals.external_sales||0)):'—'} trend={ar?'منصات التوصيل':'Delivery platforms'} good icon={<Bike size={22}/>} tone="amber"/>
      <Kpi title={ar?'عدد الطلبات':'Orders'} value={String(totals.orders||0)} trend="00:01–23:59" good icon={<DatabaseZap size={22}/>} tone="green"/>
    </div>

    {msg&&<div style={{padding:11,margin:'12px 0',borderRadius:9,lineHeight:1.8,background:isError?'#fee2e2':'#dcfce7',color:isError?'#991b1b':'#166534'}}>{msg}</div>}

    <Panel title={ar?'اتصال DGTERA الآلي':'Automatic DGTERA connection'} icon={<Link2 size={18}/>}>
      <div style={{padding:'10px 12px 0',fontSize:13,lineHeight:1.9,opacity:.9}}>
        {ar
          ? 'يحفظ CORVAX بيانات الاتصال مشفرة، ويختبرها ويبدأ الاستيراد تلقائيًا عند الحفظ. لا توجد مطابقة فروع أو حسابات ولا زر استيراد يدوي.'
          : 'CORVAX encrypts the connection, verifies it and starts importing automatically. There is no manual mapping or manual import.'}
      </div>
      <div style={grid}>
        <label>{ar?'رابط DGTERA':'DGTERA URL'}<input style={field} value={baseUrl} onChange={e=>setBaseUrl(e.target.value)}/></label>
        <label>{ar?'اسم قاعدة Odoo':'Odoo database'}<input style={field} value={database} onChange={e=>setDatabase(e.target.value)} placeholder={status.configured?(ar?'اتركه كما هو إن لم يتغير':'Leave unchanged'):''}/></label>
        <label>{ar?'مستخدم API للقراءة':'Read-only API login'}<input style={field} value={login} onChange={e=>setLogin(e.target.value)} autoComplete="off" placeholder={status.configured?(ar?'اتركه فارغًا للحفاظ عليه':'Leave blank to keep'):''}/></label>
        <label>{ar?'مفتاح API':'API key'}<input type="password" style={field} value={apiKey} onChange={e=>setApiKey(e.target.value)} autoComplete="new-password" placeholder={status.configured?'••••••••••••':''}/></label>
      </div>
      <div style={{display:'flex',gap:12,padding:'0 12px 14px',alignItems:'center',flexWrap:'wrap'}}>
        <button style={{...btn,opacity:busy?.6:1}} disabled={busy} onClick={saveConnection}>{ar?'حفظ وتفعيل الربط الآلي':'Save & activate automatic sync'}</button>
        <span style={{fontSize:13,lineHeight:1.8}}>
          <Clock3 size={16}/> {ar?'يوم المبيعات: 00:01 إلى 23:59 بتوقيت الرياض — تحديث تلقائي كل 5 دقائق.':'Sales day: 00:01–23:59 Asia/Riyadh — automatic refresh every 5 minutes.'}
        </span>
      </div>
      {status.configured&&<div style={{padding:'0 12px 14px',fontSize:13,lineHeight:1.8}}>
        {ar?'الحالة':'Status'}: <b>{status.connected?(ar?'متصل ويعمل تلقائيًا':'Connected and automatic'):(ar?'الاتصال يحتاج فحصًا':'Connection needs attention')}</b>
        {' — '}{ar?'آخر مزامنة':'Last sync'}: {status.last_sync_at?String(status.last_sync_at).replace('T',' ').slice(0,19):(ar?'لم تبدأ بعد':'Not started')}
        {status.last_error&&<span style={{color:'#b91c1c'}}> — {status.last_error}</span>}
      </div>}
    </Panel>

    {status.configured&&<>
      <Panel title={ar?'فترة عرض المبيعات':'Sales display period'} icon={<Clock3 size={18}/>}>
        <div style={grid}>
          <label>{ar?'من':'From'}<input type="date" style={field} value={startDate} onChange={e=>setStartDate(e.target.value)}/></label>
          <label>{ar?'إلى':'To'}<input type="date" style={field} value={endDate} onChange={e=>setEndDate(e.target.value)}/></label>
          <label>{ar?'الفرع':'Branch'}<select style={field} value={branchId} onChange={e=>setBranchId(e.target.value)}><option value="">{ar?'كل الفروع':'All branches'}</option>{(snapshot?.branches||[]).map(x=><option key={x.branch_id} value={x.branch_id}>{x.name}</option>)}</select></label>
          <label>{ar?'داخلي / خارجي':'Internal / external'}<select style={field} value={scope} onChange={e=>setScope(e.target.value)}><option value="">{ar?'الكل':'All'}</option><option value="INTERNAL">{ar?'داخلي':'Internal'}</option><option value="EXTERNAL">{ar?'خارجي':'External'}</option></select></label>
          <label>{ar?'نوع الخدمة':'Service mode'}<select style={field} value={service} onChange={e=>setService(e.target.value)}><option value="">{ar?'الكل':'All'}</option><option value="DINE_IN">{ar?'داخل المطعم':'Dine-in'}</option><option value="TAKEAWAY">{ar?'سفري / استلام':'Takeaway'}</option><option value="DELIVERY">{ar?'توصيل':'Delivery'}</option></select></label>
        </div>
      </Panel>

      <div className="kpis">
        <Kpi title={ar?'الفروع':'Branches'} value={String(counts.branches||0)} trend={ar?'أُنشئت من DGTERA':'From DGTERA'} good icon={<Store size={22}/>} tone="blue"/>
        <Kpi title={ar?'الأصناف':'Products'} value={String(counts.products||0)} trend={ar?'أكواد وأسعار المصدر':'Source codes & prices'} good icon={<PackageSearch size={22}/>} tone="violet"/>
        <Kpi title={ar?'العملاء':'Customers'} value={String(counts.customers||0)} trend={ar?'بما فيها شركات التوصيل':'Including delivery companies'} good icon={<Users size={22}/>} tone="green"/>
        <Kpi title={ar?'ضريبة المبيعات':'Sales VAT'} value={snapshot?fmt(Number(totals.vat||0)):'—'} trend={ar?'كما وردت من DGTERA':'As received from DGTERA'} good icon={<Receipt size={22}/>} tone="amber"/>
      </div>

      <Panel title={ar?'المبيعات حسب الفرع':'Sales by branch'} icon={<Store size={18}/>}>
        <DataTable headers={[ar?'الفرع':'Branch',ar?'الطلبات':'Orders',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'الإجمالي':'Total']} rows={(snapshot?.branch_sales||[]).map(x=>[x.key,String(x.orders),fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.sales))])}/>
      </Panel>

      <Panel title={ar?'تفصيل الداخلي والخارجي ونوع الخدمة':'Internal, external and service detail'} icon={<DatabaseZap size={18}/>}>
        <DataTable headers={[ar?'التصنيف':'Classification',ar?'الطلبات':'Orders',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={[
          ...(snapshot?.scope_sales||[]).map(x=>[scopeLabel(x.key,ar),String(x.orders),fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.sales))]),
          ...(snapshot?.service_sales||[]).map(x=>[serviceLabel(x.key,ar),String(x.orders),fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.sales))]),
        ]}/>
      </Panel>

      <Panel title={ar?'شركات ومنصات التوصيل':'Delivery companies and platforms'} icon={<Bike size={18}/>}>
        <DataTable headers={[ar?'المنصة / العميل':'Platform / customer',ar?'الطلبات':'Orders',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={(snapshot?.platform_sales||[]).map(x=>[x.key,String(x.orders),fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.sales))])}/>
      </Panel>

      <Panel title={ar?'العملاء':'Customers'} icon={<Users size={18}/>}>
        <DataTable headers={[ar?'العميل':'Customer',ar?'الطلبات':'Orders',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={(snapshot?.customer_sales||[]).map(x=>[x.key,String(x.orders),fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.sales))])}/>
      </Panel>

      <Panel title={ar?'مبيعات الأصناف':'Product sales'} icon={<PackageSearch size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الصنف':'Product',ar?'الكمية':'Qty',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'المبيعات':'Sales']} rows={(snapshot?.product_sales||[]).map(x=>[x.code,x.key,String(Number(x.quantity||0)),fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.sales))])}/>
      </Panel>

      <Panel title={ar?'طلبات DGTERA':'DGTERA orders'} icon={<Receipt size={18}/>}>
        <DataTable headers={[ar?'الطلب':'Order',ar?'الوقت':'Time',ar?'الفرع':'Branch',ar?'النوع':'Type',ar?'العميل / المنصة':'Customer / platform',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'الإجمالي':'Total',ar?'':'']} rows={(snapshot?.orders||[]).map(x=>[
          x.pos_reference||x.order_name,String(x.ordered_at).replace('T',' ').slice(0,16),x.branch,
          `${scopeLabel(x.sales_scope,ar)} — ${serviceLabel(x.service_mode,ar)}`,
          x.platform||x.customer||(ar?'عميل نقدي':'Walk-in'),
          fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.total)),
          <button key={x.id} style={{...btn,padding:'6px 10px'}} onClick={()=>setSelectedOrder(x)}>{ar?'التفاصيل':'Details'}</button>,
        ])}/>
      </Panel>

      {selectedOrder&&<Panel title={ar?`تفاصيل الطلب ${selectedOrder.pos_reference||selectedOrder.order_name}`:`Order details ${selectedOrder.pos_reference||selectedOrder.order_name}`} icon={<Receipt size={18}/>}>
        <div style={{padding:12,fontSize:13,lineHeight:1.9}}>
          {ar?'الفرع':'Branch'}: <b>{selectedOrder.branch}</b> — {ar?'العميل':'Customer'}: <b>{selectedOrder.platform||selectedOrder.customer||(ar?'غير محدد في DGTERA':'Not set in DGTERA')}</b> — {ar?'الدفع':'Payments'}: <b>{selectedOrder.payments.map(x=>`${x.method} ${fmt(Number(x.amount))}`).join('، ')||'—'}</b>
        </div>
        <DataTable headers={[ar?'الكود':'Code',ar?'الصنف':'Product',ar?'الكمية':'Qty',ar?'سعر الوحدة':'Unit price',ar?'الخصم %':'Discount %',ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'الإجمالي':'Total']} rows={selectedOrder.lines.map(x=>[x.code,x.product,String(Number(x.quantity)),fmt(Number(x.unit_price)),String(Number(x.discount_percent)),fmt(Number(x.subtotal)),fmt(Number(x.vat)),fmt(Number(x.total))])}/>
      </Panel>}

      <Panel title={ar?'سجل المزامنة الآلية':'Automatic synchronization log'} icon={<RefreshCw size={18}/>}>
        <DataTable headers={[ar?'الفترة':'Period',ar?'النافذة اليومية':'Daily window',ar?'المصدر':'Source',ar?'جديد':'Inserted',ar?'محدّث':'Updated',ar?'بدون تغيير':'Unchanged',ar?'الإجمالي':'Total',ar?'الحالة':'Status']} rows={runs.map(x=>[
          `${x.start_date} → ${x.end_date}`,x.window,String(x.source_orders),String(x.inserted),String(x.updated),String(x.unchanged),fmt(Number(x.source_total)),syncLabel(x.status,ar),
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

