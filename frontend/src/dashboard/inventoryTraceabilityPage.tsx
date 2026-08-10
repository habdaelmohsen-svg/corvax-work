import {useEffect, useMemo, useState} from 'react';
import {AlertTriangle, Boxes, Container, FileCheck2, PackageCheck, ScanLine} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type StockRow={item_id:number};
type Item={id:number;code:string;name_ar:string;name_en:string};
type Warehouse={id:number;code:string;name_ar:string;name_en:string};
type ShipmentLine={id:number;item_id:number;item_code:string;quantity:number;supplier_unit_cost:number;line_goods_value:number;allocated_landed_cost:number;landed_unit_cost:number;lot_number?:string;expiry_date?:string};
type Shipment={id:number;number:string;container_number:string;packing_list_number:string;commercial_invoice_number:string;customs_clearance_number?:string;customs_declaration_number?:string;arrival_date:string;port_of_entry?:string;carrier?:string;goods_value:number;freight_cost:number;customs_duty:number;clearance_fees:number;other_costs:number;landed_cost_total:number;status:string;journal_id?:number;lines?:ShipmentLine[]};
type Party={id:number;code:string;name_ar:string;name_en:string;party_type:string};
type MobilePOLine={id:number;item_id:number;item_code:string;item_name_ar:string;item_name_en:string;remaining_quantity:number;barcode_expected:string};
type MobilePO={id:number;number:string;status:string;supplier:string;warehouse:string;lines:MobilePOLine[]};
type AlertRow={type:string;severity:string;reference:string;message_ar:string;message_en:string;days?:number};
type InspectionDraft={barcode_value:string;accepted_quantity:string;rejected_quantity:string;rejection_reason:string;lot_number:string;production_date:string;expiry_date:string;storage_location:string;evidence:any[]};

async function json(url:string,init?:RequestInit){
  const response=await apiFetch(url,init);const payload=await response.json().catch(()=>({}));
  if(!response.ok){
    const detail=payload.detail;
    const message=typeof detail==='string'?detail:(detail&&(detail.message_ar||detail.message_en))?(detail.message_ar||detail.message_en):JSON.stringify(detail||payload);
    throw new Error(message);
  }
  return payload;
}

const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;

