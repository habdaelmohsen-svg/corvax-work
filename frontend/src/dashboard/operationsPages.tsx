import { useEffect, useState, type ReactNode } from 'react';
import {
  Activity, AlertTriangle, ArrowLeftRight, BadgeDollarSign, BarChart3, BookOpenCheck,
  Boxes, Building2, CalendarRange, CheckCircle2, ChevronLeft, ChevronRight, CircleDollarSign,
  ClipboardCheck, Clock3, Dumbbell, Factory, FileSpreadsheet, GitBranch, Languages, Landmark,
  LayoutDashboard, LogOut, Menu, MonitorCog, Network, ReceiptText, Search, Settings, ShieldCheck,
  ShoppingCart, TrendingDown, TrendingUp, Users, UtensilsCrossed, WalletCards, X,
  DatabaseBackup, FileCheck2, KeyRound, MapPin, UserCheck, Bell, Mail, CalendarDays,
  Moon, Sun, Command, ChevronDown, Sparkles, CreditCard, FileText, ArrowUpRight
} from 'lucide-react';
const DEMO_ACTIONS_ENABLED = import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_ACTIONS === 'true';

function isoDate(date=new Date()){return date.toISOString().slice(0,10)}
function addDaysIso(days:number){const d=new Date();d.setDate(d.getDate()+days);return isoDate(d)}
function currentMonthBounds(){const d=new Date();const y=d.getFullYear();const m=d.getMonth();return {start:isoDate(new Date(y,m,1)),end:isoDate(new Date(y,m+1,0))}}
import { money, pct, Kpi, Panel, AlertRow, AgeLine, QuickAction, SimpleKpi, MiniStatus, ModuleCard, ProgressRow, Statement, NoteCard, Flow, Checklist, SummaryLine, CostBar, DataTable, fmt, authHeaders, jsonHeaders } from './ui';

