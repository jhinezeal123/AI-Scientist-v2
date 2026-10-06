import {useCallback, useEffect, useState} from 'react';
import {api, History} from './api';
import RunMonitorPanel from './RunMonitorPanel';

type RunDetail = {id:string;proposal_id:string;proposal_version:number;state:string;ready:boolean;error:string|null;coder_budget:number;
  purpose:string;expected_outputs:string[];report_path:string|null;report_preview?:string;
  result_metric?:{name:string;direction:string;final_value:number;best_value:number};
  identity:{account:string;username:string;kernel_ref:string;version?:number;session_id?:number;kernel_id?:number;script_version_id?:number;status?:string;submit_attempts:number}|null;
  code_sha256:string|null;artifacts:string[];attempts:{attempt:number;state:string;session_id:string|null;
    error:string|null;checks:{pass:boolean;errors:string[];checks:string[];limitations:string[]}|null}[]};

export default function RunPanel({projectId, runs, openRunRequest, busy, onStart, onSubmit, onReconcile}: {
  projectId:string;runs:History['runs'];busy:boolean;onStart:(id:string)=>Promise<void>;
  openRunRequest:{id:string;nonce:number}|null;
  onSubmit:(id:string)=>Promise<void>;onReconcile:(id:string)=>Promise<void>}) {
  const [details,setDetails] = useState<RunDetail[]>([]);
  const [error,setError] = useState('');
  const [selection,setSelection] = useState<{projectId:string;id:string}|null>(null);
  useEffect(() => {
    if (openRunRequest && runs.some(run => run.id === openRunRequest.id))
      setSelection({projectId,id:openRunRequest.id});
  },[openRunRequest,projectId]);
  const selectedId = selection?.projectId === projectId && runs.some(run => run.id === selection.id)
    ? selection.id : null;
  const [observations,setObservations] = useState<Record<string,string>>({});
  const onObserved=useCallback((status:string) => {
    if (!selectedId)return;
    setObservations(old => old[selectedId]===status ? old : {...old,[selectedId]:status});
  },[selectedId]);
  const labels:Record<string,string> = {
    APPROVED:'Đã duyệt', IMPLEMENTING:'Đang tạo code', PREFLIGHT:'Sẵn sàng gửi',
    SUBMITTING:'Đang gửi Kaggle', UNKNOWN:'Cần đối soát', FAILED:'Có lỗi',
    REMOTE_RUNNING:'Kaggle đang chạy', REMOTE_SUCCEEDED:'Kaggle hoàn tất',
    REMOTE_FAILED:'Kaggle có lỗi', COMPLETED:'Hoàn tất',COLLECTING:'Kaggle hoàn tất · Chờ outputs',RUNNING:'Kaggle đang chạy',QUEUED:'Đang xếp hàng',STARTING:'Đang khởi động',
  };
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
    {!!runs.length && <span className="muted">{runs.length} run</span>}</div>
    {!runs.length && <p className="empty">Chưa có lần chạy. Lập và duyệt proposal ở Idea để tạo run.</p>}
    {error && <p role="alert">{error}</p>}
    {!!runs.length && <div className="run-cards" aria-label="Danh sách run">
      {runs.map(run => <button type="button" key={run.id}
        className={`run-card ${selectedId === run.id ? 'selected' : ''}`}
        aria-expanded={selectedId === run.id} aria-controls="run-detail"
        onClick={() => setSelection(selectedId === run.id ? null : {projectId,id:run.id})}>
        <span className="run-alias">Run {run.id.slice(0,8)}</span>
        <span className="run-card-status" data-state={observations[run.id] || run.state}>
          <span className="run-status-dot" aria-hidden="true"/>{labels[observations[run.id] || run.state] || observations[run.id] || run.state}
        </span>
      </button>)}
    </div>}
    {!!runs.length && !selectedId && <p className="muted run-hint">Chọn một run để xem chi tiết và thao tác.</p>}
    {selectedId && !details.some(run => run.id === selectedId) && !error && <p role="status" className="muted">Đang tải chi tiết run…</p>}
    {details.filter(run => run.id === selectedId).map(run => <article className="resource run-detail" id="run-detail" key={run.id} aria-label={`Chi tiết Run ${run.id.slice(0,8)}`}>
      <div className="panel-head"><h3>Run {run.id.slice(0,8)}</h3>
        <button type="button" onClick={() => setSelection(null)}>Đóng chi tiết</button></div>
      <div className="panel-head"><code className="source-id">{run.id}</code><span className="state-tag">{observations[run.id] || run.state}</span></div>
      {run.state === 'APPROVED' && <p>Proposal đã duyệt. Tạo code và notebook từ snapshot đã pin; chưa gửi Kaggle.</p>}
      {run.state === 'IMPLEMENTING' && <p role="status">Codex đang tạo code / kiểm preflight… Bạn có thể chuyển tab.</p>}
      {run.error && <p role="alert" className="alert error">{run.error}</p>}
      {!run.identity && (run.state === 'APPROVED' || run.state === 'FAILED') && <button className="primary"
        disabled={busy || run.attempts.length >= run.coder_budget}
        onClick={() => void onStart(run.id)}>{run.state === 'FAILED' ? 'Tiếp tục trong ngân sách còn lại' : 'Tạo code và notebook bằng Codex'}</button>}
      <p className="muted">Coder: {run.attempts.length}/{run.coder_budget} lượt đã cấp · Submit: {run.identity?.submit_attempts || 0}/1.</p>
      {run.state === 'SUBMITTING' && <p role="status">Đang gửi notebook qua MCP và xác minh phiên chạy…</p>}
      {run.ready && <button className="primary" disabled={busy} onClick={() => void onSubmit(run.id)}>Gửi notebook và chạy trên Kaggle</button>}
      {run.identity && <div className="context"><h3>Notebook trên Kaggle</h3>
        <a href={`https://www.kaggle.com/code/${run.identity.kernel_ref}${run.identity.script_version_id ? `?scriptVersionId=${run.identity.script_version_id}` : ''}`} target="_blank" rel="noreferrer">{run.identity.kernel_ref} ↗</a>
        <p>Account: {run.identity.username} · Version: {run.identity.version ?? 'chưa xác minh'}</p>
        <code className="source-id">Kernel: {run.identity.kernel_id ?? '?'} · Session: {run.identity.session_id ?? '?'} · Script version: {run.identity.script_version_id ?? '?'}</code>
        {run.identity.status && <p>Trạng thái Kaggle: {run.identity.status}</p>}
        {run.state === 'UNKNOWN' && <p>Chưa biết chắc kết quả gửi. Đối soát chỉ đọc notebook đã gửi; không tạo lần gửi mới.</p>}
        <button disabled={busy || run.state === 'SUBMITTING'} onClick={() => void onReconcile(run.id)}>{run.state === 'UNKNOWN' ? 'Đối soát lần gửi' : 'Cập nhật trạng thái từ Kaggle'}</button>
      </div>}
      <div className="context"><h3>Mục tiêu</h3><p>{run.purpose}</p><code className="source-id">Proposal {run.proposal_id} · v{run.proposal_version}</code>
        {!!run.expected_outputs?.length && <p className="muted">Đầu ra đã duyệt: {run.expected_outputs.join(' · ')}</p>}
      </div>
      {run.identity?.session_id && <RunMonitorPanel key={run.id} projectId={projectId} runId={run.id} onObserved={onObserved}/>}
      {run.attempts.map(attempt => <div className="context" key={attempt.attempt}>
        <h3>Bản code {attempt.attempt} · {attempt.state}</h3>
        {attempt.session_id && <code className="source-id">Codex session {attempt.session_id}</code>}
        {attempt.checks && <><p>Preflight: {attempt.checks.pass ? 'PASS' : 'FAIL'}</p>
          <ul>{attempt.checks.checks.map(item => <li key={item}>{item}</li>)}</ul>
          {attempt.checks.errors.map(item => <p role="alert" key={item}>{item}</p>)}</>}
        {attempt.error && <p>{attempt.error}</p>}
      </div>)}
      {run.ready && <p className="alert">Notebook đã qua preflight. Nút gửi dùng đúng proposal đã duyệt, tối đa một lần submit; mount và model cần được xác nhận khi chạy thật.</p>}
      {run.code_sha256 && <code className="source-id">Code SHA256 {run.code_sha256}</code>}
      {!!run.artifacts.length && <><h3>Artifacts đã lưu</h3><div className="stack">{run.artifacts.map(name =>
        <a key={name} href={`/api/projects/${projectId}/runs/${run.id}/artifacts/${name}`} target="_blank" rel="noreferrer">{name} ↗</a>)}</div></>}
    </article>)}
  </section>;
}
