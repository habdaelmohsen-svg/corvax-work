import type { ReactNode } from 'react';
import { CheckCircle2, ChevronRight, Clock3 } from 'lucide-react';
import {ButtonBase, Paper} from '@mui/material';

export const money = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
export const pct = (n: number) => `${n.toFixed(1)}%`;

export function AgeLine({label,value,percent,tone}:{label:string;value:string;percent:string;tone:string}){return <div className="age-line"><span><i className={tone}/>{label}</span><strong>{value}</strong><b>{percent}</b></div>}

export function QuickAction({icon,ar,arLabel,enLabel,tone,onClick}:{icon:ReactNode;ar:boolean;arLabel:string;enLabel:string;tone:string;onClick:()=>void}){return <ButtonBase className={`quick-action ${tone}`} onClick={onClick} aria-label={ar?arLabel:enLabel}><span>{icon}</span><strong>{ar?arLabel:enLabel}</strong><small>{ar?enLabel:arLabel}</small></ButtonBase>}

export function authHeaders():Record<string,string>{const token=sessionStorage.getItem('corvax_token');return token?{Authorization:`Bearer ${token}`}:{}}

export function jsonHeaders():Record<string,string>{return {'Content-Type':'application/json',...authHeaders()}}

export function Kpi({title,value,trend,good,icon,tone='blue',unit,onClick}:{title:string,value:string,trend:string,good:boolean,icon?:ReactNode,tone?:string,unit?:string,onClick?:()=>void}) {
  const points = tone==='green' ? '0,29 10,27 20,30 30,23 40,24 50,18 60,20 70,13 80,15 90,8 100,3' : tone==='violet' ? '0,25 10,22 20,27 30,20 40,23 50,15 60,18 70,11 80,13 90,6 100,2' : tone==='amber' ? '0,27 10,23 20,28 30,21 40,24 50,16 60,19 70,12 80,14 90,7 100,3' : '0,27 10,24 20,29 30,22 40,25 50,17 60,20 70,13 80,15 90,8 100,2';
  const ar=/[\u0600-\u06FF]/.test(title);
  const content = <><div className="kpi-heading">{icon&&<div className="kpi-icon">{icon}</div>}<div className="kpi-label"><span>{title}</span><small>{good?(ar?'موثّق':'ON TRACK'):(ar?'يحتاج انتباه':'ATTENTION')}</small></div><span className={`kpi-trend ${good?'good':'bad'}`}>{good?'↗':'↘'} {trend}</span></div><div className="kpi-main"><div className="kpi-value"><strong>{value}</strong>{unit&&<span>{unit}</span>}</div><div className="kpi-chart"><svg className="kpi-spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><polyline points={points}/></svg></div></div></>;
  return onClick
    ? <button type="button" className={`kpi-card tone-${tone} is-clickable`} onClick={onClick} aria-label={title}>{content}</button>
    : <Paper component="article" className={`kpi-card tone-${tone}`}>{content}</Paper>;
}

export function SimpleKpi({t,v}:{t:string,v:string}) { return <Paper component="article" className="simple-kpi"><span>{t}</span><strong>{v}</strong><i/></Paper>; }

export function Panel({title,icon,children,className='',onOpen,openLabel}:{title:string,icon:ReactNode,children:ReactNode,className?:string,onOpen?:()=>void,openLabel?:string}) { return <Paper component="section" className={`panel ${className}`}><div className="panel-head"><div className="panel-title-icon">{icon}</div><div className="panel-title-copy"><h3>{title}</h3><span>LIVE WORKSPACE</span></div>{onOpen&&<button type="button" className="panel-open" onClick={onOpen} aria-label={openLabel||title} title={openLabel||title}><ChevronRight size={17}/></button>}</div><div className="panel-body">{children}</div></Paper>; }

export function AlertRow({severity,title,meta,onClick}:{severity:'high'|'medium'|'low',title:string,meta:string,onClick?:()=>void}) {
  const content = <><i className={severity}/><div><strong>{title}</strong><span>{meta}</span></div><ChevronRight size={16}/></>;
  return onClick
    ? <button type="button" className="alert-row is-clickable" onClick={onClick} aria-label={title}>{content}</button>
    : <div className="alert-row">{content}</div>;
}