export function InventoryPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [stock,setStock]=useState<any[]>([]);const [orders,setOrders]=useState<any[]>([]);const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);
  const load=()=>Promise.all([fetch(`/api/v1/inventory/stock-summary?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),fetch(`/api/v1/inventory/purchase-orders?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json())]).then(([a,b])=>{setStock(a);setOrders(b)}).catch(()=>{});
  useEffect(()=>{load()},[companyId]);
  async function runProcurement(){setBusy(true);setMessage('');try{const [parties,warehouses,items]=await Promise.all([fetch(`/api/v1/subledgers/parties?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),fetch(`/api/v1/inventory/warehouses?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),fetch(`/api/v1/inventory/items?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json())]);const supplier=parties.find((x:any)=>x.party_type==='SUPPLIER');const wh=warehouses[0];const item=items.find((x:any)=>x.code==='RAW-001')||items[0];if(!supplier||!wh||!item)throw new Error(ar?'البيانات الأساسية غير مكتملة':'Missing master data');let r=await fetch('/api/v1/inventory/purchase-orders',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,order_date:isoDate(),supplier_id:supplier.id,warehouse_id:wh.id,lines:[{item_id:item.id,quantity:10,unit_price:12,vat_rate:15}]})});let po=await r.json();if(!r.ok)throw new Error(po.detail||'PO error');r=await fetch(`/api/v1/inventory/purchase-orders/${po.id}/approve`,{method:'POST',headers:authHeaders()});if(!r.ok)throw new Error((await r.json()).detail);r=await fetch(`/api/v1/inventory/purchase-orders/${po.id}/receive`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({receipt_date:isoDate(),lines:[{purchase_order_line_id:po.lines[0].id,quantity:10,lot_number:`LOT-${Date.now()}`,expiry_date:addDaysIso(365)}]})});const grn=await r.json();if(!r.ok)throw new Error(grn.detail);r=await fetch(`/api/v1/inventory/goods-receipts/${grn.id}/supplier-invoice`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({invoice_date:isoDate(),due_date:addDaysIso(30),supplier_invoice_number:`SUP-${Date.now()}`})});const inv=await r.json();if(!r.ok)throw new Error(inv.detail);setMessage(ar?'تم تنفيذ أمر شراء واستلام ومطابقة فاتورة المورد وترحيل القيود.':'PO, receipt, supplier invoice and accounting postings completed.');await load()}catch(e:any){setMessage(typeof e.message==='string'?e.message:JSON.stringify(e))}finally{setBusy(false)}}
  const totalValue=stock.reduce((n,r)=>n+Number(r.value||0),0);const low=stock.filter(r=>r.low_stock).length;
  return <>
    <div className="kpis rich"><Kpi title={ar?'قيمة المخزون':'Inventory value'} value={money.format(totalValue)} trend="POSTED GL" good/><Kpi title={ar?'أرصدة المخزون':'Stock balances'} value={String(stock.length)} trend={ar?'صنف/مستودع':'Item / warehouse'} good/><Kpi title={ar?'مواد منخفضة':'Low-stock items'} value={String(low)} trend={ar?'تحتاج متابعة':'Requires action'} good={low===0}/><Kpi title={ar?'أوامر الشراء':'Purchase orders'} value={String(orders.length)} trend={ar?'دورة مستندية فعلية':'Persistent workflow'} good/></div>
    <div className="journal-footer"><span>{message|| (ar?'اختبر دورة PO → GRN → Invoice':'Test PO → GRN → Invoice')}</span>{DEMO_ACTIONS_ENABLED&&<button disabled={busy} onClick={runProcurement}>{busy?(ar?'جارٍ التنفيذ...':'Running...'):(ar?'تنفيذ دورة شراء تجريبية':'Run procurement demo')}</button>}</div>
    <Panel title={ar?'الأرصدة والقيم الفعلية':'Persistent stock balances and values'} icon={<Boxes size={18}/> }><DataTable headers={[ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Quantity',ar?'الوحدة':'UOM',ar?'القيمة':'Value',ar?'الحالة':'Status']} rows={stock.map(r=>[ar?r.item_name_ar:r.item_name_en,ar?r.warehouse_name_ar:r.warehouse_name_en,String(r.quantity),r.uom,money.format(Number(r.value)),r.low_stock?(ar?'إعادة طلب':'REORDER'):(ar?'جيد':'HEALTHY')])}/></Panel>
    <Panel title={ar?'أوامر الشراء والمطابقة الثلاثية':'Purchase orders and three-way match'} icon={<ShoppingCart size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'المورد':'Supplier',ar?'القيمة':'Total',ar?'الاستلام':'Received',ar?'الحالة':'Status']} rows={orders.map(r=>[r.number,r.order_date,r.supplier,money.format(Number(r.total)),`${Number(r.received_percent).toFixed(1)}%`,r.status])}/></Panel>
  </>;
}

export function CommercePage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [summary,setSummary]=useState<any>(null); const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  const load=()=>fetch(`/api/v1/subledgers/summary?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()).then(setSummary).catch(()=>{});
  useEffect(()=>{load()},[companyId]);
  async function masters(){const [parties,banks]=await Promise.all([fetch(`/api/v1/subledgers/parties?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),fetch(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json())]);return {customer:parties.find((p:any)=>p.party_type==='CUSTOMER'),supplier:parties.find((p:any)=>p.party_type==='SUPPLIER'),bank:banks[0]}}
  async function run(kind:'sale'|'receipt'|'purchase'|'payment'){setBusy(true);setMessage('');try{const m=await masters();let response:Response;
    if(kind==='sale'){response=await fetch('/api/v1/subledgers/sales-invoices',{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify({company_id:companyId,invoice_date:isoDate(),due_date:addDaysIso(30),customer_id:m.customer.id,reference:'UI-DEMO',lines:[{description:'Demo operating sale',account_code:'411010',quantity:1,unit_price:1000,vat_rate:15}]})});const invoice=await response.json();if(!response.ok)throw new Error(invoice.detail);response=await fetch(`/api/v1/subledgers/sales-invoices/${invoice.id}/post`,{method:'POST',headers:authHeaders()})}
    else if(kind==='receipt')response=await fetch('/api/v1/subledgers/receipts',{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify({company_id:companyId,receipt_date:isoDate(),customer_id:m.customer.id,bank_account_id:m.bank.id,amount:1150,reference:'UI-RCPT'})});
    else if(kind==='purchase'){response=await fetch('/api/v1/subledgers/purchase-invoices',{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify({company_id:companyId,invoice_date:isoDate(),due_date:addDaysIso(30),supplier_id:m.supplier.id,supplier_invoice_number:`UI-${Date.now()}`,lines:[{description:'Demo operating purchase',account_code:'613010',quantity:1,unit_price:500,vat_rate:15}]})});const invoice=await response.json();if(!response.ok)throw new Error(invoice.detail);response=await fetch(`/api/v1/subledgers/purchase-invoices/${invoice.id}/post`,{method:'POST',headers:authHeaders()})}
    else response=await fetch('/api/v1/subledgers/payments',{method:'POST',headers:{'Content-Type':'application/json',...authHeaders()},body:JSON.stringify({company_id:companyId,payment_date:isoDate(),supplier_id:m.supplier.id,bank_account_id:m.bank.id,amount:575,reference:'UI-PAY'})});
    const result=await response.json();if(!response.ok)throw new Error(result.detail||'Error');setMessage(ar?'تم إنشاء المستند وترحيل أثره المحاسبي.':'Document created and accounting impact posted.');await load()
  }catch(e:any){setMessage(e.message)}finally{setBusy(false)}}
  return <>
    <div className="kpis rich"><Kpi title={ar?'رصيد البنك':'Bank balance'} value={summary?money.format(Number(summary.cash_balance)):'—'} trend="GL linked" good/><Kpi title={ar?'ذمم العملاء':'Accounts receivable'} value={summary?money.format(Number(summary.accounts_receivable)):'—'} trend="AR control" good/><Kpi title={ar?'ذمم الموردين':'Accounts payable'} value={summary?money.format(Number(summary.accounts_payable)):'—'} trend="AP control" good/><Kpi title={ar?'مطابقة الدفاتر':'Subledger reconciliation'} value={summary?'Linked':'—'} trend="Subledger → GL" good/></div>
    <div className="two-columns"><Panel title={ar?'دورة المبيعات والتحصيل':'Sales and collection cycle'} icon={<BadgeDollarSign size={18}/> }><Flow steps={[ar?'فاتورة بيع':'Sales invoice',ar?'ضريبة المخرجات':'Output VAT',ar?'ذمم العميل':'Receivable',ar?'سند قبض':'Receipt',ar?'البنك':'Bank']}/><div className="journal-footer"><span>{ar?'قيد آلي وربط بالمستند':'Automatic journal and document link'}</span>{DEMO_ACTIONS_ENABLED&&<div><button disabled={busy} onClick={()=>run('sale')}>{ar?'إنشاء وترحيل فاتورة':'Post sale invoice'}</button><button disabled={busy} onClick={()=>run('receipt')}>{ar?'تسجيل قبض':'Post receipt'}</button></div>}</div></Panel>
      <Panel title={ar?'دورة المشتريات والسداد':'Purchasing and payment cycle'} icon={<ShoppingCart size={18}/> }><Flow steps={[ar?'فاتورة مورد':'Supplier invoice',ar?'ضريبة المدخلات':'Input VAT',ar?'ذمم المورد':'Payable',ar?'سند صرف':'Payment',ar?'البنك':'Bank']}/><div className="journal-footer"><span>{ar?'قيد آلي وربط بالمستند':'Automatic journal and document link'}</span>{DEMO_ACTIONS_ENABLED&&<div><button disabled={busy} onClick={()=>run('purchase')}>{ar?'إنشاء وترحيل فاتورة':'Post purchase invoice'}</button><button disabled={busy} onClick={()=>run('payment')}>{ar?'تسجيل سداد':'Post payment'}</button></div>}</div></Panel></div>
    {message&&<div className="status-pill"><CheckCircle2 size={17}/>{message}</div>}
    <Panel title={ar?'حالة الدفاتر الفرعية':'Subledger status'} icon={<ReceiptText size={18}/> }><DataTable headers={[ar?'المؤشر':'Metric',ar?'العدد':'Count',ar?'الحالة':'Status']} rows={summary?[[ar?'فواتير البيع':'Sales invoices',String(summary.sales_invoices),ar?'مرتبطة بالأستاذ':'GL linked'],[ar?'فواتير الشراء':'Purchase invoices',String(summary.purchase_invoices),ar?'مرتبطة بالأستاذ':'GL linked'],[ar?'سندات القبض':'Receipts',String(summary.receipts),ar?'مرحلة':'Posted'],[ar?'سندات الصرف':'Payments',String(summary.payments),ar?'مرحلة':'Posted']]:[]}/></Panel>
  </>;
}

export function GymPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [summary,setSummary]=useState<any>(null);const [revenue,setRevenue]=useState<any>(null);
  const [contracts,setContracts]=useState<any[]>([]);const [classes,setClasses]=useState<any[]>([]);
  const [ptSales,setPtSales]=useState<any[]>([]);const [access,setAccess]=useState<any[]>([]);
  const [lockers,setLockers]=useState<any[]>([]);const [mods,setMods]=useState<any[]>([]);
  const [commercial,setCommercial]=useState<any>(null);const [departments,setDepartments]=useState<any[]>([]);const [facilities,setFacilities]=useState<any[]>([]);
  const [facilityBookings,setFacilityBookings]=useState<any[]>([]);const [cafeProducts,setCafeProducts]=useState<any[]>([]);const [cafeOrders,setCafeOrders]=useState<any[]>([]);const [departmentAccess,setDepartmentAccess]=useState<any[]>([]);
  const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);
  const safeJson=async(url:string,fallback:any)=>{const r=await fetch(url,{headers:authHeaders()});if(!r.ok)return fallback;return r.json()};
  const load=async()=>{setBusy(true);try{const [a,b,c,d,e,f,g,h,i,j,k,l,m,n,o]=await Promise.all([
    safeJson(`/api/v1/gym/summary?company_id=${companyId}`,null),
    safeJson(`/api/v1/revenue-recognition/summary?company_id=${companyId}`,null),
    safeJson(`/api/v1/revenue-recognition/contracts?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/class-sessions?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/pt-sales?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/access-records?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/lockers?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/membership-modifications?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/commercial-summary?company_id=${companyId}`,null),
    safeJson(`/api/v1/gym/departments?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/facilities?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/facility-bookings?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/cafe/products?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/cafe/orders?company_id=${companyId}`,[]),
    safeJson(`/api/v1/gym/department-access?company_id=${companyId}`,[]),
  ]);setSummary(a);setRevenue(b);setContracts(Array.isArray(c)?c:[]);setClasses(Array.isArray(d)?d:[]);setPtSales(Array.isArray(e)?e:[]);setAccess(Array.isArray(f)?f:[]);setLockers(Array.isArray(g)?g:[]);setMods(Array.isArray(h)?h:[]);setCommercial(i);setDepartments(Array.isArray(j)?j:[]);setFacilities(Array.isArray(k)?k:[]);setFacilityBookings(Array.isArray(l)?l:[]);setCafeProducts(Array.isArray(m)?m:[]);setCafeOrders(Array.isArray(n)?n:[]);setDepartmentAccess(Array.isArray(o)?o:[]);setMessage('')}catch(e:any){setMessage(e?.message||String(e))}finally{setBusy(false)}};
  useEffect(()=>{load()},[companyId]);
  const granted=access.filter(x=>x.status==='GRANTED').length;const denied=access.filter(x=>x.status==='DENIED').length;
  return <>
    <div className="kpis rich"><Kpi title={ar?'العضويات النشطة':'Active memberships'} value={String(summary?.active_memberships||0)} trend={ar?`مجمّدة: ${summary?.frozen_memberships||0}`:`Frozen: ${summary?.frozen_memberships||0}`} good/><Kpi title={ar?'الإيراد المقدم للعضويات':'Membership deferred revenue'} value={money.format(Number(summary?.deferred_membership_revenue||0))} trend="IFRS 15" good/><Kpi title={ar?'إيراد التدريب الشخصي المؤجل':'PT deferred revenue'} value={money.format(Number(summary?.pt_deferred_revenue||0))} trend={ar?'يُعترف به لكل جلسة':'Recognized per session'} good/><Kpi title={ar?'عمولات المدربين غير المسددة':'Unpaid trainer commissions'} value={money.format(Number(summary?.unpaid_trainer_commissions||0))} trend={ar?'إعداد ← مراجعة ← اعتماد':'Prepare → review → approve'} good={Number(summary?.unpaid_trainer_commissions||0)===0}/></div>
    <div className="journal-footer"><span>{message|| (ar?'RC15: العضويات والأقسام الرياضية والمرافق والحجوزات والكوفي شوب مرتبطة بالبيانات والمخزون والمحاسبة':'RC15: memberships, sports departments, facilities, bookings and gym cafe are linked to operations, inventory and accounting')}</span><button disabled={busy} onClick={load}>{busy?(ar?'جارٍ التحديث...':'Refreshing...'):(ar?'تحديث بيانات النادي':'Refresh gym operations')}</button></div>
    <div className="three-columns"><MiniStatus icon={<CalendarRange size={20}/>} title={ar?'الحصص المجدولة':'Scheduled classes'} value={String(summary?.scheduled_classes||0)} status={ar?`قائمة الانتظار: ${summary?.waitlisted_bookings||0}`:`Waitlist: ${summary?.waitlisted_bookings||0}`}/><MiniStatus icon={<UserCheck size={20}/>} title={ar?'الدخول':'Access control'} value={`${granted}/${granted+denied}`} status={ar?`مرفوض: ${denied}`:`Denied: ${denied}`}/><MiniStatus icon={<KeyRound size={20}/>} title={ar?'الخزائن المتاحة':'Available lockers'} value={String(summary?.available_lockers||0)} status={ar?`طلبات تعديل معلقة: ${summary?.pending_modifications||0}`:`Pending changes: ${summary?.pending_modifications||0}`}/></div>
    <div className="kpis rich"><Kpi title={ar?'أقسام النادي':'Gym departments'} value={String(commercial?.departments||0)} trend={ar?'سباحة، قوة، بادل وأقسام أخرى':'Swimming, strength, padel and more'} good/><Kpi title={ar?'إيراد حجز المرافق':'Facility booking revenue'} value={money.format(Number(commercial?.facility_net_revenue||0))} trend={ar?`معلق: ${commercial?.pending_paid_bookings||0}`:`Pending: ${commercial?.pending_paid_bookings||0}`} good/><Kpi title={ar?'مبيعات الكوفي شوب':'Gym cafe net sales'} value={money.format(Number(commercial?.cafe_net_sales||0))} trend={ar?`هامش: ${money.format(Number(commercial?.cafe_gross_profit||0))}`:`Margin: ${money.format(Number(commercial?.cafe_gross_profit||0))}`} good/><Kpi title={ar?'تكلفة الكوفي شوب':'Cafe food cost'} value={`${Number(commercial?.cafe_food_cost_percent||0).toFixed(1)}%`} trend={ar?'وصفات ومخزون فعلي':'Recipe and inventory backed'} good={Number(commercial?.cafe_food_cost_percent||0)<=40}/></div>
    <div className="two-columns"><Panel title={ar?'الأقسام الرياضية ومراكز الربحية':'Sports departments and profit centers'} icon={<Building2 size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'القسم':'Department',ar?'النوع':'Type',ar?'الفرع':'Branch',ar?'السعة':'Capacity',ar?'الحجز':'Booking']} rows={departments.map(r=>[r.code,ar?r.name_ar:r.name_en,r.department_type,String(r.branch_id),String(r.capacity),r.booking_required?(ar?'مطلوب':'Required'):(ar?'غير مطلوب':'Walk-in')])}/></Panel><Panel title={ar?'المرافق والملاعب':'Facilities, pools and courts'} icon={<MapPin size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'المرفق':'Facility',ar?'النوع':'Type',ar?'السعة':'Capacity',ar?'السعر/ساعة':'Hourly rate',ar?'الحالة':'Status']} rows={facilities.map(r=>[r.code,ar?r.name_ar:r.name_en,r.facility_type,String(r.capacity),money.format(Number(r.hourly_rate||0)),r.status])}/></Panel></div>
    <Panel title={ar?'حجوزات السباحة والبادل والمرافق':'Swimming, padel and facility bookings'} icon={<CalendarRange size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'المرفق':'Facility',ar?'من':'Starts',ar?'إلى':'Ends',ar?'المشاركون':'Participants',ar?'الوضع':'Access mode',ar?'القيمة':'Total',ar?'الحالة':'Status']} rows={facilityBookings.slice(0,20).map(r=>[r.number,r.facility,String(r.starts_at),String(r.ends_at),String(r.participants),r.access_mode,money.format(Number(r.total_amount||0)),r.status])}/></Panel>
    <div className="two-columns"><Panel title={ar?'منتجات كوفي شوب النادي':'Gym cafe products'} icon={<UtensilsCrossed size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'المنتج':'Product',ar?'التصنيف':'Category',ar?'السعر':'Price',ar?'سعر العضو':'Member price',ar?'السعرات':'Calories',ar?'بروتين':'Protein']} rows={cafeProducts.slice(0,20).map(r=>[r.code,ar?r.name_ar:r.name_en,r.category,money.format(Number(r.selling_price||0)),r.member_price?money.format(Number(r.member_price)):'—',r.calories??'—',r.protein_g??'—'])}/></Panel><Panel title={ar?'مبيعات وربحية الكوفي شوب':'Gym cafe sales and profitability'} icon={<UtensilsCrossed size={18}/>}><DataTable headers={[ar?'الفاتورة':'Order',ar?'التاريخ':'Date',ar?'العضو':'Member',ar?'المبيعات':'Sales',ar?'التكلفة':'Cost',ar?'الربح':'Profit',ar?'الحالة':'Status']} rows={cafeOrders.slice(0,20).map(r=>[r.number,r.order_date,r.member_id||'—',money.format(Number(r.subtotal||0)),money.format(Number(r.food_cost||0)),money.format(Number(r.gross_profit||0)),r.status])}/></Panel></div>
    <Panel title={ar?'دخول الأقسام الرياضية':'Sports department access'} icon={<UserCheck size={18}/> }><DataTable headers={[ar?'القسم':'Department',ar?'العضو':'Member',ar?'الوقت':'Time',ar?'الاتجاه':'Direction',ar?'الحالة':'Status',ar?'السبب':'Reason']} rows={departmentAccess.slice(0,20).map(r=>[String(r.department_id),String(r.member_id),String(r.occurred_at),r.direction,r.status,r.reason||'—'])}/></Panel>
    <Panel title={ar?'العقود والإيراد وفق IFRS 15':'Membership contracts and IFRS 15 revenue'} icon={<CircleDollarSign size={18}/> }><DataTable headers={[ar?'العقد':'Contract',ar?'العضو':'Member',ar?'الخطة':'Plan',ar?'الحالة':'Status',ar?'المفوتر':'Billed',ar?'المعترف':'Recognized',ar?'المقدم':'Deferred']} rows={contracts.map(r=>[r.number,r.member,r.plan,r.status,money.format(Number(r.net_amount)),money.format(Number(r.recognized)),money.format(Number(r.deferred))])}/><SummaryLine label={ar?'مطابقة الإيراد بعد الاستردادات':'Revenue reconciliation after refunds'} value={money.format(Number(revenue?.reconciliation_difference||0))}/></Panel>
    <div className="two-columns"><Panel title={ar?'الحصص وقوائم الانتظار':'Classes and waitlists'} icon={<CalendarDays size={18}/> }><DataTable headers={[ar?'الحصة':'Class',ar?'المدرب':'Trainer',ar?'الموعد':'Starts',ar?'السعة':'Capacity',ar?'محجوز':'Booked',ar?'انتظار':'Waiting']} rows={classes.slice(0,12).map(r=>[ar?r.class_name_ar:r.class_name_en,r.trainer||'—',String(r.starts_at),String(r.capacity),String(r.booked),String(r.waiting)])}/></Panel><Panel title={ar?'باقات التدريب الشخصي':'Personal training packages'} icon={<Dumbbell size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'العضو':'Member',ar?'المدرب':'Trainer',ar?'المستخدم':'Used',ar?'المتبقي':'Remaining',ar?'المؤجل':'Deferred']} rows={ptSales.slice(0,12).map(r=>[r.number,r.member,r.trainer,String(r.sessions_used),String(r.sessions_remaining),money.format(Number(r.deferred_balance))])}/></Panel></div>
    <div className="two-columns"><Panel title={ar?'سجل الدخول والخروج':'Access log'} icon={<UserCheck size={18}/> }><DataTable headers={[ar?'العضو':'Member ID',ar?'الفرع':'Branch',ar?'الوقت':'Time',ar?'الاتجاه':'Direction',ar?'الحالة':'Status',ar?'السبب':'Reason']} rows={access.slice(0,12).map(r=>[String(r.member_id),String(r.branch_id),String(r.occurred_at),r.direction,r.status,r.reason||'—'])}/></Panel><Panel title={ar?'الخزائن':'Lockers'} icon={<KeyRound size={18}/> }><DataTable headers={[ar?'الرمز':'Code',ar?'الفرع':'Branch',ar?'الحالة':'Status',ar?'نشطة':'Active']} rows={lockers.slice(0,20).map(r=>[r.code,String(r.branch_id),r.status,r.active?(ar?'نعم':'Yes'):(ar?'لا':'No')])}/></Panel></div>
    <Panel title={ar?'تعديلات العضويات ومسار الاعتماد':'Membership changes and approval workflow'} icon={<ArrowLeftRight size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'النوع':'Type',ar?'التاريخ':'Effective',ar?'التعديل':'Adjustment',ar?'الاسترداد':'Refund',ar?'الحالة':'Status']} rows={mods.slice(0,15).map(r=>[r.number,r.modification_type,r.effective_date,money.format(Number(r.adjustment_net||0)),money.format(Number(r.refund_total||0)),r.status])}/></Panel>
  </>;
}

export function RestaurantPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [posSummary,setPosSummary]=useState<any>(null);
  const [opsSummary,setOpsSummary]=useState<any>(null);
  const [menu,setMenu]=useState<any[]>([]);
  const [orders,setOrders]=useState<any[]>([]);
  const [tables,setTables]=useState<any[]>([]);
  const [reservations,setReservations]=useState<any[]>([]);
  const [shifts,setShifts]=useState<any[]>([]);
  const [tickets,setTickets]=useState<any[]>([]);
  const [settlements,setSettlements]=useState<any[]>([]);
  const [controls,setControls]=useState<any[]>([]);
  const [waste,setWaste]=useState<any[]>([]);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);

  const safeJson=async(url:string,fallback:any)=>{
    const response=await fetch(url,{headers:authHeaders()});
    if(!response.ok)throw new Error(`${ar?"تعذر تحميل بيانات المطعم":"Restaurant data could not be loaded"} (${response.status})`);
    const body=await response.json();
    return body;
  };
  const load=async()=>{
    setBusy(true);
    try{
      const [a,b,c,d,e,f,g,h,i,j]=await Promise.all([
        safeJson(`/api/v1/pos/summary?company_id=${companyId}`,null),
        safeJson(`/api/v1/restaurant/summary?company_id=${companyId}`,null),
        safeJson(`/api/v1/pos/menu?company_id=${companyId}`,[]),
        safeJson(`/api/v1/pos/orders?company_id=${companyId}`,[]),
        safeJson(`/api/v1/restaurant/tables?company_id=${companyId}`,[]),
        safeJson(`/api/v1/restaurant/reservations?company_id=${companyId}`,[]),
        safeJson(`/api/v1/restaurant/cashier-shifts?company_id=${companyId}`,[]),
        safeJson(`/api/v1/restaurant/kitchen/tickets?company_id=${companyId}`,[]),
        safeJson(`/api/v1/restaurant/settlements?company_id=${companyId}`,[]),
        Promise.all([
          safeJson(`/api/v1/restaurant/controls?company_id=${companyId}`,[]),
          safeJson(`/api/v1/restaurant/waste?company_id=${companyId}`,[]),
        ]),
      ]);
      setPosSummary(a);setOpsSummary(b);setMenu(Array.isArray(c)?c:[]);setOrders(Array.isArray(d)?d:[]);
      setTables(Array.isArray(e)?e:[]);setReservations(Array.isArray(f)?f:[]);setShifts(Array.isArray(g)?g:[]);
      setTickets(Array.isArray(h)?h:[]);setSettlements(Array.isArray(i)?i:[]);
      setControls(Array.isArray(j[0])?j[0]:[]);setWaste(Array.isArray(j[1])?j[1]:[]);
      setMessage('');
    }catch(e:any){setMessage(e?.message||String(e))}finally{setBusy(false)}
  };
  useEffect(()=>{load()},[companyId]);

  const openTickets=tickets.filter(r=>!['SERVED','CANCELLED'].includes(r.status));
  const pendingControls=controls.filter(r=>r.status==='SUBMITTED');
  const pendingWaste=waste.filter(r=>r.status==='SUBMITTED');
  const settlementVariance=settlements.filter(r=>r.status!=='APPROVED_POSTED').reduce((n,r)=>n+Math.abs(Number(r.variance||0)),0);
  const tableUtilization=tables.length?Math.round((tables.filter(r=>r.status==='OCCUPIED').length/tables.length)*100):0;

  return <>
    <div className="kpis rich">
      <Kpi title={ar?'صافي المبيعات':'Net sales'} value={money.format(Number(posSummary?.net_sales||0))} trend={ar?'قيود آلية ومخزون':'Automatic GL and inventory'} good/>
      <Kpi title={ar?'إشغال الطاولات':'Table utilization'} value={`${tableUtilization}%`} trend={`${opsSummary?.occupied_tables||0}/${opsSummary?.tables||0}`} good={tableUtilization<90}/>
      <Kpi title={ar?'طلبات المطبخ المفتوحة':'Open KDS tickets'} value={String(opsSummary?.kds_open_tickets||0)} trend={ar?'لحظي حسب المحطة':'Live by station'} good={Number(opsSummary?.kds_open_tickets||0)===0}/>
      <Kpi title={ar?'فرق تسويات المنصات':'Platform variance'} value={money.format(Number(opsSummary?.settlement_variances||settlementVariance))} trend={ar?'لا اعتماد قبل الصفر':'Zero before approval'} good={Number(opsSummary?.settlement_variances||settlementVariance)===0}/>
    </div>

    <div className="three-columns">
      <MiniStatus icon={<UtensilsCrossed size={20}/>} title={ar?'أنواع الخدمة':'Service modes'} value={ar?'محلي / سفري / توصيل':'Dine-in / takeaway / delivery'} status={ar?'مسار موحد للطلب والمطبخ':'Unified order and kitchen flow'}/>
      <MiniStatus icon={<ShieldCheck size={20}/>} title={ar?'الرقابة':'Operational controls'} value={String(pendingControls.length)} status={ar?'إلغاءات ومرتجعات بانتظار الاعتماد':'Voids and returns awaiting approval'}/>
      <MiniStatus icon={<DatabaseBackup size={20}/>} title={ar?'العمل دون اتصال':'Offline POS'} value={ar?'مفعّل':'Enabled'} status={ar?'مزامنة متكررة آمنة ومنع التكرار':'Idempotent sync and duplicate prevention'}/>
    </div>

    {message&&<div className="status-pill"><AlertTriangle size={17}/>{message}</div>}
    <div className="journal-footer">
      <span>{ar?'RC13 يربط الطلب والطاولة والمطبخ والمخزون والضريبة والتسوية والدفتر العام.':'RC13 links orders, tables, kitchen, inventory, VAT, settlements and the general ledger.'}</span>
      <button disabled={busy} onClick={load}>{busy?(ar?'جارٍ التحديث...':'Refreshing...'):(ar?'تحديث العمليات':'Refresh operations')}</button>
    </div>

    <div className="two-columns">
      <Panel title={ar?'حالة الطاولات والحجوزات':'Tables and reservations'} icon={<CalendarRange size={18}/> }>
        <div className="three-columns">
          <MiniStatus icon={<CheckCircle2 size={18}/>} title={ar?'متاحة':'Available'} value={String(opsSummary?.available_tables||0)} status={ar?'جاهزة للخدمة':'Ready for service'}/>
          <MiniStatus icon={<Users size={18}/>} title={ar?'مشغولة':'Occupied'} value={String(opsSummary?.occupied_tables||0)} status={ar?'مرتبطة بطلب مفتوح':'Linked to an open order'}/>
          <MiniStatus icon={<CalendarDays size={18}/>} title={ar?'حجوزات نشطة':'Active reservations'} value={String(opsSummary?.active_reservations||0)} status={ar?'محجوزة أو تم الجلوس':'Booked or seated'}/>
        </div>
        <DataTable headers={[ar?'الطاولة':'Table',ar?'المنطقة':'Area',ar?'السعة':'Capacity',ar?'الحالة':'Status']} rows={tables.map(r=>[r.code,r.area||'—',String(r.capacity),r.status])}/>
      </Panel>
      <Panel title={ar?'الحجوزات الحالية':'Current reservations'} icon={<Users size={18}/> }>
        <DataTable headers={[ar?'الرقم':'Number',ar?'العميل':'Customer',ar?'الطاولة':'Table',ar?'الضيوف':'Guests',ar?'الموعد':'Time',ar?'الحالة':'Status']} rows={reservations.slice(0,10).map(r=>[r.number,r.customer_name,r.table_code||'—',String(r.guest_count),String(r.reservation_at),r.status])}/>
      </Panel>
    </div>

    <div className="two-columns">
      <Panel title={ar?'شاشة المطبخ KDS':'Kitchen display system'} icon={<MonitorCog size={18}/> }>
        <DataTable headers={[ar?'التذكرة':'Ticket',ar?'الطلب':'Order',ar?'المحطة':'Station',ar?'البنود':'Lines',ar?'الحالة':'Status']} rows={tickets.slice(0,12).map(r=>[r.number,r.order_number||r.order_id,r.station_code||'—',String(r.lines?.length||0),r.status])}/>
        <SummaryLine label={ar?'التذاكر المفتوحة':'Open tickets'} value={String(openTickets.length)}/>
      </Panel>
      <Panel title={ar?'ورديات الكاشير':'Cashier shifts'} icon={<WalletCards size={18}/> }>
        <DataTable headers={[ar?'الوردية':'Shift',ar?'اليوم':'Business date',ar?'الافتتاح':'Opening',ar?'المتوقع':'Expected',ar?'المعدود':'Counted',ar?'الفرق':'Variance',ar?'الحالة':'Status']} rows={shifts.slice(0,10).map(r=>[r.number,String(r.business_date),money.format(Number(r.opening_balance)),money.format(Number(r.expected_cash)),r.counted_cash==null?'—':money.format(Number(r.counted_cash)),money.format(Number(r.variance||0)),r.status])}/>
      </Panel>
    </div>

    <Panel title={ar?'الطلبات وربحية الأصناف':'Orders and menu profitability'} icon={<ReceiptText size={18}/> }>
      <DataTable headers={[ar?'الطلب':'Order',ar?'النوع':'Type',ar?'القناة':'Channel',ar?'صافي البيع':'Net',ar?'تكلفة الطعام':'Food cost',ar?'هامش الربح':'Gross margin',ar?'المزامنة':'Sync',ar?'الحالة':'Status']} rows={orders.slice(0,15).map(r=>[r.number,r.order_type||'TAKEAWAY',r.payment_channel,money.format(Number(r.subtotal)),money.format(Number(r.food_cost)),money.format(Number(r.gross_profit)),r.sync_status||'ONLINE',r.status])}/>
      <div className="three-columns">
        <MiniStatus icon={<CircleDollarSign size={18}/>} title={ar?'نسبة تكلفة الطعام':'Food-cost ratio'} value={`${Number(posSummary?.food_cost_percent||0).toFixed(1)}%`} status={ar?'محسوبة من الوصفات':'Calculated from recipes'}/>
        <MiniStatus icon={<ShoppingCart size={18}/>} title={ar?'إجمالي الطلبات':'Total orders'} value={String(posSummary?.orders||orders.length)} status={ar?'كل قنوات البيع':'All sales channels'}/>
        <MiniStatus icon={<Clock3 size={18}/>} title={ar?'تسويات معلقة':'Pending settlements'} value={String(posSummary?.pending_settlements||0)} status={ar?'منصات التوصيل':'Delivery platforms'}/>
      </div>
    </Panel>

    <div className="two-columns">
      <Panel title={ar?'تسويات منصات التوصيل':'Delivery-platform settlements'} icon={<Landmark size={18}/> }>
        <DataTable headers={[ar?'المرجع':'Reference',ar?'المنصة':'Platform',ar?'الإجمالي':'Gross',ar?'العمولة':'Commission',ar?'المتوقع':'Expected',ar?'المستلم':'Received',ar?'الفرق':'Variance',ar?'الحالة':'Status']} rows={settlements.slice(0,10).map(r=>[r.settlement_reference,r.platform,money.format(Number(r.gross_sales)),money.format(Number(r.commission_amount)),money.format(Number(r.expected_net)),money.format(Number(r.received_net)),money.format(Number(r.variance)),r.status])}/>
      </Panel>
      <Panel title={ar?'الإلغاءات والمرتجعات':'Voids and returns'} icon={<ShieldCheck size={18}/> }>
        <DataTable headers={[ar?'الطلب':'Order',ar?'النوع':'Type',ar?'القيمة':'Amount',ar?'إعادة المخزون':'Restore stock',ar?'الحالة':'Status']} rows={controls.slice(0,10).map(r=>[r.order_number||r.order_id,r.request_type,money.format(Number(r.refund_total)),r.restore_inventory?(ar?'نعم':'Yes'):(ar?'لا':'No'),r.status])}/>
        <SummaryLine label={ar?'بانتظار اعتماد مستقل':'Awaiting independent approval'} value={String(pendingControls.length)}/>
      </Panel>
    </div>

    <div className="two-columns">
      <Panel title={ar?'الهدر وتكلفة الفاقد':'Waste and loss cost'} icon={<TrendingDown size={18}/> }>
        <DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'الصنف':'Item',ar?'الكمية':'Quantity',ar?'التكلفة':'Cost',ar?'السبب':'Reason',ar?'الحالة':'Status']} rows={waste.slice(0,10).map(r=>[r.number,String(r.waste_date),r.item_code,String(r.quantity),money.format(Number(r.total_cost)),r.reason_code,r.status])}/>
        <SummaryLine label={ar?'هدر معتمد ومرحّل':'Approved and posted waste'} value={money.format(Number(opsSummary?.approved_waste_cost||0))}/>
        <SummaryLine label={ar?'بانتظار الاعتماد':'Awaiting approval'} value={String(pendingWaste.length)}/>
      </Panel>
      <Panel title={ar?'الأصناف والوصفات':'Menu items and recipes'} icon={<BookOpenCheck size={18}/> }>
        <DataTable headers={[ar?'الكود':'Code',ar?'الصنف':'Menu item',ar?'سعر البيع':'Selling price',ar?'تكلفة الوصفة':'Recipe cost',ar?'نسبة التكلفة':'Food cost %']} rows={menu.slice(0,12).map(r=>[r.code,ar?r.name_ar:r.name_en,money.format(Number(r.selling_price)),money.format(Number(r.recipe_cost)),`${Number(r.food_cost_percent||0).toFixed(1)}%`])}/>
      </Panel>
    </div>
  </>;
}


export function ManufacturingPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [orders,setOrders]=useState<any[]>([]);const [oee,setOee]=useState<any>(null);const [advanced,setAdvanced]=useState<any>(null);const [routings,setRoutings]=useState<any[]>([]);const [mrpRuns,setMrpRuns]=useState<any[]>([]);const [costCloses,setCostCloses]=useState<any[]>([]);const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);
  const load=()=>Promise.all([
    fetch(`/api/v1/manufacturing/orders?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/manufacturing/oee?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/manufacturing/advanced/dashboard?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/manufacturing/advanced/routings?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/manufacturing/advanced/mrp-runs?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/manufacturing/advanced/cost-closes?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json())
  ]).then(([a,b,c,d,e,f])=>{setOrders(Array.isArray(a)?a:[]);setOee(b);setAdvanced(c);setRoutings(Array.isArray(d)?d:[]);setMrpRuns(Array.isArray(e)?e:[]);setCostCloses(Array.isArray(f)?f:[])}).catch(()=>{});
  useEffect(()=>{load()},[companyId]);
  async function runProduction(){setBusy(true);setMessage('');try{const [items,warehouses]=await Promise.all([fetch(`/api/v1/inventory/items?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),fetch(`/api/v1/inventory/warehouses?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json())]);let centers=await fetch(`/api/v1/manufacturing/work-centers?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json());if(!centers.length){const r=await fetch('/api/v1/manufacturing/work-centers',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,code:`LINE-${Date.now()}`,name_ar:'خط إنتاج تجريبي',name_en:'Demo Production Line',hourly_labor_rate:120,hourly_overhead_rate:80})});centers=[await r.json()];if(!r.ok)throw new Error(centers[0].detail)}let boms=await fetch(`/api/v1/manufacturing/boms?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json());if(!boms.length){const raw=items.find((x:any)=>x.code==='RAW-001'),pack=items.find((x:any)=>x.code==='PACK-001'),fg=items.find((x:any)=>x.code==='FG-001');const r=await fetch('/api/v1/manufacturing/boms',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,code:`BOM-${Date.now()}`,version:1,finished_item_id:fg.id,output_quantity:100,work_center_id:centers[0].id,standard_hours:4,lines:[{component_item_id:raw.id,quantity:120,scrap_percent:2},{component_item_id:pack.id,quantity:100,scrap_percent:1}]})});const created=await r.json();if(!r.ok)throw new Error(created.detail);boms=await fetch(`/api/v1/manufacturing/boms?company_id=${companyId}`,{headers:authHeaders()}).then(x=>x.json())}let r=await fetch('/api/v1/manufacturing/orders',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,order_date:isoDate(),bom_id:boms[0].id,warehouse_id:warehouses[0].id,planned_quantity:100})});const order=await r.json();if(!r.ok)throw new Error(order.detail);r=await fetch(`/api/v1/manufacturing/orders/${order.id}/issue-materials`,{method:'POST',headers:authHeaders()});let result=await r.json();if(!r.ok)throw new Error(result.detail);r=await fetch(`/api/v1/manufacturing/orders/${order.id}/complete`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({completion_date:isoDate(),completed_quantity:100,actual_hours:4.5,lot_number:`FG-${Date.now()}`,expiry_date:addDaysIso(180)})});result=await r.json();if(!r.ok)throw new Error(result.detail);r=await fetch(`/api/v1/manufacturing/orders/${order.id}/runs`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({run_date:isoDate(),planned_minutes:480,downtime_minutes:30,ideal_cycle_seconds:240,total_units:100,good_units:98})});const run=await r.json();if(!r.ok)throw new Error(run.detail);setMessage(ar?`اكتمل أمر الإنتاج بتكلفة ${money.format(Number(result.total_cost))} وOEE ${Number(run.oee).toFixed(1)}%.`:`Production completed at ${money.format(Number(result.total_cost))} cost and ${Number(run.oee).toFixed(1)}% OEE.`);await load()}catch(e:any){setMessage(typeof e.message==='string'?e.message:JSON.stringify(e))}finally{setBusy(false)}}
  const latestMrp=mrpRuns[0];
  return <>
    <div className="kpis rich"><Kpi title={ar?'متوسط OEE':'Average OEE'} value={`${Number(oee?.oee||0).toFixed(1)}%`} trend={ar?'من التشغيلات الفعلية':'From recorded runs'} good={Number(oee?.oee||0)>=70}/><Kpi title={ar?'عجز خطة المواد':'MRP shortage'} value={money.format(Number(advanced?.mrp_shortage||0))} trend={`${advanced?.mrp_runs||0} MRP`} good={Number(advanced?.mrp_shortage||0)===0}/><Kpi title={ar?'المسارات المعتمدة':'Approved routings'} value={String(advanced?.approved_routings||0)} trend={ar?'مسارات وإجراءات تشغيل':'Routes and operations'} good={Number(advanced?.approved_routings||0)>0}/><Kpi title={ar?'انحراف تكلفة الإنتاج':'Production cost variance'} value={money.format(Number(advanced?.total_cost_variance||0))} trend={`${advanced?.posted_cost_closes||0} ${ar?'إقفال مرحّل':'posted closes'}`} good={Number(advanced?.total_cost_variance||0)<=0}/></div>
    <div className="three-columns"><MiniStatus icon={<GitBranch size={20}/>} title={ar?'Routing':'Routing'} value={String(advanced?.approved_routings||0)} status={ar?'اعتماد مستقل وتسلسل عمليات':'Independent approval and operation sequence'}/><MiniStatus icon={<Boxes size={20}/>} title={ar?'WIP والعمليات':'WIP & operations'} value={`${Number(advanced?.open_operations||0)}/${Number(advanced?.operations||0)}`} status={ar?'مفتوح / إجمالي':'Open / total'}/><MiniStatus icon={<AlertTriangle size={20}/>} title={ar?'الهالك غير الطبيعي':'Abnormal scrap'} value={money.format(Number(advanced?.abnormal_scrap_cost||0))} status={`${Number(advanced?.scrap_quantity||0)} ${ar?'وحدة مسجلة':'recorded units'}`}/></div>
    <div className="journal-footer"><span>{message|| (ar?'MRP والمسارات وWIP وإقفال التكلفة والانحرافات مرتبطة بقاعدة البيانات والدفتر العام.':'MRP, routings, WIP, cost close and variances are database and ledger backed.')}</span>{DEMO_ACTIONS_ENABLED&&<button disabled={busy} onClick={runProduction}>{busy?(ar?'جارٍ التصنيع...':'Producing...'):(ar?'تنفيذ أمر إنتاج تجريبي':'Run production demo')}</button>}</div>
    <div className="two-columns"><Panel title={ar?'آخر خطة احتياجات مواد':'Latest material requirements plan'} icon={<Boxes size={18}/> }><DataTable headers={[ar?'الخطة':'Plan',ar?'الأفق':'Horizon',ar?'الطلب':'Demand',ar?'المتاح':'On hand',ar?'العجز':'Shortage',ar?'الحالة':'Status']} rows={latestMrp?[[latestMrp.code,latestMrp.horizon_end,String(latestMrp.gross_demand),String(latestMrp.total_on_hand),String(latestMrp.total_shortage),latestMrp.status]]:[]}/></Panel><Panel title={ar?'مسارات التشغيل':'Manufacturing routings'} icon={<GitBranch size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'المنتج':'Product',ar?'الإصدار':'Version',ar?'العمليات':'Operations',ar?'الحالة':'Status']} rows={routings.map(r=>[r.code,r.finished_item_code,String(r.version),String(r.operations?.length||0),r.status])}/></Panel></div>
    <Panel title={ar?'إقفال التكلفة والانحرافات':'Production cost close and variances'} icon={<FileSpreadsheet size={18}/> }><DataTable headers={[ar?'الأمر':'Order',ar?'المعياري':'Standard',ar?'الفعلي':'Actual',ar?'انحراف المواد':'Material variance',ar?'انحراف العمل':'Labor variance',ar?'انحراف الصناعي':'Overhead variance',ar?'الإجمالي':'Total variance',ar?'الحالة':'Status']} rows={costCloses.map(r=>[r.production_order_number,money.format(Number(r.standard_total_cost)),money.format(Number(r.actual_total_cost)),money.format(Number(r.material_price_variance)+Number(r.material_usage_variance)),money.format(Number(r.labor_rate_variance)+Number(r.labor_efficiency_variance)),money.format(Number(r.overhead_spending_variance)+Number(r.overhead_volume_variance)),money.format(Number(r.total_variance)),r.status])}/></Panel>
    <Panel title={ar?'أوامر الإنتاج والتكاليف الفعلية':'Production orders and actual costs'} icon={<Factory size={18}/> }><DataTable headers={[ar?'الأمر':'Order',ar?'المنتج':'Product',ar?'المخطط':'Planned',ar?'المنجز':'Completed',ar?'مواد':'Material',ar?'عمالة':'Labor',ar?'صناعي':'Overhead',ar?'الإجمالي':'Total',ar?'الحالة':'Status']} rows={orders.map(r=>[r.number,r.finished_item,String(r.planned_quantity),String(r.completed_quantity),money.format(Number(r.material_cost)),money.format(Number(r.labor_cost)),money.format(Number(r.overhead_cost)),money.format(Number(r.total_cost)),r.status])}/></Panel>
    <Panel title={ar?'سجل OEE':'OEE history'} icon={<Activity size={18}/> }><DataTable headers={[ar?'التاريخ':'Date',ar?'التوافر':'Availability',ar?'الأداء':'Performance',ar?'الجودة':'Quality','OEE']} rows={(oee?.history||[]).map((r:any)=>[r.date,`${Number(r.availability).toFixed(1)}%`,`${Number(r.performance).toFixed(1)}%`,`${Number(r.quality).toFixed(1)}%`,`${Number(r.oee).toFixed(1)}%`])}/></Panel>
  </>;
}

