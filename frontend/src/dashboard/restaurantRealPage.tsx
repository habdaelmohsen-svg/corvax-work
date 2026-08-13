import {useEffect, useMemo, useState} from 'react';
import {Bike, DatabaseZap, Receipt, Store, UtensilsCrossed} from 'lucide-react';
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
  totals:{orders:number;quantity:number;subtotal:number;vat:number;sales:number};
  product_sales:ProductRow[];platform_sales:SummaryRow[];payment_channels:SummaryRow[];
  orders:DgteraOrder[];reconciliation?:{available:boolean;matched:boolean;source_total:number|null;imported_total:number;difference:number|null};
};
type Status={configured:boolean;connected?:boolean;inherited?:boolean;last_error?:string|null};

async function json(url:string){
  const response=await apiFetch(url);const body=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body));
  return body;
}
function riyadhToday(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Riyadh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const get=(type:string)=>parts.find(x=>x.type===type)?.value||'';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
const field={padding:9,border:'1px solid var(--border)',borderRadius:9,background:'var(--surface)',color:'var(--text)'} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'1px solid var(--border)',cursor:'pointer',fontWeight:600} as const;
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
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [message,setMessage]=useState('');

  const load=async()=>{
    const currentStatus=await json(`/api/v1/integrations/dgtera/status?company_id=${companyId}`).catch(()=>({configured:false}));
    setStatus(currentStatus);
    if(!currentStatus.configured){setSnapshot(null);return;}
    const data=await json(`/api/v1/integrations/dgtera/snapshot?company_id=${companyId}&start_date=${salesDate}&end_date=${salesDate}&limit=1000`);
    setSnapshot(data);setMessage('');
  };
  useEffect(()=>{load().catch(e=>setMessage(String(e.message||e)))},[companyId,salesDate]);
  useEffect(()=>{
    const timer=window.setInterval(()=>load().catch(()=>{}),120000);
    return()=>window.clearInterval(timer);
  },[companyId,salesDate]);

  const totals=snapshot?.totals;
  const tabs:Array<[Tab,string]>=[
    ['sell',ar?'شاشة البيع':'Sales screen'],['menu',ar?'قائمة الطعام':'Menu'],
    ['platforms',ar?'منصات التوصيل':'Delivery platforms'],['orders',ar?'الطلبات':'Orders'],
    ['dgtera',ar?'الربط':'Integration'],
  ];
  return <>
    <div className="kpis">
      <Kpi title={ar?'صافي المبيعات':'Net sales'} value={totals?fmt(Number(totals.subtotal||0)):'—'} trend={ar?'دون الضريبة':'Excluding VAT'} good icon={<Receipt size={22}/>} tone="blue"/>
      <Kpi title={ar?'ضريبة المبيعات':'Sales VAT'} value={totals?fmt(Number(totals.vat||0)):'—'} trend={ar?'من DGTERA':'From DGTERA'} good icon={<DatabaseZap size={22}/>} tone="violet"/>
      <Kpi title={ar?'إجمالي المبيعات':'Gross sales'} value={totals?fmt(Number(totals.sales||0)):'—'} trend={ar?'شامل الضريبة':'Including VAT'} good icon={<Store size={22}/>} tone="green"/>
      <Kpi title={ar?'عدد الطلبات':'Orders'} value={String(totals?.orders??'—')} trend={salesDate} good icon={<Bike size={22}/>} tone="amber"/>
    </div>

    <div style={{display:'flex',alignItems:'center',gap:10,margin:'14px 0',flexWrap:'wrap'}}>
      <label>{ar?'تاريخ المبيعات':'Sales date'} <input type="date" min="2025-01-01" style={field} value={salesDate} onChange={e=>setSalesDate(e.target.value)}/></label>
      {tabs.map(([key,label])=><button key={key} type="button" onClick={()=>setTab(key)} style={{...btn,background:tab===key?'var(--accent, #1e40af)':'transparent',color:tab===key?'#fff':'var(--text)'}}>{label}</button>)}
    </div>

    {!status.configured&&<div style={{padding:14,borderRadius:10,background:'#fff7ed',color:'#9a3412',lineHeight:1.9}}>
      {ar?'لم يتم العثور على ربط DGTERA في القابضة أو شركة المطاعم. افتح تبويب «الربط» لإكمال الإعداد.':'No DGTERA connection was found in the holding or restaurant company. Open Integration to configure it.'}
    </div>}
    {message&&<div style={{padding:12,borderRadius:10,background:'#fee2e2',color:'#991b1b'}}>{message}</div>}

    {status.configured&&snapshot?.reconciliation?.available&&<div style={{padding:12,marginBottom:12,borderRadius:10,background:snapshot.reconciliation.matched?'#dcfce7':'#fee2e2',color:snapshot.reconciliation.matched?'#166534':'#991b1b',lineHeight:1.8}}>
      <b>{snapshot.reconciliation.matched?(ar?'✓ مبيعات اليوم مطابقة مع DGTERA':'✓ Day sales reconciled with DGTERA'):(ar?'⚠ يوجد فرق مطابقة':'⚠ Reconciliation difference')}</b>
      {' — '}{ar?'المصدر':'Source'}: {fmt(Number(snapshot.reconciliation.source_total||0))}
      {' — '}CORVAX: {fmt(Number(snapshot.reconciliation.imported_total||0))}
      {' — '}{ar?'الفرق':'Difference'}: {fmt(Number(snapshot.reconciliation.difference||0))}
    </div>}

    {tab==='sell'&&status.configured&&<Panel title={ar?'مبيعات DGTERA — عرض مباشر للقراءة':'DGTERA sales — live read-only view'} icon={<Receipt size={18}/> }>
      <div style={{padding:12,lineHeight:1.9,fontSize:13}}>
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
  </>;
}