export function MiniStatus({icon,title,value,status}:{icon:ReactNode,title:string,value:string,status:string}) { return <Paper component="article" className="mini-status"><div className="module-icon">{icon}</div><div className="mini-status-copy"><span>{title}</span><strong>{value}</strong><small>{status}</small></div><i className="mini-status-dot"/></Paper>; }

export function ModuleCard({icon,title,text}:{icon:ReactNode,title:string,text:string}) { return <Paper component="article" className="module-card"><div className="module-icon">{icon}</div><div><strong>{title}</strong><span>{text}</span></div></Paper>; }

export function ProgressRow({label,value}:{label:string,value:number}) { return <div className="progress-row"><div><span>{label}</span><strong>{value}%</strong></div><div className="progress"><i style={{width:`${value}%`}}/></div></div>; }

export function Statement({title,rows,asOfDate}:{title:string,rows:Array<[string,number,boolean]>,asOfDate?:string}) { const ar=/[\u0600-\u06FF]/.test(title); const renderedDate=new Intl.DateTimeFormat(ar?'ar-SA':'en-GB',{dateStyle:'medium'}).format(asOfDate?new Date(asOfDate):new Date()); return <section className="statement"><div className="statement-head"><div><span>{ar?'تقارير كورفاكس المالية':'CORVAX FINANCIAL REPORTING'}</span><h2>{title}</h2></div><div><small>{renderedDate}</small><strong>{ar?'ريال سعودي':'SAR'}</strong></div></div>{rows.map(([label,value,positive],i)=><div className={`statement-row ${i===2||i===4||i===rows.length-1?'subtotal':''}`} key={label}><span>{label}</span><strong className={positive?'':'negative'}>{value<0?'(' : ''}{money.format(Math.abs(value))}{value<0?')':''}</strong></div>)}</section>; }

export function NoteCard({no,title,standard,status}:{no:string,title:string,standard:string,status:string}) { return <article className="note-card"><span>{no}</span><div><strong>{title}</strong><small>{standard}</small></div><i>{status}</i></article>; }

export function Flow({steps}:{steps:string[]}) { return <div className="flow">{steps.map((s,i)=><div key={s}><span>{i+1}</span><strong>{s}</strong>{i<steps.length-1&&<ChevronRight size={15}/>}</div>)}</div>; }

export function Checklist({items}:{items:Array<[string,boolean]>}) { return <div className="checklist">{items.map(([label,done])=>{const ar=/[\u0600-\u06FF]/.test(label);return <div key={label}>{done?<CheckCircle2 className="done" size={18}/>:<Clock3 className="pending" size={18}/>}<span>{label}</span><strong>{done?(ar?'مكتمل':'Done'):(ar?'معلّق':'Pending')}</strong></div>})}</div>; }

export function SummaryLine({label,value,warn=false}:{label:string,value:string,warn?:boolean}) { return <div className="summary-line"><span>{label}</span><strong className={warn?'warning':''}>{value}</strong></div>; }

export function CostBar({label,value,max}:{label:string,value:number,max:number}) { return <div className="cost-bar"><div><span>{label}</span><strong>{value.toFixed(2)}</strong></div><div><i style={{width:`${value/max*100}%`}}/></div></div>; }

export function DataTable({headers,rows}:{headers:string[],rows:ReactNode[][]}) { const ar=headers.some(h=>/[\u0600-\u06FF]/.test(h)); return <Paper className="data-table responsive" role="table" aria-label={ar?'جدول البيانات':'Data table'}><div className="tr th" role="row" style={{gridTemplateColumns:`repeat(${headers.length}, minmax(125px, 1fr))`}}>{headers.map(h=><span role="columnheader" key={h}>{h}</span>)}</div>{rows.length===0?<div className="table-empty"><span>{ar?'لا توجد بيانات متاحة':'No data available'}</span><small>{ar?'ستظهر السجلات هنا عند توفرها.':'Records will appear here when available.'}</small></div>:rows.map((r,i)=><div className="tr" role="row" style={{gridTemplateColumns:`repeat(${headers.length}, minmax(125px, 1fr))`}} key={i}>{r.map((c,j)=><span role="cell" data-label={headers[j]} key={`${i}-${j}`}>{c}</span>)}</div>)}</Paper>; }

export function fmt(n:number){return money.format(n);}
