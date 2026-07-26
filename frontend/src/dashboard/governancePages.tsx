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
const DEMO_ACTIONS_ENABLED = import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_ACTIONS === 'true';

export function CrmPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [summary,setSummary]=useState<any>({});const [campaigns,setCampaigns]=useState<any[]>([]);const [leads,setLeads]=useState<any[]>([]);const [opportunities,setOpportunities]=useState<any[]>([]);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  async function load(){const h=authHeaders();const [a,b,c,d]=await Promise.all([fetch(`/api/v1/crm/summary?company_id=${companyId}`,{headers:h}),fetch(`/api/v1/crm/campaigns?company_id=${companyId}`,{headers:h}),fetch(`/api/v1/crm/leads?company_id=${companyId}`,{headers:h}),fetch(`/api/v1/crm/opportunities?company_id=${companyId}`,{headers:h})]);if(a.ok)setSummary(await a.json());if(b.ok)setCampaigns(await b.json());if(c.ok)setLeads(await c.json());if(d.ok)setOpportunities(await d.json())}
  useEffect(()=>{load().catch(()=>{})},[companyId]);
  async function createPipeline(){setBusy(true);setMessage('');try{const suffix=String(Date.now()).slice(-6);let r=await fetch('/api/v1/crm/campaigns',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,code:`CMP-${suffix}`,name_ar:'حملة نمو المبيعات',name_en:'Sales growth campaign',channel:'DIGITAL',budget:25000,start_date:'2026-08-01',end_date:'2026-09-30'})});let campaign=await r.json();if(!r.ok)throw new Error(campaign.detail||'Campaign creation failed');r=await fetch('/api/v1/crm/leads',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,campaign_id:campaign.id,source:'DIGITAL',name:'CORVAX Prospective Customer',email:`lead-${suffix}@example.com`,estimated_value:120000,notes:'Qualified lead generated from digital campaign.'})});let lead=await r.json();if(!r.ok)throw new Error(lead.detail||'Lead creation failed');r=await fetch(`/api/v1/crm/leads/${lead.id}/convert?company_id=${companyId}`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({title:'Enterprise platform opportunity',amount:120000,probability:35,expected_close_date:'2026-10-31'})});let opportunity=await r.json();if(!r.ok)throw new Error(opportunity.detail||'Conversion failed');setMessage(ar?`تم إنشاء الحملة والعميل المحتمل وتحويله إلى فرصة ${opportunity.number}`:`Campaign and lead created, then converted to ${opportunity.number}`);await load()}catch(e:any){setMessage(String(e.message||e))}finally{setBusy(false)}}
  return <>
    <div className="kpis rich"><Kpi title={ar?'العملاء المحتملون':'Leads'} value={String(summary.leads??0)} trend={`${summary.new_leads??0} ${ar?'جدد':'new'}`} good/><Kpi title={ar?'الفرص المفتوحة':'Open opportunities'} value={String(summary.open_opportunities??0)} trend={ar?'مسار بيع فعلي':'Live sales pipeline'} good/><Kpi title={ar?'قيمة المسار':'Pipeline value'} value={money.format(Number(summary.pipeline_amount??0))} trend={`${ar?'مرجح':'Weighted'} ${money.format(Number(summary.weighted_pipeline??0))}`} good/><Kpi title={ar?'الحملات':'Campaigns'} value={String(summary.campaigns??0)} trend={`${ar?'ميزانية':'Budget'} ${money.format(Number(summary.campaign_budget??0))}`} good/></div>
    <div className="journal-footer"><span>{message||(ar?'الحملات والعملاء المحتملون والفرص محفوظة في قاعدة البيانات':'Campaigns, leads and opportunities are database-backed')}</span>{DEMO_ACTIONS_ENABLED&&<button disabled={busy} onClick={createPipeline}>{busy?(ar?'جارٍ الإنشاء...':'Creating...'):(ar?'إنشاء مسار تسويقي تجريبي':'Create marketing pipeline')}</button>}</div>
    <div className="two-columns"><Panel title={ar?'الحملات التسويقية':'Marketing campaigns'} icon={<BarChart3 size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'الحملة':'Campaign',ar?'القناة':'Channel',ar?'الميزانية':'Budget',ar?'الحالة':'Status']} rows={campaigns.map(c=>[c.code,ar?c.name_ar:c.name_en,c.channel,money.format(Number(c.budget)),c.status])}/></Panel><Panel title={ar?'العملاء المحتملون':'Leads'} icon={<Users size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'الاسم':'Name',ar?'المصدر':'Source',ar?'القيمة':'Value',ar?'الحالة':'Status']} rows={leads.map(l=>[l.number,l.name,l.source,money.format(Number(l.estimated_value)),l.status])}/></Panel></div>
    <Panel title={ar?'مسار الفرص':'Opportunity pipeline'} icon={<TrendingUp size={18}/> }><DataTable headers={[ar?'الرقم':'Number',ar?'الفرصة':'Opportunity',ar?'المرحلة':'Stage',ar?'الاحتمال':'Probability',ar?'القيمة':'Amount',ar?'القيمة المرجحة':'Weighted']} rows={opportunities.map(o=>[o.number,o.title,o.stage,`${o.probability}%`,money.format(Number(o.amount)),money.format(Number(o.weighted_amount))])}/></Panel>
  </>;
}

