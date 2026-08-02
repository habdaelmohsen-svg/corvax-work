import {Window} from 'happy-dom';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {writeFileSync} from 'node:fs';

const baseUrl = process.env.CORVAX_UAT_BASE_URL || 'http://127.0.0.1:8000';
const windowInstance = new Window({url: `${baseUrl}/#/executive`});
(windowInstance as any).print = () => undefined;
Object.assign(globalThis, {
  window: windowInstance,
  document: windowInstance.document,
  localStorage: windowInstance.localStorage,
  sessionStorage: windowInstance.sessionStorage,
  HTMLElement: windowInstance.HTMLElement,
  HTMLInputElement: windowInstance.HTMLInputElement,
  HTMLSelectElement: windowInstance.HTMLSelectElement,
  Event: windowInstance.Event,
  CustomEvent: windowInstance.CustomEvent,
});
Object.defineProperty(globalThis, 'navigator', {value: windowInstance.navigator, configurable: true});
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const nativeFetch = globalThis.fetch;
const httpAudit: Array<{method:string;path:string;status:number}> = [];
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  const url = raw.startsWith('/') ? `${baseUrl}${raw}` : raw;
  const response = await nativeFetch(url, init);
  httpAudit.push({method:String(init?.method||'GET').toUpperCase(),path:new URL(url).pathname,status:response.status});
  return response;
}) as typeof fetch;

const loginResponse = await fetch('/api/v1/auth/login', {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({email: 'admin@corvaxplatform.com', password: 'Corvax@123'}),
});
if (!loginResponse.ok) throw new Error(`Login failed: ${loginResponse.status} ${await loginResponse.text()}`);
const login = await loginResponse.json();
sessionStorage.setItem('corvax_token', login.access_token);
localStorage.setItem('corvax_user', JSON.stringify(login.user));
localStorage.setItem('corvax_company', JSON.stringify({id: 'holding', apiId: 1, name_ar: 'شركة محاكاة الموظف'}));

const {DashboardRoutes} = await import('../src/dashboard/routes');
const {navItems} = await import('../src/dashboard/navigation');
const results: any[] = [];
const failures: any[] = [];
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

for (const item of navItems) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  window.location.hash = `#/${item.key}`;
  try {
    await act(async () => {
      root.render(<DashboardRoutes ar={true} companyId={1} scope={'holding'} view={item.key as any} onNavigate={() => {}}/>);
      await delay(650);
    });
    for (let attempt=0; attempt<20 && container.querySelector('.route-loading'); attempt+=1) {
      await act(async () => { await delay(100); });
    }
    const inputs = [...container.querySelectorAll('input, textarea, select')] as Array<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>;
    let filled = 0;
    for (const field of inputs) {
      if (field.disabled || field.readOnly || field instanceof HTMLInputElement && ['hidden','file','submit','button'].includes(field.type)) continue;
      await act(async () => {
        if (field instanceof HTMLSelectElement) {
          const option = [...field.options].find((entry) => !entry.disabled && entry.value);
          if (option) field.value = option.value;
        } else if (field instanceof HTMLInputElement && field.type === 'checkbox') {
          field.checked = true;
        } else if (field instanceof HTMLInputElement && field.type === 'date') {
          field.value = '2026-08-02';
        } else if (field instanceof HTMLInputElement && field.type === 'time') {
          field.value = '09:00';
        } else if (field instanceof HTMLInputElement && ['number','range'].includes(field.type)) {
          field.value = field.min && Number(field.min) > 0 ? field.min : '100';
        } else {
          field.value = field.getAttribute('placeholder')?.includes('@') ? 'uat.employee@corvax.test' : 'بيانات محاكاة موظف CORVAX';
        }
        field.dispatchEvent(new window.Event('input', {bubbles: true}));
        field.dispatchEvent(new window.Event('change', {bubbles: true}));
        await delay(10);
      });
      filled += 1;
    }
    await act(async () => { await delay(120); });
    const buttonLabels: string[] = [];
    let clicked = 0;
    const buttons = [...container.querySelectorAll('button')] as HTMLButtonElement[];
    for (const button of buttons) {
      if (button.disabled || !button.isConnected) continue;
      const label = (button.textContent || button.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
      buttonLabels.push(label.slice(0, 80));
      try {
        await act(async () => {
          button.dispatchEvent(new window.MouseEvent('click', {bubbles: true, cancelable: true}));
          await delay(140);
        });
        clicked += 1;
      } catch { /* recorded through the visible-state and failure checks below */ }
    }
    await act(async () => { await delay(350); });
    const text = container.textContent || '';
    const visibleFailure = /(تعذر تحميل|خطأ غير متوقع|Failed to load|Internal Server Error)/i.test(text);
    const row = {
      key: item.key, section: item.ar,
      inputs: inputs.length, filled,
      buttons: buttons.length, clicked, buttonLabels,
      tables: container.querySelectorAll('table').length,
      forms: container.querySelectorAll('form').length,
      visibleFailure,
      renderedChars: text.trim().length,
    };
    results.push(row);
    if (visibleFailure || row.renderedChars < 20) failures.push(row);
  } catch (error: any) {
    const row = {key: item.key, section: item.ar, error: String(error?.stack || error)};
    results.push(row); failures.push(row);
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }
}

const methodCounts = httpAudit.reduce((out:Record<string,number>,row)=>{out[row.method]=(out[row.method]||0)+1;return out;},{});
const statusCounts = httpAudit.reduce((out:Record<string,number>,row)=>{const key=String(Math.floor(row.status/100))+'xx';out[key]=(out[key]||0)+1;return out;},{});
const summary = {
  run_at: new Date().toISOString(),
  sections_declared: navItems.length,
  sections_rendered: results.filter((row) => !row.error).length,
  fields_discovered: results.reduce((sum, row) => sum + (row.inputs || 0), 0),
  fields_filled: results.reduce((sum, row) => sum + (row.filled || 0), 0),
  buttons_discovered: results.reduce((sum, row) => sum + (row.buttons || 0), 0),
  buttons_clicked: results.reduce((sum, row) => sum + (row.clicked || 0), 0),
  tables_discovered: results.reduce((sum, row) => sum + (row.tables || 0), 0),
  http_requests: httpAudit.length,
  http_methods: methodCounts,
  http_status_groups: statusCounts,
  server_errors: httpAudit.filter((row)=>row.status>=500),
  rejected_requests: httpAudit.filter((row)=>row.status>=400 && row.status<500),
  failures: failures.length,
  results,
};
const evidence = JSON.stringify(summary, null, 2);
const evidencePath = process.env.CORVAX_UAT_EVIDENCE_PATH;
if (evidencePath) writeFileSync(evidencePath, evidence, 'utf8');
console.log(evidence);
if (failures.length) process.exitCode = 2;
