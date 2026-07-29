import {useEffect, useMemo, useState} from 'react';
import {Package, Plus, Search, Layers} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Item master: raw materials, finished goods, packaging, consumables and
// services. Each item carries the three accounts that drive its postings, so a
// purchase, an issue to production and a sale all land in the right place.

type Item={id:number;code:string;name_ar:string;name_en:string;item_type:string;uom:string;
  standard_cost:number;reorder_level:number;active:boolean};
type Account={code:string;name_ar:string;name_en:string;is_postable:boolean;active:boolean};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    const msg=typeof d==='string'?d:(d&&(d.message_ar||d.message_en))?(d.message_ar||d.message_en):JSON.stringify(d||x);
    throw new Error(msg);
  }
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(185px,1fr))',gap:12,padding:12} as const;

// item_type drives which accounts matter and whether stock is tracked.
// These values must match backend/app/api/inventory.py::ITEM_TYPES exactly.
// FINISHED_GOOD is the spelling the seeder uses; sending FINISHED created a
// second, incompatible type for the same thing.
const TYPES:[string,string,string][]=[
  ['RAW_MATERIAL','مادة خام — يُتابع رصيدها','Raw material — tracked'],
  ['FINISHED_GOOD','منتج تام — يُتابع رصيده','Finished good — tracked'],
  ['PACKAGING','مواد تغليف — يُتابع رصيدها','Packaging — tracked'],
  ['INVENTORY','مخزني عام — قطع غيار ومستلزمات','General stock — tracked'],
  ['CONSUMABLE','مستهلك — بلا رصيد','Consumable — no balance'],
  ['SERVICE','خدمة — بلا رصيد','Service — no balance'],
];
const UOMS:[string,string][]=[
  ['KG','كيلوجرام'],['G','جرام'],['TON','طن'],['EA','وحدة'],['BOX','صندوق'],
  ['CTN','كرتون'],['L','لتر'],['ML','مليلتر'],['M','متر'],['PKT','عبوة'],
];

