import {randomUUID} from 'node:crypto';
import {dirname} from 'node:path';
import {mkdirSync, writeFileSync} from 'node:fs';
import {Window} from 'happy-dom';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import userEvent from '@testing-library/user-event';

type Result={name:string;pass:boolean;details:Record<string,unknown>};
type HttpCall={method:string;path:string;status:number;detail:string};

const baseUrl=process.env.CORVAX_UAT_BASE_URL||'http://127.0.0.1:8791';
const outputPath=process.env.CORVAX_UAT_OUTPUT||'/tmp/corvax_gym_ui_final.json';
const adminEmail=process.env.CORVAX_UAT_ADMIN_EMAIL||'admin@corvaxplatform.com';
const adminPassword=process.env.CORVAX_UAT_ADMIN_PASSWORD;
const companyId=Number(process.env.CORVAX_UAT_COMPANY_ID||2);
const anchorDate=process.env.CORVAX_UAT_ANCHOR_DATE||new Date().toISOString().slice(0,10);
const runId=randomUUID().replaceAll('-','').slice(0,12).toUpperCase();
const reviewerEmail=`gym.ui.reviewer.${runId.toLowerCase()}@example.invalid`;
const reviewerPassword=`Gym!${runId}a9#`;
const memberNumber=`UI-GYM-${runId}`;
const results:Result[]=[];
const calls:HttpCall[]=[];

if(!adminPassword)throw new Error('CORVAX_UAT_ADMIN_PASSWORD is required; credentials are never stored in this test file');
if(!Number.isInteger(companyId)||companyId<=0)throw new Error('CORVAX_UAT_COMPANY_ID must be a positive integer');
if(!/^\d{4}-\d{2}-\d{2}$/.test(anchorDate))throw new Error('CORVAX_UAT_ANCHOR_DATE must use YYYY-MM-DD');

function addDays(value:string,days:number){
  const date=new Date(`${value}T12:00:00Z`);date.setUTCDate(date.getUTCDate()+days);return date.toISOString().slice(0,10);
}
function dateTime(days:number,time:string){return `${addDays(anchorDate,days)}T${time}`}
function record(name:string,pass:boolean,details:Record<string,unknown>={}){results.push({name,pass,details})}
function saveEvidence(summary:Record<string,unknown>){
  mkdirSync(dirname(outputPath),{recursive:true});writeFileSync(outputPath,JSON.stringify(summary,null,2),'utf8');
}

const windowInstance=new Window({url:`${baseUrl}/#/gym`});
Object.assign(globalThis,{
  window:windowInstance,document:windowInstance.document,localStorage:windowInstance.localStorage,
  sessionStorage:windowInstance.sessionStorage,HTMLElement:windowInstance.HTMLElement,
  HTMLInputElement:windowInstance.HTMLInputElement,HTMLSelectElement:windowInstance.HTMLSelectElement,
  HTMLTextAreaElement:windowInstance.HTMLTextAreaElement,Event:windowInstance.Event,
  CustomEvent:windowInstance.CustomEvent,MouseEvent:windowInstance.MouseEvent,
  KeyboardEvent:windowInstance.KeyboardEvent,React,
});
Object.defineProperty(globalThis,'navigator',{value:windowInstance.navigator,configurable:true});
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
const originalConsoleError=console.error;
console.error=(...args:unknown[])=>{if(!String(args[0]||'').includes('not wrapped in act'))originalConsoleError(...args)};

const nativeFetch=globalThis.fetch;
globalThis.fetch=(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const raw=typeof input==='string'?input:input instanceof URL?input.toString():input.url;
  const url=raw.startsWith('/')?`${baseUrl}${raw}`:raw;
  const response=await nativeFetch(url,init);
  const detail=response.status>=400?await response.clone().text().catch(()=>''):'';
  calls.push({method:String(init?.method||'GET').toUpperCase(),path:url.replace(baseUrl,''),status:response.status,detail:detail.slice(0,500)});
  return response;
}) as typeof fetch;

