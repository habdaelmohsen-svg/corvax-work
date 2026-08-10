import {useEffect, useMemo, useState} from 'react';
import {AlertTriangle, Building2, ClipboardCheck, FileSpreadsheet, Search, Send, ShieldCheck, Trophy} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init);const x=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const addDays=(n:number)=>{const d=new Date();d.setDate(d.getDate()+n);return iso(d)};
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12} as const;
const btn={padding:'8px 13px',borderRadius:8,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={...btn,padding:'4px 9px',fontSize:12} as const;

type ActualPurchase={
  unit_price:number|string;quantity:number|string;purchase_date:string;goods_receipt_number:string;
  purchase_order_number:string;supplier_id:number;supplier_code:string;supplier_name_ar:string;
  supplier_name_en:string;supplier_vat_number?:string|null;source:'POSTED_GOODS_RECEIPT';
};
type LastPurchaseResponse={
  item_id:number;item_code:string;
  supplier_last_purchase:ActualPurchase|null;
  company_last_purchase:ActualPurchase|null;
};

export function ProcurementWorkflowTab({ar,companyId}:{ar:boolean;companyId:number}){
  const [requisitions,setRequisitions]=useState<any[]>([]);const [rfqs,setRfqs]=useState<any[]>([]);
  const [items,setItems]=useState<any[]>([]);const [warehouses,setWarehouses]=useState<any[]>([]);const [suppliers,setSuppliers]=useState<any[]>([]);
  const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);const [search,setSearch]=useState('');
  const [requestDate,setRequestDate]=useState(iso());const [neededBy,setNeededBy]=useState(addDays(14));const [warehouse,setWarehouse]=useState('');
  const [department,setDepartment]=useState('');const [justification,setJustification]=useState('');const [item,setItem]=useState('');
  const [quantity,setQuantity]=useState('');const [estimatedPrice,setEstimatedPrice]=useState('');const [specifications,setSpecifications]=useState('');
  const [suggestedSupplier,setSuggestedSupplier]=useState('');
  const [lastPurchase,setLastPurchase]=useState<LastPurchaseResponse|null>(null);const [lastPurchaseLoading,setLastPurchaseLoading]=useState(false);
  const [rejectReason,setRejectReason]=useState('');
  const [rfqReq,setRfqReq]=useState('');const [issueDate,setIssueDate]=useState(iso());const [closingDate,setClosingDate]=useState(addDays(7));
  const [selectedSuppliers,setSelectedSuppliers]=useState<number[]>([]);
  const [quoteRfq,setQuoteRfq]=useState('');const [quoteSupplier,setQuoteSupplier]=useState('');const [quoteRef,setQuoteRef]=useState('');
  const [quoteDate,setQuoteDate]=useState(iso());const [validUntil,setValidUntil]=useState(addDays(30));const [leadDays,setLeadDays]=useState('7');
  const [paymentTerms,setPaymentTerms]=useState('30 days');const [prices,setPrices]=useState<Record<number,string>>({});
  const [awardReason,setAwardReason]=useState('Lowest technically compliant total cost');
  const [workflow,setWorkflow]=useState<any>({summary:{},rows:[]});const [selectedFlow,setSelectedFlow]=useState<any>(null);
  const [profileSupplier,setProfileSupplier]=useState('');const [profile,setProfile]=useState<any>(null);
  const [profileDraft,setProfileDraft]=useState<any>({commercial_registration:'',contact_name:'',contact_email:'',contact_phone:'',payment_terms_days:30,delivery_score:0,quality_score:0,price_score:0,rejection_rate:0});
  const [pendingIban,setPendingIban]=useState('');

  const load=async()=>{
    try{
      const [pr,rfq,it,wh,pa,flow]=await Promise.all([
        json(`/api/v1/procurement/requisitions?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/procurement/rfqs?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/items?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/parties?company_id=${companyId}&party_type=SUPPLIER`).catch(()=>[]),
        json(`/api/v1/procurement/workflow-center?company_id=${companyId}`).catch(()=>({summary:{},rows:[]})),
      ]);
      setRequisitions(pr||[]);setRfqs(rfq||[]);setItems(it||[]);setWarehouses(wh||[]);setSuppliers(pa||[]);setWorkflow(flow||{summary:{},rows:[]});
      if(!profileSupplier&&pa?.length)setProfileSupplier(String(pa[0].id));
      if(!warehouse&&wh?.length)setWarehouse(String(wh[0].id));if(!item&&it?.length)setItem(String(it[0].id));
      const approved=(pr||[]).find((x:any)=>x.status==='APPROVED'&&!(rfq||[]).some((q:any)=>q.requisition_id===x.id));
      if(!rfqReq&&approved)setRfqReq(String(approved.id));
      const issued=(rfq||[]).find((x:any)=>x.status==='ISSUED');if(!quoteRfq&&issued)setQuoteRfq(String(issued.id));
    }catch(e:any){setMessage(String(e.message||e))}
  };
  useEffect(()=>{void load()},[companyId]);

  useEffect(()=>{
    if(!profileSupplier){setProfile(null);return}let active=true;
    json(`/api/v1/procurement/suppliers/${profileSupplier}/profile?company_id=${companyId}`).then(x=>{if(!active)return;setProfile(x);setProfileDraft({commercial_registration:x.commercial_registration||'',contact_name:x.contact_name||'',contact_email:x.contact_email||'',contact_phone:x.contact_phone||'',payment_terms_days:Number(x.payment_terms_days||30),delivery_score:Number(x.delivery_score||0),quality_score:Number(x.quality_score||0),price_score:Number(x.price_score||0),rejection_rate:Number(x.rejection_rate||0)})}).catch(e=>active&&setMessage(String(e.message||e)));
    return()=>{active=false};
  },[companyId,profileSupplier]);

  useEffect(()=>{
    if(!item){setLastPurchase(null);return;}
    let active=true;setLastPurchaseLoading(true);
    const supplierQuery=suggestedSupplier?`&supplier_id=${Number(suggestedSupplier)}`:'';
    json(`/api/v1/procurement/items/${Number(item)}/last-purchase?company_id=${companyId}${supplierQuery}`)
      .then(result=>{if(active)setLastPurchase(result);})
      .catch(()=>{if(active)setLastPurchase(null);})
      .finally(()=>{if(active)setLastPurchaseLoading(false);});
    return()=>{active=false;};
  },[companyId,item,suggestedSupplier]);

  const selectedRfq=rfqs.find(r=>String(r.id)===quoteRfq);
  const selectedSupplier=suppliers.find(s=>String(s.id)===suggestedSupplier);
  const supplierPurchase=lastPurchase?.supplier_last_purchase||null;
  const priceReference=supplierPurchase||lastPurchase?.company_last_purchase||null;
  const fallbackToOtherSupplier=Boolean(suggestedSupplier&&!supplierPurchase&&lastPurchase?.company_last_purchase);
  useEffect(()=>{
    if(!selectedRfq)return;
    const invited=selectedRfq.suppliers||[];if(!invited.some((s:any)=>String(s.id)===quoteSupplier))setQuoteSupplier(invited[0]?String(invited[0].id):'');
    setPrices(current=>{const next={...current};for(const line of selectedRfq.lines||[])if(next[line.id]===undefined)next[line.id]='';return next});
  },[quoteRfq,rfqs]);

  const act=async(url:string,method='POST',body?:any,success='')=>{
    setBusy(true);setMessage('');try{const result=await json(url,{method,headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});setMessage(success);await load();return result;}
    catch(e:any){setMessage(String(e.message||e));return null}finally{setBusy(false)}
  };
  const createRequisition=async()=>{
    if(!warehouse||!item||!quantity||!department.trim()||!justification.trim()){setMessage(ar?'أكمل بيانات طلب الشراء':'Complete the requisition');return}
    await act('/api/v1/procurement/requisitions','POST',{company_id:companyId,request_date:requestDate,needed_by:neededBy,warehouse_id:Number(warehouse),suggested_supplier_id:suggestedSupplier?Number(suggestedSupplier):null,department,justification,lines:[{item_id:Number(item),quantity:Number(quantity),estimated_unit_price:Number(estimatedPrice)||0,specifications:specifications||null}]},ar?'تم حفظ طلب الشراء كمسودة':'Purchase requisition saved as draft');
    setQuantity('');setEstimatedPrice('');setSpecifications('');
  };
  const createRfq=async()=>{
    if(!rfqReq||selectedSuppliers.length<2){setMessage(ar?'اختر طلبًا معتمدًا وموردين اثنين على الأقل':'Select an approved requisition and at least two suppliers');return}
    await act('/api/v1/procurement/rfqs','POST',{company_id:companyId,requisition_id:Number(rfqReq),issue_date:issueDate,closing_date:closingDate,supplier_ids:selectedSuppliers},ar?'تم إنشاء طلب عرض السعر كمسودة':'RFQ created as draft');
  };
  const recordQuote=async()=>{
    if(!selectedRfq||!quoteSupplier||!quoteRef.trim()||(selectedRfq.lines||[]).some((l:any)=>!Number(prices[l.id]))){setMessage(ar?'أكمل المورد والمرجع وسعر كل بند':'Complete supplier, reference and every line price');return}
    await act('/api/v1/procurement/quotations','POST',{company_id:companyId,rfq_id:selectedRfq.id,supplier_id:Number(quoteSupplier),supplier_reference:quoteRef,quote_date:quoteDate,valid_until:validUntil,lead_time_days:Number(leadDays)||0,payment_terms:paymentTerms,lines:(selectedRfq.lines||[]).map((l:any)=>({rfq_line_id:l.id,unit_price:Number(prices[l.id]),vat_rate:15}))},ar?'تم تسجيل عرض المورد':'Supplier quotation recorded');
    setQuoteRef('');setPrices({});
  };
  const saveProfile=async()=>{if(!profileSupplier)return;const x=await act(`/api/v1/procurement/suppliers/${profileSupplier}/profile?company_id=${companyId}`,'PUT',profileDraft,ar?'تم حفظ ملف المورد وسجلت التعديلات للمراجعة':'Supplier profile saved with audit trail');if(x)setProfile(x);};
  const requestIban=async()=>{if(!profileSupplier||pendingIban.replace(/\s/g,'').length<15){setMessage(ar?'أدخل IBAN صحيحًا':'Enter a valid IBAN');return}const x=await act(`/api/v1/procurement/suppliers/${profileSupplier}/iban-change?company_id=${companyId}`,'POST',{iban:pendingIban,reason:'Supplier bank destination change independently verified by procurement'},ar?'أُرسل تغيير IBAN لاعتماد مستقل؛ السداد على الحساب الجديد محظور حتى الاعتماد':'IBAN change sent for independent approval; new destination remains blocked');if(x)setProfile(x);setPendingIban('');};
  const approveIban=async()=>{if(!profileSupplier)return;const x=await act(`/api/v1/procurement/suppliers/${profileSupplier}/iban-change/approve?company_id=${companyId}`,'POST',undefined,ar?'تم اعتماد IBAN من مستخدم مستقل':'IBAN independently approved');if(x)setProfile(x);};
  const normalized=search.trim().toLowerCase();
  const shownPr=useMemo(()=>!normalized?requisitions:requisitions.filter(r=>[r.number,r.department,r.justification,r.status,r.suggested_supplier_code,r.suggested_supplier_name_ar,r.suggested_supplier_name_en,r.suggested_supplier_vat_number].join(' ').toLowerCase().includes(normalized)),[requisitions,normalized]);
  const shownRfqs=useMemo(()=>!normalized?rfqs:rfqs.filter(r=>[r.number,r.requisition_number,r.status,...(r.suppliers||[]).map((s:any)=>s.code)].join(' ').toLowerCase().includes(normalized)),[rfqs,normalized]);
  const comparisonQuotes=(selectedRfq?.quotations||[]).slice().sort((a:any,b:any)=>Number(a.total)-Number(b.total));
  const approvedWithoutRfq=requisitions.filter(r=>r.status==='APPROVED'&&!rfqs.some(q=>q.requisition_id===r.id));

  return <>
    <Panel title={ar?'مركز متابعة دورة الشراء من الاحتياج حتى السداد':'Procure-to-pay workflow control center'} icon={<ShieldCheck size={18}/> }>
      <div className="kpis" style={{padding:12}}>
        <Kpi title={ar?'الدورات':'Cycles'} value={String(workflow.summary?.total||0)} trend={ar?'مستندات مترابطة':'Linked documents'} good/>
        <Kpi title={ar?'مكتملة':'Complete'} value={String(workflow.summary?.complete||0)} trend={ar?'حتى تخصيص السداد':'Through payment allocation'} good/>
        <Kpi title={ar?'متوقفة +3 أيام':'Stalled +3 days'} value={String(workflow.summary?.stalled||0)} trend={ar?'تحتاج تدخل المالك الحالي':'Current owner action'} good={!workflow.summary?.stalled}/>
        <Kpi title={ar?'مخاطر رقابية':'Control risks'} value={String(workflow.summary?.at_risk||0)} trend={ar?'سعر/تأخير/استلام/سداد':'Price/delay/receipt/payment'} good={!workflow.summary?.at_risk}/>
      </div>
      <DataTable headers={[ar?'طلب الشراء':'PR',ar?'المورد':'Supplier',ar?'المرحلة':'Stage',ar?'المالك الحالي':'Current owner',ar?'مدة التوقف':'Stalled',ar?'القيمة':'Value',ar?'فرق السعر':'Price variance',ar?'الرقابة':'Controls',ar?'التفاصيل':'Drill-through']} rows={(workflow.rows||[]).map((x:any)=>[
        x.requisition.number,(ar?x.supplier_name_ar:x.supplier_name_en)||'—',x.stage,x.current_owner,`${x.stalled_days} ${ar?'يوم':'days'}`,fmt(Number(x.po_total||x.invoiced_total||0)),x.price_variance_percent==null?'—':`${fmt(Number(x.price_variance_percent))}%`,
        x.control_flags?.length?<span style={{color:'#b45309',fontWeight:700}}><AlertTriangle size={14}/> {x.control_flags.join(' · ')}</span>:'✓',
        <button data-testid={`workflow-drill-${x.requisition.id}`} key={x.requisition.id} style={smallBtn} onClick={()=>setSelectedFlow(selectedFlow?.requisition?.id===x.requisition.id?null:x)}>{ar?'فتح التسلسل':'Open timeline'}</button>
      ])}/>
      {selectedFlow&&<div data-testid="workflow-drill-through" style={{margin:12,padding:14,border:'1px solid var(--border)',borderRadius:10,background:'var(--panel-2,#f8fafc)'}}>
        <strong>{selectedFlow.requisition.number} — {ar?'تسلسل المستندات والمبالغ':'Document and amount timeline'}</strong>
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:10}}>{[
          selectedFlow.requisition,selectedFlow.rfq,selectedFlow.purchase_order,...(selectedFlow.receipts||[]),...(selectedFlow.invoices||[]),...(selectedFlow.payments||[]),
        ].filter(Boolean).map((d:any,i:number)=><span key={`${d.path}-${i}`} style={{padding:'7px 10px',borderRadius:8,border:'1px solid var(--border)'}}>{d.number} · {d.status||'POSTED'}</span>)}</div>
        <small style={{display:'block',marginTop:10}}>{ar?'المطلوب/المستلم:':'Ordered/received:'} {fmt(Number(selectedFlow.ordered_quantity))}/{fmt(Number(selectedFlow.received_quantity))} · {ar?'مفوتر:':'Invoiced:'} {fmt(Number(selectedFlow.invoiced_total))} · {ar?'مسدد:':'Paid:'} {fmt(Number(selectedFlow.paid_total))} · {ar?'متبقي:':'Outstanding:'} {fmt(Number(selectedFlow.outstanding_total))}</small>
      </div>}
    </Panel>

    <Panel title={ar?'ملف المورد الاحترافي والرقابة البنكية':'Professional supplier profile and bank controls'} icon={<Building2 size={18}/> }>
      <div style={grid}>
        <label>{ar?'المورد':'Supplier'}<select data-testid="supplier-profile-select" style={field} value={profileSupplier} onChange={e=>setProfileSupplier(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{s.code} — {ar?s.name_ar:s.name_en}</option>)}</select></label>
        <label>{ar?'السجل التجاري':'Commercial registration'}<input style={field} value={profileDraft.commercial_registration} onChange={e=>setProfileDraft({...profileDraft,commercial_registration:e.target.value})}/></label>
        <label>{ar?'مسؤول التواصل':'Contact'}<input style={field} value={profileDraft.contact_name} onChange={e=>setProfileDraft({...profileDraft,contact_name:e.target.value})}/></label>
        <label>{ar?'البريد':'Email'}<input style={field} value={profileDraft.contact_email} onChange={e=>setProfileDraft({...profileDraft,contact_email:e.target.value})}/></label>
        <label>{ar?'الهاتف':'Phone'}<input style={field} value={profileDraft.contact_phone} onChange={e=>setProfileDraft({...profileDraft,contact_phone:e.target.value})}/></label>
        <label>{ar?'شروط السداد (يوم)':'Payment terms (days)'}<input type="number" style={field} value={profileDraft.payment_terms_days} onChange={e=>setProfileDraft({...profileDraft,payment_terms_days:Number(e.target.value)})}/></label>
        {(['delivery_score','quality_score','price_score','rejection_rate'] as const).map(k=><label key={k}>{ar?({delivery_score:'الالتزام بالتوريد',quality_score:'الجودة',price_score:'تنافسية السعر',rejection_rate:'نسبة الرفض %'} as any)[k]:k.replace(/_/g,' ')}<input type="number" min="0" max="100" style={field} value={profileDraft[k]} onChange={e=>setProfileDraft({...profileDraft,[k]:Number(e.target.value)})}/></label>)}
      </div>
      {profile&&<div style={{padding:'0 12px 10px',display:'flex',gap:14,flexWrap:'wrap'}}><span>{ar?'ضريبي:':'VAT:'} {profile.vat_number||'—'}</span><span>{ar?'التقييم:':'Score:'} {fmt(Number(profile.overall_score||0))}%</span><span>{ar?'الاستلامات:':'Receipts:'} {profile.receipt_count}</span><span>{ar?'قيمة الاستلامات:':'Received value:'} {fmt(Number(profile.lifetime_received_value||0))}</span><span>{ar?'الفواتير:':'Invoices:'} {profile.invoice_count}</span></div>}
      {profile?.item_price_indicators?.length>0&&<DataTable headers={[ar?'الصنف':'Item',ar?'آخر سعر فعلي':'Last actual price',ar?'متوسط آخر 3':'Average last 3',ar?'متوسط آخر 5':'Average last 5',ar?'آخر استلام':'Last receipt']} rows={profile.item_price_indicators.map((x:any)=>[`${x.item_code} — ${ar?x.item_name_ar:x.item_name_en}`,fmt(Number(x.last_price)),fmt(Number(x.average_last_3_prices)),fmt(Number(x.average_last_5_prices)),x.last_receipt_date])}/>}
      <div style={{padding:'0 12px 12px',display:'flex',gap:8,alignItems:'end',flexWrap:'wrap'}}><button data-testid="supplier-profile-save" style={btn} disabled={busy} onClick={saveProfile}>{ar?'حفظ الملف':'Save profile'}</button><label style={{minWidth:260}}>{ar?'طلب IBAN جديد (لا يُفعّل قبل الاعتماد)':'New IBAN request (inactive until approval)'}<input data-testid="supplier-iban-input" style={field} value={pendingIban} onChange={e=>setPendingIban(e.target.value)}/></label><button data-testid="supplier-iban-request" style={{...btn,background:'#b45309'}} disabled={busy} onClick={requestIban}>{ar?'إرسال للمراجعة':'Request review'}</button>{profile?.iban_status==='PENDING_APPROVAL'&&<button data-testid="supplier-iban-approve" style={{...btn,background:'#047857'}} disabled={busy} onClick={approveIban}>{ar?'اعتماد مستقل':'Independent approve'}</button>}</div>
      {profile&&<div data-testid="supplier-iban-risk" style={{padding:12,background:profile.iban_change_risk==='HIGH'?'#fff1f2':'var(--panel-2,#f8fafc)'}}>{ar?'حالة IBAN:':'IBAN status:'} <strong>{profile.iban_status}</strong> · {ar?'المعتمد:':'Approved:'} {profile.approved_iban_masked||'—'} · {ar?'المعلق:':'Pending:'} {profile.pending_iban_masked||'—'} · {ar?'المخاطر:':'Risk:'} <strong>{profile.iban_change_risk}</strong></div>}
    </Panel>

    <div className="kpis">
      <Kpi title={ar?'طلبات الشراء':'Requisitions'} value={String(requisitions.length)} trend={ar?'من الاحتياج حتى الاعتماد':'Need to approval'} good/>
      <Kpi title={ar?'طلبات عروض الأسعار':'RFQs'} value={String(rfqs.length)} trend={ar?'منافسة موثقة':'Documented competition'} good/>
      <Kpi title={ar?'عروض الموردين':'Supplier quotes'} value={String(rfqs.reduce((n,r)=>n+(r.quotations?.length||0),0))} trend={ar?'مقارنة سعر ومدة':'Price and lead-time comparison'} good/>
      <Kpi title={ar?'ترسيات مكتملة':'Awards'} value={String(rfqs.filter(r=>r.status==='AWARDED').length)} trend={ar?'تُنشئ أمر شراء مسودة':'Creates draft PO'} good/>
    </div>
    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)'}}>{message}</div>}
    <Panel title={ar?'البحث في الطلبات والعروض':'Search requisitions and RFQs'} icon={<Search size={18}/> }><div style={{padding:12}}><input data-testid="procurement-search" style={field} value={search} onChange={e=>setSearch(e.target.value)} placeholder={ar?'رقم الطلب، القسم، المورد، الحالة...':'Number, department, supplier, status...'}/><span data-testid="procurement-search-count">{shownPr.length}/{requisitions.length} PR • {shownRfqs.length}/{rfqs.length} RFQ</span></div></Panel>

    <Panel title={ar?'طلب شراء جديد':'New purchase requisition'} icon={<ClipboardCheck size={18}/> }>
      <div style={grid}>
        <label>{ar?'تاريخ الطلب':'Request date'}<input data-testid="pr-date" type="date" style={field} value={requestDate} onChange={e=>setRequestDate(e.target.value)}/></label>
        <label>{ar?'مطلوب قبل':'Needed by'}<input data-testid="pr-needed" type="date" style={field} value={neededBy} onChange={e=>setNeededBy(e.target.value)}/></label>
        <label>{ar?'المستودع':'Warehouse'}<select data-testid="pr-warehouse" style={field} value={warehouse} onChange={e=>setWarehouse(e.target.value)}>{warehouses.map(w=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
        <label>{ar?'المورد المقترح (اختياري)':'Suggested supplier (optional)'}<select data-testid="pr-suggested-supplier" style={field} value={suggestedSupplier} onChange={e=>setSuggestedSupplier(e.target.value)}><option value="">{ar?'بدون مورد مقترح — تختاره المشتريات لاحقًا':'No suggestion — procurement selects later'}</option>{suppliers.map(s=><option key={s.id} value={s.id}>{s.code} — {ar?s.name_ar:s.name_en}</option>)}</select></label>
        <label>{ar?'الرقم الضريبي للمورد المقترح':'Suggested supplier VAT number'}<input data-testid="pr-supplier-vat" style={field} value={selectedSupplier?.vat_number||''} readOnly placeholder={ar?'يظهر تلقائيًا من بطاقة المورد':'Loaded from supplier master data'}/></label>
        <label>{ar?'القسم الطالب':'Requesting department'}<input data-testid="pr-department" style={field} value={department} onChange={e=>setDepartment(e.target.value)}/></label>
        <label>{ar?'مبرر الشراء':'Justification'}<input data-testid="pr-justification" style={field} value={justification} onChange={e=>setJustification(e.target.value)}/></label>
        <label>{ar?'الصنف':'Item'}<select data-testid="pr-item" style={field} value={item} onChange={e=>setItem(e.target.value)}>{items.map(i=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
        <label>{ar?'الكمية':'Quantity'}<input data-testid="pr-quantity" type="number" min="0" style={field} value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
        <label>{ar?'السعر التقديري':'Estimated unit price'}<input data-testid="pr-estimated-price" type="number" min="0" style={field} value={estimatedPrice} onChange={e=>setEstimatedPrice(e.target.value)}/></label>
        <label>{ar?'المواصفات':'Specifications'}<input data-testid="pr-specifications" style={field} value={specifications} onChange={e=>setSpecifications(e.target.value)}/></label>
      </div>
      <div data-testid="pr-last-purchase" style={{margin:'0 12px 12px',padding:12,border:'1px solid var(--border)',borderRadius:10,background:'var(--panel-2, #f1f5f9)',display:'flex',gap:12,alignItems:'center',justifyContent:'space-between',flexWrap:'wrap'}}>
        <div>
          <strong>{ar?'آخر سعر شراء فعلي مرحّل':'Latest posted actual purchase price'}</strong>
          <div style={{fontSize:20,fontWeight:800,marginTop:4}}>{lastPurchaseLoading?(ar?'جارٍ التحميل...':'Loading...'):priceReference?fmt(Number(priceReference.unit_price)):(ar?'لا يوجد استلام سابق':'No previous receipt')}</div>
          {priceReference&&<small style={{display:'block',marginTop:3,opacity:.78}}>{priceReference.goods_receipt_number} · {priceReference.purchase_date} · {ar?priceReference.supplier_name_ar:priceReference.supplier_name_en} · {ar?'ضريبي:':'VAT:'} {priceReference.supplier_vat_number||'—'}</small>}
          {fallbackToOtherSupplier&&<small style={{display:'block',marginTop:4,color:'#b45309'}}>{ar?'لا يوجد استلام سابق من المورد المقترح؛ السعر المعروض هو آخر استلام للصنف من مورد آخر.':'The suggested supplier has no prior receipt; this is the latest receipt from another supplier.'}</small>}
        </div>
        <button data-testid="pr-use-last-price" type="button" style={{...smallBtn,opacity:priceReference?1:.5}} disabled={!priceReference} onClick={()=>priceReference&&setEstimatedPrice(String(priceReference.unit_price))}>{ar?'استخدامه كسعر تقديري':'Use as estimate'}</button>
      </div>
      <div style={{padding:12}}><button data-testid="pr-create" style={btn} disabled={busy} onClick={createRequisition}>{ar?'حفظ الطلب':'Save requisition'}</button></div>
    </Panel>
    <Panel title={ar?'سجل طلبات الشراء':'Purchase requisition register'} icon={<ClipboardCheck size={18}/> }>
      <div style={{padding:'0 12px 10px'}}><input data-testid="pr-reject-reason" style={field} value={rejectReason} onChange={e=>setRejectReason(e.target.value)} placeholder={ar?'سبب الرفض عند استخدام زر رفض (5 أحرف على الأقل)':'Rejection reason when using Reject (minimum 5 chars)'}/></div>
      <DataTable headers={[ar?'الرقم':'Number',ar?'القسم':'Department',ar?'المورد المقترح':'Suggested supplier',ar?'الرقم الضريبي':'VAT number',ar?'التاريخ':'Date',ar?'المطلوب':'Needed',ar?'التقديري':'Estimate',ar?'الحالة':'Status',ar?'إجراء':'Action']} rows={shownPr.map(r=>[r.number,r.department,(ar?r.suggested_supplier_name_ar:r.suggested_supplier_name_en)||r.suggested_supplier_name_ar||r.suggested_supplier_name_en||'—',r.suggested_supplier_vat_number||'—',r.request_date,r.needed_by,fmt(Number(r.estimated_total||0)),r.status,
        <span data-testid={`pr-actions-${r.id}`} key={r.id} style={{display:'flex',gap:5,flexWrap:'wrap'}}><span data-testid={`pr-status-${r.id}`}>{r.status}</span>{r.status==='DRAFT'&&<button data-testid={`pr-submit-${r.id}`} style={smallBtn} disabled={busy} onClick={()=>act(`/api/v1/procurement/requisitions/${r.id}/submit`,'POST',undefined,ar?'تم إرسال الطلب':'Requisition submitted')}>{ar?'إرسال':'Submit'}</button>}{r.status==='SUBMITTED'&&<><button data-testid={`pr-approve-${r.id}`} style={smallBtn} disabled={busy} onClick={()=>act(`/api/v1/procurement/requisitions/${r.id}/approve`,'POST',undefined,ar?'تم اعتماد الطلب':'Requisition approved')}>{ar?'اعتماد':'Approve'}</button><button data-testid={`pr-reject-${r.id}`} style={{...smallBtn,background:'#b91c1c'}} disabled={busy||rejectReason.trim().length<5} onClick={()=>act(`/api/v1/procurement/requisitions/${r.id}/reject`,'POST',{reason:rejectReason},ar?'تم رفض الطلب':'Requisition rejected')}>{ar?'رفض':'Reject'}</button></>}{r.status==='APPROVED'&&(rfqs.some(q=>q.requisition_id===r.id)?'RFQ ✓':(ar?'جاهز لـRFQ':'RFQ ready'))}</span>])}/>
    </Panel>

    <Panel title={ar?'إنشاء طلب عرض سعر':'Create request for quotation'} icon={<Send size={18}/> }>
      <div style={grid}>
        <label>{ar?'طلب الشراء المعتمد':'Approved requisition'}<select data-testid="rfq-pr" style={field} value={rfqReq} onChange={e=>setRfqReq(e.target.value)}><option value="">—</option>{approvedWithoutRfq.map(r=><option key={r.id} value={r.id}>{r.number} — {r.department}{r.suggested_supplier_name_ar?` — ${r.suggested_supplier_name_ar}`:''}</option>)}</select></label>
        <label>{ar?'تاريخ الإصدار':'Issue date'}<input type="date" style={field} value={issueDate} onChange={e=>setIssueDate(e.target.value)}/></label>
        <label>{ar?'إغلاق العروض':'Closing date'}<input type="date" style={field} value={closingDate} onChange={e=>setClosingDate(e.target.value)}/></label>
      </div><div style={{padding:'0 12px 12px'}}><strong>{ar?'الموردون المدعوون (اثنان على الأقل)':'Invited suppliers (at least two)'}</strong><div style={{display:'flex',gap:12,flexWrap:'wrap',marginTop:8}}>{suppliers.map(s=><label key={s.id}><input data-testid={`rfq-supplier-${s.id}`} type="checkbox" checked={selectedSuppliers.includes(s.id)} onChange={e=>setSelectedSuppliers(v=>e.target.checked?[...v,s.id]:v.filter(id=>id!==s.id))}/> {s.code} — {ar?s.name_ar:s.name_en} · {ar?'ضريبي:':'VAT:'} {s.vat_number||'—'}</label>)}</div></div>
      <div style={{padding:12}}><button data-testid="rfq-create" style={btn} disabled={busy} onClick={createRfq}>{ar?'إنشاء RFQ':'Create RFQ'}</button></div>
    </Panel>
    <Panel title={ar?'سجل RFQ':'RFQ register'} icon={<FileSpreadsheet size={18}/> }>
      <DataTable headers={[ar?'الرقم':'Number',ar?'طلب الشراء':'PR',ar?'الموردون':'Suppliers',ar?'العروض':'Quotes',ar?'الحالة':'Status',ar?'إجراء':'Action']} rows={shownRfqs.map(r=>[r.number,r.requisition_number,(r.suppliers||[]).map((s:any)=>s.code).join(', '),String(r.quotations?.length||0),<span data-testid={`rfq-status-${r.id}`}>{r.status}</span>,r.status==='DRAFT'?<button data-testid={`rfq-issue-${r.id}`} key={r.id} style={smallBtn} disabled={busy} onClick={()=>act(`/api/v1/procurement/rfqs/${r.id}/issue`,'POST',undefined,ar?'تم إصدار RFQ':'RFQ issued')}>{ar?'إصدار':'Issue'}</button>:r.status])}/>
    </Panel>

    <Panel title={ar?'تسجيل عرض مورد':'Record supplier quotation'} icon={<FileSpreadsheet size={18}/> }>
      <div style={grid}>
        <label>RFQ<select data-testid="quote-rfq" style={field} value={quoteRfq} onChange={e=>setQuoteRfq(e.target.value)}><option value="">—</option>{rfqs.filter(r=>r.status==='ISSUED').map(r=><option key={r.id} value={r.id}>{r.number}</option>)}</select></label>
        <label>{ar?'المورد':'Supplier'}<select data-testid="quote-supplier" style={field} value={quoteSupplier} onChange={e=>setQuoteSupplier(e.target.value)}><option value="">—</option>{(selectedRfq?.suppliers||[]).map((s:any)=><option key={s.id} value={s.id}>{s.code} — {ar?s.name_ar:s.name_en}</option>)}</select></label>
        <label>{ar?'مرجع عرض المورد':'Supplier quote reference'}<input data-testid="quote-reference" style={field} value={quoteRef} onChange={e=>setQuoteRef(e.target.value)}/></label>
        <label>{ar?'تاريخ العرض':'Quote date'}<input type="date" style={field} value={quoteDate} onChange={e=>setQuoteDate(e.target.value)}/></label>
        <label>{ar?'صالح حتى':'Valid until'}<input type="date" style={field} value={validUntil} onChange={e=>setValidUntil(e.target.value)}/></label>
        <label>{ar?'مدة التوريد (يوم)':'Lead time (days)'}<input type="number" min="0" style={field} value={leadDays} onChange={e=>setLeadDays(e.target.value)}/></label>
        <label>{ar?'شروط السداد':'Payment terms'}<input style={field} value={paymentTerms} onChange={e=>setPaymentTerms(e.target.value)}/></label>
      </div>{(selectedRfq?.lines||[]).map((l:any)=><div key={l.id} style={{...grid,paddingTop:0}}><label>{l.item_code} — {ar?l.item_name_ar:l.item_name_en} ({fmt(Number(l.quantity))})<input data-testid={`quote-price-${l.id}`} type="number" min="0" style={field} value={prices[l.id]||''} onChange={e=>setPrices({...prices,[l.id]:e.target.value})} placeholder={ar?'سعر الوحدة':'Unit price'}/></label></div>)}
      <div style={{padding:12}}><button data-testid="quote-record" style={btn} disabled={busy} onClick={recordQuote}>{ar?'تسجيل العرض':'Record quotation'}</button></div>
    </Panel>
    <Panel title={ar?'المقارنة والترسية':'Comparison and award'} icon={<Trophy size={18}/> }>
      <div style={{padding:'0 12px 12px'}}><label>{ar?'سبب الترسية':'Award reason'}<input data-testid="award-reason" style={field} value={awardReason} onChange={e=>setAwardReason(e.target.value)}/></label></div>
      <DataTable headers={[ar?'الترتيب':'Rank',ar?'المورد':'Supplier',ar?'الإجمالي':'Total',ar?'التوريد':'Lead time',ar?'الشروط':'Terms',ar?'الحالة':'Status',ar?'ترسية':'Award']} rows={comparisonQuotes.map((q:any,idx:number)=>[idx+1,ar?q.supplier_name_ar:q.supplier_name_en,fmt(Number(q.total)),`${q.lead_time_days} ${ar?'يوم':'days'}`,q.payment_terms||'—',q.status,<button data-testid={`award-quote-${q.id}`} key={q.id} style={{...smallBtn,background:idx===0?'#047857':'#b45309'}} disabled={busy||selectedRfq?.status!=='ISSUED'||comparisonQuotes.length<2} onClick={()=>act(`/api/v1/procurement/rfqs/${selectedRfq.id}/award`,'POST',{quotation_id:q.id,award_reason:awardReason},ar?'تمت الترسية وإنشاء أمر شراء مسودة':'Awarded; draft purchase order created')}>{ar?'ترسية':'Award'}</button>])}/>
    </Panel>
  </>;
}
