import {Window} from 'happy-dom';
import React, {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';

const baseUrl=process.env.CORVAX_UAT_BASE_URL||'http://127.0.0.1:8129';
const browser=new Window({url:`${baseUrl}/#/purchases`});
Object.assign(globalThis,{window:browser,document:browser.document,localStorage:browser.localStorage,sessionStorage:browser.sessionStorage,HTMLElement:browser.HTMLElement,HTMLInputElement:browser.HTMLInputElement,HTMLSelectElement:browser.HTMLSelectElement,Event:browser.Event,CustomEvent:browser.CustomEvent});
Object.defineProperty(globalThis,'navigator',{value:browser.navigator,configurable:true});
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;

type Audit={role:string;method:string;path:string;status:number;detail?:string};
const nativeFetch=globalThis.fetch;const audit:Audit[]=[];let role='setup';
globalThis.fetch=(async(input:RequestInfo|URL,init?:RequestInit)=>{const raw=typeof input==='string'?input:input instanceof URL?input.toString():input.url;const url=raw.startsWith('/')?`${baseUrl}${raw}`:raw;const response=await nativeFetch(url,init);audit.push({role,method:String(init?.method||'GET').toUpperCase(),path:new URL(url).pathname,status:response.status,detail:response.ok?undefined:await response.clone().text()});return response}) as typeof fetch;

const delay=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
function assert(value:unknown,message:string):asserts value{if(!value)throw new Error(message)}
async function json(url:string,init?:RequestInit){const response=await fetch(url,init);const payload=await response.json().catch(()=>({}));if(!response.ok)throw new Error(`${response.status}: ${JSON.stringify(payload)}`);return payload}
async function login(email:string,password:string){return json('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})})}
async function waitFor(selector:string,predicate:(element:Element)=>boolean=()=>true,timeout=5000){const start=Date.now();while(Date.now()-start<timeout){const element=document.querySelector(selector);if(element&&predicate(element))return element;await act(async()=>{await delay(50)})}throw new Error(`Timeout ${selector}: ${document.body.textContent?.slice(-1200)}`)}
async function setField(testId:string,value:string){const element=await waitFor(`[data-testid="${testId}"]`) as HTMLInputElement|HTMLSelectElement;await act(async()=>{const proto=element instanceof browser.HTMLSelectElement?browser.HTMLSelectElement.prototype:browser.HTMLInputElement.prototype;const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;assert(setter,`Missing value setter: ${testId}`);setter.call(element,value);element.dispatchEvent(new browser.Event('input',{bubbles:true}));element.dispatchEvent(new browser.Event('change',{bubbles:true}));const propsKey=Object.keys(element).find(key=>key.startsWith('__reactProps$'));const onChange=propsKey?(element as any)[propsKey]?.onChange:null;if(typeof onChange==='function')onChange({target:element,currentTarget:element});await delay(25)})}
async function click(testId:string){const element=await waitFor(`[data-testid="${testId}"]`) as HTMLButtonElement;assert(!element.disabled,`${testId} disabled`);await act(async()=>{element.dispatchEvent(new browser.MouseEvent('click',{bubbles:true,cancelable:true}));await delay(350)})}

const admin=await login('admin@corvaxplatform.com','Corvax@123');
async function employee(roleCode:string,email:string,password:string,name:string){await json('/api/v1/admin/users',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${admin.access_token}`},body:JSON.stringify({name_ar:name,name_en:name,email,password,require_password_change:false,memberships:[{company_id:1,role_code:roleCode}]})});return login(email,password)}
const accountant=await employee('ACCOUNTANT','r7.ap.maker@corvaxplatform.com','R7ApMaker@123','R7 AP invoice maker');
const cfo=await employee('CFO','r7.ap.cfo@corvaxplatform.com','R7ApCfoSecure@123','R7 AP poster and payer');
const {PurchasesPage}=await import('../src/dashboard/purchasesPage');
const container=document.createElement('div');document.body.appendChild(container);let root:Root|null=null;
async function renderAs(name:'accountant'|'cfo'){
  role=name;const session=name==='accountant'?accountant:cfo;sessionStorage.setItem('corvax_token',session.access_token);localStorage.setItem('corvax_user',JSON.stringify(session.user));
  if(root)await act(async()=>root?.unmount());container.replaceChildren();root=createRoot(container);
  await act(async()=>{root?.render(<PurchasesPage ar={false} companyId={1}/>);await delay(450)});
  await click('purchases-invoices-tab');await waitFor('[data-testid="purchase-invoice-create"]');
}

await renderAs('accountant');
const supplierSelect=await waitFor('[data-testid="purchase-invoice-supplier"]') as HTMLSelectElement;
assert(supplierSelect.options.length>0,'No supplier available in invoice UI');
const supplierId=supplierSelect.value||supplierSelect.options[0].value;
await setField('purchase-invoice-supplier',supplierId);
await setField('purchase-supplier-invoice','R7-AP-UI-001');
await setField('purchase-invoice-date','2026-07-20');
await setField('purchase-invoice-due','2026-07-31');
await setField('purchase-invoice-description','R7 employee office services');
await setField('purchase-invoice-quantity','2');
await setField('purchase-invoice-price','500');
await setField('purchase-invoice-vat','15');
await click('purchase-invoice-create');
const draftList=await json('/api/v1/subledgers/purchase-invoices?company_id=1',{headers:{Authorization:`Bearer ${accountant.access_token}`}});
const invoice=draftList.find((row:any)=>row.supplier_invoice_number==='R7-AP-UI-001');
assert(invoice?.status==='DRAFT',`UI invoice was not saved as DRAFT: ${JSON.stringify(invoice)}; page=${container.textContent?.slice(-1200)}; audit=${JSON.stringify(audit.slice(-5))}`);
await waitFor(`[data-testid="purchase-invoice-status-${invoice.id}"]`,element=>element.textContent==='DRAFT');

// The maker sees the post action, but their accounting role cannot post journals.
await click(`purchase-invoice-post-${invoice.id}`);
assert(audit.some(row=>row.role==='accountant'&&row.path.endsWith(`/purchase-invoices/${invoice.id}/post`)&&row.status===403),'Maker post attempt was not rejected with 403');
assert((await waitFor(`[data-testid="purchase-invoice-status-${invoice.id}"]`)).textContent==='DRAFT','Rejected maker post changed invoice state');

await renderAs('cfo');
await waitFor(`[data-testid="purchase-invoice-status-${invoice.id}"]`,element=>element.textContent==='DRAFT');
await click(`purchase-invoice-post-${invoice.id}`);
await waitFor(`[data-testid="purchase-invoice-status-${invoice.id}"]`,element=>element.textContent==='POSTED');

const paymentSupplier=await waitFor('[data-testid="payment-supplier"]') as HTMLSelectElement;
assert([...paymentSupplier.options].some(option=>option.value===supplierId),'Invoice supplier missing from payment UI');
await setField('payment-supplier',supplierId);
const bank=await waitFor('[data-testid="payment-bank"]') as HTMLSelectElement;assert(bank.options.length>0,'No bank account available');
await setField('payment-bank',bank.value||bank.options[0].value);
await setField('payment-amount','1150');
await setField('payment-date','2026-07-21');
await setField('payment-reference','R7-AP-PAY-UI-001');
await click('payment-create');

const payments=await json('/api/v1/subledgers/payments?company_id=1',{headers:{Authorization:`Bearer ${cfo.access_token}`}});
const payment=payments.find((row:any)=>row.reference==='R7-AP-PAY-UI-001');
assert(payment,'Payment entered in UI was not persisted');
assert(Number(payment.amount)===1150&&Number(payment.allocated_amount)===1150&&Number(payment.unapplied_amount)===0,`Payment allocation mismatch: ${JSON.stringify(payment)}`);
const openItems=await json(`/api/v1/subledgers/open-items?company_id=1&ledger_type=AP&party_id=${supplierId}&include_closed=true`,{headers:{Authorization:`Bearer ${cfo.access_token}`}});
const payable=openItems.find((row:any)=>row.source_id===invoice.id||row.document_number===invoice.number);
assert(payable?.status==='CLOSED'&&Number(payable.outstanding_amount)===0,`Payable not closed: ${JSON.stringify(payable)}`);

const requestCount=audit.length;
await setField('purchase-search','R7-AP-UI-001');
await waitFor('[data-testid="purchase-search-count"]',element=>(element.textContent||'').startsWith('1/'));
assert(audit.length===requestCount,'Local invoice search called the server');
assert(!audit.some(row=>row.status>=500),`Server errors: ${JSON.stringify(audit.filter(row=>row.status>=500))}`);

console.log(JSON.stringify({database:'fresh isolated SQLite database supplied by runner',invoice_id:invoice.id,invoice_status_sequence:['DRAFT','403 maker rejection','POSTED'],invoice_total:Number(invoice.total),payment_id:payment.id,payment_amount:Number(payment.amount),allocated_amount:Number(payment.allocated_amount),unapplied_amount:Number(payment.unapplied_amount),payable_status:payable.status,local_search_server_requests:0,requests:audit.length,writes:audit.filter(row=>row.method!=='GET').length,server_errors:0},null,2));
if(root)await act(async()=>root?.unmount());container.remove();
