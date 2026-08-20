import {useCallback, useEffect, useMemo, useState} from 'react';
import {
  ArrowLeft, ArrowRight, Building2, CalendarDays, CheckCircle2, ChevronDown, ChevronLeft, Command,
  LogOut, Menu, Moon, Search, Sun,
} from 'lucide-react';
import {apiFetch} from '../api/client';
import {CorvaxAiAssistantHost} from '../components/ai-assistant';
import {NAV_GROUPS, navItems} from './navigation';
import {DashboardRoutes} from './routes';
import {useDashboardUi} from './store';
import type {CompanyScope, Lang, View} from './types';

const routeFromHash = () => (window.location.hash.replace(/^#\/?/, '').split('?')[0] || 'executive') as View;
const CORVAX_HISTORY_KEY = 'corvaxDashboardRoute';

type CorvaxHistoryState = {
  [CORVAX_HISTORY_KEY]?: true;
  corvaxFromHash?: string | null;
};

export function Shell({lang, setLang, onChangeCompany, onLogout}: {
  lang: Lang;
  setLang: (lang: Lang) => void;
  onChangeCompany: () => void;
  onLogout: () => void;
}) {
  const ar = lang === 'ar';
  const [view, setView] = useState<View>(routeFromHash);
  const navigate = useCallback((path: string, options?: {replace?: boolean}) => {
    const hash = `#${path.startsWith('/') ? path : `/${path}`}`;
    const currentHash = window.location.hash || '#/executive';
    // Clicking the already-active navigation item must not rewrite the current
    // history marker. Otherwise a direct/deep-link entry could look as if it
    // had an in-app predecessor and Back might leave CORVAX.
    if (!options?.replace && hash === currentHash) return;
    const currentState = (window.history.state || {}) as CorvaxHistoryState;
    const nextState: CorvaxHistoryState = {
      ...currentState,
      [CORVAX_HISTORY_KEY]: true,
      corvaxFromHash: options?.replace ? currentState.corvaxFromHash ?? null : currentHash,
    };
    if (options?.replace) window.history.replaceState(nextState, '', hash);
    else {
      window.location.hash = hash;
      // Setting location.hash creates the history entry. Mark that entry so the
      // shared Back button never sends a direct/deep-link visitor outside CORVAX.
      window.history.replaceState(nextState, '', hash);
    }
    setView(routeFromHash());
  }, []);
  const {menuOpen, darkMode, setMenuOpen, toggleTheme} = useDashboardUi();
  const [apiOnline, setApiOnline] = useState(false);
  const [apiVersion, setApiVersion] = useState('1.0.0-agreement-completion-rc27.4-r9.4');
  const [releaseId, setReleaseId] = useState('CORVAX-RC27.4-R9.4-DGTERA-V12-20260820');
  const [buildCommit, setBuildCommit] = useState('loading');
  const [globalQuery,setGlobalQuery]=useState('');
  const [navigationNotice, setNavigationNotice] = useState('');
  const company = useMemo(() => JSON.parse(localStorage.getItem('corvax_company') || '{}'), []);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const scope = (company.id || 'holding') as CompanyScope;
  const apiCompanyId = Number(company.apiId || 1);
  const user = useMemo(() => JSON.parse(localStorage.getItem('corvax_user') || '{}'), []);
  const userName = user.name || user.name_ar || user.name_en || (ar ? 'مستخدم CORVAX' : 'CORVAX User');
  // AUDIT H-06: the sidebar used to show all 44 sections to everyone regardless of
  // permissions. A user without access still saw the section and only met a 403
  // after clicking. Sections are now hidden unless the user holds a matching
  // permission for the active company (the wildcard "*" grants everything).
  const userPermissions = useMemo(() => {
    const byCompany = user?.permissions_by_company || {};
    const list = byCompany[String(apiCompanyId)] || byCompany[apiCompanyId] || [];
    return Array.isArray(list) ? list as string[] : [];
  }, [user, apiCompanyId]);

  const availableNav = useMemo(() => {
    const hasWildcard = userPermissions.includes('*');
    return navItems.filter((item) => {
      if (!item.scope.includes(scope)) return false;
      if (hasWildcard || !item.requires || item.requires.length === 0) return true;
      return item.requires.some((needed) =>
        userPermissions.some((held) => held === needed || held.startsWith(`${needed}.`)),
      );
    });
  }, [scope, userPermissions]);
  const current = availableNav.find((item) => item.key === view) || availableNav[0];
  const formattedDate = new Intl.DateTimeFormat(ar ? 'ar-SA' : 'en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  }).format(new Date());

  useEffect(() => {
    const state = (window.history.state || {}) as CorvaxHistoryState;
    if (!state[CORVAX_HISTORY_KEY]) {
      window.history.replaceState({
        ...state,
        [CORVAX_HISTORY_KEY]: true,
        corvaxFromHash: null,
      }, '', window.location.href);
    }
  }, []);

  useEffect(() => {
    Promise.all([
      apiFetch('/api/v1/modules/summary'),
      apiFetch('/api/v1/system/release'),
    ])
      .then(async([modulesResponse, releaseResponse]) => {
        setApiOnline(modulesResponse.ok && releaseResponse.ok);
        if (releaseResponse.ok) {
          const payload = await releaseResponse.json().catch(() => ({}));
          if (payload.version) setApiVersion(String(payload.version));
          if (payload.release_id) setReleaseId(String(payload.release_id));
          if (payload.commit) setBuildCommit(String(payload.commit).slice(0, 12));
        }
      })
      .catch(() => setApiOnline(false));
  }, []);

  useEffect(() => {
    const syncRoute = () => setView(routeFromHash());
    window.addEventListener('hashchange', syncRoute);
    return () => window.removeEventListener('hashchange', syncRoute);
  }, []);

  useEffect(() => {
    if (!availableNav.some((item) => item.key === view)) navigate('/executive', {replace: true});
  }, [availableNav, navigate, view]);

  const selectView = useCallback((next: View) => {
    if (!availableNav.some((item) => item.key === next)) {
      setNavigationNotice(ar
        ? 'لا تملك صلاحية الوصول إلى هذه الصفحة ضمن الشركة الحالية.'
        : 'You do not have access to this page for the current company.');
      setMenuOpen(false);
      return;
    }
    setNavigationNotice('');
    navigate(`/${next}`);
    setMenuOpen(false);
  }, [ar, availableNav, navigate, setMenuOpen]);

  const goBack = useCallback(() => {
    const state = (window.history.state || {}) as CorvaxHistoryState;
    if (state[CORVAX_HISTORY_KEY] && state.corvaxFromHash) {
      window.history.back();
      return;
    }
    navigate('/executive', {replace: true});
  }, [navigate]);

  return <main className={`dash ${darkMode ? 'theme-dark' : ''}`} dir={ar ? 'rtl' : 'ltr'}>
    <aside className={menuOpen ? 'open' : ''}>
      <div className="brand dark brand-sidebar">
        <div className="corvax-symbol" aria-hidden="true"><span>C</span></div>
        <div><strong>CORVAX</strong><span>BUSINESS PLATFORM</span></div>
      </div>
      <div className="nav-section-label">{ar ? 'مساحة العمل' : 'Workspace'}</div>
      <nav>
        {/* Ungrouped entry points stay at the top, always one click away. */}
        {availableNav.filter((item) => !item.group).map((item) => {
          const Icon = item.icon;
          return <button key={item.key} onClick={() => selectView(item.key)} className={view === item.key ? 'active' : ''}>
            <span className="nav-icon"><Icon size={18}/></span>
            <span className="nav-copy"><strong>{ar ? item.ar : item.en}</strong><small>{ar ? item.en : item.ar}</small></span>
            <ChevronLeft className="nav-chevron" size={14}/>
          </button>;
        })}

        {/* Grouped sections. A group opens automatically when it holds the active
            section, so deep links never land on a collapsed sidebar. */}
        {NAV_GROUPS.map((group) => {
          const items = availableNav.filter((item) => item.group === group.key);
          if (items.length === 0) return null;
          const holdsActive = items.some((item) => item.key === view);
          const open = openGroups[group.key] ?? holdsActive;
          return <div key={group.key} className="nav-group" data-group={group.key}>
            <button
              type="button"
              className={`nav-group-head${open ? ' open' : ''}${holdsActive ? ' has-active' : ''}`}
              onClick={() => setOpenGroups((prev) => ({...prev, [group.key]: !open}))}
              aria-expanded={open}
            >
              <span className="nav-group-title">{ar ? group.ar : group.en}</span>
              <span className="nav-group-count">{items.length}</span>
              <ChevronDown className="nav-group-chevron" size={14}/>
            </button>
            {open && <div className="nav-group-items">
              {items.map((item) => {
                const Icon = item.icon;
                return <button key={item.key} onClick={() => selectView(item.key)} className={view === item.key ? 'active' : ''}>
                  <span className="nav-icon"><Icon size={18}/></span>
                  <span className="nav-copy"><strong>{ar ? item.ar : item.en}</strong><small>{ar ? item.en : item.ar}</small></span>
                  <ChevronLeft className="nav-chevron" size={14}/>
                </button>;
              })}
            </div>}
          </div>;
        })}
      </nav>
      <div className="sidebar-footer">
        <button className="theme-switch" onClick={toggleTheme} aria-label={ar ? 'تغيير المظهر' : 'Toggle theme'}>
          <Moon size={16}/><span>{ar ? 'الوضع الليلي' : 'Dark mode'}</span><i className={darkMode ? 'on' : ''}><b/></i><Sun size={16}/>
        </button>
        <div className="sidebar-user">
          <div className="avatar">{String(userName).charAt(0)}</div>
          <div><strong>{userName}</strong><span>{ar ? 'مستخدم معتمد' : 'Authorized user'}</span></div>
          <button className="logout-icon" onClick={onLogout} title={ar ? 'تسجيل الخروج' : 'Logout'}><LogOut size={17}/></button>
        </div>
        <div className="version-line version-full" title={`${apiVersion} · ${releaseId} · ${buildCommit}`}>
          <strong>{apiVersion}</strong>
          <small>{releaseId}</small>
          <small>Commit: {buildCommit}</small>
          <span>© 2026 CORVAX</span>
        </div>
      </div>
    </aside>

    {menuOpen && <button className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-label={ar ? 'إغلاق القائمة' : 'Close menu'}/>} 

    <section className="workspace">
      <header className="app-header">
        <button className="mobile-menu" onClick={() => setMenuOpen(true)} aria-label={ar ? 'فتح القائمة' : 'Open menu'}><Menu size={20}/></button>
        <div className="global-search"><Search size={18}/><input value={globalQuery} onChange={(e)=>setGlobalQuery(e.target.value)} onKeyDown={(e)=>{if(e.key==='Enter'&&globalQuery.trim().length>=2){navigate(`/workbench?q=${encodeURIComponent(globalQuery.trim())}`,{replace:false})}}} aria-label={ar ? 'البحث في النظام' : 'Search system'} placeholder={ar ? 'البحث في النظام...' : 'Search in system...'}/><kbd><Command size={12}/> K</kbd></div>
        <CorvaxAiAssistantHost lang={lang}/>
        <div className="header-actions">
          
          
          
          
          <button className="company-switcher" onClick={onChangeCompany}><span className="company-badge"><Building2 size={18}/></span><span><strong>{ar ? (company.name_ar || 'المجموعة القابضة') : (company.name_en || 'Holding Group')}</strong><small>CORVAX Holding Co.</small></span><ChevronDown size={15}/></button>
          <button className="language-compact" onClick={() => setLang(ar ? 'en' : 'ar')}>{ar ? 'EN' : 'ع'}</button>
          <div className="user-profile"><div className="avatar">{String(userName).charAt(0)}</div><div><strong>{userName}</strong><small>{ar ? 'مستخدم معتمد' : 'Authorized user'}</small></div><ChevronDown size={14}/></div>
        </div>
      </header>

      <div className="page-heading">
        <div className="page-heading-copy">
          {view !== 'executive' && <button type="button" className="page-back-button" onClick={goBack} aria-label={ar ? 'الرجوع إلى الصفحة السابقة' : 'Back to previous page'}>
            {ar ? <ArrowRight size={16}/> : <ArrowLeft size={16}/>}<span>{ar ? 'رجوع' : 'Back'}</span>
          </button>}
          <span>{ar ? 'مرحبًا بعودتك' : 'Welcome back'}</span><h1>{view === 'executive' ? (ar ? `مرحبًا ${String(userName).split(' ')[0]} 👋` : `Hello ${String(userName).split(' ')[0]} 👋`) : (ar ? current.ar : current.en)}</h1><p>{view === 'executive' ? (ar ? 'إليك ملخصًا حيًا لأداء أعمالك والقرارات التي تحتاج اهتمامك.' : 'Here is a live view of business performance and decisions needing attention.') : (ar ? 'بيانات تشغيلية ومالية مترابطة مع إمكانية التتبع حتى المستند الأصلي.' : 'Connected operational and financial data with drill-through to source documents.')}</p>
        </div>
        <div className="heading-side"><div className="current-date"><CalendarDays size={18}/><span><strong>{formattedDate}</strong><small>{new Date().toLocaleDateString(ar ? 'ar-SA' : 'en-GB')}</small></span></div><div className={`status-pill ${apiOnline ? '' : 'offline'}`}><CheckCircle2 size={16}/>{apiOnline ? (ar ? 'متصل' : 'Connected') : (ar ? 'غير متصل' : 'Offline')}</div></div>
      </div>

      {navigationNotice&&<div className="navigation-notice" role="alert">{navigationNotice}</div>}
      <DashboardRoutes ar={ar} companyId={apiCompanyId} scope={scope} view={view} onNavigate={selectView}/>
    </section>
  </main>;
}
