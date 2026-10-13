import {useCallback,useEffect,useState} from 'react';
import {api,Benchmark,History,Variant,Working,RunMode,RunOutput,Resource,ResearchPlan,ResearchPipeline,KaggleAccount} from './api';
import WorkflowHumanStep from './WorkflowHumanStep';
import {Flow,HumanInput} from './projectWorkflows';
import {ProjectConfiguration} from './projectConfiguration';
import ProjectRunConfiguration from './ProjectRunConfiguration';
import RunConfigurationEditor from './RunConfigurationEditor';
import BatchRunConfiguration,{ConfiguredBatchItem} from './BatchRunConfiguration';
import RunMonitorPanel from './RunMonitorPanel';
import OutputToLibrary from './OutputToLibrary';
import ResearchScope from './ResearchScope';
import ProjectRunTree from './ProjectRunTree';
import RunBoard from './RunBoard';
import RunComparison from './RunComparison';

type RunDetail={id:string;title:string;state:string;error:string|null;deleted_at:string|null;can_delete:boolean;
  mode:RunMode;desired_output:string;parent_run_id:string|null;variant:Variant|null;
  tags:string[];run_model:'single'|'legacy';purpose:string;proposal_id:string;proposal_version:number;expected_outputs:string[];
  benchmark?:Benchmark|null;execution_mode:'ssh'|'legacy';working?:Working;output?:RunOutput;
  research?:{plan:ResearchPlan;pipeline:ResearchPipeline|null};
  report_path:string|null;report_preview?:string;artifacts:string[];
  identity:{kernel_ref:string;username:string;status?:string;session_id?:number}|null;
  result_metric?:{name:string;direction:string;final_value:number;best_value:number}};

