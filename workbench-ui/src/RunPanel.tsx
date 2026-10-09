import {useCallback,useEffect,useState} from 'react';
import {api,History,Variant,Working,RunMode,RunOutput,Resource,ResearchPlan,ResearchPipeline} from './api';
import RunMonitorPanel from './RunMonitorPanel';
import OutputToLibrary from './OutputToLibrary';
import ResearchScope from './ResearchScope';
import ProjectRunTree from './ProjectRunTree';

type RunDetail={id:string;title:string;state:string;error:string|null;deleted_at:string|null;can_delete:boolean;
  mode:RunMode;desired_output:string;parent_run_id:string|null;variant:Variant|null;
  tags:string[];run_model:'single'|'legacy';purpose:string;proposal_id:string;proposal_version:number;expected_outputs:string[];
  execution_mode:'ssh'|'legacy';working?:Working;output?:RunOutput;
  research?:{plan:ResearchPlan;pipeline:ResearchPipeline|null};
  report_path:string|null;report_preview?:string;artifacts:string[];
  identity:{kernel_ref:string;username:string;status?:string;session_id?:number}|null;
  result_metric?:{name:string;direction:string;final_value:number;best_value:number}};

export default function RunPanel({projectId,selectedRunId,onSelect,runs,busy,onWorking,onStop,onReconcile,
  onDelete,onRestore,onBranch,onOutputCopied}:{projectId:string;selectedRunId:string;onSelect:(id:string)=>void;
  runs:History['runs'];busy:boolean;onWorking:(id:string,accelerator:string,ttl:number)=>Promise<void>;
  onStop:(id:string)=>Promise<void>;onReconcile:(id:string)=>Promise<void>;onDelete:(id:string)=>Promise<void>;
  onRestore:(id:string)=>Promise<void>;onBranch:(id:string,mode:RunMode)=>void;onOutputCopied:(resource:Resource)=>void}) {
  const [showDeleted,setShowDeleted]=useState(false),[detail,setDetail]=useState<RunDetail|null>(null),[error,setError]=useState('');
  const [accelerator,setAccelerator]=useState('cpu'),[ttl,setTtl]=useState(1800);
  const visible=runs.filter(run=>Boolean(run.deleted_at)===showDeleted);
  const selectedId=visible.some(run=>run.id===selectedRunId && !run.deleted_at) ? selectedRunId : null;
  const parent=detail?.variant?.parent_run_id || detail?.parent_run_id;
  const [observed,setObserved]=useState('');
  const onObserved=useCallback((status:string)=>setObserved(status),[]);
  useEffect(()=>{
    let cancelled=false;setObserved('');
    if(!selectedId){setDetail(null);return;}
    api<RunDetail>(`/projects/${projectId}/runs/${selectedId}`).then(item=>{
      if(!cancelled){setDetail(item);setError('');}
    }).catch(e=>{if(!cancelled)setError(e.message);});
    return ()=>{cancelled=true;};
  },[projectId,selectedId,runs]);
  const run=detail?.id===selectedId ? detail : null;
  const canBranch=!!run && ['COMPLETED','FAILED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED'].includes(run.state)
    && (run.execution_mode!=='ssh' || run.working?.stop_confirmed);
  return <section className="panel run-panel"><div className="panel-head"><h2>Cây run của project</h2>
    <span className="muted">{visible.length} run</span>
    <a href={`/?page=run-tree&project=${projectId}`} target="_blank" rel="noreferrer">Mở cây toàn màn hình ↗</a>
    {runs.some(item=>item.deleted_at) && <button type="button" onClick={()=>{setShowDeleted(!showDeleted);onSelect('');}}>
      {showDeleted ? 'Cây hiện hành' : 'Run đã xóa trước đây'}</button>}</div>
    {!visible.length ? <p className="empty">Chưa có run. Lập và duyệt proposal trong Idea để tạo draft.</p>
      : <ProjectRunTree runs={visible} selectedId={selectedId} onSelect={id=>{
        const item=visible.find(item=>item.id===id);
        if(item?.deleted_at)void onRestore(id);else onSelect(id);
      }}/>}
    {error && <p role="alert" className="alert error">{error}</p>}
    {selectedId && !run && !error && <p role="status">Đang tải run…</p>}
    {run && <article className="resource run-detail" id="run-detail" aria-label={`Chi tiết ${run.title}`}>
      <div className="panel-head"><h3>{run.title || 'Run '+run.id.slice(0,8)}</h3><div className="actions">
        <button className="danger-button" type="button" disabled={busy || !run.can_delete}
          title={run.can_delete ? 'Xóa node lá và các file của run' : 'Chỉ xóa node lá đã dừng, không có idea con đang chờ'}
          onClick={()=>{if(window.confirm('Xóa run này và toàn bộ file đã lưu của run?'))void onDelete(run.id);}}>Xóa node lá</button>
        <button type="button" onClick={()=>onSelect('')}>Đóng chi tiết</button></div></div>
      <div className="panel-head"><code className="source-id">{run.id}</code><span className="state-tag">{observed || run.state}</span></div>
      <p className="mode-tag" data-mode={run.mode}>{run.mode==='etc' ? 'Etc' : parent ? 'Improve · Training/Research' : 'Draft · Training/Research'}</p>
      {!!run.tags.length && <p className="run-tags">{run.tags.map(tag=><span key={tag}>{tag}</span>)}</p>}
      {run.error && <p role="alert" className="alert error">{run.error}</p>}
      {canBranch && <div className="context branch-actions"><h3>Tạo run con</h3>
        <p>Chọn cách thực hiện rồi nhập idea và duyệt proposal cho một phiên SSH mới.</p>
        <div className="actions"><button type="button" disabled={busy} onClick={()=>onBranch(run.id,'training_research')}>Improve</button>
          <button type="button" disabled={busy} onClick={()=>onBranch(run.id,'etc')}>Etc</button></div></div>}
      {parent && <p>Run cha: <button type="button" onClick={()=>onSelect(parent)}>{runs.find(item=>item.id===parent)?.title || parent.slice(0,8)}</button></p>}
      {!run.identity && !run.working && ['APPROVED','FAILED','PREFLIGHT'].includes(run.state) && <div className="context stack">
        <h3>Working</h3><p>Một run, một phiên SSH. Agent tự sửa lỗi trong run này. Bạn chủ động tạo các phiên bản improve.</p>
        <label>Phần cứng<select value={accelerator} disabled={busy} onChange={e=>setAccelerator(e.target.value)}>
          <option value="cpu">CPU</option><option value="NvidiaT4">GPU · T4 x2</option>
          <option value="TpuV5E8">TPU · v5e-8</option><option value="TpuV6E8">TPU · v6e-8</option></select></label>
        <label>Thời gian tối đa của phiên (phút)<input type="number" min={1} max={720} step={1} value={ttl/60}
          disabled={busy} onChange={e=>setTtl(Number(e.target.value)*60)}/></label>
        <button className="primary" disabled={busy || !Number.isInteger(ttl) || ttl<60 || ttl>43200}
          onClick={()=>void onWorking(run.id,accelerator,ttl)}>Bắt đầu Working</button></div>}
      {run.working && <div className="context"><h3>Phiên Working</h3>
        <p>{run.working.accelerator==='NvidiaT4' ? 'GPU · T4 x2' : run.working.accelerator} · tối đa {run.working.ttl_seconds/60} phút</p>
        <p role="status">{run.working.stop_confirmed ? 'Backend đã xác nhận Kaggle dừng.' : run.state==='STARTING'
          ? 'Đang mở phiên SSH…' : run.state==='STOPPING' ? 'Đang chờ xác nhận Kaggle dừng.'
          : run.working.phase.startsWith('research_') ? 'Đang tạo các đầu ra bạn đã chọn.' : 'Agent đang làm việc trong phiên SSH của run.'}</p>
        {run.working.notebook_ref && <a href={`https://www.kaggle.com/code/${run.working.notebook_ref}`} target="_blank" rel="noreferrer">Mở phiên Kaggle ↗</a>}
        {!run.working.stop_confirmed && <p><button onClick={()=>void onStop(run.id)}>Dừng Working / kiểm tra lại</button></p>}
      </div>}
      {run.mode!=='etc' && run.research && <div className="context"><h3>Đầu ra đã chọn</h3>
        <ResearchScope plan={run.research.plan} pipeline={run.research.pipeline} projectId={projectId} runId={run.id}/></div>}
      <div className="context"><h3>Mục tiêu</h3><p>{run.purpose}</p>
        <code className="source-id">Proposal {run.proposal_id} · v{run.proposal_version}</code>
        {run.mode==='etc' && <><h3>Đầu ra mong muốn</h3><pre>{run.desired_output}</pre></>}
        {!!run.expected_outputs.length && <p className="muted">{run.expected_outputs.join(' · ')}</p>}
        {run.result_metric && <p>{run.result_metric.name}: {run.result_metric.final_value}</p>}
      </div>
      {run.working && <RunMonitorPanel key={run.id} projectId={projectId} runId={run.id} onObserved={onObserved} working/>}
      {run.identity && !run.working && <div className="context"><h3>Phiên đã lưu từ phiên bản trước</h3>
        <a href={`https://www.kaggle.com/code/${run.identity.kernel_ref}`} target="_blank" rel="noreferrer">Notebook trên Kaggle ↗</a>
        <button disabled={busy} onClick={()=>void onReconcile(run.id)}>Đối soát trạng thái</button>
        {run.identity.session_id && <RunMonitorPanel key={run.id} projectId={projectId} runId={run.id} onObserved={onObserved}/>}</div>}
      {!!run.artifacts.length && <h3><a className="artifacts-page-link" href={`/?page=artifacts&project=${projectId}&run=${run.id}`}>
        Artifacts đã lưu · {run.artifacts.length} file ↗</a></h3>}
      {run.mode==='etc' && run.output && <div className="context output-panel"><h3>Output</h3>
        {run.output.directory && <code className="source-id">{run.output.directory}</code>}
        {run.output.summary && <pre className="report-preview">{run.output.summary}</pre>}
        {run.output.status==='partial' && <p className="alert error">Chưa hoàn tất. File đã thu vẫn có thể tải.</p>}
        {!!run.output.files.length && <a href={`/?page=artifacts&view=output&project=${projectId}&run=${run.id}`}>Mở các file Output ↗</a>}
        <OutputToLibrary key={`${projectId}:${run.id}`} projectId={projectId} runId={run.id} output={run.output} onCopied={onOutputCopied}/></div>}
      {run.mode!=='etc' && run.report_path==='report.md' && <div className="context"><h3>Report</h3>
        <a href={`/api/projects/${projectId}/runs/${run.id}/artifacts/report.md`} target="_blank" rel="noreferrer">Mở report ↗</a>
        {run.report_preview && <pre className="report-preview">{run.report_preview}</pre>}</div>}
    </article>}
  </section>;
}
