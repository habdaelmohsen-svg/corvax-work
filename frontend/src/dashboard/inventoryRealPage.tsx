import {useEffect, useState} from 'react';
import {AlertTriangle, Boxes, Warehouse as WarehouseIcon, ShoppingCart, PackageCheck, ArrowLeftRight, FileText, Plus} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';
import {InventoryValuationControls} from './inventoryValuationControls';

// The real procurement and stock cycle:
//   purchase order -> approve -> goods receipt (raises stock, credits 214010)
//   -> supplier invoice (clears 214010) ; plus issues and transfers.
// The previous screen only fired sample data with no input fields at all.

type WH={id:number;code:string;name_ar:string;name_en:string};
type Item={id:number;code:string;name_ar:string;name_en:string;uom:string;standard_cost:number};
type Party={id:number;code?:string;name_ar:string;name_en:string;party_type:string;vat_number?:string|null;credit_limit?:number};
type PO={id:number;number:string;order_date:string;status:string;total?:number;supplier?:string;received_percent?:number};
type GRN={id:number;number:string;receipt_date:string;purchase_order_number:string;warehouse:string;total_cost:number;purchase_invoice_id?:number|null};
type Stock={item_code?:string;item_name_ar?:string;warehouse_code?:string;quantity?:number;value?:number};
type InventoryAlert={type:string;severity:string;reference:string;message_ar:string;message_en:string;quantity?:number;threshold?:number;days?:number};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    const msg=typeof d==='string'?d:(d&&(d.message_ar||d.message_en))?(d.message_ar||d.message_en):JSON.stringify(d||x);
    throw new Error(msg);
  }
  return x;
}
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const addDays=(n:number)=>{const d=new Date();d.setDate(d.getDate()+n);return iso(d);};
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'4px 11px',borderRadius:7,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(185px,1fr))',gap:12,padding:12} as const;

