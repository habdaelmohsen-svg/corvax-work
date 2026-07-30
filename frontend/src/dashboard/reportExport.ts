import {strToU8, zipSync} from 'fflate';

export type ReportColumn = {
  key: string;
  name_ar: string;
  name_en: string;
  type: 'text' | 'money' | 'number' | 'integer' | 'percent' | 'date' | 'datetime' | 'boolean';
};

export type ReportResult = {
  report: {code: string; name_ar: string; name_en: string};
  metadata: {
    company_code: string;
    company_name_ar: string;
    company_name_en: string;
    company_logo_url?: string | null;
    currency: string;
    report_code: string;
    report_name_ar: string;
    report_name_en: string;
    period_start: string;
    period_end: string;
    filters: Record<string, unknown>;
    generated_at: string;
    generated_by_ar: string;
    generated_by_en: string;
    result_sha256: string;
  };
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  totals: Record<string, unknown>;
  warnings: string[];
};

const xml = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
}[character]!));

const columnName = (index: number) => {
  let number = index + 1;
  let result = '';
  while (number) {
    number -= 1;
    result = String.fromCharCode(65 + number % 26) + result;
    number = Math.floor(number / 26);
  }
  return result;
};

const safeName = (value: string) => value
  .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '-')
  .replace(/\s+/g, '_')
  .replace(/_+/g, '_')
  .slice(0, 110);

const timestamp = (raw: string) => raw.replace(/\D/g, '').slice(0, 14);

export const reportFileName = (result: ReportResult, extension: 'xlsx' | 'pdf', ar: boolean) => {
  const metadata = result.metadata;
  const company = ar ? metadata.company_name_ar : metadata.company_name_en;
  const report = ar ? metadata.report_name_ar : metadata.report_name_en;
  return `${safeName(company)}_${metadata.report_code}_${safeName(report)}_${metadata.period_start}_${metadata.period_end}_${timestamp(metadata.generated_at)}.${extension}`;
};