export function AuditPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [summary,setSummary]=useState<any>({});
  const [risks,setRisks]=useState<any[]>([]);
  const [audits,setAudits]=useState<any[]>([]);
  const [findings,setFindings]=useState<any[]>([]);
  const [events,setEvents]=useState<any[]>([]);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  async function load(){
    const h=authHeaders();
    const [a,b,c,d,e]=await Promise.all([
      fetch(`/api/v1/governance/summary?company_id=${companyId}`,{headers:h}),
      fetch(`/api/v1/governance/risks?company_id=${companyId}`,{headers:h}),
      fetch(`/api/v1/governance/audits?company_id=${companyId}`,{headers:h}),
      fetch(`/api/v1/governance/findings?company_id=${companyId}`,{headers:h}),
      fetch(`/api/v1/audit-log?company_id=${companyId}&limit=20`,{headers:h}),
    ]);
    if(a.ok)setSummary(await a.json()); if(b.ok)setRisks(await b.json()); if(c.ok)setAudits(await c.json()); if(d.ok)setFindings(await d.json()); if(e.ok)setEvents(await e.json());
  }
  useEffect(()=>{load().catch(()=>{})},[companyId]);
  async function createAssurancePack(){setBusy(true);setMessage('');try{
    const suffix=String(Date.now()).slice(-6);
    let r=await fetch('/api/v1/governance/risks',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,code:`R-${suffix}`,title_ar:'مخاطر تجاوز صلاحيات الاعتماد',title_en:'Approval authority override risk',category:'FINANCIAL',likelihood:4,impact:5,residual_score:12,description:'Risk of transactions bypassing the approved authority matrix.'})});let risk=await r.json();if(!r.ok)throw new Error(risk.detail||'Risk creation failed');
    r=await fetch('/api/v1/governance/controls',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,risk_id:risk.id,code:`C-${suffix}`,name_ar:'فصل المنشئ عن المعتمد',name_en:'Maker-checker segregation',control_type:'PREVENTIVE',frequency:'CONTINUOUS',design_status:'EFFECTIVE',operating_status:'EFFECTIVE'})});let control=await r.json();if(!r.ok)throw new Error(control.detail||'Control creation failed');
    r=await fetch('/api/v1/governance/audits',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,code:`AUD-${suffix}`,title_ar:'مراجعة دورة المصروفات والاعتمادات',title_en:'Expenditure and approval cycle audit',audit_type:'INTERNAL',scope:'Purchasing, payments, budgets and authority controls',risk_rating:'HIGH',planned_start:'2026-08-01',planned_end:'2026-08-15'})});let audit=await r.json();if(!r.ok)throw new Error(audit.detail||'Audit creation failed');
    r=await fetch('/api/v1/governance/findings',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,engagement_id:audit.id,code:`F-${suffix}`,title_ar:'نقص توثيق الاستثناءات',title_en:'Exception documentation gap',severity:'MEDIUM',description:'Some exception approvals require stronger supporting evidence.',root_cause:'Manual exception handling',recommendation:'Require evidence and approval reason before posting.',due_date:'2026-09-01'})});let finding=await r.json();if(!r.ok)throw new Error(finding.detail||'Finding creation failed');
    r=await fetch(`/api/v1/governance/findings/${finding.id}/actions`,{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,description:'Implement mandatory evidence attachment and approval reason.',due_date:'2026-09-01'})});if(!r.ok){const x=await r.json();throw new Error(x.detail||'Action creation failed')}
    r=await fetch('/api/v1/governance/documents',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,code:`POL-${suffix}`,title_ar:'سياسة الصلاحيات والاعتمادات',title_en:'Authority and approval policy',document_type:'POLICY',version:'1.0',effective_date:'2026-08-01',review_date:'2027-08-01',content_summary:'Defines maker-checker, approval thresholds, exceptions and evidence requirements.'})});if(!r.ok){const x=await r.json();throw new Error(x.detail||'Document creation failed')}
    setMessage(ar?'تم إنشاء حزمة مخاطر وضوابط ومراجعة وإجراء تصحيحي ووثيقة مضبوطة.':'Risk, control, audit, corrective action and controlled document created.');await load();
  }catch(e:any){setMessage(String(e.message||e))}finally{setBusy(false)}}
  return <>
    <div className="kpis rich"><Kpi title={ar?'المخاطر المسجلة':'Registered risks'} value={String(summary.risks??0)} trend={`${summary.high_residual_risks??0} ${ar?'مرتفعة':'high'}`} good={(summary.high_residual_risks??0)===0}/><Kpi title={ar?'الضوابط':'Controls'} value={String(summary.controls??0)} trend={`${summary.ineffective_controls??0} ${ar?'غير فعالة':'ineffective'}`} good={(summary.ineffective_controls??0)===0}/><Kpi title={ar?'ملاحظات مفتوحة':'Open findings'} value={String(summary.open_findings??0)} trend={`${summary.overdue_findings??0} ${ar?'متأخرة':'overdue'}`} good={(summary.overdue_findings??0)===0}/><Kpi title={ar?'مراجعات':'Audit engagements'} value={String(summary.audit_engagements??0)} trend={ar?'محفوظة بقاعدة البيانات':'Database-backed'} good/></div>
    <div className="journal-footer"><span>{message||(ar?'شغّل حزمة تأكيد رقابي حقيقية لاختبار الموديول':'Create a real assurance pack to verify the module')}</span><button disabled={busy} onClick={createAssurancePack}>{busy?(ar?'جارٍ الإنشاء...':'Creating...'):(ar?'إنشاء حزمة تأكيد رقابي':'Create assurance pack')}</button></div>
    <div className="two-columns"><Panel title={ar?'سجل المخاطر':'Risk register'} icon={<AlertTriangle size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'المخاطر':'Risk',ar?'الفئة':'Category',ar?'الجوهري':'Inherent',ar?'المتبقي':'Residual',ar?'الحالة':'Status']} rows={risks.map(r=>[r.code,ar?r.title_ar:r.title_en,r.category,String(r.inherent_score),String(r.residual_score),r.status])}/></Panel><Panel title={ar?'مهام المراجعة':'Audit engagements'} icon={<ClipboardCheck size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'المهمة':'Engagement',ar?'النوع':'Type',ar?'المخاطر':'Risk',ar?'الحالة':'Status']} rows={audits.map(a=>[a.code,ar?a.title_ar:a.title_en,a.audit_type,a.risk_rating,a.status])}/></Panel></div>
    <Panel title={ar?'الملاحظات وخطط المعالجة':'Findings and remediation'} icon={<FileCheck2 size={18}/> }><DataTable headers={[ar?'الكود':'Code',ar?'الملاحظة':'Finding',ar?'الخطورة':'Severity',ar?'الاستحقاق':'Due',ar?'الحالة':'Status']} rows={findings.map(f=>[f.code,ar?f.title_ar:f.title_en,f.severity,String(f.due_date??'—'),f.status])}/></Panel>
    <Panel title={ar?'سجل التدقيق الفعلي':'Live audit trail'} icon={<ShieldCheck size={18}/> }><DataTable headers={[ar?'الوقت':'Time',ar?'الإجراء':'Action',ar?'الكيان':'Entity',ar?'المعرف':'ID',ar?'المستخدم':'User']} rows={events.map(e=>[String(e.created_at).replace('T',' ').slice(0,19),e.action,e.entity_type,e.entity_id,String(e.user_id??'—')])}/></Panel>
  </>;
}

