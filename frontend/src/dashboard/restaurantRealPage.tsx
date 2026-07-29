import {useEffect, useState} from 'react';
import {UtensilsCrossed, Plus, Receipt, TrendingUp, Bike, Wallet} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Point of sale in practice: menu items priced against a recipe, orders across
// cash / card / delivery platforms, and settlement of what the platforms owe.
//
// The single number that decides whether a kitchen makes money is the food cost
// percentage, so it is surfaced as a KPI with its benchmark, not buried.

type Platform={id:number;code:string;name_ar:string;name_en:string;commission_rate:number};
type MenuItem={id:number;code:string;name_ar:string;name_en:string;selling_price:number;vat_rate?:number};
type Order={id:number;number:string;order_date:string;order_type:string;payment_channel:string;
  subtotal?:number;vat_amount?:number;total?:number;platform_name?:string;settlement_status?:string};
type Item={id:number;code:string;name_ar:string;name_en:string};
type BOM={id:number;code?:string;name_ar?:string;finished_item_id?:number};
type WH={id:number;code:string;name_ar:string;name_en:string};
type Bank={id:number;bank_name_ar?:string;name_ar?:string};

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
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'4px 11px',borderRadius:7,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(185px,1fr))',gap:12,padding:12} as const;

const ORDER_TYPES:[string,string,string][]=[
  ['TAKEAWAY','سفري','Takeaway'],
  ['DINE_IN','صالة','Dine in'],
  ['DELIVERY','توصيل','Delivery'],
];
const CHANNELS:[string,string,string][]=[
  ['CASH','نقدًا','Cash'],
  ['CARD','شبكة / بطاقة','Card'],
  // The backend names this channel DELIVERY; it is what triggers the platform
  // receivable and the settlement flow.
  ['DELIVERY','منصة توصيل','Delivery platform'],
];

