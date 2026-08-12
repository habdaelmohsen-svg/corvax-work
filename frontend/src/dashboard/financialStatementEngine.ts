import {apiFetch} from '../api/client';

export type FinancialStatementKey = 'income' | 'balance' | 'cashflow';
export type StatementRowKind = 'line' | 'subtotal' | 'total';

export type ComparisonPeriods = {
  current: {start: string; end: string};
  previous: {start: string; end: string};
  priorYear: {start: string; end: string};
};

export type ComparativeStatements = {
  periods: ComparisonPeriods;
  current: any;
  previous: any;
  priorYear: any;
};

export type ComparativeStatementRow = {
  code: string;
  label: string;
  current: number;
  previous: number;
  priorYear: number;
  variance: number;
  variancePercent: number | null;
  kind: StatementRowKind;
};

type LineDefinition = {
  code: string;
  ar: string;
  en: string;
  section: 'income_statement' | 'financial_position' | 'cash_flows';
  field: string;
  sign?: number;
  kind?: StatementRowKind;
};

const DEFINITIONS: Record<FinancialStatementKey, LineDefinition[]> = {
  income: [
    {code:'revenue',ar:'الإيرادات',en:'Revenue',section:'income_statement',field:'revenue'},
    {code:'cost_of_revenue',ar:'تكلفة الإيرادات',en:'Cost of revenue',section:'income_statement',field:'cost_of_revenue',sign:-1},
    {code:'gross_profit',ar:'مجمل الربح',en:'Gross profit',section:'income_statement',field:'gross_profit',kind:'subtotal'},
    {code:'operating_expenses',ar:'المصروفات التشغيلية',en:'Operating expenses',section:'income_statement',field:'operating_expenses',sign:-1},
    {code:'operating_profit',ar:'الربح التشغيلي',en:'Operating profit',section:'income_statement',field:'operating_profit',kind:'subtotal'},
    {code:'other_income',ar:'إيرادات ومكاسب أخرى',en:'Other income and gains',section:'income_statement',field:'other_income'},
    {code:'other_expenses',ar:'مصروفات وخسائر أخرى',en:'Other expenses and losses',section:'income_statement',field:'other_expenses',sign:-1},
    {code:'finance_cost',ar:'تكاليف التمويل',en:'Finance costs',section:'income_statement',field:'finance_cost',sign:-1},
    {code:'profit_before_tax',ar:'الربح قبل الزكاة والضريبة',en:'Profit before zakat and tax',section:'income_statement',field:'profit_before_tax',kind:'subtotal'},
    {code:'zakat_tax',ar:'الزكاة والضريبة',en:'Zakat and tax',section:'income_statement',field:'zakat_tax',sign:-1},
    {code:'net_profit',ar:'صافي الربح',en:'Net profit',section:'income_statement',field:'net_profit',kind:'total'},
  ],
  balance: [
    {code:'current_assets',ar:'الأصول المتداولة',en:'Current assets',section:'financial_position',field:'current_assets'},
    {code:'non_current_assets',ar:'الأصول غير المتداولة',en:'Non-current assets',section:'financial_position',field:'non_current_assets'},
    {code:'total_assets',ar:'إجمالي الأصول',en:'Total assets',section:'financial_position',field:'total_assets',kind:'total'},
    {code:'current_liabilities',ar:'الالتزامات المتداولة',en:'Current liabilities',section:'financial_position',field:'current_liabilities'},
    {code:'non_current_liabilities',ar:'الالتزامات غير المتداولة',en:'Non-current liabilities',section:'financial_position',field:'non_current_liabilities'},
    {code:'total_liabilities',ar:'إجمالي الالتزامات',en:'Total liabilities',section:'financial_position',field:'total_liabilities',kind:'subtotal'},
    {code:'equity',ar:'حقوق الملكية',en:'Equity',section:'financial_position',field:'equity',kind:'subtotal'},
    {code:'liabilities_and_equity',ar:'إجمالي الالتزامات وحقوق الملكية',en:'Total liabilities and equity',section:'financial_position',field:'liabilities_and_equity',kind:'total'},
  ],
  cashflow: [
    {code:'net_operating',ar:'صافي التدفقات من الأنشطة التشغيلية',en:'Net cash from operating activities',section:'cash_flows',field:'net_operating',kind:'subtotal'},
    {code:'net_investing',ar:'صافي التدفقات من الأنشطة الاستثمارية',en:'Net cash from investing activities',section:'cash_flows',field:'net_investing',kind:'subtotal'},
    {code:'net_financing',ar:'صافي التدفقات من الأنشطة التمويلية',en:'Net cash from financing activities',section:'cash_flows',field:'net_financing',kind:'subtotal'},
    {code:'net_change',ar:'صافي التغير في النقد وما في حكمه',en:'Net change in cash and cash equivalents',section:'cash_flows',field:'net_change',kind:'total'},
    {code:'opening_cash',ar:'النقد وما في حكمه أول الفترة',en:'Cash and cash equivalents at period start',section:'cash_flows',field:'opening_cash'},
    {code:'closing_cash',ar:'النقد وما في حكمه آخر الفترة',en:'Cash and cash equivalents at period end',section:'cash_flows',field:'closing_cash',kind:'total'},
  ],
};

