import {useEffect, useRef, useState} from 'react';
import {Calendar, Download, FileBarChart, ImagePlus, Landmark, Package, Percent, Printer, ShoppingCart, TrendingUp, Users} from 'lucide-react';
import {apiFetch} from '../api/client';
import {ComparativeStatementTable} from './comparativeStatementTable';
import {
  buildStatementRows, comparisonPeriods, currentYearStart, fetchComparativeStatements,
  formatStatementAmount, formatVariancePercent, localYmd, statementTitle,
  type ComparativeStatementRow, type ComparisonPeriods, type FinancialStatementKey,
  type StatementRowKind,
} from './financialStatementEngine';
import {printBusinessDocument} from './printDocument';
import {ReportBuilderTab} from './reportBuilderTab';
import {Kpi, Panel, fmt} from './ui';

async function json(url:string,init?:RequestInit){
  const response=await apiFetch(url,init);const payload=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof payload.detail==='string'?payload.detail:JSON.stringify(payload.detail||payload));
  return payload;
}

const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const ghost={padding:'8px 14px',borderRadius:9,border:'1px solid var(--border)',background:'transparent',color:'var(--text)',cursor:'pointer',fontWeight:600} as const;
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const th={textAlign:'start',padding:'9px 12px',borderBottom:'2px solid var(--border)',fontWeight:700,fontSize:13} as const;
const td={padding:'8px 12px',borderBottom:'1px solid var(--border)',fontSize:13} as const;

const statusText=(status:any,ar:boolean)=>{
  const labels:Record<string,[string,string]>={
    DRAFT:['مسودة','Draft'],PENDING_APPROVAL:['بانتظار الاعتماد','Pending approval'],
    APPROVED:['معتمد','Approved'],POSTED:['مرحّل','Posted'],PAID:['مدفوع','Paid'],
    PARTIALLY_PAID:['مدفوع جزئيًا','Partially paid'],CANCELLED:['ملغي','Cancelled'],
    REVERSED:['معكوس','Reversed'],ACCRUED:['مستحق','Accrued'],ELIGIBLE:['مؤهل','Eligible'],
  };
  return labels[String(status||'').toUpperCase()]?.[ar?0:1]||status||'—';
};

type Row=Record<string,any>;
type Report={key:string;cat:string;ar:string;en:string};
type PeriodPreset='month'|'quarter'|'year'|'custom';

const CATEGORIES:[string,string,string][]=[
  ['financial','المالية','Financial'],['sales','المبيعات','Sales'],['purchases','المشتريات','Purchases'],
  ['inventory','المخزون','Inventory'],['receivables','الذمم','Receivables & Payables'],['commissions','العمولات','Commissions'],
];
const REPORTS:Report[]=[
  {key:'income',cat:'financial',ar:'قائمة الدخل',en:'Income Statement'},
  {key:'balance',cat:'financial',ar:'قائمة المركز المالي',en:'Balance Sheet'},
  {key:'cashflow',cat:'financial',ar:'قائمة التدفقات النقدية',en:'Cash Flow Statement'},
  {key:'trial',cat:'financial',ar:'ميزان المراجعة',en:'Trial Balance'},
  {key:'sales_invoices',cat:'sales',ar:'فواتير البيع',en:'Sales Invoices'},
  {key:'dgtera_sales',cat:'sales',ar:'مبيعات DGTERA ومقارنة الفترات',en:'DGTERA Sales & Period Comparison'},
  {key:'receipts',cat:'sales',ar:'سندات القبض',en:'Receipts'},
  {key:'purchase_invoices',cat:'purchases',ar:'فواتير الشراء',en:'Purchase Invoices'},
  {key:'payments',cat:'purchases',ar:'سندات الصرف',en:'Payments'},
  {key:'stock',cat:'inventory',ar:'ملخص المخزون',en:'Stock Summary'},
  {key:'ar_aging',cat:'receivables',ar:'أعمار ذمم العملاء',en:'AR Aging'},
  {key:'ap_aging',cat:'receivables',ar:'أعمار ذمم الموردين',en:'AP Aging'},
  {key:'commissions',cat:'commissions',ar:'العمولات المستحقة',en:'Commission Accruals'},
];