const cell = (reference: string, value: unknown, style: number, numeric = false) => {
  if (numeric && value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))) {
    return `<c r="${reference}" s="${style}"><v>${Number(value)}</v></c>`;
  }
  return `<c r="${reference}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
};

async function logoParts(url?: string | null) {
  if (!url) return null;
  try {
    const response = await fetch(url, {credentials: 'include'});
    if (!response.ok) return null;
    const mime = (response.headers.get('content-type') || '').toLowerCase();
    const extension = mime.includes('png') ? 'png' : mime.includes('jpeg') || mime.includes('jpg') ? 'jpeg' : null;
    if (!extension) return null;
    return {bytes: new Uint8Array(await response.arrayBuffer()), extension};
  } catch {
    return null;
  }
}

export async function exportSystemReportExcel(result: ReportResult, ar: boolean) {
  const metadata = result.metadata;
  const columns = result.columns;
  const lastColumn = columnName(Math.max(columns.length - 1, 0));
  const filterLabels = Object.entries(metadata.filters || {})
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(' | ');
  const title = ar ? metadata.report_name_ar : metadata.report_name_en;
  const company = ar ? metadata.company_name_ar : metadata.company_name_en;
  const generatedBy = ar ? metadata.generated_by_ar : metadata.generated_by_en;
  const rows: string[] = [];
  rows.push(`<row r="1" ht="30" customHeight="1">${cell('A1', company, 1)}</row>`);
  rows.push(`<row r="2" ht="28" customHeight="1">${cell('A2', `${metadata.report_code} — ${title}`, 2)}</row>`);
  rows.push(`<row r="3">${cell('A3', `${ar ? 'الفترة' : 'Period'}: ${metadata.period_start} → ${metadata.period_end}`, 3)}</row>`);
  rows.push(`<row r="4">${cell('A4', `${ar ? 'الفلاتر' : 'Filters'}: ${filterLabels || (ar ? 'لا يوجد' : 'None')}`, 3)}</row>`);
  rows.push(`<row r="5">${cell('A5', `${ar ? 'وقت الاستخراج' : 'Generated'}: ${metadata.generated_at} | ${ar ? 'المستخدم' : 'User'}: ${generatedBy}`, 3)}</row>`);
  rows.push(`<row r="6">${cell('A6', `${ar ? 'بصمة النتيجة' : 'Result fingerprint'}: ${metadata.result_sha256}`, 7)}</row>`);
  rows.push(`<row r="7" ht="26" customHeight="1">${columns.map((column, index) =>
    cell(`${columnName(index)}7`, ar ? column.name_ar : column.name_en, 4)
  ).join('')}</row>`);
  result.rows.forEach((source, rowIndex) => {
    const excelRow = rowIndex + 8;
    rows.push(`<row r="${excelRow}">${columns.map((column, columnIndex) => {
      const raw = source[column.key];
      const numeric = ['money', 'number', 'integer', 'percent'].includes(column.type);
      const style = column.type === 'money' ? 5 : column.type === 'percent' ? 6 : numeric ? 8 : 0;
      return cell(`${columnName(columnIndex)}${excelRow}`, raw, style, numeric);
    }).join('')}</row>`);
  });
  const totalsRow = result.rows.length + 8;
  if (Object.keys(result.totals || {}).length) {
    rows.push(`<row r="${totalsRow}" ht="24" customHeight="1">${columns.map((column, index) => {
      if (index === 0) return cell(`${columnName(index)}${totalsRow}`, ar ? 'الإجمالي' : 'Total', 9);
      const total = result.totals[column.key];
      const numeric = total !== undefined && Number.isFinite(Number(total));
      return cell(`${columnName(index)}${totalsRow}`, total ?? '', numeric ? 10 : 9, numeric);
    }).join('')}</row>`);
  }
  const lastDataRow = Math.max(result.rows.length + 7, 7);
  const columnWidths = columns.map((column, index) => {
    const label = ar ? column.name_ar : column.name_en;
    const contentWidth = result.rows.slice(0, 250).reduce((maximum, row) =>
      Math.max(maximum, String(row[column.key] ?? '').length), label.length);
    return `<col min="${index + 1}" max="${index + 1}" width="${Math.min(42, Math.max(12, contentWidth + 2))}" customWidth="1"/>`;
  }).join('');
  const logo = await logoParts(metadata.company_logo_url);
  const drawing = logo ? '<drawing r:id="rId1"/>' : '';
  const sheet = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0" rightToLeft="${ar ? 1 : 0}"><pane ySplit="7" topLeftCell="A8" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="18"/><cols>${columnWidths}</cols><sheetData>${rows.join('')}</sheetData>
<mergeCells count="6"><mergeCell ref="A1:${lastColumn}1"/><mergeCell ref="A2:${lastColumn}2"/><mergeCell ref="A3:${lastColumn}3"/><mergeCell ref="A4:${lastColumn}4"/><mergeCell ref="A5:${lastColumn}5"/><mergeCell ref="A6:${lastColumn}6"/></mergeCells>
<autoFilter ref="A7:${lastColumn}${lastDataRow}"/>
<conditionalFormatting sqref="A8:${lastColumn}${Math.max(lastDataRow, 8)}"><cfRule type="cellIs" dxfId="0" priority="1" operator="lessThan"><formula>0</formula></cfRule></conditionalFormatting>
<printOptions horizontalCentered="1"/><pageMargins left="0.25" right="0.25" top="0.55" bottom="0.55" header="0.25" footer="0.25"/>
<pageSetup orientation="${columns.length > 7 ? 'landscape' : 'portrait'}" paperSize="9" fitToWidth="1" fitToHeight="0"/>
<headerFooter><oddHeader>&amp;C${xml(company)} — ${xml(metadata.report_code)}</oddHeader><oddFooter>&amp;L${xml(generatedBy)}&amp;C${xml(metadata.generated_at)}&amp;R${ar ? 'صفحة' : 'Page'} &amp;P ${ar ? 'من' : 'of'} &amp;N</oddFooter></headerFooter>
${drawing}</worksheet>`;
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>
${logo ? `<Default Extension="${logo.extension}" ContentType="image/${logo.extension}"/>` : ''}
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
${logo ? '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' : ''}</Types>`;
  const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00;[Red](#,##0.00);-"/><numFmt numFmtId="165" formatCode="0.00&quot;%&quot;;[Red](0.00&quot;%&quot;);-"/></numFmts>
<fonts count="5"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="16"/><color rgb="FF17365D"/><name val="Arial"/></font><font><b/><sz val="14"/><color rgb="FF1E40AF"/><name val="Arial"/></font><font><b/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><color rgb="FF64748B"/><sz val="8"/><name val="Arial"/></font></fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1E40AF"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE2E8F0"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border/><border><left style="thin"><color rgb="FFD7DEE8"/></left><right style="thin"><color rgb="FFD7DEE8"/></right><top style="thin"><color rgb="FFD7DEE8"/></top><bottom style="thin"><color rgb="FFD7DEE8"/></bottom></border></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="11">
<xf fontId="0" fillId="0" borderId="1" applyBorder="1"><alignment vertical="center"/></xf>
<xf fontId="1" applyFont="1"><alignment horizontal="${ar ? 'right' : 'left'}" vertical="center"/></xf>
<xf fontId="2" applyFont="1"><alignment horizontal="${ar ? 'right' : 'left'}" vertical="center"/></xf>
<xf fontId="0"><alignment horizontal="${ar ? 'right' : 'left'}"/></xf>
<xf fontId="3" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf fontId="0" borderId="1" numFmtId="164" applyNumberFormat="1" applyBorder="1"><alignment horizontal="right"/></xf>
<xf fontId="0" borderId="1" numFmtId="165" applyNumberFormat="1" applyBorder="1"><alignment horizontal="right"/></xf>
<xf fontId="4" applyFont="1"/><xf fontId="0" borderId="1" numFmtId="4" applyNumberFormat="1" applyBorder="1"/>
<xf fontId="3" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1"/>
<xf fontId="3" fillId="2" borderId="1" numFmtId="164" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>
</cellXfs><dxfs count="1"><dxf><font><color rgb="FFB91C1C"/></font><fill><patternFill patternType="solid"><fgColor rgb="FFFFE4E6"/><bgColor indexed="64"/></patternFill></fill></dxf></dxfs></styleSheet>`;
  const files: Record<string, Uint8Array> = {
    '[Content_Types].xml': strToU8(contentTypes),
    '_rels/.rels': strToU8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
    'xl/workbook.xml': strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets><sheet name="${xml(metadata.report_code)}" sheetId="1" r:id="rId1"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>`),
    'xl/_rels/workbook.xml.rels': strToU8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'),
    'xl/styles.xml': strToU8(styles),
    'xl/worksheets/sheet1.xml': strToU8(sheet),
  };
  if (logo) {
    files[`xl/media/logo.${logo.extension}`] = logo.bytes;
    files['xl/worksheets/_rels/sheet1.xml.rels'] = strToU8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>');
    files['xl/drawings/drawing1.xml'] = strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><xdr:oneCellAnchor><xdr:from><xdr:col>${Math.max(columns.length - 2, 0)}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>0</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:ext cx="1143000" cy="381000"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="Company Logo"/><xdr:cNvPicPr/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>`);
    files['xl/drawings/_rels/drawing1.xml.rels'] = strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/logo.${logo.extension}"/></Relationships>`);
  }
  const zipped = zipSync(files, {level: 6});
  const blob = new Blob([new Uint8Array(zipped).buffer], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = reportFileName(result, 'xlsx', ar);
  anchor.click();
  URL.revokeObjectURL(href);
}

