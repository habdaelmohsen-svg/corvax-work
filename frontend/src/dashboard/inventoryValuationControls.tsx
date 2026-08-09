import {useEffect, useState} from 'react';
import {Boxes, ShieldCheck, TrendingDown} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type Item={id:number;code:string;name_ar:string;name_en:string};
type Warehouse={id:number;code:string;name_ar:string;name_en:string};
type NrvLine={item_id:number;item_code:string;item_name_ar:string;warehouse_id:number;warehouse_name_ar:string;quantity:number;carrying_cost:number;unit_cost:number;nrv_per_unit:number|null;measured_at:string;writedown_required:number};
type NrvAssessment={total_writedown_required:number;lines:NrvLine[]};

const ITEM_TYPES:[string,string,string][]=[
  ['RAW_MATERIAL','مواد خام','Raw material'],
  ['WORK_IN_PROGRESS','تحت التصنيع','Work in progress'],
  ['FINISHED_GOOD','منتج نهائي','Finished good'],
  ['PACKAGING','تعبئة وتغليف','Packaging'],
  ['CLEANING_MATERIAL','مواد نظافة','Cleaning material'],
  ['OPERATING_SUPPLY','مواد تشغيلية','Operating supply'],
  ['SPARE_PART','قطع غيار','Spare part'],
  ['SERVICE','خدمة','Service'],
];
const RAW_SUBTYPES:[string,string,string][]=[
  ['CORE_MATERIAL','أساسية (لحوم/دواجن)','Core material'],
  ['SPICE','بهارات','Spice'],
  ['CHEMICAL_BINDER','مواد ربط كيميائية','Chemical binder'],
  ['AUXILIARY_MATERIAL','مواد مساعدة (زيوت/شحوم)','Auxiliary material'],
];

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
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12} as const;

