import {useEffect, useMemo, useState} from 'react';
import {Boxes, Container, FileCheck2, PackageCheck, ShieldCheck, TrendingDown} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type StockRow={item_id:number;item_code:string;item_name_ar:string;warehouse_id:number;warehouse_name_ar:string;quantity:number;value:number};
type ShipmentLine={id:number;item_id:number;item_code:string;quantity:number;supplier_unit_cost:number;line_goods_value:number;allocated_landed_cost:number;landed_unit_cost:number;lot_number?:string;expiry_date?:string};
type Shipment={id:number;number:string;container_number:string;packing_list_number:string;commercial_invoice_number:string;customs_clearance_number?:string;customs_declaration_number?:string;arrival_date:string;port_of_entry?:string;carrier?:string;goods_value:number;freight_cost:number;customs_duty:number;clearance_fees:number;other_costs:number;landed_cost_total:number;status:string;journal_id?:number;lines?:ShipmentLine[]};
type Party={id:number;code:string;name_ar:string;party_type:string};
type NrvLine={item_id:number;item_code:string;item_name_ar:string;warehouse_id:number;warehouse_name_ar:string;quantity:number;carrying_cost:number;unit_cost:number;nrv_per_unit:number|null;measured_at:string;writedown_required:number};

const ITEM_TYPES:[string,string][]=[['RAW_MATERIAL','مواد خام'],['WORK_IN_PROGRESS','تحت التصنيع'],['FINISHED_GOOD','منتج نهائي'],['PACKAGING','تعبئة وتغليف'],['CLEANING_MATERIAL','مواد نظافة'],['OPERATING_SUPPLY','مواد تشغيلية'],['SPARE_PART','قطع غيار'],['SERVICE','خدمة']];
const RAW_SUBTYPES:[string,string][]=[['CORE_MATERIAL','أساسية (لحوم/دواجن)'],['SPICE','بهارات'],['CHEMICAL_BINDER','مواد ربط كيميائية'],['AUXILIARY_MATERIAL','مواد مساعدة (زيوت/شحوم)']];

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;

