import {Window} from 'happy-dom';

const baseUrl=process.env.CORVAX_UAT_BASE_URL||'http://127.0.0.1:8139';
const windowInstance=new Window({url:`${baseUrl}/#/manufacturing`});
Object.assign(globalThis,{
  window:windowInstance,
  document:windowInstance.document,
  localStorage:windowInstance.localStorage,
  sessionStorage:windowInstance.sessionStorage,
  HTMLElement:windowInstance.HTMLElement,
  HTMLInputElement:windowInstance.HTMLInputElement,
  HTMLSelectElement:windowInstance.HTMLSelectElement,
  HTMLButtonElement:windowInstance.HTMLButtonElement,
  Event:windowInstance.Event,
  CustomEvent:windowInstance.CustomEvent,
  MouseEvent:windowInstance.MouseEvent,
});
Object.defineProperty(globalThis,'navigator',{value:windowInstance.navigator,configurable:true});
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;

const React=await import('react');
const {act}=React;
const {createRoot}=await import('react-dom/client');
const {ManufacturingPage}=await import('../src/dashboard/operationsRealPages');

type AuditRow={role:string;method:string;path:string;status:number};
const nativeFetch=globalThis.fetch;
const httpAudit:AuditRow[]=[];
let activeRole='setup';
globalThis.fetch=(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const raw=typeof input==='string'?input:input instanceof URL?input.toString():input.url;
  const url=raw.startsWith('/')?`${baseUrl}${raw}`:raw;
  const response=await nativeFetch(url,init);
  httpAudit.push({role:activeRole,method:String(init?.method||'GET').toUpperCase(),path:new URL(url).pathname,status:response.status});
  return response;
}) as typeof fetch;

