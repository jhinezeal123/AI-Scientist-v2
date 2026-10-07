import {useEffect,useState} from 'react';
import {api} from './api';
import RunLogView from './RunLogView';

type MetricPoint={step:number;elapsed_seconds:number;total_steps:number;metrics:Record<string,number>};
type Delta={run_state:string;generation:number;entries:{seq:number;text:string;stream:string}[];next_cursor:string;
  has_more:boolean;reset:boolean;gap:boolean;terminal:boolean;
  error:string|null;telemetry_error:string|null;points:MetricPoint[];primary_metric:string|null;direction:string|null;
  observation:{identity:{status:string};observed_at:string;source:string;complete:boolean}|null};

function metricValue(value:number) {
  return Math.abs(value)>=1e6 || (value!==0 && Math.abs(value)<0.0001)
    ? value.toExponential(3) : value.toLocaleString('en-US',{maximumFractionDigits:4});
}

function MetricCurve({points,metric}:{points:MetricPoint[];metric:string}) {
  const values=points.map(point=>point.metrics[metric]);
  const minimum=Math.min(...values),maximum=Math.max(...values);
  const scale=Math.max(Math.abs(minimum),Math.abs(maximum)) || 1;
  const range=maximum/scale-minimum/scale;
  const firstStep=points[0].step,lastStep=points[points.length-1].step;
  const x=(step:number)=>firstStep===lastStep ? 224 : 72+(step-firstStep)/(lastStep-firstStep)*304;
  const y=(value:number)=>range===0 ? 99 : 30+(maximum/scale-value/scale)/range*138;
  return <svg className="metric-curve" viewBox="0 0 400 220" role="img" aria-label={`${metric} theo step`}>
    <title>{metric} theo step</title>
    <desc>{points.length} mẫu; từ {metricValue(values[0])} đến {metricValue(values[values.length-1])}.</desc>
    {Array.from(new Set([maximum,maximum/2+minimum/2,minimum])).map((value,index)=><g key={index}>
      <line className="metric-grid" x1="72" x2="376" y1={y(value)} y2={y(value)}/>
      <text x="62" y={y(value)+4} textAnchor="end">{metricValue(value)}</text>
    </g>)}
    <polyline className="metric-line" points={points.map(point=>`${x(point.step)},${y(point.metrics[metric])}`).join(' ')}/>
    {points.map(point=><circle className="metric-point" key={point.step} cx={x(point.step)} cy={y(point.metrics[metric])} r="4">
      <title>Step {point.step}: {metricValue(point.metrics[metric])}</title>
    </circle>)}
    <text x={x(firstStep)} y="200" textAnchor="middle">{firstStep}</text>
    {lastStep!==firstStep && <text x={x(lastStep)} y="200" textAnchor="middle">{lastStep}</text>}
    <text x="224" y="216" textAnchor="middle">Step</text>
  </svg>;
}

export default function RunMonitorPanel({projectId,runId,onObserved,working=false}:{projectId:string;runId:string;onObserved:(state:string)=>void;working?:boolean}) {
  const [data,setData]=useState<Delta|null>(null);
  const [entries,setEntries]=useState<Delta['entries']>([]);
  const [error,setError]=useState('');
  const [selectedMetric,setSelectedMetric]=useState('');
  useEffect(() => {
    let cancelled=false;let cursor:string|undefined;let generation:number|undefined;let timer:number;
    setData(null);setEntries([]);setError('');setSelectedMetric('');
    async function poll() {
      try {
        let page:Delta;
        do {
          page=await api<Delta>(`/projects/${projectId}/runs/${runId}/logs${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`);
          if (cancelled)return;
          const changed=generation!==undefined && generation!==page.generation;
          generation=page.generation;cursor=page.next_cursor;
          const received=page;
          setEntries(old => {
            const base=changed || received.reset ? [] : old;
            const last=base.length ? base[base.length-1].seq : 0;
            return [...base,...received.entries.filter(entry => entry.seq>last)];
          });
          setData(page);setError('');
          onObserved(page.run_state);
        } while (page.has_more);
        if (!page.terminal)timer=window.setTimeout(poll,2000);
      } catch(e) {
        if (!cancelled) {setError(e instanceof Error ? e.message : String(e));timer=window.setTimeout(poll,2000);}
      }
    }
    void poll();
    return () => {cancelled=true;window.clearTimeout(timer);};
  },[projectId,runId,onObserved]);
  const points=data?.points || [];
  const metrics=Array.from(new Set(points.flatMap(point=>Object.keys(point.metrics)
    .filter(name=>Number.isFinite(point.metrics[name])))));
  const metric=metrics.includes(selectedMetric) ? selectedMetric : metrics.includes('training_loss')
    ? 'training_loss' : data?.primary_metric && metrics.includes(data.primary_metric) ? data.primary_metric : metrics[0];
  const samples=metric ? points.filter(point=>Number.isFinite(point.metrics[metric])) : [];
  const latest=samples[samples.length-1];
  return <div className="context monitor-panel"><div className="panel-head"><h3>{working ? 'Log Working' : 'Theo dõi Kaggle'}</h3>
    <span className="state-tag">{data?.terminal ? 'Đã kết thúc' : working ? 'Đang theo dõi' : data?.observation ? 'Theo dõi nền' : 'Đang chờ quan sát'}</span></div>
    {data?.observation && <p className="muted">{data.observation.identity.status} · Quan sát lúc {new Date(data.observation.observed_at).toLocaleTimeString('vi-VN')}</p>}
    {(error || data?.error) && <p className="alert error" role="alert">{error || data?.error}</p>}
    {data?.gap && <p className="alert error">Nguồn log bị cắt hoặc đổi. Đã lưu generation mới; đang chờ đối soát log terminal.</p>}
    {data?.telemetry_error && <p className="alert error" role="alert">{data.telemetry_error}</p>}
    {!working && latest && <section className="training-metrics" aria-label="Loss và metric training">
      <div className="panel-head"><h3>Loss và metric</h3>
        <span className="muted">Step {latest.step}/{latest.total_steps} · {samples.length} mẫu</span></div>
      <label>Metric hiển thị<select value={metric} onChange={event=>setSelectedMetric(event.target.value)}>
        {metrics.map(name=><option key={name} value={name}>{name}</option>)}
      </select></label>
      <p className="metric-latest"><strong>{metricValue(latest.metrics[metric])}</strong>
        <span className="muted">Giá trị gần nhất{metric===data?.primary_metric && data.direction
          ? ` · ${data.direction==='minimize' ? 'Càng thấp càng tốt' : 'Càng cao càng tốt'}` : ''}</span></p>
      <MetricCurve points={samples} metric={metric}/>
      <details><summary>Số liệu từng step</summary><div className="metric-table-wrap">
        <table className="metric-table"><caption>{metric}</caption><thead><tr><th scope="col">Step</th>
          <th scope="col">Thời gian (giây)</th><th scope="col">Giá trị</th></tr></thead>
          <tbody>{samples.map(point=><tr key={point.step}><th scope="row">{point.step}</th>
            <td>{point.elapsed_seconds.toFixed(1)}</td><td>{metricValue(point.metrics[metric])}</td></tr>)}</tbody>
        </table></div></details>
    </section>}
    <RunLogView entries={entries} generation={data?.generation || 1}/>
  </div>;
}