export function InventoryTraceabilityPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date().toISOString().slice(0,10);
  const [stock,setStock]=useState<StockRow[]>([]);
  const [items,setItems]=useState<Item[]>([]);
  const [warehouses,setWarehouses]=useState<Warehouse[]>([]);
  const [suppliers,setSuppliers]=useState<Party[]>([]);
  const [shipments,setShipments]=useState<Shipment[]>([]);
  const [orders,setOrders]=useState<any[]>([]);
  const [mobilePO,setMobilePO]=useState<MobilePO|null>(null);
  const [mobilePoId,setMobilePoId]=useState('');
  const [receiptDate,setReceiptDate]=useState(today);
  const [inspections,setInspections]=useState<Record<number,InspectionDraft>>({});
  const [alerts,setAlerts]=useState<AlertRow[]>([]);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);

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

  const itemOptions=useMemo(()=>items.map(row=>[row.id,`${row.code} — ${ar?row.name_ar:row.name_en}`] as const),[ar,items]);
  const stockedItemCount=useMemo(()=>new Set(stock.map(row=>row.item_id)).size,[stock]);

  const load=async()=>{
    try{
      const [stockRows,partyRows,shipmentRows,itemRows,warehouseRows,orderRows,alertData]=await Promise.all([
        json(`/api/v1/inventory/stock-summary?company_id=${companyId}`),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`),
        json(`/api/v1/inventory/inbound-shipments?company_id=${companyId}`),
        json(`/api/v1/inventory/items?company_id=${companyId}`),
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`),
        json(`/api/v1/inventory/purchase-orders?company_id=${companyId}`),
        json(`/api/v1/inventory/alerts?company_id=${companyId}`),
      ]);
      const nextItems=Array.isArray(itemRows)?itemRows:[];
      const nextWarehouses=Array.isArray(warehouseRows)?warehouseRows:[];
      const nextSuppliers=(Array.isArray(partyRows)?partyRows:[]).filter((row:Party)=>['SUPPLIER','BOTH'].includes(row.party_type));
      setStock(Array.isArray(stockRows)?stockRows:[]);
      setSuppliers(nextSuppliers);setShipments(Array.isArray(shipmentRows)?shipmentRows:[]);
      setItems(nextItems);setWarehouses(nextWarehouses);
      setOrders((Array.isArray(orderRows)?orderRows:[]).filter((row:any)=>['APPROVED','PARTIALLY_RECEIVED'].includes(row.status)));
      setAlerts(Array.isArray(alertData?.alerts)?alertData.alerts:[]);
      if(!warehouseId&&nextWarehouses.length)setWarehouseId(String(nextWarehouses[0].id));
      if(!lineItemId&&nextItems.length)setLineItemId(String(nextItems[0].id));
      if(!supplierId&&nextSuppliers.length)setSupplierId(String(nextSuppliers[0].id));
    }catch(cause:any){setMessage(String(cause.message||cause));}
  };
  useEffect(()=>{void load();},[companyId]);

  const blankDraft=(line:MobilePOLine):InspectionDraft=>({barcode_value:'',accepted_quantity:String(line.remaining_quantity),rejected_quantity:'0',rejection_reason:'',lot_number:'',production_date:'',expiry_date:'',storage_location:'',evidence:[]});
  const chooseMobilePO=async(value:string)=>{
    setMobilePoId(value);setMobilePO(null);setInspections({});
    if(!value)return;
    try{
      const po=await json(`/api/v1/inventory/mobile-receipts/purchase-orders/${value}?company_id=${companyId}`) as MobilePO;
      setMobilePO(po);setInspections(Object.fromEntries(po.lines.filter(line=>Number(line.remaining_quantity)>0).map(line=>[line.id,blankDraft(line)])));
    }catch(cause:any){setMessage(String(cause.message||cause));}
  };
  const setInspection=(id:number,key:keyof InspectionDraft,value:any)=>setInspections(current=>({...current,[id]:{...current[id],[key]:value}}));
  const captureEvidence=async(id:number,file?:File)=>{
    if(!file)return;
    if(file.size>10_485_760){setMessage(ar?'حجم الدليل يتجاوز 10 MB':'Evidence exceeds 10 MB');return;}
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))).map(b=>b.toString(16).padStart(2,'0')).join('');
    const evidence={file_name:file.name,content_type:file.type,size_bytes:file.size,sha256:hash,object_key:`mobile-evidence/${companyId}/${Date.now()}-${file.name}`};
    setInspection(id,'evidence',[...(inspections[id]?.evidence||[]),evidence]);
  };
  const postMobileReceipt=async()=>{
    if(!mobilePO){setMessage(ar?'اختر أمر شراء معتمدًا':'Select an approved purchase order');return;}
    const selected=mobilePO.lines.filter(line=>Number(inspections[line.id]?.accepted_quantity||0)+Number(inspections[line.id]?.rejected_quantity||0)>0);
    if(!selected.length){setMessage(ar?'أدخل نتيجة فحص سطر واحد على الأقل':'Enter at least one inspection result');return;}
    setBusy(true);setMessage('');
    try{
      const result=await json('/api/v1/inventory/mobile-receipts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        company_id:companyId,purchase_order_id:mobilePO.id,receipt_date:receiptDate,
        lines:selected.map(line=>{const d=inspections[line.id];return {purchase_order_line_id:line.id,barcode_value:d.barcode_value,
          accepted_quantity:Number(d.accepted_quantity||0),rejected_quantity:Number(d.rejected_quantity||0),rejection_reason:d.rejection_reason||null,
          lot_number:d.lot_number,production_date:d.production_date||null,expiry_date:d.expiry_date||null,storage_location:d.storage_location,evidence:d.evidence};}),
      })});
      setMessage(ar?`تم إنشاء ${result.number} بعد الفحص — المرفوض ${result.rejected_quantity}`:`${result.number} posted after inspection`);
      setMobilePO(null);setMobilePoId('');setInspections({});await load();
    }catch(cause:any){setMessage(String(cause.message||cause));}finally{setBusy(false);}
  };

  const addLine=()=>{
    if(!lineItemId||!lineQty||!lineCost){setMessage(ar?'أكمل بيانات سطر الشحنة':'Complete the shipment line');return;}
    const itemLabel=itemOptions.find(([id])=>String(id)===lineItemId)?.[1]||lineItemId;
    setLines(current=>[...current,{item_id:Number(lineItemId),item_code:itemLabel,quantity:Number(lineQty),supplier_unit_cost:Number(lineCost),lot_number:lineLot||undefined,expiry_date:lineExpiry||undefined}]);
    setLineQty('');setLineCost('');setLineLot('');setLineExpiry('');
  };

  const createShipment=async()=>{
    if(!container||!pl||!ci||!supplierId||!warehouseId){setMessage(ar?'رقم الكونتينر وقائمة التعبئة وفاتورة المورد والمورد والمستودع إلزامية':'Container, packing list, commercial invoice, supplier, and warehouse are required');return;}
    if(!lines.length){setMessage(ar?'أضف سطرًا واحدًا على الأقل':'Add at least one line');return;}
    setBusy(true);setMessage('');
    try{
      const body={company_id:companyId,warehouse_id:Number(warehouseId),supplier_id:Number(supplierId),arrival_date:arrival,
        container_number:container,packing_list_number:pl,commercial_invoice_number:ci,customs_clearance_number:clearance||undefined,
        customs_declaration_number:declaration||undefined,port_of_entry:port||undefined,carrier:carrier||undefined,
        freight_cost:Number(freight),customs_duty:Number(duty),clearance_fees:Number(fees),other_costs:0,allocation_method:'VALUE',
        lines:lines.map(line=>({item_id:line.item_id,quantity:line.quantity,supplier_unit_cost:line.supplier_unit_cost,lot_number:line.lot_number,expiry_date:line.expiry_date}))};
      const created=await json('/api/v1/inventory/inbound-shipments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(ar?`تم إنشاء الشحنة ${created.number} — التكلفة المحمّلة ${fmt(Number(created.landed_cost_total))}`:`Shipment ${created.number} created`);
      setContainer('');setPl('');setCi('');setClearance('');setDeclaration('');setLines([]);await load();
    }catch(cause:any){setMessage(String(cause.message||cause));}
    finally{setBusy(false);}
  };

  const receiveShipment=async(id:number)=>{
    setBusy(true);setMessage('');
    try{
      const result=await json(`/api/v1/inventory/inbound-shipments/${id}/receive?company_id=${companyId}`,{method:'POST'});
      setMessage(ar?`تم الاستلام — القيد ${result.journal_number}`:`Received — journal ${result.journal_number}`);await load();
    }catch(cause:any){setMessage(String(cause.message||cause));}
    finally{setBusy(false);}
  };

  const totalLanded=lines.reduce((sum,line)=>sum+line.quantity*line.supplier_unit_cost,0)+Number(freight||0)+Number(duty||0)+Number(fees||0);
  const receivedCount=shipments.filter(row=>row.status==='RECEIVED').length;

  return <>
    <div className="kpis">
      <Kpi title={ar?'الشحنات الواردة':'Inbound shipments'} value={String(shipments.length)} trend="" good icon={<Container size={22}/>} tone="blue"/>
      <Kpi title={ar?'الشحنات المستلمة':'Received shipments'} value={String(receivedCount)} trend="" good icon={<PackageCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'أصناف بها مخزون':'Items in stock'} value={String(stockedItemCount)} trend="" good icon={<Boxes size={22}/>} tone="violet"/>
      <Kpi title={ar?'تنبيهات تشغيلية':'Operational alerts'} value={String(alerts.length)} trend="" good={alerts.length===0} icon={<AlertTriangle size={22}/>} tone="amber"/>
    </div>

    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    <Panel title={ar?'الاستلام المحمول بالباركود / QR':'Mobile barcode / QR receiving'} icon={<ScanLine size={18}/> }>
      <div style={{padding:12,display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:10}}>
        <label>{ar?'أمر شراء معتمد':'Approved purchase order'}<select style={field} value={mobilePoId} onChange={event=>void chooseMobilePO(event.target.value)}><option value="">{ar?'اختر أمر الشراء...':'Select PO...'}</option>{orders.map((row:any)=><option key={row.id} value={row.id}>{row.number} — {row.supplier}</option>)}</select></label>
        <label>{ar?'تاريخ الاستلام والترحيل':'Receipt / posting date'}<input type="date" style={field} value={receiptDate} onChange={event=>setReceiptDate(event.target.value)}/></label>
      </div>
      {mobilePO&&<div style={{padding:'0 12px 12px'}}>
        <div style={{padding:10,borderRadius:9,background:'var(--panel-2,#f1f5f9)',marginBottom:10}}><strong>{mobilePO.number}</strong> · {mobilePO.supplier} · {mobilePO.warehouse}</div>
        {mobilePO.lines.filter(line=>Number(line.remaining_quantity)>0).map(line=>{const d=inspections[line.id]||blankDraft(line);return <div key={line.id} style={{border:'1px solid var(--border)',borderRadius:12,padding:12,marginBottom:10}}>
          <div style={{display:'flex',justifyContent:'space-between',gap:8,flexWrap:'wrap'}}><strong>{line.item_code} — {ar?line.item_name_ar:line.item_name_en}</strong><span>{ar?'المتبقي':'Remaining'}: {line.remaining_quantity}</span></div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))',gap:9,marginTop:8}}>
            <label>{ar?'امسح الباركود / QR *':'Scan barcode / QR *'}<input autoComplete="off" inputMode="text" style={field} value={d.barcode_value} onChange={e=>setInspection(line.id,'barcode_value',e.target.value)} placeholder={line.barcode_expected}/></label>
            <label>{ar?'مقبول *':'Accepted *'}<input type="number" min="0" step="0.0001" style={field} value={d.accepted_quantity} onChange={e=>setInspection(line.id,'accepted_quantity',e.target.value)}/></label>
            <label>{ar?'مرفوض':'Rejected'}<input type="number" min="0" step="0.0001" style={field} value={d.rejected_quantity} onChange={e=>setInspection(line.id,'rejected_quantity',e.target.value)}/></label>
            <label>{ar?'رقم التشغيلة *':'Lot / batch *'}<input style={field} value={d.lot_number} onChange={e=>setInspection(line.id,'lot_number',e.target.value)}/></label>
            <label>{ar?'تاريخ الإنتاج':'Production date'}<input type="date" style={field} value={d.production_date} onChange={e=>setInspection(line.id,'production_date',e.target.value)}/></label>
            <label>{ar?'تاريخ الانتهاء':'Expiry date'}<input type="date" style={field} value={d.expiry_date} onChange={e=>setInspection(line.id,'expiry_date',e.target.value)}/></label>
            <label>{ar?'موقع التخزين *':'Storage bin *'}<input style={field} value={d.storage_location} onChange={e=>setInspection(line.id,'storage_location',e.target.value)} placeholder="A-03-R02-B04"/></label>
            <label>{ar?'سبب الرفض':'Rejection reason'}<input style={field} value={d.rejection_reason} onChange={e=>setInspection(line.id,'rejection_reason',e.target.value)} disabled={Number(d.rejected_quantity||0)<=0}/></label>
            <label>{ar?'صورة / محضر فحص':'Photo / inspection evidence'}<input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" capture="environment" style={field} onChange={e=>void captureEvidence(line.id,e.target.files?.[0])}/><small>{d.evidence.length} {ar?'دليل مسجل بالـ SHA-256':'evidence record(s), SHA-256 protected'}</small></label>
          </div>
        </div>})}
        <button style={{...btn,width:'100%',minHeight:46,opacity:busy?0.6:1}} disabled={busy} onClick={postMobileReceipt}>{ar?'اعتماد الفحص وإنشاء GRN':'Post inspection and create GRN'}</button>
      </div>}
    </Panel>

    <Panel title={ar?'تنبيهات المخزون والتوريد':'Inventory & supply alerts'} icon={<AlertTriangle size={18}/> }>
      <DataTable headers={[ar?'الأولوية':'Severity',ar?'النوع':'Type',ar?'المرجع':'Reference',ar?'التنبيه':'Alert']}
        rows={alerts.map((row,index)=>[<span key={index} style={{fontWeight:700,color:row.severity==='CRITICAL'?'#b91c1c':row.severity==='HIGH'?'#c2410c':'#a16207'}}>{row.severity}</span>,row.type,row.reference,ar?row.message_ar:row.message_en])}/>
    </Panel>

    <Panel title={ar?'شحنة واردة جديدة':'New inbound shipment'} icon={<Container size={18}/> }>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
        <label>{ar?'رقم الكونتينر *':'Container No. *'}<input style={field} value={container} onChange={event=>setContainer(event.target.value)} placeholder="MSKU-1234567"/></label>
        <label>{ar?'رقم قائمة التعبئة (PL) *':'Packing List No. *'}<input style={field} value={pl} onChange={event=>setPl(event.target.value)}/></label>
        <label>{ar?'رقم فاتورة المورد *':'Commercial Invoice No. *'}<input style={field} value={ci} onChange={event=>setCi(event.target.value)}/></label>
        <label>{ar?'رقم فاتورة التخليص':'Customs Clearance No.'}<input style={field} value={clearance} onChange={event=>setClearance(event.target.value)}/></label>
        <label>{ar?'رقم البيان الجمركي':'Customs Declaration No.'}<input style={field} value={declaration} onChange={event=>setDeclaration(event.target.value)}/></label>
        <label>{ar?'المورد':'Supplier'}<select style={field} value={supplierId} onChange={event=>setSupplierId(event.target.value)}>{suppliers.map(row=><option key={row.id} value={row.id}>{row.code} — {ar?row.name_ar:row.name_en}</option>)}</select></label>
        <label>{ar?'المستودع':'Warehouse'}<select style={field} value={warehouseId} onChange={event=>setWarehouseId(event.target.value)}>{warehouses.map(row=><option key={row.id} value={row.id}>{row.code} — {ar?row.name_ar:row.name_en}</option>)}</select></label>
        <label>{ar?'تاريخ الوصول':'Arrival date'}<input type="date" style={field} value={arrival} onChange={event=>setArrival(event.target.value)}/></label>
        <label>{ar?'الميناء':'Port'}<input style={field} value={port} onChange={event=>setPort(event.target.value)}/></label>
        <label>{ar?'الناقل':'Carrier'}<input style={field} value={carrier} onChange={event=>setCarrier(event.target.value)}/></label>
        <label>{ar?'تكلفة الشحن':'Freight'}<input type="number" min="0" style={field} value={freight} onChange={event=>setFreight(event.target.value)}/></label>
        <label>{ar?'الرسوم الجمركية':'Customs duty'}<input type="number" min="0" style={field} value={duty} onChange={event=>setDuty(event.target.value)}/></label>
        <label>{ar?'رسوم التخليص':'Clearance fees'}<input type="number" min="0" style={field} value={fees} onChange={event=>setFees(event.target.value)}/></label>
      </div>
      <div style={{padding:12,borderTop:'1px solid var(--border)'}}>
        <strong>{ar?'أسطر الشحنة':'Shipment lines'}</strong>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(145px,1fr))',gap:8,marginTop:8,alignItems:'end'}}>
          <label>{ar?'الصنف':'Item'}<select style={field} value={lineItemId} onChange={event=>setLineItemId(event.target.value)}>{itemOptions.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
          <label>{ar?'الكمية':'Qty'}<input type="number" min="0" style={field} value={lineQty} onChange={event=>setLineQty(event.target.value)}/></label>
          <label>{ar?'سعر المورد':'Supplier cost'}<input type="number" min="0" style={field} value={lineCost} onChange={event=>setLineCost(event.target.value)}/></label>
          <label>{ar?'الدفعة':'Lot'}<input style={field} value={lineLot} onChange={event=>setLineLot(event.target.value)}/></label>
          <label>{ar?'الصلاحية':'Expiry'}<input type="date" style={field} value={lineExpiry} onChange={event=>setLineExpiry(event.target.value)}/></label>
          <button style={btn} onClick={addLine}>{ar?'إضافة':'Add'}</button>
        </div>
        {lines.length>0&&<div style={{marginTop:10}}><DataTable headers={[ar?'الصنف':'Item',ar?'الكمية':'Qty',ar?'سعر المورد':'Cost',ar?'الدفعة':'Lot',ar?'الصلاحية':'Expiry']} rows={lines.map(line=>[line.item_code,String(line.quantity),fmt(line.supplier_unit_cost),line.lot_number||'—',line.expiry_date||'—'])}/></div>}
        <div style={{marginTop:10,display:'flex',justifyContent:'space-between',alignItems:'center',gap:12,flexWrap:'wrap'}}>
          <span>{ar?'إجمالي التكلفة المحمّلة المتوقع:':'Expected landed total:'} <strong>{fmt(totalLanded)}</strong></span>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createShipment}>{ar?'إنشاء الشحنة':'Create shipment'}</button>
        </div>
      </div>
    </Panel>

    <Panel title={ar?'الشحنات المسجلة':'Recorded shipments'} icon={<FileCheck2 size={18}/> }>
      <DataTable headers={[ar?'الرقم':'No.',ar?'الكونتينر':'Container',ar?'فاتورة المورد':'Invoice',ar?'التخليص':'Clearance',ar?'التكلفة المحمّلة':'Landed',ar?'الحالة':'Status',ar?'إجراء':'Action']}
        rows={shipments.map(row=>[row.number,row.container_number,row.commercial_invoice_number,row.customs_clearance_number||'—',fmt(Number(row.landed_cost_total)),row.status==='RECEIVED'?(ar?'مستلمة':'Received'):(ar?'مسعّرة':'Costed'),row.status==='COSTED'?<button key={row.id} style={{...btn,padding:'5px 12px'}} disabled={busy} onClick={()=>receiveShipment(row.id)}>{ar?'استلام':'Receive'}</button>:'✓'])}/>
    </Panel>
  </>;
}
