import {useEffect, useMemo, useState} from 'react';
import {BadgePercent, Building2, CheckCircle2, Download, FileCheck2, Landmark, ReceiptText, ShieldCheck} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, MiniStatus, Panel, money} from './ui';

type Party={id:number;code:string;name_ar:string;name_en:string};
type Bank={id:number;code:string;bank_name_ar:string;bank_name_en:string;gl_account_code:string};
type Category={id:number;code:string;name_ar:string;name_en:string;statutory_rate:number;source_rule:string};
type Profile={id:number;party_id:number;party_code:string;party_name_ar:string;party_name_en:string;country_code:string;tax_residency_country:string;foreign_tax_id?:string;permanent_establishment_in_ksa:boolean;beneficial_owner_confirmed:boolean;treaty_country_code?:string;treaty_relief_approval_reference?:string;treaty_relief_approval_expiry?:string};

type Tx={id:number;number:string;payment_date:string;beneficiary_name_ar:string;beneficiary_name_en:string;country_code:string;category_code:string;category_name_ar:string;category_name_en:string;gross_amount:number;statutory_rate:number;applied_rate:number;withholding_amount:number;net_cash_amount:number;dta_relief_method:string;status:string;journal_id?:number};
type WhtReturn={id:number;number:string;period_start:string;period_end:string;due_date:string;status:string;gross_payments:number;tax_withheld:number;gl_withheld:number;reconciliation_difference:number;late_days:number;estimated_late_penalty:number;sadad_invoice_number?:string;payment_date?:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
async function download(url:string,filename:string){
  const r=await apiFetch(url); if(!r.ok) throw new Error('Export failed');
  const blob=await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename; a.click(); URL.revokeObjectURL(a.href);
}
function monthBounds(value:string){
  const [year,month]=value.split('-').map(Number); const last=new Date(year,month,0).getDate();
  return {start:`${value}-01`,end:`${value}-${String(last).padStart(2,'0')}`};
}
const fieldStyle={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9};

export function WithholdingTaxPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date().toISOString().slice(0,10); const month=today.slice(0,7);
  const [parties,setParties]=useState<Party[]>([]); const [banks,setBanks]=useState<Bank[]>([]); const [categories,setCategories]=useState<Category[]>([]);
  const [profiles,setProfiles]=useState<Profile[]>([]); const [transactions,setTransactions]=useState<Tx[]>([]); const [returns,setReturns]=useState<WhtReturn[]>([]);
  const [partyId,setPartyId]=useState(''); const [country,setCountry]=useState('AE'); const [foreignTaxId,setForeignTaxId]=useState('');
  const [beneficialOwner,setBeneficialOwner]=useState(true); const [hasPe,setHasPe]=useState(false); const [treatyCountry,setTreatyCountry]=useState(''); const [treatyApproval,setTreatyApproval]=useState(''); const [treatyExpiry,setTreatyExpiry]=useState('');
  const [profileId,setProfileId]=useState(''); const [categoryId,setCategoryId]=useState(''); const [bankId,setBankId]=useState(''); const [amount,setAmount]=useState('1000'); const [paymentDate,setPaymentDate]=useState(today);
  const [debitAccount,setDebitAccount]=useState('613010'); const [description,setDescription]=useState('Professional services payment'); const [dtaMethod,setDtaMethod]=useState('STATUTORY'); const [treatyRate,setTreatyRate]=useState(''); const [dtaReference,setDtaReference]=useState(''); const [grossUp,setGrossUp]=useState(false);
  const [returnMonth,setReturnMonth]=useState(month); const [payBankId,setPayBankId]=useState(''); const [sadad,setSadad]=useState(''); const [paymentReference,setPaymentReference]=useState(''); const [returnPaymentDate,setReturnPaymentDate]=useState(today);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);

  const load=async()=>{
    try{
      const [p,b,c,pr,t,r]=await Promise.all([
        json(`/api/v1/subledgers/parties?company_id=${companyId}&party_type=SUPPLIER`),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`),
        json(`/api/v1/withholding-tax/categories?company_id=${companyId}`),
        json(`/api/v1/withholding-tax/beneficiaries?company_id=${companyId}`),
        json(`/api/v1/withholding-tax/transactions?company_id=${companyId}`),
        json(`/api/v1/withholding-tax/returns?company_id=${companyId}`),
      ]);
      setParties(p||[]);setBanks(b||[]);setCategories(c||[]);setProfiles(pr||[]);setTransactions(t||[]);setReturns(r||[]);
      if(!partyId&&p?.length)setPartyId(String(p[0].id)); if(!profileId&&pr?.length)setProfileId(String(pr[0].id));
      if(!categoryId&&c?.length)setCategoryId(String(c.find((x:Category)=>x.code==='TECHNICAL_CONSULTING')?.id||c[0].id));
      if(!bankId&&b?.length){setBankId(String(b[0].id));setPayBankId(String(b[0].id));}
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{if(profiles.length&&!profiles.some(x=>String(x.id)===profileId))setProfileId(String(profiles[0].id));},[profiles,profileId]);

  const selectedCategory=useMemo(()=>categories.find(x=>String(x.id)===categoryId),[categories,categoryId]);
  const totalTax=transactions.filter(x=>x.status==='APPROVED_POSTED').reduce((s,x)=>s+Number(x.withholding_amount||0),0);
  const pending=transactions.filter(x=>x.status==='PENDING_APPROVAL').length;
  const unpaid=returns.filter(x=>x.status==='APPROVED').reduce((s,x)=>s+Number(x.tax_withheld||0),0);
  const openReturn=returns.find(x=>x.status==='APPROVED');

  async function saveProfile(){
    if(!partyId||!country.trim()){setMessage(ar?'اختر المورد وأدخل الدولة.':'Select supplier and country.');return;}
    setBusy(true);setMessage('');try{
      const payload={company_id:companyId,party_id:Number(partyId),country_code:country.toUpperCase(),tax_residency_country:country.toUpperCase(),foreign_tax_id:foreignTaxId||null,non_resident:true,permanent_establishment_in_ksa:hasPe,related_party:false,beneficial_owner_confirmed:beneficialOwner,treaty_country_code:treatyCountry.toUpperCase()||null,residency_certificate_number:null,residency_certificate_expiry:null,treaty_relief_approval_reference:treatyApproval||null,treaty_relief_approval_expiry:treatyExpiry||null,notes:null};
      const x=await json('/api/v1/withholding-tax/beneficiaries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});setProfileId(String(x.id));setMessage(ar?'تم حفظ ملف المستفيد غير المقيم.':'Non-resident beneficiary profile saved.');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function createTransaction(){
    if(!profileId||!categoryId||!bankId||!description.trim()){setMessage(ar?'أكمل بيانات المعاملة.':'Complete the transaction data.');return;}
    setBusy(true);setMessage('');try{
      const payload={company_id:companyId,payment_date:paymentDate,beneficiary_profile_id:Number(profileId),category_id:Number(categoryId),amount:Number(amount),bank_account_id:Number(bankId),purchase_invoice_id:null,debit_account_code:debitAccount,gross_up:grossUp,source_in_ksa:true,dta_relief_method:dtaMethod,treaty_rate:treatyRate?Number(treatyRate):null,dta_reference:dtaReference||null,description,reference:null};
      const x=await json('/api/v1/withholding-tax/transactions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});setMessage(`${ar?'تم إنشاء المعاملة':'Transaction created'}: ${x.number}`);await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function txAction(id:number,action:'submit'|'approve-post'){
    setBusy(true);setMessage('');try{const x=await json(`/api/v1/withholding-tax/transactions/${id}/${action}`,{method:'POST'});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function generateReturn(){
    const bounds=monthBounds(returnMonth);setBusy(true);setMessage('');try{const x=await json('/api/v1/withholding-tax/returns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,period_start:bounds.start,period_end:bounds.end})});setMessage(`${ar?'تم إنشاء الإقرار':'Return generated'}: ${x.number}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function returnAction(id:number,action:'submit'|'approve'){
    setBusy(true);setMessage('');try{const x=await json(`/api/v1/withholding-tax/returns/${id}/${action}`,{method:'POST'});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }
  async function payReturn(id:number){
    if(!payBankId||!sadad||!paymentReference){setMessage(ar?'أدخل حساب البنك ورقم فاتورة سداد ومرجع الدفع.':'Enter bank, SADAD invoice and payment reference.');return;}
    setBusy(true);setMessage('');try{const x=await json(`/api/v1/withholding-tax/returns/${id}/pay`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bank_account_id:Number(payBankId),payment_date:returnPaymentDate,sadad_invoice_number:sadad,payment_reference:paymentReference})});setMessage(`${x.number}: ${x.status}`);await load();}catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false)}
  }

  return <>
    <div className="kpis rich">
      <Kpi title={ar?'الضريبة المرحلة':'Posted withholding'} value={money.format(totalTax)} trend={ar?'حساب 218010':'Account 218010'} good/>
      <Kpi title={ar?'بانتظار الاعتماد':'Pending approval'} value={String(pending)} trend="Maker–Checker" good={pending===0}/>
      <Kpi title={ar?'إقرارات مستحقة السداد':'Approved returns due'} value={money.format(unpaid)} trend={ar?'قبل يوم 10':'Due by day 10'} good={unpaid===0}/>
      <Kpi title={ar?'ملفات مستفيدين':'Beneficiary profiles'} value={String(profiles.length)} trend={ar?'غير مقيمين':'Non-residents'} good={profiles.length>0}/>
    </div>

    <div className="two-columns wide-left">
      <Panel title={ar?'ملف المستفيد غير المقيم':'Non-resident beneficiary profile'} icon={<Building2 size={18}/> }>
        <div className="journal-form" style={{gridTemplateColumns:'repeat(2,minmax(0,1fr))'}}>
          <label>{ar?'المورد':'Supplier'}<select value={partyId} onChange={e=>setPartyId(e.target.value)} style={fieldStyle}>{parties.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en}</option>)}</select></label>
          <label>{ar?'دولة الإقامة الضريبية':'Tax residence country'}<input value={country} onChange={e=>setCountry(e.target.value.toUpperCase())} maxLength={3}/></label>
          <label>{ar?'الرقم الضريبي الأجنبي':'Foreign tax ID'}<input value={foreignTaxId} onChange={e=>setForeignTaxId(e.target.value)}/></label>
          <label>{ar?'دولة المعاهدة':'Treaty country'}<input value={treatyCountry} onChange={e=>setTreatyCountry(e.target.value.toUpperCase())} maxLength={3}/></label>
          <label>{ar?'مرجع موافقة التطبيق المباشر':'Direct-relief approval reference'}<input value={treatyApproval} onChange={e=>setTreatyApproval(e.target.value)}/></label>
          <label>{ar?'انتهاء الموافقة':'Approval expiry'}<input type="date" value={treatyExpiry} onChange={e=>setTreatyExpiry(e.target.value)}/></label>
          <label><input type="checkbox" checked={beneficialOwner} onChange={e=>setBeneficialOwner(e.target.checked)}/> {ar?'تأكيد المستفيد الحقيقي':'Beneficial owner confirmed'}</label>
          <label><input type="checkbox" checked={hasPe} onChange={e=>setHasPe(e.target.checked)}/> {ar?'له منشأة دائمة في المملكة':'Has KSA permanent establishment'}</label>
        </div>
        <div className="journal-footer"><span>{message|| (ar?'لا تستخدم الدورة للدفعات المنسوبة إلى منشأة دائمة داخل المملكة.':'Do not use WHT for payments attributable to a KSA permanent establishment.')}</span><button disabled={busy||!parties.length} onClick={saveProfile}>{ar?'حفظ الملف':'Save profile'}</button></div>
      </Panel>
      <Panel title={ar?'الضوابط النظامية':'Compliance controls'} icon={<ShieldCheck size={18}/> }>
        <MiniStatus icon={<BadgePercent size={18}/>} title={ar?'النسب النظامية':'Statutory rates'} value="5% / 15% / 20%" status={ar?'حسب نوع الدفعة':'By payment category'}/>
        <MiniStatus icon={<FileCheck2 size={18}/>} title={ar?'المعاهدة الضريبية':'Tax treaty'} value={ar?'موثقة':'Documented'} status={ar?'تطبيق مباشر بموافقة أو مطالبة رد':'Direct approval or refund claim'}/>
        <MiniStatus icon={<CheckCircle2 size={18}/>} title="Maker–Checker" value={ar?'مفعّل':'Active'} status={ar?'المُعد لا يعتمد':'Maker cannot approve'}/>
      </Panel>
    </div>

    <Panel title={ar?'إنشاء دفعة خاضعة للاستقطاع':'Create withholding-tax payment'} icon={<ReceiptText size={18}/> }>
      <div className="journal-form" style={{gridTemplateColumns:'repeat(4,minmax(0,1fr))'}}>
        <label>{ar?'المستفيد':'Beneficiary'}<select value={profileId} onChange={e=>setProfileId(e.target.value)} style={fieldStyle}>{profiles.map(x=><option key={x.id} value={x.id}>{x.party_code} — {ar?x.party_name_ar:x.party_name_en}</option>)}</select></label>
        <label>{ar?'نوع الدفعة':'Payment category'}<select value={categoryId} onChange={e=>setCategoryId(e.target.value)} style={fieldStyle}>{categories.map(x=><option key={x.id} value={x.id}>{ar?x.name_ar:x.name_en} — {Number(x.statutory_rate)}%</option>)}</select></label>
        <label>{ar?'المبلغ':'Amount'}<input type="number" min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label>
        <label>{ar?'تاريخ الدفع':'Payment date'}<input type="date" value={paymentDate} onChange={e=>setPaymentDate(e.target.value)}/></label>
        <label>{ar?'الحساب المدين':'Debit account'}<input value={debitAccount} onChange={e=>setDebitAccount(e.target.value)}/></label>
        <label>{ar?'البنك':'Bank'}<select value={bankId} onChange={e=>setBankId(e.target.value)} style={fieldStyle}>{banks.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.bank_name_ar:x.bank_name_en}</option>)}</select></label>
        <label>{ar?'طريقة المعاهدة':'Treaty method'}<select value={dtaMethod} onChange={e=>setDtaMethod(e.target.value)} style={fieldStyle}><option value="STATUTORY">STATUTORY</option><option value="REFUND_CLAIM">REFUND_CLAIM</option><option value="DIRECT_RELIEF">DIRECT_RELIEF</option></select></label>
        <label>{ar?'نسبة المعاهدة':'Treaty rate'}<input type="number" min="0" max="100" step="0.01" value={treatyRate} onChange={e=>setTreatyRate(e.target.value)} placeholder={selectedCategory?String(selectedCategory.statutory_rate):''}/></label>
        <label>{ar?'مرجع المعاهدة':'DTA reference'}<input value={dtaReference} onChange={e=>setDtaReference(e.target.value)}/></label>
        <label style={{gridColumn:'span 3'}}>{ar?'الوصف':'Description'}<input value={description} onChange={e=>setDescription(e.target.value)}/></label>
        <label><input type="checkbox" checked={grossUp} onChange={e=>setGrossUp(e.target.checked)}/> {ar?'المبلغ صافي ويتطلب Gross-up':'Amount is net; gross-up required'}</label>
      </div>
      <div className="journal-footer"><span>{selectedCategory?`${ar?selectedCategory.name_ar:selectedCategory.name_en}: ${selectedCategory.statutory_rate}%`:message}</span><button disabled={busy||!profiles.length||!banks.length} onClick={createTransaction}>{ar?'إنشاء المعاملة':'Create transaction'}</button></div>
    </Panel>

    <Panel title={ar?'سجل معاملات ضريبة الاستقطاع':'Withholding-tax transaction register'} icon={<Landmark size={18}/> }>
      <div className="journal-footer"><span>{ar?'يُرحّل صافي المبلغ للبنك والضريبة إلى حساب الالتزام 218010.':'Net cash is posted to bank and tax to liability account 218010.'}</span><button onClick={()=>download(`/api/v1/withholding-tax/export/transactions.csv?company_id=${companyId}`,'withholding_tax_transactions.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>
      <DataTable headers={[ar?'الرقم':'Number',ar?'التاريخ':'Date',ar?'المستفيد':'Beneficiary',ar?'الفئة':'Category',ar?'الإجمالي':'Gross',ar?'النسبة':'Rate',ar?'الضريبة':'Tax',ar?'الصافي':'Net',ar?'الحالة/الإجراء':'Status / action']} rows={transactions.map(x=>[x.number,x.payment_date,ar?x.beneficiary_name_ar:x.beneficiary_name_en,ar?x.category_name_ar:x.category_name_en,money.format(Number(x.gross_amount)),`${Number(x.applied_rate)}%`,money.format(Number(x.withholding_amount)),money.format(Number(x.net_cash_amount)),<span key={x.id}>{x.status}{x.status==='DRAFT'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>txAction(x.id,'submit')}>{ar?'إرسال':'Submit'}</button>}{x.status==='PENDING_APPROVAL'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>txAction(x.id,'approve-post')}>{ar?'اعتماد وترحيل':'Approve & post'}</button>}</span>])}/>
    </Panel>

    <div className="two-columns wide-left">
      <Panel title={ar?'إنشاء الإقرار الشهري':'Generate monthly WHT return'} icon={<FileCheck2 size={18}/> }>
        <div className="journal-form" style={{gridTemplateColumns:'repeat(2,minmax(0,1fr))'}}><label>{ar?'الشهر':'Month'}<input type="month" value={returnMonth} onChange={e=>setReturnMonth(e.target.value)}/></label><label>{ar?'موعد الاستحقاق':'Due date'}<input disabled value={returns[0]?.due_date|| (ar?'اليوم العاشر من الشهر التالي':'10th of following month')}/></label></div>
        <div className="journal-footer"><span>{ar?'يُنشأ الإقرار من المعاملات المعتمدة فقط ويجب أن يطابق الأستاذ.':'The return includes approved transactions only and must reconcile to GL.'}</span><button disabled={busy} onClick={generateReturn}>{ar?'توليد الإقرار':'Generate return'}</button></div>
      </Panel>
      <Panel title={ar?'سداد الإقرار المعتمد':'Pay approved return'} icon={<Landmark size={18}/> }>
        <div className="journal-form" style={{gridTemplateColumns:'repeat(2,minmax(0,1fr))'}}>
          <label>{ar?'البنك':'Bank'}<select value={payBankId} onChange={e=>setPayBankId(e.target.value)} style={fieldStyle}>{banks.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.bank_name_ar:x.bank_name_en}</option>)}</select></label>
          <label>{ar?'تاريخ السداد':'Payment date'}<input type="date" value={returnPaymentDate} onChange={e=>setReturnPaymentDate(e.target.value)}/></label>
          <label>{ar?'رقم فاتورة سداد':'SADAD invoice'}<input value={sadad} onChange={e=>setSadad(e.target.value)}/></label>
          <label>{ar?'مرجع الدفع':'Payment reference'}<input value={paymentReference} onChange={e=>setPaymentReference(e.target.value)}/></label>
        </div>
        <div className="journal-footer"><span>{openReturn?`${openReturn.number}: ${money.format(Number(openReturn.tax_withheld))}`:(ar?'لا يوجد إقرار معتمد غير مسدد.':'No approved unpaid return.')}</span><button disabled={busy||!openReturn} onClick={()=>openReturn&&payReturn(openReturn.id)}>{ar?'سداد الإقرار':'Pay return'}</button></div>
      </Panel>
    </div>

    <Panel title={ar?'سجل إقرارات ضريبة الاستقطاع':'Monthly WHT return register'} icon={<FileCheck2 size={18}/> }>
      <div className="journal-footer"><span>{message|| (ar?'غرامة التأخر المعروضة تقديرية للرقابة ولا تُرحّل تلقائيًا.':'Displayed late penalty is an internal estimate and is not auto-posted.')}</span><button onClick={()=>download(`/api/v1/withholding-tax/export/returns.csv?company_id=${companyId}`,'withholding_tax_returns.csv').catch(e=>setMessage(e.message))}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div>
      <DataTable headers={[ar?'الرقم':'Number',ar?'الفترة':'Period',ar?'الاستحقاق':'Due',ar?'إجمالي الدفعات':'Gross payments',ar?'الضريبة':'Tax',ar?'فرق الأستاذ':'GL difference',ar?'غرامة تقديرية':'Estimated penalty',ar?'الحالة/الإجراء':'Status / action']} rows={returns.map(x=>[x.number,`${x.period_start} → ${x.period_end}`,x.due_date,money.format(Number(x.gross_payments)),money.format(Number(x.tax_withheld)),money.format(Number(x.reconciliation_difference)),money.format(Number(x.estimated_late_penalty||0)),<span key={x.id}>{x.status}{x.status==='DRAFT'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>returnAction(x.id,'submit')}>{ar?'إرسال':'Submit'}</button>}{x.status==='PENDING_APPROVAL'&&<button disabled={busy} style={{marginInlineStart:6}} onClick={()=>returnAction(x.id,'approve')}>{ar?'اعتماد':'Approve'}</button>}</span>])}/>
    </Panel>
  </>;
}
