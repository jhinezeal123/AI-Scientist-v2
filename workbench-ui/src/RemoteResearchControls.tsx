import {useEffect,useState} from 'react';
import {agentCall} from './agentApi';
import {Flow,workflowBase} from './projectWorkflows';
import WorkflowHumanStep from './WorkflowHumanStep';

/** Scoped remote controls use the same saved grants and human gates. */
export default function RemoteResearchControls({projectId}:{projectId:string}){
  const [flows,setFlows]=useState<Flow[]>([]),[flow,setFlow]=useState<Flow|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const base=workflowBase(projectId);
  useEffect(()=>{let stopped=false;agentCall<Flow[]>(base).then(async rows=>{if(stopped)return;setFlows(rows);if(rows[0])setFlow(await agentCall<Flow>(base+'/'+rows[0].id));}).catch(e=>{if(!stopped)setError(e.message);});return()=>{stopped=true;};},[projectId]);
  useEffect(()=>{if(!flow)return;let stopped=false;const timer=setInterval(()=>void agentCall<Flow>(base+'/'+flow.id).then(value=>{if(!stopped)setFlow(value);}).catch(e=>{if(!stopped)setError(e.message);}),2000);return()=>{stopped=true;clearInterval(timer);};},[projectId,flow?.id]);
  async function command(path:string,body?:unknown){setBusy(true);setError('');try{setFlow(await agentCall<Flow>(path,'POST',body));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <section className="panel"><h2>Điều khiển project</h2><p className="muted">Cấu hình tại Workflow của project trên máy chủ. Thiết bị này điều khiển cùng lượt nghiên cứu đã lưu.</p>
    {!flows.length&&<p>Project chưa có cấu hình workflow.</p>}
    {!!flows.length&&<label>Lượt nghiên cứu<select value={flow?.id||''} onChange={e=>void agentCall<Flow>(base+'/'+e.target.value).then(setFlow).catch(e=>setError(e.message))}>{flows.map(f=><option key={f.id} value={f.id}>{f.spec.goal}</option>)}</select></label>}
    {flow&&<><p>{flow.state.status} · {flow.state.stage}</p><div className="actions"><button disabled={busy||flow.state.status!=='PAUSED'} onClick={()=>void command(base+'/'+flow.id+'/start',{})}>Bắt đầu / Tiếp tục</button><button disabled={busy||!['RUNNING','WAITING'].includes(flow.state.status)} onClick={()=>void command(base+'/'+flow.id+'/pause',{})}>Dừng</button></div>
      {flow.inputs?.filter(i=>i.state==='PENDING').map(input=><WorkflowHumanStep key={input.id} input={input} disabled={busy||flow.state.status!=='WAITING'} answer={result=>void command(base+'/'+flow.id+'/inputs/'+input.id,{result})}/>)}</>}
    {error&&<p role="alert" className="alert error">{error}</p>}</section>;
}