export function ItemsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [items,setItems]=useState<Item[]>([]);
  const [accounts,setAccounts]=useState<Account[]>([]);
  const [filter,setFilter]=useState('');
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  const [code,setCode]=useState(''); const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [type,setType]=useState('RAW_MATERIAL'); const [uom,setUom]=useState('KG');
  const [cost,setCost]=useState('0'); const [reorder,setReorder]=useState('0');
  const [invAcc,setInvAcc]=useState('113010'); const [cogsAcc,setCogsAcc]=useState('511010'); const [revAcc,setRevAcc]=useState('411010');

  const load=async()=>{
    try{
      const [it,ch]=await Promise.all([
        json(`/api/v1/inventory/items?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/chart-of-accounts`).catch(()=>[]),
      ]);
      setItems(Array.isArray(it)?it:[]);
      const rows:Account[]=Array.isArray(ch)?ch:[];
      setAccounts(rows.filter(a=>a.is_postable&&a.active));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const create=async()=>{
    if(!code||!nameAr||!nameEn){setMsg(ar?'الكود والاسمان إلزامية':'Code and both names are required');setErr(true);return;}
    setBusy(true);setMsg('');setErr(false);
    try{
      const r=await json('/api/v1/inventory/items',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,code:code.trim(),name_ar:nameAr.trim(),name_en:nameEn.trim(),
          item_type:type,uom,standard_cost:Number(cost)||0,reorder_level:Number(reorder)||0,
          inventory_account_code:invAcc,cogs_account_code:cogsAcc,revenue_account_code:revAcc})});
      setMsg(ar?`تم إنشاء الصنف ${r.code||code}`:`Item ${r.code||code} created`); setErr(false);
      setCode('');setNameAr('');setNameEn('');setCost('0');setReorder('0');
      await load();
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };

  const shown=useMemo(()=>{
    const q=filter.trim().toLowerCase();
    if(!q)return items;
    return items.filter(i=>i.code.toLowerCase().includes(q)||i.name_ar.toLowerCase().includes(q)||i.name_en.toLowerCase().includes(q));
  },[items,filter]);

  // Only these four carry a countable balance (see STOCKED_ITEM_TYPES).
  const stocked=items.filter(i=>['RAW_MATERIAL','FINISHED_GOOD','PACKAGING','INVENTORY'].includes(i.item_type)).length;
  const typeLabel=(v:string)=>{const f=TYPES.find(t=>t[0]===v);return f?(ar?f[1].split(' —')[0]:f[2].split(' —')[0]):v;};
  const expense=accounts.filter(a=>a.code.startsWith('5')||a.code.startsWith('6'));
  const revenue=accounts.filter(a=>a.code.startsWith('4'));
  const asset=accounts.filter(a=>a.code.startsWith('1'));

  return <>
    <div className="kpis">
      <Kpi title={ar?'الأصناف':'Items'} value={String(items.length)} trend="" good icon={<Package size={22}/>} tone="blue"/>
      <Kpi title={ar?'أصناف مخزنية':'Stocked'} value={String(stocked)} trend={ar?'يُتابع رصيدها':'tracked'} good icon={<Layers size={22}/>} tone="violet"/>
      <Kpi title={ar?'خدمات ومستهلكات':'Services'} value={String(items.length-stocked)} trend={ar?'بلا رصيد':'no stock'} good icon={<Package size={22}/>} tone="amber"/>
      <Kpi title={ar?'نشطة':'Active'} value={String(items.filter(i=>i.active!==false).length)} trend="" good icon={<Package size={22}/>} tone="green"/>
    </div>

    {msg&&<div style={{padding:11,margin:'12px 0',borderRadius:9,fontSize:14,lineHeight:1.8,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    <Panel title={ar?'صنف جديد':'New item'} icon={<Plus size={18}/>}>
      <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
        {ar
          ? 'الحسابات الثلاثة أدناه تحدّد أين تذهب القيود: حساب المخزون يُدين عند الاستلام، وحساب التكلفة يُدين عند الصرف للإنتاج أو البيع، وحساب الإيراد يُدان عند البيع. اضبطها بدقة — تغييرها لاحقًا لا يصحّح القيود القديمة.'
          : 'The three accounts decide where postings land: inventory is debited at receipt, cost of sales when the item is issued or sold, revenue when it is sold. Set them carefully - changing them later does not restate old entries.'}
      </div>
      <div style={grid}>
        <label>{ar?'كود الصنف':'Item code'}<input style={field} value={code} onChange={e=>setCode(e.target.value)} placeholder="RM-CHK-001"/></label>
        <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)} placeholder={ar?'دجاج كامل طازج':''}/></label>
        <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
        <label>{ar?'نوع الصنف':'Item type'}<select style={field} value={type} onChange={e=>setType(e.target.value)}>
          {TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
        <label>{ar?'وحدة القياس':'Unit'}<select style={field} value={uom} onChange={e=>setUom(e.target.value)}>
          {UOMS.map(([v,a])=><option key={v} value={v}>{ar?`${a} (${v})`:v}</option>)}</select></label>
        <label>{ar?'التكلفة المعيارية':'Standard cost'}<input type="number" step="0.0001" style={field} value={cost} onChange={e=>setCost(e.target.value)}/></label>
        <label>{ar?'حد إعادة الطلب':'Reorder level'}<input type="number" step="0.01" style={field} value={reorder} onChange={e=>setReorder(e.target.value)}/></label>
        <label>{ar?'حساب المخزون':'Inventory account'}<select style={field} value={invAcc} onChange={e=>setInvAcc(e.target.value)}>
          {asset.map(a=><option key={a.code} value={a.code}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}</select></label>
        <label>{ar?'حساب التكلفة':'Cost of sales'}<select style={field} value={cogsAcc} onChange={e=>setCogsAcc(e.target.value)}>
          {expense.map(a=><option key={a.code} value={a.code}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}</select></label>
        <label>{ar?'حساب الإيراد':'Revenue account'}<select style={field} value={revAcc} onChange={e=>setRevAcc(e.target.value)}>
          {revenue.map(a=><option key={a.code} value={a.code}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}</select></label>
      </div>
      <div style={{padding:'0 12px 14px'}}>
        <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'إنشاء الصنف':'Create item'}</button>
      </div>
    </Panel>

    <Panel title={ar?'دليل الأصناف':'Item master'} icon={<Package size={18}/>}>
      <div style={{display:'flex',alignItems:'center',gap:8,padding:'10px 12px'}}>
        <Search size={15} style={{opacity:0.6}}/>
        <input style={{...field,marginTop:0}} value={filter} onChange={e=>setFilter(e.target.value)}
          placeholder={ar?'بحث بالكود أو الاسم':'Search by code or name'}/>
      </div>
      <DataTable
        headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'النوع':'Type',ar?'الوحدة':'Unit',ar?'التكلفة':'Cost',ar?'حد الطلب':'Reorder']}
        rows={shown.map(i=>[i.code,ar?i.name_ar:i.name_en,typeLabel(i.item_type),i.uom,
          fmt(Number(i.standard_cost||0)),fmt(Number(i.reorder_level||0))])}/>
    </Panel>
  </>;
}