export function QualityPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [summary,setSummary]=useState<any>(null);const [qms,setQms]=useState<any>(null);const [inspections,setInspections]=useState<any[]>([]);const [ncrs,setNcrs]=useState<any[]>([]);const [objectives,setObjectives]=useState<any[]>([]);const [plans,setPlans]=useState<any[]>([]);const [actions,setActions]=useState<any[]>([]);const [complaints,setComplaints]=useState<any[]>([]);const [suppliers,setSuppliers]=useState<any[]>([]);const [reviews,setReviews]=useState<any[]>([]);const [auditIntegrity,setAuditIntegrity]=useState<any>(null);const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);
  const load=()=>Promise.all([
    fetch(`/api/v1/quality/summary?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/qms/dashboard?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/quality/inspections?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/quality/ncrs?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/qms/objectives?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/qms/inspection-plans?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/qms/actions?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/qms/complaints?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/qms/supplier-evaluations?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/qms/management-reviews?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()),
    fetch(`/api/v1/audit-log/integrity?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.ok?r.json():null),
  ]).then(([a,b,c,d,e,f,g,h,i,j,k])=>{setSummary(a);setQms(b);setInspections(Array.isArray(c)?c:[]);setNcrs(Array.isArray(d)?d:[]);setObjectives(Array.isArray(e)?e:[]);setPlans(Array.isArray(f)?f:[]);setActions(Array.isArray(g)?g:[]);setComplaints(Array.isArray(h)?h:[]);setSuppliers(Array.isArray(i)?i:[]);setReviews(Array.isArray(j)?j:[]);setAuditIntegrity(k)}).catch(()=>{});
  useEffect(()=>{load()},[companyId]);
  async function inspect(){setBusy(true);setMessage('');try{const items=await fetch(`/api/v1/inventory/items?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json());const fg=items.find((x:any)=>x.code==='FG-001')||items[0];const orders=await fetch(`/api/v1/manufacturing/orders?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()).catch(()=>[]);let r=await fetch('/api/v1/quality/inspections',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,inspection_date:isoDate(),inspection_type:'FINAL',reference_type:'PRODUCTION_ORDER',reference_id:orders[0]?.id||1,item_id:fg?.id,lot_number:`LOT-${Date.now()}`,inspected_quantity:100,accepted_quantity:99,rejected_quantity:1,notes:'Controlled final inspection',severity:'MEDIUM'})});const result=await r.json();if(!r.ok)throw new Error(result.detail);if(result.ncr){r=await fetch(`/api/v1/quality/ncrs/${result.ncr.id}`,{method:'PATCH',headers:jsonHeaders(),body:JSON.stringify({root_cause:'Packaging seal variation',corrective_action:'Calibrate sealing station and verify next batch',due_date:addDaysIso(7),status:'IN_PROGRESS'})});if(!r.ok)throw new Error((await r.json()).detail)}setMessage(ar?'تم تسجيل الفحص وإنشاء عدم مطابقة وإجراء تصحيحي.':'Inspection, NCR and corrective action were recorded.');await load()}catch(e:any){setMessage(typeof e.message==='string'?e.message:JSON.stringify(e))}finally{setBusy(false)}}
  async function bootstrapQms(){setBusy(true);setMessage('');try{
    const items=await fetch(`/api/v1/inventory/items?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json());const parties=await fetch(`/api/v1/subledgers/parties?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.json()).catch(()=>[]);const item=items[0];const supplier=parties.find((p:any)=>p.party_type==='SUPPLIER');const customer=parties.find((p:any)=>p.party_type==='CUSTOMER');const stamp=Date.now();
    const requests:[string,any][]=[
      ['/api/v1/qms/objectives',{company_id:companyId,code:`QO-${stamp}`,name_ar:'خفض نسبة الرفض',name_en:'Reduce rejection rate',metric_name:'Rejection Rate',unit:'PERCENT',baseline_value:3,target_value:1,current_value:2,frequency:'MONTHLY',effective_from:'2026-01-01',effective_to:'2026-12-31'}],
      ['/api/v1/qms/inspection-plans',{company_id:companyId,code:`IP-${stamp}`,name_ar:'خطة فحص المنتج النهائي',name_en:'Final product inspection plan',item_id:item?.id,inspection_stage:'FINAL',sampling_method:'FIXED',sample_size:20,acceptance_number:0,rejection_number:1,specification:'Approved product specification',test_method:'Visual and dimensional checks'}],
      ['/api/v1/qms/actions',{company_id:companyId,action_type:'CORRECTIVE',source_type:'INTERNAL_AUDIT',source_id:1,title:'إغلاق سبب تكرار عيب التعبئة',description:'Eliminate repeated packaging defect',root_cause_method:'5_WHY',root_cause:'Sealing temperature drift',owner_user_id:1,due_date:'2026-12-31'}],
      ['/api/v1/qms/complaints',{company_id:companyId,received_date:isoDate(),customer_id:customer?.id,item_id:item?.id,lot_number:`LOT-${stamp}`,channel:'DIRECT',severity:'MEDIUM',description:'Seal integrity complaint',immediate_containment:'Quarantine related lot',owner_user_id:1,due_date:addDaysIso(14)}],
      ['/api/v1/qms/management-reviews',{company_id:companyId,review_date:isoDate(),scope:'Enterprise QMS and ISO 9001 controls',inputs_summary:'Objectives, audits, complaints, supplier performance and process KPIs',decisions:'Increase final inspection sampling for high-risk products',improvement_opportunities:'Automate COA and lot release',resource_needs:'One calibrated seal tester'}],
    ];
    if(supplier?.id)requests.push(['/api/v1/qms/supplier-evaluations',{company_id:companyId,supplier_id:supplier.id,period_start:currentMonthBounds().start,period_end:currentMonthBounds().end,quality_score:92,delivery_score:88,documentation_score:95,notes:'Approved supplier'}]);
    for(const [url,body] of requests){const r=await fetch(url,{method:'POST',headers:jsonHeaders(),body:JSON.stringify(body)});if(!r.ok){const e=await r.json();throw new Error(e.detail||url)}}
    setMessage(ar?'تم إنشاء حزمة QMS مترابطة: هدف جودة، خطة فحص، CAPA، شكوى، تقييم مورد ومراجعة إدارة.':'Integrated QMS package created: objective, inspection plan, CAPA, complaint, supplier evaluation and management review.');await load();
  }catch(e:any){setMessage(typeof e.message==='string'?e.message:JSON.stringify(e))}finally{setBusy(false)}}
  return <>
    <div className="kpis rich"><Kpi title={ar?'تحقيق أهداف الجودة':'Quality objectives achieved'} value={`${Number(qms?.objective_achievement_rate||0).toFixed(1)}%`} trend={`${qms?.objectives_achieved||0}/${qms?.active_objectives||0}`} good={Number(qms?.objective_achievement_rate||0)>=80}/><Kpi title={ar?'نسبة قبول الفحص':'Inspection acceptance'} value={`${Number(summary?.acceptance_rate||0).toFixed(1)}%`} trend={ar?'من الكميات المفحوصة':'Quantity based'} good={Number(summary?.acceptance_rate||0)>=95}/><Kpi title={ar?'CAPA متأخر':'Overdue CAPA'} value={String(qms?.overdue_actions||0)} trend={ar?'إجراءات تتطلب تصعيدًا':'Actions requiring escalation'} good={Number(qms?.overdue_actions||0)===0}/><Kpi title={ar?'سلامة سجل المراجعة':'Audit chain integrity'} value={auditIntegrity?.status||'—'} trend={`${auditIntegrity?.verified_records||0} hashed`} good={auditIntegrity?.status==='VALID'}/></div>
    <div className="journal-footer"><span>{message|| (ar?'نظام إدارة جودة مؤسسي يدعم جوهر ISO 9001 مع ضوابط واعتمادات وسجل مراجعة.':'Enterprise QMS supporting the ISO 9001 core with controls, approvals and audit trail.')}</span><div style={{display:'flex',gap:8}}><button disabled={busy} onClick={inspect}>{ar?'تسجيل فحص':'Record inspection'}</button><button disabled={busy} onClick={bootstrapQms}>{busy?(ar?'جارٍ التنفيذ...':'Running...'):(ar?'إنشاء حزمة QMS':'Create QMS package')}</button></div></div>
    <div className="three-columns"><MiniStatus icon={<CheckCircle2 size={20}/>} title={ar?'جوهر ISO 9001':'ISO 9001 core'} value="8/8" status={ar?'أهداف، خطط، CAPA، شكاوى، موردون، مراجعة إدارة، وثائق وتدقيق':'Objectives, plans, CAPA, complaints, suppliers, management review, documents and audit'}/><MiniStatus icon={<ClipboardCheck size={20}/>} title={ar?'خطط الفحص':'Inspection plans'} value={String(plans.length)} status={ar?'عينات وقبول ورفض ومواصفات':'Sampling, acceptance, rejection and specifications'}/><MiniStatus icon={<ShieldCheck size={20}/>} title={ar?'متوسط جودة الموردين':'Supplier quality average'} value={`${Number(qms?.supplier_quality_average||0).toFixed(1)}%`} status={ar?'تقييم 50% جودة، 30% تسليم، 20% مستندات':'50% quality, 30% delivery, 20% documentation'}/></div>
    <div className="two-columns"><Panel title={ar?'أهداف الجودة':'Quality objectives'} icon={<TrendingUp size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'الهدف':'Objective',ar?'الحالي':'Current',ar?'المستهدف':'Target',ar?'الدورية':'Frequency',ar?'معتمد':'Approved']} rows={objectives.map(r=>[r.code,ar?r.name_ar:r.name_en,String(r.current_value),String(r.target_value),r.frequency,r.approved?(ar?'نعم':'Yes'):(ar?'لا':'No')])}/></Panel><Panel title={ar?'خطط الفحص والمواصفات':'Inspection plans & specifications'} icon={<FileCheck2 size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'الخطة':'Plan',ar?'المرحلة':'Stage',ar?'العينة':'Sample',ar?'قبول/رفض':'Ac/Re',ar?'معتمد':'Approved']} rows={plans.map(r=>[r.code,ar?r.name_ar:r.name_en,r.inspection_stage,String(r.sample_size),`${r.acceptance_number}/${r.rejection_number}`,r.approved?(ar?'نعم':'Yes'):(ar?'لا':'No')])}/></Panel></div>
    <div className="two-columns"><Panel title={ar?'الإجراءات التصحيحية والوقائية CAPA':'Corrective & preventive actions'} icon={<AlertTriangle size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'العنوان':'Title',ar?'المصدر':'Source',ar?'الاستحقاق':'Due',ar?'الحالة':'Status',ar?'الفعالية':'Effectiveness']} rows={actions.map(r=>[r.number,r.title,r.source_type,String(r.due_date),r.status,r.effectiveness_result||'—'])}/></Panel><Panel title={ar?'شكاوى العملاء والجودة':'Customer quality complaints'} icon={<Users size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'العميل':'Customer',ar?'الصنف':'Item',ar?'الخطورة':'Severity',ar?'الحالة':'Status']} rows={complaints.map(r=>[r.number,String(r.received_date),r.customer||'—',r.item||'—',r.severity,r.status])}/></Panel></div>
    <div className="two-columns"><Panel title={ar?'تقييم جودة الموردين':'Supplier quality evaluation'} icon={<ShoppingCart size={18}/> }><DataTable headers={[ar?'المورد':'Supplier',ar?'الجودة':'Quality',ar?'التسليم':'Delivery',ar?'المستندات':'Documents',ar?'الإجمالي':'Overall',ar?'الفئة':'Class']} rows={suppliers.map(r=>[r.supplier,`${r.quality_score}%`,`${r.delivery_score}%`,`${r.documentation_score}%`,`${r.overall_score}%`,r.classification])}/></Panel><Panel title={ar?'مراجعة الإدارة للجودة':'Quality management review'} icon={<BookOpenCheck size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'النطاق':'Scope',ar?'الحالة':'Status',ar?'معتمد':'Approved']} rows={reviews.map(r=>[r.number,String(r.review_date),r.scope,r.status,r.approved?(ar?'نعم':'Yes'):(ar?'لا':'No')])}/></Panel></div>
    <Panel title={ar?'سجل الفحوص وعدم المطابقة':'Inspection and nonconformity register'} icon={<ClipboardCheck size={18}/> }><DataTable headers={[ar?'المرجع':'Reference',ar?'التاريخ':'Date',ar?'النوع/الخطورة':'Type / Severity',ar?'الوصف/الصنف':'Description / Item',ar?'النتيجة/الحالة':'Result / Status']} rows={[...inspections.slice(0,8).map(r=>[r.number,r.inspection_date,r.inspection_type,r.item_code||'—',r.result]),...ncrs.slice(0,8).map(r=>[r.number,'—',r.severity,r.description,r.status])]}/></Panel>
  </>;
}

