import {useEffect,useState} from 'react';
import {api} from './api';

type ComparedRun={run_id:string;title:string;purpose:string;state:string;account:string|null;
  points:{step:number;elapsed_seconds:number;total_steps:number;metrics:Record<string,number>}[];
  parent_run_id:string|null;metric:{name:string;direction:string;final_value:number;best_value:number}|null;
  protocol:{mode:string;data:[string,number,string][];split:unknown;metric:unknown}};
type Comparison={runs:ComparedRun[];same_protocol:boolean;warnings:string[];ranked_run_ids:string[]};

const colors=['#68a9ef','#dc8b47','#64c59b','#cc82da','#d8c569','#e58189','#9c9df4','#70c5d1'];
function ComparisonCurve({runs,metric}:{runs:ComparedRun[];metric:string}) {
  const series=runs.map(run=>({...run,points:run.points.filter(point=>Number.isFinite(point.metrics[metric]))}));
  const points=series.flatMap(run=>run.points);
  if(!points.length)return <p className="muted">Chưa có mẫu theo step để vẽ curve chung.</p>;
  const low=Math.min(...points.map(point=>point.metrics[metric])),high=Math.max(...points.map(point=>point.metrics[metric]));
  const scale=Math.max(Math.abs(low),Math.abs(high))||1,range=high/scale-low/scale;
  const minStep=Math.min(...points.map(point=>point.step)),maxStep=Math.max(...points.map(point=>point.step));
  const x=(step:number)=>maxStep===minStep?234:72+(step-minStep)/(maxStep-minStep)*324;
  const y=(value:number)=>range===0?100:28+(high/scale-value/scale)/range*140;
  return <section aria-label="Curve so sánh"><h4>{metric} theo step</h4>
    <svg className="metric-curve" viewBox="0 0 420 220" role="img" aria-label={`So sánh ${metric} theo step`}>
      {[low,high].map((value,index)=><g key={index}><line className="metric-grid" x1="72" x2="396" y1={y(value)} y2={y(value)}/>
        <text x="62" y={y(value)+4} textAnchor="end">{value.toPrecision(4)}</text></g>)}
      {series.map((run,index)=><g key={run.run_id}><polyline fill="none" stroke={colors[index]} strokeWidth="2"
        points={run.points.map(point=>`${x(point.step)},${y(point.metrics[metric])}`).join(' ')}/>
        {run.points.map(point=><circle key={point.step} cx={x(point.step)} cy={y(point.metrics[metric])} r="3" fill={colors[index]}>
          <title>{run.title}: step {point.step} · {point.metrics[metric]}</title></circle>)}</g>)}
      <text x="72" y="195">{minStep}</text><text x="396" y="195" textAnchor="end">{maxStep}</text>
      <text x="234" y="216" textAnchor="middle">Step</text></svg>
    <ul>{series.map((run,index)=><li key={run.run_id}><span style={{color:colors[index]}}>●</span> {run.title} · {run.points.length} mẫu · cuối {run.points[run.points.length-1]?.metrics[metric]?.toPrecision(4)||'—'}</li>)}</ul></section>;
}

export default function RunComparison({projectId,runIds,onClose,onOpen}:{projectId:string;runIds:string[];
  onClose:()=>void;onOpen:(id:string)=>void}) {
  const [data,setData]=useState<Comparison|null>(null),[error,setError]=useState('');
  useEffect(()=>{let cancelled=false;let timer:number;setData(null);setError('');
    async function refresh() {
      try {
        const value=await api<Comparison>(`/projects/${projectId}/runs/compare`,'POST',{run_ids:runIds});
        if(cancelled)return;
        setData(value);setError('');
        if(value.runs.some(run=>!['COMPLETED','FAILED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED'].includes(run.state)))
          timer=window.setTimeout(refresh,2000);
      } catch(e) {if(!cancelled)setError(e instanceof Error?e.message:String(e));}
    }
    void refresh();
    return ()=>{cancelled=true;window.clearTimeout(timer);};
  },[projectId,runIds.join(',')]);
  return <section className="run-comparison" aria-label="So sánh run"><div className="panel-head"><h3>So sánh run</h3>
    <button type="button" onClick={onClose}>Đóng</button></div>
    {error && <p role="alert" className="alert error">{error}</p>}
    {!data && !error && <p role="status">Đang đối chiếu protocol và kết quả đã lưu…</p>}
    {data && <>{data.warnings.map(warning=><p key={warning} role="status" className="alert error">{warning}</p>)}
      {data.same_protocol && <p className="muted">Cùng nguồn dữ liệu, split và metric đã duyệt.</p>}
      <div className="run-board-scroll"><table className="run-board-table"><thead><tr><th>Run</th><th>Account / trạng thái</th>
        <th>Run cha</th><th>Metric cuối</th><th>Hạng</th></tr></thead><tbody>
        {data.runs.map(run=><tr key={run.run_id}><td><button type="button" className="run-board-open" onClick={()=>onOpen(run.run_id)}>
          {run.title||run.run_id.slice(0,8)}</button><small className="run-purpose-preview" title={run.purpose}>{run.purpose}</small></td>
          <td>{run.account||'chưa gán'} · {run.state}</td><td className="mono">{run.parent_run_id?.slice(0,8)||'—'}</td>
          <td>{run.metric?`${run.metric.name}: ${run.metric.final_value}`:'chưa có'}</td>
          <td>{data.ranked_run_ids.includes(run.run_id)?data.ranked_run_ids.indexOf(run.run_id)+1:'—'}</td></tr>)}
        </tbody></table></div>
      {data.same_protocol && typeof data.runs[0]?.protocol.metric==='object' && data.runs[0].protocol.metric
        && <ComparisonCurve runs={data.runs} metric={String((data.runs[0].protocol.metric as {name?:string}).name||'')}/>}</>}
  </section>;
}
