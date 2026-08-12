import type {ComparativeStatementRow, ComparisonPeriods} from './financialStatementEngine';
import {formatStatementAmount, formatVariancePercent} from './financialStatementEngine';

const periodLabel = (period: {start:string;end:string}) => period.start === period.end
  ? period.end
  : `${period.start} — ${period.end}`;

export function ComparativeStatementTable({
  ar,
  title,
  rows,
  periods,
  loading=false,
}: {
  ar:boolean;
  title:string;
  rows:ComparativeStatementRow[];
  periods:ComparisonPeriods;
  loading?:boolean;
}) {
  return <section className="comparative-statement" aria-busy={loading}>
    <div className="comparative-statement__head">
      <div><span>{ar?'تقارير مالية موحّدة':'UNIFIED FINANCIAL REPORTING'}</span><h2>{title}</h2></div>
      <div><small>{ar?'العملة':'Currency'}</small><strong>{ar?'ريال سعودي':'SAR'}</strong></div>
    </div>
    <div className="comparative-statement__scroll">
      <table>
        <thead><tr>
          <th>{ar?'البند':'Item'}</th>
          <th className="numeric"><span>{ar?'الفترة الحالية':'Current period'}</span><small>{periodLabel(periods.current)}</small></th>
          <th className="numeric"><span>{ar?'الفترة السابقة':'Previous period'}</span><small>{periodLabel(periods.previous)}</small></th>
          <th className="numeric"><span>{ar?'الفترة المماثلة':'Same period last year'}</span><small>{periodLabel(periods.priorYear)}</small></th>
          <th className="numeric"><span>{ar?'التغير':'Variance'}</span><small>{ar?'عن الفترة السابقة':'vs previous period'}</small></th>
          <th className="numeric"><span>{ar?'نسبة التغير':'Variance %'}</span><small>{ar?'عن الفترة السابقة':'vs previous period'}</small></th>
        </tr></thead>
        <tbody>{rows.map((row)=><tr key={row.code} data-kind={row.kind}>
          <td>{row.label}</td>
          <td className="numeric">{formatStatementAmount(row.current)}</td>
          <td className="numeric">{formatStatementAmount(row.previous)}</td>
          <td className="numeric">{formatStatementAmount(row.priorYear)}</td>
          <td className={`numeric ${row.variance<0?'negative':row.variance>0?'positive':''}`}>{formatStatementAmount(row.variance)}</td>
          <td className={`numeric ${row.variancePercent!==null&&row.variancePercent<0?'negative':row.variancePercent!==null&&row.variancePercent>0?'positive':''}`}>{formatVariancePercent(row.variancePercent)}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <footer>{ar?'المصدر: القيود المرحلة في دفتر الأستاذ العام':'Source: posted entries in the general ledger'}</footer>
  </section>;
}
