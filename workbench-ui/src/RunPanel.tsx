import {useCallback, useEffect, useState} from 'react';
import {api, History, Idea, Variant, Working} from './api';
import RunMonitorPanel from './RunMonitorPanel';

type RunDetail = {id:string;proposal_id:string;proposal_version:number;state:string;ready:boolean;error:string|null;coder_calls:number;deleted_at:string|null;can_delete:boolean;
  execution_mode:'ssh'|'legacy';working?:Working;
  can_retry:boolean;parent_run_id:string|null;
  variant:Variant|null;variant_parent_deleted_at:string|null;
  purpose:string;expected_outputs:string[];report_path:string|null;report_preview?:string;
  result_metric?:{name:string;direction:string;final_value:number;best_value:number};
  collection?:{phase:string;report_attempts:number;report_limit:number};
  identity:{account:string;username:string;kernel_ref:string;version?:number;session_id?:number;kernel_id?:number;script_version_id?:number;status?:string;submit_attempts:number}|null;
  code_sha256:string|null;artifacts:string[];attempts:{attempt:number;state:string;session_id:string|null;origin:'CODEX'|'REUSE';
    error:string|null;checks:{pass:boolean;errors:string[];checks:string[];limitations:string[]}|null}[]};

const newRequestId=()=>crypto.randomUUID().replaceAll('-','');

