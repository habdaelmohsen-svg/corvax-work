import {useEffect, useMemo, useState} from 'react';
import type {CSSProperties} from 'react';
import {FileCheck2, Printer, RefreshCw, Save, Send, ShieldCheck} from 'lucide-react';
import {apiFetch} from '../api/client';
import {Kpi, Panel, fmt} from './ui';
import page1 from '../assets/vat-return-form/page-1.png';
import page2 from '../assets/vat-return-form/page-2.png';
import page3 from '../assets/vat-return-form/page-3.png';
import page4 from '../assets/vat-return-form/page-4.png';

type VatLine={
  box_code:string;name_ar:string;base_amount:number;tax_amount:number;adjustment_base:number;adjustment_tax:number;
  reported_base_amount:number;reported_tax_amount:number;transaction_count:number;
};
type VatReturn={
  id:number;period_start:string;period_end:string;status:string;total_sales:number;total_purchases:number;
  output_vat:number;input_vat:number;net_vat_payable:number;prior_period_correction:number;carried_forward_vat:number;
  adjustment_reason?:string;classification_complete:boolean;output_reconciled:boolean;input_reconciled:boolean;lines:VatLine[];
};
type Profile={
  company_id:number;legal_name_ar?:string;legal_name_en?:string;vat_number?:string;commercial_registration?:string;
  zatca_distinguished_number?:string;tax_account_number?:string;taxpayer_identity_number?:string;registered_address?:string;
};
type FormRow={number:number;label:string;amount:number;adjustment:number;tax:number};