export function ReportsCenterPage({ar,companyId}:{ar:boolean;companyId:number}){
  const now=new Date();
  const [topTab,setTopTab]=useState<'ready'|'builder'>('ready');
  const [cat,setCat]=useState('financial');
  const [active,setActive]=useState<Report|null>(REPORTS[0]);
  const [periodPreset,setPeriodPreset]=useState<PeriodPreset>('year');
  const [start,setStart]=useState(currentYearStart(now));
  const [end,setEnd]=useState(localYmd(now));
  const [title,setTitle]=useState('');
  const [headers,setHeaders]=useState<string[]>([]);
  const [rows,setRows]=useState<Row[]>([]);
  const [rowKinds,setRowKinds]=useState<StatementRowKind[]>([]);
  const [financialRows,setFinancialRows]=useState<ComparativeStatementRow[]>([]);
  const [financialPeriods,setFinancialPeriods]=useState<ComparisonPeriods|null>(null);
  const [busy,setBusy]=useState(false);
  const [logoBusy,setLogoBusy]=useState(false);
  const [message,setMessage]=useState('');
  const logoInput=useRef<HTMLInputElement>(null);

  const run=async(rep:Report)=>{
    setBusy(true);setMessage('');setActive(rep);
    try{
      let H:string[]=[];let R:Row[]=[];let K:StatementRowKind[]=[];let T=ar?rep.ar:rep.en;
      if(['income','balance','cashflow'].includes(rep.key)){
        const key=rep.key as FinancialStatementKey;
        const comparison=await fetchComparativeStatements(companyId,start,end,'indirect');
        if(key==='income'){
          const incomplete=[comparison.current,comparison.previous,comparison.priorYear]
            .map(statement=>statement?.sales_revenue_source)
            .find(source=>source?.required===true&&source?.complete!==true);
          if(incomplete){
            throw new Error(ar
              ? `لا يمكن إصدار قائمة دخل بأرقام مبيعات جزئية. أول يوم غير مكتمل في DGTERA: ${incomplete.first_missing_date||'—'}`
              : `An income statement cannot be issued with partial sales. First incomplete DGTERA day: ${incomplete.first_missing_date||'—'}`);
          }
        }
        const lines=buildStatementRows(key,comparison,ar);
        H=[ar?'البند':'Item',ar?'الفترة الحالية':'Current period',ar?'الفترة السابقة':'Previous period',ar?'الفترة المماثلة':'Same period last year',ar?'التغير':'Variance',ar?'نسبة التغير':'Variance %'];
        R=lines.map(line=>({
          [H[0]]:line.label,[H[1]]:formatStatementAmount(line.current),[H[2]]:formatStatementAmount(line.previous),
          [H[3]]:formatStatementAmount(line.priorYear),[H[4]]:formatStatementAmount(line.variance),
          [H[5]]:formatVariancePercent(line.variancePercent),
        }));
        K=lines.map(line=>line.kind);T=statementTitle(key,ar);
        setFinancialRows(lines);setFinancialPeriods(comparison.periods);
      }else if(rep.key==='trial'){
        const statement=await json(`/api/v1/finance/trial-balance?company_id=${companyId}&end_date=${end}`);
        H=[ar?'الحساب':'Account',ar?'مدين':'Debit',ar?'دائن':'Credit'];
        R=(statement.rows||[]).map((account:Row)=>({[H[0]]:`${account.code} — ${ar?account.name_ar:account.name_en}`,[H[1]]:fmt(Number(account.closing_debit||0)),[H[2]]:fmt(Number(account.closing_credit||0))}));
        R.push({[H[0]]:ar?'الإجمالي':'Total',[H[1]]:fmt(Number(statement.total_debit||0)),[H[2]]:fmt(Number(statement.total_credit||0))});
        K=R.map((_,index)=>index===R.length-1?'total':'line');
      }else if(rep.key==='dgtera_sales'){
        const query=new URLSearchParams({company_id:String(companyId),start_date:start,end_date:end});
        const data=await json(`/api/v1/integrations/dgtera/range-comparison?${query.toString()}`);
        const current=data?.metrics?.current;
        if(!current){
          const firstMissing=data?.coverage?.current?.first_missing_date||'—';
          const progress=data?.history?.progress_percent??0;
          throw new Error(ar
            ? `الفترة غير مكتملة المطابقة مع DGTERA. أول يوم غير مكتمل: ${firstMissing} — تقدم التاريخ: ${progress}%`
            : `The range is not fully reconciled with DGTERA. First missing day: ${firstMissing} — history progress: ${progress}%`);
        }
        const periods=comparisonPeriods(start,end);
        H=[ar?'المقياس':'Metric',ar?'الفترة الحالية':'Current period',ar?'الفترة السابقة':'Previous period',ar?'الفترة اللاحقة':'Next period',ar?'نفس الفترة 2025/العام السابق':'Same period prior year',ar?'الفرق عن السابقة':'Variance vs previous',ar?'نسبة التغير':'Variance %'];
        const metric=(window:string,field:string)=>{
          const value=data?.metrics?.[window]?.[field];
          return value===null||value===undefined?null:Number(value);
        };
        const show=(value:number|null)=>value===null?'—':fmt(value);
        const row=(label:string,field:string,kind:StatementRowKind='line')=>{
          const currentValue=metric('current',field);const previousValue=metric('previous',field);
          const nextValue=metric('next',field);const priorValue=metric('prior_year',field);
          const variance=currentValue!==null&&previousValue!==null?currentValue-previousValue:null;
          const variancePercent=variance!==null&&previousValue!==null&&previousValue!==0?variance/Math.abs(previousValue)*100:null;
          K.push(kind);
          return {[H[0]]:label,[H[1]]:show(currentValue),[H[2]]:show(previousValue),[H[3]]:show(nextValue),[H[4]]:show(priorValue),[H[5]]:show(variance),[H[6]]:variancePercent===null?'—':`${variancePercent>0?'+':''}${variancePercent.toFixed(1)}%`};
        };
        R=[
          row(ar?'صافي المبيعات دون الضريبة':'Net sales excluding VAT','subtotal','subtotal'),
          row(ar?'ضريبة المبيعات':'Sales VAT','vat'),
          row(ar?'إجمالي المبيعات شامل الضريبة':'Gross sales including VAT','sales','total'),
          row(ar?'عدد الطلبات':'Orders','orders'),
          row(ar?'الكمية':'Quantity','quantity'),
        ];
        T=ar?'مبيعات DGTERA ومقارنة الفترات':'DGTERA Sales & Period Comparison';
        setFinancialRows([]);setFinancialPeriods({
          current:periods.current,previous:periods.previous,priorYear:periods.priorYear,
        });
      }else if(rep.key==='sales_invoices'){
        const data=await json(`/api/v1/subledgers/sales-invoices?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'العميل':'Customer',ar?'الإجمالي':'Total',ar?'الحالة':'Status'];
        R=(data||[]).map((item:Row)=>({[H[0]]:item.number||item.id,[H[1]]:item.invoice_date,[H[2]]:ar?(item.customer_name_ar||'—'):(item.customer_name_en||'—'),[H[3]]:fmt(Number(item.total||0)),[H[4]]:statusText(item.status,ar)}));
      }else if(rep.key==='purchase_invoices'){
        const data=await json(`/api/v1/subledgers/purchase-invoices?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المورد':'Supplier',ar?'الإجمالي':'Total',ar?'الحالة':'Status'];
        R=(data||[]).map((item:Row)=>({[H[0]]:item.number||item.id,[H[1]]:item.invoice_date,[H[2]]:ar?(item.supplier_name_ar||'—'):(item.supplier_name_en||'—'),[H[3]]:fmt(Number(item.total||0)),[H[4]]:statusText(item.status,ar)}));
      }else if(rep.key==='receipts'){
        const data=await json(`/api/v1/subledgers/receipts?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المبلغ':'Amount',ar?'المرجع':'Reference'];
        R=(data||[]).map((item:Row)=>({[H[0]]:item.number||item.id,[H[1]]:item.receipt_date,[H[2]]:fmt(Number(item.amount||0)),[H[3]]:item.reference||'—'}));
      }else if(rep.key==='payments'){
        const data=await json(`/api/v1/subledgers/payments?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المبلغ':'Amount',ar?'المرجع':'Reference'];
        R=(data||[]).map((item:Row)=>({[H[0]]:item.number||item.id,[H[1]]:item.payment_date,[H[2]]:fmt(Number(item.amount||0)),[H[3]]:item.reference||'—'}));
      }else if(rep.key==='stock'){
        const data=await json(`/api/v1/inventory/stock-summary?company_id=${companyId}`);
        H=[ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Quantity',ar?'القيمة':'Value'];
        R=(data||[]).map((item:Row)=>({[H[0]]:ar?(item.item_name_ar||item.name_ar||item.item_id):(item.item_name_en||item.name_en||item.item_id),[H[1]]:ar?(item.warehouse_name_ar||item.warehouse_name_en||item.warehouse_id||'—'):(item.warehouse_name_en||item.warehouse_name_ar||item.warehouse_id||'—'),[H[2]]:fmt(Number(item.quantity||item.on_hand||0)),[H[3]]:fmt(Number(item.value||item.total_value||0))}));
      }else if(rep.key==='ar_aging'||rep.key==='ap_aging'){
        const ledger=rep.key==='ar_aging'?'AR':'AP';
        const data=await json(`/api/v1/subledgers/aging?company_id=${companyId}&ledger_type=${ledger}&as_of_date=${end}`);
        H=[ar?'الطرف':'Party',ar?'حالي':'Current','1-30','31-60','61-90','90+',ar?'الإجمالي':'Total'];
        const parties=data.parties||data.rows||data||[];
        R=(Array.isArray(parties)?parties:[]).map((party:Row)=>({[H[0]]:ar?(party.party_name_ar||party.party_code):(party.party_name_en||party.party_code),[H[1]]:fmt(Number(party.CURRENT||0)),[H[2]]:fmt(Number(party['1_30']||0)),[H[3]]:fmt(Number(party['31_60']||0)),[H[4]]:fmt(Number(party['61_90']||0)),[H[5]]:fmt(Number(party['91_120']||0)+Number(party.OVER_120||0)),[H[6]]:fmt(Number(party.total||0))}));
      }else if(rep.key==='commissions'){
        const data=await json(`/api/v1/sales-commissions/accruals?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'المستفيد':'Beneficiary',ar?'الفاتورة':'Invoice',ar?'العمولة':'Amount',ar?'قابل للدفع':'Payable',ar?'الحالة':'Status'];
        R=(data||[]).map((item:Row)=>({[H[0]]:item.number,[H[1]]:ar?(item.beneficiary_name_ar||item.beneficiary_name_en||'—'):(item.beneficiary_name_en||item.beneficiary_name_ar||'—'),[H[2]]:item.invoice_number||'—',[H[3]]:fmt(Number(item.amount||0)),[H[4]]:fmt(Number(item.payable_amount||0)),[H[5]]:statusText(item.status,ar)}));
      }
      if(!['income','balance','cashflow','dgtera_sales'].includes(rep.key)){setFinancialRows([]);setFinancialPeriods(null);}
      setTitle(T);setHeaders(H);setRows(R);setRowKinds(K);
      if(!R.length)setMessage(ar?'لا توجد بيانات لهذا التقرير في الفترة المحددة':'No data for this report in the selected period');
    }catch(error:any){
      setMessage(String(error.message||error));setHeaders([]);setRows([]);setRowKinds([]);setFinancialRows([]);setFinancialPeriods(null);
    }finally{setBusy(false);}
  };

  useEffect(()=>{if(active)run(active);},[companyId,ar]);

  const applyPeriodPreset=(preset:PeriodPreset)=>{
    setPeriodPreset(preset);if(preset==='custom')return;
    const current=new Date();
    const from=preset==='month'
      ? new Date(current.getFullYear(),current.getMonth(),1)
      : preset==='quarter'
        ? new Date(current.getFullYear(),Math.floor(current.getMonth()/3)*3,1)
        : new Date(current.getFullYear(),0,1);
    setStart(localYmd(from));setEnd(localYmd(current));
  };

  const uploadLogo=async(file?:File)=>{
    if(!file)return;
    if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>512*1024){
      setMessage(ar?'اختر شعارًا بصيغة PNG أو JPEG أو WEBP وبحجم لا يتجاوز 512 كيلوبايت.':'Choose a PNG, JPEG, or WEBP logo no larger than 512 KB.');return;
    }
    setLogoBusy(true);setMessage('');
    try{
      const dataUrl=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||''));reader.onerror=()=>reject(new Error('Unable to read logo'));reader.readAsDataURL(file);});
      const response=await json(`/api/v1/companies/${companyId}/logo`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_name:file.name,content_type:file.type,content_base64:dataUrl.split(',',2)[1]||''})});
      const stored=JSON.parse(localStorage.getItem('corvax_company')||'{}');
      localStorage.setItem('corvax_company',JSON.stringify({...stored,logo_url:response.logo_url}));
      setMessage(ar?'تم حفظ شعار الشركة وسيظهر في التقارير والقيود المطبوعة.':'Company logo saved and will appear on printed reports and journals.');
    }catch(error:any){setMessage(String(error.message||error));}
    finally{setLogoBusy(false);if(logoInput.current)logoInput.current.value='';}
  };

  const exportCsv=()=>{
    if(!headers.length)return;
    const escape=(value:any)=>{const text=String(value??'');return /[",\n]/.test(text)?'"'+text.replace(/"/g,'""')+'"':text;};
    const csv='\uFEFF'+[headers.map(escape).join(','),...rows.map(row=>headers.map(header=>escape(row[header])).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
    const link=document.createElement('a');link.href=url;link.download=`${title||'report'}_${end}.csv`;link.click();URL.revokeObjectURL(url);
  };

  const catLabel=(value:string)=>{const found=CATEGORIES.find(item=>item[0]===value);return found?(ar?found[1]:found[2]):value;};

  const printReport=()=>{
    if(!active||!headers.length)return;
    const numericByReport:Record<string,number[]>={
      income:[1,2,3,4,5],balance:[1,2,3,4,5],cashflow:[1,2,3,4,5],trial:[1,2],
      sales_invoices:[3],purchase_invoices:[3],receipts:[2],payments:[2],stock:[2,3],
      ar_aging:[1,2,3,4,5,6],ap_aging:[1,2,3,4,5,6],commissions:[3,4],
    };
    const opened=printBusinessDocument({
      ar,title,documentLabel:ar?'تقرير مالي وإداري':'Financial and management report',
      subtitle:ar?`تقرير ${active.ar} مستخرج من دفتر الأستاذ والمصادر التشغيلية المعتمدة.`:`${active.en} generated from the posted ledger and approved operating sources.`,
      columns:headers,rows:rows.map(row=>headers.map(header=>row[header])),rowKinds,
      numericColumns:numericByReport[active.key]||[],landscape:headers.length>5,
      meta:[
        {label:ar?'الفترة الحالية':'Current period',value:`${start} — ${end}`},
        ...(financialPeriods?[
          {label:ar?'الفترة السابقة':'Previous period',value:`${financialPeriods.previous.start} — ${financialPeriods.previous.end}`},
          {label:ar?'الفترة المماثلة':'Same period last year',value:`${financialPeriods.priorYear.start} — ${financialPeriods.priorYear.end}`},
        ]:[]),
        {label:ar?'فئة التقرير':'Report category',value:catLabel(active.cat)},
        {label:ar?'عدد السطور':'Row count',value:rows.length},
      ],
    });
    if(!opened)setMessage(ar?'تعذر فتح نافذة الطباعة. اسمح بالنوافذ المنبثقة لهذا الموقع.':'Unable to open the print window. Allow pop-ups for this site.');
  };

  const catReports=REPORTS.filter(report=>report.cat===cat);
  const catIcon:Record<string,any>={financial:<Landmark size={16}/>,sales:<TrendingUp size={16}/>,purchases:<ShoppingCart size={16}/>,inventory:<Package size={16}/>,receivables:<Users size={16}/>,commissions:<Percent size={16}/>};
  const topButton=(key:'ready'|'builder',label:string)=><button key={key} onClick={()=>setTopTab(key)} style={{padding:'9px 18px',borderRadius:9,border:'1px solid var(--border)',background:topTab===key?'var(--accent, #1e40af)':'transparent',color:topTab===key?'#fff':'var(--text)',cursor:'pointer',fontWeight:700}}>{label}</button>;

  if(topTab==='builder')return <>
    <div style={{display:'flex',gap:8,margin:'4px 0 16px'}}>{topButton('ready',ar?'تقارير جاهزة':'Ready reports')}{topButton('builder',ar?'مصمّم التقارير':'Report Builder')}</div>
    <ReportBuilderTab ar={ar} companyId={companyId}/>
  </>;

  return <>
    <div style={{display:'flex',gap:8,margin:'4px 0 16px'}}>{topButton('ready',ar?'تقارير جاهزة':'Ready reports')}{topButton('builder',ar?'مصمّم التقارير':'Report Builder')}</div>
    <div className="kpis">
      <Kpi title={ar?'الفئات':'Categories'} value={String(CATEGORIES.length)} trend="" good icon={<FileBarChart size={22}/>} tone="blue"/>
      <Kpi title={ar?'التقارير المتاحة':'Available reports'} value={String(REPORTS.length)} trend="" good icon={<FileBarChart size={22}/>} tone="violet"/>
      <Kpi title={ar?'التقرير الحالي':'Current report'} value={active?(ar?active.ar:active.en):'—'} trend="" good icon={<TrendingUp size={22}/>} tone="green"/>
      <Kpi title={ar?'عدد السطور':'Rows'} value={String(rows.length)} trend="" good icon={<Package size={22}/>} tone="amber"/>
    </div>

    <Panel title={ar?'مركز التقارير الموحد':'Unified Reports Center'} icon={<FileBarChart size={18}/> }>
      <div style={{padding:12}}>
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:12}}>{CATEGORIES.map(([key])=><button key={key} onClick={()=>setCat(key)} style={{...ghost,display:'flex',alignItems:'center',gap:6,background:cat===key?'var(--accent, #1e40af)':'transparent',color:cat===key?'#fff':'var(--text)'}}>{catIcon[key]}{catLabel(key)}</button>)}</div>
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:12}}>{catReports.map(report=><button key={report.key} onClick={()=>run(report)} style={{...ghost,background:active?.key===report.key?'var(--panel-2, #e0e7ff)':'transparent',fontWeight:active?.key===report.key?700:600}}>{ar?report.ar:report.en}</button>)}</div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',gap:12,alignItems:'end'}}>
          <label>{ar?'نوع الفترة':'Period preset'}<select style={field} value={periodPreset} onChange={event=>applyPeriodPreset(event.target.value as PeriodPreset)}><option value="month">{ar?'الشهر الحالي':'Current month'}</option><option value="quarter">{ar?'الربع الحالي':'Current quarter'}</option><option value="year">{ar?'من بداية السنة':'Year to date'}</option><option value="custom">{ar?'فترة مخصصة':'Custom period'}</option></select></label>
          <label>{ar?'من تاريخ':'From date'}<input type="date" style={field} value={start} onChange={event=>{setStart(event.target.value);setPeriodPreset('custom')}}/></label>
          <label>{ar?'إلى تاريخ':'To date'}<input type="date" style={field} value={end} onChange={event=>{setEnd(event.target.value);setPeriodPreset('custom')}}/></label>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy||!active} onClick={()=>active&&run(active)}>{ar?'تشغيل التقرير':'Run report'}</button>
          <button style={{...ghost,display:'flex',alignItems:'center',gap:6,justifyContent:'center'}} disabled={!rows.length} onClick={exportCsv}><Download size={16}/>{ar?'تصدير Excel':'Export Excel'}</button>
          <button style={{...ghost,display:'flex',alignItems:'center',gap:6,justifyContent:'center'}} disabled={!rows.length} onClick={printReport}><Printer size={16}/>{ar?'طباعة / PDF':'Print / PDF'}</button>
          <input ref={logoInput} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={event=>uploadLogo(event.target.files?.[0])}/>
          <button style={{...ghost,display:'flex',alignItems:'center',gap:6,justifyContent:'center'}} disabled={logoBusy} onClick={()=>logoInput.current?.click()}><ImagePlus size={16}/>{logoBusy?(ar?'جارٍ حفظ الشعار...':'Saving logo...'):(ar?'إضافة شعار الشركة':'Add company logo')}</button>
        </div>
      </div>
    </Panel>

    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {financialPeriods&&active&&['income','balance','cashflow'].includes(active.key)
      ? <ComparativeStatementTable ar={ar} title={title} rows={financialRows} periods={financialPeriods} loading={busy}/>
      : headers.length>0&&<Panel title={title} icon={<Calendar size={18}/> }>
        <div style={{overflowX:'auto',padding:'0 4px 12px'}}><table style={{width:'100%',borderCollapse:'collapse'}}>
          <thead><tr>{headers.map(header=><th key={header} style={th}>{header}</th>)}</tr></thead>
          <tbody>{rows.map((row,index)=><tr key={index} data-kind={rowKinds[index]||'line'}>{headers.map(header=><td key={header} style={td}>{row[header]}</td>)}</tr>)}</tbody>
        </table></div>
      </Panel>}
  </>;
}
