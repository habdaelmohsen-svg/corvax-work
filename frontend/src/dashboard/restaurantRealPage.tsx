import {useEffect, useMemo, useState} from 'react';
import {Bike, CalendarDays, CheckCircle2, DatabaseZap, RefreshCw, Receipt, ShieldCheck, Store, UtensilsCrossed} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';
import {DgteraIntegrationPage} from './dgteraIntegrationPage';

type Tab='sell'|'menu'|'platforms'|'orders'|'dgtera';
type SummaryRow={key:string;orders:number;quantity?:number;subtotal:number;vat:number;sales:number};
type ProductRow=SummaryRow&{code:string;quantity:number};
type DgteraOrder={
  id:number;pos_reference?:string|null;order_name:string;ordered_at:string;branch:string;
  sales_scope:string;service_mode:string;platform?:string|null;customer?:string|null;
  subtotal:number;vat:number;total:number;payments:Array<{method:string;amount:number}>;
};
type Snapshot={
  trusted_sales?:boolean;
  totals:{orders:number;quantity:number;subtotal:number;vat:number;sales:number}|null;
  product_sales:ProductRow[];platform_sales:SummaryRow[];payment_channels:SummaryRow[];
  orders:DgteraOrder[];coverage?:{complete:boolean;first_missing_date?:string|null;last_verified_at?:string|null};
  reconciliation?:{available:boolean;matched:boolean;source_total:number|null;imported_total:number;difference:number|null};
};
type Status={configured:boolean;connected?:boolean;inherited?:boolean;last_error?:string|null;last_sync_at?:string|null;
  proof?:{verified_days:number;latest_attempt_status?:string|null;serving_last_verified_after_source_error?:boolean};
  accounting?:{posted_days:number;pending_days:number;blocked_days:number};
  history?:{progress_percent:number;completed:boolean};
};

