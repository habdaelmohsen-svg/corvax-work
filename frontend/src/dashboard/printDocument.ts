export type PrintCell = string | number | null | undefined;

export type PrintMeta = {
  label: string;
  value: PrintCell;
};

export type PrintDocumentOptions = {
  ar: boolean;
  title: string;
  subtitle?: string;
  documentLabel?: string;
  columns: string[];
  rows: PrintCell[][];
  meta?: PrintMeta[];
  numericColumns?: number[];
  totals?: PrintCell[];
  status?: string;
  landscape?: boolean;
};

type StoredCompany = {
  code?: string;
  name_ar?: string;
  name_en?: string;
  currency?: string;
  logo_url?: string | null;
  primary_color?: string;
};

const escapeHtml = (value: PrintCell) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#039;');

const storedCompany = (): StoredCompany => {
  try {
    const parsed = JSON.parse(localStorage.getItem('corvax_company') || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const safeAccent = (value?: string) => value && /^#[0-9a-f]{6}$/i.test(value) ? value : '#2347a5';

const safeLogoUrl = (value?: string | null) => {
  if (!value) return null;
  if (/^data:image\/(?:png|jpeg|jpg|webp|gif);base64,[a-z0-9+/=\s]+$/i.test(value)) return value;
  try {
    const resolved = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(resolved.protocol) ? resolved.href : null;
  } catch {
    return null;
  }
};

const statusLabel = (status: string, ar: boolean) => {
  const labels: Record<string, [string, string]> = {
    DRAFT: ['مسودة', 'Draft'],
    SUBMITTED: ['مقدّم', 'Submitted'],
    PENDING_APPROVAL: ['بانتظار الاعتماد', 'Pending approval'],
    APPROVED: ['معتمد', 'Approved'],
    POSTED: ['مرحّل', 'Posted'],
    REVERSED: ['معكوس', 'Reversed'],
  };
  const found = labels[String(status || '').toUpperCase()];
  return found ? found[ar ? 0 : 1] : status;
};

export function printBusinessDocument(options: PrintDocumentOptions): boolean {
  const printWindow = window.open('', '_blank');
  if (!printWindow) return false;
  // Keep a usable Window reference for writing/printing, then sever reverse access.
  // This avoids the null return that some browsers produce with the noopener feature.
  printWindow.opener = null;

  const company = storedCompany();
  const ar = options.ar;
  const dir = ar ? 'rtl' : 'ltr';
  const lang = ar ? 'ar' : 'en';
  const companyName = ar
    ? (company.name_ar || company.name_en || 'CORVAX')
    : (company.name_en || company.name_ar || 'CORVAX');
  const companyCode = company.code || 'CORVAX';
  const companyMark = companyCode.replace(/[^A-Za-z0-9\u0600-\u06ff]/g, '').slice(0, 3).toUpperCase() || 'C';
  const currency = company.currency || 'SAR';
  const accent = safeAccent(company.primary_color);
  const logo = safeLogoUrl(company.logo_url);
  const numeric = new Set(options.numericColumns || []);
  const generatedAt = new Intl.DateTimeFormat(ar ? 'ar-SA' : 'en-GB', {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date());
  const meta = [
    ...(options.meta || []),
    {label: ar ? 'العملة' : 'Currency', value: currency},
    {label: ar ? 'تاريخ الاستخراج' : 'Generated at', value: generatedAt},
  ];
  const status = options.status ? statusLabel(options.status, ar) : '';
  const orientation = options.landscape || options.columns.length > 5 ? 'landscape' : 'portrait';

  const logoHtml = logo
    ? `<img class="company-logo" src="${escapeHtml(logo)}" alt="${escapeHtml(companyName)}"><div class="company-mark fallback">${escapeHtml(companyMark)}</div>`
    : `<div class="company-mark">${escapeHtml(companyMark)}</div>`;
  const headerCells = options.columns.map((column, index) =>
    `<th class="${numeric.has(index) ? 'numeric' : ''}">${escapeHtml(column)}</th>`).join('');
  const bodyRows = options.rows.map((row) => `<tr>${options.columns.map((_, index) =>
    `<td class="${numeric.has(index) ? 'numeric' : ''}">${escapeHtml(row[index])}</td>`).join('')}</tr>`).join('');
  const totalsRow = options.totals
    ? `<tfoot><tr>${options.columns.map((_, index) => `<td class="${numeric.has(index) ? 'numeric' : ''}">${escapeHtml(options.totals?.[index])}</td>`).join('')}</tr></tfoot>`
    : '';
  const metaHtml = meta.filter((item) => item.value !== null && item.value !== undefined && item.value !== '')
    .map((item) => `<div class="meta-item"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></div>`).join('');

  const html = `<!doctype html>
<html lang="${lang}" dir="${dir}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${escapeHtml(options.title)}</title>
  <style>
    :root{--accent:${accent};--ink:#172033;--muted:#657089;--line:#d9deea;--soft:#f4f6fa}
    @page{size:A4 ${orientation};margin:12mm 10mm 15mm}
    *{box-sizing:border-box}
    html{background:#eef1f7}
    body{margin:0 auto;max-width:1180px;background:#fff;color:var(--ink);font-family:"Segoe UI",Tahoma,Arial,"Noto Sans Arabic",sans-serif;font-size:11px;line-height:1.55;-webkit-print-color-adjust:exact;print-color-adjust:exact}
    .document{padding:28px 30px 20px}
    .top-rule{height:5px;background:var(--accent);border-radius:5px;margin-bottom:20px}
    .document-header{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;padding-bottom:16px;border-bottom:1px solid var(--line)}
    .company-identity{display:flex;align-items:center;gap:12px;min-width:0}
    .company-logo{display:block;max-width:120px;max-height:62px;object-fit:contain}
    .company-mark{width:58px;height:58px;display:grid;place-items:center;border-radius:14px;background:var(--accent);color:#fff;font-size:20px;font-weight:800;letter-spacing:.5px}
    .company-mark.fallback{display:none}
    .company-copy strong{display:block;font-size:17px;line-height:1.3;color:#111827}
    .company-copy span{display:block;margin-top:4px;color:var(--muted);font-size:10px;letter-spacing:.4px}
    .document-kind{text-align:${ar ? 'left' : 'right'};min-width:190px}
    .document-kind span{display:block;color:var(--accent);font-size:10px;font-weight:800;letter-spacing:1px;text-transform:uppercase}
    .document-kind strong{display:block;margin-top:4px;font-size:20px;line-height:1.35}
    .document-kind small{display:block;margin-top:4px;color:var(--muted)}
    .title-row{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin:20px 0 12px}
    h1{margin:0;font-size:22px;line-height:1.35;color:#111827}
    .subtitle{margin:5px 0 0;color:var(--muted);font-size:11px;max-width:760px}
    .status{display:inline-flex;align-items:center;border-radius:999px;padding:5px 12px;background:color-mix(in srgb,var(--accent) 12%,#fff);color:var(--accent);border:1px solid color-mix(in srgb,var(--accent) 28%,#fff);font-weight:800;white-space:nowrap}
    .meta{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:8px;margin:14px 0 18px}
    .meta-item{padding:8px 10px;border:1px solid var(--line);border-radius:7px;background:var(--soft);min-width:0}
    .meta-item span{display:block;color:var(--muted);font-size:9px;margin-bottom:2px}
    .meta-item strong{display:block;font-size:10.5px;overflow-wrap:anywhere}
    table{width:100%;border-collapse:separate;border-spacing:0;border:1px solid var(--line);border-radius:8px;overflow:hidden;table-layout:auto}
    thead{display:table-header-group}
    th{background:var(--accent);color:#fff;font-weight:700;text-align:start;padding:8px 9px;border-inline-end:1px solid rgba(255,255,255,.22);white-space:nowrap}
    td{padding:7px 9px;border-bottom:1px solid var(--line);border-inline-end:1px solid #edf0f5;vertical-align:top;overflow-wrap:anywhere}
    tbody tr:nth-child(even) td{background:#fafbfc}
    tbody tr:last-child td{border-bottom:0}
    th:last-child,td:last-child{border-inline-end:0}
    .numeric{text-align:end;font-variant-numeric:tabular-nums;direction:ltr;white-space:nowrap}
    tfoot td{font-weight:800;background:#eef2f8;border-top:2px solid var(--accent);border-bottom:0}
    tr{break-inside:avoid;page-break-inside:avoid}
    .empty{padding:30px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:8px}
    .document-footer{display:flex;justify-content:space-between;gap:16px;margin-top:14px;padding-top:10px;border-top:1px solid var(--line);color:var(--muted);font-size:9px}
    .document-footer strong{color:var(--ink)}
    @media(max-width:700px){.document{padding:18px}.document-header,.title-row{align-items:flex-start;flex-direction:column}.document-kind{text-align:start}.meta{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media print{html{background:#fff}body{max-width:none}.document{padding:0}.top-rule{margin-bottom:14px}.document-header{padding-bottom:12px}.meta{margin:10px 0 14px}.document-footer{break-inside:avoid}}
  </style>
</head>
<body>
  <main class="document">
    <div class="top-rule"></div>
    <header class="document-header">
      <div class="company-identity">${logoHtml}<div class="company-copy"><strong>${escapeHtml(companyName)}</strong><span>${escapeHtml(companyCode)} · ${escapeHtml(currency)} · CORVAX BUSINESS PLATFORM</span></div></div>
      <div class="document-kind"><span>${escapeHtml(options.documentLabel || (ar ? 'مستند نظامي' : 'System document'))}</span><strong>${escapeHtml(options.title)}</strong><small>${escapeHtml(ar ? 'نسخة مستخرجة من النظام' : 'System-generated copy')}</small></div>
    </header>
    <section class="title-row"><div><h1>${escapeHtml(options.title)}</h1>${options.subtitle ? `<p class="subtitle">${escapeHtml(options.subtitle)}</p>` : ''}</div>${status ? `<span class="status">${escapeHtml(status)}</span>` : ''}</section>
    <section class="meta">${metaHtml}</section>
    ${options.rows.length ? `<table><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody>${totalsRow}</table>` : `<div class="empty">${escapeHtml(ar ? 'لا توجد بيانات للطباعة' : 'No data to print')}</div>`}
    <footer class="document-footer"><span>${escapeHtml(ar ? 'هذا المستند مولّد آليًا من CORVAX.' : 'This document was generated automatically by CORVAX.')}</span><strong>${escapeHtml(companyName)}</strong></footer>
  </main>
</body>
</html>`;

  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();

  const logoImage = printWindow.document.querySelector<HTMLImageElement>('.company-logo');
  if (logoImage) {
    logoImage.addEventListener('error', () => {
      logoImage.style.display = 'none';
      const fallback = printWindow.document.querySelector<HTMLElement>('.company-mark.fallback');
      if (fallback) fallback.style.display = 'grid';
    }, {once: true});
  }
  let printQueued = false;
  const triggerPrint = () => {
    if (printQueued) return;
    printQueued = true;
    window.setTimeout(() => {
    printWindow.focus();
    printWindow.print();
    }, 120);
  };
  if (logoImage?.complete && logoImage.naturalWidth === 0) {
    logoImage.style.display = 'none';
    const fallback = printWindow.document.querySelector<HTMLElement>('.company-mark.fallback');
    if (fallback) fallback.style.display = 'grid';
  }
  if (!logoImage || logoImage.complete) triggerPrint();
  else {
    logoImage.addEventListener('load', triggerPrint, {once: true});
    logoImage.addEventListener('error', triggerPrint, {once: true});
    window.setTimeout(triggerPrint, 1500);
  }
  return true;
}