export function FoodSafetyPage({ ar, companyId }: { ar: boolean; companyId: number }) {
  const [dashboard,setDashboard]=useState<any>(null);
  const [plans,setPlans]=useState<any[]>([]);
  const [coas,setCoas]=useState<any[]>([]);
  const [recalls,setRecalls]=useState<any[]>([]);
  const load=()=>Promise.all([
    fetch(`/api/v1/food-safety/dashboard?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.ok?r.json():null),
    fetch(`/api/v1/food-safety/haccp-plans?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.ok?r.json():[]),
    fetch(`/api/v1/food-safety/coa?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.ok?r.json():[]),
    fetch(`/api/v1/food-safety/recalls?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.ok?r.json():[]),
  ]).then(([d,p,c,r])=>{setDashboard(d);setPlans(Array.isArray(p)?p:[]);setCoas(Array.isArray(c)?c:[]);setRecalls(Array.isArray(r)?r:[])}).catch(()=>{});
  useEffect(()=>{load()},[companyId]);
  return <>
    <div className="kpis rich">
      <Kpi title={ar?'خطط HACCP المعتمدة':'Approved HACCP plans'} value={String(dashboard?.approved_haccp_plans||0)} trend={ar?'تحليل مخاطر ونقاط تحكم حرجة':'Hazard analysis and CCP control'} good/>
      <Kpi title={ar?'انحرافات CCP المفتوحة':'Open CCP deviations'} value={String(dashboard?.open_ccp_deviations||0)} trend={ar?'ترتبط تلقائيًا بـ CAPA':'Automatically linked to CAPA'} good={!dashboard?.open_ccp_deviations}/>
      <Kpi title={ar?'شهادات التحليل المفرج عنها':'Released COA'} value={String(dashboard?.released_coa||0)} trend={ar?'إفراج مستقل عن التشغيلات':'Independent lot release'} good/>
      <Kpi title={ar?'استدعاءات نشطة':'Active recalls'} value={String(dashboard?.active_recalls||0)} trend={ar?'تتبع الفاعلية والاسترداد':'Recovery effectiveness tracking'} good={!dashboard?.active_recalls}/>
    </div>
    <div className="three-columns">
      <MiniStatus icon={<ShieldCheck size={20}/>} title={ar?'ISO 22000 / HACCP':'ISO 22000 / HACCP'} value={ar?'نواة فعالة':'Active core'} status={ar?'المخاطر، CCP، المراقبة والتحقق':'Hazards, CCPs, monitoring and verification'}/>
      <MiniStatus icon={<FileCheck2 size={20}/>} title={ar?'إفراج الجودة':'Quality release'} value={String(coas.filter(x=>x.status==='RELEASED').length)} status={ar?'COA مع فصل المُعد عن المعتمد':'COA maker-checker release'}/>
      <MiniStatus icon={<AlertTriangle size={20}/>} title={ar?'الاستدعاء والتتبع':'Recall & traceability'} value={String(recalls.length)} status={ar?'الفئة، اللوط، التوزيع والاسترداد':'Class, lot, distribution and recovery'}/>
    </div>
    <Panel title={ar?'خطط HACCP':'HACCP plans'} icon={<ShieldCheck size={18}/> }>
      <DataTable headers={[ar?'الكود':'Code',ar?'الخطة':'Plan',ar?'المنتج':'Item',ar?'الإصدار':'Version',ar?'المخاطر':'Hazards','CCP',ar?'الحالة':'Status']} rows={plans.map(r=>[r.code,ar?r.name_ar:r.name_en,r.item||'—',String(r.version),String(r.hazards),String(r.ccps),r.status])}/>
    </Panel>
    <div className="two-columns">
      <Panel title={ar?'شهادات التحليل':'Certificates of Analysis'} icon={<FileText size={18}/> }>
        <DataTable headers={[ar?'الرقم':'Number',ar?'الصنف':'Item',ar?'اللوط':'Lot',ar?'النتيجة':'Conclusion',ar?'الحالة':'Status']} rows={coas.map(r=>[r.number,r.item,r.lot_number,r.conclusion,r.status])}/>
      </Panel>
      <Panel title={ar?'سجل الاستدعاء':'Product recalls'} icon={<AlertTriangle size={18}/> }>
        <DataTable headers={[ar?'الرقم':'Number',ar?'الفئة':'Class',ar?'اللوط':'Lot',ar?'الاسترداد %':'Recovery %',ar?'الحالة':'Status']} rows={recalls.map(r=>[r.number,r.class,r.lot_number,String(r.effectiveness_percent),r.status])}/>
      </Panel>
    </div>
  </>;
}

