import {useEffect, useMemo, useState} from 'react';
import {Network, Plus, ChevronDown, ChevronLeft, Search, Power, Trash2, Info, Download, Upload, FileCheck2} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel} from './ui';

// Chart of accounts management. The backend allows any depth; this screen shows
// the hierarchy, marks which accounts still accept entries, and enforces the
// same accounting rules in the UI so the user understands them before saving.

type Node = {
  id:number; code:string; name_ar:string; name_en:string;
  account_type:string; statement_group:string; level:number;
  is_postable:boolean; is_cash:boolean; active:boolean;
  movement_lines:number; children:Node[];
};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    const msg = typeof d==='string' ? d
      : (d && (d.message_ar || d.message_en)) ? (d.message_ar || d.message_en)
      : (Array.isArray(d) ? d.map((i:any)=>i.msg||JSON.stringify(i)).join(' | ') : JSON.stringify(d||x));
    throw new Error(msg);
  }
  return x;
}
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const chip={padding:'2px 8px',borderRadius:999,fontSize:11,fontWeight:700} as const;

const TYPE_AR:Record<string,string>={ASSET:'أصول',LIABILITY:'التزامات',EQUITY:'حقوق ملكية',REVENUE:'إيرادات',EXPENSE:'مصروفات'};

export function ChartOfAccountsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [tree,setTree]=useState<Node[]>([]);
  const [stats,setStats]=useState<{total:number;maxLevel:number;postable:number}>({total:0,maxLevel:0,postable:0});
  const [open,setOpen]=useState<Record<number,boolean>>({});
  const [filter,setFilter]=useState('');
  const [msg,setMsg]=useState(''); const [err,setErr]=useState(false); const [busy,setBusy]=useState(false);
  // new account form
  const [parentCode,setParentCode]=useState('');
  const [code,setCode]=useState(''); const [nameAr,setNameAr]=useState(''); const [nameEn,setNameEn]=useState('');
  const [isCash,setIsCash]=useState(false);
  const [importFile,setImportFile]=useState<File|null>(null);
  const [importResult,setImportResult]=useState<any>(null);

  const load=async()=>{
    try{
      const r=await json(`/api/v1/chart-of-accounts/tree?company_id=${companyId}&include_inactive=true`);
      setTree(r.tree||[]);
      setStats({total:r.total_accounts||0,maxLevel:r.max_level||0,postable:r.postable_accounts||0});
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}
  };
  useEffect(()=>{load()},[companyId]);

  // flat list for the parent picker: only accounts that may take children
  const flat=useMemo(()=>{
    const out:Node[]=[];
    const walk=(nodes:Node[])=>nodes.forEach(n=>{out.push(n);walk(n.children);});
    walk(tree); return out;
  },[tree]);

  const expectedPrefix=useMemo(()=>{
    if(!parentCode) return '';
    return parentCode.replace(/0+$/,'') || parentCode.slice(0,1);
  },[parentCode]);

  const create=async()=>{
    if(!code||!nameAr||!nameEn){setMsg(ar?'الرقم والاسمان إلزامية':'Code and both names are required');setErr(true);return;}
    setBusy(true);setMsg('');setErr(false);
    try{
      const body:any={company_id:companyId,code:code.trim(),name_ar:nameAr.trim(),name_en:nameEn.trim(),is_cash:isCash};
      if(parentCode)body.parent_code=parentCode;
      const r=await json('/api/v1/chart-of-accounts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMsg(ar?r.message_ar:r.message_en); setErr(false);
      setCode('');setNameAr('');setNameEn('');setIsCash(false);
      await load();
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };

  const exportExcel=async()=>{
    setBusy(true);setMsg('');setErr(false);
    try{
      const response=await apiFetch(`/api/v1/chart-of-accounts/export.xlsx?company_id=${companyId}`);
      if(!response.ok)throw new Error(ar?'فشل تصدير شجرة الحسابات':'Chart export failed');
      const blob=await response.blob();const anchor=document.createElement('a');
      anchor.href=URL.createObjectURL(blob);anchor.download=`CORVAX_COA_${companyId}.xlsx`;anchor.click();
      URL.revokeObjectURL(anchor.href);
      setMsg(ar?'تم تصدير شجرة الحسابات إلى Excel':'Chart exported to Excel');
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };
  const importForm=()=>{
    if(!importFile)throw new Error(ar?'اختر ملف Excel أولًا':'Choose an Excel file first');
    const form=new FormData();form.append('file',importFile);return form;
  };
  const validateImport=async()=>{
    setBusy(true);setMsg('');setErr(false);setImportResult(null);
    try{
      const result=await json(`/api/v1/chart-of-accounts/import/validate?company_id=${companyId}`,{method:'POST',body:importForm()});
      setImportResult(result);setErr(!result.valid);
      setMsg(result.valid
        ?(ar?`نجحت المطابقة: ${result.summary.create} حساب جديد و${result.summary.update} تحديث.`:`Matched: ${result.summary.create} creates and ${result.summary.update} updates.`)
        :(ar?`فشل الفحص: ${result.summary.errors} خطأ. لن يتم تعديل النظام.`:`Validation failed with ${result.summary.errors} errors. Nothing was changed.`));
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };
  const applyImport=async()=>{
    if(!importResult?.valid)return;
    setBusy(true);setMsg('');setErr(false);
    try{
      const result=await json(`/api/v1/chart-of-accounts/import/apply?company_id=${companyId}`,{method:'POST',body:importForm()});
      setMsg(ar?`تم تطبيق الملف: ${result.summary.create} إضافة و${result.summary.update} تحديث.`:'Chart import applied.');
      setImportResult(null);setImportFile(null);await load();
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };

  const toggleActive=async(n:Node)=>{
    setBusy(true);setMsg('');setErr(false);
    try{
      await json(`/api/v1/chart-of-accounts/${n.code}`,{method:'PATCH',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({company_id:companyId,active:!n.active})});
      setMsg(ar?(n.active?`تم تعطيل ${n.code}`:`تم تنشيط ${n.code}`):(n.active?`${n.code} disabled`:`${n.code} enabled`));
      await load();
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };

  const remove=async(n:Node)=>{
    setBusy(true);setMsg('');setErr(false);
    try{
      const r=await json(`/api/v1/chart-of-accounts/${n.code}?company_id=${companyId}`,{method:'DELETE'});
      setMsg(ar?`تم حذف ${n.code}`+(r.parent_restored_to_postable?` وعاد ${r.parent_restored_to_postable} يقبل الترحيل`:'')
              :`Deleted ${n.code}`);
      await load();
    }catch(e:any){setMsg(String(e.message||e));setErr(true);}finally{setBusy(false);}
  };

  const matches=(n:Node):boolean=>{
    const q=filter.trim().toLowerCase();
    if(!q)return true;
    if(n.code.includes(q)||n.name_ar.toLowerCase().includes(q)||n.name_en.toLowerCase().includes(q))return true;
    return n.children.some(matches);
  };

  const row=(n:Node,depth=0)=>{
    if(!matches(n))return null;
    const hasKids=n.children.length>0;
    const isOpen=open[n.id] ?? (depth<1 || !!filter);
    return <div key={n.id}>
      <div style={{display:'flex',alignItems:'center',gap:8,padding:'7px 10px',
        paddingInlineStart:10+depth*20,borderBottom:'1px solid var(--border)',
        opacity:n.active?1:0.5}}>
        <button onClick={()=>setOpen(p=>({...p,[n.id]:!isOpen}))}
          style={{border:0,background:'transparent',cursor:hasKids?'pointer':'default',padding:2,visibility:hasKids?'visible':'hidden'}}>
          {isOpen?<ChevronDown size={14}/>:<ChevronLeft size={14}/>}
        </button>
        <code style={{fontWeight:700,minWidth:70}}>{n.code}</code>
        <span style={{flex:1}}>{ar?n.name_ar:n.name_en}</span>
        <span style={{...chip,background:'var(--panel-2, #eef2fb)',color:'#47536e'}}>L{n.level}</span>
        <span style={{...chip,background:'#eef2fb',color:'#3157d5'}}>{TYPE_AR[n.account_type]||n.account_type}</span>
        {n.is_postable
          ? <span style={{...chip,background:'#dcfce7',color:'#166534'}}>{ar?'يقبل الترحيل':'Postable'}</span>
          : <span style={{...chip,background:'#fef3c7',color:'#92400e'}}>{ar?'رئيسي':'Header'}</span>}
        {n.movement_lines>0&&<span style={{...chip,background:'#e0e7ff',color:'#3730a3'}}>{n.movement_lines} {ar?'حركة':'lines'}</span>}
        <button title={n.active?(ar?'تعطيل':'Disable'):(ar?'تنشيط':'Enable')} disabled={busy} onClick={()=>toggleActive(n)}
          style={{border:'1px solid var(--border)',background:'transparent',borderRadius:7,padding:'3px 7px',cursor:'pointer'}}>
          <Power size={13}/>
        </button>
        {n.movement_lines===0&&!hasKids&&
          <button title={ar?'حذف':'Delete'} disabled={busy} onClick={()=>remove(n)}
            style={{border:'1px solid var(--border)',background:'transparent',borderRadius:7,padding:'3px 7px',cursor:'pointer'}}>
            <Trash2 size={13}/>
          </button>}
      </div>
      {isOpen&&n.children.map(c=>row(c,depth+1))}
    </div>;
  };

  return <>
    <div className="kpis">
      <Kpi title={ar?'إجمالي الحسابات':'Accounts'} value={String(stats.total)} trend="" good icon={<Network size={22}/>} tone="blue"/>
      <Kpi title={ar?'أقصى مستوى':'Max depth'} value={String(stats.maxLevel)} trend={ar?'مستويات':'levels'} good icon={<Network size={22}/>} tone="violet"/>
      <Kpi title={ar?'تقبل الترحيل':'Postable'} value={String(stats.postable)} trend="" good icon={<Plus size={22}/>} tone="green"/>
      <Kpi title={ar?'حسابات رئيسية':'Headers'} value={String(stats.total-stats.postable)} trend={ar?'مجاميع':'totals'} good icon={<Info size={22}/>} tone="amber"/>
    </div>

    {msg&&<div style={{padding:11,margin:'12px 0',borderRadius:9,fontSize:14,lineHeight:1.8,
      background:err?'#fee2e2':'#dcfce7',color:err?'#991b1b':'#166534'}}>{msg}</div>}

    <Panel title={ar?'إضافة حساب':'Add an account'} icon={<Plus size={18}/>}>
      <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.8,lineHeight:1.9}}>
        {ar
          ? 'اختر الحساب الأب ثم أعطِ الحساب رقمًا داخل نطاقه. النوع يُورَث من الأب تلقائيًا. وبمجرد أن يصبح للحساب ابن، يتحوّل الأب إلى حساب رئيسي لا يقبل الترحيل — لأن المجموع لا يحمل حركاته الخاصة.'
          : 'Pick a parent, then give the account a code inside the parent range. The type is inherited. Once an account gains a child it becomes a header and stops accepting entries, because a total must not also hold its own movements.'}
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(190px,1fr))',gap:12,padding:12}}>
        <label>{ar?'الحساب الأب':'Parent account'}
          <select style={field} value={parentCode} onChange={e=>setParentCode(e.target.value)}>
            <option value="">{ar?'— حساب رئيسي جديد —':'— new root —'}</option>
            {flat.filter(n=>n.active).map(n=>
              <option key={n.id} value={n.code}>{'— '.repeat(Math.max(0,n.level-1))}{n.code} · {ar?n.name_ar:n.name_en}</option>)}
          </select></label>
        <label>{ar?'رقم الحساب':'Account code'}
          <input style={field} value={code} onChange={e=>setCode(e.target.value)}
            placeholder={expectedPrefix?`${expectedPrefix}...`:'100000'}/>
          {expectedPrefix&&<small style={{opacity:0.75}}>{ar?`يجب أن يبدأ بـ ${expectedPrefix}`:`must start with ${expectedPrefix}`}</small>}
        </label>
        <label>{ar?'الاسم (عربي)':'Name (Arabic)'}<input style={field} value={nameAr} onChange={e=>setNameAr(e.target.value)}/></label>
        <label>{ar?'الاسم (إنجليزي)':'Name (English)'}<input style={field} value={nameEn} onChange={e=>setNameEn(e.target.value)}/></label>
        <label style={{display:'flex',alignItems:'center',gap:8,marginTop:26}}>
          <input type="checkbox" checked={isCash} onChange={e=>setIsCash(e.target.checked)}/>
          {ar?'حساب نقدي (يدخل التدفقات النقدية)':'Cash account'}
        </label>
      </div>
      <div style={{padding:'0 12px 14px'}}>
        <button style={{...btn,opacity:busy?0.6:1}} disabled={busy} onClick={create}>{ar?'إنشاء الحساب':'Create account'}</button>
      </div>
    </Panel>

    <Panel title={ar?'تصدير وتعديل ومطابقة شجرة الحسابات':'Export, edit and reconcile the chart'} icon={<FileCheck2 size={18}/>}>
      <div style={{padding:'8px 12px 0',fontSize:13,opacity:0.85,lineHeight:1.9}}>
        {ar
          ? 'صدّر الملف، عدّل الأسماء أو أضف حسابات جديدة داخله، ثم ارفعه للفحص. النظام يراجع الأكواد والأب والنوع والمستوى والحركات السابقة أولًا؛ ولا يطبق أي تغيير إذا وُجد خطأ واحد.'
          : 'Export, edit names or add accounts, then upload for validation. Codes, parents, types, levels and posted history are checked before any change is applied.'}
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:12,padding:12,alignItems:'end'}}>
        <button style={{...btn,display:'inline-flex',alignItems:'center',justifyContent:'center',gap:7}} disabled={busy} onClick={exportExcel}><Download size={16}/>{ar?'تصدير Excel':'Export Excel'}</button>
        <label>{ar?'ملف شجرة الحسابات المعدّل':'Edited chart workbook'}<input type="file" accept=".xlsx" style={field}
          onChange={e=>{setImportFile(e.target.files?.[0]||null);setImportResult(null);}}/></label>
        <button style={{...btn,display:'inline-flex',alignItems:'center',justifyContent:'center',gap:7,opacity:importFile?1:.5}} disabled={busy||!importFile} onClick={validateImport}><FileCheck2 size={16}/>{ar?'مراجعة ومطابقة':'Validate & match'}</button>
        <button style={{...btn,display:'inline-flex',alignItems:'center',justifyContent:'center',gap:7,background:'#059669',opacity:importResult?.valid?1:.5}} disabled={busy||!importResult?.valid} onClick={applyImport}><Upload size={16}/>{ar?'اعتماد التعديلات':'Apply changes'}</button>
      </div>
      {importResult&&<DataTable
        headers={[ar?'سطر Excel':'Excel row',ar?'الحساب':'Account',ar?'الإجراء':'Action',ar?'النتيجة':'Result']}
        rows={importResult.rows.map((row:any)=>[
          String(row.excel_row),row.account_code,row.action,
          row.errors?.length?<span style={{color:'#b91c1c'}}>{row.errors.join(' | ')}</span>:<span style={{color:'#047857'}}>✓</span>,
        ])}/>}
    </Panel>

    <Panel title={ar?'شجرة الحسابات':'Chart of accounts'} icon={<Network size={18}/>}>
      <div style={{display:'flex',alignItems:'center',gap:8,padding:'10px 12px'}}>
        <Search size={15} style={{opacity:0.6}}/>
        <input style={{...field,marginTop:0}} value={filter} onChange={e=>setFilter(e.target.value)}
          placeholder={ar?'بحث برقم الحساب أو اسمه':'Search by code or name'}/>
      </div>
      <div style={{maxHeight:620,overflowY:'auto'}}>{tree.map(n=>row(n))}</div>
    </Panel>
  </>;
}