export function ItPage({ ar, companyId }: { ar: boolean; companyId:number }) {
  const [summary,setSummary]=useState<any>({});const [assets,setAssets]=useState<any[]>([]);const [tickets,setTickets]=useState<any[]>([]);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
  async function load(){const h=authHeaders();const [a,b,c]=await Promise.all([fetch(`/api/v1/itsm/summary?company_id=${companyId}`,{headers:h}),fetch(`/api/v1/itsm/assets?company_id=${companyId}`,{headers:h}),fetch(`/api/v1/itsm/tickets?company_id=${companyId}`,{headers:h})]);if(a.ok)setSummary(await a.json());if(b.ok)setAssets(await b.json());if(c.ok)setTickets(await c.json())}
  useEffect(()=>{load().catch(()=>{})},[companyId]);
  async function createOperationalSample(){setBusy(true);setMessage('');try{const suffix=String(Date.now()).slice(-6);let r=await fetch('/api/v1/itsm/assets',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,asset_tag:`IT-${suffix}`,asset_type:'LAPTOP',name:'CORVAX Finance Workstation',serial_number:`SN-${suffix}`,criticality:'HIGH',purchase_date:'2026-07-01',warranty_end:'2029-06-30'})});let asset=await r.json();if(!r.ok)throw new Error(asset.detail||'Asset creation failed');r=await fetch('/api/v1/itsm/tickets',{method:'POST',headers:jsonHeaders(),body:JSON.stringify({company_id:companyId,category:'ACCESS',subject:'Quarterly finance access review',description:'Review privileged finance roles and remove obsolete access.',priority:'HIGH',due_hours:48})});let ticket=await r.json();if(!r.ok)throw new Error(ticket.detail||'Ticket creation failed');setMessage(ar?`تم إنشاء أصل ${asset.asset_tag} وتذكرة ${ticket.number}`:`Created asset ${asset.asset_tag} and ticket ${ticket.number}`);await load()}catch(e:any){setMessage(String(e.message||e))}finally{setBusy(false)}}
  return <>
    <div className="kpis rich"><Kpi title={ar?'الأصول التقنية':'IT assets'} value={String(summary.it_assets??0)} trend={`${summary.active_assets??0} ${ar?'بالخدمة':'in service'}`} good/><Kpi title={ar?'تذاكر مفتوحة':'Open tickets'} value={String(summary.open_tickets??0)} trend={`${summary.high_priority_open??0} ${ar?'عالية':'high priority'}`} good={(summary.high_priority_open??0)===0}/><Kpi title={ar?'تذاكر متأخرة':'Overdue tickets'} value={String(summary.overdue_tickets??0)} trend={ar?'مراقبة SLA':'SLA monitored'} good={(summary.overdue_tickets??0)===0}/><Kpi title={ar?'الالتزام بـ SLA':'SLA compliance'} value={`${Number(summary.sla_compliance??100).toFixed(1)}%`} trend={ar?'محسوب من التذاكر':'Calculated from tickets'} good={Number(summary.sla_compliance??100)>=90}/></div>
    <div className="journal-footer"><span>{message||(ar?'الأصول والتذاكر محفوظة بقاعدة البيانات وسجل التدقيق':'Assets and tickets are persisted with audit trail')}</span>{DEMO_ACTIONS_ENABLED&&<button disabled={busy} onClick={createOperationalSample}>{busy?(ar?'جارٍ الإنشاء...':'Creating...'):(ar?'إنشاء أصل وتذكرة اختبار':'Create asset & ticket')}</button>}</div>
    <div className="two-columns"><Panel title={ar?'الأصول التقنية':'IT asset register'} icon={<MonitorCog size={18}/> }><DataTable headers={[ar?'الرقم':'Tag',ar?'النوع':'Type',ar?'الاسم':'Name',ar?'الأهمية':'Criticality',ar?'الحالة':'Status']} rows={assets.map(a=>[a.asset_tag,a.asset_type,a.name,a.criticality,a.status])}/></Panel><Panel title={ar?'إدارة الخدمات التقنية':'IT service management'} icon={<Activity size={18}/> }><DataTable headers={[ar?'التذكرة':'Ticket',ar?'الفئة':'Category',ar?'الموضوع':'Subject',ar?'الأولوية':'Priority',ar?'الحالة':'Status']} rows={tickets.map(t=>[t.number,t.category,t.subject,t.priority,t.status])}/></Panel></div>
    <Panel title={ar?'ضوابط التشغيل التقني':'Digital operations controls'} icon={<ShieldCheck size={18}/> }><Checklist items={[[ar?'سجل أصول تقني فعلي':'Database-backed IT asset register',true],[ar?'تذاكر ودورة SLA':'Ticket and SLA workflow',true],[ar?'سجل مراجعة لكل تغيير':'Audit trail for every change',true],[ar?'استعادة مجربة على خادم منفصل':'Independent restore drill',false],[ar?'اختبار اختراق مستقل':'Independent penetration test',false],[ar?'تكامل هوية مؤسسية SSO':'Enterprise SSO integration',false]]}/></Panel>
  </>;
}

