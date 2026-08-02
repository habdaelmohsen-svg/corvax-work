import {useEffect, useMemo, useState} from 'react';
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
  const [warehouses,setWarehouses]=useState<any[]>([]); const [items,setItems]=useState<any[]>([]);
  const [workCenters,setWorkCenters]=useState<any[]>([]); const [mrpRuns,setMrpRuns]=useState<any[]>([]);
  const [oee,setOee]=useState<any>(null); const [search,setSearch]=useState('');
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  // bill of materials
  const [bomCode,setBomCode]=useState(''); const [bomVersion,setBomVersion]=useState('1');
  const [finishedItemId,setFinishedItemId]=useState(''); const [outputQty,setOutputQty]=useState('1');
  const [componentItemId,setComponentItemId]=useState(''); const [componentQty,setComponentQty]=useState('1');
  const [scrapPercent,setScrapPercent]=useState('0'); const [workCenterId,setWorkCenterId]=useState('');
  const [standardHours,setStandardHours]=useState('0');
  // production order
  const [orderDate,setOrderDate]=useState(iso()); const [bomId,setBomId]=useState('');
  const [whId,setWhId]=useState(''); const [qty,setQty]=useState('');
  // material requirements planning
  const [mrpWarehouseId,setMrpWarehouseId]=useState(''); const [planningDate,setPlanningDate]=useState(iso());
  const [horizonEnd,setHorizonEnd]=useState(addDays(30)); const [demandItemId,setDemandItemId]=useState('');
  const [dueDate,setDueDate]=useState(addDays(14)); const [demandQty,setDemandQty]=useState('');
  const [safetyStock,setSafetyStock]=useState('0'); const [sourceReference,setSourceReference]=useState('');
  // completion
  const [compQty,setCompQty]=useState(''); const [compHours,setCompHours]=useState('0'); const [lot,setLot]=useState('');

  const load=async()=>{
    try{
      const [b,o,w,it,wc,m,e]=await Promise.all([
        json(`/api/v1/manufacturing/boms?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/manufacturing/orders?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/items?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/manufacturing/work-centers?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/manufacturing/advanced/mrp-runs?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/manufacturing/oee?company_id=${companyId}`).catch(()=>null),
      ]);
      setBoms(Array.isArray(b)?b:[]); setOrders(Array.isArray(o)?o:[]);
      setWarehouses(Array.isArray(w)?w:[]); setItems(Array.isArray(it)?it:[]);
      setWorkCenters(Array.isArray(wc)?wc:[]); setMrpRuns(Array.isArray(m)?m:[]); setOee(e);
      if(!bomId&&b?.length)setBomId(String(b[0].id));
      if(!whId&&w?.length)setWhId(String(w[0].id));
      if(!mrpWarehouseId&&w?.length)setMrpWarehouseId(String(w[0].id));
      const finished=it?.find((row:any)=>row.item_type==='FINISHED_GOOD')||it?.[0];
      const component=it?.find((row:any)=>row.id!==finished?.id)||it?.[0];
      if(!finishedItemId&&finished)setFinishedItemId(String(finished.id));
      if(!componentItemId&&component)setComponentItemId(String(component.id));
      if(!demandItemId&&finished)setDemandItemId(String(finished.id));
      if(!workCenterId&&wc?.length)setWorkCenterId(String(wc[0].id));
    }catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createBom=async()=>{
    if(!bomCode.trim()||!finishedItemId||!componentItemId||Number(outputQty)<=0||Number(componentQty)<=0){
      setMsg(ar?'أدخل كود القائمة والمنتج والمكوّن والكميات الصحيحة':'Enter the BOM code, product, component and valid quantities');return;
    }
    if(finishedItemId===componentItemId){setMsg(ar?'لا يمكن أن يكون المنتج النهائي مكوّنًا لنفسه':'The finished product cannot be its own component');return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,code:bomCode.trim().toUpperCase(),version:Number(bomVersion)||1,
        finished_item_id:Number(finishedItemId),output_quantity:Number(outputQty),standard_hours:Number(standardHours)||0,
        lines:[{component_item_id:Number(componentItemId),quantity:Number(componentQty),scrap_percent:Number(scrapPercent)||0}]};
      if(workCenterId)body.work_center_id=Number(workCenterId);
      const r=await json('/api/v1/manufacturing/boms',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تم إنشاء قائمة المواد ${r.code} — الإصدار ${r.version}`:`BOM ${r.code} version ${r.version} created`);
      setBomCode('');setComponentQty('1');setScrapPercent('0');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

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

  const createMrp=async()=>{
    if(!mrpWarehouseId||!demandItemId||Number(demandQty)<=0){setMsg(ar?'اختر المستودع والصنف وأدخل طلبًا أكبر من صفر':'Select warehouse and item, and enter demand greater than zero');return;}
    if(horizonEnd<planningDate||dueDate<planningDate||dueDate>horizonEnd){setMsg(ar?'يجب أن يقع تاريخ الطلب داخل أفق التخطيط':'Demand date must fall inside the planning horizon');return;}
    setBusy(true);setMsg('');
    try{
      const demand:any={item_id:Number(demandItemId),due_date:dueDate,quantity:Number(demandQty),safety_stock:Number(safetyStock)||0,source_type:'FORECAST'};
      if(sourceReference.trim())demand.source_reference=sourceReference.trim();
      const r=await json('/api/v1/manufacturing/advanced/mrp-runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        company_id:companyId,warehouse_id:Number(mrpWarehouseId),planning_date:planningDate,horizon_end:horizonEnd,demands:[demand],
      })});
      setMsg(r.job_id
        ?(ar?`تم إرسال تشغيل MRP للمحرك الخلفي (${r.job_id})`:`MRP run submitted (${r.job_id})`)
        :(ar?`تم حساب تشغيل MRP ${r.code||r.id}`:`MRP run ${r.code||r.id} calculated`));
      setDemandQty('');setSourceReference('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const approveMrp=async(id:number)=>{
    setBusy(true);setMsg('');
    try{const r=await json(`/api/v1/manufacturing/advanced/mrp-runs/${id}/approve`,{method:'POST'});
      setMsg(ar?`تم اعتماد تشغيل MRP ${r.code||id}`:`MRP run ${r.code||id} approved`);await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const filtered=useMemo(()=>{
    const q=search.trim().toLocaleLowerCase();
    const matches=(...values:any[])=>!q||values.some((value)=>String(value??'').toLocaleLowerCase().includes(q));
    return {
      boms:boms.filter((b:any)=>matches(b.code,b.version,b.finished_item_code,b.finished_item_name_ar,b.finished_item_name_en,b.work_center,...(b.lines||[]).flatMap((line:any)=>[line.component_code,line.component_name_ar,line.component_name_en]))),
      orders:orders.filter((o:any)=>matches(o.number,o.order_date,o.status,o.bom_code,o.finished_item_code)),
      mrpRuns:mrpRuns.filter((run:any)=>matches(run.code,run.status,run.warehouse_code,run.planning_date,run.horizon_end,...(run.demands||[]).flatMap((line:any)=>[line.item_code,line.source_reference]))),
    };
  },[search,boms,orders,mrpRuns]);

  const open=orders.filter((o:any)=>o.status!=='COMPLETED'&&o.status!=='CANCELLED').length;
  return <>
    <div className="kpis">
      <Kpi title={ar?'أوامر الإنتاج':'Production orders'} value={String(orders.length)} trend="" good icon={<Factory size={22}/>} tone="blue"/>
      <Kpi title={ar?'أوامر مفتوحة':'Open orders'} value={String(open)} trend="" good={open===0} icon={<Play size={22}/>} tone="amber"/>
      <Kpi title={ar?'قوائم المواد':'BOMs'} value={String(boms.length)} trend="" good icon={<ClipboardCheck size={22}/>} tone="violet"/>
      <Kpi title={ar?'كفاءة المعدات OEE':'OEE'} value={oee?`${Number(oee.oee||oee.value||0).toFixed(1)}%`:'—'} trend="" good icon={<TrendingUp size={22}/>} tone="green"/>
    </div>
    {msg&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}

    <Panel title={ar?'البحث في التصنيع':'Manufacturing search'} icon={<Factory size={18}/> }>
      <div style={{padding:12}}>
        <label>{ar?'ابحث بالكود أو المنتج أو المكوّن أو الحالة أو المرجع':'Search by code, product, component, status or reference'}
          <input data-testid="manufacturing-search" type="search" style={field} value={search} onChange={e=>setSearch(e.target.value)} placeholder={ar?'مثال: BOM أو FG-001 أو CALCULATED':'e.g. BOM, FG-001 or CALCULATED'}/>
        </label>
      </div>
    </Panel>

    <Panel title={ar?'قائمة مواد جديدة':'New bill of materials'} icon={<Plus size={18}/> }>
      <div style={grid}>
        <label>{ar?'كود القائمة':'BOM code'}<input data-testid="manufacturing-bom-code" style={field} value={bomCode} onChange={e=>setBomCode(e.target.value)} placeholder="BOM-..."/></label>
        <label>{ar?'الإصدار':'Version'}<input data-testid="manufacturing-bom-version" type="number" min="1" style={field} value={bomVersion} onChange={e=>setBomVersion(e.target.value)}/></label>
        <label>{ar?'المنتج النهائي':'Finished product'}<select data-testid="manufacturing-bom-finished-item" style={field} value={finishedItemId} onChange={e=>setFinishedItemId(e.target.value)}>{items.map((item:any)=><option key={item.id} value={item.id}>{item.code} — {ar?item.name_ar:item.name_en}</option>)}</select></label>
        <label>{ar?'كمية المخرج':'Output quantity'}<input data-testid="manufacturing-bom-output-qty" type="number" min="0.0001" step="any" style={field} value={outputQty} onChange={e=>setOutputQty(e.target.value)}/></label>
        <label>{ar?'المكوّن':'Component'}<select data-testid="manufacturing-bom-component" style={field} value={componentItemId} onChange={e=>setComponentItemId(e.target.value)}>{items.map((item:any)=><option key={item.id} value={item.id}>{item.code} — {ar?item.name_ar:item.name_en}</option>)}</select></label>
        <label>{ar?'كمية المكوّن':'Component quantity'}<input data-testid="manufacturing-bom-component-qty" type="number" min="0.0001" step="any" style={field} value={componentQty} onChange={e=>setComponentQty(e.target.value)}/></label>
        <label>{ar?'نسبة الهالك %':'Scrap %'}<input type="number" min="0" max="100" step="any" style={field} value={scrapPercent} onChange={e=>setScrapPercent(e.target.value)}/></label>
        <label>{ar?'مركز العمل (اختياري)':'Work center (optional)'}<select data-testid="manufacturing-bom-work-center" style={field} value={workCenterId} onChange={e=>setWorkCenterId(e.target.value)}><option value="">—</option>{workCenters.map((center:any)=><option key={center.id} value={center.id}>{center.code} — {ar?center.name_ar:center.name_en}</option>)}</select></label>
        <label>{ar?'الساعات المعيارية':'Standard hours'}<input type="number" min="0" step="any" style={field} value={standardHours} onChange={e=>setStandardHours(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button data-testid="manufacturing-bom-create" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createBom}>{ar?'إنشاء قائمة المواد':'Create BOM'}</button></div>
    </Panel>

    <Panel title={ar?'قوائم المواد':'Bills of materials'} icon={<ClipboardCheck size={18}/> }>
      <div data-testid="manufacturing-bom-list"><DataTable headers={[ar?'الكود':'Code',ar?'المنتج النهائي':'Finished product',ar?'المخرج':'Output',ar?'المكوّنات':'Components',ar?'مركز العمل':'Work center',ar?'الحالة':'Status']}
        rows={filtered.boms.map((b:any)=>[`${b.code} / v${b.version}`,`${b.finished_item_code||''} — ${ar?(b.finished_item_name_ar||''):(b.finished_item_name_en||'')}`,fmt(Number(b.output_quantity||0)),
          (b.lines||[]).map((line:any)=>`${line.component_code} × ${fmt(Number(line.quantity||0))}`).join('، ')||'—',b.work_center||'—',b.status])}/></div>
    </Panel>

    <Panel title={ar?'أمر إنتاج جديد':'New production order'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'تاريخ الأمر':'Order date'}<input type="date" style={field} value={orderDate} onChange={e=>setOrderDate(e.target.value)}/></label>
        <label>{ar?'قائمة المواد':'Bill of materials'}<select style={field} value={bomId} onChange={e=>setBomId(e.target.value)}>{boms.map((b:any)=><option key={b.id} value={b.id}>{b.code||b.name_ar||`BOM ${b.id}`}</option>)}</select></label>
        <label>{ar?'المستودع':'Warehouse'}<select style={field} value={whId} onChange={e=>setWhId(e.target.value)}>{warehouses.map((w:any)=><option key={w.id} value={w.id}>{ar?(w.name_ar||w.code):(w.name_en||w.code)}</option>)}</select></label>
        <label>{ar?'الكمية المخططة':'Planned quantity'}<input type="number" style={field} value={qty} onChange={e=>setQty(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createOrder}>{ar?'إنشاء الأمر':'Create order'}</button></div>
    </Panel>

    <Panel title={ar?'تشغيل تخطيط احتياجات المواد MRP':'Run material requirements planning (MRP)'} icon={<TrendingUp size={18}/> }>
      <div style={grid}>
        <label>{ar?'المستودع':'Warehouse'}<select data-testid="manufacturing-mrp-warehouse" style={field} value={mrpWarehouseId} onChange={e=>setMrpWarehouseId(e.target.value)}>{warehouses.map((w:any)=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
        <label>{ar?'تاريخ التخطيط':'Planning date'}<input type="date" style={field} value={planningDate} onChange={e=>setPlanningDate(e.target.value)}/></label>
        <label>{ar?'نهاية الأفق':'Horizon end'}<input type="date" style={field} value={horizonEnd} onChange={e=>setHorizonEnd(e.target.value)}/></label>
        <label>{ar?'صنف الطلب':'Demand item'}<select data-testid="manufacturing-mrp-demand-item" style={field} value={demandItemId} onChange={e=>setDemandItemId(e.target.value)}>{items.map((item:any)=><option key={item.id} value={item.id}>{item.code} — {ar?item.name_ar:item.name_en}</option>)}</select></label>
        <label>{ar?'تاريخ الاحتياج':'Due date'}<input type="date" style={field} value={dueDate} onChange={e=>setDueDate(e.target.value)}/></label>
        <label>{ar?'كمية الطلب':'Demand quantity'}<input data-testid="manufacturing-mrp-demand-qty" type="number" min="0.0001" step="any" style={field} value={demandQty} onChange={e=>setDemandQty(e.target.value)}/></label>
        <label>{ar?'مخزون الأمان':'Safety stock'}<input type="number" min="0" step="any" style={field} value={safetyStock} onChange={e=>setSafetyStock(e.target.value)}/></label>
        <label>{ar?'مرجع التوقع':'Forecast reference'}<input data-testid="manufacturing-mrp-source-reference" style={field} value={sourceReference} onChange={e=>setSourceReference(e.target.value)} placeholder="FORECAST-..."/></label>
      </div>
      <div style={{padding:12}}><button data-testid="manufacturing-mrp-create" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createMrp}>{ar?'حساب MRP':'Calculate MRP'}</button></div>
    </Panel>

    <Panel title={ar?'تشغيلات MRP':'MRP runs'} icon={<TrendingUp size={18}/> }>
      <div data-testid="manufacturing-mrp-list"><DataTable headers={[ar?'الكود':'Code',ar?'المستودع':'Warehouse',ar?'فترة التخطيط':'Planning horizon',ar?'الطلب':'Demand',ar?'التوريد المخطط':'Planned supply',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={filtered.mrpRuns.map((run:any)=>[run.code,run.warehouse_code,`${run.planning_date} ← ${run.horizon_end}`,fmt(Number(run.gross_demand||0)),fmt(Number(run.total_planned_supply||0)),run.status,
          run.status==='CALCULATED'?<button key={run.id} data-testid={`manufacturing-mrp-approve-${run.id}`} style={{...smallBtn,background:'#059669'}} disabled={busy} onClick={()=>approveMrp(run.id)}>{ar?'اعتماد':'Approve'}</button>:'✓'])}/></div>
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
        rows={filtered.orders.map((o:any)=>[o.number||o.id,o.order_date,fmt(Number(o.planned_quantity||0)),fmt(Number(o.completed_quantity||0)),o.status,
          <span key={o.id} style={{display:'flex',gap:5}}>
            {o.status==='RELEASED'&&<button style={smallBtn} disabled={busy} onClick={()=>issueMaterials(o.id)}>{ar?'صرف مواد':'Issue'}</button>}
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
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false); const [search,setSearch]=useState('');
  const [insDate,setInsDate]=useState(iso()); const [insType,setInsType]=useState('INCOMING');
  const [refType,setRefType]=useState('PURCHASE_RECEIPT'); const [refId,setRefId]=useState('1');
  const [itemId,setItemId]=useState(''); const [lot,setLot]=useState('');
  const [inspected,setInspected]=useState(''); const [accepted,setAccepted]=useState(''); const [rejected,setRejected]=useState('0');
  const [notes,setNotes]=useState(''); const [severity,setSeverity]=useState('MEDIUM');
  const [selectedNcrId,setSelectedNcrId]=useState(''); const [rootCause,setRootCause]=useState('');
  const [correctiveAction,setCorrectiveAction]=useState(''); const [ncrDueDate,setNcrDueDate]=useState(addDays(7));
  const [ncrStatus,setNcrStatus]=useState('IN_PROGRESS');

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
        inspected_quantity:Number(inspected),accepted_quantity:Number(accepted),rejected_quantity:Number(rejected)||0,severity};
      if(itemId)body.item_id=Number(itemId);
      if(lot)body.lot_number=lot;
      if(notes)body.notes=notes;
      const r=await json('/api/v1/quality/inspections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?`تم تسجيل الفحص ${r.number||r.id}`:`Inspection ${r.number||r.id} recorded`);
      setInspected('');setAccepted('');setRejected('0');setLot('');setNotes('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const selectNcr=(row:any)=>{
    setSelectedNcrId(String(row.id));setRootCause(row.root_cause||'');setCorrectiveAction(row.corrective_action||'');
    setNcrDueDate(row.due_date?String(row.due_date).slice(0,10):addDays(7));setNcrStatus(row.status==='OPEN'?'IN_PROGRESS':row.status);
  };
  const updateNcr=async()=>{
    if(!selectedNcrId||rootCause.trim().length<2||correctiveAction.trim().length<2){
      setMsg(ar?'اختر حالة عدم مطابقة وأدخل السبب الجذري والإجراء التصحيحي':'Select an NCR and enter its root cause and corrective action');return;
    }
    setBusy(true);setMsg('');
    try{
      const r=await json(`/api/v1/quality/ncrs/${selectedNcrId}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({root_cause:rootCause.trim(),corrective_action:correctiveAction.trim(),due_date:ncrDueDate||null,status:ncrStatus})});
      setMsg(ar?`تم تحديث ${r.number} إلى ${r.status}`:`${r.number} updated to ${r.status}`);await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const q=search.trim().toLowerCase();
  const visibleInspections=q?inspections.filter((row:any)=>[row.number,row.inspection_type,row.reference_type,row.item_code,row.lot_number,row.result].some(v=>String(v||'').toLowerCase().includes(q))):inspections;
  const visibleNcrs=q?ncrs.filter((row:any)=>[row.number,row.severity,row.description,row.root_cause,row.corrective_action,row.status].some(v=>String(v||'').toLowerCase().includes(q))):ncrs;

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
    <div style={{margin:'12px 0'}}><input data-testid="quality-search" style={field} value={search} onChange={e=>setSearch(e.target.value)} placeholder={ar?'بحث في رقم الفحص أو التشغيلة أو NCR أو الحالة':'Search inspection, lot, NCR or status'}/></div>

    <Panel title={ar?'تسجيل فحص جودة':'Record a quality inspection'} icon={<Plus size={18}/>}>
      <div style={grid}>
        <label>{ar?'تاريخ الفحص':'Inspection date'}<input data-testid="quality-date" type="date" style={field} value={insDate} onChange={e=>setInsDate(e.target.value)}/></label>
        <label>{ar?'نوع الفحص':'Inspection type'}<select data-testid="quality-type" style={field} value={insType} onChange={e=>setInsType(e.target.value)}>{TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        <label>{ar?'مصدر الفحص':'Reference type'}<select data-testid="quality-reference-type" style={field} value={refType} onChange={e=>setRefType(e.target.value)}>{REFS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        <label>{ar?'رقم المرجع':'Reference no.'}<input data-testid="quality-reference-id" type="number" style={field} value={refId} onChange={e=>setRefId(e.target.value)}/></label>
        <label>{ar?'الصنف':'Item'}<select data-testid="quality-item" style={field} value={itemId} onChange={e=>setItemId(e.target.value)}><option value="">—</option>{items.map((i:any)=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
        <label>{ar?'رقم التشغيلة':'Lot number'}<input data-testid="quality-lot" style={field} value={lot} onChange={e=>setLot(e.target.value)}/></label>
        <label>{ar?'الكمية المفحوصة':'Inspected qty'}<input data-testid="quality-inspected" type="number" style={field} value={inspected} onChange={e=>setInspected(e.target.value)}/></label>
        <label>{ar?'المقبولة':'Accepted qty'}<input data-testid="quality-accepted" type="number" style={field} value={accepted} onChange={e=>setAccepted(e.target.value)}/></label>
        <label>{ar?'المرفوضة':'Rejected qty'}<input data-testid="quality-rejected" type="number" style={field} value={rejected} onChange={e=>setRejected(e.target.value)}/></label>
        <label>{ar?'خطورة عدم المطابقة':'NCR severity'}<select data-testid="quality-severity" style={field} value={severity} onChange={e=>setSeverity(e.target.value)}><option value="LOW">LOW</option><option value="MEDIUM">MEDIUM</option><option value="HIGH">HIGH</option><option value="CRITICAL">CRITICAL</option></select></label>
        <label>{ar?'ملاحظات':'Notes'}<input style={field} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
      </div>
      <div style={{padding:12}}><button data-testid="quality-create-inspection" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'تسجيل الفحص':'Record inspection'}</button></div>
    </Panel>

    <Panel title={ar?'سجل الفحوصات':'Inspection log'} icon={<ClipboardCheck size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'النوع':'Type',ar?'مفحوص':'Inspected',ar?'مقبول':'Accepted',ar?'مرفوض':'Rejected',ar?'الحالة':'Status']}
        rows={visibleInspections.map((i:any)=>[i.number||i.id,i.inspection_date,i.inspection_type,fmt(Number(i.inspected_quantity||0)),fmt(Number(i.accepted_quantity||0)),fmt(Number(i.rejected_quantity||0)),i.result||'—'])}/>
    </Panel>

    <Panel title={ar?'معالجة حالات عدم المطابقة':'Non-conformance remediation'} icon={<ShieldCheck size={18}/> }>
      <div style={grid}>
        <label>{ar?'حالة عدم المطابقة':'NCR'}<select data-testid="quality-ncr-select" style={field} value={selectedNcrId} onChange={e=>{const row=ncrs.find((x:any)=>String(x.id)===e.target.value);if(row)selectNcr(row);else setSelectedNcrId('')}}><option value="">—</option>{visibleNcrs.map((n:any)=><option key={n.id} value={n.id}>{n.number} — {n.status}</option>)}</select></label>
        <label>{ar?'السبب الجذري':'Root cause'}<input data-testid="quality-root-cause" style={field} value={rootCause} onChange={e=>setRootCause(e.target.value)}/></label>
        <label>{ar?'الإجراء التصحيحي':'Corrective action'}<input data-testid="quality-corrective-action" style={field} value={correctiveAction} onChange={e=>setCorrectiveAction(e.target.value)}/></label>
        <label>{ar?'تاريخ الاستحقاق':'Due date'}<input type="date" style={field} value={ncrDueDate} onChange={e=>setNcrDueDate(e.target.value)}/></label>
        <label>{ar?'الحالة':'Status'}<select data-testid="quality-ncr-status" style={field} value={ncrStatus} onChange={e=>setNcrStatus(e.target.value)}><option value="IN_PROGRESS">IN_PROGRESS</option><option value="VERIFIED">VERIFIED</option><option value="CLOSED">CLOSED</option></select></label>
      </div>
      <div style={{padding:12}}><button data-testid="quality-update-ncr" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={updateNcr}>{ar?'حفظ المعالجة':'Save remediation'}</button></div>
      <DataTable headers={[ar?'الرقم':'No.',ar?'الخطورة':'Severity',ar?'الوصف':'Description',ar?'السبب':'Root cause',ar?'الإجراء':'Action',ar?'الحالة':'Status']}
        rows={visibleNcrs.map((n:any)=>[n.number,n.severity,n.description,n.root_cause||'—',n.corrective_action||'—',<button key={n.id} data-testid={`quality-select-ncr-${n.id}`} style={smallBtn} onClick={()=>selectNcr(n)}>{n.status}</button>])}/>
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

// Complete employee workflows used by the live dashboard.  The earlier compact
// screens remain exported for backwards compatibility with old embedded tests.
export function CrmEmployeePage({ar,companyId}:{ar:boolean;companyId:number}){
  const [campaigns,setCampaigns]=useState<any[]>([]);const [leads,setLeads]=useState<any[]>([]);const [opps,setOpps]=useState<any[]>([]);const [summary,setSummary]=useState<any>(null);
  const [tab,setTab]=useState<'campaigns'|'leads'|'opportunities'>('campaigns');const [search,setSearch]=useState('');const [msg,setMsg]=useState('');const [busy,setBusy]=useState(false);
  const [code,setCode]=useState('');const [nameAr,setNameAr]=useState('');const [nameEn,setNameEn]=useState('');const [channel,setChannel]=useState('DIGITAL');const [budget,setBudget]=useState('0');const [start,setStart]=useState(iso());const [end,setEnd]=useState(addDays(60));
  const [campaignId,setCampaignId]=useState('');const [leadName,setLeadName]=useState('');const [leadEmail,setLeadEmail]=useState('');const [leadPhone,setLeadPhone]=useState('');const [leadSource,setLeadSource]=useState('DIGITAL');const [leadValue,setLeadValue]=useState('0');const [leadNotes,setLeadNotes]=useState('');
  const [leadId,setLeadId]=useState('');const [convertTitle,setConvertTitle]=useState('');const [convertAmount,setConvertAmount]=useState('0');const [convertProbability,setConvertProbability]=useState('25');const [convertDate,setConvertDate]=useState(addDays(30));
  const [oppId,setOppId]=useState('');const [stage,setStage]=useState('QUALIFICATION');const [oppAmount,setOppAmount]=useState('0');const [probability,setProbability]=useState('25');const [closeDate,setCloseDate]=useState(addDays(30));const [lossReason,setLossReason]=useState('');
  const channels=[['DIGITAL',ar?'رقمي':'Digital'],['DIRECT',ar?'مباشر':'Direct'],['REFERRAL',ar?'ترشيح':'Referral'],['EVENT',ar?'فعالية':'Event']];
  const load=async()=>{try{const [c,l,o,s]=await Promise.all([json(`/api/v1/crm/campaigns?company_id=${companyId}`),json(`/api/v1/crm/leads?company_id=${companyId}`),json(`/api/v1/crm/opportunities?company_id=${companyId}`),json(`/api/v1/crm/summary?company_id=${companyId}`)]);setCampaigns(c);setLeads(l);setOpps(o);setSummary(s);if(!campaignId&&c.length)setCampaignId(String(c[0].id));}catch(e:any){setMsg(String(e.message||e));}};
  useEffect(()=>{load()},[companyId]);
  const createCampaign=async()=>{if(!code.trim()||!nameAr.trim()||!nameEn.trim()){setMsg(ar?'الكود والاسمان إلزامية':'Code and both names are required');return;}setBusy(true);setMsg('');try{const r=await json('/api/v1/crm/campaigns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,code:code.trim(),name_ar:nameAr.trim(),name_en:nameEn.trim(),channel,budget:Number(budget)||0,start_date:start,end_date:end})});setMsg(ar?`تم إنشاء الحملة ${r.code}`:`Campaign ${r.code} created`);setCode('');setNameAr('');setNameEn('');await load();}catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}};
  const createLead=async()=>{if(!leadName.trim()){setMsg(ar?'اسم العميل المحتمل إلزامي':'Lead name is required');return;}setBusy(true);setMsg('');try{const body:any={company_id:companyId,name:leadName.trim(),source:leadSource,estimated_value:Number(leadValue)||0};if(campaignId)body.campaign_id=Number(campaignId);if(leadEmail)body.email=leadEmail;if(leadPhone)body.phone=leadPhone;if(leadNotes)body.notes=leadNotes;const r=await json('/api/v1/crm/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});setMsg(ar?`تم إنشاء العميل ${r.number}`:`Lead ${r.number} created`);setLeadName('');setLeadEmail('');setLeadPhone('');setLeadNotes('');await load();}catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}};
  const chooseLead=(row:any)=>{setLeadId(String(row.id));setConvertTitle(`${row.name} opportunity`);setConvertAmount(String(row.estimated_value||0));setConvertProbability('25');setConvertDate(addDays(30));};
  const convert=async()=>{if(!leadId||convertTitle.trim().length<2){setMsg(ar?'اختر العميل وأدخل عنوان الفرصة':'Select the lead and enter the opportunity title');return;}setBusy(true);setMsg('');try{const r=await json(`/api/v1/crm/leads/${leadId}/convert?company_id=${companyId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:convertTitle.trim(),amount:Number(convertAmount)||0,probability:Number(convertProbability)||0,expected_close_date:convertDate||null})});setMsg(ar?`تم إنشاء الفرصة ${r.number}`:`Opportunity ${r.number} created`);setLeadId('');setTab('opportunities');await load();}catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}};
  const chooseOpp=(row:any)=>{setOppId(String(row.id));setStage(row.stage);setOppAmount(String(row.amount||0));setProbability(String(row.probability||0));setCloseDate(row.expected_close_date?String(row.expected_close_date).slice(0,10):addDays(30));setLossReason(row.loss_reason||'');};
  const updateOpp=async()=>{if(!oppId){setMsg(ar?'اختر فرصة':'Select an opportunity');return;}setBusy(true);setMsg('');try{const body:any={stage,amount:Number(oppAmount)||0,probability:Number(probability)||0,expected_close_date:closeDate||null};if(stage==='LOST')body.loss_reason=lossReason.trim();const r=await json(`/api/v1/crm/opportunities/${oppId}?company_id=${companyId}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});setMsg(ar?`تم تحديث ${r.number} إلى ${r.stage}`:`${r.number} updated to ${r.stage}`);await load();}catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}};
  const q=search.trim().toLowerCase();const contains=(row:any,keys:string[])=>!q||keys.some(k=>String(row[k]||'').toLowerCase().includes(q));
  const vc=campaigns.filter(r=>contains(r,['code','name_ar','name_en','channel','status']));const vl=leads.filter(r=>contains(r,['number','name','email','phone','source','status']));const vo=opps.filter(r=>contains(r,['number','title','stage','loss_reason']));
  return <>
    <div className="kpis"><Kpi title={ar?'الحملات':'Campaigns'} value={String(campaigns.length)} trend="" good icon={<TrendingUp size={22}/>} tone="blue"/><Kpi title={ar?'العملاء المحتملون':'Leads'} value={String(leads.length)} trend="" good icon={<TrendingUp size={22}/>} tone="violet"/><Kpi title={ar?'الفرص المفتوحة':'Open opportunities'} value={String(summary?.open_opportunities||0)} trend="" good icon={<ClipboardCheck size={22}/>} tone="green"/><Kpi title={ar?'قيمة المسار':'Pipeline value'} value={fmt(Number(summary?.pipeline_amount||0))} trend="" good icon={<TrendingUp size={22}/>} tone="amber"/></div>
    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>{([['campaigns',ar?'الحملات':'Campaigns'],['leads',ar?'العملاء المحتملون':'Leads'],['opportunities',ar?'الفرص':'Opportunities']] as [typeof tab,string][]).map(([k,label])=><button data-testid={`crm-tab-${k}`} key={k} style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}} onClick={()=>setTab(k)}>{label}</button>)}</div>
    {msg&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}<input data-testid="crm-search" style={field} value={search} onChange={e=>setSearch(e.target.value)} placeholder={ar?'بحث محلي في الحملة أو العميل أو الفرصة':'Local search by campaign, lead or opportunity'}/>
    {tab==='campaigns'&&<><Panel title={ar?'حملة جديدة':'New campaign'} icon={<Plus size={18}/> }><div style={grid}><label>{ar?'الكود':'Code'}<input data-testid="crm-campaign-code" style={field} value={code} onChange={e=>setCode(e.target.value)}/></label><label>{ar?'الاسم العربي':'Arabic name'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label><label>{ar?'الاسم الإنجليزي':'English name'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label><label>{ar?'القناة':'Channel'}<select style={field} value={channel} onChange={e=>setChannel(e.target.value)}>{channels.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><label>{ar?'الميزانية':'Budget'}<input type="number" style={field} value={budget} onChange={e=>setBudget(e.target.value)}/></label><label>{ar?'البدء':'Start'}<input type="date" style={field} value={start} onChange={e=>setStart(e.target.value)}/></label><label>{ar?'الانتهاء':'End'}<input type="date" style={field} value={end} onChange={e=>setEnd(e.target.value)}/></label></div><div style={{padding:12}}><button data-testid="crm-create-campaign" style={btn} disabled={busy} onClick={createCampaign}>{ar?'إنشاء الحملة':'Create campaign'}</button></div></Panel><Panel title={ar?'سجل الحملات':'Campaign register'} icon={<TrendingUp size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'القناة':'Channel',ar?'الميزانية':'Budget',ar?'الحالة':'Status']} rows={vc.map((r:any)=>[r.code,ar?r.name_ar:r.name_en,r.channel,fmt(Number(r.budget||0)),r.status])}/></Panel></>}
    {tab==='leads'&&<><Panel title={ar?'عميل محتمل جديد':'New lead'} icon={<Plus size={18}/> }><div style={grid}><label>{ar?'الحملة':'Campaign'}<select style={field} value={campaignId} onChange={e=>setCampaignId(e.target.value)}><option value="">—</option>{campaigns.map((r:any)=><option key={r.id} value={r.id}>{r.code}</option>)}</select></label><label>{ar?'الاسم':'Name'}<input data-testid="crm-lead-name" style={field} value={leadName} onChange={e=>setLeadName(e.target.value)}/></label><label>{ar?'البريد':'Email'}<input type="email" style={field} value={leadEmail} onChange={e=>setLeadEmail(e.target.value)}/></label><label>{ar?'الهاتف':'Phone'}<input style={field} value={leadPhone} onChange={e=>setLeadPhone(e.target.value)}/></label><label>{ar?'المصدر':'Source'}<select style={field} value={leadSource} onChange={e=>setLeadSource(e.target.value)}>{channels.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><label>{ar?'القيمة':'Estimated value'}<input type="number" style={field} value={leadValue} onChange={e=>setLeadValue(e.target.value)}/></label><label>{ar?'الملاحظات':'Notes'}<input style={field} value={leadNotes} onChange={e=>setLeadNotes(e.target.value)}/></label></div><div style={{padding:12}}><button data-testid="crm-create-lead" style={btn} disabled={busy} onClick={createLead}>{ar?'تسجيل العميل':'Create lead'}</button></div></Panel><Panel title={ar?'العملاء المحتملون':'Leads'} icon={<TrendingUp size={18}/> }><DataTable headers={[ar?'الرقم':'No.',ar?'الاسم':'Name',ar?'المصدر':'Source',ar?'القيمة':'Value',ar?'الحالة':'Status',ar?'إجراء':'Action']} rows={vl.map((r:any)=>[r.number,r.name,r.source,fmt(Number(r.estimated_value||0)),r.status,r.status==='NEW'?<button data-testid={`crm-select-lead-${r.id}`} key={r.id} style={smallBtn} onClick={()=>chooseLead(r)}>{ar?'تحويل':'Convert'}</button>:'—'])}/></Panel><Panel title={ar?'تحويل إلى فرصة':'Convert to opportunity'} icon={<Play size={18}/> }><div style={grid}><label>{ar?'العميل':'Lead'}<select data-testid="crm-convert-lead" style={field} value={leadId} onChange={e=>{const r=leads.find((x:any)=>String(x.id)===e.target.value);if(r)chooseLead(r);else setLeadId('')}}><option value="">—</option>{leads.filter((r:any)=>r.status==='NEW').map((r:any)=><option key={r.id} value={r.id}>{r.number} — {r.name}</option>)}</select></label><label>{ar?'عنوان الفرصة':'Title'}<input data-testid="crm-opportunity-title" style={field} value={convertTitle} onChange={e=>setConvertTitle(e.target.value)}/></label><label>{ar?'القيمة':'Amount'}<input type="number" style={field} value={convertAmount} onChange={e=>setConvertAmount(e.target.value)}/></label><label>{ar?'الاحتمال %':'Probability %'}<input type="number" min="0" max="100" style={field} value={convertProbability} onChange={e=>setConvertProbability(e.target.value)}/></label><label>{ar?'الإغلاق المتوقع':'Expected close'}<input type="date" style={field} value={convertDate} onChange={e=>setConvertDate(e.target.value)}/></label></div><div style={{padding:12}}><button data-testid="crm-convert-button" style={btn} disabled={busy} onClick={convert}>{ar?'إنشاء الفرصة':'Create opportunity'}</button></div></Panel></>}
    {tab==='opportunities'&&<><Panel title={ar?'تحديث الفرصة':'Update opportunity'} icon={<ClipboardCheck size={18}/> }><div style={grid}><label>{ar?'الفرصة':'Opportunity'}<select data-testid="crm-opportunity-select" style={field} value={oppId} onChange={e=>{const r=opps.find((x:any)=>String(x.id)===e.target.value);if(r)chooseOpp(r);else setOppId('')}}><option value="">—</option>{opps.map((r:any)=><option key={r.id} value={r.id}>{r.number} — {r.title}</option>)}</select></label><label>{ar?'المرحلة':'Stage'}<select data-testid="crm-opportunity-stage" style={field} value={stage} onChange={e=>setStage(e.target.value)}>{['QUALIFICATION','PROPOSAL','NEGOTIATION','WON','LOST'].map(v=><option key={v}>{v}</option>)}</select></label><label>{ar?'القيمة':'Amount'}<input type="number" style={field} value={oppAmount} onChange={e=>setOppAmount(e.target.value)}/></label><label>{ar?'الاحتمال %':'Probability %'}<input type="number" min="0" max="100" style={field} value={probability} onChange={e=>setProbability(e.target.value)}/></label><label>{ar?'الإغلاق المتوقع':'Expected close'}<input type="date" style={field} value={closeDate} onChange={e=>setCloseDate(e.target.value)}/></label>{stage==='LOST'&&<label>{ar?'سبب الخسارة':'Loss reason'}<input data-testid="crm-loss-reason" style={field} value={lossReason} onChange={e=>setLossReason(e.target.value)}/></label>}</div><div style={{padding:12}}><button data-testid="crm-update-opportunity" style={btn} disabled={busy} onClick={updateOpp}>{ar?'حفظ المرحلة':'Save stage'}</button></div></Panel><Panel title={ar?'مسار الفرص':'Opportunity pipeline'} icon={<TrendingUp size={18}/> }><DataTable headers={[ar?'الرقم':'No.',ar?'العنوان':'Title',ar?'المرحلة':'Stage',ar?'الاحتمال':'Probability',ar?'القيمة':'Amount',ar?'المرجح':'Weighted',ar?'إجراء':'Action']} rows={vo.map((r:any)=>[r.number,r.title,r.stage,`${r.probability}%`,fmt(Number(r.amount||0)),fmt(Number(r.weighted_amount||0)),<button data-testid={`crm-select-opportunity-${r.id}`} key={r.id} style={smallBtn} onClick={()=>chooseOpp(r)}>{ar?'اختيار':'Select'}</button>])}/></Panel></>}
  </>;
}

export function ItEmployeePage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tickets,setTickets]=useState<any[]>([]);const [assets,setAssets]=useState<any[]>([]);const [summary,setSummary]=useState<any>(null);const [tab,setTab]=useState<'tickets'|'assets'>('tickets');const [search,setSearch]=useState('');const [msg,setMsg]=useState('');const [busy,setBusy]=useState(false);
  const [subject,setSubject]=useState('');const [description,setDescription]=useState('');const [category,setCategory]=useState('GENERAL');const [priority,setPriority]=useState('MEDIUM');const [dueHours,setDueHours]=useState('24');
  const [ticketId,setTicketId]=useState('');const [assigneeId,setAssigneeId]=useState('');const [resolution,setResolution]=useState('');
  const [assetTag,setAssetTag]=useState('');const [assetType,setAssetType]=useState('LAPTOP');const [assetName,setAssetName]=useState('');const [serial,setSerial]=useState('');const [criticality,setCriticality]=useState('MEDIUM');const [purchaseDate,setPurchaseDate]=useState(iso());const [warrantyEnd,setWarrantyEnd]=useState(addDays(1095));
  const load=async()=>{try{const [t,a,s]=await Promise.all([json(`/api/v1/itsm/tickets?company_id=${companyId}`),json(`/api/v1/itsm/assets?company_id=${companyId}`),json(`/api/v1/itsm/summary?company_id=${companyId}`)]);setTickets(t);setAssets(a);setSummary(s);}catch(e:any){setMsg(String(e.message||e));}};useEffect(()=>{load()},[companyId]);
  const createAsset=async()=>{if(!assetTag.trim()||!assetName.trim()){setMsg(ar?'وسم الأصل واسمه إلزاميان':'Asset tag and name are required');return;}setBusy(true);setMsg('');try{const r=await json('/api/v1/itsm/assets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,asset_tag:assetTag.trim(),asset_type:assetType,name:assetName.trim(),serial_number:serial||null,criticality,purchase_date:purchaseDate||null,warranty_end:warrantyEnd||null})});setMsg(ar?`تم تسجيل الأصل ${r.asset_tag}`:`Asset ${r.asset_tag} registered`);setAssetTag('');setAssetName('');setSerial('');await load();}catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}};
  const createTicket=async()=>{if(!subject.trim()){setMsg(ar?'موضوع التذكرة إلزامي':'Ticket subject is required');return;}setBusy(true);setMsg('');try{const r=await json('/api/v1/itsm/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,category,subject:subject.trim(),description:description||null,priority,due_hours:Number(dueHours)||24})});setMsg(ar?`تم فتح التذكرة ${r.number}`:`Ticket ${r.number} opened`);setSubject('');setDescription('');setTicketId(String(r.id));await load();}catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}};
  const act=async(action:'assign'|'start'|'resolve')=>{if(!ticketId){setMsg(ar?'اختر تذكرة':'Select a ticket');return;}if(action==='assign'&&!Number(assigneeId)){setMsg(ar?'أدخل رقم مستخدم صحيح للإسناد':'Enter a valid assignee user ID');return;}if(action==='resolve'&&resolution.trim().length<2){setMsg(ar?'أدخل وصف الحل':'Enter the resolution');return;}setBusy(true);setMsg('');try{const init:RequestInit={method:'POST'};let url=`/api/v1/itsm/tickets/${ticketId}/${action}?company_id=${companyId}`;if(action==='assign'){init.headers={'Content-Type':'application/json'};init.body=JSON.stringify({assignee_user_id:Number(assigneeId)});}if(action==='resolve'){init.headers={'Content-Type':'application/json'};init.body=JSON.stringify({resolution:resolution.trim()});}const r=await json(url,init);setMsg(ar?`تم تنفيذ ${action} على ${r.number}`:`${action} completed for ${r.number}`);await load();}catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}};
  const q=search.trim().toLowerCase();const vt=tickets.filter((r:any)=>!q||[r.number,r.subject,r.category,r.priority,r.status,r.resolution].some(v=>String(v||'').toLowerCase().includes(q)));const va=assets.filter((r:any)=>!q||[r.asset_tag,r.asset_type,r.name,r.serial_number,r.status,r.criticality].some(v=>String(v||'').toLowerCase().includes(q)));
  return <><div className="kpis"><Kpi title={ar?'التذاكر':'Tickets'} value={String(tickets.length)} trend="" good icon={<MonitorCog size={22}/>} tone="blue"/><Kpi title={ar?'المفتوحة':'Open'} value={String(summary?.open_tickets||0)} trend="" good={!summary?.open_tickets} icon={<MonitorCog size={22}/>} tone="amber"/><Kpi title={ar?'الأصول التقنية':'IT assets'} value={String(assets.length)} trend="" good icon={<ShieldCheck size={22}/>} tone="violet"/><Kpi title={ar?'التزام SLA':'SLA compliance'} value={`${Number(summary?.sla_compliance??100).toFixed(0)}%`} trend="" good icon={<ClipboardCheck size={22}/>} tone="green"/></div><div style={{display:'flex',gap:8,margin:'14px 0'}}><button data-testid="itsm-tab-tickets" style={btn} onClick={()=>setTab('tickets')}>{ar?'التذاكر':'Tickets'}</button><button data-testid="itsm-tab-assets" style={btn} onClick={()=>setTab('assets')}>{ar?'الأصول':'Assets'}</button></div>{msg&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{msg}</div>}<input data-testid="itsm-search" style={field} value={search} onChange={e=>setSearch(e.target.value)} placeholder={ar?'بحث محلي بالرقم أو الاسم أو الحالة':'Local search by number, name or status'}/>
    {tab==='assets'&&<><Panel title={ar?'تسجيل أصل تقني':'Register IT asset'} icon={<Plus size={18}/> }><div style={grid}><label>{ar?'وسم الأصل':'Asset tag'}<input data-testid="itsm-asset-tag" style={field} value={assetTag} onChange={e=>setAssetTag(e.target.value)}/></label><label>{ar?'النوع':'Type'}<select style={field} value={assetType} onChange={e=>setAssetType(e.target.value)}>{['LAPTOP','DESKTOP','SERVER','NETWORK','MOBILE'].map(v=><option key={v}>{v}</option>)}</select></label><label>{ar?'الاسم':'Name'}<input data-testid="itsm-asset-name" style={field} value={assetName} onChange={e=>setAssetName(e.target.value)}/></label><label>{ar?'الرقم التسلسلي':'Serial number'}<input style={field} value={serial} onChange={e=>setSerial(e.target.value)}/></label><label>{ar?'الأهمية':'Criticality'}<select style={field} value={criticality} onChange={e=>setCriticality(e.target.value)}>{['LOW','MEDIUM','HIGH','CRITICAL'].map(v=><option key={v}>{v}</option>)}</select></label><label>{ar?'تاريخ الشراء':'Purchase date'}<input type="date" style={field} value={purchaseDate} onChange={e=>setPurchaseDate(e.target.value)}/></label><label>{ar?'نهاية الضمان':'Warranty end'}<input type="date" style={field} value={warrantyEnd} onChange={e=>setWarrantyEnd(e.target.value)}/></label></div><div style={{padding:12}}><button data-testid="itsm-create-asset" style={btn} disabled={busy} onClick={createAsset}>{ar?'حفظ الأصل':'Save asset'}</button></div></Panel><Panel title={ar?'سجل الأصول':'Asset register'} icon={<ShieldCheck size={18}/> }><DataTable headers={[ar?'الوسم':'Tag',ar?'الاسم':'Name',ar?'النوع':'Type',ar?'التسلسلي':'Serial',ar?'الأهمية':'Criticality',ar?'الحالة':'Status']} rows={va.map((r:any)=>[r.asset_tag,r.name,r.asset_type,r.serial_number||'—',r.criticality,r.status])}/></Panel></>}
    {tab==='tickets'&&<><Panel title={ar?'تذكرة دعم جديدة':'New support ticket'} icon={<Plus size={18}/> }><div style={grid}><label>{ar?'الموضوع':'Subject'}<input data-testid="itsm-ticket-subject" style={field} value={subject} onChange={e=>setSubject(e.target.value)}/></label><label>{ar?'الفئة':'Category'}<select style={field} value={category} onChange={e=>setCategory(e.target.value)}>{['GENERAL','ACCESS','HARDWARE','SOFTWARE','NETWORK'].map(v=><option key={v}>{v}</option>)}</select></label><label>{ar?'الأولوية':'Priority'}<select style={field} value={priority} onChange={e=>setPriority(e.target.value)}>{['LOW','MEDIUM','HIGH','CRITICAL'].map(v=><option key={v}>{v}</option>)}</select></label><label>{ar?'مهلة الإنجاز (ساعة)':'Due hours'}<input type="number" min="1" max="720" style={field} value={dueHours} onChange={e=>setDueHours(e.target.value)}/></label><label>{ar?'الوصف':'Description'}<input style={field} value={description} onChange={e=>setDescription(e.target.value)}/></label></div><div style={{padding:12}}><button data-testid="itsm-create-ticket" style={btn} disabled={busy} onClick={createTicket}>{ar?'فتح التذكرة':'Open ticket'}</button></div></Panel><Panel title={ar?'تنفيذ دورة التذكرة':'Process ticket'} icon={<Play size={18}/> }><div style={grid}><label>{ar?'التذكرة':'Ticket'}<select data-testid="itsm-ticket-select" style={field} value={ticketId} onChange={e=>setTicketId(e.target.value)}><option value="">—</option>{tickets.map((r:any)=><option key={r.id} value={r.id}>{r.number} — {r.status}</option>)}</select></label><label>{ar?'رقم مستخدم الفني':'Technician user ID'}<input data-testid="itsm-assignee-id" type="number" style={field} value={assigneeId} onChange={e=>setAssigneeId(e.target.value)}/></label><label>{ar?'وصف الحل':'Resolution'}<input data-testid="itsm-resolution" style={field} value={resolution} onChange={e=>setResolution(e.target.value)}/></label></div><div style={{padding:12,display:'flex',gap:8,flexWrap:'wrap'}}><button data-testid="itsm-assign-ticket" style={btn} disabled={busy} onClick={()=>act('assign')}>{ar?'إسناد':'Assign'}</button><button data-testid="itsm-start-ticket" style={btn} disabled={busy} onClick={()=>act('start')}>{ar?'بدء العمل':'Start'}</button><button data-testid="itsm-resolve-ticket" style={{...btn,background:'#059669'}} disabled={busy} onClick={()=>act('resolve')}>{ar?'حل التذكرة':'Resolve'}</button></div></Panel><Panel title={ar?'سجل التذاكر':'Ticket register'} icon={<MonitorCog size={18}/> }><DataTable headers={[ar?'الرقم':'No.',ar?'الموضوع':'Subject',ar?'الفئة':'Category',ar?'الأولوية':'Priority',ar?'المسند إليه':'Assignee',ar?'الحالة':'Status',ar?'الحل':'Resolution',ar?'إجراء':'Action']} rows={vt.map((r:any)=>[r.number,r.subject,r.category,r.priority,r.assignee_user_id||'—',r.status,r.resolution||'—',<button data-testid={`itsm-select-ticket-${r.id}`} key={r.id} style={smallBtn} onClick={()=>setTicketId(String(r.id))}>{ar?'اختيار':'Select'}</button>])}/></Panel></>}
  </>;
}