const REQUEST_TIMEOUT_MS=30000;
async function json(url:string,init?:RequestInit){
  const controller=new AbortController();
  const timer=window.setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
  try{
    const response=await apiFetch(url,{...init,signal:controller.signal});const body=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body));
    return body;
  }catch(error){
    if(controller.signal.aborted)throw new Error(`DGTERA API request timed out after ${REQUEST_TIMEOUT_MS/1000} seconds`);
    throw error;
  }finally{window.clearTimeout(timer)}
}
function riyadhToday(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Riyadh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const get=(type:string)=>parts.find(x=>x.type===type)?.value||'';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
const paymentLabel=(key:string,ar:boolean)=>({
  CASH:ar?'نقدي':'Cash',CARD:ar?'بطاقات / شبكة':'Card / POS',
  PLATFORM_CREDIT:ar?'آجل — ذمم تطبيقات التوصيل':'On account — delivery apps',
  OTHER:ar?'طريقة دفع أخرى':'Other payment',UNCLASSIFIED:ar?'غير مصنف':'Unclassified',
}[key]||key);
const serviceLabel=(key:string,ar:boolean)=>({
  DINE_IN:ar?'داخل المطعم':'Dine-in',TAKEAWAY:ar?'سفري / استلام':'Takeaway',
  DELIVERY:ar?'تطبيق توصيل':'Delivery app',
}[key]||key);

export function RestaurantPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=useMemo(riyadhToday,[]);
  const [tab,setTab]=useState<Tab>('sell');
  const [salesDate,setSalesDate]=useState(today);
  const [status,setStatus]=useState<Status>({configured:false});
  const [statusReady,setStatusReady]=useState(false);
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [message,setMessage]=useState('');
  const [sourceNotice,setSourceNotice]=useState('');
  const [loading,setLoading]=useState(false);
  const [refreshing,setRefreshing]=useState(false);

  const load=async(refreshSource=false)=>{
    setLoading(true);
    try{
      const currentStatus=await json(`/api/v1/integrations/dgtera/status?company_id=${companyId}`);
      setStatus(currentStatus);
      setStatusReady(true);
      if(!currentStatus.configured){setSnapshot(null);return;}
      if(refreshSource&&salesDate===today){
        setRefreshing(true);
        try{
          const result=await json(`/api/v1/integrations/dgtera/refresh-current?company_id=${companyId}`,{method:'POST'});
          setSourceNotice(result.refreshed
            ? (ar?'تمت قراءة يوم DGTERA الحالي ومطابقته الآن.':'Current DGTERA day was read and reconciled now.')
            : '');
        }catch(error){
          setSourceNotice(ar
            ? `تعذر التحديث المباشر، وسيستمر عرض آخر يوم موثّق: ${String((error as Error).message||error)}`
            : `Live refresh failed; the last verified day remains visible: ${String((error as Error).message||error)}`);
        }finally{setRefreshing(false)}
      }
      const data=await json(`/api/v1/integrations/dgtera/snapshot?company_id=${companyId}&start_date=${salesDate}&end_date=${salesDate}&limit=1000`);
      setSnapshot(data);setMessage('');
    }catch(error){
      setSnapshot(null);
      throw error;
    }finally{setLoading(false)}
  };
  useEffect(()=>{
    setStatusReady(false);setMessage('');
    load(salesDate===today).catch(e=>setMessage(ar
      ? `تعذر تحميل بيانات DGTERA: ${String(e.message||e)}. لم يُعامل هذا الخطأ كعدم وجود ربط.`
      : `DGTERA data could not be loaded: ${String(e.message||e)}. This error was not treated as a missing connection.`));
  },[companyId,salesDate]);
  useEffect(()=>{
    const timer=window.setInterval(()=>load(salesDate===today).catch(()=>{}),120000);
    return()=>window.clearInterval(timer);
  },[companyId,salesDate]);

  const totals=snapshot?.totals;
  const tabs:Array<[Tab,string]>=[
    ['sell',ar?'شاشة البيع':'Sales screen'],['menu',ar?'قائمة الطعام':'Menu'],
    ['platforms',ar?'منصات التوصيل':'Delivery platforms'],['orders',ar?'الطلبات':'Orders'],
    ['dgtera',ar?'الربط':'Integration'],
  ];
  return <div className="restaurant-workspace">
    <div className="kpis">
      <Kpi title={ar?'صافي المبيعات':'Net sales'} value={totals?fmt(Number(totals.subtotal||0)):'—'} trend={ar?'إيراد مرحّل':'Posted revenue'} good={Boolean(snapshot?.trusted_sales)} icon={<Receipt size={22}/>} tone="blue"/>
      <Kpi title={ar?'ضريبة المبيعات':'Sales VAT'} value={totals?fmt(Number(totals.vat||0)):'—'} trend={ar?'من تقرير DGTERA':'DGTERA report'} good={Boolean(snapshot?.trusted_sales)} icon={<DatabaseZap size={22}/>} tone="violet"/>
      <Kpi title={ar?'إجمالي المبيعات':'Gross sales'} value={totals?fmt(Number(totals.sales||0)):'—'} trend={ar?'شامل الضريبة':'Including VAT'} good={Boolean(snapshot?.trusted_sales)} icon={<Store size={22}/>} tone="green"/>
      <Kpi title={ar?'عدد الطلبات':'Orders'} value={String(totals?.orders??'—')} trend={salesDate} good={Boolean(snapshot?.trusted_sales)} icon={<Bike size={22}/>} tone="amber"/>
    </div>

    <div className="module-commandbar">
      <label className="date-control"><CalendarDays size={17}/><span>{ar?'تاريخ التقرير':'Report date'}</span><input type="date" min="2025-01-01" value={salesDate} onChange={e=>setSalesDate(e.target.value)}/></label>
      <div className="module-tabs">{tabs.map(([key,label])=><button key={key} type="button" onClick={()=>setTab(key)} className={tab===key?'active':''}>{label}</button>)}</div>
      <button className="refresh-source" type="button" disabled={refreshing||loading||salesDate!==today} onClick={()=>load(true)}><RefreshCw size={17} className={refreshing?'spin':''}/>{ar?'تحديث المصدر':'Refresh source'}</button>
    </div>

    <div className="integration-health">
      <article className={status.connected?'healthy':'warning'}><CheckCircle2 size={18}/><span>{ar?'اتصال DGTERA':'DGTERA connection'}</span><strong>{status.connected?(ar?'متصل':'Connected'):(ar?'بانتظار الربط':'Setup required')}</strong></article>
      <article className={(status.accounting?.pending_days||0)===0?'healthy':'warning'}><Receipt size={18}/><span>{ar?'الترحيل المحاسبي':'Ledger posting'}</span><strong>{ar?`${status.accounting?.posted_days||0} يوم مرحّل`:`${status.accounting?.posted_days||0} days posted`}</strong></article>
      <article className={status.history?.completed?'healthy':'progressing'}><DatabaseZap size={18}/><span>{ar?'التاريخ المستورد':'Imported history'}</span><strong>{status.history?.progress_percent??0}%</strong></article>
      <article className={snapshot?.trusted_sales?'healthy':'warning'}><ShieldCheck size={18}/><span>{ar?'دليل اليوم':'Day proof'}</span><strong>{snapshot?.trusted_sales?(ar?'مطابق بلا فرق':'Zero difference'):(ar?'غير مكتمل':'Incomplete')}</strong></article>
    </div>

    {statusReady&&!status.configured&&<div className="system-banner warning">
      {ar?'لم يتم العثور على ربط DGTERA في القابضة أو شركة المطاعم. افتح تبويب «الربط» لإكمال الإعداد.':'No DGTERA connection was found in the holding or restaurant company. Open Integration to configure it.'}
    </div>}
    {message&&<div className="system-banner danger">{message}</div>}
    {sourceNotice&&<div className="system-banner info">{sourceNotice}</div>}
    {status.configured&&snapshot&&!snapshot.trusted_sales&&<div className="system-banner danger">
      {ar?'تم إيقاف عرض المبيعات لأن الفترة لم تجتز المطابقة الصارمة مع DGTERA دون أي فرق. لا يتم استخدام أرقام نقطة البيع المحلية أو أرقام محفوظة قديمة كبديل.':'Sales are hidden because this period has not passed zero-difference strict reconciliation with DGTERA. Local POS or stale cached figures are never used as a fallback.'}
      {snapshot.coverage?.first_missing_date&&<small>{ar?'أول يوم يحتاج إعادة قراءة: ':'First date requiring a new read: '}{snapshot.coverage.first_missing_date}</small>}
    </div>}

    {status.configured&&snapshot?.reconciliation?.available&&<div className={`system-banner ${snapshot.reconciliation.matched?'success':'danger'} reconciliation-banner`}>
      <b>{snapshot.reconciliation.matched?(ar?'✓ مبيعات اليوم مطابقة مع DGTERA':'✓ Day sales reconciled with DGTERA'):(ar?'⚠ يوجد فرق مطابقة':'⚠ Reconciliation difference')}</b>
      {' — '}{ar?'المصدر':'Source'}: {fmt(Number(snapshot.reconciliation.source_total||0))}
      {' — '}CORVAX: {fmt(Number(snapshot.reconciliation.imported_total||0))}
      {' — '}{ar?'الفرق':'Difference'}: {fmt(Number(snapshot.reconciliation.difference||0))}
    </div>}

    {tab==='sell'&&status.configured&&<Panel title={ar?'مبيعات DGTERA — عرض مباشر للقراءة':'DGTERA sales — live read-only view'} icon={<Receipt size={18}/> }>
      <div className="panel-intro">
        {ar
          ? 'هذه الشاشة تعرض مبيعات DGTERA الفعلية وتُحدّث كل دقيقتين. لا تُنشئ طلبًا ثانيًا داخل CORVAX، وبذلك لا تتكرر الإيرادات بين المطاعم والقابضة.'
          : 'This screen shows actual DGTERA sales and refreshes every two minutes. It does not create a second CORVAX order, preventing duplicated restaurant/holding revenue.'}
      </div>
      <DataTable headers={[ar?'التصنيف':'Collection',ar?'الطلبات':'Orders',ar?'صافي المبيعات':'Net sales',ar?'الضريبة':'VAT',ar?'الإجمالي':'Gross']} rows={(snapshot?.payment_channels||[]).map(row=>[
        paymentLabel(row.key,ar),String(row.orders),fmt(Number(row.subtotal)),fmt(Number(row.vat)),fmt(Number(row.sales)),
      ])}/>
    </Panel>}

    {tab==='menu'&&status.configured&&<Panel title={ar?'قائمة الطعام ومبيعات الأصناف من DGTERA':'DGTERA menu and product sales'} icon={<UtensilsCrossed size={18}/> }>
      <DataTable headers={[ar?'الكود':'Code',ar?'الصنف':'Product',ar?'الكمية':'Qty',ar?'صافي المبيعات':'Net sales',ar?'الضريبة':'VAT',ar?'الإجمالي':'Gross']} rows={(snapshot?.product_sales||[]).map(row=>[
        row.code,row.key,fmt(Number(row.quantity)),fmt(Number(row.subtotal)),fmt(Number(row.vat)),fmt(Number(row.sales)),
      ])}/>
    </Panel>}

    {tab==='platforms'&&status.configured&&<>
      <Panel title={ar?'منصات التوصيل من DGTERA':'DGTERA delivery platforms'} icon={<Bike size={18}/> }>
        <DataTable headers={[ar?'المنصة':'Platform',ar?'الطلبات':'Orders',ar?'صافي المبيعات':'Net sales',ar?'الضريبة':'VAT',ar?'الإجمالي':'Gross']} rows={(snapshot?.platform_sales||[]).map(row=>[
          row.key,String(row.orders),fmt(Number(row.subtotal)),fmt(Number(row.vat)),fmt(Number(row.sales)),
        ])}/>
      </Panel>
      <Panel title={ar?'الآجل المستحق على تطبيقات التوصيل':'Delivery-app receivables'} icon={<DatabaseZap size={18}/> }>
        <DataTable headers={[ar?'التصنيف':'Classification',ar?'الطلبات':'Orders',ar?'الصافي المستحق':'Net receivable',ar?'الضريبة':'VAT',ar?'الإجمالي':'Gross']} rows={(snapshot?.payment_channels||[]).filter(row=>row.key==='PLATFORM_CREDIT').map(row=>[
          paymentLabel(row.key,ar),String(row.orders),fmt(Number(row.subtotal)),fmt(Number(row.vat)),fmt(Number(row.sales)),
        ])}/>
      </Panel>
    </>}

    {tab==='orders'&&status.configured&&<Panel title={ar?'طلبات DGTERA':'DGTERA orders'} icon={<Receipt size={18}/> }>
      <DataTable headers={[ar?'الطلب':'Order',ar?'الوقت':'Time',ar?'الفرع':'Branch',ar?'الخدمة':'Service',ar?'العميل / المنصة':'Customer / platform',ar?'صافي':'Net',ar?'الضريبة':'VAT',ar?'الإجمالي':'Gross',ar?'الدفع':'Payment']} rows={(snapshot?.orders||[]).map(order=>[
        order.pos_reference||order.order_name,String(order.ordered_at).replace('T',' ').slice(0,16),order.branch,
        serviceLabel(order.service_mode,ar),order.platform||order.customer||(ar?'عميل نقدي':'Walk-in'),
        fmt(Number(order.subtotal)),fmt(Number(order.vat)),fmt(Number(order.total)),
        order.payments.map(payment=>`${payment.method}: ${fmt(Number(payment.amount))}`).join('، ')||'—',
      ])}/>
    </Panel>}

    {tab==='dgtera'&&<DgteraIntegrationPage ar={ar} companyId={companyId}/>} 
  </div>;
}