async function api(path:string,init:RequestInit={}){
  const headers=new Headers(init.headers);const token=sessionStorage.getItem('corvax_token');
  if(token)headers.set('Authorization',`Bearer ${token}`);
  const response=await fetch(path,{...init,headers});const body=await response.json().catch(()=>null);
  if(!response.ok)throw new Error(`${response.status} ${JSON.stringify(body)}`);return body;
}
async function login(email:string,password:string){
  const value=await api('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
  sessionStorage.setItem('corvax_token',value.access_token);localStorage.setItem('corvax_user',JSON.stringify(value.user));return value;
}
const delay=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));

async function main(){
  const admin=await login(adminEmail,adminPassword);
  const jsonHeaders={'Content-Type':'application/json'};
  await api('/api/v1/admin/users',{method:'POST',headers:jsonHeaders,body:JSON.stringify({
    name_ar:`مراجع عمليات النادي ${runId}`,name_en:`Gym Operations Reviewer ${runId}`,email:reviewerEmail,
    password:reviewerPassword,require_password_change:false,memberships:[{company_id:companyId,role_code:'SUPER_ADMIN'}],
  })});
  const branches=await api(`/api/v1/enterprise/companies/${companyId}/branches`);const branch=branches[0];
  const plans=await api(`/api/v1/revenue-recognition/plans?company_id=${companyId}`);const plan=plans.find((row:any)=>row.code==='ANNUAL')||plans[0];
  const banks=await api(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`);const bank=banks[0];
  const facilities=await api(`/api/v1/gym/facilities?company_id=${companyId}`);const padel=facilities.find((row:any)=>row.code==='PADEL-C1');
  if(!branch||!plan||!bank||!padel)throw new Error('Seeded gym branch, plan, bank account or PADEL-C1 facility is missing');
  const member=await api('/api/v1/revenue-recognition/members',{method:'POST',headers:jsonHeaders,body:JSON.stringify({
    company_id:companyId,member_number:memberNumber,name_ar:`عضو واجهة ${runId}`,name_en:`Gym UI Member ${runId}`,mobile:'0502222001',
  })});
  const contract=await api('/api/v1/revenue-recognition/contracts',{method:'POST',headers:jsonHeaders,body:JSON.stringify({
    company_id:companyId,member_id:member.id,plan_id:plan.id,start_date:anchorDate,bank_account_id:bank.id,branch_id:branch.id,
  })});
  record('fresh_gym_member_and_contract',!!member.id&&contract.status==='ACTIVE',{member:member.member_number,contract:contract.number,status:contract.status});

  const {DashboardRoutes}=await import('../src/dashboard/routes');
  const container=document.createElement('div');document.body.appendChild(container);const root=createRoot(container);
  const user=userEvent.setup({document:windowInstance.document});let renderSequence=0;
  async function render(){
    localStorage.setItem('corvax_company',JSON.stringify({id:'gym',apiId:companyId,name_ar:'شركة النادي'}));renderSequence+=1;
    await act(async()=>{root.render(<DashboardRoutes key={renderSequence} ar={true} companyId={companyId} scope={'gym'} view={'gym'} onNavigate={()=>{}}/>)});
    for(let attempt=0;attempt<30;attempt+=1){await act(async()=>{await delay(100)});if(!container.querySelector('.route-loading')&&(container.textContent||'').includes('الأعضاء والعقود'))break;}
    await act(async()=>{await delay(350)});
  }
  function labels(prefix:string){return [...container.querySelectorAll('label')].filter(node=>(node.textContent||'').replace(/\s+/g,' ').trim().startsWith(prefix))}
  function control(prefix:string,index=0){
    const label=labels(prefix)[index];if(!label)throw new Error(`Missing label: ${prefix}`);
    const item=label.querySelector('input,select,textarea') as HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement|null;
    if(!item)throw new Error(`Missing control: ${prefix}`);return item;
  }
  async function setValue(prefix:string,value:string,index=0){
    const item=control(prefix,index);
    if(item.tagName==='SELECT')await user.selectOptions(item as HTMLSelectElement,value);
    else{await user.clear(item);await user.type(item,value)}
    await act(async()=>{await delay(100)});
  }
  function button(text:string,index=0){
    const items=[...container.querySelectorAll('button')].filter(node=>(node.textContent||'').replace(/\s+/g,' ').trim().includes(text));
    const item=items[index] as HTMLButtonElement|undefined;if(!item)throw new Error(`Missing button: ${text}`);return item;
  }
  async function click(text:string,index=0,waitMs=800){await user.click(button(text,index));await act(async()=>{await delay(waitMs)})}

  await render();await click('الأعضاء والعقود',0,250);
  const memberSearch=container.querySelector('[aria-label="بحث عمليات الجيم"]') as HTMLInputElement;
  await user.type(memberSearch,member.member_number);await act(async()=>{await delay(150)});
  record('member_contract_local_search',(container.textContent||'').includes(member.member_number)&&!(container.textContent||'').includes('عضو تجريبي'),{query:member.member_number});

  await click('تعديل العضوية',0,200);await setValue('عقد العضوية',String(contract.id));await setValue('نوع التعديل','FREEZE');
  await setValue('تاريخ السريان',anchorDate);await setValue('بداية التجميد',anchorDate);await setValue('نهاية التجميد',addDays(anchorDate,2));
  await setValue('سبب التعديل',`سفر العضو واختبار فصل المنشئ عن المعتمد ${runId}`);await click('إرسال للمراجعة',0,900);
  let modifications=await api(`/api/v1/gym/membership-modifications?company_id=${companyId}`);
  const freeze=modifications.find((row:any)=>row.contract_id===contract.id&&row.type==='FREEZE');
  record('freeze_submitted_from_ui',freeze?.status==='SUBMITTED',{number:freeze?.number,status:freeze?.status});
  const ownModificationStart=calls.length;await click('اعتماد التعديل',0,400);
  const ownModificationApproval=calls.slice(ownModificationStart).find(row=>row.path===`/api/v1/gym/membership-modifications/${freeze.id}/approve`);
  record('membership_maker_checker_denial',ownModificationApproval?.status===409&&(container.textContent||'').includes('Maker cannot approve own membership modification'),{status:ownModificationApproval?.status});

  const reviewer=await login(reviewerEmail,reviewerPassword);await render();await click('تعديل العضوية',0,250);await click('اعتماد التعديل',0,1000);
  modifications=await api(`/api/v1/gym/membership-modifications?company_id=${companyId}`);const approvedFreeze=modifications.find((row:any)=>row.id===freeze.id);
  let contracts=await api(`/api/v1/revenue-recognition/contracts?company_id=${companyId}`);let changedContract=contracts.find((row:any)=>row.id===contract.id);
  record('freeze_approved_by_independent_checker',approvedFreeze?.status==='APPROVED_POSTED'&&changedContract?.status==='FROZEN'&&changedContract?.end_date===addDays(contract.end_date,3),
    {reviewer_id:reviewer.user?.id,status:approvedFreeze?.status,contract_status:changedContract?.status,new_end:changedContract?.end_date});

  await click('الدخول والخروج',0,200);await setValue('العضو',String(member.id));await setValue('وقت الحركة',dateTime(1,'10:00'));
  await setValue('الاتجاه','IN');await setValue('طريقة التحقق','QR');await click('تسجيل الحركة',0,800);
  let access=await api(`/api/v1/gym/access-records?company_id=${companyId}`);const denied=access.find((row:any)=>row.member_id===member.id&&row.status==='DENIED');
  record('frozen_member_access_denied_ui',denied?.reason==='MEMBERSHIP_FROZEN'&&(container.textContent||'').includes('العضوية مجمّدة'),{status:denied?.status,reason:denied?.reason});
  await setValue('وقت الحركة',dateTime(3,'10:00'));await click('تسجيل الحركة',0,800);
  access=await api(`/api/v1/gym/access-records?company_id=${companyId}`);const granted=access.find((row:any)=>row.member_id===member.id&&row.status==='GRANTED');
  contracts=await api(`/api/v1/revenue-recognition/contracts?company_id=${companyId}`);changedContract=contracts.find((row:any)=>row.id===contract.id);
  record('automatic_unfreeze_and_access_grant_ui',!!granted&&changedContract?.status==='ACTIVE'&&(container.textContent||'').includes('تم تسجيل الحركة والسماح بالدخول'),{status:granted?.status,contract_status:changedContract?.status});

  sessionStorage.setItem('corvax_token',admin.access_token);localStorage.setItem('corvax_user',JSON.stringify(admin.user));await render();await click('حجز المرافق',0,250);
  await setValue('المرفق',String(padel.id));await setValue('العضو',String(member.id));await setValue('عقد العضوية',String(contract.id));
  await setValue('وقت البداية',dateTime(4,'18:00'));await setValue('وقت النهاية',dateTime(4,'19:30'));await setValue('عدد المشاركين','4');
  await setValue('حساب التحصيل',String(bank.id));await setValue('ملاحظات الحجز',`حجز بادل مدفوع ${runId}`);await click('إنشاء الحجز',0,1000);
  let bookings=await api(`/api/v1/gym/facility-bookings?company_id=${companyId}`);const booking=bookings.find((row:any)=>row.member_id===member.id&&row.facility_id===padel.id);
  record('paid_facility_booking_submitted_ui',booking?.status==='SUBMITTED'&&Number(booking?.total_amount)===276,{number:booking?.number,status:booking?.status,total:booking?.total_amount});
  const ownBookingStart=calls.length;await click('اعتماد الحجز',0,400);
  const ownBookingApproval=calls.slice(ownBookingStart).find(row=>row.path===`/api/v1/gym/facility-bookings/${booking.id}/approve`);
  record('facility_booking_maker_checker_denial',ownBookingApproval?.status===409&&(container.textContent||'').includes('Maker cannot approve own paid booking'),{status:ownBookingApproval?.status});

  await login(reviewerEmail,reviewerPassword);await render();await click('حجز المرافق',0,250);await click('اعتماد الحجز',0,1000);
  bookings=await api(`/api/v1/gym/facility-bookings?company_id=${companyId}`);const approvedBooking=bookings.find((row:any)=>row.id===booking.id);
  record('facility_booking_approved_and_posted_ui',approvedBooking?.status==='CONFIRMED'&&!!approvedBooking?.sale_journal_id,{status:approvedBooking?.status,sale_journal_id:approvedBooking?.sale_journal_id});
  const bookingSearch=container.querySelector('[aria-label="بحث عمليات الجيم"]') as HTMLInputElement;
  await user.type(bookingSearch,booking.number);await act(async()=>{await delay(150)});
  const visibleBookingNumbers=[...container.querySelectorAll('[role="cell"]')].filter(cell=>(cell.textContent||'').trim()===booking.number).length;
  record('facility_booking_local_search',visibleBookingNumbers===1,{query:booking.number,visible_rows:visibleBookingNumbers});

  await act(async()=>root.unmount());container.remove();
  const expectedConflictPaths=new Set([
    `/api/v1/gym/membership-modifications/${freeze.id}/approve`,
    `/api/v1/gym/facility-bookings/${booking.id}/approve`,
  ]);
  const expected409=calls.filter(row=>row.status===409&&expectedConflictPaths.has(row.path)).length;
  const unexpectedErrors=calls.filter(row=>row.status>=400&&!(row.status===409&&expectedConflictPaths.has(row.path)));
  const summary={
    suite:'gym_employee_workflow_simulation',run_id:runId,run_at:new Date().toISOString(),anchor_date:anchorDate,company_id:companyId,
    passed:results.filter(row=>row.pass).length,total:results.length,failed:results.filter(row=>!row.pass),results,
    requests:{total:calls.length,writes:calls.filter(row=>row.method!=='GET').length,expected_409:expected409,
      unexpected_errors:unexpectedErrors.map(row=>({method:row.method,path:row.path,status:row.status,detail:row.detail})),
      statuses:calls.reduce((out:Record<string,number>,row)=>{out[row.status]=(out[row.status]||0)+1;return out},{})},
  };
  saveEvidence(summary);console.log(`GYM_UI_EVIDENCE=${outputPath}`);console.log(JSON.stringify(summary));
  if(summary.failed.length||unexpectedErrors.length)process.exitCode=2;
}

main().catch(error=>{
  const summary={suite:'gym_employee_workflow_simulation',run_id:runId,run_at:new Date().toISOString(),anchor_date:anchorDate,
    company_id:companyId,passed:results.filter(row=>row.pass).length,total:results.length,failed:results.filter(row=>!row.pass),results,
    fatal_error:String((error as Error)?.stack||error),requests:{total:calls.length,writes:calls.filter(row=>row.method!=='GET').length}};
  saveEvidence(summary);console.error('GYM_UI_FATAL',error);console.error(`GYM_UI_EVIDENCE=${outputPath}`);process.exitCode=1;
});