export function HrPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [payrollSummary,setPayrollSummary]=useState<any>(null);
  const [runs,setRuns]=useState<any[]>([]);
  const [hr,setHr]=useState<any>(null);
  const [advanced,setAdvanced]=useState<any>(null);
  const [attendance,setAttendance]=useState<any[]>([]);
  const [contracts,setContracts]=useState<any[]>([]);
  const [overtime,setOvertime]=useState<any[]>([]);
  const [adjustments,setAdjustments]=useState<any[]>([]);
  const [wps,setWps]=useState<any[]>([]);
  const [valuations,setValuations]=useState<any[]>([]);
  const [message,setMessage]=useState('');

  const safeJson=(url:string, fallback:any)=>fetch(url,{headers:authHeaders()}).then(async r=>r.ok?await r.json():fallback).catch(()=>fallback);
  const load=()=>Promise.all([
    safeJson(`/api/v1/payroll/summary?company_id=${companyId}`,null),
    safeJson(`/api/v1/payroll/runs?company_id=${companyId}`,[]),
    safeJson(`/api/v1/hr/summary?company_id=${companyId}`,null),
    safeJson(`/api/v1/hr-payroll/summary?company_id=${companyId}`,null),
    safeJson(`/api/v1/hr/attendance?company_id=${companyId}&start_date=${currentMonthBounds().start}&end_date=${currentMonthBounds().end}`,[]),
    safeJson(`/api/v1/hr-payroll/contracts?company_id=${companyId}`,[]),
    safeJson(`/api/v1/hr-payroll/overtime?company_id=${companyId}`,[]),
    safeJson(`/api/v1/hr-payroll/adjustments?company_id=${companyId}`,[]),
    safeJson(`/api/v1/hr-payroll/wps?company_id=${companyId}`,[]),
    safeJson(`/api/v1/hr-payroll/benefits/valuations?company_id=${companyId}`,[]),
  ]).then(([a,b,c,d,e,f,g,h,i,j])=>{
    setPayrollSummary(a);setRuns(Array.isArray(b)?b:[]);setHr(c);setAdvanced(d);
    setAttendance(Array.isArray(e)?e:[]);setContracts(Array.isArray(f)?f:[]);
    setOvertime(Array.isArray(g)?g:[]);setAdjustments(Array.isArray(h)?h:[]);
    setWps(Array.isArray(i)?i:[]);setValuations(Array.isArray(j)?j:[]);
    setMessage('');
  }).catch((e:any)=>setMessage(e?.message||String(e)));
  useEffect(()=>{load()},[companyId]);

  const latestValuation=valuations[0];
  const pendingPayroll=runs.filter(r=>!['PAID','CANCELLED'].includes(r.status)).length;
  const attendanceIssues=attendance.filter(a=>a.status==='LATE'||a.status==='ABSENT').length;
  const approvedOvertime=overtime.filter(r=>r.status==='APPROVED').reduce((n,r)=>n+Number(r.approved_minutes||0),0);
  return <>
    <div className="kpis rich">
      <Kpi title={ar?'الموظفون النشطون':'Active employees'} value={String(hr?.active_employees||payrollSummary?.active_employees||0)} trend={ar?'ملفات مشفرة وصلاحيات دقيقة':'Encrypted profiles and granular access'} good/>
      <Kpi title={ar?'صافي آخر مسير':'Latest net payroll'} value={money.format(Number(payrollSummary?.net||0))} trend={payrollSummary?.latest_status||'—'} good={payrollSummary?.latest_status==='PAID'}/>
      <Kpi title={ar?'اكتمال الحضور':'Attendance completeness'} value={`${Number(payrollSummary?.attendance_completeness_percent||0).toFixed(1)}%`} trend={ar?'بوابة قبل الاعتماد':'Pre-approval control gate'} good={Number(payrollSummary?.attendance_completeness_percent||0)>=95}/>
      <Kpi title={ar?'التزام المنافع IAS 19':'IAS 19 benefit obligation'} value={money.format(Number(latestValuation?.total_dbo||0))} trend={latestValuation?.status|| (ar?'لا توجد قيمة':'No valuation')} good={latestValuation?.status==='APPROVED_POSTED'}/>
    </div>
    <div className="three-columns">
      <MiniStatus icon={<ShieldCheck size={20}/>} title={ar?'سير الرواتب الرقابي':'Controlled payroll workflow'} value={payrollSummary?.strict_workflow?(ar?'صارم':'Strict'):(ar?'توافقي':'Compatible')} status={ar?'احتساب ← مراجعة ← اعتماد وترحيل ← WPS ← صرف':'Calculate → review → approve/post → WPS → pay'}/>
      <MiniStatus icon={<FileCheck2 size={20}/>} title={ar?'العقود المعتمدة':'Employee contracts'} value={String(contracts.filter(r=>r.status==='ACTIVE').length)} status={ar?'فصل المُعد عن المعتمد':'Maker-checker approval'}/>
      <MiniStatus icon={<Clock3 size={20}/>} title={ar?'الإضافي المعتمد':'Approved overtime'} value={`${approvedOvertime} min`} status={ar?'يدخل آليًا في المسير':'Automatically included in payroll'}/>
    </div>
    {message&&<div className="status-pill"><AlertTriangle size={17}/>{message}</div>}
    <div className="two-columns">
      <Panel title={ar?'مسيرات الرواتب':'Payroll runs'} icon={<Users size={18}/> }>
        <DataTable headers={[ar?'الفترة':'Period',ar?'الموظفون':'Employees',ar?'الإجمالي':'Gross',ar?'الخصومات':'Deductions',ar?'الصافي':'Net',ar?'اكتمال الحضور':'Attendance',ar?'الحالة':'Status']} rows={runs.map(r=>[`${r.period_year}-${String(r.period_month).padStart(2,'0')}`,String(r.employees),money.format(Number(r.total_gross)),money.format(Number(r.total_deductions)),money.format(Number(r.total_net)),`${Number(r.attendance_completeness_percent||0).toFixed(1)}%`,r.status])}/>
      </Panel>
      <Panel title={ar?'دفعات حماية الأجور WPS':'WPS wage-protection batches'} icon={<FileSpreadsheet size={18}/> }>
        <DataTable headers={[ar?'الدفعة':'Batch',ar?'تاريخ التنفيذ':'Execution date',ar?'الموظفون':'Employees',ar?'القيمة':'Amount',ar?'الحالة':'Status']} rows={wps.map(r=>[r.batch_number,String(r.execution_date),String(r.line_count),money.format(Number(r.total_amount)),r.status])}/>
      </Panel>
    </div>
    <div className="two-columns">
      <Panel title={ar?'العقود الوظيفية':'Employment contracts'} icon={<FileText size={18}/> }>
        <DataTable headers={[ar?'العقد':'Contract',ar?'الموظف':'Employee',ar?'النوع':'Type',ar?'البداية':'Start',ar?'النهاية':'End',ar?'الحالة':'Status']} rows={contracts.map(r=>[r.contract_number,ar?r.employee_name_ar:r.employee_name_en,r.contract_type,String(r.start_date),r.end_date?String(r.end_date):'—',r.status])}/>
      </Panel>
      <Panel title={ar?'الإضافي والتعديلات':'Overtime and payroll adjustments'} icon={<Clock3 size={18}/> }>
        <DataTable headers={[ar?'المرجع':'Reference',ar?'الموظف':'Employee',ar?'الفترة/التاريخ':'Period / Date',ar?'القيمة':'Value',ar?'النوع':'Type',ar?'الحالة':'Status']} rows={[
          ...overtime.slice(0,6).map(r=>[r.number,r.employee,String(r.work_date),`${r.approved_minutes} min`,ar?'إضافي':'Overtime',r.status]),
          ...adjustments.slice(0,6).map(r=>[r.number,r.employee,r.period,money.format(Number(r.amount)),r.earning?(ar?'استحقاق':'Earning'):(ar?'استقطاع':'Deduction'),r.status])
        ]}/>
      </Panel>
    </div>
    <div className="two-columns">
      <Panel title={ar?'الحضور وتأثيره على المسير':'Attendance impact on payroll'} icon={<MapPin size={18}/> }>
        <div className="three-columns">
          <MiniStatus icon={<UserCheck size={18}/>} title={ar?'سجلات الشهر':'Monthly records'} value={String(attendance.length)} status={ar?'مصدر ووقت وموقع':'Source, time and location'}/>
          <MiniStatus icon={<AlertTriangle size={18}/>} title={ar?'تأخير/غياب':'Late / absent'} value={String(attendanceIssues)} status={ar?'خصم حسب السياسة':'Policy-driven deduction'}/>
          <MiniStatus icon={<CheckCircle2 size={18}/>} title={ar?'مسيرات معلقة':'Open payroll runs'} value={String(pendingPayroll)} status={ar?'لا صرف قبل WPS مقبول':'No payment before accepted WPS'}/>
        </div>
        <DataTable headers={[ar?'التاريخ':'Date',ar?'الموظف':'Employee',ar?'الحالة':'Status',ar?'التأخير':'Late',ar?'الإضافي':'Overtime',ar?'المصدر':'Source']} rows={attendance.slice(0,8).map(a=>[String(a.work_date),String(a.employee_id),a.status,`${a.late_minutes}m`,`${a.overtime_minutes}m`,a.source])}/>
      </Panel>
      <Panel title={ar?'تقييم منافع الموظفين':'Employee-benefit valuations'} icon={<BadgeDollarSign size={18}/> }>
        <DataTable headers={[ar?'تاريخ التقييم':'Valuation date',ar?'الإصدار':'Version',ar?'الموظفون':'Employees',ar?'DBO':'DBO',ar?'تكلفة الخدمة':'Service cost',ar?'الفائدة':'Interest',ar?'الحالة':'Status']} rows={valuations.map(r=>[String(r.valuation_date),String(r.version),String(r.employee_count),money.format(Number(r.total_dbo)),money.format(Number(r.current_service_cost)),money.format(Number(r.interest_cost)),r.status])}/>
        <div className="journal-footer"><span>{ar?'محرك دعم إداري بتقديرات موثقة؛ لا يستبدل تقرير الخبير الاكتواري المستقل.':'Management-support engine with documented assumptions; it does not replace an independent actuarial report.'}</span><button onClick={load}>{ar?'تحديث البيانات':'Refresh data'}</button></div>
      </Panel>
    </div>
    <div className="three-columns">
      <MiniStatus icon={<FileCheck2 size={20}/>} title={ar?'العقود':'Contracts'} value={String(advanced?.contracts||0)} status={ar?'محفوظة وقابلة للتدقيق':'Persistent and auditable'}/>
      <MiniStatus icon={<Clock3 size={20}/>} title={ar?'إضافي بانتظار القرار':'Pending overtime'} value={String(advanced?.pending_overtime||0)} status={ar?'اعتماد مستقل':'Independent approval'}/>
      <MiniStatus icon={<WalletCards size={20}/>} title={ar?'تعديلات معتمدة':'Approved adjustments'} value={String(advanced?.approved_adjustments||0)} status={ar?'تدخل مرة واحدة في المسير':'Applied once to payroll'}/>
    </div>
  </>;
}