export function InventoryTraceabilityPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date().toISOString().slice(0,10);
  const [tab,setTab]=useState<'shipments'|'classify'|'nrv'>('shipments');
  const [stock,setStock]=useState<StockRow[]>([]);
  const [suppliers,setSuppliers]=useState<Party[]>([]);
  const [shipments,setShipments]=useState<Shipment[]>([]);
  const [nrv,setNrv]=useState<{total_writedown_required:number;lines:NrvLine[]}|null>(null);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);

  // shipment form
  const [supplierId,setSupplierId]=useState('');
  const [warehouseId,setWarehouseId]=useState('');
  const [container,setContainer]=useState('');
  const [pl,setPl]=useState('');
  const [ci,setCi]=useState('');
  const [clearance,setClearance]=useState('');
  const [declaration,setDeclaration]=useState('');
  const [port,setPort]=useState('');
  const [carrier,setCarrier]=useState('');
  const [arrival,setArrival]=useState(today);
  const [freight,setFreight]=useState('0');
  const [duty,setDuty]=useState('0');
  const [fees,setFees]=useState('0');
  const [lineItemId,setLineItemId]=useState('');
  const [lineQty,setLineQty]=useState('');
  const [lineCost,setLineCost]=useState('');
  const [lineLot,setLineLot]=useState('');
  const [lineExpiry,setLineExpiry]=useState('');
  const [lines,setLines]=useState<{item_id:number;item_code:string;quantity:number;supplier_unit_cost:number;lot_number?:string;expiry_date?:string}[]>([]);

  // classify form
  const [clsItem,setClsItem]=useState('');
  const [clsType,setClsType]=useState('RAW_MATERIAL');
  const [clsSubtype,setClsSubtype]=useState('CORE_MATERIAL');
  const [clsValuation,setClsValuation]=useState('WEIGHTED_AVERAGE');
  const [clsIssue,setClsIssue]=useState('FEFO');

  // nrv form
  const [nrvItem,setNrvItem]=useState('');
  const [nrvWarehouse,setNrvWarehouse]=useState('');
  const [nrvValue,setNrvValue]=useState('');

  const warehouses=useMemo(()=>{
    const seen=new Map<number,string>();
    stock.forEach(r=>{if(!seen.has(r.warehouse_id))seen.set(r.warehouse_id,r.warehouse_name_ar);});
    return [...seen.entries()];
  },[stock]);
  const items=useMemo(()=>{
    const seen=new Map<number,string>();
    stock.forEach(r=>{if(!seen.has(r.item_id))seen.set(r.item_id,`${r.item_code} — ${r.item_name_ar}`);});
    return [...seen.entries()];
  },[stock]);

  const load=async()=>{
    try{
      const [s,p,sh]=await Promise.all([
        json(`/api/v1/inventory/stock-summary?company_id=${companyId}`),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`),
        json(`/api/v1/inventory/inbound-shipments?company_id=${companyId}`),
      ]);
      setStock(s||[]);
      setSuppliers((p||[]).filter((x:Party)=>x.party_type==='SUPPLIER'));
      setShipments(sh||[]);
      if(!warehouseId&&s?.length)setWarehouseId(String(s[0].warehouse_id));
      if(!lineItemId&&s?.length)setLineItemId(String(s[0].item_id));
      if(!clsItem&&s?.length)setClsItem(String(s[0].item_id));
      if(!nrvItem&&s?.length){setNrvItem(String(s[0].item_id));setNrvWarehouse(String(s[0].warehouse_id));}
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{if(suppliers.length&&!supplierId)setSupplierId(String(suppliers[0].id));},[suppliers]);

  const loadNrv=async()=>{
    try{const r=await json(`/api/v1/inventory/nrv-assessment?company_id=${companyId}`);setNrv(r);}
    catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{if(tab==='nrv')loadNrv();},[tab,companyId]);

  const addLine=()=>{
    if(!lineItemId||!lineQty||!lineCost){setMessage(ar?'أكمل بيانات السطر':'Complete line fields');return;}
    const code=items.find(([id])=>String(id)===lineItemId)?.[1]||lineItemId;
    setLines([...lines,{item_id:Number(lineItemId),item_code:String(code),quantity:Number(lineQty),supplier_unit_cost:Number(lineCost),lot_number:lineLot||undefined,expiry_date:lineExpiry||undefined}]);
    setLineQty('');setLineCost('');setLineLot('');setLineExpiry('');
  };

  const createShipment=async()=>{
    if(!container||!pl||!ci){setMessage(ar?'رقم الكونتينر وPL وفاتورة المورد إلزامية':'Container, PL and commercial invoice are required');return;}
    if(!lines.length){setMessage(ar?'أضف سطرًا واحدًا على الأقل':'Add at least one line');return;}
    setBusy(true);setMessage('');
    try{
      const body={company_id:companyId,warehouse_id:Number(warehouseId),supplier_id:Number(supplierId),arrival_date:arrival,
        container_number:container,packing_list_number:pl,commercial_invoice_number:ci,customs_clearance_number:clearance||undefined,
        customs_declaration_number:declaration||undefined,port_of_entry:port||undefined,carrier:carrier||undefined,
        freight_cost:Number(freight),customs_duty:Number(duty),clearance_fees:Number(fees),other_costs:0,allocation_method:'VALUE',
        lines:lines.map(l=>({item_id:l.item_id,quantity:l.quantity,supplier_unit_cost:l.supplier_unit_cost,lot_number:l.lot_number,expiry_date:l.expiry_date}))};
      const created=await json('/api/v1/inventory/inbound-shipments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(ar?`تم إنشاء الشحنة ${created.number} — التكلفة المحمّلة ${fmt(Number(created.landed_cost_total))}`:`Shipment ${created.number} created`);
      setContainer('');setPl('');setCi('');setClearance('');setDeclaration('');setLines([]);
      await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const receiveShipment=async(id:number)=>{
    setBusy(true);setMessage('');
    try{const r=await json(`/api/v1/inventory/inbound-shipments/${id}/receive?company_id=${companyId}`,{method:'POST'});
      setMessage(ar?`تم الاستلام — قيد ${r.journal_number}`:`Received — journal ${r.journal_number}`);await load();}
    catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const classify=async()=>{
    setBusy(true);setMessage('');
    try{
      const body:any={company_id:companyId,item_id:Number(clsItem),item_type:clsType,valuation_method:clsValuation,physical_issue_method:clsIssue};
      if(clsType==='RAW_MATERIAL')body.item_subtype=clsSubtype;
      const r=await json('/api/v1/inventory/items/classify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(ar?`تم تصنيف ${r.code}`:`Classified ${r.code}`);
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const writedown=async()=>{
    setBusy(true);setMessage('');
    try{
      const body:any={company_id:companyId,item_id:Number(nrvItem),warehouse_id:Number(nrvWarehouse)};
      if(nrvValue)body.nrv_per_unit=Number(nrvValue);
      const r=await json('/api/v1/inventory/nrv-writedown',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(r.journal_number?(ar?`تخفيض ${fmt(Number(r.writedown))} — قيد ${r.journal_number}`:`Write-down ${fmt(Number(r.writedown))} — ${r.journal_number}`):(ar?'NRV ليست أقل من التكلفة — لا تخفيض':'NRV not below cost'));
      await loadNrv();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const totalLanded=lines.reduce((s,l)=>s+l.quantity*l.supplier_unit_cost,0)+Number(freight||0)+Number(duty||0)+Number(fees||0);
  const receivedCount=shipments.filter(s=>s.status==='RECEIVED').length;

  return <>
    <div className="kpis">
      <Kpi title={ar?'الشحنات الواردة':'Inbound shipments'} value={String(shipments.length)} trend="" good icon={<Container size={22}/>} tone="blue"/>
      <Kpi title={ar?'مستلمة':'Received'} value={String(receivedCount)} trend="" good icon={<PackageCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'أصناف بها مخزون':'Items in stock'} value={String(items.length)} trend="" good icon={<Boxes size={22}/>} tone="violet"/>
      <Kpi title={ar?'تخفيض NRV مطلوب':'NRV write-down due'} value={nrv?fmt(Number(nrv.total_writedown_required)):'—'} trend="" good={false} icon={<TrendingDown size={22}/>} tone="amber"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0'}}>
      {([['shipments',ar?'الشحنات الواردة':'Shipments'],['classify',ar?'تصنيف الأصناف':'Classify'],['nrv',ar?'تقييم NRV':'NRV assessment']] as [typeof tab,string][]).map(([k,label])=>
        <button key={k} onClick={()=>setTab(k)} style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{label}</button>)}
    </div>

    {message&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {tab==='shipments'&&<>
      <Panel title={ar?'شحنة واردة جديدة':'New inbound shipment'} icon={<Container size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'رقم الكونتينر *':'Container No. *'}<input style={field} value={container} onChange={e=>setContainer(e.target.value)} placeholder="MSKU-1234567"/></label>
          <label>{ar?'رقم قائمة التعبئة (PL) *':'Packing List No. *'}<input style={field} value={pl} onChange={e=>setPl(e.target.value)}/></label>
          <label>{ar?'رقم فاتورة المورد *':'Commercial Invoice No. *'}<input style={field} value={ci} onChange={e=>setCi(e.target.value)}/></label>
          <label>{ar?'رقم فاتورة التخليص':'Customs Clearance No.'}<input style={field} value={clearance} onChange={e=>setClearance(e.target.value)}/></label>
          <label>{ar?'رقم البيان الجمركي':'Customs Declaration No.'}<input style={field} value={declaration} onChange={e=>setDeclaration(e.target.value)}/></label>
          <label>{ar?'المورد':'Supplier'}<select style={field} value={supplierId} onChange={e=>setSupplierId(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{s.name_ar}</option>)}</select></label>
          <label>{ar?'المستودع':'Warehouse'}<select style={field} value={warehouseId} onChange={e=>setWarehouseId(e.target.value)}>{warehouses.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
          <label>{ar?'تاريخ الوصول':'Arrival date'}<input type="date" style={field} value={arrival} onChange={e=>setArrival(e.target.value)}/></label>
          <label>{ar?'الميناء':'Port'}<input style={field} value={port} onChange={e=>setPort(e.target.value)}/></label>
          <label>{ar?'الناقل':'Carrier'}<input style={field} value={carrier} onChange={e=>setCarrier(e.target.value)}/></label>
          <label>{ar?'الشحن':'Freight'}<input type="number" style={field} value={freight} onChange={e=>setFreight(e.target.value)}/></label>
          <label>{ar?'الجمارك':'Customs duty'}<input type="number" style={field} value={duty} onChange={e=>setDuty(e.target.value)}/></label>
          <label>{ar?'رسوم التخليص':'Clearance fees'}<input type="number" style={field} value={fees} onChange={e=>setFees(e.target.value)}/></label>
        </div>
        <div style={{padding:12,borderTop:'1px solid var(--border)'}}>
          <strong>{ar?'أسطر الشحنة':'Shipment lines'}</strong>
          <div style={{display:'grid',gridTemplateColumns:'2fr 1fr 1fr 1fr 1fr auto',gap:8,marginTop:8,alignItems:'end'}}>
            <label>{ar?'الصنف':'Item'}<select style={field} value={lineItemId} onChange={e=>setLineItemId(e.target.value)}>{items.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
            <label>{ar?'الكمية':'Qty'}<input type="number" style={field} value={lineQty} onChange={e=>setLineQty(e.target.value)}/></label>
            <label>{ar?'سعر المورد':'Supplier cost'}<input type="number" style={field} value={lineCost} onChange={e=>setLineCost(e.target.value)}/></label>
            <label>{ar?'الدفعة':'Lot'}<input style={field} value={lineLot} onChange={e=>setLineLot(e.target.value)}/></label>
            <label>{ar?'الصلاحية':'Expiry'}<input type="date" style={field} value={lineExpiry} onChange={e=>setLineExpiry(e.target.value)}/></label>
            <button style={btn} onClick={addLine}>{ar?'إضافة':'Add'}</button>
          </div>
          {lines.length>0&&<div style={{marginTop:10}}><DataTable headers={[ar?'الصنف':'Item',ar?'الكمية':'Qty',ar?'سعر المورد':'Cost',ar?'الدفعة':'Lot',ar?'الصلاحية':'Expiry']} rows={lines.map(l=>[l.item_code,String(l.quantity),fmt(l.supplier_unit_cost),l.lot_number||'—',l.expiry_date||'—'])}/></div>}
          <div style={{marginTop:10,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
            <span>{ar?'إجمالي التكلفة المحمّلة المتوقع:':'Expected landed total:'} <strong>{fmt(totalLanded)}</strong></span>
            <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createShipment}>{ar?'إنشاء الشحنة':'Create shipment'}</button>
          </div>
        </div>
      </Panel>

      <Panel title={ar?'الشحنات المسجّلة':'Recorded shipments'} icon={<FileCheck2 size={18}/>}>
        <DataTable
          headers={[ar?'الرقم':'No.',ar?'الكونتينر':'Container',ar?'فاتورة المورد':'Invoice',ar?'التخليص':'Clearance',ar?'التكلفة المحمّلة':'Landed',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={shipments.map(s=>[s.number,s.container_number,s.commercial_invoice_number,s.customs_clearance_number||'—',fmt(Number(s.landed_cost_total)),
            s.status==='RECEIVED'?(ar?'مستلمة':'Received'):(ar?'مسعّرة':'Costed'),
            s.status==='COSTED'?<button key={s.id} style={{...btn,padding:'5px 12px'}} disabled={busy} onClick={()=>receiveShipment(s.id)}>{ar?'استلام':'Receive'}</button>:'✓'])}/>
      </Panel>
    </>}

    {tab==='classify'&&<Panel title={ar?'تصنيف صنف':'Classify item'} icon={<Boxes size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
        <label>{ar?'الصنف':'Item'}<select style={field} value={clsItem} onChange={e=>setClsItem(e.target.value)}>{items.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
        <label>{ar?'النوع':'Type'}<select style={field} value={clsType} onChange={e=>setClsType(e.target.value)}>{ITEM_TYPES.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
        {clsType==='RAW_MATERIAL'&&<label>{ar?'الفئة الفرعية':'Subtype'}<select style={field} value={clsSubtype} onChange={e=>setClsSubtype(e.target.value)}>{RAW_SUBTYPES.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>}
        <label>{ar?'طريقة التقييم':'Valuation'}<select style={field} value={clsValuation} onChange={e=>setClsValuation(e.target.value)}><option value="WEIGHTED_AVERAGE">{ar?'متوسط مرجح':'Weighted average'}</option><option value="FIFO">FIFO</option></select></label>
        <label>{ar?'طريقة الصرف المادي':'Physical issue'}<select style={field} value={clsIssue} onChange={e=>setClsIssue(e.target.value)}><option value="FEFO">FEFO ({ar?'الأقرب انتهاءً':'earliest expiry'})</option><option value="FIFO">FIFO</option></select></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={classify}>{ar?'حفظ التصنيف':'Save classification'}</button>
        <p style={{marginTop:8,fontSize:13,color:'var(--muted)'}}>{ar?'ملاحظة: LIFO ممنوع حسب معيار IAS 2. تغيير طريقة التقييم يُسجّل في سجل التدقيق.':'Note: LIFO is prohibited by IAS 2. Valuation changes are audit-logged.'}</p>
      </div>
    </Panel>}

    {tab==='nrv'&&<>
      <Panel title={ar?'قيد تخفيض NRV':'Record NRV write-down'} icon={<TrendingDown size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'الصنف':'Item'}<select style={field} value={nrvItem} onChange={e=>setNrvItem(e.target.value)}>{items.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
          <label>{ar?'المستودع':'Warehouse'}<select style={field} value={nrvWarehouse} onChange={e=>setNrvWarehouse(e.target.value)}>{warehouses.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
          <label>{ar?'NRV لكل وحدة (اتركها فارغة لاستخدام المحفوظة)':'NRV per unit (blank = stored)'}<input type="number" style={field} value={nrvValue} onChange={e=>setNrvValue(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={writedown}>{ar?'ترحيل التخفيض':'Post write-down'}</button></div>
      </Panel>
      <Panel title={ar?'تقرير تقييم NRV (للمراجع الخارجي)':'NRV assessment (external auditor)'} icon={<ShieldCheck size={18}/>}>
        <DataTable
          headers={[ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Qty',ar?'التكلفة/وحدة':'Cost/u',ar?'NRV/وحدة':'NRV/u',ar?'القياس':'Measured',ar?'تخفيض مطلوب':'Write-down']}
          rows={(nrv?.lines||[]).map(l=>[l.item_code,l.warehouse_name_ar,String(l.quantity),fmt(Number(l.unit_cost)),l.nrv_per_unit!=null?fmt(Number(l.nrv_per_unit)):'—',l.measured_at==='NRV'?(ar?'بـNRV':'at NRV'):(ar?'بالتكلفة':'at cost'),fmt(Number(l.writedown_required))])}/>
      </Panel>
    </>}
  </>;
}
