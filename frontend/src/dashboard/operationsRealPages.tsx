import {useEffect, useState} from 'react';
import {Factory, ClipboardCheck, TrendingUp, MonitorCog, ShieldCheck, Plus, Play} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Real working screens replacing the previous demo pages for
// Manufacturing, Quality, CRM, ITSM and Governance/Audit.

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    throw new Error(typeof d==='string'?d:(Array.isArray(d)?d.map((i:any)=>i.msg||JSON.stringify(i)).join(' | '):JSON.stringify(d||x)));
  }
  return x;
}
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const addDays=(n:number)=>{const d=new Date();d.setDate(d.getDate()+n);return iso(d);};
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'4px 10px',borderRadius:7,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12} as const;

// ==================================================== MANUFACTURING
export function ManufacturingPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [boms,setBoms]=useState<any[]>([]); const [orders,setOrders]=useState<any[]>([]);
  const [warehouses,setWarehouses]=useState<any[]>([]); const [oee,setOee]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [orderDate,setOrderDate]=useState(iso()); const [bomId,setBomId]=useState('');
  const [whId,setWhId]=useState(''); const [qty,setQty]=useState('');
  // completion
  const [compQty,setCompQty]=useState(''); const [compHours,setCompHours]=useState('0'); const [lot,setLot]=useState('');

  const load=async()=>{
    try{
      const [b,o,w,e]=await Promise.all([
        json(`/api/v1/manufacturing/boms?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/manufacturing/orders?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/manufacturing/oee?company_id=${companyId}`).catch(()=>null),
      ]);
      setBoms(Array.isArray(b)?b:[]); setOrders(Array.isArray(o)?o:[]);
      setWarehouses(Array.isArray(w)?w:[]); setOee(e);
      if(!bomId&&b?.length)setBomId(String(b[0].id));
      if(!whId&&w?.length)setWhId(String(w[0].id));
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createOrder=async()=>{
    if(!bomId||!whId||!qty){setMsg(ar?'اختر قائمة المواد والمستودع والكمية':'Select BOM, warehouse and quantity');return;}
    setBusy(true);setMsg('');
    try{const r=await json('/api/v1/manufacturing/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,order_date:orderDate,bom_id:Number(bomId),warehouse_id:Number(whId),planned_quantity:Number(qty)})});
      setMsg(ar?`تم إنشاء أمر الإنتاج ${r.number||r.id}`:`Production order ${r.number||r.id} created`);setQty('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const issueMaterials=async(id:number)=>{
    setBusy(true);setMsg('');
    try{await json(`/api/v1/manufacturing/orders/${id}/issue-materials`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId})});
      setMsg(ar?'تم صرف المواد للأمر':'Materials issued');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const complete=async(id:number)=>{
    if(!compQty){setMsg(ar?'أدخل الكمية المنتجة أولًا':'Enter completed quantity first');return;}
    setBusy(true);setMsg('');
    try{const body:any={completion_date:iso(),completed_quantity:Number(compQty),actual_hours:Number(compHours)||0};
      if(lot)body.lot_number=lot;
      await json(`/api/v1/manufacturing/orders/${id}/complete?company_id=${companyId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?'تم إقفال أمر الإنتاج':'Order completed');setCompQty('');setLot('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const open=orders.filter((o:any)=>o.status!=='COMPLETED'&&o.status!=='CANCELLED').length;
  return <>
    <div className="kpis">
      <Kpi title={ar?'أوامر الإنتاج':'Production orders'} value={String(orders.length)} trend="" good icon={<Factory size={22}/>} tone="blue"/>
      <Kpi title={ar?'أوامر مفتوحة':'Open orders'} value={String(open)} trend="" good={open===0} icon={<Play size={22}/>} tone="amber"/>
      <Kpi title={ar?'قوائم المواد':'BOMs'} value={String(boms.length)} trend="" good icon={<ClipboardCheck size={22}/>} tone="violet"/>
      <Kpi title={ar?'كفاءة المعدات OEE':'OEE'} value={oee?`${Number(oee.oee||oee.value||0).toFixed(1)}%`:'—'} trend="" good icon={<TrendingUp size={22}/>} tone="green"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'أمر إنتاج جديد':'New production order'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'تاريخ الأمر':'Order date'}<input type="date" style={field} value={orderDate} onChange={e=>setOrderDate(e.target.value)}/></label>
        <label>{ar?'قائمة المواد':'Bill of materials'}<select style={field} value={bomId} onChange={e=>setBomId(e.target.value)}>{boms.map((b:any)=><option key={b.id} value={b.id}>{b.code||b.name_ar||`BOM ${b.id}`}</option>)}</select></label>
        <label>{ar?'المستودع':'Warehouse'}<select style={field} value={whId} onChange={e=>setWhId(e.target.value)}>{warehouses.map((w:any)=><option key={w.id} value={w.id}>{ar?(w.name_ar||w.code):(w.name_en||w.code)}</option>)}</select></label>
        <label>{ar?'الكمية المخططة':'Planned quantity'}<input type="number" style={field} value={qty} onChange={e=>setQty(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createOrder}>{ar?'إنشاء الأمر':'Create order'}</button></div>
    </Panel>

    <Panel title={ar?'بيانات الإقفال (تُستخدم عند إقفال أمر)':'Completion data (used when closing an order)'} icon={<ClipboardCheck size={18}/>}>
      <div style={grid}>
        <label>{ar?'الكمية المنتجة':'Completed quantity'}<input type="number" style={field} value={compQty} onChange={e=>setCompQty(e.target.value)}/></label>
        <label>{ar?'الساعات الفعلية':'Actual hours'}<input type="number" style={field} value={compHours} onChange={e=>setCompHours(e.target.value)}/></label>
        <label>{ar?'رقم التشغيلة':'Lot number'}<input style={field} value={lot} onChange={e=>setLot(e.target.value)}/></label>
      </div>
    </Panel>

    <Panel title={ar?'أوامر الإنتاج':'Production orders'} icon={<Factory size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المخطط':'Planned',ar?'المنتج':'Completed',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={orders.map((o:any)=>[o.number||o.id,o.order_date,fmt(Number(o.planned_quantity||0)),fmt(Number(o.completed_quantity||0)),o.status,
          <span key={o.id} style={{display:'flex',gap:5}}>
            {o.status==='PLANNED'&&<button style={smallBtn} disabled={busy} onClick={()=>issueMaterials(o.id)}>{ar?'صرف مواد':'Issue'}</button>}
            {(o.status==='IN_PROGRESS'||o.status==='RELEASED')&&<button style={{...smallBtn,background:'#059669'}} disabled={busy} onClick={()=>complete(o.id)}>{ar?'إقفال':'Complete'}</button>}
            {o.status==='COMPLETED'&&'✓'}
          </span>])}/>
    </Panel>
  </>;
}

// ==================================================== QUALITY
export function QualityPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [inspections,setInspections]=useState<any[]>([]); const [ncrs,setNcrs]=useState<any[]>([]);
  const [items,setItems]=useState<any[]>([]); const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [insDate,setInsDate]=useState(iso()); const [insType,setInsType]=useState('INCOMING');
  const [refType,setRefType]=useState('PURCHASE_RECEIPT'); const [refId,setRefId]=useState('1');
  const [itemId,setItemId]=useState(''); const [lot,setLot]=useState('');
  const [inspected,setInspected]=useState(''); const [accepted,setAccepted]=useState(''); const [rejected,setRejected]=useState('0');
  const [notes,setNotes]=useState('');

  const load=async()=>{
    try{
      const [i,n,it,s]=await Promise.all([
        json(`/api/v1/quality/inspections?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/quality/ncrs?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/items?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/quality/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setInspections(Array.isArray(i)?i:[]); setNcrs(Array.isArray(n)?n:[]);
      setItems(Array.isArray(it)?it:[]); setSummary(s);
      if(!itemId&&it?.length)setItemId(String(it[0].id));
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const create=async()=>{
    if(!inspected||!accepted){setMsg(ar?'أدخل الكميات المفحوصة والمقبولة':'Enter inspected and accepted quantities');return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,inspection_date:insDate,inspection_type:insType,
        reference_type:refType,reference_id:Number(refId)||1,
        inspected_quantity:Number(inspected),accepted_quantity:Number(accepted),rejected_quantity:Number(rejected)||0};
      if(itemId)body.item_id=Number(itemId);
      if(lot)body.lot_number=lot;
      if(notes)body.notes=notes;
      const r=await json('/api/v1/quality/inspections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تم تسجيل الفحص ${r.number||r.id}`:`Inspection ${r.number||r.id} recorded`);
      setInspected('');setAccepted('');setRejected('0');setLot('');setNotes('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const TYPES:[string,string,string][]=[['INCOMING','فحص وارد','Incoming'],['IN_PROCESS','أثناء الإنتاج','In-process'],['FINAL','فحص نهائي','Final'],['RETURN','فحص مرتجع','Return']];
  const REFS:[string,string,string][]=[['PURCHASE_RECEIPT','استلام مشتريات','Purchase receipt'],['PRODUCTION_ORDER','أمر إنتاج','Production order'],['SALES_RETURN','مرتجع مبيعات','Sales return']];
  return <>
    <div className="kpis">
      <Kpi title={ar?'الفحوصات':'Inspections'} value={String(inspections.length)} trend="" good icon={<ClipboardCheck size={22}/>} tone="blue"/>
      <Kpi title={ar?'حالات عدم مطابقة':'NCRs'} value={String(ncrs.length)} trend="" good={ncrs.length===0} icon={<ShieldCheck size={22}/>} tone="amber"/>
      <Kpi title={ar?'نسبة القبول':'Acceptance rate'} value={summary?`${Number(summary.acceptance_rate||0).toFixed(1)}%`:'—'} trend="" good icon={<TrendingUp size={22}/>} tone="green"/>
      <Kpi title={ar?'نسبة الرفض':'Rejection rate'} value={summary?`${Number(summary.rejection_rate||0).toFixed(1)}%`:'—'} trend="" good icon={<ShieldCheck size={22}/>} tone="violet"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'تسجيل فحص جودة':'Record a quality inspection'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'تاريخ الفحص':'Inspection date'}<input type="date" style={field} value={insDate} onChange={e=>setInsDate(e.target.value)}/></label>
        <label>{ar?'نوع الفحص':'Inspection type'}<select style={field} value={insType} onChange={e=>setInsType(e.target.value)}>{TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        <label>{ar?'مصدر الفحص':'Reference type'}<select style={field} value={refType} onChange={e=>setRefType(e.target.value)}>{REFS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        <label>{ar?'رقم المرجع':'Reference no.'}<input type="number" style={field} value={refId} onChange={e=>setRefId(e.target.value)}/></label>
        <label>{ar?'الصنف':'Item'}<select style={field} value={itemId} onChange={e=>setItemId(e.target.value)}><option value="">—</option>{items.map((i:any)=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
        <label>{ar?'رقم التشغيلة':'Lot number'}<input style={field} value={lot} onChange={e=>setLot(e.target.value)}/></label>
        <label>{ar?'الكمية المفحوصة':'Inspected qty'}<input type="number" style={field} value={inspected} onChange={e=>setInspected(e.target.value)}/></label>
        <label>{ar?'المقبولة':'Accepted qty'}<input type="number" style={field} value={accepted} onChange={e=>setAccepted(e.target.value)}/></label>
        <label>{ar?'المرفوضة':'Rejected qty'}<input type="number" style={field} value={rejected} onChange={e=>setRejected(e.target.value)}/></label>
        <label>{ar?'ملاحظات':'Notes'}<input style={field} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'تسجيل الفحص':'Record inspection'}</button></div>
    </Panel>

    <Panel title={ar?'سجل الفحوصات':'Inspection log'} icon={<ClipboardCheck size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'النوع':'Type',ar?'مفحوص':'Inspected',ar?'مقبول':'Accepted',ar?'مرفوض':'Rejected',ar?'الحالة':'Status']}
        rows={inspections.map((i:any)=>[i.number||i.id,i.inspection_date,i.inspection_type,fmt(Number(i.inspected_quantity||0)),fmt(Number(i.accepted_quantity||0)),fmt(Number(i.rejected_quantity||0)),i.status||'—'])}/>
    </Panel>
  </>;
}

// ==================================================== CRM
export function CrmPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [campaigns,setCampaigns]=useState<any[]>([]); const [leads,setLeads]=useState<any[]>([]);
  const [opportunities,setOpportunities]=useState<any[]>([]); const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [tab,setTab]=useState<'campaigns'|'leads'>('campaigns');
  const [code,setCode]=useState(''); const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [channel,setChannel]=useState('DIGITAL'); const [budget,setBudget]=useState('0');
  const [start,setStart]=useState(iso()); const [end,setEnd]=useState(addDays(60));
  const [lCampaign,setLCampaign]=useState(''); const [lName,setLName]=useState(''); const [lEmail,setLEmail]=useState('');
  const [lSource,setLSource]=useState('DIGITAL'); const [lValue,setLValue]=useState('');

  const load=async()=>{
    try{
      const [c,l,o,s]=await Promise.all([
        json(`/api/v1/crm/campaigns?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/crm/leads?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/crm/opportunities?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/crm/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setCampaigns(Array.isArray(c)?c:[]); setLeads(Array.isArray(l)?l:[]);
      setOpportunities(Array.isArray(o)?o:[]); setSummary(s);
      if(!lCampaign&&c?.length)setLCampaign(String(c[0].id));
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createCampaign=async()=>{
    if(!code||!nameAr||!nameEn){setMsg(ar?'الكود والاسمان إلزامية':'Code and names required');return;}
    setBusy(true);setMsg('');
    try{const r=await json('/api/v1/crm/campaigns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,code,name_ar:nameAr,name_en:nameEn,channel,budget:Number(budget)||0,start_date:start,end_date:end})});
      setMsg(ar?`تم إنشاء الحملة ${r.code||r.id}`:`Campaign ${r.code||r.id} created`);setCode('');setNameAr('');setNameEn('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const createLead=async()=>{
    if(!lName){setMsg(ar?'اسم العميل المحتمل إلزامي':'Lead name required');return;}
    setBusy(true);setMsg('');
    try{const body:any={company_id:companyId,source:lSource,name:lName,estimated_value:Number(lValue)||0};
      if(lCampaign)body.campaign_id=Number(lCampaign);
      if(lEmail)body.email=lEmail;
      const r=await json('/api/v1/crm/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تم تسجيل العميل المحتمل ${r.id}`:`Lead ${r.id} created`);setLName('');setLEmail('');setLValue('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const CHANNELS:[string,string,string][]=[['DIGITAL','رقمي','Digital'],['DIRECT','مباشر','Direct'],['REFERRAL','ترشيح','Referral'],['EVENT','فعالية','Event']];
  return <>
    <div className="kpis">
      <Kpi title={ar?'الحملات':'Campaigns'} value={String(campaigns.length)} trend="" good icon={<TrendingUp size={22}/>} tone="blue"/>
      <Kpi title={ar?'العملاء المحتملون':'Leads'} value={String(leads.length)} trend="" good icon={<TrendingUp size={22}/>} tone="violet"/>
      <Kpi title={ar?'الفرص':'Opportunities'} value={String(opportunities.length)} trend="" good icon={<ClipboardCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'قيمة الفرص':'Pipeline value'} value={summary?fmt(Number(summary.pipeline_value||0)):'—'} trend="" good icon={<TrendingUp size={22}/>} tone="amber"/>
    </div>
    <div style={{display:'flex',gap:8,margin:'14px 0'}}>
      {([['campaigns',ar?'الحملات':'Campaigns'],['leads',ar?'العملاء المحتملون':'Leads']] as [typeof tab,string][]).map(([k,l])=>
        <button key={k} onClick={()=>setTab(k)} style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>
    {msg&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    {tab==='campaigns'&&<>
      <Panel title={ar?'حملة تسويقية جديدة':'New marketing campaign'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={code} onChange={e=>setCode(e.target.value)}/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
          <label>{ar?'القناة':'Channel'}<select style={field} value={channel} onChange={e=>setChannel(e.target.value)}>{CHANNELS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'الميزانية':'Budget'}<input type="number" style={field} value={budget} onChange={e=>setBudget(e.target.value)}/></label>
          <label>{ar?'البدء':'Start'}<input type="date" style={field} value={start} onChange={e=>setStart(e.target.value)}/></label>
          <label>{ar?'الانتهاء':'End'}<input type="date" style={field} value={end} onChange={e=>setEnd(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createCampaign}>{ar?'إنشاء الحملة':'Create campaign'}</button></div>
      </Panel>
      <Panel title={ar?'الحملات':'Campaigns'} icon={<TrendingUp size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'القناة':'Channel',ar?'الميزانية':'Budget',ar?'الحالة':'Status']}
          rows={campaigns.map((c:any)=>[c.code,ar?c.name_ar:c.name_en,c.channel,fmt(Number(c.budget||0)),c.status||'ACTIVE'])}/>
      </Panel>
    </>}

    {tab==='leads'&&<>
      <Panel title={ar?'عميل محتمل جديد':'New lead'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'الحملة':'Campaign'}<select style={field} value={lCampaign} onChange={e=>setLCampaign(e.target.value)}><option value="">—</option>{campaigns.map((c:any)=><option key={c.id} value={c.id}>{c.code} — {ar?c.name_ar:c.name_en}</option>)}</select></label>
          <label>{ar?'الاسم':'Name'}<input style={field} value={lName} onChange={e=>setLName(e.target.value)}/></label>
          <label>{ar?'البريد':'Email'}<input type="email" style={field} value={lEmail} onChange={e=>setLEmail(e.target.value)}/></label>
          <label>{ar?'المصدر':'Source'}<select style={field} value={lSource} onChange={e=>setLSource(e.target.value)}>{CHANNELS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'القيمة المتوقعة':'Estimated value'}<input type="number" style={field} value={lValue} onChange={e=>setLValue(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createLead}>{ar?'تسجيل العميل المحتمل':'Create lead'}</button></div>
      </Panel>
      <Panel title={ar?'العملاء المحتملون':'Leads'} icon={<TrendingUp size={18}/>}>
        <DataTable headers={[ar?'الاسم':'Name',ar?'المصدر':'Source',ar?'القيمة':'Value',ar?'الحالة':'Status']}
          rows={leads.map((l:any)=>[l.name,l.source,fmt(Number(l.estimated_value||0)),l.status||'NEW'])}/>
      </Panel>
    </>}
  </>;
}

// ==================================================== ITSM
export function ItPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tickets,setTickets]=useState<any[]>([]); const [assets,setAssets]=useState<any[]>([]);
  const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [subject,setSubject]=useState(''); const [descr,setDescr]=useState('');
  const [category,setCategory]=useState('GENERAL'); const [priority,setPriority]=useState('MEDIUM'); const [dueHours,setDueHours]=useState('24');

  const load=async()=>{
    try{
      const [t,a,s]=await Promise.all([
        json(`/api/v1/itsm/tickets?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/itsm/assets?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/itsm/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setTickets(Array.isArray(t)?t:[]); setAssets(Array.isArray(a)?a:[]); setSummary(s);
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createTicket=async()=>{
    if(!subject){setMsg(ar?'الموضوع إلزامي':'Subject required');return;}
    setBusy(true);setMsg('');
    try{const body:any={company_id:companyId,category,subject,priority,due_hours:Number(dueHours)||24};
      if(descr)body.description=descr;
      const r=await json('/api/v1/itsm/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تم فتح التذكرة ${r.number||r.id}`:`Ticket ${r.number||r.id} opened`);setSubject('');setDescr('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const startTicket=async(id:number)=>{
    setBusy(true);setMsg('');
    try{await json(`/api/v1/itsm/tickets/${id}/start?company_id=${companyId}`,{method:'POST'});setMsg(ar?'بدأ العمل على التذكرة':'Ticket started');await load();}
    catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const CATS:[string,string,string][]=[['GENERAL','عام','General'],['ACCESS','صلاحيات','Access'],['HARDWARE','أجهزة','Hardware'],['SOFTWARE','برمجيات','Software'],['NETWORK','شبكة','Network']];
  const PRIOS:[string,string,string][]=[['LOW','منخفضة','Low'],['MEDIUM','متوسطة','Medium'],['HIGH','عالية','High'],['CRITICAL','حرجة','Critical']];
  const openT=tickets.filter((t:any)=>t.status!=='CLOSED'&&t.status!=='RESOLVED').length;
  return <>
    <div className="kpis">
      <Kpi title={ar?'التذاكر':'Tickets'} value={String(tickets.length)} trend="" good icon={<MonitorCog size={22}/>} tone="blue"/>
      <Kpi title={ar?'مفتوحة':'Open'} value={String(openT)} trend="" good={openT===0} icon={<MonitorCog size={22}/>} tone="amber"/>
      <Kpi title={ar?'أصول تقنية':'IT assets'} value={String(assets.length)} trend="" good icon={<ShieldCheck size={22}/>} tone="violet"/>
      <Kpi title={ar?'الالتزام بالـSLA':'SLA compliance'} value={summary?`${Number(summary.sla_compliance||0).toFixed(0)}%`:'—'} trend="" good icon={<ClipboardCheck size={22}/>} tone="green"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'تذكرة دعم جديدة':'New support ticket'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'الموضوع':'Subject'}<input style={field} value={subject} onChange={e=>setSubject(e.target.value)}/></label>
        <label>{ar?'الفئة':'Category'}<select style={field} value={category} onChange={e=>setCategory(e.target.value)}>{CATS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        <label>{ar?'الأولوية':'Priority'}<select style={field} value={priority} onChange={e=>setPriority(e.target.value)}>{PRIOS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        <label>{ar?'مهلة الإنجاز (ساعة)':'Due (hours)'}<input type="number" min="1" max="720" style={field} value={dueHours} onChange={e=>setDueHours(e.target.value)}/></label>
        <label>{ar?'الوصف':'Description'}<input style={field} value={descr} onChange={e=>setDescr(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createTicket}>{ar?'فتح التذكرة':'Open ticket'}</button></div>
    </Panel>

    <Panel title={ar?'التذاكر':'Tickets'} icon={<MonitorCog size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'الموضوع':'Subject',ar?'الفئة':'Category',ar?'الأولوية':'Priority',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={tickets.map((t:any)=>[t.number||t.id,t.subject,t.category,t.priority,t.status,
          t.status==='OPEN'||t.status==='NEW'?<button key={t.id} style={smallBtn} disabled={busy} onClick={()=>startTicket(t.id)}>{ar?'بدء':'Start'}</button>:'—'])}/>
    </Panel>
  </>;
}