export function RestaurantPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'sell'|'menu'|'platforms'|'orders'>('sell');
  const [platforms,setPlatforms]=useState<Platform[]>([]);
  const [menu,setMenu]=useState<MenuItem[]>([]);
  const [orders,setOrders]=useState<Order[]>([]);
  const [items,setItems]=useState<Item[]>([]);
  const [boms,setBoms]=useState<BOM[]>([]);
  const [warehouses,setWarehouses]=useState<WH[]>([]);
  const [banks,setBanks]=useState<Bank[]>([]);
  const [summary,setSummary]=useState<any>(null);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  // sell
  const [oType,setOType]=useState('TAKEAWAY'); const [oChannel,setOChannel]=useState('CASH');
  const [oWh,setOWh]=useState(''); const [oBank,setOBank]=useState(''); const [oPlatform,setOPlatform]=useState('');
  const [cart,setCart]=useState<{menu_item_id:number;quantity:number}[]>([]);
  const [pickItem,setPickItem]=useState(''); const [pickQty,setPickQty]=useState('1');
  // menu item
  const [mCode,setMCode]=useState(''); const [mAr,setMAr]=useState(''); const [mEn,setMEn]=useState('');
  const [mItem,setMItem]=useState(''); const [mBom,setMBom]=useState(''); const [mPrice,setMPrice]=useState('');
  const [mVat,setMVat]=useState('15');
  // platform
  const [plCode,setPlCode]=useState(''); const [plAr,setPlAr]=useState(''); const [plEn,setPlEn]=useState(''); const [plRate,setPlRate]=useState('');

  const load=async()=>{
    try{
      const [pf,mn,or,it,bm,wh,bk,sm]=await Promise.all([
        json(`/api/v1/pos/platforms?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/pos/menu?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/pos/orders?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/items?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/manufacturing/boms?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/pos/summary?company_id=${companyId}`).catch(()=>null),
      ]);
      setPlatforms(Array.isArray(pf)?pf:[]); setMenu(Array.isArray(mn)?mn:[]);
      setOrders(Array.isArray(or)?or:[]); setItems(Array.isArray(it)?it:[]);
      setBoms(Array.isArray(bm)?bm:[]); setWarehouses(Array.isArray(wh)?wh:[]);
      setBanks(Array.isArray(bk)?bk:[]); setSummary(sm);
      if(!oWh&&wh?.length)setOWh(String(wh[0].id));
      if(!oBank&&bk?.length)setOBank(String(bk[0].id));
      if(!pickItem&&mn?.length)setPickItem(String(mn[0].id));
      if(!mItem&&it?.length)setMItem(String(it[0].id));
      if(!mBom&&bm?.length)setMBom(String(bm[0].id));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};

  const addToCart=()=>{
    if(!pickItem||Number(pickQty)<=0)return;
    const id=Number(pickItem), q=Number(pickQty);
    setCart(c=>{
      const i=c.findIndex(x=>x.menu_item_id===id);
      if(i>=0){const n=[...c]; n[i]={...n[i],quantity:n[i].quantity+q}; return n;}
      return [...c,{menu_item_id:id,quantity:q}];
    });
    setPickQty('1');
  };

  const cartTotal=cart.reduce((s,l)=>{
    const m=menu.find(x=>x.id===l.menu_item_id);
    return s+Number(m?.selling_price||0)*l.quantity;
  },0);
  // Menu prices in a restaurant are normally quoted VAT inclusive.
  const cartNet=cartTotal/1.15, cartVat=cartTotal-cartNet;

  const sell=async()=>{
    if(!cart.length){bad({message:ar?'أضف صنفًا واحدًا على الأقل':'Add at least one item'});return;}
    if(!oWh){bad({message:ar?'اختر المستودع':'Pick a warehouse'});return;}
    if(oChannel==='DELIVERY'&&!oPlatform){bad({message:ar?'اختر منصة التوصيل':'Pick the platform'});return;}
    if(oChannel!=='DELIVERY'&&!oBank){bad({message:ar?'اختر الحساب البنكي':'Pick a bank account'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,order_date:iso(),warehouse_id:Number(oWh),
        payment_channel:oChannel,business_unit:'RESTAURANT',order_type:oType,
        lines:cart.map(l=>({menu_item_id:l.menu_item_id,quantity:l.quantity}))};
      if(oChannel==='DELIVERY')body.platform_id=Number(oPlatform);
      else body.bank_account_id=Number(oBank);
      const r=await json('/api/v1/pos/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(ar?`تم تسجيل الطلب ${r.number||''} — الإجمالي ${fmt(Number(r.total||cartTotal))}`
           :`Order ${r.number||''} recorded — total ${fmt(Number(r.total||cartTotal))}`);
      setCart([]); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const createMenuItem=async()=>{
    if(!mCode||!mAr||!mEn||!mItem||!mBom||!mPrice){bad({message:ar?'أكمل البيانات — الوصفة إلزامية لحساب التكلفة':'Complete the fields — the recipe is required for costing'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/pos/menu',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,code:mCode,name_ar:mAr,name_en:mEn,
          inventory_item_id:Number(mItem),recipe_bom_id:Number(mBom),
          selling_price:Number(mPrice),vat_rate:Number(mVat)})});
      ok(ar?`تمت إضافة ${mAr} للقائمة`:`${mEn} added to the menu`);
      setMCode('');setMAr('');setMEn('');setMPrice(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const createPlatform=async()=>{
    if(!plCode||!plAr||!plEn||plRate===''){bad({message:ar?'أكمل بيانات المنصة':'Complete the platform'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/pos/platforms',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,code:plCode,name_ar:plAr,name_en:plEn,commission_rate:Number(plRate)})});
      ok(ar?`تمت إضافة ${plAr} بعمولة ${plRate}%`:`${plEn} added at ${plRate}% commission`);
      setPlCode('');setPlAr('');setPlEn('');setPlRate(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const settle=async(id:number)=>{
    if(!oBank){bad({message:ar?'اختر حسابًا بنكيًا أولًا من تبويب البيع':'Pick a bank account in the sell tab first'});return;}
    setBusy(true);setMsg('');
    try{
      await json(`/api/v1/pos/orders/${id}/settle`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({settlement_date:iso(),bank_account_id:Number(oBank)})});
      ok(ar?'تمت تسوية مستحقات المنصة':'Platform settlement recorded'); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const fcPercent=Number(summary?.food_cost_percent||0);
  const fcGood=fcPercent>0&&fcPercent<=35;

  return <>
    <div className="kpis">
      <Kpi title={ar?'صافي المبيعات':'Net sales'} value={summary?fmt(Number(summary.net_sales||0)):'—'} trend={`${summary?.orders??0} ${ar?'طلبًا':'orders'}`} good icon={<Receipt size={22}/>} tone="blue"/>
      <Kpi title={ar?'تكلفة الطعام':'Food cost'} value={summary?fmt(Number(summary.food_cost||0)):'—'} trend="" good icon={<UtensilsCrossed size={22}/>} tone="violet"/>
      <Kpi title={ar?'نسبة تكلفة الطعام':'Food cost %'} value={`${fcPercent.toFixed(1)}%`} trend={ar?'المعيار ٢٨-٣٥٪':'target 28-35%'} good={fcGood} icon={<TrendingUp size={22}/>} tone={fcGood?'green':'amber'}/>
      <Kpi title={ar?'مستحق من المنصات':'Due from platforms'} value={summary?fmt(Number(summary.pending_settlements||0)):'—'} trend="" good={(summary?.pending_settlements||0)===0} icon={<Bike size={22}/>} tone="amber"/>
    </div>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['sell',ar?'شاشة البيع':'Sell'],['menu',ar?'قائمة الطعام':'Menu'],
         ['platforms',ar?'منصات التوصيل':'Platforms'],['orders',ar?'الطلبات':'Orders']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>setTab(k)}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.9,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab==='sell'&&<>
      {menu.length===0
        ? <Panel title={ar?'ابدأ من القائمة':'Start with the menu'} icon={<UtensilsCrossed size={18}/>}>
            <div style={{padding:16,fontSize:14,lineHeight:1.9}}>
              {ar?'لا توجد أصناف في قائمة الطعام. أضف صنفًا من تبويب «قائمة الطعام» أولًا — كل صنف يحتاج وصفة لحساب تكلفته وخصم مكوّناته من المخزون.'
                 :'The menu is empty. Add an item first - each one needs a recipe so its cost is known and its components leave stock.'}
            </div>
          </Panel>
        : <>
          <Panel title={ar?'طلب جديد':'New order'} icon={<Receipt size={18}/>}>
            <div style={grid}>
              <label>{ar?'نوع الطلب':'Order type'}<select style={field} value={oType} onChange={e=>setOType(e.target.value)}>
                {ORDER_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
              <label>{ar?'قناة الدفع':'Payment channel'}<select style={field} value={oChannel} onChange={e=>setOChannel(e.target.value)}>
                {CHANNELS.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
              {oChannel==='DELIVERY'
                ? <label>{ar?'المنصة':'Platform'}<select style={field} value={oPlatform} onChange={e=>setOPlatform(e.target.value)}>
                    <option value="">{ar?'اختر...':'Select...'}</option>
                    {platforms.map(p=><option key={p.id} value={p.id}>{ar?p.name_ar:p.name_en} — {p.commission_rate}%</option>)}</select></label>
                : <label>{ar?'الحساب البنكي':'Bank account'}<select style={field} value={oBank} onChange={e=>setOBank(e.target.value)}>
                    {banks.map(b=><option key={b.id} value={b.id}>{b.bank_name_ar||b.name_ar||`#${b.id}`}</option>)}</select></label>}
              <label>{ar?'المستودع':'Warehouse'}<select style={field} value={oWh} onChange={e=>setOWh(e.target.value)}>
                {warehouses.map(w=><option key={w.id} value={w.id}>{w.code} — {ar?w.name_ar:w.name_en}</option>)}</select></label>
            </div>
            <div style={{...grid,paddingTop:0,alignItems:'end'}}>
              <label>{ar?'الصنف':'Menu item'}<select style={field} value={pickItem} onChange={e=>setPickItem(e.target.value)}>
                {menu.map(m=><option key={m.id} value={m.id}>{ar?m.name_ar:m.name_en} — {fmt(Number(m.selling_price||0))}</option>)}</select></label>
              <label>{ar?'الكمية':'Qty'}<input type="number" min="1" step="1" style={field} value={pickQty} onChange={e=>setPickQty(e.target.value)}/></label>
              <button style={{...btn,background:'transparent',color:'var(--text)',border:'1px solid var(--border)'}} onClick={addToCart}>
                <Plus size={15}/> {ar?'إضافة للطلب':'Add'}
              </button>
            </div>
          </Panel>
          <Panel title={ar?'محتوى الطلب':'Order contents'} icon={<Wallet size={18}/>}>
            {cart.length===0
              ? <div style={{padding:16,fontSize:14,opacity:0.8}}>{ar?'الطلب فارغ.':'The order is empty.'}</div>
              : <>
                <DataTable headers={[ar?'الصنف':'Item',ar?'الكمية':'Qty',ar?'السعر':'Price',ar?'الإجمالي':'Line total',ar?'':'']}
                  rows={cart.map((l,idx)=>{
                    const m=menu.find(x=>x.id===l.menu_item_id);
                    return [ar?(m?.name_ar||''):(m?.name_en||''),String(l.quantity),
                      fmt(Number(m?.selling_price||0)),fmt(Number(m?.selling_price||0)*l.quantity),
                      <button key={idx} style={{...smallBtn,background:'#b91c1c'}}
                        onClick={()=>setCart(c=>c.filter((_,i)=>i!==idx))}>{ar?'حذف':'Remove'}</button>];
                  })}/>
                <div style={{padding:14,display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))',gap:12}}>
                  <div><small style={{opacity:0.75}}>{ar?'الصافي':'Net'}</small><div style={{fontWeight:700,fontSize:18}}>{fmt(cartNet)}</div></div>
                  <div><small style={{opacity:0.75}}>{ar?'الضريبة ١٥٪':'VAT 15%'}</small><div style={{fontWeight:700,fontSize:18}}>{fmt(cartVat)}</div></div>
                  <div><small style={{opacity:0.75}}>{ar?'الإجمالي':'Total'}</small><div style={{fontWeight:700,fontSize:20,color:'#166534'}}>{fmt(cartTotal)}</div></div>
                </div>
                <div style={{padding:'0 14px 16px',fontSize:12,opacity:0.7}}>
                  {ar?'الأسعار المعروضة شاملة الضريبة، والصافي محسوب بقسمتها على ١٫١٥.':'Prices are VAT inclusive; the net is the price divided by 1.15.'}
                </div>
                <div style={{padding:'0 14px 16px'}}>
                  <button style={{...btn,background:'#166534',opacity:busy?0.6:1}} disabled={busy} onClick={sell}>
                    {ar?`تأكيد الطلب — ${fmt(cartTotal)}`:`Confirm — ${fmt(cartTotal)}`}
                  </button>
                </div>
              </>}
          </Panel>
        </>}
    </>}

    {tab==='menu'&&<>
      <Panel title={ar?'صنف جديد في القائمة':'New menu item'} icon={<Plus size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'كل صنف مرتبط بوصفة (قائمة مواد) وبصنف مخزني. الوصفة تحدد تكلفة الطبق وتخصم مكوّناته من المخزون عند البيع — بدونها تبيع بلا معرفة ربحك.'
            : 'Every menu item links to a recipe (BOM) and a stock item. The recipe drives the plate cost and removes the components from stock on sale.'}
        </div>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={mCode} onChange={e=>setMCode(e.target.value)} placeholder="MENU-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={mAr} onChange={e=>setMAr(e.target.value)} placeholder={ar?'وجبة دجاج مشوي':''}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={mEn} onChange={e=>setMEn(e.target.value)}/></label>
          <label>{ar?'الصنف المخزني':'Stock item'}<select style={field} value={mItem} onChange={e=>setMItem(e.target.value)}>
            {items.map(i=><option key={i.id} value={i.id}>{i.code} — {ar?i.name_ar:i.name_en}</option>)}</select></label>
          <label>{ar?'الوصفة':'Recipe (BOM)'}<select style={field} value={mBom} onChange={e=>setMBom(e.target.value)}>
            {boms.map(b=><option key={b.id} value={b.id}>{b.code||b.name_ar||`BOM ${b.id}`}</option>)}</select></label>
          <label>{ar?'سعر البيع (شامل الضريبة)':'Selling price (VAT incl.)'}<input type="number" step="0.01" style={field} value={mPrice} onChange={e=>setMPrice(e.target.value)}/></label>
          <label>{ar?'الضريبة %':'VAT %'}<input type="number" style={field} value={mVat} onChange={e=>setMVat(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createMenuItem}>{ar?'إضافة للقائمة':'Add to menu'}</button>
        </div>
      </Panel>
      <Panel title={ar?'قائمة الطعام':'Menu'} icon={<UtensilsCrossed size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'السعر':'Price',ar?'الضريبة':'VAT']}
          rows={menu.map(m=>[m.code,ar?m.name_ar:m.name_en,fmt(Number(m.selling_price||0)),`${m.vat_rate??15}%`])}/>
      </Panel>
    </>}

    {tab==='platforms'&&<>
      <Panel title={ar?'منصة توصيل جديدة':'New delivery platform'} icon={<Bike size={18}/>}>
        <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
          {ar
            ? 'العمولة تُسجَّل مصروفًا عند كل طلب، والباقي يُقيَّد ذمة على المنصة حتى التسوية. راقبها: عمولة تتجاوز ٢٥٪ قد تجعل ربحك من المنصة سالبًا بعد تكلفة الطعام.'
            : 'The commission is expensed on each order and the remainder sits as a receivable until settlement. Above 25% the platform channel can turn loss making once food cost is counted.'}
        </div>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={plCode} onChange={e=>setPlCode(e.target.value)} placeholder="PLT-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={plAr} onChange={e=>setPlAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={plEn} onChange={e=>setPlEn(e.target.value)}/></label>
          <label>{ar?'نسبة العمولة %':'Commission %'}<input type="number" step="0.1" style={field} value={plRate} onChange={e=>setPlRate(e.target.value)}/>
            {Number(plRate)>25&&<small style={{color:'#b45309'}}>{ar?'⚠ عمولة مرتفعة — راجع ربحية هذه القناة':'⚠ high commission'}</small>}</label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createPlatform}>{ar?'إضافة المنصة':'Add platform'}</button>
        </div>
      </Panel>
      <Panel title={ar?'المنصات':'Platforms'} icon={<Bike size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'العمولة':'Commission',ar?'التقييم':'Assessment']}
          rows={platforms.map(p=>[p.code,ar?p.name_ar:p.name_en,`${p.commission_rate}%`,
            Number(p.commission_rate)>25?(ar?'مرتفعة':'High'):(ar?'مقبولة':'Acceptable')])}/>
      </Panel>
    </>}

    {tab==='orders'&&<Panel title={ar?'الطلبات':'Orders'} icon={<Receipt size={18}/>}>
      <DataTable headers={[ar?'الرقم':'No.',ar?'التاريخ':'Date',ar?'النوع':'Type',ar?'القناة':'Channel',
        ar?'الصافي':'Net',ar?'الضريبة':'VAT',ar?'الإجمالي':'Total',ar?'إجراء':'Action']}
        rows={orders.map(o=>[o.number,o.order_date,
          (ORDER_TYPES.find(t=>t[0]===o.order_type)||[])[ar?1:2]||o.order_type,
          o.platform_name||((CHANNELS.find(c=>c[0]===o.payment_channel)||[])[ar?1:2]||o.payment_channel),
          fmt(Number(o.subtotal||0)),fmt(Number(o.vat_amount||0)),fmt(Number(o.total||0)),
          (o.payment_channel==='DELIVERY'&&o.settlement_status!=='SETTLED')
            ? <button key={o.id} style={smallBtn} disabled={busy} onClick={()=>settle(o.id)}>{ar?'تسوية':'Settle'}</button>
            : '—'])}/>
    </Panel>}
  </>;
}