const delay=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
function assert(condition:unknown,message:string):asserts condition{if(!condition)throw new Error(message)}
async function json(url:string,init?:RequestInit){
  const response=await fetch(url,init);const payload=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(`${response.status}: ${JSON.stringify(payload)}`);
  return payload;
}
async function login(email:string,password:string){return json('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})})}
async function createUser(adminToken:string,data:any){return json('/api/v1/admin/users',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${adminToken}`},body:JSON.stringify(data)})}
async function waitFor(selector:string,predicate:(element:Element)=>boolean=()=>true,timeoutMs=7000){
  const start=Date.now();
  while(Date.now()-start<timeoutMs){
    const element=document.querySelector(selector);
    if(element&&predicate(element))return element;
    await act(async()=>{await delay(50)});
  }
  throw new Error(`Timed out waiting for ${selector}: ${document.body.textContent?.slice(-1400)}`);
}
let reactPropsKey:string|undefined;
function reactProps(element:any){
  const key=reactPropsKey||Reflect.ownKeys(element).find(name=>typeof name==='string'&&name.startsWith('__reactProps$')) as string|undefined;
  assert(key,`React props were not found for ${element.tagName}: ${Reflect.ownKeys(element).map(String).slice(-20).join(', ')}`);
  reactPropsKey=key;
  return element[key];
}
async function setField(testId:string,value:string){
  const element=await waitFor(`[data-testid="${testId}"]`) as HTMLInputElement|HTMLSelectElement;
  await act(async()=>{
    element.value=value;
    const props=reactProps(element);
    assert(typeof props.onChange==='function',`${testId} has no React onChange handler`);
    props.onChange({target:element,currentTarget:element});
    await delay(35);
  });
}
async function click(testId:string){
  const element=await waitFor(`[data-testid="${testId}"]`) as HTMLButtonElement;
  assert(!element.disabled,`${testId} is disabled`);
  await act(async()=>{
    const props=reactProps(element);
    assert(typeof props.onClick==='function',`${testId} has no React onClick handler`);
    await props.onClick({target:element,currentTarget:element,preventDefault:()=>undefined});
    await delay(150);
  });
}
function selectValue(testId:string,needle:string){
  const element=document.querySelector(`[data-testid="${testId}"]`) as HTMLSelectElement|null;
  assert(element,`${testId} select is missing`);
  const option=[...element.options].find(row=>row.textContent?.includes(needle));
  assert(option,`${needle} option is missing from ${testId}`);
  return option.value;
}

const admin=await login('admin@corvaxplatform.com','Corvax@123');
const employees=[
  {role:'production_manager',name_ar:'مدير إنتاج محاكاة MRP',name_en:'MRP Production Manager',username:'r7_mrp_production',email:'r7.mrp.production@corvaxplatform.com',password:'R7MrpProduction@123',role_code:'PRODUCTION_MANAGER'},
  {role:'cfo',name_ar:'مدير مالي اعتماد MRP',name_en:'MRP CFO Approver',username:'r7_mrp_cfo',email:'r7.mrp.cfo@corvaxplatform.com',password:'R7MrpCfoApprove@123',role_code:'CFO'},
];
for(const employee of employees){
  await createUser(admin.access_token,{name_ar:employee.name_ar,name_en:employee.name_en,username:employee.username,email:employee.email,password:employee.password,require_password_change:false,memberships:[{company_id:4,role_code:employee.role_code}]});
}
const sessions:Record<string,any>={};
for(const employee of employees)sessions[employee.role]=await login(employee.email,employee.password);
assert(sessions.production_manager.user.id!==sessions.cfo.user.id,'Maker and approver must be different employees');

const container=document.createElement('div');document.body.appendChild(container);
let root:ReturnType<typeof createRoot>|null=null;
async function renderAs(role:'production_manager'|'cfo'){
  activeRole=role;
  sessionStorage.setItem('corvax_token',sessions[role].access_token);
  localStorage.setItem('corvax_user',JSON.stringify(sessions[role].user));
  if(root)await act(async()=>root?.unmount());
  container.replaceChildren();root=createRoot(container);
  await act(async()=>{root?.render(<ManufacturingPage ar={false} companyId={4}/>);await delay(350)});
  await waitFor('[data-testid="manufacturing-bom-finished-item"]',element=>(element as HTMLSelectElement).options.length>=3);
  await waitFor('[data-testid="manufacturing-bom-work-center"]',element=>(element as HTMLSelectElement).options.length>=2);
}

await renderAs('production_manager');
await setField('manufacturing-bom-code','BOM-UI-MRP-001');
await setField('manufacturing-bom-version','2');
await setField('manufacturing-bom-finished-item',selectValue('manufacturing-bom-finished-item','FG-001'));
await setField('manufacturing-bom-output-qty','1');
await setField('manufacturing-bom-component',selectValue('manufacturing-bom-component','RAW-001'));
await setField('manufacturing-bom-component-qty','2');
await setField('manufacturing-bom-work-center',selectValue('manufacturing-bom-work-center','LINE-01'));
await click('manufacturing-bom-create');
await waitFor('[data-testid="manufacturing-bom-list"]',element=>(element.textContent||'').includes('BOM-UI-MRP-001'));

activeRole='maker_verification';
const makerHeaders={Authorization:`Bearer ${sessions.production_manager.access_token}`};
const boms=await json('/api/v1/manufacturing/boms?company_id=4',{headers:makerHeaders});
const createdBom=boms.find((row:any)=>row.code==='BOM-UI-MRP-001'&&row.version===2);
assert(createdBom,'Created BOM is absent from the API list');
assert(createdBom.finished_item_code==='FG-001','BOM finished item mismatch');
assert(createdBom.lines?.length===1&&createdBom.lines[0].component_code==='RAW-001','BOM component mismatch');
assert(Number(createdBom.lines[0].quantity)===2,'BOM component quantity mismatch');
assert(createdBom.work_center==='Production Line 01','BOM work center mismatch');

activeRole='production_manager';
await setField('manufacturing-mrp-warehouse',selectValue('manufacturing-mrp-warehouse','MAIN'));
await setField('manufacturing-mrp-demand-item',selectValue('manufacturing-mrp-demand-item','FG-001'));
await setField('manufacturing-mrp-demand-qty','7000');
await setField('manufacturing-mrp-source-reference','UI-MRP-FORECAST-001');
await click('manufacturing-mrp-create');
await waitFor('[data-testid="manufacturing-mrp-list"]',element=>(element.textContent||'').includes('CALCULATED'));

activeRole='maker_verification';
const calculatedRuns=await json('/api/v1/manufacturing/advanced/mrp-runs?company_id=4',{headers:makerHeaders});
const run=calculatedRuns.find((row:any)=>row.demands?.some((d:any)=>d.source_reference==='UI-MRP-FORECAST-001'));
assert(run,'MRP run created through the UI was not found');
assert(run.status==='CALCULATED','MRP run did not enter CALCULATED state');
assert(run.created_by===sessions.production_manager.user.id,'MRP preparer identity mismatch');
assert(run.requirements?.some((row:any)=>row.item_code==='FG-001'&&row.bom_id===createdBom.id),'MRP did not use the newly created BOM version');

activeRole='production_manager';
const requestsBeforeSearch=httpAudit.length;
await setField('manufacturing-search','BOM-UI-MRP-001');
assert((document.querySelector('[data-testid="manufacturing-bom-list"]')?.textContent||'').includes('BOM-UI-MRP-001'),'Local BOM search did not retain the matching row');
await setField('manufacturing-search','UI-MRP-FORECAST-001');
assert((document.querySelector('[data-testid="manufacturing-mrp-list"]')?.textContent||'').includes(run.code),'Local MRP reference search did not retain the matching run');
await setField('manufacturing-search','NO-SUCH-MANUFACTURING-ROW');
assert((document.querySelector('[data-testid="manufacturing-bom-list"]')?.textContent||'').includes('No data available'),'Local BOM search did not hide non-matching rows');
assert((document.querySelector('[data-testid="manufacturing-mrp-list"]')?.textContent||'').includes('No data available'),'Local MRP search did not hide non-matching rows');
assert(httpAudit.length===requestsBeforeSearch,'Local search unexpectedly made an HTTP request');
await setField('manufacturing-search','');

await click(`manufacturing-mrp-approve-${run.id}`);
const makerApproval=httpAudit.findLast(row=>row.role==='production_manager'&&row.path.endsWith(`/mrp-runs/${run.id}/approve`)&&row.method==='POST');
assert(makerApproval?.status===403,`Production manager approval should be denied with 403, received ${makerApproval?.status}`);

await renderAs('cfo');
await waitFor(`[data-testid="manufacturing-mrp-approve-${run.id}"]`);
await click(`manufacturing-mrp-approve-${run.id}`);
await waitFor('[data-testid="manufacturing-mrp-list"]',element=>(element.textContent||'').includes('APPROVED'));

activeRole='final_verification';
const finalRuns=await json('/api/v1/manufacturing/advanced/mrp-runs?company_id=4',{headers:{Authorization:`Bearer ${sessions.cfo.access_token}`}});
const approved=finalRuns.find((row:any)=>row.id===run.id);
assert(approved?.status==='APPROVED','CFO approval was not persisted');
assert(approved.approved_by===sessions.cfo.user.id,'MRP approver identity mismatch');
assert(!httpAudit.some(row=>row.status>=500),`Server errors detected: ${JSON.stringify(httpAudit.filter(row=>row.status>=500))}`);

const result={
  database:'fresh isolated SQLite database supplied by runner',
  bom:{id:createdBom.id,code:createdBom.code,version:createdBom.version,finished_item:createdBom.finished_item_code,component:createdBom.lines[0].component_code,component_quantity:Number(createdBom.lines[0].quantity),work_center:createdBom.work_center},
  mrp:{id:approved.id,code:approved.code,status:approved.status,gross_demand:Number(approved.gross_demand),planned_supply:Number(approved.total_planned_supply),source_reference:approved.demands[0].source_reference},
  employees:{preparer:sessions.production_manager.user.id,approver:sessions.cfo.user.id,separate:sessions.production_manager.user.id!==sessions.cfo.user.id},
  controls:{production_manager_approval_status:makerApproval?.status,cfo_approval_status:httpAudit.findLast(row=>row.role==='cfo'&&row.path.endsWith(`/mrp-runs/${run.id}/approve`)&&row.method==='POST')?.status,local_search_server_requests:0},
  http:{requests:httpAudit.length,writes:httpAudit.filter(row=>row.method!=='GET').length,server_errors:httpAudit.filter(row=>row.status>=500).length},
};
console.log(JSON.stringify(result,null,2));
if(root)await act(async()=>root?.unmount());
container.remove();
