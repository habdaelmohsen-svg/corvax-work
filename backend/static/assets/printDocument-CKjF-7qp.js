import{S as e}from"./ui-fGK8FcTS.js";var t=e(`printer`,[[`path`,{d:`M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2`,key:`143wyd`}],[`path`,{d:`M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6`,key:`1itne7`}],[`rect`,{x:`6`,y:`14`,width:`12`,height:`8`,rx:`1`,key:`1ue0tg`}]]),n=e=>String(e??``).replace(/&/g,`&amp;`).replace(/</g,`&lt;`).replace(/>/g,`&gt;`).replace(/"/g,`&quot;`).replace(/'/g,`&#039;`),r=()=>{try{let e=JSON.parse(localStorage.getItem(`corvax_company`)||`{}`);return e&&typeof e==`object`?e:{}}catch{return{}}},i=e=>e&&/^#[0-9a-f]{6}$/i.test(e)?e:`#2347a5`,a=e=>{if(!e)return null;if(/^data:image\/(?:png|jpeg|jpg|webp|gif);base64,[a-z0-9+/=\s]+$/i.test(e))return e;try{let t=new URL(e,window.location.origin);return[`http:`,`https:`].includes(t.protocol)?t.href:null}catch{return null}},o=(e,t)=>{let n={DRAFT:[`مسودة`,`Draft`],SUBMITTED:[`مقدّم`,`Submitted`],PENDING_APPROVAL:[`بانتظار الاعتماد`,`Pending approval`],APPROVED:[`معتمد`,`Approved`],POSTED:[`مرحّل`,`Posted`],REVERSED:[`معكوس`,`Reversed`]}[String(e||``).toUpperCase()];return n?n[+!t]:e};function s(e){let t=window.open(``,`_blank`);if(!t)return!1;t.opener=null;let s=r(),c=e.ar,l=c?`rtl`:`ltr`,u=c?`ar`:`en`,d=c?s.name_ar||s.name_en||`CORVAX`:s.name_en||s.name_ar||`CORVAX`,f=s.code||`CORVAX`,p=f.replace(/[^A-Za-z0-9\u0600-\u06ff]/g,``).slice(0,3).toUpperCase()||`C`,m=s.currency||`SAR`,h=i(s.primary_color),g=a(s.logo_url),_=new Set(e.numericColumns||[]),v=new Intl.DateTimeFormat(c?`ar-SA`:`en-GB`,{dateStyle:`medium`,timeStyle:`short`}).format(new Date),y=[...e.meta||[],{label:c?`العملة`:`Currency`,value:m},{label:c?`تاريخ الاستخراج`:`Generated at`,value:v}],b=e.status?o(e.status,c):``,x=e.landscape||e.columns.length>5?`landscape`:`portrait`,S=g?`<img class="company-logo" src="${n(g)}" alt="${n(d)}"><div class="company-mark fallback">${n(p)}</div>`:`<div class="company-mark">${n(p)}</div>`,C=e.columns.map((e,t)=>`<th class="${_.has(t)?`numeric`:``}">${n(e)}</th>`).join(``),w=e.rows.map(t=>`<tr>${e.columns.map((e,r)=>`<td class="${_.has(r)?`numeric`:``}">${n(t[r])}</td>`).join(``)}</tr>`).join(``),T=e.totals?`<tfoot><tr>${e.columns.map((t,r)=>`<td class="${_.has(r)?`numeric`:``}">${n(e.totals?.[r])}</td>`).join(``)}</tr></tfoot>`:``,E=y.filter(e=>e.value!==null&&e.value!==void 0&&e.value!==``).map(e=>`<div class="meta-item"><span>${n(e.label)}</span><strong>${n(e.value)}</strong></div>`).join(``),D=`<!doctype html>
<html lang="${u}" dir="${l}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${n(e.title)}</title>
  <style>
    :root{--accent:${h};--ink:#172033;--muted:#657089;--line:#d9deea;--soft:#f4f6fa}
    @page{size:A4 ${x};margin:12mm 10mm 15mm}
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
    .document-kind{text-align:${c?`left`:`right`};min-width:190px}
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
      <div class="company-identity">${S}<div class="company-copy"><strong>${n(d)}</strong><span>${n(f)} · ${n(m)} · CORVAX BUSINESS PLATFORM</span></div></div>
      <div class="document-kind"><span>${n(e.documentLabel||(c?`مستند نظامي`:`System document`))}</span><strong>${n(e.title)}</strong><small>${n(c?`نسخة مستخرجة من النظام`:`System-generated copy`)}</small></div>
    </header>
    <section class="title-row"><div><h1>${n(e.title)}</h1>${e.subtitle?`<p class="subtitle">${n(e.subtitle)}</p>`:``}</div>${b?`<span class="status">${n(b)}</span>`:``}</section>
    <section class="meta">${E}</section>
    ${e.rows.length?`<table><thead><tr>${C}</tr></thead><tbody>${w}</tbody>${T}</table>`:`<div class="empty">${n(c?`لا توجد بيانات للطباعة`:`No data to print`)}</div>`}
    <footer class="document-footer"><span>${n(c?`هذا المستند مولّد آليًا من CORVAX.`:`This document was generated automatically by CORVAX.`)}</span><strong>${n(d)}</strong></footer>
  </main>
</body>
</html>`;t.document.open(),t.document.write(D),t.document.close();let O=t.document.querySelector(`.company-logo`);O&&O.addEventListener(`error`,()=>{O.style.display=`none`;let e=t.document.querySelector(`.company-mark.fallback`);e&&(e.style.display=`grid`)},{once:!0});let k=!1,A=()=>{k||(k=!0,window.setTimeout(()=>{t.focus(),t.print()},120))};if(O?.complete&&O.naturalWidth===0){O.style.display=`none`;let e=t.document.querySelector(`.company-mark.fallback`);e&&(e.style.display=`grid`)}return!O||O.complete?A():(O.addEventListener(`load`,A,{once:!0}),O.addEventListener(`error`,A,{once:!0}),window.setTimeout(A,1500)),!0}export{t as n,s as t};