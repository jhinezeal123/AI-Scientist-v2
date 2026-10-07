import {useCallback, useEffect, useState} from 'react';
import {api, History} from './api';
import RunMonitorPanel from './RunMonitorPanel';

type RunDetail = {id:string;proposal_id:string;proposal_version:number;state:string;ready:boolean;error:string|null;coder_calls:number;
  can_retry:boolean;parent_run_id:string|null;
  purpose:string;expected_outputs:string[];report_path:string|null;report_preview?:string;
  result_metric?:{name:string;direction:string;final_value:number;best_value:number};
  collection?:{phase:string;report_attempts:number;report_limit:number};
  identity:{account:string;username:string;kernel_ref:string;version?:number;session_id?:number;kernel_id?:number;script_version_id?:number;status?:string;submit_attempts:number}|null;
  code_sha256:string|null;artifacts:string[];attempts:{attempt:number;state:string;session_id:string|null;origin:'CODEX'|'REUSE';
    error:string|null;checks:{pass:boolean;errors:string[];checks:string[];limitations:string[]}|null}[]};

export default function RunPanel({projectId, runs, busy, onStart, onSubmit, onReconcile, onRetry}: {
  projectId:string;runs:History['runs'];busy:boolean;onStart:(id:string)=>Promise<void>;
  onSubmit:(id:string)=>Promise<void>;onReconcile:(id:string)=>Promise<void>;
  onRetry:(id:string)=>Promise<string|undefined>}) {
  const [details,setDetails] = useState<RunDetail[]>([]);
  const [error,setError] = useState('');
  const [selection,setSelection] = useState<{projectId:string;id:string}|null>(null);
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
    REMOTE_FAILED:'Kaggle có lỗi', COMPLETED:'Hoàn tất',COLLECTING:'Đang hoàn tất kết quả',RUNNING:'Kaggle đang chạy',QUEUED:'Đang xếp hàng',STARTING:'Đang khởi động',
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
          <span className="run-status-dot" aria-hidden="true"/>{run.state === 'COLLECTING' && details.find(item => item.id === run.id)?.collection?.phase === 'retry_exhausted'
            ? 'Report cần xử lý' : labels[observations[run.id] || run.state] || observations[run.id] || run.state}
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
      {!run.identity && ['APPROVED','FAILED','PREFLIGHT'].includes(run.state) && <button className="primary"
        disabled={busy}
        onClick={() => void onStart(run.id)}>{run.state === 'APPROVED' && !run.attempts.length ? 'Tạo code và notebook bằng Codex' : 'Tạo lại / sửa code bằng Codex'}</button>}
      <p className="muted">Đã gọi coder {run.coder_calls} lượt · Đã gửi Kaggle {run.identity?.submit_attempts || 0} lượt trong run này. Không giới hạn tổng số lượt bạn yêu cầu.</p>
      {run.parent_run_id && <p className="muted">Tạo từ Run {run.parent_run_id.slice(0,8)} · dùng cùng proposal đã duyệt.</p>}
      {run.can_retry && <div className="stack"><button disabled={busy} onClick={() => void onRetry(run.id).then(id => {
        if (id)setSelection({projectId,id});
      })}>Tạo lượt chạy mới</button><small className="muted">Dùng lại code đã lưu và proposal đã duyệt. Trong run mới, bạn chọn sửa code hoặc gửi Kaggle.</small></div>}
      {run.collection && <p className="muted">Report: {run.collection.report_attempts}/{run.collection.report_limit} lượt đã cấp.</p>}
      {run.state === 'COLLECTING' && run.collection?.phase === 'retry_exhausted' && <p role="alert" className="alert error">Outputs đã được xác minh. Report đã hết lượt thử cho phép; cần xử lý lỗi và duyệt thêm lượt report để tiếp tục.</p>}
      {run.state === 'SUBMITTING' && <p role="status">Đang gửi notebook qua MCP và xác minh phiên chạy…</p>}
      {run.ready && <button className="primary" disabled={busy} onClick={() => void onSubmit(run.id)}>Gửi notebook và chạy trên Kaggle</button>}
      {run.identity && <div className="context"><h3>Notebook trên Kaggle</h3>
        <a href={`https://www.kaggle.com/code/${run.identity.kernel_ref}${run.identity.script_version_id ? `?scriptVersionId=${run.identity.script_version_id}` : ''}`} target="_blank" rel="noreferrer">{run.identity.kernel_ref} ↗</a>
        <p>Account: {run.identity.username} · Version: {run.identity.version ?? 'chưa xác minh'}</p>
        <code className="source-id">Kernel: {run.identity.kernel_id ?? '?'} · Session: {run.identity.session_id ?? '?'} · Script version: {run.identity.script_version_id ?? '?'}</code>
        {run.identity.status && <p>Trạng thái Kaggle: {run.identity.status}</p>}
        {run.state === 'UNKNOWN' && <p>Chưa biết chắc kết quả gửi. Đối soát chỉ đọc notebook đã gửi; không tạo lần gửi mới.</p>}
        <button disabled={busy || run.state === 'SUBMITTING'} onClick={() => void onReconcile(run.id)}>{run.state === 'UNKNOWN' ? 'Đối soát lần gửi' : 'Cập nhật trạng thái từ Kaggle'}</button>
        {(['REMOTE_SUCCEEDED','COLLECTING'].includes(observations[run.id] || run.state) && run.collection?.phase !== 'retry_exhausted') && <p role="status">Kaggle đã hoàn tất. Workbench đang xác minh outputs và tạo report.</p>}
      </div>}
      <div className="context"><h3>Mục tiêu</h3><p>{run.purpose}</p><code className="source-id">Proposal {run.proposal_id} · v{run.proposal_version}</code>
        {!!run.expected_outputs?.length && <p className="muted">Đầu ra đã duyệt: {run.expected_outputs.join(' · ')}</p>}
        {run.result_metric && <p>Kết quả đo được: {run.result_metric.name} · {run.result_metric.direction} · cuối {run.result_metric.final_value} · tốt nhất {run.result_metric.best_value}</p>}
      </div>
      {run.identity?.session_id && <RunMonitorPanel key={run.id} projectId={projectId} runId={run.id} onObserved={onObserved}/>}
      {run.attempts.map(attempt => <div className="context" key={attempt.attempt}>
        <h3>Bản code {attempt.attempt} · {attempt.origin === 'REUSE' ? 'Dùng lại code' : 'Codex'} · {attempt.state}</h3>
        {attempt.session_id && <code className="source-id">Codex session {attempt.session_id}</code>}
        {attempt.checks && <><p>Preflight: {attempt.checks.pass ? 'PASS' : 'FAIL'}</p>
          <ul>{attempt.checks.checks.map(item => <li key={item}>{item}</li>)}</ul>
          {attempt.checks.errors.map(item => <p role="alert" key={item}>{item}</p>)}</>}
        {attempt.error && <p>{attempt.error}</p>}
      </div>)}
      {run.ready && <p className="alert">Notebook đã qua preflight. Bấm gửi để chạy lượt này trên Kaggle. Sau khi kết thúc, dùng “Tạo lượt chạy mới” để chạy tiếp; mount và model cần được xác nhận khi chạy thật.</p>}
      {run.code_sha256 && <code className="source-id">Code SHA256 {run.code_sha256}</code>}
      {!!run.artifacts.length && <><h3>Artifacts đã lưu</h3><div className="stack">{run.artifacts.map(name =>
        <a key={name} href={`/api/projects/${projectId}/runs/${run.id}/artifacts/${name}`} target="_blank" rel="noreferrer">{name} ↗</a>)}</div></>}
      {run.report_path === 'report.md' && <><h3>Report</h3><a href={`/api/projects/${projectId}/runs/${run.id}/artifacts/report.md`} target="_blank" rel="noreferrer">Mở report ↗</a>
        {run.report_preview && <pre className="report-preview">{run.report_preview}</pre>}</>}
    </article>)}
  </section>;
}