export default function RunPanel({projectId, selectedRunId, onSelect, runs, busy, onWorking, onStop, onReconcile, onRetry, onDelete, onRestore, onCreateVariant}: {
  projectId:string;selectedRunId:string;onSelect:(id:string)=>void;runs:History['runs'];busy:boolean;onWorking:(id:string,accelerator:string,ttl:number)=>Promise<void>;
  onStop:(id:string)=>Promise<void>;onReconcile:(id:string)=>Promise<void>;
  onRetry:(id:string)=>Promise<string|undefined>;onDelete:(id:string)=>Promise<void>;onRestore:(id:string)=>Promise<void>;
  onCreateVariant:(id:string,requestId:string,title:string,purpose:string,changeSummary:string)=>Promise<Idea|undefined>}) {
  const [showDeleted,setShowDeleted]=useState(false);
  const visible=runs.filter(run=>Boolean(run.deleted_at)===showDeleted);
  const deletedCount=runs.filter(run=>run.deleted_at).length;
  const [details,setDetails] = useState<RunDetail[]>([]);
  const [error,setError] = useState('');
  const [accelerator,setAccelerator] = useState('cpu');
  const [ttl,setTtl] = useState(1800);
  const [variantOpen,setVariantOpen]=useState(false);
  const [variantTitle,setVariantTitle]=useState('');
  const [variantPurpose,setVariantPurpose]=useState('');
  const [variantChanges,setVariantChanges]=useState('');
  const [variantRequestId,setVariantRequestId]=useState(newRequestId);
  const [variantAttempted,setVariantAttempted]=useState(false);
  const selectedId = visible.some(run => run.id===selectedRunId && !run.deleted_at) ? selectedRunId : null;
  const [observations,setObservations] = useState<Record<string,string>>({});
  const onObserved=useCallback((status:string) => {
    if (!selectedId)return;
    setObservations(old => old[selectedId]===status ? old : {...old,[selectedId]:status});
  },[selectedId]);
  const labels:Record<string,string> = {
    APPROVED:'Sẵn sàng Working', IMPLEMENTING:'Đang tạo code', PREFLIGHT:'Sẵn sàng Working',
    SUBMITTING:'Đang gửi Kaggle', UNKNOWN:'Cần đối soát', FAILED:'Có lỗi',
    REMOTE_RUNNING:'Kaggle đang chạy', REMOTE_SUCCEEDED:'Kaggle hoàn tất',
    REMOTE_FAILED:'Kaggle có lỗi', COMPLETED:'Hoàn tất',COLLECTING:'Đang hoàn tất kết quả',RUNNING:'Kaggle đang chạy',QUEUED:'Đang xếp hàng',STARTING:'Đang mở Kaggle',
    WORKING:'Đang Working',STOPPING:'Đang dừng Kaggle',CANCELLED:'Đã dừng',
  };
  function editVariant(setter:(value:string)=>void,value:string) {
    setter(value);
    if (variantAttempted) {setVariantRequestId(newRequestId());setVariantAttempted(false);}
  }
  function resetVariant() {
    setVariantTitle('');setVariantPurpose('');setVariantChanges('');setVariantRequestId(newRequestId());setVariantAttempted(false);
  }
  useEffect(()=>{setVariantOpen(false);resetVariant();},[selectedRunId]);
  useEffect(() => {
    let cancelled = false;
    // A fresh history state (including T08 COMPLETED) supersedes earlier local observations.
    setObservations({});
    Promise.all(runs.map(run => api<RunDetail>(`/projects/${projectId}/runs/${run.id}`)))
      .then(items => {if (!cancelled) {setDetails(items);setError('');}})
      .catch(e => {if (!cancelled) setError(e.message);});
    return () => {cancelled = true;};
  }, [projectId,runs]);
  return <section className="panel run-panel"><div className="panel-head"><h2>Lần chạy của project</h2>
    <button type="button" disabled={busy} onClick={()=>{setShowDeleted(!showDeleted);onSelect('');}}>
      {showDeleted ? 'Run đã lưu' : `Đã xóa (${deletedCount})`}</button>
    {!!visible.length && <span className="muted">{visible.length} run</span>}</div>
    {!visible.length && <p className="empty">{showDeleted ? 'Chưa có run đã xóa.' : 'Chưa có lần chạy. Lập và duyệt proposal ở Idea để tạo run.'}</p>}
    {error && <p role="alert">{error}</p>}
    {!!visible.length && <div className="run-cards" aria-label={showDeleted ? 'Run đã xóa' : 'Danh sách run'}>
      {visible.map(run => <button type="button" key={run.id} disabled={!!run.deleted_at && busy}
        aria-label={run.deleted_at ? `Khôi phục Run ${run.id.slice(0,8)}` : undefined}
        className={`run-card ${selectedId === run.id ? 'selected' : ''}`}
        aria-expanded={selectedId === run.id} aria-controls="run-detail"
        onClick={() => run.deleted_at ? void onRestore(run.id) : onSelect(selectedId === run.id ? '' : run.id)}>
        <span className="run-alias">Run {run.id.slice(0,8)}</span>
        <span className="run-card-status" data-state={observations[run.id] || run.state}>
          <span className="run-status-dot" aria-hidden="true"/>{run.deleted_at ? 'Đã xóa · bấm để khôi phục' : run.state === 'COLLECTING' && details.find(item => item.id === run.id)?.collection?.phase === 'retry_exhausted'
            ? 'Report cần xử lý' : labels[observations[run.id] || run.state] || observations[run.id] || run.state}
        </span>
      </button>)}
    </div>}
    {!!visible.length && !selectedId && !showDeleted && <p className="muted run-hint">Chọn một run để xem chi tiết và thao tác.</p>}
    {selectedId && !details.some(run => run.id === selectedId) && !error && <p role="status" className="muted">Đang tải chi tiết run…</p>}
    {details.filter(run => run.id === selectedId).map(run => <article className="resource run-detail" id="run-detail" key={run.id} aria-label={`Chi tiết Run ${run.id.slice(0,8)}`}>
      <div className="panel-head"><h3>Run {run.id.slice(0,8)}</h3>
        <div className="actions"><button type="button" className="danger-button" disabled={busy || !run.can_delete}
          title={run.can_delete ? 'Có thể khôi phục trong mục Đã xóa' : 'Dừng hoặc đối soát Kaggle trước khi xóa'}
          onClick={()=>void onDelete(run.id)}>Xóa run</button>
        <button type="button" onClick={() => onSelect('')}>Đóng chi tiết</button></div></div>
      <div className="panel-head"><code className="source-id">{run.id}</code><span className="state-tag">{observations[run.id] || run.state}</span></div>
      {run.state === 'APPROVED' && <p>Proposal đã duyệt. Bắt đầu Working để agent viết và chạy code trực tiếp trong Kaggle.</p>}
      {run.error && <p role="alert" className="alert error">{run.error}</p>}
      {!run.identity && !run.working && ['APPROVED','FAILED','PREFLIGHT'].includes(run.state) && <div className="context stack">
        <h3>Working</h3>
        <p>Mở phiên Kaggle, viết và chạy code qua SSH, lưu kết quả rồi dừng phiên.</p>
        <label>Phần cứng<select value={accelerator} disabled={busy} onChange={e=>setAccelerator(e.target.value)}>
          <option value="cpu">CPU</option><option value="NvidiaT4">GPU · T4 x2</option>
          <option value="TpuV5E8">TPU · v5e-8</option><option value="TpuV6E8">TPU · v6e-8</option>
        </select></label>
        <label>Thời gian tối đa của phiên (phút)<input type="number" min="1" max="720" step="1" value={ttl/60}
          disabled={busy} onChange={e=>setTtl(Number(e.target.value)*60)}/></label>
        <button className="primary" disabled={busy || !Number.isInteger(ttl) || ttl<60 || ttl>43200}
          onClick={()=>void onWorking(run.id,accelerator,ttl)}>Bắt đầu Working</button>
      </div>}
      {run.working && <div className="context"><h3>Phiên Working</h3>
        <p>{run.working.accelerator === 'NvidiaT4' ? 'GPU · T4 x2' : run.working.accelerator} · tối đa {run.working.ttl_seconds/60} phút</p>
        <p role="status">{run.working.stop_confirmed ? 'Backend đã xác nhận Kaggle dừng.'
          : run.state==='STARTING' ? 'Đang mở Kaggle và kết nối SSH…'
          : run.state==='STOPPING' ? 'Đang chờ xác nhận Kaggle dừng. Kết quả chưa được đánh dấu hoàn tất.'
          : run.working.phase==='collecting' ? 'Đang lưu và kiểm tra kết quả trước khi dừng Kaggle.'
          : 'Agent đang viết và thực thi code trên Kaggle qua cùng một kết nối SSH.'}</p>
        {run.working.notebook_ref && <a href={`https://www.kaggle.com/code/${run.working.notebook_ref}`} target="_blank" rel="noreferrer">Mở phiên trên Kaggle ↗</a>}
        {!run.working.stop_confirmed && <p><button onClick={()=>void onStop(run.id)}>
          {run.state==='STOPPING' ? 'Yêu cầu dừng / kiểm tra lại' : 'Dừng Working'}</button></p>}
        {run.working.summary && <><h3>Tóm tắt công việc</h3><p>{run.working.summary.summary}</p></>}
      </div>}
      <p className="muted">Mỗi lượt do bạn yêu cầu. Không giới hạn tổng số lượt Working.</p>
      {run.parent_run_id && <p className="muted">Tạo từ Run {run.parent_run_id.slice(0,8)} · dùng cùng proposal đã duyệt.</p>}
      {run.variant && <div className="context">
        <h3>Biến thể từ kết quả đã lưu</h3><p>Run cha: {run.variant.parent_run_id}</p>
        {run.variant_parent_deleted_at
          ? <div className="stack"><p role="status" className="muted">Run cha đang ẩn. Khôi phục run cha để mở lại.</p>
            <button type="button" disabled={busy} onClick={()=>void onRestore(run.variant!.parent_run_id).then(()=>onSelect(run.variant!.parent_run_id))}>Khôi phục và mở Run cha</button></div>
          : <button type="button" onClick={()=>onSelect(run.variant!.parent_run_id)}>Mở Run cha</button>}
        <p><strong>Mục đích mới: </strong>{run.variant.purpose}</p>
        <p><strong>Thay đổi: </strong>{run.variant.change_summary}</p>
        <small className="muted">Proposal {run.variant.parent_proposal_id} · v{run.variant.parent_proposal_version} · context {run.variant.baseline.parent.context_sha256}</small>
      </div>}
      {run.can_retry && <div className="stack"><button disabled={busy} onClick={() => void onRetry(run.id).then(id => {
        if (id)onSelect(id);
      })}>Tạo lượt Working mới</button><small className="muted">Dùng cùng proposal đã duyệt và tham khảo kết quả cũ. Bấm Working để bắt đầu lượt mới.</small></div>}
      {run.collection && <p className="muted">Report: {run.collection.report_attempts}/{run.collection.report_limit} lượt đã cấp.</p>}
      {run.state === 'COLLECTING' && run.collection?.phase === 'retry_exhausted' && <p role="alert" className="alert error">Outputs đã được xác minh. Report đã hết lượt thử cho phép; cần xử lý lỗi và duyệt thêm lượt report để tiếp tục.</p>}
      {run.state === 'SUBMITTING' && <p role="status">Đang gửi notebook qua MCP và xác minh phiên chạy…</p>}
      {run.identity && <div className="context"><h3>Notebook trên Kaggle</h3>
        <a href={`https://www.kaggle.com/code/${run.identity.kernel_ref}${run.identity.script_version_id ? `?scriptVersionId=${run.identity.script_version_id}` : ''}`} target="_blank" rel="noreferrer">{run.identity.kernel_ref} ↗</a>
        <p>Account: {run.identity.username} · Version: {run.identity.version ?? 'chưa xác minh'}</p>
        <code className="source-id">Kernel: {run.identity.kernel_id ?? '?'} · Session: {run.identity.session_id ?? '?'} · Script version: {run.identity.script_version_id ?? '?'}</code>
        {run.identity.status && <p>Trạng thái Kaggle: {run.identity.status}</p>}
        {run.state === 'UNKNOWN' && <p>Chưa biết chắc kết quả gửi. Đối soát chỉ đọc notebook đã gửi; không tạo lần gửi mới.</p>}
        <button disabled={busy || run.state === 'SUBMITTING'} onClick={() => void onReconcile(run.id)}>{run.state === 'UNKNOWN' ? 'Đối soát lần gửi' : 'Cập nhật trạng thái từ Kaggle'}</button>
        {['REMOTE_SUCCEEDED','COLLECTING'].includes(observations[run.id] || run.state) && <p className="muted">Run thuộc phiên bản cũ. Kết quả đã lưu vẫn có thể xem; tạo lượt Working mới để tiếp tục.</p>}
      </div>}
      <div className="context"><h3>Mục tiêu</h3><p>{run.purpose}</p><code className="source-id">Proposal {run.proposal_id} · v{run.proposal_version}</code>
        {!!run.expected_outputs?.length && <p className="muted">Đầu ra đã duyệt: {run.expected_outputs.join(' · ')}</p>}
        {run.result_metric && <p>Kết quả đo được: {run.result_metric.name} · {run.result_metric.direction} · cuối {run.result_metric.final_value} · tốt nhất {run.result_metric.best_value}</p>}
      </div>
      {run.identity?.session_id && <RunMonitorPanel key={run.id} projectId={projectId} runId={run.id} onObserved={onObserved}/>}
      {run.working && <RunMonitorPanel key={run.id} projectId={projectId} runId={run.id} onObserved={onObserved} working/>}
      {run.code_sha256 && <code className="source-id">Code SHA256 {run.code_sha256}</code>}
      {!!run.artifacts.length && <h3><a className="artifacts-page-link"
        href={`/?page=artifacts&project=${projectId}&run=${run.id}`}>
        Artifacts đã lưu · {run.artifacts.length} file ↗
      </a></h3>}
      {run.report_path === 'report.md' && <><h3>Report</h3><a href={`/api/projects/${projectId}/runs/${run.id}/artifacts/report.md`} target="_blank" rel="noreferrer">Mở report ↗</a>
        {run.report_preview && <pre className="report-preview">{run.report_preview}</pre>}</>}
      {['COMPLETED','FAILED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED'].includes(run.state)
        && !run.deleted_at && (run.execution_mode!=='ssh' || run.working?.stop_confirmed) && <div className="context stack">
          {!variantOpen ? <button type="button" disabled={busy} onClick={()=>setVariantOpen(true)}>Tạo biến thể idea</button>
            : <form className="stack" onSubmit={event=>{event.preventDefault();setVariantAttempted(true);
              void onCreateVariant(run.id,variantRequestId,variantTitle.trim(),variantPurpose.trim(),variantChanges.trim()).then(idea=>{
                if (idea) {setVariantOpen(false);resetVariant();}
              });}}>
              <h3>Tạo biến thể idea</h3><p>Run cha: {run.id}</p>
              <p><strong>Mục tiêu cũ: </strong>{run.purpose}</p>
              <label>Tiêu đề<input required maxLength={80} value={variantTitle} disabled={busy}
                onChange={event=>editVariant(setVariantTitle,event.target.value)}/></label>
              <label>Mục đích mới<textarea required rows={3} maxLength={20000} value={variantPurpose} disabled={busy}
                onChange={event=>editVariant(setVariantPurpose,event.target.value)}/></label>
              <label>Thay đổi so với run gốc<textarea required rows={4} maxLength={20000} value={variantChanges} disabled={busy}
                onChange={event=>editVariant(setVariantChanges,event.target.value)}/></label>
              <div className="actions"><button className="primary" disabled={busy || !variantTitle.trim() || !variantPurpose.trim() || !variantChanges.trim()}>Lưu idea biến thể</button>
                <button type="button" disabled={busy} onClick={()=>{setVariantOpen(false);resetVariant();}}>Hủy</button></div>
            </form>}
        </div>}
    </article>)}
  </section>;
}