export default function RunPanel({projectId,selectedRunId,onSelect,runs,busy,onStop,onResumeQueue,onReconcile,
  onDelete,onRestore,onBranch,onBatch,onOutputCopied,workflow,onWorkflowAnswer,onConfigurationSaved,onConfigured,onReplanned}:{projectId:string;selectedRunId:string;onSelect:(id:string)=>void;
  onConfigured:()=>void;onReplanned:(ideaId:string)=>void;
  onConfigurationSaved:(value:ProjectConfiguration)=>void;workflow?:Flow;onWorkflowAnswer:(input:HumanInput,result:unknown)=>Promise<void>;
  runs:History['runs'];busy:boolean;
  onStop:(id:string)=>Promise<void>;onResumeQueue:(id:string)=>Promise<void>;onReconcile:(id:string)=>Promise<void>;onDelete:(id:string)=>Promise<void>;
  onRestore:(id:string)=>Promise<void>;onBranch:(id:string,mode:RunMode)=>void;
  onBatch:(items:ConfiguredBatchItem[])=>Promise<void>;
  onOutputCopied:(resource:Resource)=>void}) {
  const [showDeleted,setShowDeleted]=useState(false),[detail,setDetail]=useState<RunDetail|null>(null),[error,setError]=useState('');
  const [configurationRevision,setConfigurationRevision]=useState(0);
  const [accounts,setAccounts]=useState<KaggleAccount[]>([]);
  const [comparison,setComparison]=useState<string[]>([]);
  const [benchmarks,setBenchmarks]=useState<Benchmark[]>([]),[benchmarkId,setBenchmarkId]=useState('');
  useEffect(()=>{let cancelled=false;api<Benchmark[]>(`/projects/${projectId}/benchmarks`).then(items=>{if(!cancelled)setBenchmarks(items);}).catch(e=>{if(!cancelled)setError(e.message);});return ()=>{cancelled=true;};},[projectId,runs.length,runs.map(run=>run.state).join(',')]);
  const [batchIds,setBatchIds]=useState<string[]>([]);
  useEffect(()=>{let cancelled=false;api<KaggleAccount[]>('/kaggle/accounts').then(items=>{if(!cancelled)setAccounts(items);})
    .catch(e=>{if(!cancelled)setError(e.message);});return()=>{cancelled=true;};},[]);
  const ownedRun=!!workflow&&workflow.state.run_id===selectedRunId;
  const runInputs=workflow?.inputs?.filter(i=>i.state==='PENDING'&&!['ideation','literature','approval'].includes(i.stage))||[];
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
  useEffect(()=>{
    if(run?.id)document.getElementById('run-detail')?.scrollIntoView({block:'start',behavior:'smooth'});
  },[run?.id]);
  const canBranch=!!run && ['COMPLETED','FAILED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED'].includes(run.state)
    && (run.execution_mode!=='ssh' || run.working?.stop_confirmed);
  return <section className="panel run-panel"><div className="panel-head"><h2>Cây run của project</h2>
    <span className="muted">{visible.length} run</span>
    <a href={`/?page=run-tree&project=${projectId}`} target="_blank" rel="noreferrer">Mở cây toàn màn hình ↗</a>
    {runs.some(item=>item.deleted_at) && <button type="button" onClick={()=>{setShowDeleted(!showDeleted);onSelect('');}}>
      {showDeleted ? 'Cây hiện hành' : 'Run đã xóa trước đây'}</button>}</div>
    <ProjectRunConfiguration key={configurationRevision} projectId={projectId} disabled={busy} onSaved={onConfigurationSaved}/>
    {!!benchmarks.length&&<section className="run-comparison"><label>Biểu đồ MLflow theo benchmark<select value={benchmarkId} onChange={e=>setBenchmarkId(e.target.value)}><option value="">Chọn benchmark</option>{benchmarks.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select></label></section>}
    {benchmarkId && <RunComparison projectId={projectId} benchmarkId={benchmarkId} runIds={[]} onClose={()=>setBenchmarkId('')} onOpen={onSelect}/>}
    <RunBoard runs={visible} selectedId={selectedId} onSelect={onSelect} onCompare={ids=>setComparison(ids)}
      onBatch={ids=>{if(workflow&&ids.includes(workflow.state.run_id||'')){setError('Run này được điều phối qua workflow. Duyệt tại bước chờ bên dưới.');return;}setBatchIds(ids);}}/>
    {batchIds.length>=2&&<BatchRunConfiguration projectId={projectId} runIds={batchIds} accounts={accounts} disabled={busy}
      onClose={()=>setBatchIds([])} onOpen={id=>{setBatchIds([]);onSelect(id);}} onStart={onBatch}/>}
    {workflow&&runInputs.filter(input=>input.prompt.kind!=='run_configuration').map(input=><WorkflowHumanStep key={input.id} input={input} disabled={busy||workflow.state.status!=='WAITING'} answer={result=>void onWorkflowAnswer(input,result)}/>)}
    {comparison.length>=2 && <RunComparison projectId={projectId} runIds={comparison}
      onClose={()=>setComparison([])} onOpen={onSelect}/>}
    {!visible.length ? <p className="empty">Chưa có run. Lập và duyệt proposal trong Idea để tạo draft.</p>
      : <ProjectRunTree runs={visible} selectedId={selectedId} onSelect={id=>{
        const item=visible.find(item=>item.id===id);
        if(item?.deleted_at)void onRestore(id);else onSelect(id);
      }}/>}
    {error && <p role="alert" className="alert error">{error}</p>}
    {selectedId && !run && !error && <p role="status">Đang tải run…</p>}
    {run && <article className="resource run-detail" id="run-detail" aria-label={`Chi tiết ${run.title}`}>
      <div className="panel-head"><h3>{run.title || 'Run '+run.id.slice(0,8)}</h3><div className="actions">
        <button className="danger-button" type="button" disabled={busy || ownedRun || !run.can_delete}
          title={run.can_delete ? 'Xóa node lá và các file của run' : 'Chỉ xóa node lá đã dừng, không có idea con đang chờ'}
          onClick={()=>{if(window.confirm('Xóa run này và toàn bộ file đã lưu của run?'))void onDelete(run.id);}}>Xóa node lá</button>
        <button type="button" onClick={()=>onSelect('')}>Đóng chi tiết</button></div></div>
      <div className="panel-head"><code className="source-id">{run.id}</code><span className="state-tag">{observed || run.state}</span></div>
      <p className="mode-tag" data-mode={run.mode}>{run.mode==='benchmark' ? 'Benchmark' : run.mode==='etc' ? 'Etc' : parent ? 'Improve · Training/Research' : 'Draft · Training/Research'}</p>
      {run.mode==='benchmark' && <div className="context"><h3>Dataset Kaggle public</h3>
        <p>Title: {('Benchmark: '+run.purpose.trim().split(/\s+/).join(' ')).slice(0,50).trimEnd()}</p>
        <p>Slug: <code>ais-benchmark-{run.id}</code></p>
        <small>Kiểm tra tên hợp lệ và chưa tồn tại trên account trước khi mở phiên Kaggle; kiểm tra lại trước khi upload. Không ghi đè dataset.</small></div>}
      {!!run.tags.length && <p className="run-tags">{run.tags.map(tag=><span key={tag}>{tag}</span>)}</p>}
      {run.error && <p role="alert" className="alert error">{run.error}</p>}
      {canBranch && <div className="context branch-actions"><h3>Tạo run con</h3>
        <p>Chọn cách thực hiện rồi nhập idea và duyệt proposal cho một phiên SSH mới.</p>
        <div className="actions"><button type="button" disabled={busy} onClick={()=>onBranch(run.id,'training_research')}>Improve</button>
          <button type="button" disabled={busy} onClick={()=>onBranch(run.id,'etc')}>Etc</button></div></div>}
      {parent && <p>Run cha: <button type="button" onClick={()=>onSelect(parent)}>{runs.find(item=>item.id===parent)?.title || parent.slice(0,8)}</button></p>}
      {!run.identity&&!run.working&&['APPROVED','FAILED','PREFLIGHT'].includes(run.state)&&(!ownedRun||workflow!.spec.run_setup==='per_run'&&workflow!.spec.require_run_approval)&&
        <RunConfigurationEditor key={run.id} projectId={projectId} runId={run.id} disabled={busy}
          canStart={!ownedRun||workflow!.state.status==='WAITING'&&runInputs.some(input=>input.prompt.kind==='run_configuration')}
          onChanged={()=>{setConfigurationRevision(n=>n+1);onConfigured();}} onReplanned={onReplanned}/>}
      {ownedRun&&!run.working&&(workflow!.spec.run_setup!=='per_run'||!workflow!.spec.require_run_approval)&&<div className="context"><h3>Môi trường đã được cấp trước</h3><p>{workflow!.spec.account} · {workflow!.spec.accelerator} · {workflow!.spec.ttl_seconds/60} phút</p></div>}
      {run.working && <div className="context"><h3>Phiên Working</h3>
        <p>Account: {accounts.find(item=>item.account===run.working?.account)?.username || run.working.account || 'chưa rõ'}</p>
        <p>{run.working.accelerator==='NvidiaT4' ? 'GPU · T4 x2' : run.working.accelerator} · tối đa {run.working.ttl_seconds/60} phút</p>
        <p role="status">{run.working.stop_confirmed ? 'Backend đã xác nhận Kaggle dừng.' : run.state==='STARTING'
          ? 'Đang mở phiên SSH…' : run.state==='QUEUED' ? run.working.phase==='renewing_cookie' ? 'Cookie hết hạn. Đang tự đăng nhập trước khi tiếp tục run.' : run.working.phase==='blocked' ? 'Hàng chờ bị chặn; kiểm tra account rồi tiếp tục thủ công.' : 'Đang chờ account có chỗ trống (tối đa 2 session/account).'
          : run.state==='STOPPING' ? 'Đang chờ xác nhận Kaggle dừng.'
          : run.working.phase.startsWith('research_') ? 'Đang tạo các đầu ra bạn đã chọn.' : 'Agent đang làm việc trong phiên SSH của run.'}</p>
        {run.working.notebook_ref && <a href={`https://www.kaggle.com/code/${run.working.notebook_ref}`} target="_blank" rel="noreferrer">Mở phiên Kaggle ↗</a>}
        {!run.working.stop_confirmed && <p><button onClick={()=>void onStop(run.id)}>{run.state==='QUEUED'?'Hủy hàng chờ':'Dừng Working / kiểm tra lại'}</button>
          {run.state==='QUEUED' && run.working.phase==='blocked' && <button onClick={()=>void onResumeQueue(run.id)}>Tiếp tục hàng chờ</button>}</p>}
      </div>}
      {run.benchmark && <div className="context"><h3>Benchmark</h3><a href={run.benchmark.dataset.url} target="_blank" rel="noreferrer">{run.benchmark.title} · public · dataset v{run.benchmark.dataset.version}</a><p>{run.benchmark.definition.metric.name}: {run.benchmark.definition.metric.definition}</p><button type="button" onClick={()=>setBenchmarkId(run.benchmark!.id)}>Xem các run cùng benchmark</button></div>}
      {run.mode==='training_research' && run.research && <div className="context"><h3>Đầu ra đã chọn</h3>
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
      {['etc','benchmark'].includes(run.mode) && run.output && <div className="context output-panel"><h3>Output</h3>
        {run.output.directory && <code className="source-id">{run.output.directory}</code>}
        {run.output.summary && <pre className="report-preview">{run.output.summary}</pre>}
        {run.output.status==='partial' && <p className="alert error">Chưa hoàn tất. File đã thu vẫn có thể tải.</p>}
        {!!run.output.files.length && <a href={`/?page=artifacts&view=output&project=${projectId}&run=${run.id}`}>Mở các file Output ↗</a>}
        {run.mode==='etc' && <OutputToLibrary key={`${projectId}:${run.id}`} projectId={projectId} runId={run.id} output={run.output} onCopied={onOutputCopied}/>}</div>}
      {run.mode==='training_research' && run.report_path==='report.md' && <div className="context"><h3>Report</h3>
        <a href={`/api/projects/${projectId}/runs/${run.id}/artifacts/report.md`} target="_blank" rel="noreferrer">Mở report ↗</a>
        {run.report_preview && <pre className="report-preview">{run.report_preview}</pre>}</div>}
    </article>}
  </section>;
}
