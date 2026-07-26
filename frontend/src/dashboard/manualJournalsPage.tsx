import {useEffect, useMemo, useState} from 'react';
import {BookOpenCheck, Plus, Trash2, Scale, Send, CheckCircle2, RotateCcw, Paperclip, Search} from 'lucide-react';
import {apiFetch} from '../api/client';
import {DataTable, Kpi, Panel, fmt} from './ui';

// A real manual journal entry screen:
//  - pick any postable account from the chart of accounts (searchable)
//  - unlimited lines (add / remove)
//  - real, editable entry date
//  - live balance indicator (debit vs credit) with a guard before saving
//  - optional cost center and branch per line
//  - full workflow: save -> submit -> approve -> post -> reverse
//  - attach supporting documents to a posted journal

type Account={id:number;code:string;name_ar:string;name_en:string;type:string;is_postable:boolean;active:boolean};
type CostCenter={id:number;code:string;name_ar:string;name_en:string};
type Branch={id:number;code:string;name_ar:string;name_en:string};
type Line={account_code:string;description:string;debit:string;credit:string;cost_center_code:string;branch_code:string};
type Journal={id:number;number:string;entry_date:string;reference:string;description:string;status:string;total_debit:number;total_credit:number};

async function json(url:string,init?:RequestInit){
  const r=await apiFetch(url,init); const x=await r.json().catch(()=>({}));
  if(!r.ok){
    const d=x.detail;
    throw new Error(typeof d==='string'?d:(Array.isArray(d)?d.map((i:any)=>i.msg||JSON.stringify(i)).join(' | '):JSON.stringify(d||x)));
  }
  return x;
}
const iso=(d=new Date())=>d.toISOString().slice(0,10);
const field={display:'block',width:'100%',marginTop:5,padding:9,border:'1px solid var(--border)',borderRadius:9} as const;
const cell={width:'100%',padding:'7px 8px',border:'1px solid var(--border)',borderRadius:7,fontSize:13} as const;
const btn={padding:'9px 16px',borderRadius:9,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600} as const;
const ghost={padding:'8px 14px',borderRadius:9,border:'1px solid var(--border)',background:'transparent',color:'var(--text)',cursor:'pointer',fontWeight:600} as const;
const smallBtn={padding:'4px 10px',borderRadius:7,border:'none',background:'var(--accent, #1e40af)',color:'#fff',cursor:'pointer',fontWeight:600,fontSize:12} as const;
const th={textAlign:'start',padding:'8px 10px',borderBottom:'2px solid var(--border)',fontWeight:700,fontSize:13} as const;
const td={padding:'6px 8px',borderBottom:'1px solid var(--border)',fontSize:13,verticalAlign:'top'} as const;

const emptyLine=():Line=>({account_code:'',description:'',debit:'',credit:'',cost_center_code:'',branch_code:''});
const CF_ACTIVITIES:[string,string,string][]=[['','بدون تصنيف','No classification'],['OPERATING','تشغيلية','Operating'],['INVESTING','استثمارية','Investing'],['FINANCING','تمويلية','Financing']];

