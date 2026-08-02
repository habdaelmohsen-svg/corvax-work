import {useEffect, useMemo, useState} from 'react';
import {
  CalendarRange, Download, FileBarChart, Filter, Play, Printer, Search,
  Settings2, ShieldCheck, TableProperties, TriangleAlert,
} from 'lucide-react';
import {apiFetch} from '../api/client';
import {Kpi, Panel, fmt} from './ui';
import {ReportBuilderTab} from './reportBuilderTab';
import {
  exportSystemReportExcel, printSystemReportPdf,
  type ReportColumn, type ReportResult,
} from './reportExport';

type CatalogReport = {
  code: string;
  category: string;
  name_ar: string;
  name_en: string;
  priority: 'P0' | 'P1' | 'P2';
  source: string;
  period_mode: 'RANGE' | 'AS_OF';
  status: 'IMPLEMENTED';
  export_formats: string[];
};
type Catalog = {
  section_name_ar: string;
  section_name_en: string;
  report_count: number;
  reports: CatalogReport[];
  vat_profile: {filing_frequency: 'MONTHLY' | 'QUARTERLY'; return_layout_version: string};
  can_export: boolean;
  can_configure_tax: boolean;
};
type PeriodType = 'CUSTOM' | 'MONTH' | 'QUARTER' | 'YEAR';

const CATEGORY_LABELS: Record<string, [string, string]> = {
  VAT: ['ضريبة القيمة المضافة', 'VAT'],
  FINANCIAL: ['القوائم المالية', 'Financial Statements'],
  SALES: ['المبيعات والعملاء', 'Sales & Customers'],
  PURCHASES: ['المشتريات والموردون', 'Purchases & Suppliers'],
  INVENTORY: ['المخزون', 'Inventory'],
  GENERAL_LEDGER: ['الأستاذ العام', 'General Ledger'],
  CASH: ['النقد والبنوك', 'Cash & Banking'],
  FIXED_ASSETS: ['الأصول الثابتة', 'Fixed Assets'],
  BUDGET: ['الموازنة', 'Budget'],
  AUDIT: ['المراجعة', 'Audit'],
  CLOSE: ['الإقفال', 'Close'],
};
const iso = (date: Date) => date.toISOString().slice(0, 10);
const button = {padding: '9px 15px', borderRadius: 9, border: 'none', background: 'var(--accent, #1e40af)', color: '#fff', cursor: 'pointer', fontWeight: 700} as const;
const ghost = {padding: '8px 13px', borderRadius: 9, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontWeight: 650} as const;
const field = {display: 'block', width: '100%', marginTop: 5, padding: 9, border: '1px solid var(--border)', borderRadius: 9, background: 'var(--panel)', color: 'var(--text)'} as const;
const th = {textAlign: 'start', padding: '9px 11px', borderBottom: '2px solid var(--border)', background: 'var(--panel-2)', fontWeight: 750, fontSize: 12, position: 'sticky', top: 0, zIndex: 1} as const;
const td = {padding: '8px 11px', borderBottom: '1px solid var(--border)', fontSize: 12, verticalAlign: 'top'} as const;

async function json(url: string, init?: RequestInit) {
  const response = await apiFetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || payload));
  }
  return payload;
}

function recommendedPeriod(report?: CatalogReport | null): PeriodType {
  if (!report) return 'MONTH';
  if (report.code === 'FS-02' || report.code === 'FS-05' || report.code === 'FS-08') return 'QUARTER';
  if (report.code === 'FS-03' || report.code === 'FS-06' || report.code === 'FS-09') return 'YEAR';
  return 'MONTH';
}

function renderValue(value: unknown, column: ReportColumn, ar: boolean) {
  if (value === null || value === undefined || value === '') return '—';
  if (column.type === 'boolean') return value ? (ar ? 'نعم' : 'Yes') : (ar ? 'لا' : 'No');
  if (column.type === 'money' || column.type === 'number') return fmt(Number(value));
  if (column.type === 'integer') return new Intl.NumberFormat(ar ? 'ar-SA' : 'en-US', {maximumFractionDigits: 0}).format(Number(value));
  if (column.type === 'percent') return `${new Intl.NumberFormat(ar ? 'ar-SA' : 'en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(Number(value))}%`;
  return String(value);
}

