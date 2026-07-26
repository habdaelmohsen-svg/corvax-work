import {useEffect, useState} from 'react';
import {Truck, User, Route, Thermometer} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

type Vehicle={id:number;plate_number:string;name_ar:string;name_en:string;vehicle_type:string;is_refrigerated:boolean;odometer_km:number;status:string};
type Driver={id:number;name_ar:string;name_en:string;license_number:string;license_expiry?:string;phone?:string;status:string};
type Trip={id:number;number:string;vehicle_plate?:string;driver_name_ar?:string;trip_date:string;origin_ar?:string;destination_ar?:string;purpose:string;distance_km:number;fuel_cost:number;cargo_temperature?:number;status:string};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail||x));
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;

const VEHICLE_TYPES:[string,string,string][]=[['REFRIGERATED_TRUCK','شاحنة مبردة','Refrigerated truck'],['TRUCK','شاحنة','Truck'],['VAN','فان','Van'],['CAR','سيارة','Car'],['FORKLIFT','رافعة شوكية','Forklift']];
const PURPOSES:[string,string,string][]=[['DELIVERY','توصيل','Delivery'],['PICKUP','استلام','Pickup'],['TRANSFER','نقل داخلي','Transfer'],['OTHER','أخرى','Other']];

export function FleetPage({ar,companyId}:{ar:boolean;companyId:number}){
  const today=new Date().toISOString().slice(0,10);
  const [tab,setTab]=useState<'vehicles'|'drivers'|'trips'>('vehicles');
  const [vehicles,setVehicles]=useState<Vehicle[]>([]);
  const [drivers,setDrivers]=useState<Driver[]>([]);
  const [trips,setTrips]=useState<Trip[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // vehicle
  const [plate,setPlate]=useState(''); const [vNameAr,setVNameAr]=useState(''); const [vNameEn,setVNameEn]=useState(''); const [vType,setVType]=useState('REFRIGERATED_TRUCK'); const [refrigerated,setRefrigerated]=useState(true);
  // driver
  const [dNameAr,setDNameAr]=useState(''); const [dNameEn,setDNameEn]=useState(''); const [license,setLicense]=useState(''); const [licenseExp,setLicenseExp]=useState(''); const [phone,setPhone]=useState('');
  // trip
  const [tVehicle,setTVehicle]=useState(''); const [tDriver,setTDriver]=useState(''); const [tDate,setTDate]=useState(today); const [origin,setOrigin]=useState(''); const [dest,setDest]=useState(''); const [purpose,setPurpose]=useState('DELIVERY'); const [distance,setDistance]=useState('0'); const [fuel,setFuel]=useState('0'); const [temp,setTemp]=useState('');

  const load=async()=>{
    try{
      const [v,d,t]=await Promise.all([
        json(`/api/v1/departments/fleet/vehicles?company_id=${companyId}`),
        json(`/api/v1/departments/fleet/drivers?company_id=${companyId}`),
        json(`/api/v1/departments/fleet/trips?company_id=${companyId}`),
      ]);
      setVehicles(v||[]); setDrivers(d||[]); setTrips(t||[]);
      if(!tVehicle&&v?.length)setTVehicle(String(v[0].id));
      if(!tDriver&&d?.length)setTDriver(String(d[0].id));
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const createVehicle=async()=>{
    if(!plate||!vNameAr||!vNameEn){setMessage(ar?'اللوحة والاسمان إلزامية':'Plate and names required');return;}
    setBusy(true);setMessage('');
    try{await json('/api/v1/departments/fleet/vehicles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,plate_number:plate,name_ar:vNameAr,name_en:vNameEn,vehicle_type:vType,is_refrigerated:refrigerated})});
      setMessage(ar?'تمت إضافة المركبة':'Vehicle added');setPlate('');setVNameAr('');setVNameEn('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createDriver=async()=>{
    if(!dNameAr||!dNameEn||!license){setMessage(ar?'الاسمان ورقم الرخصة إلزامية':'Names and license required');return;}
    setBusy(true);setMessage('');
    try{await json('/api/v1/departments/fleet/drivers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,name_ar:dNameAr,name_en:dNameEn,license_number:license,license_expiry:licenseExp||undefined,phone:phone||undefined})});
      setMessage(ar?'تمت إضافة السائق':'Driver added');setDNameAr('');setDNameEn('');setLicense('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };
  const createTrip=async()=>{
    if(!tVehicle||!tDriver){setMessage(ar?'اختر المركبة والسائق':'Select vehicle and driver');return;}
    setBusy(true);setMessage('');
    try{const r=await json('/api/v1/departments/fleet/trips',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_id:companyId,vehicle_id:Number(tVehicle),driver_id:Number(tDriver),trip_date:tDate,origin_ar:origin||undefined,destination_ar:dest||undefined,purpose,distance_km:Number(distance),fuel_cost:Number(fuel),cargo_temperature:temp?Number(temp):undefined})});
      setMessage(ar?`تم إنشاء الرحلة ${r.number}`:`Trip ${r.number} created`);setOrigin('');setDest('');await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const label=(list:[string,string,string][],v:string)=>{const f=list.find(x=>x[0]===v);return f?(ar?f[1]:f[2]):v;};
  const refrigeratedCount=vehicles.filter(v=>v.is_refrigerated).length;
  const totalFuel=trips.reduce((s,t)=>s+Number(t.fuel_cost||0),0);

  return <>
    <div className="kpis">
      <Kpi title={ar?'المركبات':'Vehicles'} value={String(vehicles.length)} trend="" good icon={<Truck size={22}/>} tone="blue"/>
      <Kpi title={ar?'مبردة':'Refrigerated'} value={String(refrigeratedCount)} trend="" good icon={<Thermometer size={22}/>} tone="violet"/>
      <Kpi title={ar?'السائقون':'Drivers'} value={String(drivers.length)} trend="" good icon={<User size={22}/>} tone="green"/>
      <Kpi title={ar?'إجمالي الوقود':'Total fuel'} value={fmt(totalFuel)} trend="" good icon={<Route size={22}/>} tone="amber"/>
    </div>
    <div style={{display:'flex',gap:8,margin:'14px 0'}}>
      {([['vehicles',ar?'المركبات':'Vehicles'],['drivers',ar?'السائقون':'Drivers'],['trips',ar?'الرحلات':'Trips']] as [typeof tab,string][]).map(([k,l])=>
        <button key={k} onClick={()=>setTab(k)} style={{...btn,background:tab===k?'var(--accent, #1e40af)':'transparent',color:tab===k?'#fff':'var(--text)',border:'1px solid var(--border)'}}>{l}</button>)}
    </div>
    {message&&<div style={{padding:10,marginBottom:12,borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14}}>{message}</div>}

    {tab==='vehicles'&&<>
      <Panel title={ar?'مركبة جديدة':'New vehicle'} icon={<Truck size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'رقم اللوحة':'Plate number'}<input style={field} value={plate} onChange={e=>setPlate(e.target.value)}/></label>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={vNameAr} onChange={e=>setVNameAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={vNameEn} onChange={e=>setVNameEn(e.target.value)}/></label>
          <label>{ar?'النوع':'Type'}<select style={field} value={vType} onChange={e=>setVType(e.target.value)}>{VEHICLE_TYPES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label style={{display:'flex',alignItems:'center',gap:8,marginTop:24}}><input type="checkbox" checked={refrigerated} onChange={e=>setRefrigerated(e.target.checked)}/>{ar?'مبردة':'Refrigerated'}</label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createVehicle}>{ar?'إضافة المركبة':'Add vehicle'}</button></div>
      </Panel>
      <Panel title={ar?'المركبات':'Vehicles'} icon={<Truck size={18}/>}>
        <DataTable headers={[ar?'اللوحة':'Plate',ar?'الاسم':'Name',ar?'النوع':'Type',ar?'مبردة':'Refrigerated',ar?'العداد':'Odometer',ar?'الحالة':'Status']}
          rows={vehicles.map(v=>[v.plate_number,ar?v.name_ar:v.name_en,label(VEHICLE_TYPES,v.vehicle_type),v.is_refrigerated?(ar?'نعم':'Yes'):(ar?'لا':'No'),fmt(Number(v.odometer_km)),v.status])}/>
      </Panel>
    </>}

    {tab==='drivers'&&<>
      <Panel title={ar?'سائق جديد':'New driver'} icon={<User size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={dNameAr} onChange={e=>setDNameAr(e.target.value)}/></label>
          <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={dNameEn} onChange={e=>setDNameEn(e.target.value)}/></label>
          <label>{ar?'رقم الرخصة':'License number'}<input style={field} value={license} onChange={e=>setLicense(e.target.value)}/></label>
          <label>{ar?'انتهاء الرخصة':'License expiry'}<input type="date" style={field} value={licenseExp} onChange={e=>setLicenseExp(e.target.value)}/></label>
          <label>{ar?'الهاتف':'Phone'}<input style={field} value={phone} onChange={e=>setPhone(e.target.value)}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createDriver}>{ar?'إضافة السائق':'Add driver'}</button></div>
      </Panel>
      <Panel title={ar?'السائقون':'Drivers'} icon={<User size={18}/>}>
        <DataTable headers={[ar?'الاسم':'Name',ar?'رقم الرخصة':'License',ar?'انتهاء الرخصة':'Expiry',ar?'الهاتف':'Phone',ar?'الحالة':'Status']}
          rows={drivers.map(d=>[ar?d.name_ar:d.name_en,d.license_number,d.license_expiry||'—',d.phone||'—',d.status])}/>
      </Panel>
    </>}

    {tab==='trips'&&<>
      <Panel title={ar?'رحلة جديدة':'New trip'} icon={<Route size={18}/>}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:12,padding:12}}>
          <label>{ar?'المركبة':'Vehicle'}<select style={field} value={tVehicle} onChange={e=>setTVehicle(e.target.value)}>{vehicles.map(v=><option key={v.id} value={v.id}>{v.plate_number} — {ar?v.name_ar:v.name_en}</option>)}</select></label>
          <label>{ar?'السائق':'Driver'}<select style={field} value={tDriver} onChange={e=>setTDriver(e.target.value)}>{drivers.map(d=><option key={d.id} value={d.id}>{ar?d.name_ar:d.name_en}</option>)}</select></label>
          <label>{ar?'التاريخ':'Date'}<input type="date" style={field} value={tDate} onChange={e=>setTDate(e.target.value)}/></label>
          <label>{ar?'من':'Origin'}<input style={field} value={origin} onChange={e=>setOrigin(e.target.value)}/></label>
          <label>{ar?'إلى':'Destination'}<input style={field} value={dest} onChange={e=>setDest(e.target.value)}/></label>
          <label>{ar?'الغرض':'Purpose'}<select style={field} value={purpose} onChange={e=>setPurpose(e.target.value)}>{PURPOSES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
          <label>{ar?'المسافة (كم)':'Distance (km)'}<input type="number" style={field} value={distance} onChange={e=>setDistance(e.target.value)}/></label>
          <label>{ar?'تكلفة الوقود':'Fuel cost'}<input type="number" style={field} value={fuel} onChange={e=>setFuel(e.target.value)}/></label>
          <label>{ar?'حرارة الحمولة °م':'Cargo temp °C'}<input type="number" style={field} value={temp} onChange={e=>setTemp(e.target.value)} placeholder={ar?'للمبرد':'refrigerated'}/></label>
        </div>
        <div style={{padding:12}}><button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={createTrip}>{ar?'إنشاء الرحلة':'Create trip'}</button></div>
      </Panel>
      <Panel title={ar?'الرحلات':'Trips'} icon={<Route size={18}/>}>
        <DataTable headers={[ar?'الرقم':'No.',ar?'المركبة':'Vehicle',ar?'السائق':'Driver',ar?'التاريخ':'Date',ar?'الوجهة':'Destination',ar?'الحرارة':'Temp',ar?'الحالة':'Status']}
          rows={trips.map(t=>[t.number,t.vehicle_plate||'—',t.driver_name_ar||'—',t.trip_date,t.destination_ar||'—',t.cargo_temperature!=null?`${t.cargo_temperature}°`:'—',t.status])}/>
      </Panel>
    </>}
  </>;
}
