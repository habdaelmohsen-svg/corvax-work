import {useEffect, useState} from 'react';
import {Users, Percent, Wallet, CheckCircle2, Clock} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Commissions live INSIDE the Sales department (a tab), not a separate section.
// Backend: /sales-commissions/... — accrual is tied to sale AND collection.
type Beneficiary={id:number;code:string;name_ar:string;name_en:string;beneficiary_type:string;default_basis:string;default_rate:number;active:boolean};
type Invoice={id:number;number?:string;invoice_date:string;total?:number;status:string};
type Accrual={id:number;number:string;beneficiary_name_ar?:string;beneficiary_type?:string;invoice_number?:string;basis:string;rate:number;amount:number;collected_ratio:number;payable_amount:number;paid_amount:number;status:string};
type Bank={id:number;bank_name_ar?:string;name_ar?:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'5px 12px',borderRadius:8,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;

const TYPES:[string,string,string][]=[['SALES_REP','مندوب مبيعات','Sales rep'],['BROKER','وسيط خارجي','Broker']];
const BASIS:[string,string,string][]=[['PERCENTAGE','نسبة %','Percentage %'],['FIXED','مبلغ ثابت','Fixed amount']];
const STATUS:Record<string,[string,string]>={PENDING:['معلّقة','Pending'],PARTIAL:['قابلة جزئيًا','Partial'],PAYABLE:['قابلة للدفع','Payable'],APPROVED:['معتمدة','Approved'],PAID:['مدفوعة','Paid'],CANCELLED:['ملغاة','Cancelled']};

export function SalesCommissionsTab({ar,companyId}:{ar:boolean;companyId:number}){
  const [sub,setSub]=useState<'beneficiaries'|'accruals'>('beneficiaries');
  const [beneficiaries,setBeneficiaries]=useState<Beneficiary[]>([]);
  const [invoices,setInvoices]=useState<Invoice[]>([]);
  const [accruals,setAccruals]=useState<Accrual[]>([]);
  const [banks,setBanks]=useState<Bank[]>([]);
  const [summary,setSummary]=useState<any>(null);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // beneficiary form
  const [code,setCode]=useState(''); const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState(''); const [bType,setBType]=useState('SALES_REP'); const [basis,setBasis]=useState('PERCENTAGE'); const [rate,setRate]=useState('2.5');
  // accrual form
  const [aBen,setABen]=useState(''); const [aInv,setAInv]=useState(''); const [aOverride,setAOverride]=useState(false); const [aBasis,setABasis]=useState('PERCENTAGE'); const [aRate,setARate]=useState('');
  // pay
  const [payBank,setPayBank]=useState('');

  const load=async()=>{
    try{
      const [b,inv,acc,bk,sum]=await Promise.all([
        json(`/api/v1/sales-commissions/beneficiaries?company_id=${companyId}`),
        json(`/api/v1/subledgers/sales-invoices?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/sales-commissions/accruals?company_id=${companyId}`),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/sales-commissions/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setBeneficiaries(b||[]); setInvoices((inv||[]).filter((x:Invoice)=>x.status==='POSTED')); setAccruals(acc||[]); setBanks(bk||[]); setSummary(sum);
      if(!aBen&&b?.length)setABen(String(b[0].id));
      if(!payBank&&bk?.length)setPayBank(String(bk[0].id));
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createBeneficiary=async()=>{
    if(!code||!nameAr||!nameEn){setMessage(ar?'الكود والاسمان إلزامية':'Code and names required');return;}
    setBusy(true);setMessage('');
    try{await json('/api/v1/sales-commissions/beneficiaries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,code,name_ar:nameAr,name_en:nameEn,beneficiary_type:bType,default_basis:basis,default_rate:Number(rate)})});
      setMessage(ar?'تمت إضافة المستفيد':'Beneficiary added');setCode('');setNameAr('');setNameEn('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createAccrual=async()=>{
    if(!aBen||!aInv){setMessage(ar?'اختر المستفيد والفاتورة':'Select beneficiary and invoice');return;}
    setBusy(true);setMessage('');
    try{const body:any={company_id:companyId,beneficiary_id:Number(aBen),sales_invoice_id:Number(aInv)};
      if(aOverride){body.basis=aBasis;body.rate=Number(aRate);}
      const r=await json('/api/v1/sales-commissions/accruals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(ar?`تم احتساب العمولة ${r.number} (${fmt(Number(r.amount))})`:`Commission ${r.number} accrued (${fmt(Number(r.amount))})`);await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const refresh=async(id:number)=>{
    setBusy(true);setMessage('');
    try{await json(`/api/v1/sales-commissions/accruals/${id}/refresh?company_id=${companyId}`,{method:'POST'});setMessage(ar?'تم تحديث نسبة التحصيل':'Collection refreshed');await load();}
    catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const approve=async(id:number)=>{
    setBusy(true);setMessage('');
    try{await json(`/api/v1/sales-commissions/accruals/${id}/approve?company_id=${companyId}`,{method:'POST'});setMessage(ar?'تم اعتماد العمولة':'Approved');await load();}
    catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const pay=async(id:number)=>{
    if(!payBank){setMessage(ar?'اختر البنك':'Select bank');return;}
    setBusy(true);setMessage('');
    try{const r=await json(`/api/v1/sales-commissions/accruals/${id}/pay`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,bank_account_id:Number(payBank)})});
      setMessage(ar?`تم صرف العمولة (${r.journal_number})`:`Paid (${r.journal_number})`);await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const label=(list:[string,string,string][],v:string)=>{const f=list.find(x=>x[0]===v);return f?(ar?f[1]:f[2]):v;};
  const st=(s:string)=>STATUS[s]?(ar?STATUS[s][0]:STATUS[s][1]):s;
  const pctStr=(r:number)=>`${Math.round(Number(r)*100)}%`;

  return <>
    <div className="kpis">
      <Kpi title={ar?'المستفيدون':'Beneficiaries'} value={summary?String(summary.beneficiaries):String(beneficiaries.length)} trend="" good icon={<Users size={22}/>} tone="blue"/>
      <Kpi title={ar?'إجمالي العمولات':'Total accrued'} value={summary?fmt(Number(summary.total_accrued)):'—'} trend="" good icon={<Percent size={22}/>} tone="violet"/>
      <Kpi title={ar?'قابلة للدفع':'Payable now'} value={summary?fmt(Number(summary.total_payable)):'—'} trend="" good icon={<Clock size={22}/>} tone="amber"/>
      <Kpi title={ar?'مدفوعة':'Paid'} value={summary?fmt(Number(summary.total_paid)):'—'} trend="" good icon={<CheckCircle2 size={22}/>} tone="green"/>
    </div>
    <div style={{display:'flex',gap:8,margin:'14px 0'}}>
      {([['beneficiaries',ar?'المستفيدون':'Beneficiaries'],['accruals',ar?'العمولات المستحقة':'Accruals']] as [typeof sub,string][]).map(([k,l])=>
        <button key={k} onClick={()=>setSub(k)} style={{...btn,background:sub===k?'var(--accent, #1e40af)':'transparent',color:sub===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>
    {message&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {sub==='beneficiaries'&&<>
      <Panel title={ar?'مستفيد عمولة جديد':'New commission beneficiary'} icon={<Users size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
          <label>{ar?'الكود':'Code'}<input style={field} value={code} onChange={e=>setCode(e.target.value)}/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
          <label>{ar?'النوع':'Type'}<select style={field} value={bType} onChange={e=>setBType(e.target.value)}>{TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'أساس العمولة':'Basis'}<select style={field} value={basis} onChange={e=>setBasis(e.target.value)}>{BASIS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{basis==='PERCENTAGE'?(ar?'النسبة %':'Rate %'):(ar?'المبلغ':'Amount')}<input type="number" style={field} value={rate} onChange={e=>setRate(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createBeneficiary}>{ar?'إضافة المستفيد':'Add beneficiary'}</button></div>
      </Panel>
      <Panel title={ar?'المستفيدون':'Beneficiaries'} icon={<Users size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'النوع':'Type',ar?'الأساس':'Basis',ar?'المعدّل':'Rate']}
          rows={beneficiaries.map(b=>[b.code,ar?b.name_ar:b.name_en,label(TYPES,b.beneficiary_type),label(BASIS,b.default_basis),b.default_basis==='PERCENTAGE'?`${b.default_rate}%`:fmt(Number(b.default_rate))])}/>
      </Panel>
    </>}

    {sub==='accruals'&&<>
      <Panel title={ar?'احتساب عمولة على فاتورة':'Accrue commission on invoice'} icon={<Percent size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
          <label>{ar?'المستفيد':'Beneficiary'}<select style={field} value={aBen} onChange={e=>setABen(e.target.value)}>{beneficiaries.map(b=><option key={b.id} value={b.id}>{b.code} — {ar?b.name_ar:b.name_en}</option>)}</select></label>
          <label>{ar?'فاتورة البيع (مرحّلة)':'Sales invoice (posted)'}<select style={field} value={aInv} onChange={e=>setAInv(e.target.value)}><option value="">{ar?'اختر...':'Select...'}</option>{invoices.map(i=><option key={i.id} value={i.id}>{i.number||i.id} — {fmt(Number(i.total||0))}</option>)}</select></label>
          <label style={{display:'flex',alignItems:'center',gap:8,marginTop:24}}><input type="checkbox" checked={aOverride} onChange={e=>setAOverride(e.target.checked)}/>{ar?'تجاوز المعدّل الافتراضي':'Override default rate'}</label>
          {aOverride&&<label>{ar?'الأساس':'Basis'}<select style={field} value={aBasis} onChange={e=>setABasis(e.target.value)}>{BASIS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>}
          {aOverride&&<label>{aBasis==='PERCENTAGE'?(ar?'النسبة %':'Rate %'):(ar?'المبلغ':'Amount')}<input type="number" style={field} value={aRate} onChange={e=>setARate(e.target.value)}/></label>}
        </div>
        <div style={{padding:'0 12px 12px',fontSize:13,opacity:0.75}}>{ar?'العمولة تُحتسب على صافي الفاتورة (دون ضريبة)، وتصبح قابلة للدفع بنسبة ما يُحصَّل من الفاتورة.':'Commission is on the net invoice (excl. VAT) and becomes payable in proportion to what is collected.'}</div>
        <div style={{padding:'0 12px 12px'}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createAccrual}>{ar?'احتساب العمولة':'Accrue commission'}</button></div>
      </Panel>
      <Panel title={ar?'صرف العمولات (يتطلب اعتمادًا)':'Pay commissions (approval required)'} icon={<Wallet size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'بنك الصرف':'Payment bank'}<select style={field} value={payBank} onChange={e=>setPayBank(e.target.value)}>{banks.map(b=><option key={b.id} value={b.id}>{b.bank_name_ar||b.name_ar}</option>)}</select></label>
        </div>
      </Panel>
      <Panel title={ar?'العمولات المستحقة':'Commission accruals'} icon={<Percent size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'المستفيد':'Beneficiary',ar?'الفاتورة':'Invoice',ar?'العمولة':'Amount',ar?'المُحصَّل':'Collected',ar?'قابل للدفع':'Payable',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={accruals.map(a=>[a.number,a.beneficiary_name_ar||'—',a.invoice_number||'—',fmt(Number(a.amount)),pctStr(a.collected_ratio),fmt(Number(a.payable_amount)),st(a.status),
            <span key={a.id} style={{display:'flex',gap:6}}>
              {(a.status==='PENDING'||a.status==='PARTIAL')&&<button style={smallBtn} disabled={busy} onClick={()=>refresh(a.id)}>{ar?'تحديث':'Refresh'}</button>}
              {(a.status==='PARTIAL'||a.status==='PAYABLE')&&<button style={smallBtn} disabled={busy} onClick={()=>approve(a.id)}>{ar?'اعتماد':'Approve'}</button>}
              {a.status==='APPROVED'&&<button style={{...smallBtn,background:'#059669'}} disabled={busy} onClick={()=>pay(a.id)}>{ar?'صرف':'Pay'}</button>}
              {a.status==='PAID'&&'✓'}
            </span>])}/>
      </Panel>
    </>}
  </>;
}
