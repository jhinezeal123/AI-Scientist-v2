import {useEffect,useState} from 'react';
import {api,KaggleAccount} from './api';
import {RunConfiguration,RunExecutionConfiguration,sameExperimentStrategy} from './projectConfiguration';
import RunExecutionFields from './RunExecutionFields';

export type ConfiguredBatchItem={run_id:string;version:number;configuration:RunConfiguration};
export default function BatchRunConfiguration({projectId,runIds,accounts,disabled,onClose,onOpen,onStart}:{projectId:string;
  runIds:string[];accounts:KaggleAccount[];disabled:boolean;onClose:()=>void;onOpen:(id:string)=>void;onStart:(items:ConfiguredBatchItem[])=>Promise<void>}){
  const [values,setValues]=useState<RunExecutionConfiguration[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{let stopped=false;void Promise.all(runIds.map(id=>api<RunExecutionConfiguration>(`/projects/${projectId}/runs/${id}/configuration`)))
    .then(items=>{if(!stopped)setValues(items);}).catch(e=>{if(!stopped)setError(e.message);});return()=>{stopped=true;};},[projectId,runIds.join(',')]);
  function valid(item:RunExecutionConfiguration){const c=item.configuration;return !!c.account&&Number.isInteger(c.ttl_seconds)&&c.ttl_seconds>=180&&c.ttl_seconds<=43200
    &&c.execution_seconds>=1&&c.execution_seconds<=c.ttl_seconds-120&&c.output_bytes>=1
    &&(!item.limits.execution_seconds||c.execution_seconds<=item.limits.execution_seconds)
    &&(!item.limits.output_bytes||c.output_bytes<=item.limits.output_bytes)&&sameExperimentStrategy(c.search,item.planned_search)
    &&(!item.execution_requirements?.accelerators.length||item.execution_requirements.accelerators.includes(c.accelerator));}
  return <section className="run-comparison"><div className="panel-head"><h3>Chạy các run đã cấu hình</h3><button type="button" onClick={onClose}>Đóng</button></div>
    <p className="muted">Mỗi run giữ account, accelerator và budget riêng. Account hết chỗ sẽ đưa run vào hàng chờ.</p>
    {error&&<p role="alert" className="alert error">{error}</p>}
    {values.map(item=><details key={item.run_id} open><summary>Run {item.run_id.slice(0,8)} · {item.configuration.account||'chưa chọn account'}</summary>
      <fieldset disabled={disabled||busy||item.approved}><RunExecutionFields value={item.configuration} accounts={accounts} allowSearch={item.mode==='training_research'}
        onChange={part=>setValues(current=>current.map(value=>value.run_id===item.run_id?{...value,configuration:{...value.configuration,...part}}:value))}/></fieldset>
      {!valid(item)&&<p className="alert">Hoàn tất cấu hình hoặc <button onClick={()=>onOpen(item.run_id)}>mở run để lập lại proposal</button>.</p>}
    </details>)}
    <button className="primary" disabled={disabled||busy||values.length!==runIds.length||values.some(item=>!valid(item))} onClick={()=>{
      setBusy(true);void onStart(values.map(item=>({run_id:item.run_id,version:item.version,configuration:item.configuration})))
        .then(onClose).catch(e=>setError(e.message)).finally(()=>setBusy(false));}}>Duyệt và chạy batch</button>
  </section>;
}