export function InventoryValuationControls({ar,companyId,mode}:{ar:boolean;companyId:number;mode:'classify'|'nrv'}){
  const [items,setItems]=useState<Item[]>([]);
  const [warehouses,setWarehouses]=useState<Warehouse[]>([]);
  const [message,setMessage]=useState('');
  const [error,setError]=useState(false);
  const [busy,setBusy]=useState(false);
  const [nrv,setNrv]=useState<NrvAssessment|null>(null);

  const [clsItem,setClsItem]=useState('');
  const [clsType,setClsType]=useState('RAW_MATERIAL');
  const [clsSubtype,setClsSubtype]=useState('CORE_MATERIAL');
  const [clsValuation,setClsValuation]=useState('WEIGHTED_AVERAGE');
  const [clsIssue,setClsIssue]=useState('FEFO');
  const [nrvItem,setNrvItem]=useState('');
  const [nrvWarehouse,setNrvWarehouse]=useState('');
  const [nrvValue,setNrvValue]=useState('');

  const loadMasters=async()=>{
    try{
      const [itemRows,warehouseRows]=await Promise.all([
        json(`/api/v1/inventory/items?company_id=${companyId}`),
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`),
      ]);
      const nextItems=Array.isArray(itemRows)?itemRows:[];
      const nextWarehouses=Array.isArray(warehouseRows)?warehouseRows:[];
      setItems(nextItems);setWarehouses(nextWarehouses);
      if(!clsItem&&nextItems.length)setClsItem(String(nextItems[0].id));
      if(!nrvItem&&nextItems.length)setNrvItem(String(nextItems[0].id));
      if(!nrvWarehouse&&nextWarehouses.length)setNrvWarehouse(String(nextWarehouses[0].id));
    }catch(cause:any){setMessage(String(cause.message||cause));setError(true);}
  };

  const loadNrv=async()=>{
    try{setNrv(await json(`/api/v1/inventory/nrv-assessment?company_id=${companyId}`));}
    catch(cause:any){setMessage(String(cause.message||cause));setError(true);}
  };

  useEffect(()=>{void loadMasters();},[companyId]);
  useEffect(()=>{if(mode==='nrv')void loadNrv();},[companyId,mode]);

  const classify=async()=>{
    if(!clsItem){setMessage(ar?'اختر الصنف':'Select an item');setError(true);return;}
    setBusy(true);setMessage('');
    try{
      const body:any={company_id:companyId,item_id:Number(clsItem),item_type:clsType,valuation_method:clsValuation,physical_issue_method:clsIssue};
      if(clsType==='RAW_MATERIAL')body.item_subtype=clsSubtype;
      const result=await json('/api/v1/inventory/items/classify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(ar?`تم حفظ تصنيف ${result.code}`:`Classification saved for ${result.code}`);setError(false);
    }catch(cause:any){setMessage(String(cause.message||cause));setError(true);}
    finally{setBusy(false);}
  };

  const writedown=async()=>{
    if(!nrvItem||!nrvWarehouse){setMessage(ar?'اختر الصنف والمستودع':'Select an item and warehouse');setError(true);return;}
    setBusy(true);setMessage('');
    try{
      const body:any={company_id:companyId,item_id:Number(nrvItem),warehouse_id:Number(nrvWarehouse)};
      if(nrvValue)body.nrv_per_unit=Number(nrvValue);
      const result=await json('/api/v1/inventory/nrv-writedown',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(result.journal_number
        ?(ar?`تم ترحيل تخفيض ${fmt(Number(result.writedown))} بالقيد ${result.journal_number}`:`Write-down ${fmt(Number(result.writedown))} posted as ${result.journal_number}`)
        :(ar?'صافي القيمة القابلة للتحقق ليس أقل من التكلفة؛ لا يوجد تخفيض.':'NRV is not below cost; no write-down was posted.'));
      setError(false);await loadNrv();
    }catch(cause:any){setMessage(String(cause.message||cause));setError(true);}
    finally{setBusy(false);}
  };

  return <>
    {message&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.8,background:error?'#fee2e2':'#dcfce7',color:error?'#991b1b':'#166534'}}>{message}</div>}
    {mode==='classify'&&<Panel title={ar?'تصنيف الأصناف وسياسة التقييم':'Item classification and valuation policy'} icon={<Boxes size={18}/> }>
      <div style={grid}>
        <label>{ar?'الصنف':'Item'}<select data-testid="inventory-classify-item" style={field} value={clsItem} onChange={event=>setClsItem(event.target.value)}>{items.map(row=><option key={row.id} value={row.id}>{row.code} — {ar?row.name_ar:row.name_en}</option>)}</select></label>
        <label>{ar?'نوع الصنف':'Item type'}<select data-testid="inventory-classify-type" style={field} value={clsType} onChange={event=>setClsType(event.target.value)}>{ITEM_TYPES.map(([value,labelAr,labelEn])=><option key={value} value={value}>{ar?labelAr:labelEn}</option>)}</select></label>
        {clsType==='RAW_MATERIAL'&&<label>{ar?'التصنيف الفرعي':'Subtype'}<select style={field} value={clsSubtype} onChange={event=>setClsSubtype(event.target.value)}>{RAW_SUBTYPES.map(([value,labelAr,labelEn])=><option key={value} value={value}>{ar?labelAr:labelEn}</option>)}</select></label>}
        <label>{ar?'طريقة تقييم المخزون':'Inventory valuation'}<select style={field} value={clsValuation} onChange={event=>setClsValuation(event.target.value)}><option value="WEIGHTED_AVERAGE">{ar?'المتوسط المرجح':'Weighted average'}</option><option value="FIFO">FIFO</option></select></label>
        <label>{ar?'طريقة الصرف المادي':'Physical issue method'}<select style={field} value={clsIssue} onChange={event=>setClsIssue(event.target.value)}><option value="FEFO">FEFO ({ar?'الأقرب انتهاءً':'earliest expiry'})</option><option value="FIFO">FIFO</option></select></label>
      </div>
      <div style={{padding:'0 12px 14px'}}><button data-testid="inventory-classify-save" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={classify}>{ar?'حفظ التصنيف':'Save classification'}</button>
        <p style={{marginTop:8,fontSize:13,color:'var(--muted)'}}>{ar?'لا يسمح النظام باستخدام LIFO وفق IAS 2، وكل تغيير في سياسة التقييم يُسجل في سجل التدقيق.':'LIFO is prohibited under IAS 2, and every valuation-policy change is audit-logged.'}</p>
      </div>
    </Panel>}

    {mode==='nrv'&&<>
      <div className="kpis">
        <Kpi title={ar?'تخفيض NRV المطلوب':'NRV write-down required'} value={nrv?fmt(Number(nrv.total_writedown_required)):'—'} trend={ar?'الأقل من التكلفة أو صافي القيمة القابلة للتحقق':'Lower of cost and NRV'} good={Number(nrv?.total_writedown_required||0)===0} icon={<TrendingDown size={22}/>} tone="amber"/>
      </div>
      <Panel title={ar?'تقييم صافي القيمة القابلة للتحقق NRV':'Net realizable value assessment'} icon={<TrendingDown size={18}/> }>
        <div style={grid}>
          <label>{ar?'الصنف':'Item'}<select data-testid="inventory-nrv-item" style={field} value={nrvItem} onChange={event=>setNrvItem(event.target.value)}>{items.map(row=><option key={row.id} value={row.id}>{row.code} — {ar?row.name_ar:row.name_en}</option>)}</select></label>
          <label>{ar?'المستودع':'Warehouse'}<select data-testid="inventory-nrv-warehouse" style={field} value={nrvWarehouse} onChange={event=>setNrvWarehouse(event.target.value)}>{warehouses.map(row=><option key={row.id} value={row.id}>{row.code} — {ar?row.name_ar:row.name_en}</option>)}</select></label>
          <label>{ar?'NRV لكل وحدة':'NRV per unit'}<input data-testid="inventory-nrv-value" type="number" min="0" step="0.0001" style={field} value={nrvValue} onChange={event=>setNrvValue(event.target.value)} placeholder={ar?'اتركه فارغًا لاستخدام القيمة المحفوظة':'Blank uses the stored value'}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}><button data-testid="inventory-nrv-post" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={writedown}>{ar?'ترحيل التخفيض عند الحاجة':'Post required write-down'}</button></div>
      </Panel>
      <Panel title={ar?'تقرير تقييم NRV للمراجعة':'NRV assessment audit report'} icon={<ShieldCheck size={18}/> }>
        <DataTable headers={[ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Qty',ar?'التكلفة/وحدة':'Cost/u',ar?'NRV/وحدة':'NRV/u',ar?'أساس القياس':'Measurement',ar?'التخفيض المطلوب':'Write-down']}
          rows={(nrv?.lines||[]).map(line=>[line.item_code,line.warehouse_name_ar,String(line.quantity),fmt(Number(line.unit_cost)),line.nrv_per_unit==null?'—':fmt(Number(line.nrv_per_unit)),line.measured_at==='NRV'?(ar?'صافي القيمة القابلة للتحقق':'NRV'):(ar?'التكلفة':'Cost'),fmt(Number(line.writedown_required))])}/>
      </Panel>
    </>}
  </>;
}
