import {useEffect, useState} from 'react';
import {
  CalendarClock, CheckCircle2, DoorOpen, Dumbbell, Lock, MapPin, Plus, Search,
  ShieldCheck, Snowflake, TrendingUp, Users, XCircle,
} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// Gym operations: trainers, class types and sessions, lockers and PT packages.
//
// The accounting point that matters here is revenue recognition. A yearly
// membership or a ten-session PT package is NOT revenue on the day it is sold -
// it is deferred and released as the service is delivered. The screen states
// that plainly because getting it wrong inflates one month and empties the next.

type Branch={id:number;code:string;name_ar:string;name_en:string};
type Trainer={id:number;code:string;name_ar:string;name_en:string;commission_rate:number;active?:boolean};
type ClassType={id:number;code:string;name_ar:string;name_en:string;duration_minutes?:number;default_capacity?:number};
type Session={id:number;starts_at:string;capacity?:number;booked?:number;status?:string;
  class_type?:string;trainer?:string};
type Locker={id:number;code:string;status?:string;member?:string};
type Package={id:number;code:string;name_ar:string;name_en:string;sessions_count?:number;net_price?:number};
type Member={id:number;member_number:string;name_ar:string;name_en:string;mobile?:string};
type Contract={id:number;number:string;member:string;plan:string;start_date:string;end_date:string;status:string;
  net_amount?:number;recognized?:number;deferred?:number};
type Modification={id:number;number:string;contract_id:number;contract_number:string;type:string;effective_date:string;
  freeze_start?:string;freeze_end?:string;extension_days?:number;adjustment_net?:number;refund_total?:number;status:string;reason:string};
type Facility={id:number;code:string;name_ar:string;name_en:string;facility_type:string;capacity:number;hourly_rate?:number;status:string};
type FacilityBooking={id:number;number:string;facility_id:number;facility:string;member_id?:number;contract_id?:number;
  starts_at:string;ends_at:string;participants:number;access_mode:string;total_amount?:number;status:string};
type AccessRecord={id:number;branch_id:number;member_id:number;contract_id?:number;occurred_at:string;direction:string;
  method:string;status:string;reason?:string};
type BankAccount={id:number;code:string;bank_name_ar:string;bank_name_en:string;iban?:string};

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

const localNow=()=>{
  const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset());
  return d.toISOString().slice(0,16);
};
const localDate=(days=0)=>{
  const d=new Date(); d.setDate(d.getDate()+days); d.setMinutes(d.getMinutes()-d.getTimezoneOffset());
  return d.toISOString().slice(0,10);
};
const futureLocal=(days:number,hour:number,minute=0)=>{
  const d=new Date(); d.setDate(d.getDate()+days); d.setHours(hour,minute,0,0); d.setMinutes(d.getMinutes()-d.getTimezoneOffset());
  return d.toISOString().slice(0,16);
};

