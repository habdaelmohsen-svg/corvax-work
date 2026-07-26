import {useEffect, useState} from 'react';
import {FileBarChart, Download, Printer, Calendar, TrendingUp, ShoppingCart, Package, Users, Landmark, Percent} from 'lucide-react';
import {apiFetch} from '../api/client';
import {Kpi, Panel, fmt} from './ui';
import {ReportBuilderTab} from './reportBuilderTab';

// Reports Center: a UNIFIED front-end over reports that already exist in the platform.
// It does not duplicate report logic - it calls the existing endpoints, lets the user
// pick a period, and adds export (CSV -> opens in Excel) and print/PDF (browser).

async function json(url:string){
  const r=await apiFetch(url); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const iso=(d:Date)=>d.toISOString().slice(0,10);
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const ghost={padding:'8px 14px',borderRadius:9,border:'1px solid var(--border)',background:'transparent',color:'var(--text)',cursor:'pointer',fontWeight:600} as const;
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const th={textAlign:'start',padding:'9px 12px',borderBottom:'2px solid var(--border)',fontWeight:700,fontSize:13} as const;
const td={padding:'8px 12px',borderBottom:'1px solid var(--border)',fontSize:13} as const;

type Row=Record<string,any>;
type Report={key:string;cat:string;ar:string;en:string};

const CATEGORIES:[string,string,string][]=[
  ['financial','المالية','Financial'],
  ['sales','المبيعات','Sales'],
  ['purchases','المشتريات','Purchases'],
  ['inventory','المخزون','Inventory'],
  ['receivables','الذمم','Receivables & Payables'],
  ['commissions','العمولات','Commissions'],
];
const REPORTS:Report[]=[
  {key:'income',cat:'financial',ar:'قائمة الدخل',en:'Income Statement'},
  {key:'balance',cat:'financial',ar:'قائمة المركز المالي',en:'Balance Sheet'},
  {key:'cashflow',cat:'financial',ar:'قائمة التدفقات النقدية',en:'Cash Flow Statement'},
  {key:'trial',cat:'financial',ar:'ميزان المراجعة',en:'Trial Balance'},
  {key:'sales_invoices',cat:'sales',ar:'فواتير البيع',en:'Sales Invoices'},
  {key:'receipts',cat:'sales',ar:'سندات القبض',en:'Receipts'},
  {key:'purchase_invoices',cat:'purchases',ar:'فواتير الشراء',en:'Purchase Invoices'},
  {key:'payments',cat:'purchases',ar:'سندات الصرف',en:'Payments'},
  {key:'stock',cat:'inventory',ar:'ملخص المخزون',en:'Stock Summary'},
  {key:'ar_aging',cat:'receivables',ar:'أعمار ذمم العملاء',en:'AR Aging'},
  {key:'ap_aging',cat:'receivables',ar:'أعمار ذمم الموردين',en:'AP Aging'},
  {key:'commissions',cat:'commissions',ar:'العمولات المستحقة',en:'Commission Accruals'},
];

export function ReportsCenterPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [topTab,setTopTab]=useState<'ready'|'builder'>('ready');
  const today=new Date();
  const yearStart=new Date(today.getFullYear(),0,1);
  const [cat,setCat]=useState('financial');
  const [active,setActive]=useState<Report|null>(REPORTS[0]);
  const [start,setStart]=useState(iso(yearStart));
  const [end,setEnd]=useState(iso(today));
  const [title,setTitle]=useState('');
  const [headers,setHeaders]=useState<string[]>([]);
  const [rows,setRows]=useState<Row[]>([]);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');

  const run=async(rep:Report)=>{
    setBusy(true);setMessage('');setActive(rep);
    try{
      let H:string[]=[]; let R:Row[]=[]; let T=ar?rep.ar:rep.en;
      if(rep.key==='income'){
        const s=await json(`/api/v1/finance/statements?company_id=${companyId}&start_date=${start}&end_date=${end}`);
        const inc=s.income_statement||{};
        H=[ar?'البند':'Item',ar?'المبلغ':'Amount'];
        R=[
          [ar?'الإيرادات':'Revenue',inc.revenue],
          [ar?'تكلفة الإيرادات':'Cost of revenue',inc.cost_of_revenue],
          [ar?'مجمل الربح':'Gross profit',inc.gross_profit],
          [ar?'المصروفات التشغيلية':'Operating expenses',inc.operating_expenses],
          [ar?'الربح التشغيلي':'Operating profit',inc.operating_profit],
          [ar?'إيرادات أخرى':'Other income',inc.other_income],
          [ar?'مصروفات أخرى':'Other expenses',inc.other_expenses],
          [ar?'تكلفة التمويل':'Finance cost',inc.finance_cost],
          [ar?'الزكاة والضريبة':'Zakat & tax',inc.zakat_tax],
          [ar?'صافي الربح':'Net profit',inc.net_profit],
        ].map(([k,v])=>({[H[0]]:k,[H[1]]:fmt(Number(v||0))}));
      } else if(rep.key==='balance'){
        const s=await json(`/api/v1/finance/statements?company_id=${companyId}&start_date=${start}&end_date=${end}`);
        const fp=s.financial_position||{};
        H=[ar?'البند':'Item',ar?'المبلغ':'Amount'];
        R=[
          [ar?'أصول متداولة':'Current assets',fp.current_assets],
          [ar?'أصول غير متداولة':'Non-current assets',fp.non_current_assets],
          [ar?'إجمالي الأصول':'Total assets',fp.total_assets],
          [ar?'خصوم متداولة':'Current liabilities',fp.current_liabilities],
          [ar?'خصوم غير متداولة':'Non-current liabilities',fp.non_current_liabilities],
          [ar?'إجمالي الخصوم':'Total liabilities',fp.total_liabilities],
          [ar?'حقوق الملكية':'Equity',fp.equity],
        ].map(([k,v])=>({[H[0]]:k,[H[1]]:fmt(Number(v||0))}));
      } else if(rep.key==='cashflow'){
        const s=await json(`/api/v1/finance/statements?company_id=${companyId}&start_date=${start}&end_date=${end}`);
        const cf=s.cash_flows||{};
        H=[ar?'النشاط':'Activity',ar?'التدفق':'Cash flow'];
        R=[
          [ar?'الأنشطة التشغيلية':'Operating',cf.net_operating],
          [ar?'الأنشطة الاستثمارية':'Investing',cf.net_investing],
          [ar?'الأنشطة التمويلية':'Financing',cf.net_financing],
          [ar?'صافي التغير في النقد':'Net change',cf.net_change],
          [ar?'النقد الافتتاحي':'Opening cash',cf.opening_cash],
          [ar?'النقد الختامي':'Closing cash',cf.closing_cash],
        ].map(([k,v])=>({[H[0]]:k,[H[1]]:fmt(Number(v||0))}));
      } else if(rep.key==='trial'){
        const s=await json(`/api/v1/finance/trial-balance?company_id=${companyId}&as_of_date=${end}`);
        H=[ar?'الحساب':'Account',ar?'مدين':'Debit',ar?'دائن':'Credit'];
        R=(s.rows||[]).map((a:Row)=>({[H[0]]:`${a.code} — ${ar?a.name_ar:a.name_en}`,[H[1]]:fmt(Number(a.closing_debit||0)),[H[2]]:fmt(Number(a.closing_credit||0))}));
        R.push({[H[0]]:ar?'الإجمالي':'Total',[H[1]]:fmt(Number(s.total_debit||0)),[H[2]]:fmt(Number(s.total_credit||0))});
      } else if(rep.key==='sales_invoices'){
        const d=await json(`/api/v1/subledgers/sales-invoices?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'العميل':'Customer',ar?'الإجمالي':'Total',ar?'الحالة':'Status'];
        R=(d||[]).map((i:Row)=>({[H[0]]:i.number||i.id,[H[1]]:i.invoice_date,[H[2]]:ar?(i.customer_name_ar||'—'):(i.customer_name_en||'—'),[H[3]]:fmt(Number(i.total||0)),[H[4]]:i.status}));
      } else if(rep.key==='purchase_invoices'){
        const d=await json(`/api/v1/subledgers/purchase-invoices?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المورد':'Supplier',ar?'الإجمالي':'Total',ar?'الحالة':'Status'];
        R=(d||[]).map((i:Row)=>({[H[0]]:i.number||i.id,[H[1]]:i.invoice_date,[H[2]]:ar?(i.supplier_name_ar||'—'):(i.supplier_name_en||'—'),[H[3]]:fmt(Number(i.total||0)),[H[4]]:i.status}));
      } else if(rep.key==='receipts'){
        const d=await json(`/api/v1/subledgers/receipts?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المبلغ':'Amount',ar?'المرجع':'Reference'];
        R=(d||[]).map((i:Row)=>({[H[0]]:i.number||i.id,[H[1]]:i.receipt_date,[H[2]]:fmt(Number(i.amount||0)),[H[3]]:i.reference||'—'}));
      } else if(rep.key==='payments'){
        const d=await json(`/api/v1/subledgers/payments?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المبلغ':'Amount',ar?'المرجع':'Reference'];
        R=(d||[]).map((i:Row)=>({[H[0]]:i.number||i.id,[H[1]]:i.payment_date,[H[2]]:fmt(Number(i.amount||0)),[H[3]]:i.reference||'—'}));
      } else if(rep.key==='stock'){
        const d=await json(`/api/v1/inventory/stock-summary?company_id=${companyId}`);
        H=[ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Quantity',ar?'القيمة':'Value'];
        R=(d||[]).map((i:Row)=>({[H[0]]:ar?(i.item_name_ar||i.name_ar||i.item_id):(i.item_name_en||i.name_en||i.item_id),[H[1]]:i.warehouse_name_ar||i.warehouse_id||'—',[H[2]]:fmt(Number(i.quantity||i.on_hand||0)),[H[3]]:fmt(Number(i.value||i.total_value||0))}));
      } else if(rep.key==='ar_aging'||rep.key==='ap_aging'){
        const lt=rep.key==='ar_aging'?'AR':'AP';
        const d=await json(`/api/v1/subledgers/aging?company_id=${companyId}&ledger_type=${lt}&as_of_date=${end}`);
        H=[ar?'الطرف':'Party',ar?'حالي':'Current','1-30','31-60','61-90','90+',ar?'الإجمالي':'Total'];
        const parties=d.parties||d.rows||d||[];
        R=(Array.isArray(parties)?parties:[]).map((p:Row)=>({[H[0]]:ar?(p.party_name_ar||p.party_code):(p.party_name_en||p.party_code),[H[1]]:fmt(Number(p.CURRENT||0)),[H[2]]:fmt(Number(p['1_30']||0)),[H[3]]:fmt(Number(p['31_60']||0)),[H[4]]:fmt(Number(p['61_90']||0)),[H[5]]:fmt(Number(p['91_120']||0)+Number(p.OVER_120||0)),[H[6]]:fmt(Number(p.total||0))}));
      } else if(rep.key==='commissions'){
        const d=await json(`/api/v1/sales-commissions/accruals?company_id=${companyId}`);
        H=[ar?'الرقم':'No.',ar?'المستفيد':'Beneficiary',ar?'الفاتورة':'Invoice',ar?'العمولة':'Amount',ar?'قابل للدفع':'Payable',ar?'الحالة':'Status'];
        R=(d||[]).map((a:Row)=>({[H[0]]:a.number,[H[1]]:a.beneficiary_name_ar||'—',[H[2]]:a.invoice_number||'—',[H[3]]:fmt(Number(a.amount||0)),[H[4]]:fmt(Number(a.payable_amount||0)),[H[5]]:a.status}));
      }
      setTitle(T);setHeaders(H);setRows(R);
      if(!R.length)setMessage(ar?'لا توجد بيانات لهذا التقرير في الفترة المحددة':'No data for this report in the selected period');
    }catch(e:any){setMessage(String(e.message||e));setHeaders([]);setRows([]);}
    finally{setBusy(false);}
  };
  useEffect(()=>{if(active)run(active);},[companyId]);

  const exportCsv=()=>{
    if(!headers.length)return;
    const esc=(v:any)=>{const s=String(v??'');return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;};
    const lines=[headers.map(esc).join(','),...rows.map(r=>headers.map(h=>esc(r[h])).join(','))];
    const csv='\uFEFF'+lines.join('\r\n'); // BOM so Excel reads Arabic correctly
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download=`${title||'report'}_${end}.csv`;a.click();URL.revokeObjectURL(url);
  };
  const printReport=()=>{
    const w=window.open('','_blank');if(!w)return;
    const dir=ar?'rtl':'ltr';
    const thead='<tr>'+headers.map(h=>`<th style="text-align:${ar?'right':'left'};padding:8px;border-bottom:2px solid #333">${h}</th>`).join('')+'</tr>';
    const tbody=rows.map(r=>'<tr>'+headers.map(h=>`<td style="padding:6px 8px;border-bottom:1px solid #ccc">${r[h]??''}</td>`).join('')+'</tr>').join('');
    w.document.write(`<html dir="${dir}"><head><title>${title}</title><meta charset="utf-8"></head><body style="font-family:Arial,sans-serif;padding:24px"><h2>${title}</h2><div style="color:#555;margin-bottom:12px">${ar?'الفترة':'Period'}: ${start} → ${end}</div><table style="width:100%;border-collapse:collapse">${thead}${tbody}</table><script>window.onload=()=>window.print()</script></body></html>`);
    w.document.close();
  };

  const catReports=REPORTS.filter(r=>r.cat===cat);
  const catLabel=(c:string)=>{const f=CATEGORIES.find(x=>x[0]===c);return f?(ar?f[1]:f[2]):c;};
  const catIcon:Record<string,any>={financial:<Landmark size={16}/>,sales:<TrendingUp size={16}/>,purchases:<ShoppingCart size={16}/>,inventory:<Package size={16}/>,receivables:<Users size={16}/>,commissions:<Percent size={16}/>};

  const _topBtn=(k:'ready'|'builder',l:string)=>(<button key={k} onClick={()=>setTopTab(k)} style={{padding:'9px 18px',borderRadius:9,border:'1px solid var(--border)',background:topTab===k?'var(--accent, #1e40af)':'transparent',color:topTab===k?'#fff':'var(--text)',cursor:'pointer',fontWeight:700}}>{l}</button>);
  if(topTab==='builder'){
    return <>
      <div style={{display:'flex',gap:8,margin:'4px 0 16px'}}>{_topBtn('ready',ar?'تقارير جاهزة':'Ready reports')}{_topBtn('builder',ar?'مصمّم التقارير':'Report Builder')}</div>
      <ReportBuilderTab ar={ar} companyId={companyId}/>
    </>;
  }
  return <>
    <div style={{display:'flex',gap:8,margin:'4px 0 16px'}}>{_topBtn('ready',ar?'تقارير جاهزة':'Ready reports')}{_topBtn('builder',ar?'مصمّم التقارير':'Report Builder')}</div>
    <div className="kpis">
      <Kpi title={ar?'الفئات':'Categories'} value={String(CATEGORIES.length)} trend="" good icon={<FileBarChart size={22}/>} tone="blue"/>
      <Kpi title={ar?'التقارير المتاحة':'Available reports'} value={String(REPORTS.length)} trend="" good icon={<FileBarChart size={22}/>} tone="violet"/>
      <Kpi title={ar?'التقرير الحالي':'Current report'} value={active?(ar?active.ar:active.en):'—'} trend="" good icon={<TrendingUp size={22}/>} tone="green"/>
      <Kpi title={ar?'عدد السطور':'Rows'} value={String(rows.length)} trend="" good icon={<Package size={22}/>} tone="amber"/>
    </div>

    <Panel title={ar?'مركز التقارير':'Reports Center'} icon={<FileBarChart size={18}/>}>
      <div style={{padding:12}}>
        {/* category chips */}
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:12}}>
          {CATEGORIES.map(([k])=>
            <button key={k} onClick={()=>setCat(k)} style={{...ghost,display:'flex',alignItems:'center',gap:6,background:cat===k?'var(--accent, #1e40af)':'transparent',color:cat===k?'#fff':'var(--text)'}}>{catIcon[k]}{catLabel(k)}</button>)}
        </div>
        {/* report chips in category */}
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:12}}>
          {catReports.map(r=>
            <button key={r.key} onClick={()=>run(r)} style={{...ghost,background:active?.key===r.key?'var(--panel-2, #e0e7ff)':'transparent',fontWeight:active?.key===r.key?700:600}}>{ar?r.ar:r.en}</button>)}
        </div>
        {/* period + actions */}
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',gap:12,alignItems:'end'}}>
          <label>{ar?'من تاريخ':'From date'}<input type="date" style={field} value={start} onChange={e=>setStart(e.target.value)}/></label>
          <label>{ar?'إلى تاريخ':'To date'}<input type="date" style={field} value={end} onChange={e=>setEnd(e.target.value)}/></label>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy||!active} onClick={()=>active&&run(active)}>{ar?'تشغيل التقرير':'Run report'}</button>
          <button style={{...ghost,display:'flex',alignItems:'center',gap:6,justifyContent:'center'}} disabled={!rows.length} onClick={exportCsv}><Download size={16}/>{ar?'تصدير Excel':'Export Excel'}</button>
          <button style={{...ghost,display:'flex',alignItems:'center',gap:6,justifyContent:'center'}} disabled={!rows.length} onClick={printReport}><Printer size={16}/>{ar?'طباعة / PDF':'Print / PDF'}</button>
        </div>
      </div>
    </Panel>

    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {headers.length>0&&<Panel title={title} icon={<Calendar size={18}/>}>
      <div style={{overflowX:'auto',padding:'0 4px 12px'}}>
        <table style={{width:'100%',borderCollapse:'collapse'}}>
          <thead><tr>{headers.map(h=><th key={h} style={th}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((r,i)=><tr key={i}>{headers.map(h=><td key={h} style={td}>{r[h]}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </Panel>}
  </>;
}