const html = (value: unknown) => xml(value);

export function printSystemReportPdf(result: ReportResult, ar: boolean) {
  const metadata = result.metadata;
  const title = ar ? metadata.report_name_ar : metadata.report_name_en;
  const company = ar ? metadata.company_name_ar : metadata.company_name_en;
  const generatedBy = ar ? metadata.generated_by_ar : metadata.generated_by_en;
  const headers = result.columns.map(column => `<th>${html(ar ? column.name_ar : column.name_en)}</th>`).join('');
  const body = result.rows.map(row => `<tr>${result.columns.map(column => {
    const value = row[column.key];
    const numeric = ['money', 'number', 'integer', 'percent'].includes(column.type);
    const shown = numeric && value !== null && value !== undefined
      ? new Intl.NumberFormat(ar ? 'ar-SA' : 'en-US', {minimumFractionDigits: column.type === 'integer' ? 0 : 2, maximumFractionDigits: column.type === 'integer' ? 0 : 2}).format(Number(value))
      : String(value ?? '');
    return `<td class="${numeric ? 'num' : ''} ${Number(value) < 0 ? 'neg' : ''}">${html(shown)}</td>`;
  }).join('')}</tr>`).join('');
  const filters = Object.entries(metadata.filters || {}).filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${html(key)}: ${html(value)}`).join(' | ');
  const popup = window.open('', '_blank');
  if (!popup) return;
  popup.document.write(`<!doctype html><html dir="${ar ? 'rtl' : 'ltr'}"><head><meta charset="utf-8"><title>${html(title)}</title>
<style>
@page{size:${result.columns.length > 7 ? 'A4 landscape' : 'A4 portrait'};margin:18mm 8mm 15mm}
*{box-sizing:border-box}body{font-family:Arial,"Noto Sans Arabic",sans-serif;color:#172033;margin:0;font-size:10px}
.head{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #1e40af;padding-bottom:8px;margin-bottom:10px}
.logo{width:110px;max-height:46px;object-fit:contain}.brand{font-size:18px;font-weight:800;color:#17365d}.title{font-size:16px;font-weight:800;color:#1e40af;margin:5px 0}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px;background:#f1f5f9;padding:8px;margin-bottom:10px;border-radius:6px}
table{width:100%;border-collapse:collapse;table-layout:auto}thead{display:table-header-group}tr{break-inside:avoid}
th{background:#1e40af;color:white;padding:6px;border:1px solid #18358f;text-align:${ar ? 'right' : 'left'};font-weight:700}
td{padding:5px;border:1px solid #d7dee8;vertical-align:top;word-break:break-word}.num{text-align:end;white-space:nowrap}.neg{color:#b91c1c;background:#fff1f2}
.warnings{margin:8px 0;padding:7px;background:#fff7ed;border:1px solid #fdba74}.fingerprint{font-size:7px;color:#64748b;margin-top:8px;word-break:break-all}
.footer{position:fixed;bottom:-10mm;left:0;right:0;color:#64748b;font-size:8px;display:flex;justify-content:space-between}
.page:after{content:counter(page)} @media print{button{display:none}}
</style></head><body>
<div class="head"><div>${metadata.company_logo_url ? `<img class="logo" src="${html(metadata.company_logo_url)}">` : '<div class="brand">CORVAX</div>'}</div><div><div class="brand">${html(company)}</div><div class="title">${html(metadata.report_code)} — ${html(title)}</div></div></div>
<div class="meta"><div><b>${ar ? 'الفترة' : 'Period'}:</b> ${html(metadata.period_start)} → ${html(metadata.period_end)}</div><div><b>${ar ? 'العملة' : 'Currency'}:</b> ${html(metadata.currency)}</div>
<div><b>${ar ? 'وقت الاستخراج' : 'Generated'}:</b> ${html(metadata.generated_at)}</div><div><b>${ar ? 'المستخدم' : 'User'}:</b> ${html(generatedBy)}</div>
<div style="grid-column:1/-1"><b>${ar ? 'الفلاتر' : 'Filters'}:</b> ${filters || (ar ? 'لا يوجد' : 'None')}</div></div>
${result.warnings.length ? `<div class="warnings">${result.warnings.map(warning => `<div>• ${html(warning)}</div>`).join('')}</div>` : ''}
<table><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>
<div class="fingerprint">${ar ? 'بصمة النتيجة' : 'Result fingerprint'}: ${html(metadata.result_sha256)}</div>
<div class="footer"><span>${html(generatedBy)} — ${html(metadata.generated_at)}</span><span>${ar ? 'صفحة' : 'Page'} <span class="page"></span></span></div>
<script>window.onload=()=>{setTimeout(()=>window.print(),250)}</script></body></html>`);
  popup.document.close();
}
