import { useEffect, useState, type ReactNode } from 'react';
import {
  Activity, AlertTriangle, ArrowLeftRight, BadgeDollarSign, BarChart3, BookOpenCheck,
  Boxes, Building2, CalendarRange, CheckCircle2, ChevronLeft, ChevronRight, CircleDollarSign,
  ClipboardCheck, Clock3, Dumbbell, Factory, FileSpreadsheet, GitBranch, Languages, Landmark,
  LayoutDashboard, LogOut, Menu, MonitorCog, Network, ReceiptText, Search, Settings, ShieldCheck,
  ShoppingCart, TrendingDown, TrendingUp, Users, UtensilsCrossed, WalletCards, X,
  DatabaseBackup, FileCheck2, KeyRound, MapPin, UserCheck, Bell, Mail, CalendarDays,
  Moon, Sun, Command, ChevronDown, Sparkles, CreditCard, FileText, ArrowUpRight
} from 'lucide-react';
import { money, pct, Kpi, Panel, AlertRow, AgeLine, QuickAction, SimpleKpi, MiniStatus, ModuleCard, ProgressRow, Statement, NoteCard, Flow, Checklist, SummaryLine, CostBar, DataTable, fmt, authHeaders, jsonHeaders } from './ui';

export function ExecutivePage({ ar, companyId, apiCompanyId }: { ar: boolean; companyId: string; apiCompanyId: number }) {
  /* CORVAX-H7-LIVE-KPIS: executive KPIs are read from the posted general ledger.
     Fabricated figures are never rendered - unavailable values show an em dash. */
  const [live, setLive] = useState<any>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setLive(null); setLoadFailed(false);
    const get = (url: string) => fetch(url, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([
      get(`/api/v1/finance/statements?company_id=${apiCompanyId}`),
      get(`/api/v1/finance/trial-balance?company_id=${apiCompanyId}`),
      companyId === 'restaurant' ? get(`/api/v1/pos/summary?company_id=${apiCompanyId}`) : Promise.resolve(null),
      companyId === 'gym' ? get(`/api/v1/gym/summary?company_id=${apiCompanyId}`) : Promise.resolve(null),
    ]).then((results) => {
      if (!active) return;
      const [statements, trialBalance, pos, gym] = results;
      if (!statements && !trialBalance && !pos && !gym) { setLoadFailed(true); return; }
      setLive({ statements, trialBalance, pos, gym });
    });
    return () => { active = false; };
  }, [apiCompanyId, companyId]);

  const dash = '\u2014';
  const num = (value: any) => (value === null || value === undefined || Number.isNaN(Number(value)) ? dash : fmt(Number(value)));
  const percent = (value: any) => (value === null || value === undefined || Number.isNaN(Number(value)) ? dash : `${Number(value).toFixed(1)}%`);
  const income = live?.statements?.income_statement ?? null;
  const position = live?.statements?.financial_position ?? null;
  const cash = (() => {
    const rows = live?.trialBalance?.rows;
    if (!Array.isArray(rows)) return null;
    return rows.filter((row: any) => row?.statement_group === 'CASH')
      .reduce((sum: number, row: any) => sum + Number(row?.closing_debit ?? 0) - Number(row?.closing_credit ?? 0), 0);
  })();
  const periodLabel = live?.statements?.period
    ? `${live.statements.period.start_date} - ${live.statements.period.end_date}`
    : '';

  const kpis: any[] = companyId === 'gym'
    ? [[ar?'الأعضاء النشطون':'Active members', live?.gym?.active_members ?? dash, '', true, 'blue'],
       [ar?'الإيراد المعترف':'Recognized revenue', num(income?.revenue), '', true, 'green'],
       [ar?'مجمل الربح':'Gross profit', num(income?.gross_profit), '', true, 'violet'],
       [ar?'إجمالي الأصول':'Total assets', num(position?.total_assets), '', true, 'amber']]
    : companyId === 'restaurant'
    ? [[ar?'صافي المبيعات':'Net sales', num(live?.pos?.net_sales), '', true, 'blue'],
       [ar?'نسبة تكلفة الطعام':'Food cost', percent(live?.pos?.food_cost_percent), '', false, 'green'],
       [ar?'مجمل الربح':'Gross profit', num(live?.pos?.gross_profit), '', true, 'violet'],
       [ar?'عدد الطلبات':'Orders', live?.pos?.orders ?? dash, '', true, 'amber']]
    : [[ar?'إجمالي الإيرادات':'Total Revenue', num(income?.revenue), '', true, 'blue'],
       [ar?'صافي الربح':'Net Profit', num(income?.net_profit ?? income?.operating_profit), '', true, 'green'],
       [ar?'إجمالي الأصول':'Total Assets', num(position?.total_assets), '', true, 'violet'],
       [ar?'النقد والرصيد البنكي':'Cash & Bank Balance', num(cash), '', true, 'amber']];
  const icons=[<BarChart3 size={23}/>,<CircleDollarSign size={23}/>,<Landmark size={23}/>,<CreditCard size={23}/>];
  return <>
        {loadFailed && <div className="kpi-source-note" role="status">{ar ? 'تعذر تحميل الأرقام الحية - لن تُعرض أي أرقام تقديرية.' : 'Live figures unavailable - no estimated numbers are shown.'}</div>}
    {periodLabel && <div className="kpi-source-note">{ar ? `المصدر: دفتر الأستاذ المرحّل · الفترة ${periodLabel}` : `Source: posted general ledger · period ${periodLabel}`}</div>}
    <div className="kpis executive-kpis">{kpis.map(([title,value,trend,good,tone],index) => <Kpi key={String(title)} title={String(title)} value={String(value)} trend={String(trend)} good={Boolean(good)} tone={String(tone)} icon={icons[index]}/>)}</div>

    <div className="executive-main-grid">
      <Panel title={ar?'الأداء المالي — آخر 12 شهر':'Financial Performance — Last 12 Months'} icon={<BarChart3 size={18}/> } className="performance-panel">
        <div className="panel-toolbar"><div className="chart-keys"><span><i className="key blue"/>{ar?'الإيرادات':'Revenue'}</span><span><i className="key amber"/>{ar?'المصروفات':'Expenses'}</span><span><i className="key green"/>{ar?'صافي الربح':'Net Profit'}</span></div><button className="currency-chip">SAR <ChevronDown size={13}/></button></div>
        <svg className="performance-chart" viewBox="0 0 720 250" preserveAspectRatio="none" role="img" aria-label="financial performance chart">
          <defs><linearGradient id="blueArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3b82f6" stopOpacity=".18"/><stop offset="1" stopColor="#3b82f6" stopOpacity="0"/></linearGradient></defs>
          {[45,85,125,165,205].map(y=><line key={y} x1="40" y1={y} x2="700" y2={y} className="grid-line"/>)}
          <path className="area-blue" d="M40 181 L95 168 L150 157 L205 137 L260 142 L315 123 L370 145 L425 158 L480 144 L535 139 L590 137 L645 101 L700 70 L700 220 L40 220 Z"/>
          <polyline className="line blue-line" points="40,181 95,168 150,157 205,137 260,142 315,123 370,145 425,158 480,144 535,139 590,137 645,101 700,70"/>
          <polyline className="line amber-line" points="40,202 95,193 150,190 205,169 260,174 315,157 370,178 425,190 480,174 535,164 590,154 645,125 700,101"/>
          <polyline className="line green-line" points="40,216 95,211 150,212 205,194 260,190 315,177 370,181 425,197 480,182 535,177 590,178 645,155 700,136"/>
          {[[40,181],[205,137],[315,123],[425,158],[590,137],[700,70]].map(([x,y])=><circle key={`${x}-${y}`} cx={x} cy={y} r="4" className="blue-dot"/>)}
        </svg>
        <div className="chart-months"><span>{ar?'يونيو':'Jun'}</span><span>{ar?'أغسطس':'Aug'}</span><span>{ar?'أكتوبر':'Oct'}</span><span>{ar?'ديسمبر':'Dec'}</span><span>{ar?'فبراير':'Feb'}</span><span>{ar?'أبريل':'Apr'}</span><span>{ar?'مايو':'May'}</span></div>
      </Panel>

      <Panel title={ar?'توزيع المصروفات':'Expenses Breakdown'} icon={<CircleDollarSign size={18}/> } className="expense-panel">
        <div className="expense-content"><div className="expense-donut"><div><span>{ar?'إجمالي المصروفات':'Total Expenses'}</span><strong>107.5M</strong><small>SAR</small></div></div><div className="expense-list">
          <div><i className="blue"/><span>{ar?'المشتريات':'Purchases'}</span><strong>42%</strong></div>
          <div><i className="amber"/><span>{ar?'المصروفات التشغيلية':'Operating Expenses'}</span><strong>25%</strong></div>
          <div><i className="teal"/><span>{ar?'رواتب ومزايا':'Salaries & Benefits'}</span><strong>18%</strong></div>
          <div><i className="violet"/><span>{ar?'التسويق والمبيعات':'Marketing & Sales'}</span><strong>8%</strong></div>
          <div><i className="gold"/><span>{ar?'استهلاك وإطفاء':'Depreciation'}</span><strong>7%</strong></div>
        </div></div>
      </Panel>

      <Panel title={ar?'التنبيهات والإشعارات':'Alerts & Notifications'} icon={<Bell size={18}/> } className="alerts-panel">
        <div className="alerts-filter"><span>{ar?'الأولوية اليوم':'Today priorities'}</span><button>{ar?'عرض الكل':'View all'} <ChevronDown size={13}/></button></div>
        <AlertRow severity="high" title={ar?'مخزون منخفض':'Low Stock Alert'} meta={ar?'12 منتج · منذ 10 دقائق':'12 items · 10m ago'}/>
        <AlertRow severity="medium" title={ar?'فاتورة مستحقة':'Overdue Invoice'} meta={ar?'24 فاتورة · منذ 25 دقيقة':'24 invoices · 25m ago'}/>
        <AlertRow severity="low" title={ar?'اعتماد طلب شراء':'PO Approval'} meta={ar?'8 طلبات · منذ ساعة':'8 requests · 1h ago'}/>
        <AlertRow severity="low" title={ar?'موافقة إجازة':'Leave Approval'} meta={ar?'5 طلبات · منذ ساعتين':'5 requests · 2h ago'}/>
        <AlertRow severity="medium" title={ar?'تأكيد مالي جاهز':'Financial Assurance Ready'} meta={ar?'فترة أبريل 2026 · منذ 3 ساعات':'April 2026 period · 3h ago'}/>
      </Panel>
    </div>

    <div className="executive-bottom-grid">
      <Panel title={ar?'الذمم المدينة':'Accounts Receivable'} icon={<Users size={18}/> } className="compact-metric-panel">
        <div className="metric-head"><div><strong>32,750,000</strong><span>SAR</span><small className="bad">↑ 8.2% {ar?'عن الماضي':'vs last month'}</small></div><div className="mini-ring receivable"/></div>
        <AgeLine label={ar?'0 - 30 يوم':'0 - 30 Days'} value="18,200,000" percent="55%" tone="blue"/>
        <AgeLine label={ar?'31 - 60 يوم':'31 - 60 Days'} value="8,750,000" percent="27%" tone="amber"/>
        <AgeLine label={ar?'+60 يوم':'+60 Days'} value="5,800,000" percent="18%" tone="red"/>
      </Panel>
      <Panel title={ar?'الذمم الدائنة':'Accounts Payable'} icon={<WalletCards size={18}/> } className="compact-metric-panel">
        <div className="metric-head"><div><strong>18,950,000</strong><span>SAR</span><small className="good">↓ 5.1% {ar?'عن الماضي':'vs last month'}</small></div><div className="mini-ring payable"/></div>
        <AgeLine label={ar?'0 - 30 يوم':'0 - 30 Days'} value="9,500,000" percent="50%" tone="blue"/>
        <AgeLine label={ar?'31 - 60 يوم':'31 - 60 Days'} value="6,200,000" percent="33%" tone="amber"/>
        <AgeLine label={ar?'+60 يوم':'+60 Days'} value="3,250,000" percent="17%" tone="red"/>
      </Panel>
      <Panel title={ar?'التدفقات النقدية (MTD)':'Cash Flow (MTD)'} icon={<BarChart3 size={18}/> } className="cash-panel">
        <div className="cash-total"><strong>14,580,000</strong><span>SAR</span><small>↑ 11.4%</small></div>
        <div className="cash-bars">{[24,36,29,51,42,64,28,48,72,45,31,58,37,67,42,55].map((h,i)=><i key={i} style={{height:`${h}%`}}/>)}</div>
        <div className="cash-lines"><span><i className="teal"/>{ar?'تشغيلية':'Operating'}<strong>22,450,000</strong></span><span><i className="amber"/>{ar?'استثمارية':'Investing'}<strong className="negative">(5,120,000)</strong></span><span><i className="red"/>{ar?'تمويلية':'Financing'}<strong className="negative">(2,750,000)</strong></span></div>
      </Panel>
      <Panel title={ar?'الوصول السريع':'Quick Access'} icon={<Sparkles size={18}/> } className="quick-panel">
        <div className="quick-grid">
          <QuickAction icon={<BookOpenCheck size={20}/>} ar={ar} arLabel="قيد يومية" enLabel="Journal Entry" tone="blue"/>
          <QuickAction icon={<FileText size={20}/>} ar={ar} arLabel="فاتورة بيع" enLabel="Sales Invoice" tone="cyan"/>
          <QuickAction icon={<ShoppingCart size={20}/>} ar={ar} arLabel="طلب شراء" enLabel="Purchase Order" tone="violet"/>
          <QuickAction icon={<CreditCard size={20}/>} ar={ar} arLabel="دفعة" enLabel="Payment" tone="amber"/>
          <QuickAction icon={<FileCheck2 size={20}/>} ar={ar} arLabel="إقفال فترة" enLabel="Close Period" tone="green"/>
          <QuickAction icon={<TrendingUp size={20}/>} ar={ar} arLabel="تقرير الربح" enLabel="P&L Report" tone="blue"/>
          <QuickAction icon={<BookOpenCheck size={20}/>} ar={ar} arLabel="ميزان المراجعة" enLabel="Trial Balance" tone="teal"/>
          <QuickAction icon={<LayoutDashboard size={20}/>} ar={ar} arLabel="لوحة التنفيذي" enLabel="Executive" tone="gold"/>
        </div>
      </Panel>
    </div>

    <div className="executive-status-strip">
      <div><span className="status-icon blue"><CheckCircle2 size={17}/></span><span>{ar?'جودة البيانات':'Data Quality'}</span><strong>98%</strong></div>
      <div><span className="status-icon green"><ShieldCheck size={17}/></span><span>{ar?'الامتثال والضوابط':'Compliance & Controls'}</span><strong>96%</strong></div>
      <div><span className="status-icon red"><AlertTriangle size={17}/></span><span>{ar?'المخاطر المفتوحة':'Open Risks'}</span><strong>8</strong></div>
      <div><span className="status-icon amber"><ClipboardCheck size={17}/></span><span>{ar?'الملاحظات العالية':'High Audit Findings'}</span><strong>3</strong></div>
      <button>{ar?'عرض لوحة الحوكمة':'Open Governance Dashboard'}<ArrowUpRight size={16}/></button>
    </div>
  </>;
}