const two = (value: number) => String(value).padStart(2, '0');

export function localYmd(value = new Date()): string {
  return `${value.getFullYear()}-${two(value.getMonth() + 1)}-${two(value.getDate())}`;
}

export function currentYearStart(value = new Date()): string {
  return `${value.getFullYear()}-01-01`;
}

function parseYmd(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function utcYmd(value: Date): string {
  return `${value.getUTCFullYear()}-${two(value.getUTCMonth() + 1)}-${two(value.getUTCDate())}`;
}

function addDays(value: string, days: number): string {
  const date = parseYmd(value);
  date.setUTCDate(date.getUTCDate() + days);
  return utcYmd(date);
}

function shiftYear(value: string, years: number): string {
  const date = parseYmd(value);
  const targetYear = date.getUTCFullYear() + years;
  const month = date.getUTCMonth();
  const lastDay = new Date(Date.UTC(targetYear, month + 1, 0)).getUTCDate();
  return utcYmd(new Date(Date.UTC(targetYear, month, Math.min(date.getUTCDate(), lastDay))));
}

export function comparisonPeriods(start: string, end: string): ComparisonPeriods {
  const startDate = parseYmd(start);
  const endDate = parseYmd(end);
  if (Number.isNaN(startDate.valueOf()) || Number.isNaN(endDate.valueOf()) || startDate > endDate) {
    throw new Error('Invalid reporting period');
  }
  const inclusiveDays = Math.round((endDate.valueOf() - startDate.valueOf()) / 86400000) + 1;
  return {
    current: {start, end},
    previous: {start: addDays(start, -inclusiveDays), end: addDays(start, -1)},
    priorYear: {start: shiftYear(start, -1), end: shiftYear(end, -1)},
  };
}

async function statement(companyId: number, period: {start: string; end: string}, method: 'direct' | 'indirect') {
  const query = new URLSearchParams({
    company_id: String(companyId),
    start_date: period.start,
    end_date: period.end,
    method,
  });
  const response = await apiFetch(`/api/v1/finance/statements?${query.toString()}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Financial statement load failed');
  return payload;
}

export async function fetchComparativeStatements(
  companyId: number,
  start: string,
  end: string,
  method: 'direct' | 'indirect' = 'indirect',
): Promise<ComparativeStatements> {
  const periods = comparisonPeriods(start, end);
  const [current, previous, priorYear] = await Promise.all([
    statement(companyId, periods.current, method),
    statement(companyId, periods.previous, method),
    statement(companyId, periods.priorYear, method),
  ]);
  return {periods, current, previous, priorYear};
}

function amount(payload: any, definition: LineDefinition): number {
  const raw = Number(payload?.[definition.section]?.[definition.field] || 0);
  return raw * (definition.sign || 1);
}

export function buildStatementRows(
  key: FinancialStatementKey,
  data: ComparativeStatements,
  ar: boolean,
): ComparativeStatementRow[] {
  return DEFINITIONS[key].map((definition) => {
    const current = amount(data.current, definition);
    const previous = amount(data.previous, definition);
    const priorYear = amount(data.priorYear, definition);
    const variance = current - previous;
    return {
      code: definition.code,
      label: ar ? definition.ar : definition.en,
      current,
      previous,
      priorYear,
      variance,
      variancePercent: previous === 0 ? null : (variance / Math.abs(previous)) * 100,
      kind: definition.kind || 'line',
    };
  });
}

export function statementTitle(key: FinancialStatementKey, ar: boolean): string {
  const titles: Record<FinancialStatementKey, [string, string]> = {
    income: ['قائمة الربح أو الخسارة', 'Statement of Profit or Loss'],
    balance: ['قائمة المركز المالي', 'Statement of Financial Position'],
    cashflow: ['قائمة التدفقات النقدية', 'Statement of Cash Flows'],
  };
  return titles[key][ar ? 0 : 1];
}

export function formatStatementAmount(value: number): string {
  const formatted = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0}).format(Math.abs(value));
  return value < 0 ? `(${formatted})` : formatted;
}

export function formatVariancePercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}