export function AccessGovernancePage({ ar, companyId }: { ar: boolean; companyId: number }) {
  const [dashboard,setDashboard]=useState<any>(null);
  const [conflicts,setConflicts]=useState<any[]>([]);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const load=()=>Promise.all([
    fetch(`/api/v1/access-governance/dashboard?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.ok?r.json():null),
    fetch(`/api/v1/access-governance/conflicts?company_id=${companyId}`,{headers:authHeaders()}).then(r=>r.ok?r.json():[]),
  ]).then(([d,c])=>{setDashboard(d);setConflicts(Array.isArray(c)?c:[])}).catch(()=>{});
  useEffect(()=>{load()},[companyId]);
  async function scan(){setBusy(true);setMessage('');try{const r=await fetch(`/api/v1/access-governance/scan/${companyId}`,{method:'POST',headers:authHeaders()});const p=await r.json();if(!r.ok)throw new Error(p.detail||'Scan failed');setMessage(ar?`تم الفحص: ${p.new_conflicts} تعارضات جديدة.`:`Scan completed: ${p.new_conflicts} new conflicts.`);await load()}catch(e:any){setMessage(e.message||String(e))}finally{setBusy(false)}}
  return <>
    <div className="assurance-hero">
      <div><span>{ar?'حوكمة الوصول وفصل المهام':'ACCESS GOVERNANCE & SEGREGATION OF DUTIES'}</span><h2>{ar?'لا صلاحيات حساسة بلا مراجعة دورية ومستقلة':'No sensitive access without independent periodic certification'}</h2><p>{ar?'يفحص تعارضات الصلاحيات، يمنع التصديق الذاتي، وينفذ سحب الدور بعد اعتماد حملة المراجعة.':'Detects permission conflicts, blocks self-certification and executes role revocation after campaign approval.'}</p></div>
      <div className="assurance-conclusion"><strong>{String(dashboard?.open_sod_conflicts||0)}</strong><span>{ar?'تعارضات مفتوحة':'Open conflicts'}</span></div>
    </div>
    <div className="kpis rich">
      <Kpi title={ar?'تعارضات مفتوحة':'Open SoD conflicts'} value={String(dashboard?.open_sod_conflicts||0)} trend={ar?'تحتاج إزالة أو ضابطًا مخففًا':'Require removal or mitigation'} good={!dashboard?.open_sod_conflicts}/>
      <Kpi title={ar?'تعارضات مخففة':'Mitigated conflicts'} value={String(dashboard?.mitigated_sod_conflicts||0)} trend={ar?'بموعد معالجة وضابط موثق':'Documented control and due date'} good/>
      <Kpi title={ar?'اعتمادات معلقة':'Pending certifications'} value={String(dashboard?.pending_access_certifications||0)} trend={ar?'لا تُغلق الحملة قبل حسمها':'Campaign cannot close while pending'} good={!dashboard?.pending_access_certifications}/>
      <Kpi title={ar?'حملات نشطة':'Active campaigns'} value={String(dashboard?.active_campaigns||0)} trend={ar?'مراجعة دورية للأدوار':'Periodic role review'} good/>
    </div>
    <div className="journal-footer"><span>{message||(ar?'الفحص لا يعتمد على اسم الدور فقط؛ بل يجمع جميع صلاحيات المستخدم داخل الشركة.':'The scan aggregates all user permissions across company roles, not role names only.')}</span><button disabled={busy} onClick={scan}>{busy?(ar?'جارٍ الفحص...':'Scanning...'):(ar?'تشغيل فحص فصل المهام':'Run SoD scan')}</button></div>
    <Panel title={ar?'تعارضات الصلاحيات':'Segregation-of-duties conflicts'} icon={<KeyRound size={18}/> }>
      <DataTable headers={[ar?'المستخدم':'User',ar?'القاعدة':'Rule',ar?'الخطورة':'Severity',ar?'الصلاحية الأولى':'Permission A',ar?'الصلاحية الثانية':'Permission B',ar?'الحالة':'Status']} rows={conflicts.map(r=>[r.user,r.rule_code,r.severity,r.permission_a,r.permission_b,r.status])}/>
    </Panel>
    <div className="three-columns">
      <MiniStatus icon={<UserCheck size={20}/>} title={ar?'منع التصديق الذاتي':'No self-certification'} value={ar?'مفعل':'Enabled'} status={ar?'لا يراجع المستخدم صلاحياته':'Users cannot review their own access'}/>
      <MiniStatus icon={<GitBranch size={20}/>} title={ar?'فصل المنشئ عن المعتمد':'Maker-checker'} value={ar?'إلزامي':'Mandatory'} status={ar?'مدير الوصول لا يعتمد حملته':'Access manager cannot approve campaign'}/>
      <MiniStatus icon={<ShieldCheck size={20}/>} title={ar?'سحب الصلاحية':'Access revocation'} value={ar?'منفذ آليًا':'System-enforced'} status={ar?'يطبق عند اعتماد قرار REVOKE':'Applied when REVOKE decision is approved'}/>
    </div>
  </>;
}