export function ManualJournalsPage({ar,companyId}:{ar:boolean;companyId:number}){
  const [accounts,setAccounts]=useState<Account[]>([]);
  const [costCenters,setCostCenters]=useState<CostCenter[]>([]);
  const [branches,setBranches]=useState<Branch[]>([]);
  const [journals,setJournals]=useState<Journal[]>([]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  // header
  const [entryDate,setEntryDate]=useState(iso());
  const [reference,setReference]=useState('');
  const [description,setDescription]=useState('');
  const [cfActivity,setCfActivity]=useState('');
  // lines
  const [lines,setLines]=useState<Line[]>([emptyLine(),emptyLine()]);
  const [accountFilter,setAccountFilter]=useState('');

  const load=async()=>{
    try{
      const [ch,cc,br,js]=await Promise.all([
        json(`/api/v1/enterprise/companies/${companyId}/chart-of-accounts`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/cost-centers`).catch(()=>[]),
        json(`/api/v1/enterprise/companies/${companyId}/branches`).catch(()=>[]),
        json(`/api/v1/finance/journals?company_id=${companyId}&limit=20`).catch(()=>[]),
      ]);
      const rows:Account[]=Array.isArray(ch)?ch:(ch.accounts||ch.rows||[]);
      setAccounts(rows.filter(a=>a.is_postable&&a.active));
      setCostCenters(Array.isArray(cc)?cc:[]);
      setBranches(Array.isArray(br)?br:[]);
      setJournals(Array.isArray(js)?js:(js.rows||[]));
    }catch(e:any){setMessage(String(e.message||e));}
  };
  useEffect(()=>{load()},[companyId]);

  const setLine=(i:number,patch:Partial<Line>)=>setLines(p=>p.map((l,idx)=>idx===i?{...l,...patch}:l));
  const addLine=()=>setLines(p=>[...p,emptyLine()]);
  const removeLine=(i:number)=>setLines(p=>p.length<=2?p:p.filter((_,idx)=>idx!==i));

  const totals=useMemo(()=>{
    const d=lines.reduce((s,l)=>s+(Number(l.debit)||0),0);
    const c=lines.reduce((s,l)=>s+(Number(l.credit)||0),0);
    return {debit:d,credit:c,diff:Math.round((d-c)*100)/100};
  },[lines]);
  const balanced=totals.diff===0&&totals.debit>0;

  const filteredAccounts=useMemo(()=>{
    const q=accountFilter.trim().toLowerCase();
    if(!q)return accounts;
    return accounts.filter(a=>a.code.includes(q)||a.name_ar.toLowerCase().includes(q)||a.name_en.toLowerCase().includes(q));
  },[accounts,accountFilter]);

  const accountLabel=(code:string)=>{
    const a=accounts.find(x=>x.code===code);
    return a?`${a.code} — ${ar?a.name_ar:a.name_en}`:code;
  };

  const resetForm=()=>{setLines([emptyLine(),emptyLine()]);setReference('');setDescription('');setCfActivity('');};

  const saveJournal=async()=>{
    if(!reference.trim()||!description.trim()){setMessage(ar?'المرجع والبيان إلزاميان':'Reference and description are required');return;}
    const usable=lines.filter(l=>l.account_code&&((Number(l.debit)||0)>0||(Number(l.credit)||0)>0));
    if(usable.length<2){setMessage(ar?'القيد يحتاج سطرين على الأقل بحساب ومبلغ':'At least two lines with an account and an amount are required');return;}
    for(const l of usable){
      if((Number(l.debit)||0)>0&&(Number(l.credit)||0)>0){setMessage(ar?'لا يجوز أن يحتوي السطر على مدين ودائن معًا':'A line cannot hold both debit and credit');return;}
    }
    if(!balanced){setMessage(ar?`القيد غير متوازن: الفرق ${fmt(Math.abs(totals.diff))}`:`Not balanced: difference ${fmt(Math.abs(totals.diff))}`);return;}
    setBusy(true);setMessage('');
    try{
      const body:any={
        company_id:companyId,entry_date:entryDate,reference:reference.trim(),description:description.trim(),
        lines:usable.map(l=>({
          account_code:l.account_code,
          description:l.description||description.trim(),
          debit:Number(l.debit)||0,credit:Number(l.credit)||0,
          ...(l.cost_center_code?{cost_center_code:l.cost_center_code}:{}),
          ...(l.branch_code?{branch_code:l.branch_code}:{}),
        })),
      };
      if(cfActivity)body.cash_flow_activity=cfActivity;
      const r=await json('/api/v1/finance/journals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      setMessage(ar?`تم حفظ القيد ${r.number} — الحالة ${r.status}`:`Journal ${r.number} saved — status ${r.status}`);
      resetForm();await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const workflow=async(id:number,action:'submit'|'approve'|'post'|'reverse')=>{
    setBusy(true);setMessage('');
    try{
      const r=await json(`/api/v1/finance/journals/${id}/${action}`,{method:'POST'});
      const labels:any={submit:ar?'تم التقديم':'Submitted',approve:ar?'تم الاعتماد':'Approved',post:ar?'تم الترحيل':'Posted',reverse:ar?'تم العكس':'Reversed'};
      setMessage(`${labels[action]} — ${r.number||id}`);await load();
    }catch(e:any){setMessage(String(e.message||e));}finally{setBusy(false);}
  };

  const posted=journals.filter(j=>j.status==='POSTED').length;
  const inFlow=journals.filter(j=>!['POSTED','REVERSED'].includes(j.status)).length;

  return <>
    <div className="kpis">
      <Kpi title={ar?'الحسابات القابلة للترحيل':'Postable accounts'} value={String(accounts.length)} trend="" good icon={<BookOpenCheck size={22}/>} tone="blue"/>
      <Kpi title={ar?'قيود معروضة':'Listed journals'} value={String(journals.length)} trend="" good icon={<Scale size={22}/>} tone="violet"/>
      <Kpi title={ar?'مرحّلة':'Posted'} value={String(posted)} trend="" good icon={<CheckCircle2 size={22}/>} tone="green"/>
      <Kpi title={ar?'تحت الإجراء':'In workflow'} value={String(inFlow)} trend="" good={inFlow===0} icon={<Send size={22}/>} tone="amber"/>
    </div>

    {message&&<div style={{padding:11,margin:'12px 0',borderRadius:9,background:'var(--panel-2, #f1f5f9)',fontSize:14,lineHeight:1.7}}>{message}</div>}

    <Panel title={ar?'قيد يومية جديد':'New journal entry'} icon={<BookOpenCheck size={18}/>}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12,padding:12}}>
        <label>{ar?'تاريخ القيد':'Entry date'}<input type="date" style={field} value={entryDate} onChange={e=>setEntryDate(e.target.value)}/></label>
        <label>{ar?'المرجع':'Reference'}<input style={field} value={reference} onChange={e=>setReference(e.target.value)} placeholder={ar?'JV-2026-001':''}/></label>
        <label>{ar?'البيان':'Description'}<input style={field} value={description} onChange={e=>setDescription(e.target.value)} placeholder={ar?'بيان القيد':''}/></label>
        <label>{ar?'تصنيف التدفق النقدي':'Cash flow activity'}<select style={field} value={cfActivity} onChange={e=>setCfActivity(e.target.value)}>{CF_ACTIVITIES.map(([v,a,e])=><option key={v} value={v}>{ar?a:e}</option>)}</select></label>
      </div>

      <div style={{padding:'0 12px 8px',display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
        <div style={{display:'flex',alignItems:'center',gap:6,flex:'1 1 240px'}}>
          <Search size={15} style={{opacity:0.6}}/>
          <input style={{...cell,margin:0}} value={accountFilter} onChange={e=>setAccountFilter(e.target.value)} placeholder={ar?'بحث في شجرة الحسابات (رقم أو اسم)':'Search chart of accounts'}/>
        </div>
        <button style={{...ghost,display:'flex',alignItems:'center',gap:6}} onClick={addLine}><Plus size={15}/>{ar?'إضافة سطر':'Add line'}</button>
      </div>

      <div style={{overflowX:'auto',padding:'0 12px'}}>
        <table style={{width:'100%',borderCollapse:'collapse'}}>
          <thead><tr>
            <th style={{...th,width:'26%'}}>{ar?'الحساب':'Account'}</th>
            <th style={{...th,width:'20%'}}>{ar?'البيان':'Description'}</th>
            <th style={{...th,width:'13%'}}>{ar?'مدين':'Debit'}</th>
            <th style={{...th,width:'13%'}}>{ar?'دائن':'Credit'}</th>
            <th style={{...th,width:'12%'}}>{ar?'مركز التكلفة':'Cost center'}</th>
            <th style={{...th,width:'12%'}}>{ar?'الفرع':'Branch'}</th>
            <th style={{...th,width:'4%'}}></th>
          </tr></thead>
          <tbody>
            {lines.map((l,i)=>(
              <tr key={i}>
                <td style={td}>
                  <select style={cell} value={l.account_code} onChange={e=>setLine(i,{account_code:e.target.value})}>
                    <option value="">{ar?'اختر الحساب...':'Select account...'}</option>
                    {filteredAccounts.map(a=><option key={a.code} value={a.code}>{a.code} — {ar?a.name_ar:a.name_en}</option>)}
                  </select>
                </td>
                <td style={td}><input style={cell} value={l.description} onChange={e=>setLine(i,{description:e.target.value})}/></td>
                <td style={td}><input type="number" min="0" step="0.01" style={{...cell,textAlign:'end'}} value={l.debit} onChange={e=>setLine(i,{debit:e.target.value,credit:e.target.value?'':l.credit})}/></td>
                <td style={td}><input type="number" min="0" step="0.01" style={{...cell,textAlign:'end'}} value={l.credit} onChange={e=>setLine(i,{credit:e.target.value,debit:e.target.value?'':l.debit})}/></td>
                <td style={td}>
                  <select style={cell} value={l.cost_center_code} onChange={e=>setLine(i,{cost_center_code:e.target.value})}>
                    <option value="">—</option>
                    {costCenters.map(c=><option key={c.code} value={c.code}>{ar?c.name_ar:c.name_en}</option>)}
                  </select>
                </td>
                <td style={td}>
                  <select style={cell} value={l.branch_code} onChange={e=>setLine(i,{branch_code:e.target.value})}>
                    <option value="">—</option>
                    {branches.map(b=><option key={b.code} value={b.code}>{ar?b.name_ar:b.name_en}</option>)}
                  </select>
                </td>
                <td style={td}>
                  <button title={ar?'حذف السطر':'Remove line'} onClick={()=>removeLine(i)} disabled={lines.length<=2}
                    style={{padding:6,borderRadius:7,border:'1px solid var(--border)',background:'transparent',cursor:lines.length<=2?'not-allowed':'pointer',opacity:lines.length<=2?0.4:1}}>
                    <Trash2 size={14}/>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td style={{...td,fontWeight:700}} colSpan={2}>{ar?'الإجمالي':'Total'}</td>
              <td style={{...td,fontWeight:700,textAlign:'end'}}>{fmt(totals.debit)}</td>
              <td style={{...td,fontWeight:700,textAlign:'end'}}>{fmt(totals.credit)}</td>
              <td style={td} colSpan={3}></td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div style={{margin:'10px 12px',padding:'10px 14px',borderRadius:9,display:'flex',alignItems:'center',gap:10,
        background:balanced?'#dcfce7':(totals.debit||totals.credit)?'#fee2e2':'var(--panel-2, #f1f5f9)',
        color:balanced?'#166534':(totals.debit||totals.credit)?'#991b1b':'var(--text)',fontSize:14,fontWeight:600}}>
        <Scale size={17}/>
        {balanced
          ? (ar?'القيد متوازن وجاهز للحفظ':'Journal is balanced and ready to save')
          : (totals.debit||totals.credit)
            ? (ar?`القيد غير متوازن — الفرق ${fmt(Math.abs(totals.diff))}`:`Not balanced — difference ${fmt(Math.abs(totals.diff))}`)
            : (ar?'أدخل الحسابات والمبالغ':'Enter accounts and amounts')}
      </div>

      <div style={{padding:'0 12px 14px',display:'flex',gap:8,flexWrap:'wrap'}}>
        <button style={{...btn,opacity:(busy||!balanced)?0.55:1}} disabled={busy||!balanced} onClick={saveJournal}>{ar?'حفظ القيد':'Save journal'}</button>
        <button style={ghost} disabled={busy} onClick={resetForm}>{ar?'تفريغ النموذج':'Clear form'}</button>
      </div>
    </Panel>

    <Panel title={ar?'دورة القيود (تقديم ← اعتماد ← ترحيل)':'Journal workflow (submit → approve → post)'} icon={<Send size={18}/>}>
      <div style={{overflowX:'auto',padding:'0 4px 12px'}}>
        <table style={{width:'100%',borderCollapse:'collapse'}}>
          <thead><tr>
            <th style={th}>{ar?'الرقم':'No.'}</th><th style={th}>{ar?'التاريخ':'Date'}</th>
            <th style={th}>{ar?'المرجع':'Reference'}</th><th style={th}>{ar?'البيان':'Description'}</th>
            <th style={th}>{ar?'مدين':'Debit'}</th><th style={th}>{ar?'دائن':'Credit'}</th>
            <th style={th}>{ar?'الحالة':'Status'}</th><th style={th}>{ar?'إجراء':'Action'}</th>
          </tr></thead>
          <tbody>
            {journals.map(j=>(
              <tr key={j.id}>
                <td style={td}>{j.number}</td>
                <td style={td}>{j.entry_date}</td>
                <td style={td}>{j.reference}</td>
                <td style={td}>{j.description}</td>
                <td style={{...td,textAlign:'end'}}>{fmt(Number(j.total_debit||0))}</td>
                <td style={{...td,textAlign:'end'}}>{fmt(Number(j.total_credit||0))}</td>
                <td style={td}>{j.status}</td>
                <td style={td}>
                  <span style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                    {j.status==='DRAFT'&&<button style={smallBtn} disabled={busy} onClick={()=>workflow(j.id,'submit')}>{ar?'تقديم':'Submit'}</button>}
                    {j.status==='SUBMITTED'&&<button style={smallBtn} disabled={busy} onClick={()=>workflow(j.id,'approve')}>{ar?'اعتماد':'Approve'}</button>}
                    {j.status==='APPROVED'&&<button style={{...smallBtn,background:'#059669'}} disabled={busy} onClick={()=>workflow(j.id,'post')}>{ar?'ترحيل':'Post'}</button>}
                    {j.status==='POSTED'&&<button style={{...smallBtn,background:'#b45309'}} disabled={busy} onClick={()=>workflow(j.id,'reverse')} title={ar?'عكس القيد':'Reverse'}><RotateCcw size={12}/></button>}
                    {j.status==='REVERSED'&&'—'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{padding:'0 12px 12px',fontSize:13,opacity:0.75,display:'flex',alignItems:'center',gap:7}}>
        <Paperclip size={14}/>{ar?'يمكن إرفاق المستندات المؤيدة للقيد من نظام المرفقات (نوع الكيان: JOURNAL_ENTRY).':'Supporting documents can be attached via the attachments system (entity type: JOURNAL_ENTRY).'}
      </div>
    </Panel>
  </>;
}