export function ReportsCenterPage({ar, companyId, initialCategory = 'VAT'}: {ar: boolean; companyId: number; initialCategory?: string}) {
  const today = new Date();
  const [topTab, setTopTab] = useState<'system' | 'builder'>('system');
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [active, setActive] = useState<CatalogReport | null>(null);
  const [category, setCategory] = useState(initialCategory);
  const [search, setSearch] = useState('');
  const [periodType, setPeriodType] = useState<PeriodType>('MONTH');
  const [anchorDate, setAnchorDate] = useState(iso(today));
  const [startDate, setStartDate] = useState(iso(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [endDate, setEndDate] = useState(iso(today));
  const [branchId, setBranchId] = useState('');
  const [itemId, setItemId] = useState('');
  const [partyId, setPartyId] = useState('');
  const [method, setMethod] = useState<'direct' | 'indirect'>('indirect');
  const [slowDays, setSlowDays] = useState('90');
  const [obsoleteDays, setObsoleteDays] = useState('180');
  const [result, setResult] = useState<ReportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [profileBusy, setProfileBusy] = useState(false);

  useEffect(() => {
    let current = true;
    setMessage('');
    setResult(null);
    json(`/api/v1/system-reports/catalog?company_id=${companyId}`)
      .then((payload: Catalog) => {
        if (!current) return;
        setCatalog(payload);
        const first = payload.reports.find(report => report.category === initialCategory) || payload.reports[0] || null;
        setActive(first);
        setCategory(first?.category || 'VAT');
        setPeriodType(recommendedPeriod(first));
      })
      .catch(error => current && setMessage(String(error.message || error)));
    return () => { current = false; };
  }, [companyId, initialCategory]);

  const categories = useMemo(() => {
    const values: string[] = [];
    for (const report of catalog?.reports || []) if (!values.includes(report.category)) values.push(report.category);
    return values;
  }, [catalog]);
  const reports = useMemo(() => (catalog?.reports || []).filter(report => {
    if (report.category !== category) return false;
    const query = search.trim().toLowerCase();
    return !query || report.code.toLowerCase().includes(query) ||
      report.name_ar.toLowerCase().includes(query) || report.name_en.toLowerCase().includes(query);
  }), [catalog, category, search]);

  const chooseReport = (report: CatalogReport) => {
    setActive(report);
    setResult(null);
    setMessage('');
    setPeriodType(recommendedPeriod(report));
  };

  const run = async () => {
    if (!active) return;
    setBusy(true);
    setMessage('');
    try {
      const body: Record<string, unknown> = {
        company_id: companyId,
        report_code: active.code,
        period_type: periodType,
        anchor_date: anchorDate,
        method,
        slow_days: Number(slowDays),
        obsolete_days: Number(obsoleteDays),
        limit: 5000,
      };
      if (periodType === 'CUSTOM') {
        body.start_date = startDate;
        body.end_date = endDate;
      }
      if (branchId) body.branch_id = Number(branchId);
      if (itemId) body.item_id = Number(itemId);
      if (partyId) body.party_id = Number(partyId);
      const payload = await json('/api/v1/system-reports/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      setResult(payload);
      if (!payload.rows?.length) setMessage(ar ? 'اكتمل تشغيل التقرير، ولا توجد حركات مطابقة للفترة والفلاتر.' : 'Report completed; no matching transactions for the selected period and filters.');
    } catch (error: any) {
      setResult(null);
      setMessage(String(error.message || error));
    } finally {
      setBusy(false);
    }
  };

  const updateVatFrequency = async (filing_frequency: 'MONTHLY' | 'QUARTERLY') => {
    if (!catalog?.can_configure_tax) return;
    setProfileBusy(true);
    setMessage('');
    try {
      await json('/api/v1/system-reports/vat-profile', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          company_id: companyId,
          filing_frequency,
          return_layout_version: catalog.vat_profile.return_layout_version,
        }),
      });
      setCatalog({...catalog, vat_profile: {...catalog.vat_profile, filing_frequency}});
    } catch (error: any) {
      setMessage(String(error.message || error));
    } finally {
      setProfileBusy(false);
    }
  };

  const tab = (key: 'system' | 'builder', label: string) => (
    <button key={key} onClick={() => setTopTab(key)} style={{
      ...ghost, padding: '9px 18px',
      background: topTab === key ? 'var(--accent, #1e40af)' : 'transparent',
      color: topTab === key ? '#fff' : 'var(--text)',
    }}>{label}</button>
  );
  if (topTab === 'builder') {
    return <>
      <div style={{display: 'flex', gap: 8, margin: '4px 0 16px'}}>
        {tab('system', ar ? 'تقارير النظام الكاملة' : 'Complete System Reports')}
        {tab('builder', ar ? 'مصمّم التقارير' : 'Report Builder')}
      </div>
      <ReportBuilderTab ar={ar} companyId={companyId}/>
    </>;
  }

  const numericKeys = new Set(result?.columns.filter(column => ['money', 'number', 'integer', 'percent'].includes(column.type)).map(column => column.key));
  return <>
    <div style={{display: 'flex', gap: 8, margin: '4px 0 16px'}}>
      {tab('system', ar ? 'تقارير النظام الكاملة' : 'Complete System Reports')}
      {tab('builder', ar ? 'مصمّم التقارير' : 'Report Builder')}
    </div>

    <div className="kpis">
      <Kpi title={ar ? 'التقارير المنفذة' : 'Implemented Reports'} value={String(catalog?.report_count || 0)} trend="57 / 57" good icon={<FileBarChart size={22}/>} tone="blue"/>
      <Kpi title={ar ? 'الفئات' : 'Categories'} value={String(categories.length)} trend="" good icon={<TableProperties size={22}/>} tone="violet"/>
      <Kpi title={ar ? 'الأولوية' : 'Priority'} value={active?.priority || '—'} trend={active?.status || ''} good icon={<ShieldCheck size={22}/>} tone="green"/>
      <Kpi title={ar ? 'عدد السطور' : 'Rows'} value={String(result?.rows.length || 0)} trend={result?.metadata?.currency || ''} good icon={<CalendarRange size={22}/>} tone="amber"/>
    </div>

    <Panel title={ar ? 'مركز التقارير الشامل' : 'Comprehensive Reporting Center'} icon={<FileBarChart size={18}/>}>
      <div style={{padding: 12}}>
        <div style={{display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) auto', gap: 10, alignItems: 'end', marginBottom: 12}}>
          <label>{ar ? 'بحث بالاسم أو الكود' : 'Search by name or code'}
            <div style={{position: 'relative'}}>
              <Search size={16} style={{position: 'absolute', insetInlineStart: 10, top: 15, opacity: .55}}/>
              <input style={{...field, paddingInlineStart: 34}} value={search} onChange={event => setSearch(event.target.value)} placeholder="VAT-05 / قائمة الدخل"/>
            </div>
          </label>
          {catalog?.can_configure_tax && <label>{ar ? 'دورية إقرار VAT' : 'VAT Filing Frequency'}
            <select style={{...field, minWidth: 165}} disabled={profileBusy} value={catalog.vat_profile.filing_frequency} onChange={event => updateVatFrequency(event.target.value as 'MONTHLY' | 'QUARTERLY')}>
              <option value="MONTHLY">{ar ? 'شهري' : 'Monthly'}</option>
              <option value="QUARTERLY">{ar ? 'ربع سنوي' : 'Quarterly'}</option>
            </select>
          </label>}
        </div>

        <div style={{display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 11}}>
          {categories.map(key => {
            const label = CATEGORY_LABELS[key] || [key, key];
            const count = catalog?.reports.filter(report => report.category === key).length || 0;
            return <button key={key} onClick={() => {setCategory(key); setSearch('');}} style={{
              ...ghost,
              background: category === key ? 'var(--accent, #1e40af)' : 'transparent',
              color: category === key ? '#fff' : 'var(--text)',
            }}>{ar ? label[0] : label[1]} <small>({count})</small></button>;
          })}
        </div>

        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 8, marginBottom: 14}}>
          {reports.map(report => <button key={report.code} onClick={() => chooseReport(report)} style={{
            ...ghost, textAlign: 'start', minHeight: 58,
            borderColor: active?.code === report.code ? 'var(--accent, #1e40af)' : 'var(--border)',
            background: active?.code === report.code ? 'var(--panel-2)' : 'transparent',
          }}>
            <div style={{display: 'flex', justifyContent: 'space-between', gap: 8}}>
              <strong>{report.code}</strong>
              <small style={{color: report.priority === 'P0' ? '#b91c1c' : report.priority === 'P1' ? '#a16207' : '#64748b'}}>{report.priority}</small>
            </div>
            <div style={{fontSize: 12, marginTop: 4}}>{ar ? report.name_ar : report.name_en}</div>
          </button>)}
        </div>

        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(145px,1fr))', gap: 10, alignItems: 'end'}}>
          <label>{ar ? 'نوع الفترة' : 'Period Type'}
            <select style={field} value={periodType} onChange={event => setPeriodType(event.target.value as PeriodType)}>
              <option value="MONTH">{ar ? 'شهري' : 'Month'}</option>
              <option value="QUARTER">{ar ? 'ربع سنوي' : 'Quarter'}</option>
              <option value="YEAR">{ar ? 'سنوي' : 'Year'}</option>
              <option value="CUSTOM">{ar ? 'فترة مخصصة' : 'Custom'}</option>
            </select>
          </label>
          {periodType !== 'CUSTOM' && <label>{ar ? 'تاريخ مرجعي' : 'Anchor Date'}<input type="date" style={field} value={anchorDate} onChange={event => setAnchorDate(event.target.value)}/></label>}
          {periodType === 'CUSTOM' && <>
            <label>{ar ? 'من تاريخ' : 'From'}<input type="date" style={field} value={startDate} onChange={event => setStartDate(event.target.value)}/></label>
            <label>{ar ? 'إلى تاريخ' : 'To'}<input type="date" style={field} value={endDate} onChange={event => setEndDate(event.target.value)}/></label>
          </>}
          <label>{ar ? 'معرف الفرع (اختياري)' : 'Branch ID (optional)'}<input type="number" min="1" style={field} value={branchId} onChange={event => setBranchId(event.target.value)}/></label>
          {active?.code === 'INV-02' && <label>{ar ? 'معرف الصنف' : 'Item ID'}<input type="number" min="1" style={field} value={itemId} onChange={event => setItemId(event.target.value)}/></label>}
          {(active?.code.startsWith('SAL-0') || active?.code.startsWith('PUR-0')) && <label>{ar ? 'معرف الطرف (اختياري)' : 'Party ID (optional)'}<input type="number" min="1" style={field} value={partyId} onChange={event => setPartyId(event.target.value)}/></label>}
          {active?.code.startsWith('FS-0') && <label>{ar ? 'طريقة التدفقات' : 'Cash-flow Method'}
            <select style={field} value={method} onChange={event => setMethod(event.target.value as 'direct' | 'indirect')}>
              <option value="indirect">{ar ? 'غير مباشرة' : 'Indirect'}</option>
              <option value="direct">{ar ? 'مباشرة' : 'Direct'}</option>
            </select>
          </label>}
          {active?.code.startsWith('INV-0') && active.code !== 'INV-01' && active.code !== 'INV-02' && <>
            <label>{ar ? 'حد بطيء الحركة (يوم)' : 'Slow Days'}<input type="number" min="1" style={field} value={slowDays} onChange={event => setSlowDays(event.target.value)}/></label>
            <label>{ar ? 'حد غير المتحرك (يوم)' : 'Obsolete Days'}<input type="number" min="1" style={field} value={obsoleteDays} onChange={event => setObsoleteDays(event.target.value)}/></label>
          </>}
          <button style={{...button, opacity: busy ? .6 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7}} disabled={busy || !active} onClick={run}>
            <Play size={16}/>{busy ? (ar ? 'جارٍ التشغيل...' : 'Running...') : (ar ? 'تشغيل التقرير' : 'Run Report')}
          </button>
        </div>
      </div>
    </Panel>

    {message && <div style={{padding: 11, margin: '12px 0', borderRadius: 9, background: 'var(--panel-2)', display: 'flex', gap: 8, alignItems: 'center'}}>
      <TriangleAlert size={17}/><span>{message}</span>
    </div>}

    {result && <>
      <Panel title={`${result.metadata.report_code} — ${ar ? result.metadata.report_name_ar : result.metadata.report_name_en}`} icon={<TableProperties size={18}/>}>
        <div style={{padding: 12}}>
          <div style={{display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 10}}>
            <div style={{fontSize: 12, lineHeight: 1.8}}>
              <div><strong>{ar ? 'الشركة' : 'Company'}:</strong> {ar ? result.metadata.company_name_ar : result.metadata.company_name_en}</div>
              <div><strong>{ar ? 'الفترة' : 'Period'}:</strong> {result.metadata.period_start} → {result.metadata.period_end}</div>
              <div><strong>{ar ? 'وقت الاستخراج' : 'Generated'}:</strong> {result.metadata.generated_at} — {ar ? result.metadata.generated_by_ar : result.metadata.generated_by_en}</div>
            </div>
            <div style={{display: 'flex', gap: 8, alignItems: 'start'}}>
              <button style={{...ghost, display: 'flex', alignItems: 'center', gap: 6}} disabled={!catalog?.can_export} onClick={() => exportSystemReportExcel(result, ar)}>
                <Download size={16}/>{ar ? 'Excel احترافي' : 'Professional Excel'}
              </button>
              <button style={{...ghost, display: 'flex', alignItems: 'center', gap: 6}} disabled={!catalog?.can_export} onClick={() => printSystemReportPdf(result, ar)}>
                <Printer size={16}/>{ar ? 'طباعة / PDF' : 'Print / PDF'}
              </button>
            </div>
          </div>
          {result.warnings.length > 0 && <div style={{padding: 9, background: '#fff7ed', color: '#9a3412', border: '1px solid #fdba74', borderRadius: 8, marginBottom: 10}}>
            {result.warnings.map((warning, index) => <div key={index}>• {warning}</div>)}
          </div>}
          <div style={{overflow: 'auto', maxHeight: '65vh', border: '1px solid var(--border)', borderRadius: 8}}>
            <table style={{width: '100%', borderCollapse: 'collapse', whiteSpace: 'nowrap'}}>
              <thead><tr>{result.columns.map(column => <th key={column.key} style={th}>{ar ? column.name_ar : column.name_en}</th>)}</tr></thead>
              <tbody>{result.rows.length ? result.rows.map((row, rowIndex) => <tr key={rowIndex}>
                {result.columns.map(column => {
                  const value = row[column.key];
                  const negative = numericKeys.has(column.key) && Number(value) < 0;
                  return <td key={column.key} style={{...td, textAlign: numericKeys.has(column.key) ? 'end' : 'start', color: negative ? '#b91c1c' : undefined, background: negative ? '#fff1f2' : undefined}}>
                    {renderValue(value, column, ar)}
                  </td>;
                })}
              </tr>) : <tr><td colSpan={result.columns.length} style={{...td, textAlign: 'center', padding: 28}}>{ar ? 'لا توجد بيانات مطابقة' : 'No matching data'}</td></tr>}</tbody>
              {Object.keys(result.totals || {}).length > 0 && <tfoot><tr>{result.columns.map((column, index) => <td key={column.key} style={{...td, fontWeight: 800, background: 'var(--panel-2)', textAlign: numericKeys.has(column.key) ? 'end' : 'start'}}>
                {index === 0 ? (ar ? 'الإجمالي' : 'Total') : result.totals[column.key] !== undefined ? renderValue(result.totals[column.key], column, ar) : ''}
              </td>)}</tr></tfoot>}
            </table>
          </div>
          <div style={{display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', marginTop: 9, fontSize: 11, color: 'var(--muted)'}}>
            <span>{ar ? 'عدد السطور' : 'Rows'}: {result.rows.length}</span>
            <span style={{wordBreak: 'break-all'}}>{ar ? 'بصمة النتيجة' : 'Result fingerprint'}: {result.metadata.result_sha256}</span>
          </div>
        </div>
      </Panel>
    </>}
  </>;
}
