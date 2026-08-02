import {useEffect, useMemo, useState} from 'react';
import {AlertTriangle, BarChart3, Boxes, CheckCircle2, Download, Factory, FileSpreadsheet, Globe2, RefreshCw, ShieldCheck} from 'lucide-react';
import {authHeaders, DataTable, jsonHeaders, Kpi, MiniStatus, money, Panel, SummaryLine} from './ui';

type Tab='imports'|'inventory'|'budget'|'costing';

async function readJson(url:string, fallback:any){
  const response=await fetch(url,{headers:authHeaders()});
  if(!response.ok)return fallback;
  return response.json();
}

async function downloadAuthenticated(url:string, filename:string){
  const response=await fetch(url,{headers:authHeaders()});
  if(!response.ok){const x=await response.json().catch(()=>({}));throw new Error(x.detail||'Export failed')}
  const blob=await response.blob();
  const objectUrl=URL.createObjectURL(blob);
  const anchor=document.createElement('a');anchor.href=objectUrl;anchor.download=filename;anchor.click();URL.revokeObjectURL(objectUrl);
}

export function OperationalControlsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date().toISOString().slice(0,10);
  const [tab,setTab]=useState<Tab>('imports');
  const [imports,setImports]=useState<any[]>([]);
  const [aging,setAging]=useState<any>({summary:{},rows:[]});
  const [reconciliation,setReconciliation]=useState<any>({rows:[],all_reconciled:false});
  const [budgets,setBudgets]=useState<any[]>([]);
  const [analytics,setAnalytics]=useState<any>(null);
  const [granularity,setGranularity]=useState<'DAILY'|'MONTHLY'|'ANNUAL'>('MONTHLY');
  const [startDate,setStartDate]=useState(`${today.slice(0,4)}-01-01`);
  const [endDate,setEndDate]=useState(today);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [form,setForm]=useState({declaration_date:today,origin_country:'BRA',customs_reference:'',treatment:'THROUGH_RETURN',customs_value:'10000',vat_base:'10000',vat_collected_on_declaration:'0'});
  const [items,setItems]=useState<any[]>([]);
  const [rollups,setRollups]=useState<any[]>([]);
  const [selectedRollupId,setSelectedRollupId]=useState<number|null>(null);
  const [rollupForm,setRollupForm]=useState({item_id:'',quantity:'1',as_of_date:today,cost_basis:'STANDARD'});
  const [warehouses,setWarehouses]=useState<any[]>([]);const [goodsReceipts,setGoodsReceipts]=useState<any[]>([]);const [suppliers,setSuppliers]=useState<any[]>([]);
  const [landedCosts,setLandedCosts]=useState<any[]>([]);const [counts,setCounts]=useState<any[]>([]);
  const [landedForm,setLandedForm]=useState({goods_receipt_id:'',import_declaration_id:'',supplier_id:'',document_date:today,due_date:today,supplier_invoice_number:'',charge_type:'FREIGHT',description:'',amount:'',allocation_method:'VALUE',tax_code:'P15',capitalizable:true});
  const [countForm,setCountForm]=useState({warehouse_id:'',count_date:today,count_type:'FULL'});const [selectedCountId,setSelectedCountId]=useState<number|null>(null);const [countValues,setCountValues]=useState<Record<number,string>>({});

  const budgetId=budgets[0]?.id;
  const load=async()=>{
    setBusy(true);setMessage('');
    try{
      const [im,ag,rec,bg,it,cr,wh,grn,pa,lc,cnt]=await Promise.all([
        readJson(`/api/v1/operational-controls/imports?company_id=${companyId}`,[]),
        readJson(`/api/v1/operational-controls/inventory-aging?company_id=${companyId}&as_of=${today}`,{summary:{},rows:[]}),
        readJson(`/api/v1/operational-controls/perpetual-reconciliation?company_id=${companyId}&as_of=${today}`,{rows:[],all_reconciled:false}),
        readJson(`/api/v1/budgets?company_id=${companyId}`,[]),
        readJson(`/api/v1/inventory/items?company_id=${companyId}`,[]),
        readJson(`/api/v1/operational-controls/cost-rollups?company_id=${companyId}&limit=30`,[]),
        readJson(`/api/v1/inventory/warehouses?company_id=${companyId}`,[]),
        readJson(`/api/v1/inventory/goods-receipts?company_id=${companyId}`,[]),
        readJson(`/api/v1/subledgers/parties?company_id=${companyId}&party_type=SUPPLIER`,[]),
        readJson(`/api/v1/operational-controls/landed-costs?company_id=${companyId}`,[]),
        readJson(`/api/v1/operational-controls/inventory-counts?company_id=${companyId}`,[]),
      ]);
      setImports(Array.isArray(im)?im:[]);setAging(ag);setReconciliation(rec);setBudgets(Array.isArray(bg)?bg:[]);
      setItems(Array.isArray(it)?it:[]);setRollups(Array.isArray(cr)?cr:[]);
      setWarehouses(Array.isArray(wh)?wh:[]);setGoodsReceipts(Array.isArray(grn)?grn:[]);setSuppliers(Array.isArray(pa)?pa:[]);setLandedCosts(Array.isArray(lc)?lc:[]);setCounts(Array.isArray(cnt)?cnt:[]);
      if(!landedForm.goods_receipt_id&&grn?.length)setLandedForm(current=>({...current,goods_receipt_id:String(grn[0].id)}));
      if(!landedForm.supplier_id&&pa?.length)setLandedForm(current=>({...current,supplier_id:String(pa[0].id)}));
      if(!countForm.warehouse_id&&wh?.length)setCountForm(current=>({...current,warehouse_id:String(wh[0].id)}));
      const chosen=(cnt||[]).find((x:any)=>x.status==='FROZEN')||(cnt||[])[0];
      if(chosen){setSelectedCountId(current=>current&&(cnt||[]).some((x:any)=>x.id===current)?current:chosen.id);setCountValues(current=>{const next={...current};for(const line of chosen.lines||[])if(next[line.id]===undefined)next[line.id]=String(line.counted_quantity??line.book_quantity??0);return next})}
      if(Array.isArray(cr)&&cr.length){setSelectedRollupId(current=>current&&cr.some((x:any)=>x.id===current)?current:cr[0].id)}else{setSelectedRollupId(null)}
      if(!rollupForm.item_id&&Array.isArray(it)&&it.length){
        const candidate=it.find((x:any)=>String(x.item_type||'').toUpperCase().includes('FINISHED'))||it.find((x:any)=>String(x.code||'').toUpperCase().startsWith('FG'))||it[0];
        setRollupForm(current=>({...current,item_id:String(candidate.id)}));
      }
    }catch(e:any){setMessage(e?.message||String(e))}finally{setBusy(false)}
  };
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{
    if(!budgetId){setAnalytics(null);return}
    readJson(`/api/v1/operational-controls/budget-analytics?budget_id=${budgetId}&start_date=${startDate}&end_date=${endDate}&granularity=${granularity}&historical_years=2&language=${ar?'ar':'en'}`,null).then(setAnalytics);
  },[budgetId,startDate,endDate,granularity,ar]);

  async function createCostRollup(){
    if(!rollupForm.item_id){setMessage(ar?'اختر المنتج النهائي أولًا':'Select a finished product first');return}
    setBusy(true);setMessage('');
    try{
      const response=await fetch('/api/v1/operational-controls/cost-rollups',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({
        company_id:companyId,item_id:Number(rollupForm.item_id),quantity:Number(rollupForm.quantity),as_of_date:rollupForm.as_of_date,cost_basis:rollupForm.cost_basis
      })});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||'Cost roll-up failed');
      setMessage(ar?`تم إنشاء تحليل التكلفة ${data.number} بتكلفة وحدة ${money.format(Number(data.unit_cost||0))}.`:`Cost roll-up ${data.number} created at unit cost ${money.format(Number(data.unit_cost||0))}.`);
      await load();setTab('costing');
    }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }

  const selectedRollup=useMemo(()=>rollups.find((row:any)=>row.id===selectedRollupId)||rollups[0]||null,[rollups,selectedRollupId]);
  const rollupStatusLabel=(status?:string)=>({PREPARED:ar?'مُعد':'Prepared',READY_FOR_REVIEW:ar?'جاهز للمراجعة':'Ready for review',REVIEWED:ar?'تمت المراجعة':'Reviewed',APPROVED:ar?'معتمد':'Approved',REJECTED:ar?'مرفوض':'Rejected'} as Record<string,string>)[status||'']||status||'—';

  async function transitionRollup(action:'review'|'approve'){
    const row=selectedRollup;if(!row){setMessage(ar?'لا يوجد تحليل تكلفة':'No cost roll-up available');return}
    setBusy(true);setMessage('');
    try{const response=await fetch(`/api/v1/operational-controls/cost-rollups/${row.id}/${action}`,{method:'POST',headers:authHeaders()});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Action failed');
      setMessage(ar?(action==='review'?'تمت مراجعة تحليل التكلفة':'تم اعتماد تحليل التكلفة وتحديث التكلفة المعيارية'):(action==='review'?'Cost roll-up reviewed':'Cost roll-up approved and standard cost updated'));await load();
    }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }

  async function createImport(){
    setBusy(true);setMessage('');
    try{
      const vatBase=Number(form.vat_base||0);
      const payload={company_id:companyId,declaration_date:form.declaration_date,origin_country:form.origin_country.toUpperCase(),customs_reference:form.customs_reference||null,
        treatment:form.treatment,customs_value:Number(form.customs_value||0),vat_base:vatBase,vat_rate:15,vat_collected_on_declaration:Number(form.vat_collected_on_declaration||0),
        vat_accounted_in_return:form.treatment==='THROUGH_RETURN'?Number((vatBase*.15).toFixed(2)):0,
        evidence:{zero_customs_vat_reason:form.treatment,source:'RC20 operational screen'},
        lines:[{description:ar?'واردات بضاعة خارجية':'Foreign merchandise import',quantity:1,uom:'EA',customs_value:Number(form.customs_value||0),vat_base:vatBase,vat_due:Number((vatBase*.15).toFixed(2))}]};
      const response=await fetch('/api/v1/operational-controls/imports',{method:'POST',headers:jsonHeaders(),body:JSON.stringify(payload)});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||'Error');
      await load();
      setMessage(ar?`تم إنشاء البيان ${data.number}. أرسله الآن، ثم يجب أن يعتمد ويرحل بواسطة مستخدم مستقل.`:`Declaration ${data.number} created. Submit it now; an independent user must approve and post it.`);
    }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }

  async function createLandedCost(){
    if(!landedForm.goods_receipt_id||!landedForm.supplier_id||!landedForm.supplier_invoice_number.trim()||!landedForm.amount){setMessage(ar?'أكمل بيانات التكلفة الواصلة':'Complete landed-cost fields');return}
    setBusy(true);setMessage('');
    try{const response=await fetch('/api/v1/operational-controls/landed-costs',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,document_date:landedForm.document_date,goods_receipt_id:Number(landedForm.goods_receipt_id),import_declaration_id:landedForm.import_declaration_id?Number(landedForm.import_declaration_id):null,allocation_method:landedForm.allocation_method,charges:[{supplier_id:Number(landedForm.supplier_id),supplier_invoice_number:landedForm.supplier_invoice_number,invoice_date:landedForm.document_date,due_date:landedForm.due_date,charge_type:landedForm.charge_type,description:landedForm.description||landedForm.charge_type,amount:Number(landedForm.amount),capitalizable:landedForm.capitalizable,tax_code:landedForm.tax_code}]})});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Landed cost failed');
      setMessage(ar?`تم إنشاء ${data.number}؛ أرسله ثم اعتمده من مستخدم مستقل.`:`${data.number} created; submit then approve with an independent user.`);setLandedForm({...landedForm,supplier_invoice_number:'',amount:'',description:''});await load();
    }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }
  async function transitionLanded(row:any,action:'submit'|'approve'|'post'){
    setBusy(true);setMessage('');try{const response=await fetch(`/api/v1/operational-controls/landed-costs/${row.id}/${action}`,{method:'POST',headers:authHeaders()});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Landed cost action failed');setMessage(ar?`تم تنفيذ ${action} على ${row.number}`:`${action} completed for ${row.number}`);await load();}catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }
  async function createCount(){
    if(!countForm.warehouse_id){setMessage(ar?'اختر المستودع':'Select warehouse');return}setBusy(true);setMessage('');
    try{const response=await fetch('/api/v1/operational-controls/inventory-counts',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,warehouse_id:Number(countForm.warehouse_id),count_date:countForm.count_date,count_type:countForm.count_type})});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Count failed');setSelectedCountId(data.id);setCountValues(Object.fromEntries((data.lines||[]).map((line:any)=>[line.id,String(line.book_quantity)])));setMessage(ar?`تم تجميد الجرد ${data.number}; أدخل الكميات الفعلية.`:`Count ${data.number} frozen; enter physical quantities.`);await load();}catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }
  const selectedCount=useMemo(()=>counts.find((row:any)=>row.id===selectedCountId)||counts[0]||null,[counts,selectedCountId]);
  async function saveAndSubmitCount(){
    if(!selectedCount||selectedCount.status!=='FROZEN')return;setBusy(true);setMessage('');
    try{for(const line of selectedCount.lines||[]){const response=await fetch(`/api/v1/operational-controls/inventory-counts/${selectedCount.id}/lines/${line.id}`,{method:'PATCH',headers:jsonHeaders(),body:JSON.stringify({counted_quantity:Number(countValues[line.id]),reason:'R7 employee physical count'})});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Count line failed')}
      const response=await fetch(`/api/v1/operational-controls/inventory-counts/${selectedCount.id}/submit`,{method:'POST',headers:authHeaders()});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Count submit failed');setMessage(ar?'تم حفظ كل الكميات وإرسال الجرد للاعتماد':'All quantities saved and count submitted');await load();
    }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }
  async function approveCount(row:any){setBusy(true);setMessage('');try{const response=await fetch(`/api/v1/operational-controls/inventory-counts/${row.id}/approve`,{method:'POST',headers:authHeaders()});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Count approval failed');setMessage(ar?`تم اعتماد ${row.number} وترحيل فرق الجرد.`:`${row.number} approved and variance posted.`);await load();}catch(e:any){setMessage(e.message)}finally{setBusy(false)}}

  async function transitionImport(row:any,action:'submit'|'approve'|'post'){
    setBusy(true);setMessage('');
    try{
      const response=await fetch(`/api/v1/operational-controls/imports/${row.id}/${action}`,{method:'POST',headers:authHeaders()});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.detail||'Import workflow action failed');
      await load();
      const labels={
        submit:ar?`تم إرسال البيان ${row.number} للاعتماد.`:`Declaration ${row.number} submitted for approval.`,
        approve:ar?`تم اعتماد البيان ${row.number}. يمكن الآن ترحيله.`:`Declaration ${row.number} approved and ready to post.`,
        post:ar?`تم ترحيل البيان ${row.number} وربط أثره المحاسبي.`:`Declaration ${row.number} posted with its accounting effect.`,
      };
      setMessage(labels[action]);
    }catch(e:any){setMessage(e?.message||String(e))}finally{setBusy(false)}
  }

  const importVat=imports.reduce((n,r)=>n+Number(r.vat_accounted_in_return||r.vat_collected_on_declaration||0),0);
  const inventoryValue=Object.values(aging?.summary||{}).reduce((n:any,v:any)=>Number(n)+Number(v||0),0) as number;
  const atRisk=Number(aging?.summary?.SLOW_MOVING||0)+Number(aging?.summary?.OBSOLETE||0)+Number(aging?.summary?.EXPIRED||0);
  const budgetRows=analytics?.rows||[];
  const unfavorable=budgetRows.filter((r:any)=>!r.favorable).length;
  const statusLabels:{[k:string]:string}={AT_CUSTOMS:ar?'محصلة في الجمارك':'At customs',THROUGH_RETURN:ar?'عبر الإقرار':'Through return',SUSPENDED:ar?'معلقة':'Suspended',EXEMPT:ar?'معفاة':'Exempt'};
  const importStatusLabels:{[k:string]:string}={DRAFT:ar?'مسودة':'Draft',SUBMITTED:ar?'مرسل للاعتماد':'Submitted',APPROVED:ar?'معتمد':'Approved',POSTED:ar?'مرحّل':'Posted'};

  return <>
    <div className="kpis rich">
      <Kpi title={ar?'بيانات الاستيراد':'Import declarations'} value={String(imports.length)} trend={ar?'بسبب واضح لضريبة البيان':'Explicit customs VAT treatment'} good/>
      <Kpi title={ar?'ضريبة واردات مثبتة':'Import VAT accounted'} value={money.format(importVat)} trend={ar?'جمارك أو عبر الإقرار':'Customs or VAT return'} good/>
      <Kpi title={ar?'قيمة المخزون':'Inventory carrying value'} value={money.format(inventoryValue)} trend={ar?'دفتر مساعد مستمر':'Perpetual subledger'} good={reconciliation?.all_reconciled}/>
      <Kpi title={ar?'مخزون معرض للمخاطر':'At-risk inventory'} value={money.format(atRisk)} trend={ar?'راكد أو منتهي':'Slow, obsolete or expired'} good={atRisk===0}/>
    </div>

    <div className="statement-tabs">
      {([['imports',ar?'الواردات والتصدير':'Imports & Exports'],['costing',ar?'التكلفة الواصلة والتفكيك':'Landed Cost & Explosion'],['inventory',ar?'الجرد المستمر':'Perpetual Inventory'],['budget',ar?'الموازنة والتحليل':'Budget Analytics']] as [Tab,string][]).map(([key,label])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{label}</button>)}
    </div>

    {message&&<div className="status-pill"><AlertTriangle size={17}/>{message}</div>}
    <div className="journal-footer"><span>{ar?'RC20 يربط الواردات والتكلفة والمخزون والموازنة بالأستاذ العام.':'RC20 links trade, costing, inventory and budgets to the general ledger.'}</span><button disabled={busy} onClick={load}><RefreshCw size={15}/>{busy?(ar?'جارٍ التحديث':'Refreshing'):(ar?'تحديث البيانات':'Refresh')}</button></div>

    {tab==='imports'&&<>
      <div className="two-columns wide-left">
        <Panel title={ar?'إضافة بيان استيراد':'Create import declaration'} icon={<Globe2 size={18}/>}>
          <div className="journal-form">
            <label>{ar?'تاريخ البيان':'Declaration date'}<input type="date" value={form.declaration_date} onChange={e=>setForm({...form,declaration_date:e.target.value})}/></label>
            <label>{ar?'بلد المنشأ':'Origin country'}<input maxLength={3} value={form.origin_country} onChange={e=>setForm({...form,origin_country:e.target.value})}/></label>
            <label>{ar?'المرجع الجمركي':'Customs reference'}<input value={form.customs_reference} onChange={e=>setForm({...form,customs_reference:e.target.value})}/></label>
            <label>{ar?'معالجة الضريبة':'VAT treatment'}<select value={form.treatment} onChange={e=>setForm({...form,treatment:e.target.value})}><option value="THROUGH_RETURN">{ar?'صفر في البيان — عبر الإقرار':'Zero on declaration — through return'}</option><option value="AT_CUSTOMS">{ar?'محصلة في الجمارك':'Collected at customs'}</option><option value="SUSPENDED">{ar?'معلقة جمركيًا':'Customs suspended'}</option><option value="EXEMPT">{ar?'معفاة':'Exempt'}</option></select></label>
            <label>{ar?'القيمة الجمركية':'Customs value'}<input type="number" min="0" value={form.customs_value} onChange={e=>setForm({...form,customs_value:e.target.value})}/></label>
            <label>{ar?'وعاء VAT':'VAT base'}<input type="number" min="0" value={form.vat_base} onChange={e=>setForm({...form,vat_base:e.target.value})}/></label>
            <label>{ar?'VAT المحصل في البيان':'VAT collected on declaration'}<input type="number" min="0" value={form.vat_collected_on_declaration} onChange={e=>setForm({...form,vat_collected_on_declaration:e.target.value})}/></label>
          </div>
          <div className="journal-footer"><span>{ar?'الصفر لا يُقبل دون سبب معالجة نظامي.':'Zero customs VAT requires an explicit treatment reason.'}</span><button disabled={busy} onClick={createImport}>{ar?'إنشاء البيان':'Create declaration'}</button></div>
        </Panel>
        <Panel title={ar?'ضوابط المعالجة':'Treatment controls'} icon={<ShieldCheck size={18}/>}>
          <MiniStatus icon={<CheckCircle2 size={18}/>} title={ar?'فاتورة المورد الأجنبي':'Foreign supplier invoice'} value="0% Saudi VAT" status={ar?'لا تعني إعفاء الاستيراد تلقائيًا':'Does not automatically exempt the import'}/>
          <MiniStatus icon={<FileSpreadsheet size={18}/>} title={ar?'البيان صفر':'Zero customs declaration'} value={ar?'سبب إلزامي':'Reason required'} status={ar?'إقرار / تعليق / إعفاء':'Return / suspension / exemption'}/>
          <MiniStatus icon={<Download size={18}/>} title={ar?'التصدير':'Exports'} value="0%" status={ar?'بعد اعتماد مستندات الإثبات':'After approved export evidence'}/>
        </Panel>
      </div>
      <Panel title={ar?'سجل بيانات الاستيراد':'Import declaration register'} icon={<Globe2 size={18}/>}>
        <div className="journal-footer"><span>{ar?'السجل قابل للتصدير مع معالجة الضريبة وسبب الصفر.':'Export includes VAT treatment and zero-declaration reason.'}</span><button onClick={()=>downloadAuthenticated(`/api/v1/operational-controls/imports/export.csv?company_id=${companyId}`,'import_declarations.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>
        <DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'المنشأ':'Origin',ar?'المعالجة':'Treatment',ar?'القيمة':'Value',ar?'VAT البيان':'Customs VAT',ar?'VAT الإقرار':'Return VAT',ar?'الحالة':'Status',ar?'الإجراء':'Action']} rows={imports.slice(0,30).map(r=>[r.number,r.declaration_date,r.origin_country,statusLabels[r.treatment]||r.treatment,money.format(Number(r.customs_value||0)),money.format(Number(r.vat_collected_on_declaration||0)),money.format(Number(r.vat_accounted_in_return||0)),importStatusLabels[r.status]||r.status,
          r.status==='DRAFT'?<button disabled={busy} onClick={()=>transitionImport(r,'submit')}>{ar?'إرسال':'Submit'}</button>:
          r.status==='SUBMITTED'?<button disabled={busy} onClick={()=>transitionImport(r,'approve')}>{ar?'اعتماد':'Approve'}</button>:
          r.status==='APPROVED'?<button disabled={busy} onClick={()=>transitionImport(r,'post')}>{ar?'ترحيل':'Post'}</button>:
          r.status==='POSTED'?<span>✓</span>:'—'])}/>
      </Panel>
    </>}

    {tab==='costing'&&<>
      <div className="kpis rich">
        <Kpi title={ar?'المواد المباشرة':'Direct materials'} value={money.format(Number(selectedRollup?.direct_material_cost||0))} trend={ar?'من BOM متعدد المستويات':'Multi-level BOM'} good/>
        <Kpi title={ar?'التعبئة والتغليف':'Packaging'} value={money.format(Number(selectedRollup?.packaging_cost||0))} trend={ar?'مفصولة عن الخام':'Separated from raw material'} good/>
        <Kpi title={ar?'الأجور والمصاريف المباشرة':'Labor & direct expense'} value={money.format(Number(selectedRollup?.direct_labor_cost||0)+Number(selectedRollup?.direct_expense_cost||0))} trend={ar?'Routing والتشغيل الخارجي':'Routing & outside processing'} good/>
        <Kpi title={ar?'التكاليف الصناعية غير المباشرة':'Manufacturing overhead'} value={money.format(Number(selectedRollup?.overhead_total||0))} trend={ar?'متغير + ثابت':'Variable + fixed'} good={Number(selectedRollup?.overhead_total||0)>=0}/>
      </div>
      <div className="two-columns wide-left">
        <Panel title={ar?'إنشاء تفكيك تكلفة المنتج النهائي':'Create finished-product cost roll-up'} icon={<Factory size={18}/>}>
          <div className="journal-form">
            <label>{ar?'المنتج النهائي':'Finished product'}<select value={rollupForm.item_id} onChange={e=>setRollupForm({...rollupForm,item_id:e.target.value})}><option value="">{ar?'اختر المنتج':'Select product'}</option>{items.map((item:any)=><option key={item.id} value={item.id}>{item.code} — {ar?item.name_ar:item.name_en}</option>)}</select></label>
            <label>{ar?'الكمية المطلوب تحليلها':'Analysis quantity'}<input type="number" min="0.0001" step="0.0001" value={rollupForm.quantity} onChange={e=>setRollupForm({...rollupForm,quantity:e.target.value})}/></label>
            <label>{ar?'تاريخ التكلفة':'Cost date'}<input type="date" value={rollupForm.as_of_date} onChange={e=>setRollupForm({...rollupForm,as_of_date:e.target.value})}/></label>
            <label>{ar?'أساس التكلفة':'Cost basis'}<select value={rollupForm.cost_basis} onChange={e=>setRollupForm({...rollupForm,cost_basis:e.target.value})}><option value="STANDARD">{ar?'التكلفة المعيارية':'Standard cost'}</option><option value="ACTUAL">{ar?'متوسط التكلفة الفعلية':'Actual average cost'}</option></select></label>
          </div>
          <div className="journal-footer"><span>{ar?'يفك المنتجات نصف المصنعة حتى المواد الأساسية ويكشف دورات BOM.':'Explodes semi-finished products to base materials and detects BOM cycles.'}</span><button disabled={busy} onClick={createCostRollup}>{ar?'إنشاء تحليل التكلفة':'Create cost roll-up'}</button></div>
        </Panel>
        <Panel title={ar?'نتيجة التحليل الحالية':'Current roll-up result'} icon={<BarChart3 size={18}/>}>
          <SummaryLine label={ar?'رقم التحليل':'Roll-up number'} value={selectedRollup?.number||'—'}/>
          <SummaryLine label={ar?'المنتج':'Product'} value={selectedRollup?`${selectedRollup.item_code} — ${ar?selectedRollup.item_name_ar:selectedRollup.item_name_en}`:'—'}/>
          <SummaryLine label={ar?'إجمالي التكلفة':'Total cost'} value={money.format(Number(selectedRollup?.total_cost||0))}/>
          <SummaryLine label={ar?'تكلفة الوحدة':'Unit cost'} value={money.format(Number(selectedRollup?.unit_cost||0))}/>
          <SummaryLine label={ar?'التكلفة المعيارية الحالية':'Current standard cost'} value={money.format(Number(selectedRollup?.current_standard_cost||0))}/>
          <SummaryLine label={ar?'فرق التكلفة المعيارية':'Standard-cost variance'} value={money.format(Number(selectedRollup?.standard_cost_variance||0))} warn={Number(selectedRollup?.standard_cost_variance||0)>0}/>
          <SummaryLine label={ar?'الحالة':'Status'} value={rollupStatusLabel(selectedRollup?.status)}/>
          <div className="journal-footer"><button disabled={busy||!selectedRollup||selectedRollup?.status!=='READY_FOR_REVIEW'} onClick={()=>transitionRollup('review')}>{ar?'مراجعة':'Review'}</button><button disabled={busy||!selectedRollup||selectedRollup?.status!=='REVIEWED'} onClick={()=>transitionRollup('approve')}>{ar?'اعتماد وتحديث المعياري':'Approve & update standard'}</button></div>
        </Panel>
      </div>
      <Panel title={ar?'مكونات تكلفة المنتج النهائي':'Finished-product cost components'} icon={<Factory size={18}/>}>
        <DataTable headers={[ar?'المكوّن':'Component',ar?'القيمة':'Amount',ar?'النسبة من الإجمالي':'% of total']} rows={[
          [ar?'المواد الخام المباشرة':'Direct raw materials',money.format(Number(selectedRollup?.direct_material_cost||0)),selectedRollup?.total_cost?`${(Number(selectedRollup.direct_material_cost)/Number(selectedRollup.total_cost)*100).toFixed(1)}%`:'0%'],
          [ar?'التعبئة والتغليف':'Packaging',money.format(Number(selectedRollup?.packaging_cost||0)),selectedRollup?.total_cost?`${(Number(selectedRollup.packaging_cost)/Number(selectedRollup.total_cost)*100).toFixed(1)}%`:'0%'],
          [ar?'الأجور المباشرة':'Direct labor',money.format(Number(selectedRollup?.direct_labor_cost||0)),selectedRollup?.total_cost?`${(Number(selectedRollup.direct_labor_cost)/Number(selectedRollup.total_cost)*100).toFixed(1)}%`:'0%'],
          [ar?'المصاريف المباشرة':'Direct expenses',money.format(Number(selectedRollup?.direct_expense_cost||0)),selectedRollup?.total_cost?`${(Number(selectedRollup.direct_expense_cost)/Number(selectedRollup.total_cost)*100).toFixed(1)}%`:'0%'],
          [ar?'Overhead متغير':'Variable overhead',money.format(Number(selectedRollup?.variable_overhead_cost||0)),selectedRollup?.total_cost?`${(Number(selectedRollup.variable_overhead_cost)/Number(selectedRollup.total_cost)*100).toFixed(1)}%`:'0%'],
          [ar?'Overhead ثابت':'Fixed overhead',money.format(Number(selectedRollup?.fixed_overhead_cost||0)),selectedRollup?.total_cost?`${(Number(selectedRollup.fixed_overhead_cost)/Number(selectedRollup.total_cost)*100).toFixed(1)}%`:'0%'],
        ]}/>
      </Panel>
      <Panel title={ar?'تفاصيل تفكيك BOM والمسار التشغيلي':'BOM and routing explosion detail'} icon={<FileSpreadsheet size={18}/>}>
        <div className="journal-footer"><span>{ar?'كل سطر يعرض المستوى والكمية وتكلفة الوحدة ومصدر التكلفة.':'Every line shows level, quantity, unit cost and cost source.'}</span><button disabled={!selectedRollup} onClick={()=>selectedRollup&&downloadAuthenticated(`/api/v1/operational-controls/cost-rollups/${selectedRollup.id}/export.csv`,`cost_rollup_${selectedRollup.number}.csv`).catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير التفاصيل':'Export detail'}</button></div>
        <DataTable headers={[ar?'المستوى':'Level',ar?'النوع':'Type',ar?'الوصف':'Description',ar?'الكمية/الساعات':'Qty / hours',ar?'تكلفة الوحدة':'Unit cost',ar?'الإجمالي':'Total']} rows={(selectedRollup?.lines||[]).map((line:any)=>[String(line.level),line.line_type,ar?line.description_ar:line.description_en,String(line.quantity),money.format(Number(line.unit_cost||0)),money.format(Number(line.total_cost||0))])}/>
      </Panel>
      <Panel title={ar?'سجل تحليلات التكلفة':'Cost roll-up register'} icon={<BarChart3 size={18}/>}> 
        <div className="cost-rollup-selector">
          <label>{ar?'التحليل المعروض':'Displayed roll-up'}
            <select value={selectedRollup?.id||''} onChange={e=>setSelectedRollupId(Number(e.target.value))}>
              {rollups.map((row:any)=><option key={row.id} value={row.id}>{row.number} — {row.item_code} — {rollupStatusLabel(row.status)}</option>)}
            </select>
          </label>
        </div>
        <DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'المنتج':'Product',ar?'الأساس':'Basis',ar?'الكمية':'Quantity',ar?'تكلفة الوحدة':'Unit cost',ar?'الفرق':'Variance',ar?'الحالة':'Status']} rows={rollups.map((row:any)=>[row.number,row.as_of_date,`${row.item_code} — ${ar?row.item_name_ar:row.item_name_en}`,row.cost_basis==='STANDARD'?(ar?'معياري':'Standard'):(ar?'فعلي':'Actual'),String(row.quantity),money.format(Number(row.unit_cost||0)),money.format(Number(row.standard_cost_variance||0)),rollupStatusLabel(row.status)])}/>
      </Panel>
      <div className="two-columns wide-left">
        <Panel title={ar?'إضافة تكلفة واصلة':'Create landed cost'} icon={<Factory size={18}/> }>
          <div className="journal-form">
            <label>{ar?'إذن الاستلام':'Goods receipt'}<select value={landedForm.goods_receipt_id} onChange={e=>setLandedForm({...landedForm,goods_receipt_id:e.target.value})}><option value="">{ar?'اختر':'Select'}</option>{goodsReceipts.map((r:any)=><option key={r.id} value={r.id}>{r.number} — {r.receipt_date}</option>)}</select></label>
            <label>{ar?'بيان الاستيراد':'Import declaration'}<select value={landedForm.import_declaration_id} onChange={e=>setLandedForm({...landedForm,import_declaration_id:e.target.value})}><option value="">{ar?'بدون':'None'}</option>{imports.map((r:any)=><option key={r.id} value={r.id}>{r.number}</option>)}</select></label>
            <label>{ar?'مورد الخدمة':'Charge supplier'}<select value={landedForm.supplier_id} onChange={e=>setLandedForm({...landedForm,supplier_id:e.target.value})}><option value="">{ar?'اختر':'Select'}</option>{suppliers.map((r:any)=><option key={r.id} value={r.id}>{r.code} — {ar?r.name_ar:r.name_en}</option>)}</select></label>
            <label>{ar?'رقم فاتورة الخدمة':'Supplier invoice'}<input value={landedForm.supplier_invoice_number} onChange={e=>setLandedForm({...landedForm,supplier_invoice_number:e.target.value})}/></label>
            <label>{ar?'التاريخ':'Document date'}<input type="date" value={landedForm.document_date} onChange={e=>setLandedForm({...landedForm,document_date:e.target.value})}/></label>
            <label>{ar?'الاستحقاق':'Due date'}<input type="date" value={landedForm.due_date} onChange={e=>setLandedForm({...landedForm,due_date:e.target.value})}/></label>
            <label>{ar?'نوع التكلفة':'Charge type'}<select value={landedForm.charge_type} onChange={e=>setLandedForm({...landedForm,charge_type:e.target.value})}><option value="FREIGHT">{ar?'شحن':'Freight'}</option><option value="CUSTOMS">{ar?'جمارك':'Customs'}</option><option value="INSURANCE">{ar?'تأمين':'Insurance'}</option><option value="HANDLING">{ar?'مناولة':'Handling'}</option></select></label>
            <label>{ar?'الوصف':'Description'}<input value={landedForm.description} onChange={e=>setLandedForm({...landedForm,description:e.target.value})}/></label>
            <label>{ar?'المبلغ':'Amount'}<input type="number" min="0.01" step="0.01" value={landedForm.amount} onChange={e=>setLandedForm({...landedForm,amount:e.target.value})}/></label>
            <label>{ar?'أساس التوزيع':'Allocation basis'}<select value={landedForm.allocation_method} onChange={e=>setLandedForm({...landedForm,allocation_method:e.target.value})}><option value="VALUE">{ar?'القيمة':'Value'}</option><option value="QUANTITY">{ar?'الكمية':'Quantity'}</option><option value="WEIGHT">{ar?'الوزن':'Weight'}</option></select></label>
            <label>{ar?'الضريبة':'Tax code'}<select value={landedForm.tax_code} onChange={e=>setLandedForm({...landedForm,tax_code:e.target.value})}><option value="P15">15%</option><option value="P0">0%</option><option value="PEX">{ar?'معفى':'Exempt'}</option></select></label>
            <label><input type="checkbox" checked={landedForm.capitalizable} onChange={e=>setLandedForm({...landedForm,capitalizable:e.target.checked})}/>{ar?'تُحمّل على المخزون':'Capitalize into inventory'}</label>
          </div>
          <div className="journal-footer"><span>{ar?'الاعتماد يجب أن يتم بمستخدم مستقل.':'Approval must be performed by an independent user.'}</span><button disabled={busy} onClick={createLandedCost}>{ar?'إنشاء':'Create'}</button></div>
        </Panel>
        <Panel title={ar?'سجل التكاليف الواصلة':'Landed-cost register'} icon={<FileSpreadsheet size={18}/> }>
          <DataTable headers={[ar?'الرقم':'Number',ar?'الاستلام':'Receipt',ar?'التوزيع':'Allocation',ar?'الإجمالي':'Total',ar?'الحالة':'Status',ar?'الإجراء':'Action']} rows={landedCosts.map((row:any)=>[row.number,row.goods_receipt_number||row.goods_receipt_id,row.allocation_method,money.format(Number(row.total_amount||0)),row.status,row.status==='DRAFT'?<button disabled={busy} onClick={()=>transitionLanded(row,'submit')}>{ar?'إرسال':'Submit'}</button>:row.status==='SUBMITTED'?<button disabled={busy} onClick={()=>transitionLanded(row,'approve')}>{ar?'اعتماد':'Approve'}</button>:row.status==='APPROVED'?<button disabled={busy} onClick={()=>transitionLanded(row,'post')}>{ar?'ترحيل':'Post'}</button>:<span>✓</span>])}/>
        </Panel>
      </div>
    </>}

    {tab==='inventory'&&<>
      <div className="kpis">
        <Kpi title={ar?'نشط':'Active'} value={money.format(Number(aging?.summary?.ACTIVE||0))} trend={ar?'حركة طبيعية':'Normal movement'} good/>
        <Kpi title={ar?'بطيء الحركة':'Slow moving'} value={money.format(Number(aging?.summary?.SLOW_MOVING||0))} trend={ar?'أكثر من 90 يومًا':'Over 90 days'} good={Number(aging?.summary?.SLOW_MOVING||0)===0}/>
        <Kpi title={ar?'راكد':'Obsolete'} value={money.format(Number(aging?.summary?.OBSOLETE||0))} trend={ar?'أكثر من 180 يومًا':'Over 180 days'} good={Number(aging?.summary?.OBSOLETE||0)===0}/>
        <Kpi title={ar?'منتهي':'Expired'} value={money.format(Number(aging?.summary?.EXPIRED||0))} trend={ar?'يحتاج إجراء فوري':'Immediate action'} good={Number(aging?.summary?.EXPIRED||0)===0}/>
      </div>
      <div className="two-columns wide-left">
        <Panel title={ar?'بدء جرد فعلي':'Start physical inventory count'} icon={<Boxes size={18}/> }>
          <div className="journal-form">
            <label>{ar?'المستودع':'Warehouse'}<select value={countForm.warehouse_id} onChange={e=>setCountForm({...countForm,warehouse_id:e.target.value})}><option value="">{ar?'اختر':'Select'}</option>{warehouses.map((w:any)=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
            <label>{ar?'تاريخ الجرد':'Count date'}<input type="date" value={countForm.count_date} onChange={e=>setCountForm({...countForm,count_date:e.target.value})}/></label>
            <label>{ar?'نوع الجرد':'Count type'}<select value={countForm.count_type} onChange={e=>setCountForm({...countForm,count_type:e.target.value})}><option value="FULL">{ar?'شامل':'Full'}</option><option value="CYCLE">{ar?'دوري':'Cycle'}</option><option value="SPOT">{ar?'مفاجئ':'Spot'}</option></select></label>
          </div>
          <div className="journal-footer"><span>{ar?'يجمّد النظام كميات الدفتر عند الإنشاء.':'The system freezes book quantities at creation.'}</span><button disabled={busy} onClick={createCount}>{ar?'بدء الجرد':'Start count'}</button></div>
        </Panel>
        <Panel title={ar?'إدخال الكميات الفعلية':'Enter physical quantities'} icon={<FileSpreadsheet size={18}/> }>
          <label>{ar?'الجرد':'Count'}<select value={selectedCount?.id||''} onChange={e=>setSelectedCountId(Number(e.target.value))}>{counts.map((row:any)=><option key={row.id} value={row.id}>{row.number} — {row.status}</option>)}</select></label>
          <DataTable headers={[ar?'الصنف':'Item',ar?'الدفتر':'Book',ar?'الفعلي':'Counted',ar?'الفرق':'Variance']} rows={(selectedCount?.lines||[]).map((line:any)=>[line.item_code||line.item_id,String(line.book_quantity),<input aria-label={`count-${line.id}`} type="number" step="0.0001" value={countValues[line.id]??String(line.counted_quantity??line.book_quantity??0)} disabled={selectedCount?.status!=='FROZEN'} onChange={e=>setCountValues({...countValues,[line.id]:e.target.value})}/>,String(Number(countValues[line.id]??line.counted_quantity??line.book_quantity??0)-Number(line.book_quantity||0))])}/>
          <div className="journal-footer"><span>{selectedCount?`${selectedCount.number} — ${selectedCount.status}`:(ar?'لا يوجد جرد':'No count')}</span><button disabled={busy||!selectedCount||selectedCount.status!=='FROZEN'} onClick={saveAndSubmitCount}>{ar?'حفظ وإرسال':'Save & submit'}</button><button disabled={busy||!selectedCount||selectedCount.status!=='SUBMITTED'} onClick={()=>selectedCount&&approveCount(selectedCount)}>{ar?'اعتماد وترحيل الفرق':'Approve variance'}</button></div>
        </Panel>
      </div>
      <Panel title={ar?'سجل الجرد':'Inventory count register'} icon={<ShieldCheck size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'النوع':'Type',ar?'المستودع':'Warehouse',ar?'الحالة':'Status',ar?'الفروق':'Variances']} rows={counts.map((row:any)=>[row.number,row.count_date,row.count_type,row.warehouse_code||row.warehouse_id,row.status,String((row.lines||[]).filter((line:any)=>Number(line.variance_quantity||0)!==0).length)])}/></Panel>
      <div className="two-columns">
        <Panel title={ar?'أعمار المخزون':'Inventory aging'} icon={<Boxes size={18}/>}><DataTable headers={[ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Quantity',ar?'القيمة':'Value',ar?'آخر حركة':'Last movement',ar?'الأيام':'Days',ar?'التصنيف':'Class']} rows={(aging?.rows||[]).slice(0,30).map((r:any)=>[String(r.item_id),String(r.warehouse_id),String(r.quantity),money.format(Number(r.carrying_value||0)),r.last_movement_date||'—',String(r.days_without_movement),r.classification])}/></Panel>
        <Panel title={ar?'مطابقة الجرد المستمر مع الأستاذ':'Perpetual inventory reconciliation'} icon={<ShieldCheck size={18}/>}>
          <SummaryLine label={ar?'الحالة الإجمالية':'Overall status'} value={reconciliation?.all_reconciled?(ar?'متطابق':'Reconciled'):(ar?'يحتاج معالجة':'Needs action')} warn={!reconciliation?.all_reconciled}/>
          <DataTable headers={[ar?'الحساب':'Account',ar?'دفتر المخزون':'Subledger',ar?'الأستاذ العام':'GL',ar?'الفرق':'Difference']} rows={(reconciliation?.rows||[]).map((r:any)=>[r.account_code,money.format(Number(r.stock_subledger||0)),money.format(Number(r.general_ledger||0)),money.format(Number(r.difference||0))])}/>
        </Panel>
      </div>
    </>}

    {tab==='budget'&&<>
      <div className="journal-form">
        <label>{ar?'من':'From'}<input type="date" value={startDate} onChange={e=>setStartDate(e.target.value)}/></label>
        <label>{ar?'إلى':'To'}<input type="date" value={endDate} onChange={e=>setEndDate(e.target.value)}/></label>
        <label>{ar?'المستوى':'Granularity'}<select value={granularity} onChange={e=>setGranularity(e.target.value as any)}><option value="DAILY">{ar?'يومي':'Daily'}</option><option value="MONTHLY">{ar?'شهري':'Monthly'}</option><option value="ANNUAL">{ar?'سنوي':'Annual'}</option></select></label>
      </div>
      <div className="kpis rich">
        <Kpi title={ar?'الموازنة':'Budget'} value={money.format(Number(analytics?.totals?.budget||0))} trend={granularity} good/>
        <Kpi title={ar?'الفعلي':'Actual'} value={money.format(Number(analytics?.totals?.actual||0))} trend={ar?'من القيود المرحلة':'Posted GL only'} good/>
        <Kpi title={ar?'الانحراف':'Variance'} value={money.format(Number(analytics?.totals?.variance||0))} trend={`${unfavorable} ${ar?'انحرافات سلبية':'unfavorable rows'}`} good={unfavorable===0}/>
        <Kpi title={ar?'المتوسط التاريخي':'Historical average'} value={money.format(Number(analytics?.totals?.historical_average||0))} trend={ar?'آخر سنتين':'Last two years'} good/>
      </div>
      <Panel title={ar?'الموازنة مقابل الفعلي والتاريخي مع التعليق':'Budget vs actual vs historical with commentary'} icon={<BarChart3 size={18}/>}>
        {budgetId&&<div className="journal-footer"><span>{ar?'التعليق يحدد اتجاه الانحراف وما إذا كان إيجابيًا أو سلبيًا.':'Commentary explains direction and favorability of each variance.'}</span><button onClick={()=>downloadAuthenticated(`/api/v1/operational-controls/budget-analytics/export.csv?budget_id=${budgetId}&start_date=${startDate}&end_date=${endDate}&granularity=${granularity}&historical_years=2`,'budget_actual_historical.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>}
        <DataTable headers={[ar?'الفترة':'Period',ar?'الحساب':'Account',ar?'الموازنة':'Budget',ar?'الفعلي':'Actual',ar?'الانحراف':'Variance',ar?'التاريخي':'Historical',ar?'التعليق':'Comment']} rows={budgetRows.slice(0,60).map((r:any)=>[`${r.period_start} — ${r.period_end}`,r.account_code,money.format(Number(r.budget||0)),money.format(Number(r.actual||0)),money.format(Number(r.variance||0)),money.format(Number(r.historical_average||0)),r.comment])}/>
      </Panel>
    </>}
  </>;
}