const iso=(d=new Date())=>d.toISOString().slice(0,10);
const monthStart=()=>{const d=new Date();return iso(new Date(d.getFullYear(),d.getMonth(),1))};
const monthEnd=()=>{const d=new Date();return iso(new Date(d.getFullYear(),d.getMonth()+1,0))};
const number=(value:unknown)=>Number(value||0);
const officialNumber=(value:unknown)=>new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}).format(number(value));
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9,background:'var(--panel)',color:'var(--text)'} as const;
const btn={padding:'9px 15px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:700,display:'inline-flex',gap:7,alignItems:'center'} as const;

async function json(url:string,init?:RequestInit){
  const response=await apiFetch(url,init);const payload=await response.json().catch(()=>({}));
  if(!response.ok){const detail=payload.detail;throw new Error(typeof detail==='string'?detail:JSON.stringify(detail||payload))}
  return payload;
}

function PrintedField({x,y,w=15.3,value,align='center'}:{x:number;y:number;w?:number;value:string;align?:CSSProperties['textAlign']}){
  return <div className="vat-printed-field" style={{left:`${x}%`,top:`${y}%`,width:`${w}%`,textAlign:align}}>{value||'غير مسجل'}</div>;
}

function VatCells({rows,page}:{rows:FormRow[];page:2|3}){
  const positions=page===2
    ? [42.46,47.09,50.77,53.74,56.71,59.80,65.26,71.32]
    : [18.59,27.14,29.63,32.36,35.69,39.96,43.88,47.09];
  const taxBoxes=new Set([1,6,7,8,9,12,13,14,15,16]);
  return <>{rows.map((row,index)=>{
    const firstSales=row.number===1;
    const firstPage3=row.number===9;
    const page3Purchase=[10,11,12].includes(row.number);
    const amountX=firstSales?45.80:firstPage3?46.47:page3Purchase?47.31:46.30;
    const adjustmentX=firstSales?27.48:firstPage3?28.15:page3Purchase?28.99:27.98;
    const taxX=firstSales?8.49:firstPage3?9.16:row.number>=12?10.0:8.99;
    return <div key={row.number}>
    {row.number<=12&&<>
      <PrintedField x={amountX} y={positions[index]} w={15.35} value={officialNumber(row.amount)}/>
      <PrintedField x={adjustmentX} y={positions[index]} w={15.25} value={officialNumber(row.adjustment)}/>
    </>}
    {taxBoxes.has(row.number)&&<PrintedField x={taxX} y={positions[index]} w={15.25} value={officialNumber(row.tax)}/>}
  </div>})}</>;
}

export function VatReturnPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [returns,setReturns]=useState<VatReturn[]>([]);const [selectedId,setSelectedId]=useState('');
  const [profile,setProfile]=useState<Profile>({company_id:companyId});const [profileDraft,setProfileDraft]=useState<Profile>({company_id:companyId});
  const [start,setStart]=useState(monthStart);const [end,setEnd]=useState(monthEnd);
  const [adjustments,setAdjustments]=useState<Record<string,string>>({});const [prior,setPrior]=useState('0');
  const [carried,setCarried]=useState('0');const [reason,setReason]=useState('');
  const [exciseRelevant,setExciseRelevant]=useState(false);const [governmentSupplies,setGovernmentSupplies]=useState(false);
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');

  const load=async(preferred?:number)=>{
    const [vatRows,taxpayer]=await Promise.all([
      json(`/api/v1/compliance/vat-returns?company_id=${companyId}`),
      json(`/api/v1/compliance/vat-taxpayer-profile?company_id=${companyId}`),
    ]);
    setReturns(vatRows||[]);setProfile(taxpayer);setProfileDraft(taxpayer);
    const next=preferred||(vatRows?.[0]?.id);if(next)setSelectedId(String(next));
  };
  useEffect(()=>{setBusy(true);load().catch(e=>setMessage(String(e.message||e))).finally(()=>setBusy(false))},[companyId]);
  const selected=useMemo(()=>returns.find(row=>String(row.id)===selectedId)||null,[returns,selectedId]);
  const lineMap=useMemo(()=>Object.fromEntries((selected?.lines||[]).map(line=>[line.box_code,line])),[selected]);
  useEffect(()=>{
    if(!selected)return;
    setAdjustments(Object.fromEntries(selected.lines.map(line=>[line.box_code,String(number(line.adjustment_base))])));
    setPrior(String(number(selected.prior_period_correction)));setCarried(String(number(selected.carried_forward_vat)));
    setReason(selected.adjustment_reason||'');
  },[selectedId,selected]);

  const combine=(codes:string[])=>codes.reduce((acc,code)=>{
    const line=lineMap[code];if(!line)return acc;
    acc.amount+=number(line.reported_base_amount);acc.adjustment+=number(line.adjustment_base);acc.tax+=number(line.reported_tax_amount);
    return acc;
  },{amount:0,adjustment:0,tax:0});
  const row=(number_:number,label:string,codes:string[]):FormRow=>({number:number_,label,...combine(codes)});
  const rows1to5=[
    row(1,'المبيعات الخاضعة للنسبة الأساسية (15%)',['SALES_STANDARD']),
    {number:2,label:'المبيعات التي تتحمل الدولة ضريبتها',amount:0,adjustment:0,tax:0},
    row(3,'المبيعات المحلية الخاضعة للنسبة الصفرية',['SALES_ZERO']),
    row(4,'الصادرات',['SALES_EXPORT']),
    row(5,'المبيعات المعفاة من الضريبة',['SALES_EXEMPT']),
  ];
  const salesTotal=rows1to5.reduce((a,r)=>({amount:a.amount+r.amount,adjustment:a.adjustment+r.adjustment,tax:a.tax+r.tax}),{amount:0,adjustment:0,tax:0});
  const purchaseRows=[
    row(7,'المشتريات الخاضعة للنسبة الأساسية (15%)',['PURCHASE_STANDARD']),
    row(8,'الاستيرادات المدفوعة عند الجمارك',['PURCHASE_IMPORTS_CUSTOMS']),
    row(9,'الاستيرادات الخاضعة للاحتساب العكسي',['PURCHASE_REVERSE_CHARGE','PURCHASE_IMPORTS_THROUGH_RETURN']),
    row(10,'المشتريات الخاضعة للنسبة الصفرية',['PURCHASE_ZERO']),
    row(11,'المشتريات المعفاة من الضريبة',['PURCHASE_EXEMPT']),
  ];
  const purchaseTotal=purchaseRows.reduce((a,r)=>({amount:a.amount+r.amount,adjustment:a.adjustment+r.adjustment,tax:a.tax+r.tax}),{amount:0,adjustment:0,tax:0});
  const page2Rows=[...rows1to5,{number:6,label:'إجمالي المبيعات',...salesTotal},...purchaseRows.slice(0,2)];
  const currentVat=number(selected?.output_vat)-number(selected?.input_vat);
  const page3Rows=[
    purchaseRows[2],purchaseRows[3],purchaseRows[4],{number:12,label:'إجمالي المشتريات',...purchaseTotal},
    {number:13,label:'إجمالي ضريبة القيمة المضافة المستحقة للفترة الحالية',amount:0,adjustment:0,tax:currentVat},
    {number:14,label:'تصحيحات من الفترات السابقة',amount:0,adjustment:0,tax:number(selected?.prior_period_correction)},
    {number:15,label:'ضريبة مرحلة من الفترات السابقة',amount:0,adjustment:0,tax:number(selected?.carried_forward_vat)},
    {number:16,label:'صافي الضريبة المستحقة أو المستردة',amount:0,adjustment:0,tax:number(selected?.net_vat_payable)},
  ];

  const generate=async()=>{
    setBusy(true);setMessage('');
    try{
      const created=await json('/api/v1/compliance/vat-return',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,period_start:start,period_end:end})});
      await load(created.id);setMessage(ar?'تم توليد مسودة الإقرار وربطها بحركات النظام والأستاذ العام':'VAT draft generated from system transactions and the general ledger');
    }catch(e:any){setMessage(String(e.message||e))}finally{setBusy(false)}
  };
  const saveProfile=async()=>{
    setBusy(true);setMessage('');
    try{
      const updated=await json(`/api/v1/compliance/vat-taxpayer-profile?company_id=${companyId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(profileDraft)});
      setProfile(updated);setProfileDraft(updated);setMessage(ar?'تم حفظ بيانات المكلف':'Taxpayer profile saved');
    }catch(e:any){setMessage(String(e.message||e))}finally{setBusy(false)}
  };
  const saveAdjustments=async()=>{
    if(!selected)return;setBusy(true);setMessage('');
    try{
      const updated=await json(`/api/v1/compliance/vat-returns/${selected.id}/adjustments`,{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({lines:selected.lines.map(line=>({box_code:line.box_code,adjustment_base:Number(adjustments[line.box_code]||0)})),
          prior_period_correction:Number(prior||0),carried_forward_vat:Number(carried||0),adjustment_reason:reason||null})});
      setReturns(rows=>rows.map(item=>item.id===updated.id?updated:item));setMessage(ar?'تم حفظ التعديلات وإعادة احتساب صافي الضريبة':'Adjustments saved and net VAT recalculated');
    }catch(e:any){setMessage(String(e.message||e))}finally{setBusy(false)}
  };
  const transition=async(action:'submit'|'approve')=>{
    if(!selected)return;setBusy(true);setMessage('');
    try{
      const updated=await json(`/api/v1/compliance/vat-returns/${selected.id}/${action}`,{method:'POST'});
      setReturns(rows=>rows.map(item=>item.id===updated.id?updated:item));setMessage(action==='submit'?(ar?'تم الإرسال للموافقة الداخلية — لم يُقدّم للهيئة':'Sent for internal approval — not filed with ZATCA'):(ar?'تم الاعتماد الداخلي — التقديم للهيئة ما زال خارجيًا':'Internally approved — ZATCA filing remains external'));
    }catch(e:any){setMessage(String(e.message||e))}finally{setBusy(false)}
  };
  const profileFields:[keyof Profile,string,string][]=[
    ['legal_name_ar','اسم المكلف','Taxpayer name'],['zatca_distinguished_number','الرقم المميز','Distinguished number'],
    ['tax_account_number','رقم الحساب الضريبي','Tax account number'],['taxpayer_identity_number','رقم الهوية','Identity number'],
    ['vat_number','الرقم الضريبي VAT','VAT number'],['commercial_registration','السجل التجاري','Commercial registration'],
    ['registered_address','العنوان المسجل','Registered address'],
  ];

  return <>
    <div className="kpis">
      <Kpi title={ar?'مسودات الإقرار':'VAT returns'} value={String(returns.length)} trend={selected?.status||'—'} good icon={<FileCheck2 size={22}/>} tone="blue"/>
      <Kpi title={ar?'ضريبة المخرجات':'Output VAT'} value={fmt(number(selected?.output_vat))} trend="" good icon={<RefreshCw size={22}/>} tone="violet"/>
      <Kpi title={ar?'ضريبة المدخلات':'Input VAT'} value={fmt(number(selected?.input_vat))} trend="" good icon={<Save size={22}/>} tone="green"/>
      <Kpi title={ar?'الصافي':'Net VAT'} value={fmt(number(selected?.net_vat_payable))} trend={ar?'مستحق / مسترد':'payable / reclaimable'} good icon={<ShieldCheck size={22}/>} tone="amber"/>
    </div>
    <div className="vat-internal-banner">{ar?'مسودة داخلية مرتبطة بالنظام — لا تعني أن الإقرار تم تقديمه إلى هيئة الزكاة والضريبة والجمارك.':'Internal system-linked draft — this does not mean the return was filed with ZATCA.'}</div>
    {message&&<div className="vat-message">{message}</div>}
    <Panel title={ar?'الفترة والإجراءات':'Period and actions'} icon={<FileCheck2 size={18}/>}>
      <div className="vat-controls-grid">
        <label>{ar?'من':'From'}<input type="date" style={field} value={start} onChange={e=>setStart(e.target.value)}/></label>
        <label>{ar?'إلى':'To'}<input type="date" style={field} value={end} onChange={e=>setEnd(e.target.value)}/></label>
        <label>{ar?'الإقرار':'Return'}<select style={field} value={selectedId} onChange={e=>setSelectedId(e.target.value)}><option value="">{ar?'لا يوجد':'None'}</option>{returns.map(item=><option key={item.id} value={item.id}>{item.period_start} — {item.period_end} · {item.status}</option>)}</select></label>
      </div>
      <div className="vat-action-row">
        <button style={btn} disabled={busy} onClick={generate}><RefreshCw size={16}/>{ar?'توليد/تحديث المسودة':'Generate / refresh'}</button>
        <button style={{...btn,background:'#475569'}} onClick={()=>window.print()}><Printer size={16}/>{ar?'طباعة / حفظ PDF':'Print / save PDF'}</button>
        {selected?.status==='DRAFT'&&<button style={{...btn,background:'#7c3aed'}} disabled={busy} onClick={()=>transition('submit')}><Send size={16}/>{ar?'إرسال للموافقة الداخلية':'Submit internally'}</button>}
        {selected?.status==='PENDING_APPROVAL'&&<button style={{...btn,background:'#047857'}} disabled={busy} onClick={()=>transition('approve')}><ShieldCheck size={16}/>{ar?'اعتماد داخلي':'Internal approval'}</button>}
      </div>
    </Panel>
    <Panel title={ar?'بيانات المكلف من النظام':'System taxpayer profile'} icon={<Save size={18}/>}>
      <div className="vat-controls-grid">{profileFields.map(([key,arabic,english])=><label key={key}>{ar?arabic:english}<input style={field} value={String(profileDraft[key]||'')} onChange={e=>setProfileDraft(value=>({...value,[key]:e.target.value}))}/></label>)}</div>
      <div className="vat-action-row"><button style={btn} disabled={busy} onClick={saveProfile}><Save size={16}/>{ar?'حفظ بيانات المكلف':'Save taxpayer profile'}</button></div>
    </Panel>
    {selected&&<Panel title={ar?'التعديلات والإفصاحات':'Adjustments and disclosures'} icon={<Save size={18}/>}>
      <div className="vat-question-grid">
        <label><input type="checkbox" checked={exciseRelevant} onChange={e=>setExciseRelevant(e.target.checked)}/>{ar?'لدي معاملات خاضعة للضريبة الانتقائية 5% خلال الفترة':'Excise-related transactions during the period'}</label>
        <label><input type="checkbox" checked={governmentSupplies} onChange={e=>setGovernmentSupplies(e.target.checked)}/>{ar?'لدي توريدات خاضعة تتحمل الدولة ضريبتها':'Government-borne VAT supplies'}</label>
      </div>
      <div className="vat-adjustment-grid">{selected.lines.filter(line=>['SALES_STANDARD','SALES_ZERO','SALES_EXPORT','SALES_EXEMPT','PURCHASE_STANDARD','PURCHASE_IMPORTS_CUSTOMS','PURCHASE_REVERSE_CHARGE','PURCHASE_ZERO','PURCHASE_EXEMPT','PURCHASE_IMPORTS_THROUGH_RETURN'].includes(line.box_code)).map(line=><label key={line.box_code}>{line.name_ar}<small>{line.box_code}</small><input type="number" step="0.01" style={field} value={adjustments[line.box_code]||'0'} onChange={e=>setAdjustments(value=>({...value,[line.box_code]:e.target.value}))}/></label>)}</div>
      <div className="vat-controls-grid">
        <label>{ar?'تصحيحات الفترات السابقة':'Prior-period correction'}<input type="number" step="0.01" style={field} value={prior} onChange={e=>setPrior(e.target.value)}/></label>
        <label>{ar?'ضريبة مرحلة من الفترات السابقة':'VAT carried forward'}<input type="number" min="0" step="0.01" style={field} value={carried} onChange={e=>setCarried(e.target.value)}/></label>
        <label>{ar?'سبب التعديل (إلزامي عند وجود تعديل)':'Adjustment reason'}<input style={field} value={reason} onChange={e=>setReason(e.target.value)}/></label>
      </div>
      <div className="vat-action-row"><button style={btn} disabled={busy||selected.status!=='DRAFT'} onClick={saveAdjustments}><Save size={16}/>{ar?'حفظ وإعادة الاحتساب':'Save and recalculate'}</button></div>
    </Panel>}

    <div className="vat-form-preview" dir="rtl">
      <section className="vat-paper vat-paper-1" style={{backgroundImage:`url(${page1})`}}>
        <div className="vat-draft-watermark">مسودة داخلية · NOT FILED</div>
        <PrintedField x={6.30} y={48.28} w={11.93} value={selected?`VAT-${selected.id}`:'—'}/>
        <PrintedField x={34.20} y={48.28} w={11.93} value={selected?.status||'جديد'}/>
        <PrintedField x={57.56} y={48.28} w={22.86} value="ضريبة القيمة المضافة"/>
        <PrintedField x={6.30} y={53.74} w={11.93} value={selected?.period_end||end}/>
        <PrintedField x={34.20} y={53.74} w={11.93} value={selected?.period_start||start}/>
        <PrintedField x={57.56} y={53.74} w={22.86} value={`${selected?.period_start||start} — ${selected?.period_end||end}`}/>
        <PrintedField x={65.46} y={65.02} w={16.13} value={profile.zatca_distinguished_number||'غير مسجل'}/>
        <PrintedField x={33.53} y={65.02} w={16.13} value={profile.tax_account_number||profile.vat_number||'غير مسجل'}/>
        <PrintedField x={9.83} y={65.02} w={11.93} value={profile.taxpayer_identity_number||profile.commercial_registration||'غير مسجل'}/>
        <PrintedField x={9.83} y={70.13} w={67.56} value={profile.legal_name_ar||'غير مسجل'} align="right"/>
        <PrintedField x={9.83} y={75.24} w={67.56} value={profile.registered_address||'غير مسجل'} align="right"/>
      </section>
      <section className="vat-paper vat-paper-2" style={{backgroundImage:`url(${page2})`}}>
        <div className="vat-draft-watermark">مسودة داخلية · NOT FILED</div>
        <div className="vat-radio-cover vat-radio-one">{exciseRelevant?'نعم ●    لا ○':'نعم ○    لا ●'}</div>
        <div className="vat-radio-cover vat-radio-two">{governmentSupplies?'نعم ●    لا ○':'نعم ○    لا ●'}</div>
        <VatCells rows={page2Rows} page={2}/>
      </section>
      <section className="vat-paper vat-paper-3" style={{backgroundImage:`url(${page3})`}}>
        <div className="vat-draft-watermark">مسودة داخلية · NOT FILED</div>
        <VatCells rows={page3Rows} page={3}/>
      </section>
      <section className="vat-paper vat-paper-4" style={{backgroundImage:`url(${page4})`}}>
        <div className="vat-draft-watermark">مسودة داخلية · NOT FILED</div>
      </section>
    </div>
  </>;
}