export function InventoryPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'stock'|'orders'|'moves'|'warehouses'|'classify'|'nrv'|'alerts'>('stock');
  const [warehouses,setWarehouses]=useState<WH[]>([]);
  const [items,setItems]=useState<Item[]>([]);
  const [suppliers,setSuppliers]=useState<Party[]>([]);
  const [orders,setOrders]=useState<PO[]>([]);
  const [receipts,setReceipts]=useState<GRN[]>([]);
  const [stock,setStock]=useState<Stock[]>([]);
  const [alerts,setAlerts]=useState<InventoryAlert[]>([]);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  // purchase order
  const [poSupplier,setPoSupplier]=useState(''); const [poWh,setPoWh]=useState(''); const [poDate,setPoDate]=useState(iso());
  const [poItem,setPoItem]=useState(''); const [poQty,setPoQty]=useState(''); const [poPrice,setPoPrice]=useState('');
  const [receiptLot,setReceiptLot]=useState(''); const [receiptExpiry,setReceiptExpiry]=useState('');
  // supplier master data
  const [supCode,setSupCode]=useState(''); const [supAr,setSupAr]=useState(''); const [supEn,setSupEn]=useState('');
  const [supVat,setSupVat]=useState(''); const [supCredit,setSupCredit]=useState('0');
  // warehouse
  const [whCode,setWhCode]=useState(''); const [whAr,setWhAr]=useState(''); const [whEn,setWhEn]=useState(''); const [whType,setWhType]=useState('MAIN');
  // issue
  const [isWh,setIsWh]=useState(''); const [isItem,setIsItem]=useState(''); const [isQty,setIsQty]=useState(''); const [isReason,setIsReason]=useState('PRODUCTION');
  // transfer
  const [trFrom,setTrFrom]=useState(''); const [trTo,setTrTo]=useState(''); const [trItem,setTrItem]=useState(''); const [trQty,setTrQty]=useState('');
  // Supplier invoice matched to a posted goods receipt.
  const [invoiceDate,setInvoiceDate]=useState(iso()); const [dueDate,setDueDate]=useState(addDays(30));
  const [supplierInvoiceNo,setSupplierInvoiceNo]=useState('');

  const load=async()=>{
    try{
      const [w,i,p,o,s,g,a]=await Promise.all([
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/items?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/parties?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/purchase-orders?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/stock-summary?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/goods-receipts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/alerts?company_id=${companyId}`).catch(()=>({alerts:[]})),
      ]);
      setWarehouses(Array.isArray(w)?w:[]); setItems(Array.isArray(i)?i:[]);
      setSuppliers((Array.isArray(p)?p:[]).filter((x:Party)=>x.party_type==='SUPPLIER'));
      setOrders(Array.isArray(o)?o:[]); setStock(Array.isArray(s)?s:[]);
      setReceipts(Array.isArray(g)?g:[]);
      setAlerts(Array.isArray(a?.alerts)?a.alerts:[]);
      if(!poWh&&w?.length)setPoWh(String(w[0].id));
      if(!isWh&&w?.length)setIsWh(String(w[0].id));
      if(!trFrom&&w?.length)setTrFrom(String(w[0].id));
      if(!poItem&&i?.length)setPoItem(String(i[0].id));
      if(!isItem&&i?.length)setIsItem(String(i[0].id));
      if(!trItem&&i?.length)setTrItem(String(i[0].id));
      const sup=(Array.isArray(p)?p:[]).filter((x:Party)=>x.party_type==='SUPPLIER');
      if(!poSupplier&&sup.length)setPoSupplier(String(sup[0].id));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};

  const createWarehouse=async()=>{
    if(!whCode||!whAr||!whEn){bad({message:ar?'أكمل البيانات':'Complete the fields'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/inventory/warehouses',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,code:whCode,name_ar:whAr,name_en:whEn,warehouse_type:whType})});
      ok(ar?`تم إنشاء المستودع ${whCode}`:`Warehouse ${whCode} created`);
      setWhCode('');setWhAr('');setWhEn(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const createSupplier=async()=>{
    if(!supCode.trim()||!supAr.trim()||!supEn.trim()){
      bad({message:ar?'كود المورد والاسمان إلزامية':'Supplier code and both names are required'});return;
    }
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/subledgers/parties',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,code:supCode.trim(),name_ar:supAr.trim(),name_en:supEn.trim(),
          party_type:'SUPPLIER',vat_number:supVat.trim()||null,credit_limit:Number(supCredit)||0})});
      setSupCode('');setSupAr('');setSupEn('');setSupVat('');setSupCredit('0');
      await load();setPoSupplier(String(r.id));
      ok(ar?`تم إنشاء المورد ${r.code} واختياره لأمر الشراء`:`Supplier ${r.code} created and selected for the purchase order`);
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const createPO=async()=>{
    if(!poSupplier||!poWh||!poItem||!poQty||!poPrice){bad({message:ar?'أكمل بيانات الأمر':'Complete the order'});return;}
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/inventory/purchase-orders',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,order_date:poDate,supplier_id:Number(poSupplier),
          warehouse_id:Number(poWh),
          lines:[{item_id:Number(poItem),quantity:Number(poQty),unit_price:Number(poPrice)}]})});
      ok(ar?`تم إنشاء أمر الشراء ${r.number||r.id} — يحتاج اعتمادًا قبل الاستلام`
           :`Purchase order ${r.number||r.id} created — approve it before receiving`);
      setPoQty('');setPoPrice(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const approvePO=async(id:number)=>{
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/inventory/purchase-orders/${id}/approve`,{method:'POST'});
      ok(ar?'تم اعتماد أمر الشراء — يمكنك الآن إثبات الاستلام':'Approved — you can now record the receipt');
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const receivePO=async(id:number)=>{
    setBusy(true);setMsg('');
    try{
      // There is no GET for a single order; the list already carries the lines.
      const all=await json(`/api/v1/inventory/purchase-orders?company_id=${companyId}`);
      const po=(Array.isArray(all)?all:[]).find((o:any)=>o.id===id);
      // Receive only what is still outstanding: the backend refuses a quantity
      // greater than (ordered - already received), so a partially received
      // order must send the remainder, not the original quantity.
      const lines=(po?.lines||[])
        .map((l:any)=>({purchase_order_line_id:l.id,
          quantity:Number(l.quantity||0)-Number(l.received_quantity||0),
          lot_number:receiptLot.trim()||null,
          expiry_date:receiptExpiry||null}))
        .filter((l:any)=>l.quantity>0);
      if(!lines.length){bad({message:ar?'لا توجد كميات متبقية للاستلام في هذا الأمر':'Nothing left to receive on this order'});return;}
      const r=await json(`/api/v1/inventory/purchase-orders/${id}/receive`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({receipt_date:iso(),lines})});
      ok(ar?`تم إثبات الاستلام ${r.number||''} — زاد المخزون وسُجّل في «استلامات غير مفوترة» 214010`
           :`Receipt ${r.number||''} recorded — stock raised, 214010 credited`);
      setReceiptLot('');setReceiptExpiry('');
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const issue=async()=>{
    if(!isWh||!isItem||!isQty){bad({message:ar?'أكمل بيانات الصرف':'Complete the issue'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/inventory/issues',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,issue_date:iso(),warehouse_id:Number(isWh),
          item_id:Number(isItem),quantity:Number(isQty),reference:isReason+'-'+Date.now()})});
      ok(ar?'تم صرف الكمية من المستودع':'Issued from the warehouse');
      setIsQty(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const transfer=async()=>{
    if(!trFrom||!trTo||!trItem||!trQty){bad({message:ar?'أكمل بيانات التحويل':'Complete the transfer'});return;}
    if(trFrom===trTo){bad({message:ar?'المستودعان متطابقان':'Source and destination are the same'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/inventory/transfers',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,transfer_date:iso(),source_warehouse_id:Number(trFrom),
          destination_warehouse_id:Number(trTo),item_id:Number(trItem),quantity:Number(trQty),
          reference:'TRANSFER-'+Date.now()})});
      ok(ar?'تم التحويل بين المستودعين':'Transferred between warehouses');
      setTrQty(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const invoiceGRN=async(id:number)=>{
    if(!supplierInvoiceNo.trim()){bad({message:ar?'أدخل رقم فاتورة المورد':'Enter the supplier invoice number'});return;}
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/inventory/goods-receipts/'+id+'/supplier-invoice',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({invoice_date:invoiceDate,due_date:dueDate,supplier_invoice_number:supplierInvoiceNo.trim()})});
      ok((ar?'تمت المطابقة الثلاثية وربط فاتورة المورد ':'Three-way match posted as ')+(r.number||r.id));
      setSupplierInvoiceNo('');await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const openPOs=orders.filter(o=>!['RECEIVED','INVOICED','CLOSED','CANCELLED'].includes(o.status)).length;
  const totalValue=stock.reduce((s,r)=>s+Number(r.value||0),0);

  return <>
    <div className="kpis">
      <Kpi title={ar?'المستودعات':'Warehouses'} value={String(warehouses.length)} trend="" good icon={<WarehouseIcon size={22}/>} tone="blue"/>
      <Kpi title={ar?'الأصناف':'Items'} value={String(items.length)} trend="" good icon={<Boxes size={22}/>} tone="violet"/>
      <Kpi title={ar?'أوامر شراء مفتوحة':'Open orders'} value={String(openPOs)} trend="" good={openPOs===0} icon={<ShoppingCart size={22}/>} tone="amber"/>
      <Kpi title={ar?'قيمة المخزون':'Stock value'} value={fmt(totalValue)} trend="" good icon={<PackageCheck size={22}/>} tone="green"/>
      <Kpi title={ar?'تنبيهات المخزون':'Inventory alerts'} value={String(alerts.length)} trend="" good={alerts.length===0} icon={<AlertTriangle size={22}/>} tone="amber"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['stock',ar?'الأرصدة':'Stock'],['orders',ar?'دورة الشراء':'Purchase cycle'],
         ['moves',ar?'الصرف والتحويل':'Issues & transfers'],['warehouses',ar?'المستودعات':'Warehouses'],
         ['classify',ar?'تصنيف الأصناف':'Item classification'],['nrv',ar?'تقييم NRV':'NRV assessment'],
         ['alerts',ar?'التنبيهات':'Alerts']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>setTab(k)}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.8,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab==='stock'&&<Panel title={ar?'أرصدة المخزون':'Stock balances'} icon={<Boxes size={18}/>}>
      <DataTable headers={[ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Quantity',ar?'القيمة':'Value']}
        rows={stock.map(s=>[s.item_code||'—',s.warehouse_code||'—',fmt(Number(s.quantity||0)),fmt(Number(s.value||0))])}/>
    </Panel>}

    {tab==='alerts'&&<Panel title={ar?'تنبيهات المخزون والتوريد':'Inventory & procurement alerts'} icon={<AlertTriangle size={18}/> }>
      <div style={{padding:'8px 12px 0',fontSize:13,opacity:.8}}>{ar?'تُحتسب من أوامر الشراء والكميات وحدود إعادة الطلب وتواريخ التشغيلات وآخر حركة فعلية.':'Calculated from POs, quantities, reorder levels, lot expiry and actual last movement.'}</div>
      <DataTable headers={[ar?'الأولوية':'Severity',ar?'النوع':'Type',ar?'المرجع':'Reference',ar?'التفاصيل':'Details']}
        rows={alerts.map((row,index)=>[<span key={index} style={{fontWeight:700,color:row.severity==='CRITICAL'?'#b91c1c':row.severity==='HIGH'?'#c2410c':'#a16207'}}>{row.severity}</span>,row.type,row.reference,ar?row.message_ar:row.message_en])}/>
    </Panel>}

    {tab==='orders'&&<>
      <Panel title={ar?'مورد جديد':'New supplier'} icon={<Plus size={18}/> }>
        <div style={grid}>
          <label>{ar?'كود المورد':'Supplier code'}<input style={field} value={supCode} onChange={e=>setSupCode(e.target.value)} placeholder="SUP-NEW-001"/></label>
          <label>{ar?'اسم المورد (عربي)':'Supplier name (Arabic)'}<input style={field} value={supAr} onChange={e=>setSupAr(e.target.value)}/></label>
          <label>{ar?'اسم المورد (إنجليزي)':'Supplier name (English)'}<input style={field} value={supEn} onChange={e=>setSupEn(e.target.value)}/></label>
          <label>{ar?'الرقم الضريبي للمورد':'Supplier VAT number'}<input inputMode="numeric" maxLength={15} style={field} value={supVat} onChange={e=>setSupVat(e.target.value)} placeholder="15 digits"/></label>
          <label>{ar?'حد الائتمان للمورد':'Supplier credit limit'}<input type="number" min="0" step="0.01" style={field} value={supCredit} onChange={e=>setSupCredit(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px',display:'flex',gap:12,alignItems:'center',flexWrap:'wrap'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createSupplier}>{ar?'إنشاء المورد':'Create supplier'}</button>
          <span style={{fontSize:12,opacity:.75}}>{ar?'يتطلب الرقم الضريبي 15 رقمًا عند إدخاله.':'VAT number must contain 15 digits when supplied.'}</span>
        </div>
        <DataTable headers={[ar?'الكود':'Code',ar?'المورد':'Supplier',ar?'الرقم الضريبي':'VAT number',ar?'حد الائتمان':'Credit limit']}
          rows={suppliers.map(s=>[s.code||String(s.id),ar?s.name_ar:s.name_en,s.vat_number||'—',fmt(Number(s.credit_limit||0))])}/>
      </Panel>
      <Panel title={ar?'أمر شراء جديد':'New purchase order'} icon={<Plus size={18}/> }>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'الدورة الصحيحة: أمر شراء ← اعتماد ← إثبات استلام (هنا يزيد المخزون) ← فاتورة المورد. لا تُرحّل فاتورة شراء على حساب المخزون مباشرة، وإلا صار المخزون مدينًا مرتين.'
            : 'Correct flow: order -> approve -> goods receipt (this is where stock rises) -> supplier invoice. Never post an invoice straight to inventory or stock is debited twice.'}
        </div>
        <div style={grid}>
          <label>{ar?'المورد':'Supplier'}<select style={field} value={poSupplier} onChange={e=>setPoSupplier(e.target.value)}>
            {suppliers.map(s=><option key={s.id} value={s.id}>{ar?s.name_ar:s.name_en}</option>)}</select></label>
          <label>{ar?'المستودع':'Warehouse'}<select style={field} value={poWh} onChange={e=>setPoWh(e.target.value)}>
            {warehouses.map(w=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
          <label>{ar?'تاريخ الأمر':'Order date'}<input type="date" style={field} value={poDate} onChange={e=>setPoDate(e.target.value)}/></label>
          <label>{ar?'الصنف':'Item'}<select style={field} value={poItem} onChange={e=>{setPoItem(e.target.value);
            const it=items.find(i=>String(i.id)===e.target.value); if(it&&!poPrice)setPoPrice(String(it.standard_cost||''));}}>
            {items.map(i=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
          <label>{ar?'الكمية':'Quantity'}<input type="number" step="0.01" style={field} value={poQty} onChange={e=>setPoQty(e.target.value)}/></label>
          <label>{ar?'سعر الوحدة':'Unit price'}<input type="number" step="0.0001" style={field} value={poPrice} onChange={e=>setPoPrice(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createPO}>{ar?'إنشاء أمر الشراء':'Create order'}</button>
        </div>
      </Panel>
      <Panel title={ar?'بيانات التشغيلة عند الاستلام':'Receipt lot traceability'} icon={<PackageCheck size={18}/> }>
        <div style={grid}>
          <label>{ar?'رقم التشغيلة / الدفعة':'Lot / batch number'}<input style={field} value={receiptLot} onChange={e=>setReceiptLot(e.target.value)} placeholder="LOT-2026-001"/></label>
          <label>{ar?'تاريخ الصلاحية':'Expiry date'}<input type="date" style={field} value={receiptExpiry} onChange={e=>setReceiptExpiry(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 12px',fontSize:12,opacity:.75}}>{ar?'تُرسل هذه البيانات مع سطور أمر الشراء عند الضغط على «إثبات استلام».':'These values are sent with the purchase-order lines when Receive is pressed.'}</div>
      </Panel>
      <Panel title={ar?'أوامر الشراء':'Purchase orders'} icon={<ShoppingCart size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'المورد':'Supplier',ar?'القيمة':'Value',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={orders.map(o=>[o.number||o.id,o.order_date,o.supplier||'—',fmt(Number(o.total||0)),o.status,
            <span key={o.id} style={{display:'flex',gap:5}}>
              {o.status==='DRAFT'&&<button style={smallBtn} disabled={busy} onClick={()=>approvePO(o.id)}>{ar?'اعتماد':'Approve'}</button>}
              {['APPROVED','PARTIALLY_RECEIVED'].includes(o.status)&&<button style={{...smallBtn,background:'#059669'}} disabled={busy} onClick={()=>receivePO(o.id)}>{ar?'إثبات استلام':'Receive'}</button>}
              {['RECEIVED','INVOICED','CLOSED'].includes(o.status)&&<span style={{fontSize:12,opacity:0.7}}>{o.status==='INVOICED'?(ar?'مفوّتَر':'Invoiced'):(ar?'مستلَم':'Received')}</span>}
            </span>])}/>
      </Panel>
      <Panel title={ar?'المطابقة الثلاثية: أمر — استلام — فاتورة':'Three-way match: PO — receipt — invoice'} icon={<FileText size={18}/>}>
        <div style={grid}>
          <label>{ar?'تاريخ الفاتورة':'Invoice date'}<input type="date" style={field} value={invoiceDate} onChange={e=>setInvoiceDate(e.target.value)}/></label>
          <label>{ar?'تاريخ الاستحقاق':'Due date'}<input type="date" style={field} value={dueDate} onChange={e=>setDueDate(e.target.value)}/></label>
          <label>{ar?'رقم فاتورة المورد':'Supplier invoice no.'}<input style={field} value={supplierInvoiceNo} onChange={e=>setSupplierInvoiceNo(e.target.value)} placeholder="SUP-INV-0001"/></label>
        </div>
        <DataTable headers={[ar?'الاستلام':'Receipt',ar?'أمر الشراء':'PO',ar?'التاريخ':'Date',ar?'القيمة':'Value',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={receipts.map(g=>[g.number,g.purchase_order_number,g.receipt_date,fmt(Number(g.total_cost||0)),g.purchase_invoice_id?(ar?'مفوّتَر':'Invoiced'):(ar?'بانتظار الفاتورة':'Awaiting invoice'),
            g.purchase_invoice_id?'✓':<button key={g.id} style={smallBtn} disabled={busy} onClick={()=>invoiceGRN(g.id)}>{ar?'مطابقة وترحيل':'Match & post'}</button>])}/>
      </Panel>
    </>}

    {tab==='moves'&&<>
      <Panel title={ar?'صرف من المستودع':'Issue from warehouse'} icon={<ArrowLeftRight size={18}/>}>
        <div style={grid}>
          <label>{ar?'المستودع':'Warehouse'}<select style={field} value={isWh} onChange={e=>setIsWh(e.target.value)}>
            {warehouses.map(w=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
          <label>{ar?'الصنف':'Item'}<select style={field} value={isItem} onChange={e=>setIsItem(e.target.value)}>
            {items.map(i=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
          <label>{ar?'الكمية':'Quantity'}<input type="number" step="0.01" style={field} value={isQty} onChange={e=>setIsQty(e.target.value)}/></label>
          <label>{ar?'السبب':'Reason'}<select style={field} value={isReason} onChange={e=>setIsReason(e.target.value)}>
            <option value="PRODUCTION">{ar?'صرف للإنتاج':'To production'}</option>
            <option value="SALE">{ar?'بيع':'Sale'}</option>
            <option value="DAMAGE">{ar?'تالف':'Damaged'}</option>
            <option value="SAMPLE">{ar?'عينة':'Sample'}</option>
            <option value="ADJUSTMENT">{ar?'تسوية جرد':'Stock adjustment'}</option>
          </select></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={issue}>{ar?'صرف':'Issue'}</button>
        </div>
      </Panel>
      <Panel title={ar?'تحويل بين المستودعات':'Transfer between warehouses'} icon={<ArrowLeftRight size={18}/>}>
        <div style={grid}>
          <label>{ar?'من مستودع':'From'}<select style={field} value={trFrom} onChange={e=>setTrFrom(e.target.value)}>
            {warehouses.map(w=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
          <label>{ar?'إلى مستودع':'To'}<select style={field} value={trTo} onChange={e=>setTrTo(e.target.value)}>
            <option value="">{ar?'اختر...':'Select...'}</option>
            {warehouses.map(w=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
          <label>{ar?'الصنف':'Item'}<select style={field} value={trItem} onChange={e=>setTrItem(e.target.value)}>
            {items.map(i=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
          <label>{ar?'الكمية':'Quantity'}<input type="number" step="0.01" style={field} value={trQty} onChange={e=>setTrQty(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={transfer}>{ar?'تحويل':'Transfer'}</button>
        </div>
      </Panel>
    </>}

    {tab==='warehouses'&&<>
      <Panel title={ar?'مستودع جديد':'New warehouse'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={whCode} onChange={e=>setWhCode(e.target.value)} placeholder="WH-COLD-01"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={whAr} onChange={e=>setWhAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={whEn} onChange={e=>setWhEn(e.target.value)}/></label>
          <label>{ar?'النوع':'Type'}<select style={field} value={whType} onChange={e=>setWhType(e.target.value)}>
            {/* Must match backend WAREHOUSE_TYPES. GENERAL is aliased to MAIN. */}
            <option value="MAIN">{ar?'رئيسي — عام':'Main'}</option>
            <option value="RAW">{ar?'مواد خام':'Raw materials'}</option>
            <option value="FINISHED">{ar?'منتج تام':'Finished goods'}</option>
            <option value="RAW_AND_FINISHED">{ar?'خام ومنتج تام معًا':'Raw and finished'}</option>
            <option value="COLD">{ar?'مبرّد — ٠ إلى ٤ درجات':'Chilled 0-4 C'}</option>
            <option value="FROZEN">{ar?'مجمّد — ١٨- درجة فأقل':'Frozen -18 C'}</option>
            <option value="QUARANTINE">{ar?'حجر — بانتظار الفحص':'Quarantine'}</option>
            <option value="TRANSIT">{ar?'عبور — بين المواقع':'In transit'}</option>
            <option value="TAX_WAREHOUSE">{ar?'مستودع ضريبي مرخّص':'Licensed tax warehouse'}</option>
          </select></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createWarehouse}>{ar?'إنشاء المستودع':'Create warehouse'}</button>
        </div>
      </Panel>
      <Panel title={ar?'المستودعات':'Warehouses'} icon={<WarehouseIcon size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name']}
          rows={warehouses.map(w=>[w.code,ar?w.name_ar:w.name_en])}/>
      </Panel>
    </>}

    {(tab==='classify'||tab==='nrv')&&<InventoryValuationControls ar={ar} companyId={companyId} mode={tab}/>} 
  </>;
}
