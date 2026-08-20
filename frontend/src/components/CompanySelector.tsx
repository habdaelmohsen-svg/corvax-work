import { useEffect, useMemo, useState } from 'react';
import { Building2, Dumbbell, Factory, Utensils, Languages, ArrowLeft, ArrowRight } from 'lucide-react';
import { translations } from '../i18n/translations';
import '../styles/company-selector.css';

type Lang = 'ar' | 'en';
type Scope = 'holding' | 'gym' | 'restaurant' | 'manufacturing';
type ApiCompany = {id:number;code:string;name_ar:string;name_en:string;currency:string;primary_color:string;logo_url?:string|null};
type UiCompany = ApiCompany & {id_scope:Scope;apiId:number;icon:typeof Building2;accent:string};

const scopeMap:Record<string,Scope>={HOLD:'holding',GYM:'gym',REST:'restaurant',MFG:'manufacturing'};
const iconMap={holding:Building2,gym:Dumbbell,restaurant:Utensils,manufacturing:Factory};

export function CompanySelector({lang,setLang,onContinue}:{lang:Lang;setLang:(l:Lang)=>void;onContinue:(company:any)=>void}){
  const [apiCompanies,setApiCompanies]=useState<ApiCompany[]>([]);
  const [selected,setSelected]=useState(1);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const t=translations[lang];
  const ar=lang==='ar';
  const Arrow=ar?ArrowLeft:ArrowRight;
  const companies=useMemo<UiCompany[]>(()=>apiCompanies.map(c=>{
    const id_scope=scopeMap[c.code]||'holding';
    return {...c,id_scope,apiId:c.id,icon:iconMap[id_scope],accent:c.primary_color||'#3157d5'};
  }),[apiCompanies]);
  const selectedCompany=companies.find(c=>c.apiId===selected);

  const [loadError,setLoadError]=useState(false);

  useEffect(()=>{
    const token=sessionStorage.getItem('corvax_token');
    fetch('/api/v1/companies',{headers:token?{Authorization:`Bearer ${token}`}:{}})
      .then(r=>r.ok?r.json():Promise.reject())
      .then((rows:ApiCompany[])=>{setApiCompanies(rows);if(rows.length)setSelected(rows[0].id)})
      // AUDIT M-02: never present demo companies when the API fails. Showing them
      // suggests the user has access to companies that may not exist.
      .catch(()=>{setApiCompanies([]);setLoadError(true);});
  },[]);

  async function continueToCompany(){
    const company=companies.find(c=>c.apiId===selected); if(!company)return;
    setLoading(true);setError('');
    try{
      const token=sessionStorage.getItem('corvax_token');
      const response=await fetch('/api/v1/auth/company-context',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({company_id:company.apiId})});
      if(!response.ok)throw new Error();
      const context=await response.json();
      try{
        const stored=JSON.parse(localStorage.getItem('corvax_user')||'{}');
        const byCompany={...(stored.permissions_by_company||{})};
        if(Array.isArray(context.permissions))byCompany[String(company.apiId)]=context.permissions;
        localStorage.setItem('corvax_user',JSON.stringify({...stored,permissions_by_company:byCompany}));
      }catch{/* Login payload remains the fallback if local storage is unavailable. */}
      onContinue({...company,id:company.id_scope});
    }catch{setError(ar?'تعذر تفعيل بيئة الشركة.':'Unable to activate company workspace.')}finally{setLoading(false)}
  }

  return <main className="page" dir={ar?'rtl':'ltr'}>
    <header className="topbar"><div className="brand"><div className="corvax-symbol"><span>C</span></div><div><strong>CORVAX</strong><span>BUSINESS PLATFORM</span></div></div><button className="lang-btn" onClick={()=>setLang(ar?'en':'ar')}><Languages size={18}/>{ar?'English':'العربية'}</button></header>
    <section className="hero"><div className="hero-copy"><span className="eyebrow">CORVAX BUSINESS WORKSPACE</span><h1>{t.chooseCompany}</h1><p>{t.subtitle}</p><div className="workspace-stats"><span><strong>{companies.length}</strong>{ar?'شركات متاحة':'Available companies'}</span><span><strong>1</strong>{ar?'هوية موحدة':'Unified identity'}</span><span><strong>24/7</strong>{ar?'مراقبة النظام':'System monitoring'}</span></div></div>
      <div className="company-grid">{companies.map(c=>{const Icon=c.icon;const active=selected===c.apiId;return <button key={c.apiId} className={`company-card ${active?'active':''}`} onClick={()=>setSelected(c.apiId)} style={{'--accent':c.accent} as React.CSSProperties}><div className="icon-wrap"><Icon size={26}/></div><div><strong>{ar?c.name_ar:c.name_en}</strong><span>{c.currency} · Multi Branch</span></div><div className="radio">{active&&<div/>}</div></button>})}</div>
      {selectedCompany&&<div className="selected-workspace"><div className="selected-workspace-mark"><selectedCompany.icon size={22}/></div><div><span>{ar?'سيتم فتح مساحة':'Opening workspace'}</span><strong>{ar?selectedCompany.name_ar:selectedCompany.name_en}</strong></div><small>{selectedCompany.currency} · {ar?'بيانات وصلاحيات مستقلة':'isolated data & permissions'}</small></div>}
      {error&&<div className="error">{error}</div>}
      <button className="continue-btn" disabled={loading} onClick={continueToCompany}>{loading?(ar?'جارٍ التفعيل...':'Activating...'):t.continue}<Arrow size={19}/></button>
      <div className="module-strip"><span>{t.finance}</span><span>{t.inventory}</span><span>{t.manufacturingModule}</span><span>{t.hr}</span></div>
    </section>
  </main>
}
