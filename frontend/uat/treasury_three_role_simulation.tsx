import {Window} from 'happy-dom';
import React, {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';


const baseUrl = process.env.CORVAX_UAT_BASE_URL || 'http://127.0.0.1:8128';
const windowInstance = new Window({url: `${baseUrl}/#/treasury`});
Object.assign(globalThis, {
  window: windowInstance,
  document: windowInstance.document,
  localStorage: windowInstance.localStorage,
  sessionStorage: windowInstance.sessionStorage,
  HTMLElement: windowInstance.HTMLElement,
  HTMLInputElement: windowInstance.HTMLInputElement,
  HTMLSelectElement: windowInstance.HTMLSelectElement,
  HTMLAnchorElement: windowInstance.HTMLAnchorElement,
  Event: windowInstance.Event,
  CustomEvent: windowInstance.CustomEvent,
});
Object.defineProperty(globalThis, 'navigator', {value: windowInstance.navigator, configurable: true});
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

type AuditRow={role:string;method:string;path:string;status:number};
type ExportCapture={contentType:string;contentDisposition:string;text:string};
const nativeFetch=globalThis.fetch;
const httpAudit:AuditRow[]=[];
let exportCapture:ExportCapture|null=null;
let downloadedFilename='';
Object.defineProperty(windowInstance.HTMLAnchorElement.prototype,'click',{configurable:true,value:function(this:HTMLAnchorElement){downloadedFilename=this.download;}});
let activeRole='setup';
globalThis.fetch=(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const raw=typeof input==='string'?input:input instanceof URL?input.toString():input.url;
  const url=raw.startsWith('/')?`${baseUrl}${raw}`:raw;
  const response=await nativeFetch(url,init);
  const path=new URL(url).pathname;
  httpAudit.push({role:activeRole,method:String(init?.method||'GET').toUpperCase(),path,status:response.status});
  if(path==='/api/v1/banking/statements/export.csv'&&response.ok){const copy=response.clone();exportCapture={contentType:copy.headers.get('content-type')||'',contentDisposition:copy.headers.get('content-disposition')||'',text:await copy.text()};}
  return response;
}) as typeof fetch;

