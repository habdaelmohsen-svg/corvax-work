import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  AlertTriangle, ArrowUpRight, BarChart3, Bell, BookOpenCheck, CalendarDays, CheckCircle2,
  CircleDollarSign, ClipboardCheck, CreditCard, FileCheck2, FileText, Landmark,
  LayoutDashboard, ShieldCheck, ShoppingCart, Sparkles, TrendingUp, Users, WalletCards,
} from 'lucide-react';
import { AgeLine, AlertRow, Kpi, Panel, QuickAction, authHeaders, fmt } from './ui';
import { navigateFromExecutive, type ExecutiveNavigationKey } from './executiveNavigation';
import type { View } from './types';

export function ExecutivePage({ ar, companyId, apiCompanyId, onNavigate }: {
  ar: boolean;
  companyId: string;
  apiCompanyId: number;
  onNavigate: (view: View) => void;
}) {
  /* CORVAX-H7-LIVE-KPIS: executive KPIs are read from the posted general ledger.
     Fabricated figures are never rendered - unavailable values show an em dash. */
  const [live, setLive] = useState<any>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setLive(null); setLoadFailed(false);
    const get = (url: string) => fetch(url, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const today = new Date().toISOString().slice(0, 10);
    Promise.all([
      get(`/api/v1/finance/statements?company_id=${apiCompanyId}`),
      get(`/api/v1/finance/trial-balance?company_id=${apiCompanyId}`),
      companyId === 'restaurant' ? get(`/api/v1/pos/summary?company_id=${apiCompanyId}`) : Promise.resolve(null),
      companyId === 'gym' ? get(`/api/v1/gym/summary?company_id=${apiCompanyId}`) : Promise.resolve(null),
      companyId === 'holding' || companyId === 'restaurant'
        ? get(`/api/v1/integrations/dgtera/executive-summary?company_id=${apiCompanyId}`)
        : Promise.resolve(null),
      get(`/api/v1/subledgers/aging?company_id=${apiCompanyId}&ledger_type=AR&as_of_date=${today}`),
      get(`/api/v1/subledgers/aging?company_id=${apiCompanyId}&ledger_type=AP&as_of_date=${today}`),
      get(`/api/v1/inventory/stock-summary?company_id=${apiCompanyId}`),
      get(`/api/v1/governance/summary?company_id=${apiCompanyId}`),
    ]).then((results) => {
      if (!active) return;
      const [statements, trialBalance, pos, gym, dgtera, arAging, apAging, inventory, governance] = results;
      if (!results.some(Boolean)) { setLoadFailed(true); return; }
      setLive({ statements, trialBalance, pos, gym, dgtera, arAging, apAging, inventory, governance });
    });
    return () => { active = false; };
  }, [apiCompanyId, companyId]);

  const dash = '\u2014';
  const numeric = (value: unknown): number | null => {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const num = (value: unknown) => {
    const parsed = numeric(value);
    return parsed === null ? dash : fmt(parsed);
  };
  const signedNum = (value: unknown) => {
    const parsed = numeric(value);
    if (parsed === null) return dash;
    return parsed < 0 ? `(${fmt(Math.abs(parsed))})` : fmt(parsed);
  };
  const percent = (value: unknown) => {
    const parsed = numeric(value);
    return parsed === null ? dash : `${parsed.toFixed(1)}%`;
  };
  const income = live?.statements?.income_statement ?? null;
  const position = live?.statements?.financial_position ?? null;
  const cashFlows = live?.statements?.cash_flows ?? null;
  const cash = (() => {
    const rows = live?.trialBalance?.rows;
    if (!Array.isArray(rows)) return null;
    return rows.filter((row: any) => row?.statement_group === 'CASH')
      .reduce((sum: number, row: any) => sum + Number(row?.closing_debit ?? 0) - Number(row?.closing_credit ?? 0), 0);
  })();
  const periodLabel = live?.statements?.period
    ? `${live.statements.period.start_date} - ${live.statements.period.end_date}`
    : '';
  const go = (key: ExecutiveNavigationKey) => navigateFromExecutive(key, onNavigate);
  const positive = (value: unknown) => Math.max(0, numeric(value) ?? 0);
  const expenseParts = [
    { label: ar ? 'تكلفة الإيراد' : 'Cost of revenue', value: positive(income?.cost_of_revenue), tone: 'blue', color: 'var(--cv-blue)' },
    { label: ar ? 'المصروفات التشغيلية' : 'Operating expenses', value: positive(income?.operating_expenses), tone: 'amber', color: 'var(--cv-amber)' },
    { label: ar ? 'تكاليف التمويل' : 'Finance costs', value: positive(income?.finance_cost), tone: 'teal', color: 'var(--cv-teal)' },
    { label: ar ? 'الزكاة والضريبة' : 'Zakat and tax', value: positive(income?.zakat_tax), tone: 'violet', color: 'var(--cv-violet)' },
    { label: ar ? 'مصروفات أخرى' : 'Other expenses', value: positive(income?.other_expenses), tone: 'gold', color: 'var(--cv-gold)' },
  ];
  const totalExpenses = income ? expenseParts.reduce((sum, item) => sum + item.value, 0) : null;
  const expenseShare = (value: number) => totalExpenses && totalExpenses > 0 ? `${(value / totalExpenses * 100).toFixed(1)}%` : dash;
  const expenseGradient = (() => {
    if (!totalExpenses || totalExpenses <= 0) return 'conic-gradient(var(--cv-border) 0 100%)';
    let cursor = 0;
    return `conic-gradient(${expenseParts.map((item) => {
      const start = cursor;
      cursor += item.value / totalExpenses * 100;
      return `${item.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`;
    }).join(',')})`;
  })();
  const performanceRows = [
    { label: ar ? 'الإيرادات' : 'Revenue', value: numeric(income?.revenue), tone: 'blue' },
    {
      label: ar ? 'إجمالي المصروفات' : 'Total expenses',
      value: totalExpenses,
      tone: 'amber',
    },
    { label: ar ? 'صافي الربح' : 'Net profit', value: numeric(income?.net_profit), tone: 'green' },
  ];
  const performanceMax = Math.max(1, ...performanceRows.map((item) => Math.abs(item.value ?? 0)));

  const aging = (report: any) => {
    const buckets = report?.buckets;
    if (!buckets) return null;
    const current30 = positive(buckets.CURRENT) + positive(buckets['1_30']);
    const middle = positive(buckets['31_60']);
    const over60 = positive(buckets['61_90']) + positive(buckets['91_120']) + positive(buckets.OVER_120);
    const total = current30 + middle + over60;
    const share = (value: number) => total > 0 ? `${(value / total * 100).toFixed(0)}%` : '0%';
    return { current30, middle, over60, total, share };
  };
  const arAging = aging(live?.arAging);
  const apAging = aging(live?.apAging);
  const overdueAr = Array.isArray(live?.arAging?.details)
    ? live.arAging.details.filter((item: any) => Number(item?.overdue_days ?? 0) > 0).length
    : null;
  const overdueAp = Array.isArray(live?.apAging?.details)
    ? live.apAging.details.filter((item: any) => Number(item?.overdue_days ?? 0) > 0).length
    : null;
  const lowStock = Array.isArray(live?.inventory)
    ? live.inventory.filter((item: any) => item?.low_stock === true).length
    : null;
  const governance = live?.governance ?? null;
  const qualityChecks = [
    live?.trialBalance?.balanced,
    position?.balanced,
    live?.arAging?.reconciled,
    live?.apAging?.reconciled,
  ].filter((value) => typeof value === 'boolean') as boolean[];
  const dataQuality = qualityChecks.length
    ? `${(qualityChecks.filter(Boolean).length / qualityChecks.length * 100).toFixed(0)}%`
    : dash;
  const controlCount = numeric(governance?.controls);
  const ineffectiveControls = numeric(governance?.ineffective_controls);
  const controlEffectiveness = controlCount !== null && ineffectiveControls !== null
    ? (controlCount > 0 ? `${(Math.max(0, controlCount - ineffectiveControls) / controlCount * 100).toFixed(0)}%` : '100%')
    : dash;
  const alertCount = (value: number | null, singularAr: string, pluralAr: string, singularEn: string, pluralEn: string) => {
    if (value === null) return ar ? 'غير متاح من المصدر' : 'Source unavailable';
    if (ar) return `${value} ${value === 1 ? singularAr : pluralAr}`;
    return `${value} ${value === 1 ? singularEn : pluralEn}`;
  };
  const cashBars = [
    { key: 'operating', value: numeric(cashFlows?.net_operating), tone: 'teal' },
    { key: 'investing', value: numeric(cashFlows?.net_investing), tone: 'amber' },
    { key: 'financing', value: numeric(cashFlows?.net_financing), tone: 'red' },
  ];
  const cashBarMax = Math.max(1, ...cashBars.map((item) => Math.abs(item.value ?? 0)));
  const dgteraYear = live?.dgtera?.periods?.YEAR?.metrics?.current;

  const kpis: Array<[string, string | number, string, boolean, string, ExecutiveNavigationKey]> = companyId === 'gym'
    ? [[ar?'الأعضاء النشطون':'Active members', live?.gym?.active_members ?? dash, '', true, 'blue', 'gymMembers'],
       [ar?'الإيراد المعترف':'Recognized revenue', num(income?.revenue), '', true, 'green', 'revenue'],
       [ar?'مجمل الربح':'Gross profit', num(income?.gross_profit), '', true, 'violet', 'grossProfit'],
       [ar?'إجمالي الأصول':'Total assets', num(position?.total_assets), '', true, 'amber', 'totalAssets']]
    : companyId === 'restaurant'
    ? [[ar?'صافي إيرادات المبيعات':'Net sales revenue', num(dgteraYear?.subtotal), ar?'دون الضريبة — منذ بداية السنة':'Excluding VAT — year to date', true, 'blue', 'restaurantSales'],
       [ar?'ضريبة المبيعات':'Sales VAT', num(dgteraYear?.vat), ar?'من DGTERA':'From DGTERA', true, 'green', 'restaurantSales'],
       [ar?'إجمالي المبيعات':'Gross sales', num(dgteraYear?.sales), ar?'شامل الضريبة':'Including VAT', true, 'violet', 'restaurantSales'],
       [ar?'عدد الطلبات':'Orders', dgteraYear?.orders ?? dash, ar?'منذ بداية السنة':'Year to date', true, 'amber', 'restaurantOrders']]
    : [[ar?'إجمالي الإيرادات (صافي)':'Total Revenue (Net)', num(dgteraYear?.subtotal), ar?'مبيعات المطاعم دون الضريبة':'Restaurant sales excluding VAT', true, 'blue', 'revenue'],
       [ar?'صافي الربح':'Net Profit', num(income?.net_profit ?? income?.operating_profit), '', true, 'green', 'netProfit'],
       [ar?'إجمالي الأصول':'Total Assets', num(position?.total_assets), '', true, 'violet', 'totalAssets'],
       [ar?'النقد والرصيد البنكي':'Cash & Bank Balance', num(cash), '', true, 'amber', 'cashBalance']];
  const icons=[<BarChart3 size={23}/>,<CircleDollarSign size={23}/>,<Landmark size={23}/>,<CreditCard size={23}/>];
  const showDgteraHome = companyId === 'holding' || companyId === 'restaurant';
  const dgteraCards: Array<{
    key: 'DAY' | 'WEEK' | 'MONTH' | 'YEAR';
    title: string;
    target: ExecutiveNavigationKey;
    tone: string;
    icon: ReactNode;
  }> = [
    {key:'DAY', title:ar?'صافي مبيعات اليوم':'Today net sales', target:'dgteraDailySales', tone:'blue', icon:<ShoppingCart size={23}/>},
    {key:'WEEK', title:ar?'صافي مبيعات الأسبوع':'Week-to-date net sales', target:'dgteraWeeklySales', tone:'violet', icon:<CalendarDays size={23}/>},
    {key:'MONTH', title:ar?'صافي مبيعات الشهر':'Month-to-date net sales', target:'dgteraMonthlySales', tone:'amber', icon:<BarChart3 size={23}/>},
    {key:'YEAR', title:ar?'صافي مبيعات السنة':'Year-to-date net sales', target:'dgteraYearlySales', tone:'green', icon:<TrendingUp size={23}/>},
  ];
  const dgteraTrend = (period: any) => {
    const change = numeric(period?.comparison?.previous_change_percent);
    if (change === null) return ar ? 'لا توجد فترة سابقة للمقارنة' : 'No previous-period comparison';
    const value = `${change > 0 ? '+' : ''}${change.toFixed(1)}%`;
    return ar ? `${value} عن الفترة السابقة` : `${value} vs previous period`;
  };
  return <>
        {loadFailed && <div className="kpi-source-note" role="status">{ar ? 'تعذر تحميل الأرقام الحية - لن تُعرض أي أرقام تقديرية.' : 'Live figures unavailable - no estimated numbers are shown.'}</div>}
    {periodLabel && <div className="kpi-source-note">{ar ? `المصدر: دفتر الأستاذ المرحّل · الفترة ${periodLabel}` : `Source: posted general ledger · period ${periodLabel}`}</div>}
    <div className="kpis executive-kpis">{kpis.map(([title,value,trend,good,tone,target],index) => <Kpi key={String(title)} title={String(title)} value={String(value)} trend={String(trend)} good={Boolean(good)} tone={String(tone)} icon={icons[index]} onClick={()=>go(target)}/>)}</div>

    {showDgteraHome && <>
      <div className="kpi-source-note">
        {live?.dgtera
          ? (ar ? 'صافي مبيعات DGTERA دون الضريبة — تظهر في القابضة وشركة المطاعم من نفس السجل دون تكرار.' : 'DGTERA net sales excluding VAT — shared by holding and restaurant from one non-duplicated record set.')
          : (ar ? 'مبيعات DGTERA غير متاحة حاليًا؛ افتح بطاقة المبيعات لمراجعة حالة الربط.' : 'DGTERA sales are currently unavailable; open a sales card to review the connection.')}
      </div>
      <div className="kpis executive-kpis dgtera-home-kpis">{dgteraCards.map((card) => {
        const period = live?.dgtera?.periods?.[card.key];
        return <Kpi
          key={card.key}
          title={card.title}
          value={num(period?.metrics?.current?.subtotal)}
          trend={dgteraTrend(period)}
          good={(numeric(period?.comparison?.previous_change_percent) ?? 0) >= 0}
          tone={card.tone}
          icon={card.icon}
          onClick={()=>go(card.target)}
        />;
      })}</div>
    </>}

    <div className="executive-main-grid">
      <Panel title={ar?'الأداء المالي — الفترة الحالية':'Financial Performance — Current Period'} icon={<BarChart3 size={18}/> } className="performance-panel" onOpen={()=>go('financialPerformance')} openLabel={ar?'فتح القوائم المالية':'Open financial statements'}>
        <div className="panel-toolbar"><div className="chart-keys"><span><i className="key blue"/>{ar?'الإيرادات':'Revenue'}</span><span><i className="key amber"/>{ar?'المصروفات':'Expenses'}</span><span><i className="key green"/>{ar?'صافي الربح':'Net Profit'}</span></div><span className="currency-chip">SAR</span></div>
        <div className="live-performance-chart" role="img" aria-label={ar?'الإيرادات والمصروفات وصافي الربح للفترة الحالية':'Revenue, expenses and net profit for the current period'}>
          {performanceRows.map((item) => <div className="live-performance-row" key={item.label}>
            <span>{item.label}</span>
            <div><i className={item.tone} style={{width: item.value === null ? '0%' : `${Math.max(2, Math.abs(item.value) / performanceMax * 100)}%`}}/></div>
            <strong className={(item.value ?? 0) < 0 ? 'negative' : ''}>{signedNum(item.value)}</strong>
          </div>)}
        </div>
        <div className="live-source-caption">{periodLabel || (ar?'لا توجد فترة مالية متاحة من المصدر.':'No financial period is available from the source.')}</div>
      </Panel>

      <Panel title={ar?'توزيع المصروفات':'Expenses Breakdown'} icon={<CircleDollarSign size={18}/> } className="expense-panel" onOpen={()=>go('expenseBreakdown')} openLabel={ar?'فتح تفاصيل المصروفات':'Open expense details'}>
        <div className="expense-content"><div className="expense-donut" style={{background: expenseGradient}}><div><span>{ar?'إجمالي المصروفات':'Total Expenses'}</span><strong>{num(totalExpenses)}</strong><small>SAR</small></div></div><div className="expense-list">
          {expenseParts.map((item) => <div key={item.label}><i className={item.tone}/><span>{item.label}</span><strong>{expenseShare(item.value)}</strong></div>)}
        </div></div>
      </Panel>

      <Panel title={ar?'التنبيهات والإشعارات':'Alerts & Notifications'} icon={<Bell size={18}/> } className="alerts-panel" onOpen={()=>go('allAlerts')} openLabel={ar?'فتح مركز العمل':'Open work center'}>
        <div className="alerts-filter"><span>{ar?'الأولوية اليوم':'Today priorities'}</span><button type="button" onClick={()=>go('allAlerts')}>{ar?'عرض الكل':'View all'} <ArrowUpRight size={13}/></button></div>
        <AlertRow severity={lowStock ? 'high' : 'low'} title={ar?'مخزون تحت حد إعادة الطلب':'Items Below Reorder Level'} meta={alertCount(lowStock,'صنف','أصناف','item','items')} onClick={()=>go('lowStockAlert')}/>
        <AlertRow severity={overdueAr ? 'medium' : 'low'} title={ar?'فواتير عملاء متأخرة':'Overdue Customer Invoices'} meta={alertCount(overdueAr,'فاتورة','فواتير','invoice','invoices')} onClick={()=>go('overdueInvoiceAlert')}/>
        <AlertRow severity={overdueAp ? 'medium' : 'low'} title={ar?'فواتير موردين متأخرة':'Overdue Supplier Invoices'} meta={alertCount(overdueAp,'فاتورة','فواتير','invoice','invoices')} onClick={()=>go('overdueInvoiceAlert')}/>
        <AlertRow severity={numeric(governance?.high_residual_risks) ? 'high' : 'low'} title={ar?'مخاطر متبقية مرتفعة':'High Residual Risks'} meta={alertCount(numeric(governance?.high_residual_risks),'خطر','مخاطر','risk','risks')} onClick={()=>go('openRisks')}/>
        <AlertRow severity={numeric(governance?.overdue_findings) ? 'medium' : 'low'} title={ar?'ملاحظات مراجعة متأخرة':'Overdue Audit Findings'} meta={alertCount(numeric(governance?.overdue_findings),'ملاحظة','ملاحظات','finding','findings')} onClick={()=>go('auditFindings')}/>
      </Panel>
    </div>

    <div className="executive-bottom-grid">
      <Panel title={ar?'الذمم المدينة':'Accounts Receivable'} icon={<Users size={18}/> } className="compact-metric-panel" onOpen={()=>go('receivables')} openLabel={ar?'فتح أعمار الذمم المدينة':'Open receivables aging'}>
        <div className="metric-head"><div><strong>{num(arAging?.total)}</strong><span>SAR</span><small className={live?.arAging?.reconciled ? 'good' : 'bad'}>{live?.arAging ? (live.arAging.reconciled ? (ar?'متطابق مع الأستاذ العام':'Reconciled to GL') : (ar?'يوجد فرق مطابقة':'Reconciliation difference')) : (ar?'المصدر غير متاح':'Source unavailable')}</small></div><div className="mini-ring receivable"/></div>
        <AgeLine label={ar?'0 - 30 يوم':'0 - 30 Days'} value={num(arAging?.current30)} percent={arAging?.share(arAging.current30) ?? dash} tone="blue"/>
        <AgeLine label={ar?'31 - 60 يوم':'31 - 60 Days'} value={num(arAging?.middle)} percent={arAging?.share(arAging.middle) ?? dash} tone="amber"/>
        <AgeLine label={ar?'+60 يوم':'+60 Days'} value={num(arAging?.over60)} percent={arAging?.share(arAging.over60) ?? dash} tone="red"/>
      </Panel>
      <Panel title={ar?'الذمم الدائنة':'Accounts Payable'} icon={<WalletCards size={18}/> } className="compact-metric-panel" onOpen={()=>go('payables')} openLabel={ar?'فتح أعمار الذمم الدائنة':'Open payables aging'}>
        <div className="metric-head"><div><strong>{num(apAging?.total)}</strong><span>SAR</span><small className={live?.apAging?.reconciled ? 'good' : 'bad'}>{live?.apAging ? (live.apAging.reconciled ? (ar?'متطابق مع الأستاذ العام':'Reconciled to GL') : (ar?'يوجد فرق مطابقة':'Reconciliation difference')) : (ar?'المصدر غير متاح':'Source unavailable')}</small></div><div className="mini-ring payable"/></div>
        <AgeLine label={ar?'0 - 30 يوم':'0 - 30 Days'} value={num(apAging?.current30)} percent={apAging?.share(apAging.current30) ?? dash} tone="blue"/>
        <AgeLine label={ar?'31 - 60 يوم':'31 - 60 Days'} value={num(apAging?.middle)} percent={apAging?.share(apAging.middle) ?? dash} tone="amber"/>
        <AgeLine label={ar?'+60 يوم':'+60 Days'} value={num(apAging?.over60)} percent={apAging?.share(apAging.over60) ?? dash} tone="red"/>
      </Panel>
      <Panel title={ar?'التدفقات النقدية (MTD)':'Cash Flow (MTD)'} icon={<BarChart3 size={18}/> } className="cash-panel" onOpen={()=>go('cashFlow')} openLabel={ar?'فتح الخزينة والتسويات':'Open treasury and reconciliation'}>
        <div className="cash-total"><strong>{num(cashFlows?.closing_cash)}</strong><span>SAR</span><small className={cashFlows?.cash_reconciled ? 'good' : 'bad'}>{cashFlows ? (cashFlows.cash_reconciled ? (ar?'متطابق مع حركة النقد':'Cash movement reconciled') : (ar?'فرق مطابقة نقدية':'Cash reconciliation difference')) : (ar?'المصدر غير متاح':'Source unavailable')}</small></div>
        <div className="cash-bars">{cashBars.map((item)=><i key={item.key} className={item.tone} title={signedNum(item.value)} style={{height:`${item.value === null ? 0 : Math.max(8, Math.abs(item.value) / cashBarMax * 100)}%`}}/>)}</div>
        <div className="cash-lines"><span><i className="teal"/>{ar?'تشغيلية':'Operating'}<strong className={(cashBars[0].value ?? 0)<0?'negative':''}>{signedNum(cashBars[0].value)}</strong></span><span><i className="amber"/>{ar?'استثمارية':'Investing'}<strong className={(cashBars[1].value ?? 0)<0?'negative':''}>{signedNum(cashBars[1].value)}</strong></span><span><i className="red"/>{ar?'تمويلية':'Financing'}<strong className={(cashBars[2].value ?? 0)<0?'negative':''}>{signedNum(cashBars[2].value)}</strong></span></div>
      </Panel>
      <Panel title={ar?'الوصول السريع':'Quick Access'} icon={<Sparkles size={18}/> } className="quick-panel">
        <div className="quick-grid">
          <QuickAction icon={<BookOpenCheck size={20}/>} ar={ar} arLabel="قيد يومية" enLabel="Journal Entry" tone="blue" onClick={()=>go('journalEntry')}/>
          <QuickAction icon={<FileText size={20}/>} ar={ar} arLabel="فاتورة بيع" enLabel="Sales Invoice" tone="cyan" onClick={()=>go('salesInvoice')}/>
          <QuickAction icon={<ShoppingCart size={20}/>} ar={ar} arLabel="طلب شراء" enLabel="Purchase Order" tone="violet" onClick={()=>go('purchaseOrder')}/>
          <QuickAction icon={<CreditCard size={20}/>} ar={ar} arLabel="دفعة" enLabel="Payment" tone="amber" onClick={()=>go('payment')}/>
          <QuickAction icon={<FileCheck2 size={20}/>} ar={ar} arLabel="إقفال فترة" enLabel="Close Period" tone="green" onClick={()=>go('closePeriod')}/>
          <QuickAction icon={<TrendingUp size={20}/>} ar={ar} arLabel="تقرير الربح" enLabel="P&L Report" tone="blue" onClick={()=>go('profitReport')}/>
          <QuickAction icon={<BookOpenCheck size={20}/>} ar={ar} arLabel="ميزان المراجعة" enLabel="Trial Balance" tone="teal" onClick={()=>go('trialBalance')}/>
          <QuickAction icon={<LayoutDashboard size={20}/>} ar={ar} arLabel="مركز التقارير" enLabel="Reports Center" tone="gold" onClick={()=>go('reportsCenter')}/>
        </div>
      </Panel>
    </div>

    <div className="executive-status-strip">
      <button type="button" className="status-metric" onClick={()=>go('dataQuality')}><span className="status-icon blue"><CheckCircle2 size={17}/></span><span>{ar?'سلامة المطابقات':'Reconciliation Quality'}</span><strong>{dataQuality}</strong></button>
      <button type="button" className="status-metric" onClick={()=>go('compliance')}><span className="status-icon green"><ShieldCheck size={17}/></span><span>{ar?'فعالية الضوابط':'Control Effectiveness'}</span><strong>{controlEffectiveness}</strong></button>
      <button type="button" className="status-metric" onClick={()=>go('openRisks')}><span className="status-icon red"><AlertTriangle size={17}/></span><span>{ar?'المخاطر المرتفعة':'High Risks'}</span><strong>{num(governance?.high_residual_risks)}</strong></button>
      <button type="button" className="status-metric" onClick={()=>go('auditFindings')}><span className="status-icon amber"><ClipboardCheck size={17}/></span><span>{ar?'الملاحظات المتأخرة':'Overdue Findings'}</span><strong>{num(governance?.overdue_findings)}</strong></button>
      <button type="button" className="governance-button" onClick={()=>go('governance')}>{ar?'عرض لوحة الحوكمة':'Open Governance Dashboard'}<ArrowUpRight size={16}/></button>
    </div>
  </>;
}
