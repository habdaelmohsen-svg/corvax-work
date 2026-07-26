import {useState} from 'react';
import {Wrench, Download, FileText, Filter, Table2, Plus, X, Play} from 'lucide-react';
import {apiFetch} from '../api/client';
import {Kpi, Panel, fmt} from './ui';
import * as XLSX from 'xlsx';
import {jsPDF} from 'jspdf';
import autoTable from 'jspdf-autotable';

// Report Builder: hybrid (ready-made data sources + free customization).
// The user picks a data source, chooses columns, filters, groups/aggregates,
// then exports to real .xlsx or .pdf.

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

type Col={key:string;ar:string;en:string;numeric?:boolean};
type Source={
  id:string; ar:string; en:string; cat:string;
  url:(companyId:number,start:string,end:string)=>string;
  pick?:(raw:any)=>any[];      // extract the array from the response
  cols:Col[];
};

// ---- All data sources across the whole system ----
const SOURCES:Source[]=[
  {id:'sales_invoices',cat:'sales',ar:'فواتير البيع',en:'Sales Invoices',
   url:(c)=>`/api/v1/subledgers/sales-invoices?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'invoice_date',ar:'التاريخ',en:'Date'},{key:'customer_name_ar',ar:'العميل',en:'Customer'},{key:'subtotal',ar:'الصافي',en:'Subtotal',numeric:true},{key:'vat_amount',ar:'الضريبة',en:'VAT',numeric:true},{key:'total',ar:'الإجمالي',en:'Total',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
  {id:'purchase_invoices',cat:'purchases',ar:'فواتير الشراء',en:'Purchase Invoices',
   url:(c)=>`/api/v1/subledgers/purchase-invoices?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'invoice_date',ar:'التاريخ',en:'Date'},{key:'supplier_name_ar',ar:'المورد',en:'Supplier'},{key:'supplier_invoice_number',ar:'فاتورة المورد',en:'Supplier inv.'},{key:'total',ar:'الإجمالي',en:'Total',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
  {id:'receipts',cat:'sales',ar:'سندات القبض',en:'Receipts',
   url:(c)=>`/api/v1/subledgers/receipts?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'receipt_date',ar:'التاريخ',en:'Date'},{key:'amount',ar:'المبلغ',en:'Amount',numeric:true},{key:'reference',ar:'المرجع',en:'Reference'}]},
  {id:'payments',cat:'purchases',ar:'سندات الصرف',en:'Payments',
   url:(c)=>`/api/v1/subledgers/payments?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'payment_date',ar:'التاريخ',en:'Date'},{key:'amount',ar:'المبلغ',en:'Amount',numeric:true},{key:'reference',ar:'المرجع',en:'Reference'}]},
  {id:'journals',cat:'financial',ar:'القيود المحاسبية',en:'Journal Entries',
   url:(c)=>`/api/v1/finance/journals?company_id=${c}`,
   pick:(d)=>Array.isArray(d)?d:(d.journals||d.rows||[]),
   cols:[{key:'number',ar:'رقم القيد',en:'No.'},{key:'entry_date',ar:'التاريخ',en:'Date'},{key:'description',ar:'البيان',en:'Description'},{key:'reference',ar:'المرجع',en:'Reference'},{key:'total_debit',ar:'مدين',en:'Debit',numeric:true},{key:'total_credit',ar:'دائن',en:'Credit',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
  {id:'trial',cat:'financial',ar:'ميزان المراجعة',en:'Trial Balance',
   url:(c,_,end)=>`/api/v1/finance/trial-balance?company_id=${c}&as_of_date=${end}`,
   pick:(d)=>d.rows||[],
   cols:[{key:'code',ar:'رقم الحساب',en:'Code'},{key:'name_ar',ar:'اسم الحساب',en:'Account'},{key:'closing_debit',ar:'مدين',en:'Debit',numeric:true},{key:'closing_credit',ar:'دائن',en:'Credit',numeric:true}]},
  {id:'stock',cat:'inventory',ar:'ملخص المخزون',en:'Stock Summary',
   url:(c)=>`/api/v1/inventory/stock-summary?company_id=${c}`,
   cols:[{key:'item_name_ar',ar:'الصنف',en:'Item'},{key:'warehouse_name_ar',ar:'المستودع',en:'Warehouse'},{key:'quantity',ar:'الكمية',en:'Quantity',numeric:true},{key:'value',ar:'القيمة',en:'Value',numeric:true}]},
  {id:'items',cat:'inventory',ar:'الأصناف',en:'Items',
   url:(c)=>`/api/v1/inventory/items?company_id=${c}`,
   cols:[{key:'code',ar:'الكود',en:'Code'},{key:'name_ar',ar:'الاسم',en:'Name'},{key:'item_type',ar:'النوع',en:'Type'},{key:'unit',ar:'الوحدة',en:'Unit'}]},
  {id:'parties',cat:'sales',ar:'العملاء والموردون',en:'Customers & Suppliers',
   url:(c)=>`/api/v1/subledgers/parties?company_id=${c}`,
   cols:[{key:'code',ar:'الكود',en:'Code'},{key:'name_ar',ar:'الاسم',en:'Name'},{key:'party_type',ar:'النوع',en:'Type'}]},
  {id:'assets',cat:'financial',ar:'الأصول الثابتة',en:'Fixed Assets',
   url:(c)=>`/api/v1/assets/lifecycle?company_id=${c}`,
   pick:(d)=>Array.isArray(d)?d:(d.assets||d.rows||[]),
   cols:[{key:'code',ar:'الكود',en:'Code'},{key:'name_ar',ar:'الاسم',en:'Name'},{key:'acquisition_cost',ar:'التكلفة',en:'Cost',numeric:true},{key:'net_book_value',ar:'القيمة الدفترية',en:'NBV',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
  {id:'employees',cat:'hr',ar:'الموظفون',en:'Employees',
   url:(c)=>`/api/v1/payroll/employees?company_id=${c}`,
   pick:(d)=>Array.isArray(d)?d:(d.employees||d.rows||[]),
   cols:[{key:'employee_number',ar:'الرقم الوظيفي',en:'Emp. No.'},{key:'name_ar',ar:'الاسم',en:'Name'},{key:'nationality_group',ar:'الجنسية',en:'Nationality'},{key:'hire_date',ar:'تاريخ التعيين',en:'Hire date'},{key:'basic_salary',ar:'الراتب الأساسي',en:'Basic salary',numeric:true},{key:'housing_allowance',ar:'بدل السكن',en:'Housing',numeric:true},{key:'other_allowance',ar:'بدلات أخرى',en:'Other allow.',numeric:true}]},
  {id:'commissions',cat:'sales',ar:'العمولات المستحقة',en:'Commission Accruals',
   url:(c)=>`/api/v1/sales-commissions/accruals?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'beneficiary_name_ar',ar:'المستفيد',en:'Beneficiary'},{key:'invoice_number',ar:'الفاتورة',en:'Invoice'},{key:'amount',ar:'العمولة',en:'Amount',numeric:true},{key:'payable_amount',ar:'قابل للدفع',en:'Payable',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
  {id:'fleet_trips',cat:'fleet',ar:'رحلات الأسطول',en:'Fleet Trips',
   url:(c)=>`/api/v1/departments/fleet/trips?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'trip_date',ar:'التاريخ',en:'Date'},{key:'vehicle_plate',ar:'المركبة',en:'Vehicle'},{key:'destination_ar',ar:'الوجهة',en:'Destination'},{key:'distance_km',ar:'المسافة',en:'Distance',numeric:true},{key:'fuel_cost',ar:'الوقود',en:'Fuel',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
  {id:'legal_contracts',cat:'legal',ar:'العقود القانونية',en:'Legal Contracts',
   url:(c)=>`/api/v1/departments/legal/contracts?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'title_ar',ar:'العنوان',en:'Title'},{key:'counterparty_ar',ar:'الطرف الآخر',en:'Counterparty'},{key:'value',ar:'القيمة',en:'Value',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
  {id:'maintenance_wo',cat:'maintenance',ar:'أوامر الصيانة',en:'Maintenance Work Orders',
   url:(c)=>`/api/v1/departments/maintenance/work-orders?company_id=${c}`,
   cols:[{key:'number',ar:'الرقم',en:'No.'},{key:'asset_name_ar',ar:'الأصل',en:'Asset'},{key:'work_type',ar:'النوع',en:'Type'},{key:'total_cost',ar:'التكلفة',en:'Cost',numeric:true},{key:'status',ar:'الحالة',en:'Status'}]},
];

const CATS:[string,string,string][]=[['financial','المالية','Financial'],['sales','المبيعات','Sales'],['purchases','المشتريات','Purchases'],['inventory','المخزون','Inventory'],['hr','الموارد البشرية','HR'],['fleet','الأسطول','Fleet'],['legal','القانونية','Legal'],['maintenance','الصيانة','Maintenance']];
type Agg='none'|'sum'|'count'|'avg';

export function ReportBuilderTab({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date();
  const [cat,setCat]=useState('sales');
  const [source,setSource]=useState<Source>(SOURCES[0]);
  const [selCols,setSelCols]=useState<string[]>(SOURCES[0].cols.map(c=>c.key));
  const [start,setStart]=useState(iso(new Date(today.getFullYear(),0,1)));
  const [end,setEnd]=useState(iso(today));
  const [dateField,setDateField]=useState('');
  const [textFilterCol,setTextFilterCol]=useState('');
  const [textFilterVal,setTextFilterVal]=useState('');
  const [groupBy,setGroupBy]=useState('');
  const [agg,setAgg]=useState<Agg>('none');
  const [aggCol,setAggCol]=useState('');
  const [reportName,setReportName]=useState('');
  const [rows,setRows]=useState<any[]>([]);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');

  const pickSource=(s:Source)=>{
    setSource(s); setSelCols(s.cols.map(c=>c.key));
    const df=s.cols.find(c=>c.key.includes('date'));
    setDateField(df?df.key:''); setGroupBy(''); setAgg('none'); setAggCol('');
    const num=s.cols.find(c=>c.numeric); setAggCol(num?num.key:'');
    setTextFilterCol(''); setTextFilterVal(''); setRows([]);
  };

  const toggleCol=(k:string)=>setSelCols(p=>p.includes(k)?p.filter(x=>x!==k):[...p,k]);

  const run=async()=>{
    setBusy(true);setMessage('');
    try{
      const raw=await json(source.url(companyId,start,end));
      let data:any[]=source.pick?source.pick(raw):(Array.isArray(raw)?raw:[]);
      // date filter
      if(dateField){
        data=data.filter(r=>{const v=r[dateField];if(!v)return true;const s=String(v).slice(0,10);return s>=start&&s<=end;});
      }
      // text filter
      if(textFilterCol&&textFilterVal.trim()){
        const q=textFilterVal.trim().toLowerCase();
        data=data.filter(r=>String(r[textFilterCol]??'').toLowerCase().includes(q));
      }
      // grouping / aggregation
      let out:any[];
      if(groupBy&&agg!=='none'){
        const groups:Record<string,any[]>={};
        data.forEach(r=>{const k=String(r[groupBy]??'—');(groups[k]=groups[k]||[]).push(r);});
        out=Object.entries(groups).map(([k,items])=>{
          const row:any={[groupBy]:k};
          if(agg==='count'){row['__value']=items.length;}
          else if(aggCol){
            const nums=items.map(i=>Number(i[aggCol]||0));
            row['__value']=agg==='sum'?nums.reduce((a,b)=>a+b,0):nums.reduce((a,b)=>a+b,0)/(nums.length||1);
          }
          return row;
        });
      } else {
        out=data.map(r=>{const o:any={};selCols.forEach(k=>o[k]=r[k]);return o;});
      }
      setRows(out);
      if(!out.length)setMessage(ar?'لا توجد بيانات مطابقة':'No matching data');
    }catch(e:any){setMessage(String(e.message||e));setRows([]);}
    finally{setBusy(false);}
  };

  // Build headers + matrix for export/preview
  const buildMatrix=()=>{
    let heads:string[]; let keys:string[];
    if(groupBy&&agg!=='none'){
      const gcol=source.cols.find(c=>c.key===groupBy);
      const aggLabel=agg==='count'?(ar?'العدد':'Count'):agg==='sum'?(ar?'الإجمالي':'Sum'):(ar?'المتوسط':'Average');
      heads=[gcol?(ar?gcol.ar:gcol.en):groupBy,aggLabel]; keys=[groupBy,'__value'];
    } else {
      const cols=source.cols.filter(c=>selCols.includes(c.key));
      heads=cols.map(c=>ar?c.ar:c.en); keys=cols.map(c=>c.key);
    }
    const matrix=rows.map(r=>keys.map(k=>{
      const v=r[k];
      const col=source.cols.find(c=>c.key===k);
      if(k==='__value'&&(agg==='sum'||agg==='avg'))return Number(v||0);
      if(col?.numeric)return Number(v||0);
      return v??'';
    }));
    return {heads,keys,matrix};
  };

  const title=()=>reportName.trim()||(ar?source.ar:source.en);

  const exportExcel=()=>{
    const {heads,matrix}=buildMatrix();
    const aoa=[heads,...matrix];
    const ws=XLSX.utils.aoa_to_sheet(aoa);
    const wb=XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb,ws,'Report');
    XLSX.writeFile(wb,`${title()}_${end}.xlsx`);
  };

  const exportPdf=()=>{
    const {heads,matrix}=buildMatrix();
    const doc=new jsPDF({orientation:matrix[0]&&matrix[0].length>5?'landscape':'portrait'});
    doc.setFontSize(14);
    // jsPDF core fonts don't shape Arabic; use a transliteration-safe title and note.
    doc.text(String(title()),14,16);
    doc.setFontSize(9);
    doc.text(`Period: ${start} - ${end}  |  Rows: ${matrix.length}`,14,22);
    autoTable(doc,{
      head:[heads],
      body:matrix.map(row=>row.map(v=>typeof v==='number'?fmt(v):String(v))),
      startY:28, styles:{fontSize:8,cellPadding:2}, headStyles:{fillColor:[30,64,175]},
    });
    doc.save(`${title()}_${end}.pdf`);
  };

  const {heads,matrix}=rows.length?buildMatrix():{heads:[] as string[],matrix:[] as any[][]};
  const catSources=SOURCES.filter(s=>s.cat===cat);
  const catLabel=(c:string)=>{const f=CATS.find(x=>x[0]===c);return f?(ar?f[1]:f[2]):c;};
  const numericTotal=(()=>{
    if(!(groupBy&&agg!=='none'))return null;
    if(agg==='count'){return matrix.reduce((a,r)=>a+Number(r[1]||0),0);}
    if(agg==='sum'){return matrix.reduce((a,r)=>a+Number(r[1]||0),0);}
    return null;
  })();

  return <>
    <div className="kpis">
      <Kpi title={ar?'مصادر البيانات':'Data sources'} value={String(SOURCES.length)} trend="" good icon={<Table2 size={22}/>} tone="blue"/>
      <Kpi title={ar?'المصدر الحالي':'Current source'} value={ar?source.ar:source.en} trend="" good icon={<Wrench size={22}/>} tone="violet"/>
      <Kpi title={ar?'الأعمدة المختارة':'Columns'} value={String(groupBy&&agg!=='none'?2:selCols.length)} trend="" good icon={<Filter size={22}/>} tone="amber"/>
      <Kpi title={ar?'السطور':'Rows'} value={String(rows.length)} trend={numericTotal!=null?(ar?`إجمالي ${fmt(numericTotal)}`:`total ${fmt(numericTotal)}`):''} good icon={<FileText size={22}/>} tone="green"/>
    </div>

    <Panel title={ar?'مصمّم التقارير':'Report Builder'} icon={<Wrench size={18}/>}>
      <div style={{padding:12}}>
        <div style={{fontSize:13,fontWeight:700,marginBottom:6}}>{ar?'1) اختر الفئة ومصدر البيانات':'1) Pick category & data source'}</div>
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:10}}>
          {CATS.map(([k])=><button key={k} onClick={()=>setCat(k)} style={{...ghost,background:cat===k?'var(--accent, #1e40af)':'transparent',color:cat===k?'#fff':'var(--text)'}}>{catLabel(k)}</button>)}
        </div>
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:14}}>
          {catSources.length===0&&<span style={{opacity:0.6,fontSize:13}}>{ar?'لا مصادر في هذه الفئة':'No sources in this category'}</span>}
          {catSources.map(s=><button key={s.id} onClick={()=>pickSource(s)} style={{...ghost,background:source.id===s.id?'var(--panel-2, #e0e7ff)':'transparent',fontWeight:source.id===s.id?700:600}}>{ar?s.ar:s.en}</button>)}
        </div>

        <div style={{fontSize:13,fontWeight:700,marginBottom:6}}>{ar?'2) اختر الأعمدة':'2) Choose columns'}</div>
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:14}}>
          {source.cols.map(c=>{const on=selCols.includes(c.key);return(
            <button key={c.key} onClick={()=>toggleCol(c.key)} style={{...ghost,display:'flex',alignItems:'center',gap:5,background:on?'var(--accent, #1e40af)':'transparent',color:on?'#fff':'var(--text)',padding:'6px 10px'}}>
              {on?<X size={13}/>:<Plus size={13}/>}{ar?c.ar:c.en}</button>);})}
        </div>

        <div style={{fontSize:13,fontWeight:700,marginBottom:6}}>{ar?'3) التصفية':'3) Filters'}</div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',gap:12,marginBottom:14}}>
          {dateField&&<><label>{ar?'من تاريخ':'From'}<input type="date" style={field} value={start} onChange={e=>setStart(e.target.value)}/></label>
          <label>{ar?'إلى تاريخ':'To'}<input type="date" style={field} value={end} onChange={e=>setEnd(e.target.value)}/></label></>}
          <label>{ar?'عمود التصفية النصية':'Text filter column'}<select style={field} value={textFilterCol} onChange={e=>setTextFilterCol(e.target.value)}><option value="">{ar?'بدون':'None'}</option>{source.cols.map(c=><option key={c.key} value={c.key}>{ar?c.ar:c.en}</option>)}</select></label>
          {textFilterCol&&<label>{ar?'القيمة تحتوي':'Value contains'}<input style={field} value={textFilterVal} onChange={e=>setTextFilterVal(e.target.value)}/></label>}
        </div>

        <div style={{fontSize:13,fontWeight:700,marginBottom:6}}>{ar?'4) التجميع والتلخيص (اختياري)':'4) Group & summarize (optional)'}</div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',gap:12,marginBottom:14}}>
          <label>{ar?'تجميع حسب':'Group by'}<select style={field} value={groupBy} onChange={e=>setGroupBy(e.target.value)}><option value="">{ar?'بدون تجميع':'No grouping'}</option>{source.cols.filter(c=>!c.numeric).map(c=><option key={c.key} value={c.key}>{ar?c.ar:c.en}</option>)}</select></label>
          <label>{ar?'الدالة':'Function'}<select style={field} value={agg} onChange={e=>setAgg(e.target.value as Agg)}><option value="none">{ar?'بدون':'None'}</option><option value="count">{ar?'عدد':'Count'}</option><option value="sum">{ar?'مجموع':'Sum'}</option><option value="avg">{ar?'متوسط':'Average'}</option></select></label>
          {(agg==='sum'||agg==='avg')&&<label>{ar?'عمود القيمة':'Value column'}<select style={field} value={aggCol} onChange={e=>setAggCol(e.target.value)}>{source.cols.filter(c=>c.numeric).map(c=><option key={c.key} value={c.key}>{ar?c.ar:c.en}</option>)}</select></label>}
        </div>

        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',gap:12,alignItems:'end'}}>
          <label>{ar?'اسم التقرير':'Report name'}<input style={field} value={reportName} onChange={e=>setReportName(e.target.value)} placeholder={ar?source.ar:source.en}/></label>
          <button style={{...btn,display:'flex',alignItems:'center',gap:6,justifyContent:'center',opacity:busy?0.6:1}} disabled={busy} onClick={run}><Play size={16}/>{ar?'تشغيل التقرير':'Run report'}</button>
          <button style={{...ghost,display:'flex',alignItems:'center',gap:6,justifyContent:'center'}} disabled={!rows.length} onClick={exportExcel}><Download size={16}/>{ar?'تصدير Excel':'Export Excel'}</button>
          <button style={{...ghost,display:'flex',alignItems:'center',gap:6,justifyContent:'center'}} disabled={!rows.length} onClick={exportPdf}><FileText size={16}/>{ar?'تصدير PDF':'Export PDF'}</button>
        </div>
      </div>
    </Panel>

    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {heads.length>0&&<Panel title={title()} icon={<Table2 size={18}/>}>
      <div style={{overflowX:'auto',padding:'0 4px 12px'}}>
        <table style={{width:'100%',borderCollapse:'collapse'}}>
          <thead><tr>{heads.map((h,i)=><th key={i} style={th}>{h}</th>)}</tr></thead>
          <tbody>{matrix.map((r,i)=><tr key={i}>{r.map((v,j)=><td key={j} style={td}>{typeof v==='number'?fmt(v):String(v??'')}</td>)}</tr>)}</tbody>
          {numericTotal!=null&&<tfoot><tr><td style={{...td,fontWeight:700}}>{ar?'الإجمالي':'Total'}</td><td style={{...td,fontWeight:700}}>{fmt(numericTotal)}</td></tr></tfoot>}
        </table>
      </div>
    </Panel>}
  </>;
}
