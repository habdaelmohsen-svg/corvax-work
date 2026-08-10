import {useEffect, useState} from 'react';
import {Users, KeyRound, ShieldCheck, UserPlus, Lock, Unlock, RotateCcw} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

// User management: create employees with a short login name and a temporary
// password, force them to replace it at first sign-in, reset passwords, unlock
// accounts and enable or disable access.

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    throw new Error(typeof d==='string'?d:(Array.isArray(d)?d.map((i:any)=>i.msg||JSON.stringify(i)).join(' | '):JSON.stringify(d||x)));
  }
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'4px 10px',borderRadius:7,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;
const grid={display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12} as const;

function normaliseUsername(value:string){
  return value.trim().toLowerCase().replace(/\s+/g,'.').replace(/[._-]{2,}/g,'.').replace(/^[._-]+|[._-]+$/g,'');
}
function validUsername(value:string){
  return value.length>=3 && [...value].every((character)=>/[\p{L}\p{N}._-]/u.test(character));
}
function validEmail(value:string){return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)}

type Row={id:number;name_ar:string;name_en:string;email:string;username?:string;active:boolean;require_password_change?:boolean;locked_until?:string|null;memberships?:{company_id:number;role:string}[]};

const ROLES:[string,string,string][]=[
  ['SUPER_ADMIN','مدير النظام','System administrator'],
  ['CFO','مدير مالي','CFO'],
  ['FINANCIAL_CONTROLLER','مراقب مالي','Financial controller'],
  ['ACCOUNTANT','محاسب','Accountant'],
  ['AUDITOR','مراجع','Auditor'],
  ['SALES_MANAGER','مدير مبيعات','Sales manager'],
  ['HR_MANAGER','مدير موارد بشرية','HR manager'],
  ['PRODUCTION_MANAGER','مدير إنتاج','Production manager'],
  ['QUALITY_MANAGER','مدير جودة','Quality manager'],
  ['IT_MANAGER','مدير تقنية','IT manager'],
  ['RESTAURANT_MANAGER','مدير مطعم','Restaurant manager'],
  ['GYM_MANAGER','مدير النادي','Gym manager'],
  ['GYM_TRAINER','مدرب النادي','Gym trainer'],
  ['GYM_CAFE_CASHIER','كاشير كافيه النادي','Gym cafe cashier'],
  ['GYM_FACILITY_SUPERVISOR','مشرف مرافق النادي','Gym facility supervisor'],
];

