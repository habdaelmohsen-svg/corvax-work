import {useEffect, useMemo, useState} from 'react';
import {Boxes, Container, FileCheck2, PackageCheck} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type StockRow={item_id:number};
type Item={id:number;code:string;name_ar:string;name_en:string};
type Warehouse={id:number;code:string;name_ar:string;name_en:string};
type ShipmentLine={id:number;item_id:number;item_code:string;quantity:number;supplier_unit_cost:number;line_goods_value:number;allocated_landed_cost:number;landed_unit_cost:number;lot_number?:string;expiry_date?:string};
type Shipment={id:number;number:string;container_number:string;packing_list_number:string;commercial_invoice_number:string;customs_clearance_number?:string;customs_declaration_number?:string;arrival_date:string;port_of_entry?:string;carrier?:string;goods_value:number;freight_cost:number;customs_duty:number;clearance_fees:number;other_costs:number;landed_cost_total:number;status:string;journal_id?:number;lines?:ShipmentLine[]};
type Party={id:number;code:string;name_ar:string;name_en:string;party_type:string};

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
      const [stockRows,partyRows,shipmentRows,itemRows,warehouseRows]=await Promise.all([
        json(`/api/v1/inventory/stock-summary?company_id=${companyId}`),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`),
        json(`/api/v1/inventory/inbound-shipments?company_id=${companyId}`),
        json(`/api/v1/inventory/items?company_id=${companyId}`),
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`),
      ]);
      const nextItems=Array.isArray(itemRows)?itemRows:[];
      const nextWarehouses=Array.isArray(warehouseRows)?warehouseRows:[];
      const nextSuppliers=(Array.isArray(partyRows)?partyRows:[]).filter((row:Party)=>['SUPPLIER','BOTH'].includes(row.party_type));
      setStock(Array.isArray(stockRows)?stockRows:[]);
      setSuppliers(nextSuppliers);setShipments(Array.isArray(shipmentRows)?shipmentRows:[]);
      setItems(nextItems);setWarehouses(nextWarehouses);
      if(!warehouseId&&nextWarehouses.length)setWarehouseId(String(nextWarehouses[0].id));
      if(!lineItemId&&nextItems.length)setLineItemId(String(nextItems[0].id));
      if(!supplierId&&nextSuppliers.length)setSupplierId(String(nextSuppliers[0].id));
    }catch(cause:any){setMessage(String(cause.message||cause));}
  };
  useEffect(()=>{void load();},[companyId]);

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
    </div>

    {message&&<div style={{padding:10,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

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
        <div style={{display:'grid',gridTemplateColumns:'2fr 1fr 1fr 1fr 1fr auto',gap:8,marginTop:8,alignItems:'end'}}>
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
