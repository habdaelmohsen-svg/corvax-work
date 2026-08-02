import {Window} from 'happy-dom';
import React, {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';

const baseUrl=process.env.CORVAX_UAT_BASE_URL||'http://127.0.0.1:8130';
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
async function waitFor(selector:string,predicate:(element:Element)=>boolean=()=>true,timeout=6000){const start=Date.now();while(Date.now()-start<timeout){const element=document.querySelector(selector);if(element&&predicate(element))return element;await act(async()=>{await delay(50)})}throw new Error(`Timeout ${selector}: ${document.body.textContent?.slice(-1500)}`)}
async function setField(testId:string,value:string){const element=await waitFor(`[data-testid="${testId}"]`) as HTMLInputElement|HTMLSelectElement;await act(async()=>{const proto=element instanceof browser.HTMLSelectElement?browser.HTMLSelectElement.prototype:browser.HTMLInputElement.prototype;const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;assert(setter,`No setter for ${testId}`);setter.call(element,value);element.dispatchEvent(new browser.Event('input',{bubbles:true}));element.dispatchEvent(new browser.Event('change',{bubbles:true}));const propsKey=Object.keys(element).find(key=>key.startsWith('__reactProps$'));const onChange=propsKey?(element as any)[propsKey]?.onChange:null;if(typeof onChange==='function')onChange({target:element,currentTarget:element});await delay(30)})}
async function setCheckbox(testId:string,checked:boolean){const element=await waitFor(`[data-testid="${testId}"]`) as HTMLInputElement;await act(async()=>{const setter=Object.getOwnPropertyDescriptor(browser.HTMLInputElement.prototype,'checked')?.set;assert(setter,`No checkbox setter for ${testId}`);setter.call(element,checked);element.dispatchEvent(new browser.Event('change',{bubbles:true}));const propsKey=Object.keys(element).find(key=>key.startsWith('__reactProps$'));const onChange=propsKey?(element as any)[propsKey]?.onChange:null;if(typeof onChange==='function')onChange({target:element,currentTarget:element});await delay(30)})}
async function click(testId:string){const element=await waitFor(`[data-testid="${testId}"]`) as HTMLButtonElement;assert(!element.disabled,`${testId} disabled`);await act(async()=>{element.dispatchEvent(new browser.MouseEvent('click',{bubbles:true,cancelable:true}));await delay(400)})}

const admin=await login('admin@corvaxplatform.com','Corvax@123');
async function employee(email:string,password:string,roles:string[],name:string){await json('/api/v1/admin/users',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${admin.access_token}`},body:JSON.stringify({name_ar:name,name_en:name,email,password,require_password_change:false,memberships:roles.map(role_code=>({company_id:1,role_code}))})});return login(email,password)}
const buyer=await employee('r7.ui.buyer@corvaxplatform.com','R7UiBuyerSecure@123',['ACCOUNTANT','CFO'],'R7 purchasing employee');
const approver=await employee('r7.ui.proc.approver@corvaxplatform.com','R7UiProcApprove@123',['CFO'],'R7 procurement approver');
const poApprover=await employee('r7.ui.po.approver@corvaxplatform.com','R7UiPoApprove@123',['CFO'],'R7 purchase order approver');
const buyerHeader={Authorization:`Bearer ${buyer.access_token}`,'Content-Type':'application/json'};
const suppliers=await json('/api/v1/subledgers/parties?company_id=1&party_type=SUPPLIER',{headers:{Authorization:`Bearer ${buyer.access_token}`}});
const supplierA=suppliers[0];assert(supplierA,'Seed supplier missing');
const supplierB=await json('/api/v1/subledgers/parties',{method:'POST',headers:buyerHeader,body:JSON.stringify({company_id:1,code:'R7-UI-SUP-B',name_ar:'مورد واجهة المنافسة ب',name_en:'R7 UI Competitive Supplier B',party_type:'SUPPLIER',vat_number:'310000000000003',credit_limit:500000})});

const {ProcurementWorkflowTab}=await import('../src/dashboard/procurementWorkflowTab');
const container=document.createElement('div');document.body.appendChild(container);let root:Root|null=null;
async function renderAs(name:'buyer'|'approver'){
  role=name;const session=name==='buyer'?buyer:approver;sessionStorage.setItem('corvax_token',session.access_token);localStorage.setItem('corvax_user',JSON.stringify(session.user));if(root)await act(async()=>root?.unmount());container.replaceChildren();root=createRoot(container);await act(async()=>{root?.render(<ProcurementWorkflowTab ar={false} companyId={1}/>);await delay(600)});await waitFor('[data-testid="pr-create"]');
}

await renderAs('buyer');
await setField('pr-date','2026-07-20');await setField('pr-needed','2026-07-31');await setField('pr-department','Production R7 UI');await setField('pr-justification','Replenish production input after approved minimum-level alert');await setField('pr-quantity','200');await setField('pr-estimated-price','12');await setField('pr-specifications','Lot tracked and expiry greater than twelve months');
await click('pr-create');
let prs=await json('/api/v1/procurement/requisitions?company_id=1',{headers:{Authorization:`Bearer ${buyer.access_token}`}});const pr=prs.find((row:any)=>row.department==='Production R7 UI');assert(pr?.status==='DRAFT'&&Number(pr.estimated_total)===2400,`PR mismatch: ${JSON.stringify(pr)}`);
await click(`pr-submit-${pr.id}`);await waitFor(`[data-testid="pr-status-${pr.id}"]`,element=>element.textContent==='SUBMITTED');
await click(`pr-approve-${pr.id}`);assert(audit.some(row=>row.role==='buyer'&&row.path.endsWith(`/requisitions/${pr.id}/approve`)&&row.status===409),'Self-approval was not rejected');assert((await waitFor(`[data-testid="pr-status-${pr.id}"]`)).textContent==='SUBMITTED','Self-approval changed PR status');

await renderAs('approver');await click(`pr-approve-${pr.id}`);await waitFor(`[data-testid="pr-status-${pr.id}"]`,element=>element.textContent==='APPROVED');
await renderAs('buyer');await setField('rfq-pr',String(pr.id));
await setCheckbox(`rfq-supplier-${supplierA.id}`,true);await click('rfq-create');assert((container.textContent||'').includes('at least two suppliers'),'One-supplier validation not displayed');
await setCheckbox(`rfq-supplier-${supplierB.id}`,true);await click('rfq-create');
let rfqs=await json('/api/v1/procurement/rfqs?company_id=1',{headers:{Authorization:`Bearer ${buyer.access_token}`}});const rfq=rfqs.find((row:any)=>row.requisition_id===pr.id);assert(rfq?.status==='DRAFT'&&rfq.suppliers.length===2,`RFQ mismatch: ${JSON.stringify(rfq)}`);
await click(`rfq-issue-${rfq.id}`);await waitFor(`[data-testid="rfq-status-${rfq.id}"]`,element=>element.textContent==='ISSUED');

await setField('quote-rfq',String(rfq.id));await setField('quote-supplier',String(supplierA.id));await setField('quote-reference','R7-UI-QUOTE-A');await setField(`quote-price-${rfq.lines[0].id}`,'10');await click('quote-record');
await waitFor('[data-testid="quote-record"]',element=>!(element as HTMLButtonElement).disabled);await act(async()=>{await delay(500)});
await setField('quote-rfq',String(rfq.id));await act(async()=>{await delay(100)});await setField('quote-supplier',String(supplierB.id));await setField('quote-reference','R7-UI-QUOTE-B');await setField(`quote-price-${rfq.lines[0].id}`,'11');await click('quote-record');
rfqs=await json('/api/v1/procurement/rfqs?company_id=1',{headers:{Authorization:`Bearer ${buyer.access_token}`}});const quoted=rfqs.find((row:any)=>row.id===rfq.id);assert(quoted.quotations.length===2,`Expected two quotes: ${JSON.stringify(quoted)}; page=${container.textContent?.slice(-1200)}; audit=${JSON.stringify(audit.slice(-8))}`);const ordered=[...quoted.quotations].sort((a:any,b:any)=>Number(a.total)-Number(b.total));assert(Number(ordered[0].total)===2300&&Number(ordered[1].total)===2530,'Quote totals are wrong');
await click(`award-quote-${ordered[0].id}`);assert(audit.some(row=>row.role==='buyer'&&row.path.endsWith(`/rfqs/${rfq.id}/award`)&&row.status===409),'RFQ creator award was not rejected');

await renderAs('approver');await waitFor(` [data-testid="award-quote-${ordered[0].id}"]`.trim());await click(`award-quote-${ordered[0].id}`);
const finalRfqs=await json('/api/v1/procurement/rfqs?company_id=1',{headers:{Authorization:`Bearer ${approver.access_token}`}});const awarded=finalRfqs.find((row:any)=>row.id===rfq.id);assert(awarded.status==='AWARDED'&&awarded.awarded_quotation_id===ordered[0].id,`Award failed: ${JSON.stringify(awarded)}`);
const purchaseOrders=await json('/api/v1/inventory/purchase-orders?company_id=1',{headers:{Authorization:`Bearer ${approver.access_token}`}});const purchaseOrder=purchaseOrders.find((row:any)=>row.source_requisition_id===pr.id&&row.source_quotation_id===ordered[0].id);assert(purchaseOrder?.status==='DRAFT',`Traceable draft PO missing: ${JSON.stringify(purchaseOrders)}`);
let poResponse=await fetch(`${baseUrl}/api/v1/inventory/purchase-orders/${purchaseOrder.id}/approve`,{method:'POST',headers:{Authorization:`Bearer ${approver.access_token}`}});assert(poResponse.status===409,`Awarder PO self-approval expected 409, got ${poResponse.status}`);
poResponse=await fetch(`${baseUrl}/api/v1/inventory/purchase-orders/${purchaseOrder.id}/approve`,{method:'POST',headers:{Authorization:`Bearer ${poApprover.access_token}`}});assert(poResponse.status===200,`Independent PO approval failed: ${poResponse.status} ${await poResponse.text()}`);

const requestsBeforeSearch=audit.length;await setField('procurement-search',pr.number);await waitFor('[data-testid="procurement-search-count"]',element=>(element.textContent||'').startsWith('1/'));assert(audit.length===requestsBeforeSearch,'Local procurement search called the server');assert(!audit.some(row=>row.status>=500),`Server errors: ${JSON.stringify(audit.filter(row=>row.status>=500))}`);
console.log(JSON.stringify({database:'fresh isolated SQLite database supplied by runner',requisition:{id:pr.id,number:pr.number,estimate:Number(pr.estimated_total),states:['DRAFT','SUBMITTED','409 self-approval','APPROVED']},rfq:{id:rfq.id,number:rfq.number,suppliers:2,one_supplier_ui_rejected:true,quotes:ordered.map((q:any)=>({id:q.id,total:Number(q.total)})),maker_award_status:409,status:'AWARDED'},purchase_order:{id:purchaseOrder.id,source_requisition_id:purchaseOrder.source_requisition_id,source_quotation_id:purchaseOrder.source_quotation_id,awarder_self_approval:409,independent_approval:200},local_search_server_requests:0,requests:audit.length,writes:audit.filter(row=>row.method!=='GET').length,server_errors:0},null,2));
if(root)await act(async()=>root?.unmount());container.remove();
