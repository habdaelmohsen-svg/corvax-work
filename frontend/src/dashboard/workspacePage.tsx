import {useEffect, useMemo, useState} from 'react';
import {Download, RefreshCw, Search, ShieldCheck, Workflow} from 'lucide-react';
import {navItems} from './navigation';
import type {View} from './types';
import {DataTable, Kpi, Panel, authHeaders, money} from './ui';

type QueueItem={module:string;item_type:string;id:number;number:string;status:string;title:string;amount:number;created_at?:string;view?:View};

type ModuleResult={key:View;ar:string;en:string};

const queryFromHash=()=>{
  try{return new URLSearchParams(window.location.hash.split('?')[1]||'').get('q')||''}
  catch{return ''}
};

export function WorkspacePage({ar,companyId,onNavigate}:{ar:boolean;companyId:number;onNavigate:(view:View)=>void}){
  const [items,setItems]=useState<QueueItem[]>([]);const [counts,setCounts]=useState<Record<string,number>>({});
  const [query,setQuery]=useState(queryFromHash);const [results,setResults]=useState<QueueItem[]>([]);
  const [modules,setModules]=useState<ModuleResult[]>([]);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  const load=async()=>{setBusy(true);try{const r=await fetch(`/api/v1/workspace/work-queue?company_id=${companyId}&limit=200`,{headers:authHeaders()});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Work queue failed');setItems(data.items||[]);setCounts(data.by_module||{});setMessage('')}catch(e:any){setMessage(e.message)}finally{setBusy(false)}};
  useEffect(()=>{load()},[companyId]);
  useEffect(()=>{
    const sync=()=>{const next=queryFromHash();setQuery(next);if(next.trim().length>=2)void search(next)};
    window.addEventListener('hashchange',sync);sync();
    return()=>window.removeEventListener('hashchange',sync);
  },[companyId]); // eslint-disable-line react-hooks/exhaustive-deps
  async function search(raw=query){
    const normalized=raw.trim().toLowerCase();
    if(normalized.length<2){setResults([]);setModules([]);return}
    const aliases:Record<string,string[]>={
      vatReturn:['vat','ضريبة القيمة المضافة','الاقرار الضريبي','الإقرار الضريبي'],
      reports:['تقارير','reports','اعمار العملاء','أعمار العملاء','اعمار الموردين','أعمار الموردين','القوائم المالية'],
      hr:['موظف','الموظفين','الوردية','الورديات','فرع','الفروع','رواتب','payroll','shift','branch'],
      cipProjects:['مشروع','مشروعات','تحت التنفيذ','cip','project'],
    };
    setModules(navItems.filter(item=>{
      const hay=[item.ar,item.en,item.key,...(aliases[item.key]||[])].join(' ').toLowerCase();
      return hay.includes(normalized);
    }).slice(0,12).map(item=>({key:item.key,ar:item.ar,en:item.en})));
    setBusy(true);
    try{const r=await fetch(`/api/v1/workspace/search?company_id=${companyId}&q=${encodeURIComponent(raw.trim())}`,{headers:authHeaders()});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Search failed');setResults(data.results||[]);setMessage('')}catch(e:any){setMessage(e.message)}finally{setBusy(false)}
  }
  const totalAmount=useMemo(()=>items.reduce((n,x)=>n+Number(x.amount||0),0),[items]);
  const shown=query.trim().length>=2?results:items;
  async function exportCsv(){const r=await fetch(`/api/v1/workspace/work-queue.csv?company_id=${companyId}`,{headers:authHeaders()});if(!r.ok){setMessage(ar?'تعذر التصدير':'Export failed');return}const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`corvax-work-queue-${companyId}.csv`;a.click();URL.revokeObjectURL(url)}
  return <>
    <div className="kpis rich"><Kpi title={ar?'إجمالي المهام المفتوحة':'Open work items'} value={String(items.length)} trend={ar?'من قاعدة البيانات مباشرة':'Live database'} good={items.length===0}/><Kpi title={ar?'النادي':'Gym'} value={String(counts.GYM||0)} trend={ar?'عضويات ومرافق':'Memberships & facilities'} good={(counts.GYM||0)===0}/><Kpi title={ar?'المطاعم ونقاط البيع':'Restaurant & POS'} value={String(counts.POS||0)} trend={ar?'إلغاءات وتسويات':'Controls & settlements'} good={(counts.POS||0)===0}/><Kpi title={ar?'الرواتب':'Payroll'} value={String(counts.HR||0)} trend={money.format(totalAmount)} good={(counts.HR||0)===0}/><Kpi title={ar?'طلبات شراء بانتظار الاعتماد':'Procurement approvals'} value={String(counts.PROCUREMENT||0)} trend={ar?'طلبات شراء مرسلة':'Submitted requisitions'} good={(counts.PROCUREMENT||0)===0}/></div>
    <div className="journal-footer"><span>{message||(ar?'مركز موحد للبحث والمهام والاعتمادات مع منع الاعتماد الذاتي.':'Unified search, work queue and approvals with maker-checker control.')}</span><div style={{display:'flex',gap:8}}><button disabled={busy} onClick={load}><RefreshCw size={15}/>{ar?'تحديث':'Refresh'}</button><button onClick={exportCsv}><Download size={15}/>{ar?'تصدير CSV':'Export CSV'}</button></div></div>
    <Panel title={ar?'البحث الشامل في النظام':'Global system search'} icon={<Search size={18}/> }><div className="workbench-search"><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==='Enter'&&search()} placeholder={ar?'ابحث عن VAT أو التقارير أو رقم مستند...':'Search VAT, reports, or a document number...'}/><button disabled={busy||query.trim().length<2} onClick={()=>search()}>{ar?'بحث':'Search'}</button>{query&&<button className="secondary" onClick={()=>{setQuery('');setResults([]);setModules([])}}>{ar?'مسح':'Clear'}</button>}</div></Panel>
    {query.trim().length>=2&&<Panel title={ar?'صفحات ووحدات مطابقة':'Matching pages and modules'} icon={<Search size={18}/>}>
      {modules.length?<div className="module-search-results">{modules.map(module=><button key={module.key} onClick={()=>onNavigate(module.key)}><strong>{ar?module.ar:module.en}</strong><span>{ar?module.en:module.ar}</span></button>)}</div>:<div style={{padding:14,opacity:.75}}>{ar?'لا توجد صفحة مطابقة للاسم؛ نتائج المستندات تظهر أدناه.':'No page name matched; document results appear below.'}</div>}
    </Panel>}
    <div className="three-columns"><div className="mini-status"><Workflow size={20}/><div><span>{ar?'قائمة موحدة':'Unified queue'}</span><strong>{items.length}</strong><small>{ar?'مرتبة حسب الأحدث':'Newest first'}</small></div></div><div className="mini-status"><ShieldCheck size={20}/><div><span>{ar?'الرقابة':'Control'}</span><strong>Maker–Checker</strong><small>{ar?'منع الاعتماد الذاتي':'Self-approval blocked'}</small></div></div><div className="mini-status"><Search size={20}/><div><span>{ar?'نتائج البحث':'Search results'}</span><strong>{query?results.length:items.length}</strong><small>{ar?'عبر المستندات والمالية والمخزون والتشغيل':'Across documents, finance, inventory and operations'}</small></div></div></div>
    <Panel title={query?(ar?'نتائج البحث':'Search results'):(ar?'قائمة العمل والاعتمادات':'Work queue and approvals')} icon={<Workflow size={18}/> }><DataTable headers={[ar?'الوحدة':'Module',ar?'النوع':'Type',ar?'الرقم':'Number',ar?'الوصف':'Description',ar?'القيمة':'Amount',ar?'الحالة':'Status',ar?'التاريخ':'Created']} rows={shown.map(r=>[r.module,r.item_type,r.view?<button key={`${r.item_type}-${r.id}`} className="link-button" onClick={()=>onNavigate(r.view!)}>{r.number}</button>:r.number,r.title,money.format(Number(r.amount||0)),r.status,r.created_at?new Date(r.created_at).toLocaleString(ar?'ar-SA':'en-GB'):'—'])}/></Panel>
  </>;
}