export function UsersPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [rows,setRows]=useState<Row[]>([]);
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);
  const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [username,setUsername]=useState(''); const [email,setEmail]=useState('');
  const [password,setPassword]=useState(''); const [role,setRole]=useState('ACCOUNTANT');
  const [resetPw,setResetPw]=useState('');

  const load=async()=>{
    try{const r=await json(`/api/v1/admin/users?company_id=${companyId}`);setRows(Array.isArray(r)?r:[]);}
    catch(e:any){setMsg(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const create=async()=>{
    const login=normaliseUsername(username||nameEn);
    const resolvedEmail=(email.trim()||`${login}@corvax.local`).toLowerCase();
    if(!nameAr.trim()||!nameEn.trim()||!login||!password){setMsg(ar?'الاسمان وكلمة المرور إلزامية، واسم الدخول يُنشأ تلقائيًا من الاسم الإنجليزي':'Names and password are required; the login is generated from the English name');return;}
    if(!validUsername(login)){setMsg(ar?'اسم الدخول يجب أن يكون 3 أحرف على الأقل، ويقبل الحروف والأرقام والنقطة والشرطة فقط. مثال: hussein.mahmoud':'Username needs at least 3 characters and may contain letters, numbers, dot, dash or underscore. Example: hussein.mahmoud');return;}
    if(!validEmail(resolvedEmail)){setMsg(ar?'صيغة البريد غير صحيحة. اتركه فارغًا ليُنشئه النظام تلقائيًا.':'The email format is invalid. Leave it blank to generate one automatically.');return;}
    if(password.length<6){setMsg(ar?'كلمة المرور المؤقتة 6 أحرف على الأقل':'Temporary password needs at least 6 characters');return;}
    setBusy(true);setMsg('');
    try{
      const body={company_id:companyId,name_ar:nameAr.trim(),name_en:nameEn.trim(),
        username:login,
        email:resolvedEmail,
        password,require_password_change:true,
        memberships:[{company_id:companyId,role_code:role}]};
      const r=await json('/api/v1/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar
        ? `تم إنشاء المستخدم "${r.username||login}" — سيُطلب منه تغيير كلمة المرور عند أول دخول`
        : `User "${r.username||login}" created — a password change will be required at first sign-in`);
      setNameAr('');setNameEn('');setUsername('');setEmail('');setPassword('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const reset=async(id:number,name:string)=>{
    if(!resetPw||resetPw.length<6){setMsg(ar?'أدخل كلمة مرور مؤقتة (6 أحرف على الأقل) في الحقل أعلاه':'Enter a temporary password (min 6 characters) in the field above');return;}
    setBusy(true);setMsg('');
    try{await json(`/api/v1/admin/users/${id}/reset-password`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,new_password:resetPw,require_change:true})});
      setMsg(ar?`تمت إعادة تعيين كلمة مرور ${name} — سيُطلب تغييرها عند الدخول`:`Password reset for ${name} — change required at next sign-in`);
      setResetPw('');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const unlock=async(id:number)=>{
    setBusy(true);setMsg('');
    try{await json(`/api/v1/admin/users/${id}/unlock?company_id=${companyId}`,{method:'POST'});
      setMsg(ar?'تم فتح الحساب':'Account unlocked');await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };
  const toggle=async(id:number,active:boolean)=>{
    setBusy(true);setMsg('');
    // This endpoint takes company_id and active as query parameters, not a body.
    try{await json(`/api/v1/admin/users/${id}/status?company_id=${companyId}&active=${!active}`,{method:'PATCH'});
      setMsg(active?(ar?'تم تعطيل الحساب':'Account disabled'):(ar?'تم تنشيط الحساب':'Account enabled'));await load();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  const pending=rows.filter(r=>r.require_password_change).length;
  const disabled=rows.filter(r=>!r.active).length;
  const label=(v:string)=>{const f=ROLES.find(x=>x[0]===v);return f?(ar?f[1]:f[2]):v;};

  return <>
    <div className="kpis">
      <Kpi title={ar?'المستخدمون':'Users'} value={String(rows.length)} trend="" good icon={<Users size={22}/>} tone="blue"/>
      <Kpi title={ar?'بانتظار تغيير كلمة المرور':'Pending password change'} value={String(pending)} trend="" good={pending===0} icon={<KeyRound size={22}/>} tone="amber"/>
      <Kpi title={ar?'حسابات معطّلة':'Disabled'} value={String(disabled)} trend="" good={disabled===0} icon={<Lock size={22}/>} tone="violet"/>
      <Kpi title={ar?'حسابات نشطة':'Active'} value={String(rows.filter(r=>r.active).length)} trend="" good icon={<ShieldCheck size={22}/>} tone="green"/>
    </div>
    {msg&&<div style={{padding:11,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14,lineHeight:1.7}}>{msg}</div>}

    <Panel title={ar?'إضافة مستخدم جديد':'Add a new user'} icon={<UserPlus size={18}/>}>
      <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.8,lineHeight:1.8}}>
        {ar
          ? 'يُنشئ النظام اسم الدخول تلقائيًا من الاسم الإنجليزي، ويمكنك تعديله. سيدخل الموظف به مع كلمة المرور المؤقتة مرة واحدة، ثم يضع كلمة مرور خاصة به.'
          : 'The login is generated from the English name and can be edited. The employee uses it with the temporary password once, then sets a private password.'}
      </div>
      <div style={grid}>
        <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
        <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
        <label>{ar?'اسم المستخدم (للدخول) — تلقائي':'Username (for sign-in) — automatic'}<input style={field} value={username} onChange={e=>setUsername(e.target.value)} onBlur={()=>setUsername(normaliseUsername(username||nameEn))} placeholder={normaliseUsername(nameEn)||'hussein.mahmoud'}/>
          {(username||nameEn)&&<small style={{display:'block',marginTop:4,color:validUsername(normaliseUsername(username||nameEn))?'#166534':'#b91c1c'}}>{ar?'اسم الدخول الفعلي: ':'Actual login: '}<b dir="ltr">{normaliseUsername(username||nameEn)||'—'}</b></small>}
        </label>
        <label>{ar?'كلمة المرور المؤقتة':'Temporary password'}<input type="password" style={field} value={password} onChange={e=>setPassword(e.target.value)}/></label>
        <label>{ar?'الدور':'Role'}<select style={field} value={role} onChange={e=>setRole(e.target.value)}>{ROLES.map(([v])=><option key={v} value={v}>{label(v)}</option>)}</select></label>
        <label>{ar?'البريد (اختياري)':'Email (optional)'}<input type="email" style={field} value={email} onChange={e=>setEmail(e.target.value)} placeholder={ar?'يُولَّد تلقائيًا':'auto-generated'}/></label>
      </div>
      <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'إنشاء المستخدم':'Create user'}</button></div>
    </Panel>

    <Panel title={ar?'كلمة مرور مؤقتة لإعادة التعيين':'Temporary password for resets'} icon={<KeyRound size={18}/>}>
      <div style={grid}>
        <label>{ar?'اكتبها هنا ثم اضغط "إعادة تعيين" أمام الموظف':'Type it here, then press "Reset" next to the employee'}
          <input style={field} value={resetPw} onChange={e=>setResetPw(e.target.value)}/></label>
      </div>
    </Panel>

    <Panel title={ar?'المستخدمون':'Users'} icon={<Users size={18}/>}>
      <DataTable
        headers={[ar?'اسم المستخدم':'Username',ar?'الاسم':'Name',ar?'البريد':'Email',ar?'الدور':'Roles',ar?'الحالة':'Status',ar?'إجراءات':'Actions']}
        rows={rows.map(u=>[
          u.username||'—',
          ar?u.name_ar:u.name_en,
          u.email,
          (u.memberships||[]).filter(m=>m.company_id===companyId).map(m=>label(m.role)).join(', ')||'—',
          <span key={`s${u.id}`}>
            {!u.active?(ar?'معطّل':'Disabled'):u.require_password_change?(ar?'يجب تغيير كلمة المرور':'Must change password'):(ar?'نشط':'Active')}
          </span>,
          <span key={`a${u.id}`} style={{display:'flex',gap:5,flexWrap:'wrap'}}>
            <button style={smallBtn} disabled={busy} onClick={()=>reset(u.id,ar?u.name_ar:u.name_en)}>{ar?'إعادة تعيين':'Reset'}</button>
            {u.locked_until&&<button style={{...smallBtn,background:'#b45309'}} disabled={busy} onClick={()=>unlock(u.id)}><Unlock size={12}/></button>}
            <button style={{...smallBtn,background:u.active?'#b91c1c':'#059669'}} disabled={busy} onClick={()=>toggle(u.id,u.active)}>
              {u.active?(ar?'تعطيل':'Disable'):(ar?'تنشيط':'Enable')}
            </button>
          </span>,
        ])}/>
    </Panel>
  </>;
}

// ==================================================== FORCED PASSWORD CHANGE
export function ForcePasswordChange({ar,onDone}:{ar:boolean;onDone:()=>void}){
  const [current,setCurrent]=useState(''); const [next,setNext]=useState(''); const [confirm,setConfirm]=useState('');
  const [msg,setMsg]=useState(''); const [busy,setBusy]=useState(false);

  const submit=async()=>{
    if(next.length<12){setMsg(ar?'كلمة المرور الجديدة 12 حرفًا على الأقل':'The new password needs at least 12 characters');return;}
    if(next!==confirm){setMsg(ar?'كلمتا المرور غير متطابقتين':'The two passwords do not match');return;}
    if(next===current){setMsg(ar?'كلمة المرور الجديدة يجب أن تختلف عن الحالية':'The new password must differ from the current one');return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/auth/password/change',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({current_password:current,new_password:next})});
      onDone();
    }catch(e:any){setMsg(String(e.message||e));}finally{setBusy(false);}
  };

  return <div style={{position:'fixed',inset:0,background:'rgba(15,23,42,0.75)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:9999,padding:20}}>
    <div style={{background:'var(--panel, #fff)',borderRadius:16,padding:26,maxWidth:460,width:'100%',boxShadow:'0 20px 60px rgba(0,0,0,0.35)'}}>
      <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:6}}>
        <KeyRound size={22}/>
        <h2 style={{margin:0,fontSize:20}}>{ar?'تغيير كلمة المرور مطلوب':'Password change required'}</h2>
      </div>
      <p style={{fontSize:14,opacity:0.8,lineHeight:1.8,marginTop:8}}>
        {ar
          ? 'كلمة المرور الحالية مؤقتة ولا يمكن الاستمرار بها. ضع كلمة مرور خاصة بك (12 حرفًا على الأقل) للمتابعة.'
          : 'Your current password is temporary and cannot be kept. Set your own password (at least 12 characters) to continue.'}
      </p>
      <label style={{display:'block',marginTop:14,fontSize:13,fontWeight:600}}>{ar?'كلمة المرور الحالية':'Current password'}
        <input type="password" style={field} value={current} onChange={e=>setCurrent(e.target.value)} autoFocus/></label>
      <label style={{display:'block',marginTop:12,fontSize:13,fontWeight:600}}>{ar?'كلمة المرور الجديدة':'New password'}
        <input type="password" style={field} value={next} onChange={e=>setNext(e.target.value)}/></label>
      <label style={{display:'block',marginTop:12,fontSize:13,fontWeight:600}}>{ar?'تأكيد كلمة المرور':'Confirm password'}
        <input type="password" style={field} value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
      {msg&&<div style={{marginTop:12,padding:10,borderRadius:9,background:'#fee2e2',color:'#991b1b',fontSize:13,lineHeight:1.7}}>{msg}</div>}
      <button style={{...btn,width:'100%',marginTop:16,padding:'11px 16px',opacity:busy?0.6:1}} disabled={busy} onClick={submit}>
        {ar?'حفظ كلمة المرور والمتابعة':'Save password and continue'}
      </button>
      <div style={{marginTop:10,fontSize:12,opacity:0.65,display:'flex',alignItems:'center',gap:6}}>
        <ShieldCheck size={13}/>{ar?'لا يستطيع أحد — بما فيهم المدير — رؤية كلمة مرورك الجديدة.':'Nobody, including the administrator, can see your new password.'}
      </div>
    </div>
  </div>;
}