const delay=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
function assert(condition:unknown,message:string):asserts condition{if(!condition)throw new Error(message)}
async function json(url:string,init?:RequestInit){const response=await fetch(url,init);const payload=await response.json();if(!response.ok)throw new Error(`${response.status}: ${JSON.stringify(payload)}`);return payload}
async function login(email:string,password:string){return json('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})})}
async function createUser(adminToken:string,data:any){return json('/api/v1/admin/users',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${adminToken}`},body:JSON.stringify(data)})}
async function waitFor(selector:string,predicate:(element:Element)=>boolean=()=>true,timeoutMs=4000){const start=Date.now();while(Date.now()-start<timeoutMs){const element=document.querySelector(selector);if(element&&predicate(element))return element;await act(async()=>{await delay(40)})}throw new Error(`Timed out waiting for ${selector}: ${document.body.textContent?.slice(-1000)}`)}
async function waitUntil(predicate:()=>boolean,message:string,timeoutMs=4000){const start=Date.now();while(Date.now()-start<timeoutMs){if(predicate())return;await act(async()=>{await delay(40)})}throw new Error(message)}
async function setField(testId:string,value:string){const element=await waitFor(`[data-testid="${testId}"]`) as HTMLInputElement|HTMLSelectElement;await act(async()=>{const prototype=element instanceof window.HTMLSelectElement?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype;const setter=Object.getOwnPropertyDescriptor(prototype,'value')?.set;assert(setter,`No native value setter for ${testId}`);setter.call(element,value);element.dispatchEvent(new window.Event('input',{bubbles:true}));element.dispatchEvent(new window.Event('change',{bubbles:true}));const propsKey=Object.keys(element).find(key=>key.startsWith('__reactProps$'));const onChange=propsKey?(element as any)[propsKey]?.onChange:null;if(typeof onChange==='function')onChange({target:element,currentTarget:element});await delay(25)})}
async function click(testId:string){const element=await waitFor(`[data-testid="${testId}"]`) as HTMLButtonElement;assert(!element.disabled,`${testId} is disabled`);await act(async()=>{element.dispatchEvent(new window.MouseEvent('click',{bubbles:true,cancelable:true}));await delay(250)})}

const admin=await login('admin@corvaxplatform.com','Corvax@123');
const users=[
  {role:'maker',name_en:'R7 Treasury Maker',name_ar:'مُعد كشف الخزانة R7',username:'r7_treasury_maker',email:'r7.treasury.maker@corvaxplatform.com',password:'R7TreasuryMaker@123',role_code:'ACCOUNTANT'},
  {role:'matcher',name_en:'R7 Treasury Matcher',name_ar:'مطابق كشف الخزانة R7',username:'r7_treasury_matcher',email:'r7.treasury.matcher@corvaxplatform.com',password:'R7TreasuryMatcher@123',role_code:'ACCOUNTANT'},
  {role:'reconciler',name_en:'R7 Treasury Controller',name_ar:'مراقب تسوية الخزانة R7',username:'r7_treasury_controller',email:'r7.treasury.controller@corvaxplatform.com',password:'R7TreasuryController@123',role_code:'FINANCIAL_CONTROLLER'},
];
for(const user of users){await createUser(admin.access_token,{name_ar:user.name_ar,name_en:user.name_en,username:user.username,email:user.email,password:user.password,require_password_change:false,memberships:[{company_id:1,role_code:user.role_code}]})}
const sessions:Record<string,any>={};
for(const user of users)sessions[user.role]=await login(user.email,user.password);

const {TreasuryPage}=await import('../src/dashboard/financePages');
const container=document.createElement('div');document.body.appendChild(container);
let root:Root|null=null;
async function renderAs(role:string){activeRole=role;sessionStorage.setItem('corvax_token',sessions[role].access_token);localStorage.setItem('corvax_user',JSON.stringify(sessions[role].user));if(root)await act(async()=>root?.unmount());container.replaceChildren();root=createRoot(container);await act(async()=>{root?.render(<TreasuryPage ar={false} companyId={1}/>);await delay(300)});await waitFor('[data-testid="bank-create"]');}

// Employee 1 prepares a real one-line statement through the rendered form.
await renderAs('maker');
await setField('bank-statement-date','2026-01-01');
await setField('bank-opening','0');
await setField('bank-closing','2000000');
await setField('bank-line-date','2026-01-01');
await setField('bank-reference','OPENING');
await setField('bank-description','R7 opening capital bank line');
await setField('bank-line-amount','2000000');
await setField('bank-direction','CREDIT');
await click('bank-create');
const createdStatus=await waitFor('[data-testid="bank-status-1"]',element=>element.textContent==='DRAFT');
assert(createdStatus.textContent==='DRAFT','Statement did not enter DRAFT state');
const createdIdentity=(await waitFor('[data-testid="bank-created-by-1"]')).textContent||'';
assert(createdIdentity.includes('R7 Treasury Maker')&&createdIdentity.includes('@r7_treasury_maker'),`Maker identity missing: ${createdIdentity}`);

// The maker can see the match control, but the API must block self-matching.
await click('bank-match-1');
assert((container.textContent||'').includes('statement creator cannot complete reconciliation'),'Maker-checker rejection was not shown in the UI');
assert((await waitFor('[data-testid="bank-status-1"]')).textContent==='DRAFT','Self-match changed statement state');

// Local search includes employee identity and makes no extra HTTP request.
const requestsBeforeSearch=httpAudit.length;
await setField('bank-search','r7_treasury_maker');
assert((await waitFor('[data-testid="bank-search-count"]')).textContent==='1/1','Identity search did not find the statement');
await setField('bank-search','no-such-statement');
assert((await waitFor('[data-testid="bank-search-count"]')).textContent==='0/1','Non-matching local search did not filter the row');
assert(httpAudit.length===requestsBeforeSearch,'Local search unexpectedly called the server');

// Employee 2 independently matches the bank line.
await renderAs('matcher');
await waitFor('[data-testid="bank-status-1"]',element=>element.textContent==='DRAFT');
await click('bank-match-1');
await waitFor('[data-testid="bank-status-1"]',element=>element.textContent==='MATCHED');
const matchedIdentity=(await waitFor('[data-testid="bank-matched-by-1"]')).textContent||'';
assert(matchedIdentity.includes('R7 Treasury Matcher')&&matchedIdentity.includes('@r7_treasury_matcher'),`Matcher identity missing: ${matchedIdentity}`);
assert(((await waitFor('[data-testid="bank-workflow-1"]')).textContent||'').includes('MATCH ✓'),'MATCH workflow state not rendered');

// Employee 3, with bank.reconcile only, performs final reconciliation.
await renderAs('reconciler');
await waitFor('[data-testid="bank-status-1"]',element=>element.textContent==='MATCHED');
await click('bank-reconcile-1');
await waitFor('[data-testid="bank-status-1"]',element=>element.textContent==='RECONCILED');
const finalMaker=(await waitFor('[data-testid="bank-created-by-1"]')).textContent||'';
const finalMatcher=(await waitFor('[data-testid="bank-matched-by-1"]')).textContent||'';
const finalReconciler=(await waitFor('[data-testid="bank-reconciled-by-1"]')).textContent||'';
assert(finalMaker.includes('R7 Treasury Maker'),'Final maker identity missing');
assert(finalMatcher.includes('R7 Treasury Matcher'),'Final matcher identity missing');
assert(finalReconciler.includes('R7 Treasury Controller')&&finalReconciler.includes('@r7_treasury_controller'),`Reconciler identity missing: ${finalReconciler}`);
const finalWorkflow=(await waitFor('[data-testid="bank-workflow-1"]')).textContent||'';
assert(finalWorkflow.includes('CREATE ✓')&&finalWorkflow.includes('MATCH ✓')&&finalWorkflow.includes('RECONCILE ✓'),`Final workflow is incomplete: ${finalWorkflow}`);

// The rendered export button downloads the real endpoint and the CSV carries
// the document number, balances, final state and all three SoD identities.
await click('bank-export');
// The response body and anchor click complete asynchronously after the button
// handler returns.  Wait for those observable effects instead of relying on a
// fixed delay, otherwise a slower fresh migration can make this test flaky.
await waitUntil(()=>exportCapture!==null&&downloadedFilename!=='','Treasury CSV endpoint or browser download did not complete');
assert(exportCapture,'Treasury CSV endpoint was not requested by the UI');
assert(downloadedFilename==='bank_statements_1.csv',`Unexpected downloaded filename: ${downloadedFilename}`);
assert(exportCapture.contentType.includes('text/csv'),`Unexpected export content type: ${exportCapture.contentType}`);
assert(exportCapture.contentDisposition.includes('bank_statements_1.csv'),`Missing CSV content disposition: ${exportCapture.contentDisposition}`);
const csvText=exportCapture.text;
for(const expected of ['Statement number','Bank code','Statement date','Opening balance','Closing balance','Created by username','Matched by username','Reconciled by username','BANK-STMT-1-000001','BANK-01','2026-01-01','2000000.00','RECONCILED','R7 Treasury Maker','r7_treasury_maker','R7 Treasury Matcher','r7_treasury_matcher','R7 Treasury Controller','r7_treasury_controller'])assert(csvText.includes(expected),`CSV content missing ${expected}: ${csvText}`);

activeRole='verification';
const finalStatements=await json('/api/v1/banking/statements?company_id=1',{headers:{Authorization:`Bearer ${sessions.reconciler.access_token}`}});
const finalStatement=finalStatements.find((row:any)=>row.id===1);
assert(finalStatement?.status==='RECONCILED','API final state is not RECONCILED');
assert(finalStatement.created_by_user?.id===sessions.maker.user.id,'API maker identity mismatch');
assert(finalStatement.matched_by_user?.id===sessions.matcher.user.id,'API matcher identity mismatch');
assert(finalStatement.reconciled_by_user?.id===sessions.reconciler.user.id,'API reconciler identity mismatch');
assert(!httpAudit.some(row=>row.status>=500),`Server errors detected: ${JSON.stringify(httpAudit.filter(row=>row.status>=500))}`);

const result={
  database:'fresh isolated SQLite database supplied by runner',
  statement_id:finalStatement.id,
  state_sequence:['DRAFT','MATCHED','RECONCILED'],
  employees:{maker:sessions.maker.user.id,matcher:sessions.matcher.user.id,reconciler:sessions.reconciler.user.id},
  identities_visible:{maker:finalMaker,matcher:finalMatcher,reconciler:finalReconciler},
  maker_self_match_status:httpAudit.find(row=>row.role==='maker'&&row.path.endsWith('/auto-match')&&row.method==='POST')?.status,
  local_search:{identity_result:'1/1',non_match_result:'0/1',server_requests:0},
  csv_export:{filename:downloadedFilename,content_type:exportCapture.contentType,statement_number:'BANK-STMT-1-000001',status:'RECONCILED',identity_columns:3,bytes:new TextEncoder().encode(csvText).length},
  workflow_text:finalWorkflow,
  requests:httpAudit.length,
  writes:httpAudit.filter(row=>row.method!=='GET').length,
  server_errors:httpAudit.filter(row=>row.status>=500).length,
};
console.log(JSON.stringify(result,null,2));
if(root)await act(async()=>root?.unmount());
container.remove();
