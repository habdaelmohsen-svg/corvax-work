import {useEffect, useMemo, useState} from 'react';
import {BadgePercent, Boxes, CheckCircle2, Download, Factory, FileCheck2, Landmark, PackageCheck, ShieldCheck, Warehouse as WarehouseIcon} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, MiniStatus, Panel, money} from './ui';

type Warehouse={id:number;code:string;name_ar:string;name_en:string};
type Item={id:number;code:string;name_ar:string;name_en:string;uom:string;active:boolean};
type Bank={id:number;code:string;bank_name_ar:string;bank_name_en:string;gl_account_code:string};
type Category={id:number;code:string;name_ar:string;name_en:string;statutory_rate:number;tariff_reference?:string};
type Profile={id:number;warehouse_id:number;warehouse_code:string;warehouse_name_ar:string;warehouse_name_en:string;license_number:string;license_start_date:string;license_expiry_date:string;permitted_activities:string;bank_guarantee_amount:number;estimated_monthly_excise_value:number;minimum_guarantee_indicator:number;guarantee_indicator_sufficient:boolean;status:string};
type Product={id:number;item_id:number;item_code:string;item_name_ar:string;item_name_en:string;category_id:number;category_code:string;category_name_ar:string;category_name_en:string;excise_rate:number;registered_retail_price:number;indicative_price:number;taxable_unit_value:number;package_quantity:number;package_uom:string;tax_stamp_required:boolean};
type Movement={id:number;number:string;movement_date:string;event_type:string;item_code:string;item_name_ar:string;item_name_en:string;category_code:string;warehouse_code?:string;destination_warehouse_code?:string;quantity:number;taxable_value:number;excise_rate:number;excise_amount:number;customs_excise_paid:number;tax_settlement_method:string;status:string;journal_id?:number};
type StockRow={warehouse_profile_id:number;warehouse_code:string;warehouse_name_ar:string;warehouse_name_en:string;product_id:number;item_code:string;item_name_ar:string;item_name_en:string;category_code:string;quantity:number;uom:string;estimated_excise_exposure:number};
type Stock={as_of:string;rows:StockRow[];total_estimated_excise_exposure:number};
type ExciseReturn={id:number;number:string;period_start:string;period_end:string;due_date:string;status:string;taxable_value:number;gross_excise:number;customs_paid:number;tax_payable:number;gl_payable:number;reconciliation_difference:number;estimated_late_penalty:number;sadad_invoice_number?:string;payment_date?:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
async function download(url:string,filename:string){
  const r=await apiFetch(url); if(!r.ok) throw new Error('Export failed');
  const blob=await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename; a.click(); URL.revokeObjectURL(a.href);
}
const fieldStyle={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9};
function twoMonthBounds(value:string){
  let [year,month]=value.split('-').map(Number); if(month%2===0) month-=1;
  const start=`${year}-${String(month).padStart(2,'0')}-01`;
  const endDate=new Date(Date.UTC(year,month+1,0));
  const end=endDate.toISOString().slice(0,10);
  return {start,end,label:`${year}-${String(month).padStart(2,'0')}`};
}

export function ExciseTaxPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date().toISOString().slice(0,10); const defaultPeriod=twoMonthBounds(today.slice(0,7)).label;
  const [warehouses,setWarehouses]=useState<Warehouse[]>([]); const [items,setItems]=useState<Item[]>([]); const [banks,setBanks]=useState<Bank[]>([]);
  const [categories,setCategories]=useState<Category[]>([]); const [profiles,setProfiles]=useState<Profile[]>([]); const [products,setProducts]=useState<Product[]>([]);
  const [movements,setMovements]=useState<Movement[]>([]); const [returns,setReturns]=useState<ExciseReturn[]>([]); const [stock,setStock]=useState<Stock>({as_of:today,rows:[],total_estimated_excise_exposure:0});
  const [warehouseId,setWarehouseId]=useState(''); const [licenseNumber,setLicenseNumber]=useState('EXW-LIC-001'); const [licenseStart,setLicenseStart]=useState(`${today.slice(0,4)}-01-01`); const [licenseExpiry,setLicenseExpiry]=useState(`${Number(today.slice(0,4))+1}-12-31`); const [activities,setActivities]=useState('PRODUCE,STORE,RECEIVE,TRANSFER'); const [guarantee,setGuarantee]=useState('0'); const [monthlyExposure,setMonthlyExposure]=useState('0');
  const [itemId,setItemId]=useState(''); const [categoryId,setCategoryId]=useState(''); const [retailPrice,setRetailPrice]=useState('10'); const [indicativePrice,setIndicativePrice]=useState('0'); const [hsCode,setHsCode]=useState(''); const [stampRequired,setStampRequired]=useState(false);
  const [productId,setProductId]=useState(''); const [sourceProfileId,setSourceProfileId]=useState(''); const [destinationProfileId,setDestinationProfileId]=useState(''); const [eventType,setEventType]=useState('PRODUCTION'); const [settlement,setSettlement]=useState('SUSPENDED'); const [quantity,setQuantity]=useState('100'); const [movementDate,setMovementDate]=useState(today); const [debitAccount,setDebitAccount]=useState('624120'); const [bankId,setBankId]=useState(''); const [customsDeclaration,setCustomsDeclaration]=useState(''); const [customsPaid,setCustomsPaid]=useState('0'); const [description,setDescription]=useState('Excise movement');
  const [returnPeriod,setReturnPeriod]=useState(defaultPeriod); const [returnBankId,setReturnBankId]=useState(''); const [sadad,setSadad]=useState(''); const [paymentReference,setPaymentReference]=useState(''); const [paymentDate,setPaymentDate]=useState(today);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);

  const load=async()=>{
    try{
      const [w,i,b,c,wp,p,m,r,s]=await Promise.all([
        json(`/api/v1/inventory/warehouses?company_id=${companyId}`),
        json(`/api/v1/inventory/items?company_id=${companyId}`),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`),
        json(`/api/v1/excise-tax/categories?company_id=${companyId}`),
        json(`/api/v1/excise-tax/warehouse-profiles?company_id=${companyId}`),
        json(`/api/v1/excise-tax/products?company_id=${companyId}`),
        json(`/api/v1/excise-tax/movements?company_id=${companyId}`),
        json(`/api/v1/excise-tax/returns?company_id=${companyId}`),
        json(`/api/v1/excise-tax/stock?company_id=${companyId}`),
      ]);
      setWarehouses(w||[]);setItems((i||[]).filter((x:Item)=>x.active!==false));setBanks(b||[]);setCategories(c||[]);setProfiles(wp||[]);setProducts(p||[]);setMovements(m||[]);setReturns(r||[]);setStock(s||{as_of:today,rows:[],total_estimated_excise_exposure:0});
      if(!warehouseId&&w?.length)setWarehouseId(String(w[0].id)); if(!itemId&&i?.length)setItemId(String(i[0].id)); if(!categoryId&&c?.length)setCategoryId(String(c[0].id));
      if(!sourceProfileId&&wp?.length)setSourceProfileId(String(wp[0].id)); if(!productId&&p?.length)setProductId(String(p[0].id));
      if(!bankId&&b?.length){setBankId(String(b[0].id));setReturnBankId(String(b[0].id));}
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{if(eventType==='RELEASE_CONSUMPTION'||eventType==='SELF_CONSUMPTION'||eventType==='UNEXPLAINED_LOSS')setSettlement('PAYABLE');else if(eventType==='IMPORT_RECEIPT')setSettlement('SUSPENDED');else setSettlement('SUSPENDED');},[eventType]);

  const activeProfiles=profiles.filter(x=>x.status==='ACTIVE');
  const approvedTax=movements.filter(x=>x.status==='APPROVED_POSTED').reduce((s,x)=>s+Number(x.excise_amount||0),0);
  const pending=movements.filter(x=>x.status==='PENDING_APPROVAL').length;
  const unpaidReturn=returns.find(x=>x.status==='APPROVED'&&Number(x.tax_payable)>0);
  const selectedCategory=useMemo(()=>categories.find(x=>String(x.id)===categoryId),[categories,categoryId]);

  async function saveProfile(){
    if(!warehouseId){setMessage(ar?'اختر المستودع.':'Select a warehouse.');return;} setBusy(true);setMessage('');
    try{await json('/api/v1/excise-tax/warehouse-profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,warehouse_id:Number(warehouseId),license_number:licenseNumber,license_start_date:licenseStart,license_expiry_date:licenseExpiry,permitted_activities:activities,bank_guarantee_amount:Number(guarantee),estimated_monthly_excise_value:Number(monthlyExposure),status:'ACTIVE',notes:null})});setMessage(ar?'تم حفظ ملف المستودع الضريبي.':'Tax warehouse profile saved.');await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function saveProduct(){
    if(!itemId||!categoryId){setMessage(ar?'اختر الصنف والفئة الانتقائية.':'Select item and excise category.');return;} setBusy(true);setMessage('');
    try{await json('/api/v1/excise-tax/products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,item_id:Number(itemId),category_id:Number(categoryId),hs_code:hsCode||null,zatca_registration_reference:null,registered_retail_price:Number(retailPrice),indicative_price:Number(indicativePrice),package_quantity:1,package_uom:'EA',tax_stamp_required:stampRequired})});setMessage(ar?'تم تسجيل الصنف الانتقائي.':'Excise product registered.');await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function createMovement(){
    if(!productId||!sourceProfileId){setMessage(ar?'اختر المنتج والمستودع الضريبي.':'Select product and tax warehouse.');return;} setBusy(true);setMessage('');
    try{const payload={company_id:companyId,movement_date:movementDate,event_type:eventType,product_id:Number(productId),warehouse_profile_id:Number(sourceProfileId),destination_warehouse_profile_id:eventType==='TRANSFER_SUSPENDED'&&destinationProfileId?Number(destinationProfileId):null,quantity:Number(quantity),tax_settlement_method:settlement,customs_declaration_number:customsDeclaration||null,customs_excise_paid:Number(customsPaid),debit_account_code:(settlement==='PAYABLE'||settlement==='CUSTOMS_PAID')?debitAccount:null,bank_account_id:settlement==='CUSTOMS_PAID'?Number(bankId):null,reference:null,description};const x=await json('/api/v1/excise-tax/movements',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});setMessage(`${ar?'تم إنشاء الحركة':'Movement created'}: ${x.number}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function movementAction(id:number,action:'submit'|'approve-post'){
    setBusy(true);setMessage('');try{const x=await json(`/api/v1/excise-tax/movements/${id}/${action}`,{method:'POST'});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function generateReturn(){
    const bounds=twoMonthBounds(returnPeriod);setBusy(true);setMessage('');try{const x=await json('/api/v1/excise-tax/returns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,period_start:bounds.start,period_end:bounds.end})});setMessage(`${ar?'تم إنشاء الإقرار':'Return generated'}: ${x.number}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function returnAction(id:number,action:'submit'|'approve'){
    setBusy(true);setMessage('');try{const x=await json(`/api/v1/excise-tax/returns/${id}/${action}`,{method:'POST'});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function payReturn(){
    if(!unpaidReturn||!returnBankId||!sadad||!paymentReference){setMessage(ar?'أكمل بيانات السداد.':'Complete payment details.');return;}setBusy(true);setMessage('');try{const x=await json(`/api/v1/excise-tax/returns/${unpaidReturn.id}/pay`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bank_account_id:Number(returnBankId),payment_date:paymentDate,sadad_invoice_number:sadad,payment_reference:paymentReference})});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }

  return <>
    <div className="page-title"><div><h2>{ar?'الضريبة الانتقائية والمستودعات الضريبية':'Excise Tax & Tax Warehouses'}</h2><p>{ar?'إدارة المنتجات الانتقائية والتعليق الضريبي والإفراج والإقرار ثنائي الشهر.':'Manage excise goods, tax suspension, releases and bi-monthly returns.'}</p></div></div>
    <div className="kpi-grid">
      <Kpi icon={<WarehouseIcon/>} title={ar?'المستودعات الضريبية':'Tax warehouses'} value={String(profiles.length)} trend={ar?'ملفات ترخيص مسجلة':'Registered licence profiles'} good={profiles.length>0}/>
      <Kpi icon={<PackageCheck/>} title={ar?'المنتجات الانتقائية':'Excise products'} value={String(products.length)} trend={ar?'مرتبطة بالفئات والأسعار':'Linked to categories and prices'} good={products.length>0} tone="green"/>
      <Kpi icon={<BadgePercent/>} title={ar?'ضريبة الحركات المعتمدة':'Approved movement tax'} value={money.format(approvedTax)} trend={ar?'قبل تسويات الإقرار':'Before return settlement'} good={true} tone="amber"/>
      <Kpi icon={<FileCheck2/>} title={ar?'حركات بانتظار الاعتماد':'Pending approvals'} value={String(pending)} trend="Maker–Checker" good={pending===0} tone="violet"/>
    </div>

    <div className="two-columns wide-left">
      <Panel title={ar?'ترخيص المستودع الضريبي':'Tax warehouse licence profile'} icon={<WarehouseIcon size={18}/> }>
        <div className="journal-form" style={{gridTemplateColumns:'repeat(3,minmax(0,1fr))'}}>
          <label>{ar?'المستودع':'Warehouse'}<select value={warehouseId} onChange={e=>setWarehouseId(e.target.value)} style={fieldStyle}>{warehouses.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}</select></label>
          <label>{ar?'رقم الترخيص':'Licence number'}<input value={licenseNumber} onChange={e=>setLicenseNumber(e.target.value)}/></label>
          <label>{ar?'الأنشطة المصرح بها':'Permitted activities'}<input value={activities} onChange={e=>setActivities(e.target.value)}/></label>
          <label>{ar?'بداية الترخيص':'Licence start'}<input type="date" value={licenseStart} onChange={e=>setLicenseStart(e.target.value)}/></label>
          <label>{ar?'نهاية الترخيص':'Licence expiry'}<input type="date" value={licenseExpiry} onChange={e=>setLicenseExpiry(e.target.value)}/></label>
          <label>{ar?'الضمان البنكي':'Bank guarantee'}<input type="number" min="0" step="0.01" value={guarantee} onChange={e=>setGuarantee(e.target.value)}/></label>
          <label>{ar?'القيمة الانتقائية الشهرية التقديرية':'Estimated monthly excise value'}<input type="number" min="0" step="0.01" value={monthlyExposure} onChange={e=>setMonthlyExposure(e.target.value)}/></label>
        </div>
        <div className="journal-footer"><span>{message|| (ar?'مؤشر الضمان رقابي ولا يغني عن متطلبات الترخيص الرسمية.':'Guarantee indicator is an internal control, not a licence determination.')}</span><button disabled={busy||!warehouses.length} onClick={saveProfile}>{ar?'حفظ الملف':'Save profile'}</button></div>
      </Panel>
      <Panel title={ar?'الرقابة النظامية':'Compliance controls'} icon={<ShieldCheck size={18}/> }>
        <MiniStatus icon={<BadgePercent size={18}/>} title={ar?'الفئات':'Categories'} value="50% / 100%" status={ar?'حسب فئة السلعة':'By goods category'}/>
        <MiniStatus icon={<CheckCircle2 size={18}/>} title="Maker–Checker" value={ar?'مفعّل':'Active'} status={ar?'المُعد لا يعتمد':'Maker cannot approve'}/>
        <MiniStatus icon={<FileCheck2 size={18}/>} title={ar?'دورية الإقرار':'Return cycle'} value={ar?'شهران':'Two months'} status={ar?'آخر يوم من الشهر التالي':'Last day of following month'}/>
      </Panel>
    </div>

    <Panel title={ar?'تسجيل منتج خاضع للضريبة الانتقائية':'Register excise product'} icon={<Boxes size={18}/> }>
      <div className="journal-form" style={{gridTemplateColumns:'repeat(4,minmax(0,1fr))'}}>
        <label>{ar?'الصنف':'Item'}<select value={itemId} onChange={e=>setItemId(e.target.value)} style={fieldStyle}>{items.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}</select></label>
        <label>{ar?'الفئة الانتقائية':'Excise category'}<select value={categoryId} onChange={e=>setCategoryId(e.target.value)} style={fieldStyle}>{categories.map(x=><option key={x.id} value={x.id}>{ar?x.name_ar:x.name_en} — {Number(x.statutory_rate)}%</option>)}</select></label>
        <label>{ar?'سعر البيع بالتجزئة المسجل':'Registered retail price'}<input type="number" min="0" step="0.01" value={retailPrice} onChange={e=>setRetailPrice(e.target.value)}/></label>
        <label>{ar?'السعر الاسترشادي':'Indicative price'}<input type="number" min="0" step="0.01" value={indicativePrice} onChange={e=>setIndicativePrice(e.target.value)}/></label>
        <label>{ar?'رمز HS':'HS code'}<input value={hsCode} onChange={e=>setHsCode(e.target.value)}/></label>
        <label><input type="checkbox" checked={stampRequired} onChange={e=>setStampRequired(e.target.checked)}/> {ar?'يتطلب ختمًا ضريبيًا':'Tax stamp required'}</label>
      </div>
      <div className="journal-footer"><span>{selectedCategory?`${ar?selectedCategory.name_ar:selectedCategory.name_en}: ${selectedCategory.statutory_rate}%`:message}</span><button disabled={busy||!items.length||!categories.length} onClick={saveProduct}>{ar?'تسجيل المنتج':'Register product'}</button></div>
    </Panel>

    <Panel title={ar?'حركة المستودع الضريبي':'Tax warehouse movement'} icon={<Factory size={18}/> }>
      <div className="journal-form" style={{gridTemplateColumns:'repeat(4,minmax(0,1fr))'}}>
        <label>{ar?'المنتج':'Product'}<select value={productId} onChange={e=>setProductId(e.target.value)} style={fieldStyle}>{products.map(x=><option key={x.id} value={x.id}>{x.item_code} — {ar?x.item_name_ar:x.item_name_en}</option>)}</select></label>
        <label>{ar?'نوع الحركة':'Event'}<select value={eventType} onChange={e=>setEventType(e.target.value)} style={fieldStyle}><option value="PRODUCTION">PRODUCTION</option><option value="IMPORT_RECEIPT">IMPORT_RECEIPT</option><option value="TRANSFER_SUSPENDED">TRANSFER_SUSPENDED</option><option value="RELEASE_CONSUMPTION">RELEASE_CONSUMPTION</option><option value="SELF_CONSUMPTION">SELF_CONSUMPTION</option><option value="EXPORT">EXPORT</option><option value="AUTHORIZED_DESTRUCTION">AUTHORIZED_DESTRUCTION</option><option value="UNEXPLAINED_LOSS">UNEXPLAINED_LOSS</option><option value="RETURN_TO_SUSPENSION">RETURN_TO_SUSPENSION</option></select></label>
        <label>{ar?'مستودع المصدر':'Source warehouse'}<select value={sourceProfileId} onChange={e=>setSourceProfileId(e.target.value)} style={fieldStyle}>{activeProfiles.map(x=><option key={x.id} value={x.id}>{x.warehouse_code} — {ar?x.warehouse_name_ar:x.warehouse_name_en}</option>)}</select></label>
        <label>{ar?'مستودع الوجهة':'Destination warehouse'}<select value={destinationProfileId} onChange={e=>setDestinationProfileId(e.target.value)} style={fieldStyle}><option value="">—</option>{activeProfiles.filter(x=>String(x.id)!==sourceProfileId).map(x=><option key={x.id} value={x.id}>{x.warehouse_code} — {ar?x.warehouse_name_ar:x.warehouse_name_en}</option>)}</select></label>
        <label>{ar?'الكمية':'Quantity'}<input type="number" min="0.0001" step="0.0001" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
        <label>{ar?'التاريخ':'Date'}<input type="date" value={movementDate} onChange={e=>setMovementDate(e.target.value)}/></label>
        <label>{ar?'التسوية الضريبية':'Tax settlement'}<select value={settlement} onChange={e=>setSettlement(e.target.value)} style={fieldStyle}><option value="SUSPENDED">SUSPENDED</option><option value="PAYABLE">PAYABLE</option><option value="CUSTOMS_PAID">CUSTOMS_PAID</option><option value="EXEMPT">EXEMPT</option></select></label>
        <label>{ar?'الحساب المدين':'Debit account'}<input value={debitAccount} onChange={e=>setDebitAccount(e.target.value)}/></label>
        <label>{ar?'رقم البيان الجمركي':'Customs declaration'}<input value={customsDeclaration} onChange={e=>setCustomsDeclaration(e.target.value)}/></label>
        <label>{ar?'ضريبة مسددة في الجمارك':'Excise paid at customs'}<input type="number" min="0" step="0.01" value={customsPaid} onChange={e=>setCustomsPaid(e.target.value)}/></label>
        <label>{ar?'البنك':'Bank'}<select value={bankId} onChange={e=>setBankId(e.target.value)} style={fieldStyle}><option value="">—</option>{banks.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.bank_name_ar:x.bank_name_en}</option>)}</select></label>
        <label>{ar?'الوصف':'Description'}<input value={description} onChange={e=>setDescription(e.target.value)}/></label>
      </div>
      <div className="journal-footer"><span>{ar?'الإفراج والاستهلاك الذاتي والفقد غير المبرر تنشئ التزام الضريبة عند الاعتماد.':'Release, self-consumption and unexplained loss create excise liability on approval.'}</span><button disabled={busy||!products.length||!activeProfiles.length} onClick={createMovement}>{ar?'إنشاء الحركة':'Create movement'}</button></div>
    </Panel>

    <Panel title={ar?'سجل حركات الضريبة الانتقائية':'Excise movement register'} icon={<Landmark size={18}/> }>
      <div className="journal-footer"><span>{message}</span><button onClick={()=>download(`/api/v1/excise-tax/export/movements.csv?company_id=${companyId}`,'excise_movements.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>
      <DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'الحركة':'Event',ar?'الصنف':'Item',ar?'المستودع':'Warehouse',ar?'الكمية':'Qty',ar?'الوعاء':'Taxable value',ar?'الضريبة':'Excise',ar?'التسوية':'Settlement',ar?'الحالة/الإجراء':'Status / action']} rows={movements.map(x=>[x.number,x.movement_date,x.event_type,x.item_code,x.destination_warehouse_code?`${x.warehouse_code} → ${x.destination_warehouse_code}`:x.warehouse_code,x.quantity,money.format(Number(x.taxable_value)),money.format(Number(x.excise_amount)),x.tax_settlement_method,<span key={x.id}>{x.status}{x.status==='DRAFT'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>movementAction(x.id,'submit')}>{ar?'إرسال':'Submit'}</button>}{x.status==='PENDING_APPROVAL'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>movementAction(x.id,'approve-post')}>{ar?'اعتماد وترحيل':'Approve & post'}</button>}</span>])}/>
    </Panel>

    <div className="two-columns wide-left">
      <Panel title={ar?'مخزون المستودع الضريبي':'Tax warehouse stock'} icon={<Boxes size={18}/> }>
        <div className="journal-footer"><span>{`${ar?'التعرض الانتقائي التقديري':'Estimated excise exposure'}: ${money.format(Number(stock.total_estimated_excise_exposure||0))}`}</span><button onClick={()=>download(`/api/v1/excise-tax/export/stock.csv?company_id=${companyId}`,'excise_tax_warehouse_stock.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>
        <DataTable headers={[ar?'المستودع':'Warehouse',ar?'الصنف':'Item',ar?'الفئة':'Category',ar?'الكمية':'Quantity',ar?'الوحدة':'UOM',ar?'التعرض التقديري':'Estimated exposure']} rows={stock.rows.map(x=>[x.warehouse_code,x.item_code,x.category_code,x.quantity,x.uom,money.format(Number(x.estimated_excise_exposure))])}/>
      </Panel>
      <Panel title={ar?'مؤشرات تراخيص المستودعات':'Warehouse licence indicators'} icon={<ShieldCheck size={18}/> }>
        {profiles.length?profiles.map(x=><MiniStatus key={x.id} icon={<WarehouseIcon size={18}/>} title={`${x.warehouse_code} — ${x.license_number}`} value={x.status} status={`${ar?'الضمان':'Guarantee'} ${money.format(Number(x.bank_guarantee_amount))} / ${money.format(Number(x.minimum_guarantee_indicator))}`}/>):<p>{ar?'لا توجد ملفات مستودعات ضريبية.':'No tax warehouse profiles.'}</p>}
      </Panel>
    </div>

    <div className="two-columns wide-left">
      <Panel title={ar?'إنشاء الإقرار ثنائي الشهر':'Generate bi-monthly excise return'} icon={<FileCheck2 size={18}/> }>
        <div className="journal-form" style={{gridTemplateColumns:'repeat(2,minmax(0,1fr))'}}><label>{ar?'شهر بداية الفترة':'Period start month'}<input type="month" value={returnPeriod} onChange={e=>setReturnPeriod(e.target.value)}/></label><label>{ar?'الفترة المحسوبة':'Calculated period'}<input disabled value={`${twoMonthBounds(returnPeriod).start} → ${twoMonthBounds(returnPeriod).end}`}/></label></div>
        <div className="journal-footer"><span>{ar?'يُنشأ الإقرار من الحركات المعتمدة فقط ويجب أن يطابق حساب 218020.':'Return includes approved movements only and must reconcile to account 218020.'}</span><button disabled={busy} onClick={generateReturn}>{ar?'توليد الإقرار':'Generate return'}</button></div>
      </Panel>
      <Panel title={ar?'سداد الإقرار المعتمد':'Pay approved excise return'} icon={<Landmark size={18}/> }>
        <div className="journal-form" style={{gridTemplateColumns:'repeat(2,minmax(0,1fr))'}}>
          <label>{ar?'البنك':'Bank'}<select value={returnBankId} onChange={e=>setReturnBankId(e.target.value)} style={fieldStyle}>{banks.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.bank_name_ar:x.bank_name_en}</option>)}</select></label>
          <label>{ar?'تاريخ السداد':'Payment date'}<input type="date" value={paymentDate} onChange={e=>setPaymentDate(e.target.value)}/></label>
          <label>{ar?'رقم فاتورة سداد':'SADAD invoice'}<input value={sadad} onChange={e=>setSadad(e.target.value)}/></label>
          <label>{ar?'مرجع الدفع':'Payment reference'}<input value={paymentReference} onChange={e=>setPaymentReference(e.target.value)}/></label>
        </div>
        <div className="journal-footer"><span>{unpaidReturn?`${unpaidReturn.number}: ${money.format(Number(unpaidReturn.tax_payable))}`:(ar?'لا يوجد إقرار معتمد غير مسدد.':'No approved unpaid return.')}</span><button disabled={busy||!unpaidReturn} onClick={payReturn}>{ar?'سداد الإقرار':'Pay return'}</button></div>
      </Panel>
    </div>

    <Panel title={ar?'سجل إقرارات الضريبة الانتقائية':'Excise return register'} icon={<FileCheck2 size={18}/> }>
      <div className="journal-footer"><span>{ar?'الغرامة المعروضة مؤشر رقابي تقديري ولا تُرحّل تلقائيًا.':'Displayed penalty is an internal estimate and is not auto-posted.'}</span><button onClick={()=>download(`/api/v1/excise-tax/export/returns.csv?company_id=${companyId}`,'excise_tax_returns.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>
      <DataTable headers={[ar?'الرقم':'Number',ar?'الفترة':'Period',ar?'الاستحقاق':'Due',ar?'الوعاء':'Taxable value',ar?'إجمالي الضريبة':'Gross excise',ar?'المسدد بالجمارك':'Customs paid',ar?'المستحق':'Payable',ar?'فرق الأستاذ':'GL difference',ar?'الحالة/الإجراء':'Status / action']} rows={returns.map(x=>[x.number,`${x.period_start} → ${x.period_end}`,x.due_date,money.format(Number(x.taxable_value)),money.format(Number(x.gross_excise)),money.format(Number(x.customs_paid)),money.format(Number(x.tax_payable)),money.format(Number(x.reconciliation_difference)),<span key={x.id}>{x.status}{x.status==='DRAFT'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>returnAction(x.id,'submit')}>{ar?'إرسال':'Submit'}</button>}{x.status==='PENDING_APPROVAL'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>returnAction(x.id,'approve')}>{ar?'اعتماد':'Approve'}</button>}</span>])}/>
    </Panel>
  </>;
}