export function GymPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tab,setTab]=useState<'overview'|'members'|'memberships'|'facilities'|'access'|'trainers'|'classes'|'lockers'>('overview');
  const [branches,setBranches]=useState<Branch[]>([]);
  const [trainers,setTrainers]=useState<Trainer[]>([]);
  const [classTypes,setClassTypes]=useState<ClassType[]>([]);
  const [sessions,setSessions]=useState<Session[]>([]);
  const [lockers,setLockers]=useState<Locker[]>([]);
  const [packages,setPackages]=useState<Package[]>([]);
  const [summary,setSummary]=useState<any>(null);
  const [members,setMembers]=useState<Member[]>([]);
  const [contracts,setContracts]=useState<Contract[]>([]);
  const [modifications,setModifications]=useState<Modification[]>([]);
  const [facilities,setFacilities]=useState<Facility[]>([]);
  const [facilityBookings,setFacilityBookings]=useState<FacilityBooking[]>([]);
  const [accessRecords,setAccessRecords]=useState<AccessRecord[]>([]);
  const [bankAccounts,setBankAccounts]=useState<BankAccount[]>([]);
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  const [search,setSearch]=useState('');
  const [branch,setBranch]=useState('');
  // trainer
  const [tCode,setTCode]=useState(''); const [tAr,setTAr]=useState(''); const [tEn,setTEn]=useState(''); const [tRate,setTRate]=useState('10');
  // class type + session
  const [ctCode,setCtCode]=useState(''); const [ctAr,setCtAr]=useState(''); const [ctEn,setCtEn]=useState('');
  const [ctMin,setCtMin]=useState('60'); const [ctCap,setCtCap]=useState('20');
  const [sType,setSType]=useState(''); const [sTrainer,setSTrainer]=useState(''); const [sStart,setSStart]=useState(localNow());
  const [sCap,setSCap]=useState('');
  // locker
  const [lCode,setLCode]=useState('');
  // membership change (maker -> checker)
  const [mContract,setMContract]=useState(''); const [mType,setMType]=useState<'FREEZE'|'EXTENSION'>('FREEZE');
  const [mEffective,setMEffective]=useState(localDate()); const [mFreezeStart,setMFreezeStart]=useState(localDate());
  const [mFreezeEnd,setMFreezeEnd]=useState(localDate(2)); const [mExtensionDays,setMExtensionDays]=useState('30');
  const [mReason,setMReason]=useState(''); const [mRejectReason,setMRejectReason]=useState('');
  // facility booking
  const [bFacility,setBFacility]=useState(''); const [bMember,setBMember]=useState(''); const [bContract,setBContract]=useState('');
  const [bStarts,setBStarts]=useState(futureLocal(2,18)); const [bEnds,setBEnds]=useState(futureLocal(2,19,30));
  const [bParticipants,setBParticipants]=useState('1'); const [bBank,setBBank]=useState('');
  const [bNotes,setBNotes]=useState(''); const [bCancelReason,setBCancelReason]=useState('');
  // member access capture
  const [aMember,setAMember]=useState(''); const [aWhen,setAWhen]=useState(localNow());
  const [aDirection,setADirection]=useState<'IN'|'OUT'>('IN'); const [aMethod,setAMethod]=useState<'MANUAL'|'QR'|'CARD'>('QR');

  const load=async()=>{
    try{
      const [br,tr,ct,ss,lk,pk,sm,mb,co,mo,fa,fb,ac,ba]=await Promise.all([
        json(`/api/v1/enterprise/companies/${companyId}/branches`).catch(()=>[]),
        json(`/api/v1/gym/trainers?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/class-types?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/class-sessions?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/lockers?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/pt-packages?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/summary?company_id=${companyId}`).catch(()=>null),
        json(`/api/v1/revenue-recognition/members?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/revenue-recognition/contracts?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/membership-modifications?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/facilities?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/facility-bookings?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/gym/access-records?company_id=${companyId}`).catch(()=>[]),
        json(`/api/v1/subledgers/bank-accounts?company_id=${companyId}`).catch(()=>[]),
      ]);
      setBranches(Array.isArray(br)?br:[]); setTrainers(Array.isArray(tr)?tr:[]);
      setSessions(Array.isArray(ss)?ss:[]);
      setClassTypes(Array.isArray(ct)?ct:[]);
      setLockers(Array.isArray(lk)?lk:[]); setPackages(Array.isArray(pk)?pk:[]); setSummary(sm);
      setMembers(Array.isArray(mb)?mb:[]); setContracts(Array.isArray(co)?co:[]);
      setModifications(Array.isArray(mo)?mo:[]); setFacilities(Array.isArray(fa)?fa:[]);
      setFacilityBookings(Array.isArray(fb)?fb:[]); setAccessRecords(Array.isArray(ac)?ac:[]);
      setBankAccounts(Array.isArray(ba)?ba:[]);
      setBranch(v=>Array.isArray(br)&&br.some((x:Branch)=>String(x.id)===v)?v:(br?.[0]?.id?String(br[0].id):''));
      setSType(v=>Array.isArray(ct)&&ct.some((x:ClassType)=>String(x.id)===v)?v:(ct?.[0]?.id?String(ct[0].id):''));
      setMContract(v=>Array.isArray(co)&&co.some((x:Contract)=>String(x.id)===v)?v:(co?.[0]?.id?String(co[0].id):''));
      setBFacility(v=>Array.isArray(fa)&&fa.some((x:Facility)=>String(x.id)===v)?v:(fa?.[0]?.id?String(fa[0].id):''));
      setBMember(v=>Array.isArray(mb)&&mb.some((x:Member)=>String(x.id)===v)?v:(mb?.[0]?.id?String(mb[0].id):''));
      setBContract(v=>Array.isArray(co)&&co.some((x:Contract)=>String(x.id)===v)?v:(co?.[0]?.id?String(co[0].id):''));
      setAMember(v=>Array.isArray(mb)&&mb.some((x:Member)=>String(x.id)===v)?v:(mb?.[0]?.id?String(mb[0].id):''));
      setBBank(v=>Array.isArray(ba)&&ba.some((x:BankAccount)=>String(x.id)===v)?v:(ba?.[0]?.id?String(ba[0].id):''));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  const ok=(m:string)=>{setMsg(m);setErr(false);};
  const bad=(e:any)=>{setMsg(String(e.message||e));setErr(true);};
  const needBranch=()=>{if(!branch){bad({message:ar?'اختر الفرع أولًا':'Pick a branch first'});return true;}return false;};
  const statusLabel=(value?:string)=>{
    if(!value)return '—';
    const labels:Record<string,[string,string]>={
      ACTIVE:['نشطة','Active'],FROZEN:['مجمّدة','Frozen'],SUBMITTED:['بانتظار الاعتماد','Awaiting approval'],
      APPROVED_POSTED:['معتمدة ومُرحّلة','Approved & posted'],REJECTED:['مرفوضة','Rejected'],
      CONFIRMED:['مؤكد','Confirmed'],CANCELLED:['ملغى','Cancelled'],AVAILABLE:['متاح','Available'],
      GRANTED:['مسموح','Granted'],DENIED:['مرفوض','Denied'],IN:['دخول','In'],OUT:['خروج','Out'],
    };
    return labels[value]?.[ar?0:1]||value;
  };
  const accessReason=(value?:string)=>{
    if(!value)return ar?'عضوية صالحة':'Valid membership';
    const labels:Record<string,[string,string]>={
      NO_ACTIVE_MEMBERSHIP:['لا توجد عضوية نشطة','No active membership'],MEMBERSHIP_FROZEN:['العضوية مجمّدة','Membership frozen'],
      MEMBERSHIP_CANCELLED:['العضوية ملغاة','Membership cancelled'],OUTSIDE_MEMBERSHIP_TERM:['خارج مدة العضوية','Outside membership term'],
      WRONG_BRANCH:['العضوية مرتبطة بفرع آخر','Wrong branch'],
    };
    return labels[value]?.[ar?0:1]||value;
  };

  const addTrainer=async()=>{
    if(needBranch())return;
    if(!tCode||!tAr||!tEn){bad({message:ar?'أكمل بيانات المدرب':'Complete the trainer'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/gym/trainers',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,branch_id:Number(branch),code:tCode,
          name_ar:tAr,name_en:tEn,commission_rate:Number(tRate)||0})});
      ok(ar?`تم تسجيل المدرب ${tAr} بعمولة ${tRate}% — تُستحق عند تنفيذ الجلسة لا عند بيع الباقة`
           :`Trainer added at ${tRate}% — commission accrues when the session is delivered`);
      setTCode('');setTAr('');setTEn(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addClassType=async()=>{
    if(!ctCode||!ctAr||!ctEn){bad({message:ar?'أكمل بيانات نوع الحصة':'Complete the class type'});return;}
    setBusy(true);setMsg('');
    try{
      const r=await json('/api/v1/gym/class-types',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,code:ctCode,name_ar:ctAr,name_en:ctEn,
          duration_minutes:Number(ctMin)||60,default_capacity:Number(ctCap)||20})});
      ok(ar?'تم إنشاء نوع الحصة':'Class type created');
      setCtCode('');setCtAr('');setCtEn('');
      if(r?.id&&!sType)setSType(String(r.id));
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addSession=async()=>{
    if(needBranch())return;
    if(!sType||!sStart){bad({message:ar?'اختر نوع الحصة ووقتها':'Pick a class type and time'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,branch_id:Number(branch),class_type_id:Number(sType),
        starts_at:new Date(sStart).toISOString(),waitlist_enabled:true};
      if(sTrainer)body.trainer_id=Number(sTrainer);
      if(sCap)body.capacity=Number(sCap);
      await json('/api/v1/gym/class-sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(ar?'تم جدولة الحصة':'Session scheduled'); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const addLocker=async()=>{
    if(needBranch())return;
    if(!lCode){bad({message:ar?'أدخل رقم الخزانة':'Enter a locker code'});return;}
    setBusy(true);setMsg('');
    try{
      await json('/api/v1/gym/lockers',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,branch_id:Number(branch),code:lCode})});
      ok(ar?`تمت إضافة الخزانة ${lCode}`:`Locker ${lCode} added`);
      setLCode(''); await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const submitModification=async()=>{
    if(!mContract){bad({message:ar?'اختر عقد العضوية':'Select a membership contract'});return;}
    if(mReason.trim().length<3){bad({message:ar?'اكتب سببًا واضحًا للتعديل':'Enter a clear modification reason'});return;}
    if(mType==='FREEZE'&&(!mFreezeStart||!mFreezeEnd||mFreezeEnd<mFreezeStart)){
      bad({message:ar?'أدخل فترة تجميد صحيحة':'Enter a valid freeze period'});return;
    }
    if(mType==='EXTENSION'&&Number(mExtensionDays)<=0){bad({message:ar?'أدخل عدد أيام تمديد صحيحًا':'Enter valid extension days'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,contract_id:Number(mContract),modification_type:mType,
        effective_date:mEffective,reason:mReason.trim()};
      if(mType==='FREEZE'){body.freeze_start=mFreezeStart;body.freeze_end=mFreezeEnd;}
      else body.extension_days=Number(mExtensionDays);
      const result=await json('/api/v1/gym/membership-modifications',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(ar?`تم إرسال ${result.number} للمراجع المستقل — لا يستطيع المُنشئ اعتماده`:`${result.number} submitted to an independent checker; the maker cannot approve it`);
      setMReason('');await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const approveModification=async(id:number)=>{
    setBusy(true);setMsg('');
    try{
      const result=await json(`/api/v1/gym/membership-modifications/${id}/approve`,{method:'POST'});
      ok(ar?`تم اعتماد ${result.number} وتطبيق أثره على العقد`:`${result.number} approved and applied to the contract`);await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const rejectModification=async(id:number)=>{
    if(mRejectReason.trim().length<3){bad({message:ar?'اكتب سبب الرفض قبل التنفيذ':'Enter the rejection reason first'});return;}
    setBusy(true);setMsg('');
    try{
      const result=await json(`/api/v1/gym/membership-modifications/${id}/reject`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({reason:mRejectReason.trim()})});
      ok(ar?`تم رفض ${result.number} مع حفظ السبب`:`${result.number} rejected with a recorded reason`);setMRejectReason('');await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const submitFacilityBooking=async()=>{
    if(!bFacility||!bMember||!bContract){bad({message:ar?'اختر المرفق والعضو والعقد':'Select the facility, member and contract'});return;}
    const member=members.find(x=>String(x.id)===bMember);const contract=contracts.find(x=>String(x.id)===bContract);
    if(member&&contract&&contract.member!==member.name_en){bad({message:ar?'العقد المختار لا يخص هذا العضو':'The selected contract does not belong to this member'});return;}
    if(!bStarts||!bEnds||new Date(bEnds)<=new Date(bStarts)){bad({message:ar?'وقت النهاية يجب أن يكون بعد البداية':'End time must be after start time'});return;}
    setBusy(true);setMsg('');
    try{
      const body:any={company_id:companyId,facility_id:Number(bFacility),member_id:Number(bMember),contract_id:Number(bContract),
        starts_at:new Date(bStarts).toISOString(),ends_at:new Date(bEnds).toISOString(),participants:Number(bParticipants)||1,
        notes:bNotes.trim()||undefined};
      if(bBank)body.bank_account_id=Number(bBank);
      const result=await json('/api/v1/gym/facility-bookings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      ok(result.status==='SUBMITTED'
        ? (ar?`تم إرسال الحجز المدفوع ${result.number} لاعتماد موظف مستقل`:`Paid booking ${result.number} sent to an independent approver`)
        : (ar?`تم تأكيد الحجز ${result.number}`:`Booking ${result.number} confirmed`));
      setBNotes('');await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const approveBooking=async(id:number)=>{
    setBusy(true);setMsg('');
    try{const result=await json(`/api/v1/gym/facility-bookings/${id}/approve`,{method:'POST'});
      ok(ar?`تم اعتماد الحجز ${result.number} وترحيل إيراده`:`Booking ${result.number} approved and its revenue posted`);await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const cancelBooking=async(id:number)=>{
    if(bCancelReason.trim().length<3){bad({message:ar?'اكتب سبب الإلغاء أولًا':'Enter the cancellation reason first'});return;}
    setBusy(true);setMsg('');
    try{const result=await json(`/api/v1/gym/facility-bookings/${id}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:bCancelReason.trim()})});
      ok(ar?`تم إلغاء الحجز ${result.number} وتسجيل أثر الاسترداد إن وُجد`:`Booking ${result.number} cancelled; any refund was recorded`);setBCancelReason('');await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const captureAccess=async()=>{
    if(needBranch())return;
    if(!aMember||!aWhen){bad({message:ar?'اختر العضو ووقت الحركة':'Select the member and access time'});return;}
    setBusy(true);setMsg('');
    try{
      const result=await json('/api/v1/gym/access-records',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,branch_id:Number(branch),member_id:Number(aMember),
          occurred_at:new Date(aWhen).toISOString(),direction:aDirection,method:aMethod})});
      setErr(result.status==='DENIED');
      setMsg(result.status==='GRANTED'
        ? (ar?'تم تسجيل الحركة والسماح بالدخول':'Access captured and granted')
        : (ar?`تم تسجيل محاولة مرفوضة: ${accessReason(result.reason)}`:`Denied attempt recorded: ${accessReason(result.reason)}`));
      await load();
    }catch(e){bad(e);}finally{setBusy(false);}
  };

  const freeLockers=lockers.filter(l=>!l.member&&l.status!=='OCCUPIED').length;
  const upcoming=sessions.filter(s=>new Date(s.starts_at)>new Date()).length;
  const pendingModifications=modifications.filter(x=>x.status==='SUBMITTED').length;
  const q=search.trim().toLocaleLowerCase();
  const matches=(...values:unknown[])=>!q||values.some(value=>String(value??'').toLocaleLowerCase().includes(q));
  const filteredMembers=members.filter(x=>matches(x.member_number,x.name_ar,x.name_en,x.mobile));
  const filteredContracts=contracts.filter(x=>matches(x.number,x.member,x.plan,x.status,x.start_date,x.end_date));
  const filteredModifications=modifications.filter(x=>matches(x.number,x.contract_number,x.type,x.status,x.reason,x.effective_date));
  const filteredFacilities=facilities.filter(x=>matches(x.code,x.name_ar,x.name_en,x.facility_type,x.status));
  const filteredBookings=facilityBookings.filter(x=>matches(x.number,x.facility,x.status,x.access_mode,x.member_id,x.contract_id));
  const filteredAccess=accessRecords.filter(x=>{
    const member=members.find(m=>m.id===x.member_id);
    return matches(x.member_id,member?.member_number,member?.name_ar,member?.name_en,x.status,x.reason,x.direction,x.method,x.occurred_at);
  });

  return <>
    <div className="kpis">
      <Kpi title={ar?'العضويات النشطة':'Active memberships'} value={String(summary?.active_memberships??contracts.filter(x=>x.status==='ACTIVE').length)}
        trend={`${members.length} ${ar?'عضوًا مسجلًا':'registered members'}`} good icon={<Users size={22}/>} tone="blue"/>
      <Kpi title={ar?'حصص قادمة':'Upcoming classes'} value={String(upcoming)} trend={`${sessions.length} ${ar?'إجمالًا':'total'}`} good icon={<CalendarClock size={22}/>} tone="violet"/>
      <Kpi title={ar?'خزائن متاحة':'Free lockers'} value={String(freeLockers)} trend={`${lockers.length} ${ar?'إجمالًا':'total'}`} good={freeLockers>0} icon={<Lock size={22}/>} tone="green"/>
      <Kpi title={ar?'طلبات تعديل معلّقة':'Pending membership changes'} value={String(pendingModifications)}
        trend={ar?'تتطلب مُراجعًا مستقلًا':'Independent checker required'} good={pendingModifications===0} icon={<ShieldCheck size={22}/>} tone="amber"/>
    </div>

    <Panel title={ar?'الفرع':'Branch'} icon={<Dumbbell size={18}/>}>
      <div style={{padding:12,maxWidth:420}}>
        <label>{ar?'اختر الفرع — كل ما تنشئه يخصّه':'Branch — everything you create belongs to it'}
          <select style={field} value={branch} onChange={e=>setBranch(e.target.value)}>
            <option value="">{ar?'اختر...':'Select...'}</option>
            {branches.map(b=><option key={b.id} value={b.id}>{b.code} — {ar?b.name_ar:b.name_en}</option>)}
          </select></label>
      </div>
    </Panel>

    <div style={{display:'flex',gap:8,margin:'14px 0',flexWrap:'wrap'}}>
      {([['overview',ar?'نظرة عامة':'Overview'],['members',ar?'الأعضاء والعقود':'Members & contracts'],
         ['memberships',ar?'تعديل العضوية':'Membership changes'],['facilities',ar?'حجز المرافق':'Facility booking'],
         ['access',ar?'الدخول والخروج':'Access'],['trainers',ar?'المدربون':'Trainers'],
         ['classes',ar?'الحصص':'Classes'],['lockers',ar?'الخزائن':'Lockers']] as [typeof tab,string][])
        .map(([k,l])=><button key={k} onClick={()=>{setTab(k);setSearch('')}}
          style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',
            color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>

    {msg&&<div style={{padding:11,marginBottom:12,borderRadius:9,fontSize:14,lineHeight:1.9,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    {tab!=='overview'&&<div style={{position:'relative',marginBottom:12,maxWidth:620}}>
      <Search size={18} style={{position:'absolute',insetInlineStart:12,top:12,opacity:0.65}}/>
      <input value={search} onChange={e=>setSearch(e.target.value)} aria-label={ar?'بحث عمليات الجيم':'Search gym operations'}
        placeholder={ar?'ابحث محليًا بالرقم أو الاسم أو الحالة...':'Local search by number, name or status...'}
        style={{...field,marginTop:0,paddingInlineStart:40}}/>
    </div>}

    {tab==='overview'&&<>
      <Panel title={ar?'الاعتراف بالإيراد — القاعدة المحاسبية':'Revenue recognition'} icon={<TrendingUp size={18}/>}>
        <div style={{padding:14,fontSize:14,lineHeight:2}}>
          {ar
            ? <>العضوية السنوية وباقة التدريب الشخصي <b>ليست إيرادًا يوم بيعها</b>. عند القبض تُسجَّل <b>إيرادات مؤجلة</b> (التزام)، ثم يُعترف بجزء منها شهريًا أو مع كل جلسة مُنفَّذة.
              <br/><br/>
              <b>لماذا؟</b> لأنك لم تقدّم الخدمة بعد. الاعتراف الكامل عند البيع <b>يضخّم إيراد الشهر ويفرغ الأشهر التالية</b>، فتظهر أرباح غير حقيقية ثم انهيار مفاجئ.
              <br/><br/>
              <b>وعمولة المدرب</b> تُستحق عند <b>تنفيذ</b> الجلسة لا عند بيع الباقة — وإلا دفعت عمولة على خدمة لم تُقدَّم.</>
            : <>A yearly membership or a PT package is not revenue on the sale date. Cash creates deferred revenue, released monthly or per delivered session. Recognising it all at once inflates one month and empties the next. Trainer commission accrues on delivery, not on sale.</>}
        </div>
      </Panel>
      <Panel title={ar?'مؤشرات تستحق المتابعة':'Metrics that matter'} icon={<Dumbbell size={18}/>}>
        <DataTable headers={[ar?'المؤشر':'Metric',ar?'المعادلة':'Formula',ar?'المعيار':'Benchmark']}
          rows={[
            [ar?'نسبة التجديد':'Renewal rate',ar?'المجدّدون ÷ المنتهية عضويتهم':'renewed / expired',ar?'أعلى من ٧٠٪':'> 70%'],
            [ar?'معدل الحضور':'Attendance',ar?'الزيارات ÷ عدد الأعضاء':'visits / members',ar?'يقيس التفاعل':'engagement'],
            [ar?'الإيراد لكل عضو':'Revenue per member',ar?'الإيراد ÷ الأعضاء':'revenue / members','—'],
            [ar?'إشغال الحصص':'Class fill rate',ar?'المحجوز ÷ السعة':'booked / capacity',ar?'أعلى من ٦٥٪':'> 65%'],
          ]}/>
        <div style={{padding:'0 14px 16px',fontSize:13,lineHeight:1.9,opacity:0.9}}>
          {ar?'⚠ نسبة تجديد منخفضة مع إيراد مرتفع تعني نموذجًا هشًّا: تعتمد على أعضاء جدد لتعويض المتسربين.'
             :'⚠ Low renewal with high revenue is a fragile model: new members are covering churn.'}
        </div>
      </Panel>
    </>}

    {tab==='members'&&<>
      <Panel title={ar?'دليل الأعضاء':'Member directory'} icon={<Users size={18}/> }>
        <DataTable headers={[ar?'رقم العضو':'Member no.',ar?'الاسم':'Name',ar?'الجوال':'Mobile']}
          rows={filteredMembers.map(member=>[member.member_number,ar?member.name_ar:member.name_en,member.mobile||'—'])}/>
      </Panel>
      <Panel title={ar?'عقود العضوية والإيراد المؤجل':'Membership contracts and deferred revenue'} icon={<ShieldCheck size={18}/> }>
        <DataTable headers={[ar?'رقم العقد':'Contract',ar?'العضو':'Member',ar?'الخطة':'Plan',ar?'المدة':'Term',ar?'المؤجل':'Deferred',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={filteredContracts.map(contract=>[
            contract.number,contract.member,contract.plan,`${contract.start_date} → ${contract.end_date}`,
            fmt(Number(contract.deferred||0)),statusLabel(contract.status),
            <button type="button" style={{...btn,padding:'6px 10px'}} onClick={()=>{setMContract(String(contract.id));setSearch('');setTab('memberships')}}>
              {ar?'طلب تعديل':'Request change'}
            </button>,
          ])}/>
      </Panel>
    </>}

    {tab==='memberships'&&<>
      <Panel title={ar?'طلب تعديل عضوية — فصل المُنشئ عن المعتمد':'Membership change — maker/checker separation'} icon={<Snowflake size={18}/> }>
        <div style={grid}>
          <label>{ar?'عقد العضوية':'Membership contract'}
            <select style={field} value={mContract} onChange={e=>setMContract(e.target.value)}>
              <option value="">{ar?'اختر...':'Select...'}</option>
              {contracts.map(contract=><option key={contract.id} value={contract.id}>{contract.number} — {contract.member} — {statusLabel(contract.status)}</option>)}
            </select>
          </label>
          <label>{ar?'نوع التعديل':'Change type'}
            <select style={field} value={mType} onChange={e=>setMType(e.target.value as 'FREEZE'|'EXTENSION')}>
              <option value="FREEZE">{ar?'تجميد مؤقت':'Temporary freeze'}</option>
              <option value="EXTENSION">{ar?'تمديد مدة العضوية':'Extend membership'}</option>
            </select>
          </label>
          <label>{ar?'تاريخ السريان':'Effective date'}<input type="date" style={field} value={mEffective} onChange={e=>setMEffective(e.target.value)}/></label>
          {mType==='FREEZE'?<>
            <label>{ar?'بداية التجميد':'Freeze starts'}<input type="date" style={field} value={mFreezeStart} onChange={e=>setMFreezeStart(e.target.value)}/></label>
            <label>{ar?'نهاية التجميد':'Freeze ends'}<input type="date" style={field} value={mFreezeEnd} onChange={e=>setMFreezeEnd(e.target.value)}/>
              <small style={{opacity:0.75}}>{ar?'يُفك التجميد تلقائيًا بعد هذا التاريخ وتُمدد نهاية العقد':'Access resumes automatically after this date and the contract end is extended'}</small>
            </label>
          </>:<label>{ar?'أيام التمديد':'Extension days'}<input type="number" min="1" max="730" style={field} value={mExtensionDays} onChange={e=>setMExtensionDays(e.target.value)}/></label>}
          <label>{ar?'سبب التعديل':'Reason'}<textarea style={field} value={mReason} onChange={e=>setMReason(e.target.value)} placeholder={ar?'مثال: سفر العضو مع إرفاق المستند':'Example: member travel with supporting document'}/></label>
        </div>
        <div style={{padding:'0 12px 14px',display:'flex',gap:10,alignItems:'center',flexWrap:'wrap'}}>
          <button type="button" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={submitModification}>{ar?'إرسال للمراجعة':'Submit for review'}</button>
          <span style={{fontSize:13,opacity:0.8}}>{ar?'المنشئ لا يمكنه اعتماد أو رفض طلبه':'The maker cannot approve or reject their own request'}</span>
        </div>
      </Panel>
      <Panel title={ar?'طلبات التعديل ومسار الاعتماد':'Change requests and approvals'} icon={<ShieldCheck size={18}/> }>
        <div style={{padding:12,maxWidth:520}}>
          <label>{ar?'سبب الرفض (يُستخدم عند الضغط على رفض)':'Rejection reason (used by Reject)'}
            <input style={field} value={mRejectReason} onChange={e=>setMRejectReason(e.target.value)} placeholder={ar?'بيانات أو مستندات غير مكتملة':'Missing data or evidence'}/>
          </label>
        </div>
        <DataTable headers={[ar?'الرقم':'Number',ar?'العقد':'Contract',ar?'النوع':'Type',ar?'السريان':'Effective',ar?'الفترة/الأيام':'Period / days',ar?'السبب':'Reason',ar?'الحالة':'Status',ar?'إجراء المراجع':'Checker action']}
          rows={filteredModifications.map(change=>[
            change.number,change.contract_number,change.type,change.effective_date,
            change.type==='FREEZE'?`${change.freeze_start} → ${change.freeze_end}`:String(change.extension_days||'—'),
            change.reason,statusLabel(change.status),
            change.status==='SUBMITTED'?<div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
              <button type="button" style={{...btn,padding:'6px 9px',background:'#166534'}} disabled={busy} onClick={()=>approveModification(change.id)}>
                <CheckCircle2 size={14} style={{verticalAlign:'middle'}}/> {ar?'اعتماد التعديل':'Approve change'}
              </button>
              <button type="button" style={{...btn,padding:'6px 9px',background:'#991b1b'}} disabled={busy} onClick={()=>rejectModification(change.id)}>
                <XCircle size={14} style={{verticalAlign:'middle'}}/> {ar?'رفض التعديل':'Reject change'}
              </button>
            </div>:'—',
          ])}/>
      </Panel>
    </>}

    {tab==='facilities'&&<>
      <Panel title={ar?'حجز مرفق أو ملعب':'Book a facility or court'} icon={<MapPin size={18}/> }>
        <div style={grid}>
          <label>{ar?'المرفق':'Facility'}
            <select style={field} value={bFacility} onChange={e=>setBFacility(e.target.value)}>
              <option value="">{ar?'اختر...':'Select...'}</option>
              {facilities.filter(x=>x.status==='AVAILABLE').map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.name_ar:x.name_en} — {fmt(Number(x.hourly_rate||0))}/{ar?'ساعة':'hour'}</option>)}
            </select>
          </label>
          <label>{ar?'العضو':'Member'}
            <select style={field} value={bMember} onChange={e=>{
              const memberId=e.target.value;setBMember(memberId);
              const member=members.find(x=>String(x.id)===memberId);const contract=contracts.find(x=>x.member===member?.name_en&&['ACTIVE','FROZEN'].includes(x.status));
              if(contract)setBContract(String(contract.id));
            }}>
              <option value="">{ar?'اختر...':'Select...'}</option>
              {members.map(x=><option key={x.id} value={x.id}>{x.member_number} — {ar?x.name_ar:x.name_en}</option>)}
            </select>
          </label>
          <label>{ar?'عقد العضوية':'Membership contract'}
            <select style={field} value={bContract} onChange={e=>setBContract(e.target.value)}>
              <option value="">{ar?'اختر...':'Select...'}</option>
              {contracts.map(x=><option key={x.id} value={x.id}>{x.number} — {x.member} — {statusLabel(x.status)}</option>)}
            </select>
          </label>
          <label>{ar?'وقت البداية':'Starts at'}<input type="datetime-local" style={field} value={bStarts} onChange={e=>setBStarts(e.target.value)}/></label>
          <label>{ar?'وقت النهاية':'Ends at'}<input type="datetime-local" style={field} value={bEnds} onChange={e=>setBEnds(e.target.value)}/></label>
          <label>{ar?'عدد المشاركين':'Participants'}<input type="number" min="1" style={field} value={bParticipants} onChange={e=>setBParticipants(e.target.value)}/></label>
          <label>{ar?'حساب التحصيل (للحجز المدفوع)':'Collection account (paid booking)'}
            <select style={field} value={bBank} onChange={e=>setBBank(e.target.value)}>
              <option value="">{ar?'— لا يوجد —':'— none —'}</option>
              {bankAccounts.map(x=><option key={x.id} value={x.id}>{x.code} — {ar?x.bank_name_ar:x.bank_name_en}</option>)}
            </select>
          </label>
          <label>{ar?'ملاحظات الحجز':'Booking notes'}<textarea style={field} value={bNotes} onChange={e=>setBNotes(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}><button type="button" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={submitFacilityBooking}>{ar?'إنشاء الحجز':'Create booking'}</button></div>
      </Panel>
      <Panel title={ar?'المرافق المتاحة':'Available facilities'} icon={<MapPin size={18}/> }>
        <DataTable headers={[ar?'الكود':'Code',ar?'المرفق':'Facility',ar?'النوع':'Type',ar?'السعة':'Capacity',ar?'السعر/ساعة':'Hourly rate',ar?'الحالة':'Status']}
          rows={filteredFacilities.map(x=>[x.code,ar?x.name_ar:x.name_en,x.facility_type,String(x.capacity),fmt(Number(x.hourly_rate||0)),statusLabel(x.status)])}/>
      </Panel>
      <Panel title={ar?'حجوزات المرافق':'Facility bookings'} icon={<CalendarClock size={18}/> }>
        <div style={{padding:12,maxWidth:520}}><label>{ar?'سبب الإلغاء':'Cancellation reason'}<input style={field} value={bCancelReason} onChange={e=>setBCancelReason(e.target.value)}/></label></div>
        <DataTable headers={[ar?'الرقم':'Number',ar?'المرفق':'Facility',ar?'الوقت':'Time',ar?'المشاركون':'Participants',ar?'القيمة':'Total',ar?'الحالة':'Status',ar?'إجراء':'Action']}
          rows={filteredBookings.map(booking=>[
            booking.number,booking.facility,`${String(booking.starts_at).replace('T',' ').slice(0,16)} → ${String(booking.ends_at).replace('T',' ').slice(0,16)}`,
            String(booking.participants),fmt(Number(booking.total_amount||0)),statusLabel(booking.status),
            ['SUBMITTED','CONFIRMED'].includes(booking.status)?<div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
              {booking.status==='SUBMITTED'&&<button type="button" style={{...btn,padding:'6px 9px',background:'#166534'}} disabled={busy} onClick={()=>approveBooking(booking.id)}>{ar?'اعتماد الحجز':'Approve booking'}</button>}
              <button type="button" style={{...btn,padding:'6px 9px',background:'#991b1b'}} disabled={busy} onClick={()=>cancelBooking(booking.id)}>{ar?'إلغاء الحجز':'Cancel booking'}</button>
            </div>:'—',
          ])}/>
      </Panel>
    </>}

    {tab==='access'&&<>
      <Panel title={ar?'تسجيل دخول أو خروج عضو':'Capture member entry or exit'} icon={<DoorOpen size={18}/> }>
        <div style={grid}>
          <label>{ar?'العضو':'Member'}
            <select style={field} value={aMember} onChange={e=>setAMember(e.target.value)}>
              <option value="">{ar?'اختر...':'Select...'}</option>
              {members.map(x=><option key={x.id} value={x.id}>{x.member_number} — {ar?x.name_ar:x.name_en}</option>)}
            </select>
          </label>
          <label>{ar?'وقت الحركة':'Access time'}<input type="datetime-local" style={field} value={aWhen} onChange={e=>setAWhen(e.target.value)}/></label>
          <label>{ar?'الاتجاه':'Direction'}
            <select style={field} value={aDirection} onChange={e=>setADirection(e.target.value as 'IN'|'OUT')}>
              <option value="IN">{ar?'دخول':'Entry'}</option><option value="OUT">{ar?'خروج':'Exit'}</option>
            </select>
          </label>
          <label>{ar?'طريقة التحقق':'Verification method'}
            <select style={field} value={aMethod} onChange={e=>setAMethod(e.target.value as 'MANUAL'|'QR'|'CARD')}>
              <option value="QR">QR</option><option value="CARD">{ar?'بطاقة':'Card'}</option><option value="MANUAL">{ar?'يدوي':'Manual'}</option>
            </select>
          </label>
        </div>
        <div style={{padding:'0 12px 14px'}}><button type="button" style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={captureAccess}>{ar?'تسجيل الحركة':'Capture access'}</button></div>
      </Panel>
      <Panel title={ar?'سجل الدخول والخروج وقرارات المنع':'Access log and denial decisions'} icon={<DoorOpen size={18}/> }>
        <DataTable headers={[ar?'العضو':'Member',ar?'الفرع':'Branch',ar?'الوقت':'Time',ar?'الاتجاه':'Direction',ar?'الطريقة':'Method',ar?'القرار':'Decision',ar?'السبب':'Reason']}
          rows={filteredAccess.map(row=>{
            const member=members.find(x=>x.id===row.member_id);
            return [member?`${member.member_number} — ${ar?member.name_ar:member.name_en}`:String(row.member_id),String(row.branch_id),
              String(row.occurred_at).replace('T',' ').slice(0,16),statusLabel(row.direction),row.method,statusLabel(row.status),accessReason(row.reason)];
          })}/>
      </Panel>
    </>}

    {tab==='trainers'&&<>
      <Panel title={ar?'مدرب جديد':'New trainer'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={tCode} onChange={e=>setTCode(e.target.value)} placeholder="TRN-001"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={tAr} onChange={e=>setTAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={tEn} onChange={e=>setTEn(e.target.value)}/></label>
          <label>{ar?'نسبة العمولة %':'Commission %'}<input type="number" step="0.5" style={field} value={tRate} onChange={e=>setTRate(e.target.value)}/>
            <small style={{opacity:0.75}}>{ar?'تُستحق عند تنفيذ الجلسة':'accrues on delivery'}</small></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addTrainer}>{ar?'تسجيل المدرب':'Add trainer'}</button>
        </div>
      </Panel>
      <Panel title={ar?'المدربون':'Trainers'} icon={<Users size={18}/>}>
        <DataTable headers={[ar?'الكود':'Code',ar?'الاسم':'Name',ar?'العمولة':'Commission']}
          rows={trainers.map(t=>[t.code,ar?t.name_ar:t.name_en,`${t.commission_rate}%`])}/>
      </Panel>
    </>}

    {tab==='classes'&&<>
      <Panel title={ar?'نوع حصة جديد':'New class type'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'الكود':'Code'}<input style={field} value={ctCode} onChange={e=>setCtCode(e.target.value)} placeholder="CLS-YOGA"/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={ctAr} onChange={e=>setCtAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={ctEn} onChange={e=>setCtEn(e.target.value)}/></label>
          <label>{ar?'المدة (دقيقة)':'Duration (min)'}<input type="number" style={field} value={ctMin} onChange={e=>setCtMin(e.target.value)}/></label>
          <label>{ar?'السعة الافتراضية':'Default capacity'}<input type="number" style={field} value={ctCap} onChange={e=>setCtCap(e.target.value)}/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addClassType}>{ar?'إنشاء النوع':'Create type'}</button>
        </div>
      </Panel>
      <Panel title={ar?'جدولة حصة':'Schedule a session'} icon={<CalendarClock size={18}/>}>
        {classTypes.length===0
          ? <div style={{padding:16,fontSize:14}}>{ar?'أنشئ نوع حصة أولًا.':'Create a class type first.'}</div>
          : <>
            <div style={grid}>
              <label>{ar?'نوع الحصة':'Class type'}<select style={field} value={sType} onChange={e=>setSType(e.target.value)}>
                {classTypes.map(c=><option key={c.id} value={c.id}>{ar?c.name_ar:c.name_en}</option>)}</select></label>
              <label>{ar?'المدرب':'Trainer'}<select style={field} value={sTrainer} onChange={e=>setSTrainer(e.target.value)}>
                <option value="">{ar?'— بلا مدرب —':'— none —'}</option>
                {trainers.map(t=><option key={t.id} value={t.id}>{ar?t.name_ar:t.name_en}</option>)}</select></label>
              <label>{ar?'وقت البدء':'Starts at'}<input type="datetime-local" style={field} value={sStart} onChange={e=>setSStart(e.target.value)}/></label>
              <label>{ar?'السعة (اختياري)':'Capacity'}<input type="number" style={field} value={sCap} onChange={e=>setSCap(e.target.value)}/></label>
            </div>
            <div style={{padding:'0 12px 14px'}}>
              <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addSession}>{ar?'جدولة':'Schedule'}</button>
            </div>
          </>}
      </Panel>
      <Panel title={ar?'الحصص':'Sessions'} icon={<CalendarClock size={18}/>}>
        <DataTable headers={[ar?'النوع':'Type',ar?'المدرب':'Trainer',ar?'الوقت':'Starts',ar?'السعة':'Capacity',ar?'الحالة':'Status']}
          rows={sessions.map(s=>[s.class_type||'—',s.trainer||'—',
            (s.starts_at||'').replace('T',' ').slice(0,16),String(s.capacity??'—'),s.status||'—'])}/>
      </Panel>
    </>}

    {tab==='lockers'&&<>
      <Panel title={ar?'خزانة جديدة':'New locker'} icon={<Plus size={18}/>}>
        <div style={grid}>
          <label>{ar?'رقم الخزانة':'Locker code'}<input style={field} value={lCode} onChange={e=>setLCode(e.target.value)} placeholder="L-101"/></label>
        </div>
        <div style={{padding:'0 12px 14px'}}>
          <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={addLocker}>{ar?'إضافة':'Add'}</button>
        </div>
      </Panel>
      <Panel title={ar?'الخزائن':'Lockers'} icon={<Lock size={18}/>}>
        <DataTable headers={[ar?'الرقم':'Code',ar?'الحالة':'Status',ar?'العضو':'Member']}
          rows={lockers.map(l=>[l.code,l.status||(ar?'متاحة':'Free'),l.member||'—'])}/>
      </Panel>
      <Panel title={ar?'باقات التدريب الشخصي':'PT packages'} icon={<Dumbbell size={18}/>}>
        {packages.length>0
          ? <DataTable headers={[ar?'الكود':'Code',ar?'الباقة':'Package',ar?'الجلسات':'Sessions',ar?'السعر':'Price']}
              rows={packages.map(p=>[p.code,ar?p.name_ar:p.name_en,String(p.sessions_count??'—'),fmt(Number(p.net_price||0))])}/>
          : <div style={{padding:16,fontSize:14,lineHeight:1.9,opacity:0.85}}>
              {ar?'لا توجد باقات تدريب شخصي نشطة لهذه الشركة.'
                 :'There are no active PT packages for this company.'}
            </div>}
        <div style={{padding:'0 14px 16px',fontSize:13,lineHeight:1.9,opacity:0.9}}>
          {ar?'الباقة تُباع مقدمًا وتُستهلك بالجلسة — إيرادها مؤجل يُعترف به مع كل جلسة مُنفَّذة.'
             :'A package is sold upfront and consumed per session; its revenue is deferred and released on delivery.'}
        </div>
      </Panel>
    </>}
  </>;
}
