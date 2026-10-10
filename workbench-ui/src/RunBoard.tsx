import {useMemo,useState} from 'react';
import {History} from './api';

type Run=History['runs'][number];

export default function RunBoard({runs,selectedId,onSelect,onCompare,onBatch}:{runs:Run[];selectedId:string|null;
  onSelect:(id:string)=>void;onCompare:(ids:string[])=>void;onBatch:(ids:string[])=>void}) {
  const [query,setQuery]=useState(''),[state,setState]=useState('all');
  const [compare,setCompare]=useState<string[]>([]);
  const states=useMemo(()=>['all',...new Set(runs.map(run=>run.state))],[runs]);
  const visible=runs.filter(run=>!run.deleted_at && (state==='all'||run.state===state)
    && `${run.title||''} ${run.purpose||''} ${run.account||''} ${run.id}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  function toggle(id:string) {setCompare(current=>current.includes(id)?current.filter(item=>item!==id)
    :current.length<8?[...current,id]:current);}
  const batchReady=compare.length>=2 && compare.every(id=>runs.some(run=>run.id===id
    && ['APPROVED','PREFLIGHT','FAILED'].includes(run.state) && !run.working));
  return <section className="run-board" aria-label="Bảng run"><div className="panel-head"><h3>Run board</h3>
    <span className="muted">{visible.length}/{runs.filter(run=>!run.deleted_at).length} run</span></div>
    <div className="run-board-controls"><label>Tìm purpose/account<input value={query} onChange={e=>setQuery(e.target.value)}
      placeholder="Tên, purpose, account hoặc ID"/></label><label>Trạng thái<select value={state} onChange={e=>setState(e.target.value)}>
        {states.map(item=><option key={item} value={item}>{item==='all'?'Tất cả':item}</option>)}</select></label>
      <button type="button" disabled={compare.length<2} onClick={()=>onCompare(compare)}>So sánh {compare.length||''}</button>
      <button type="button" disabled={!batchReady} title="Chỉ các run đã được duyệt và chưa mở Working"
        onClick={()=>onBatch(compare)}>Batch Working</button></div>
    <div className="run-board-scroll"><table className="run-board-table"><thead><tr><th scope="col">So sánh</th><th scope="col">Run / mục đích</th>
      <th scope="col">Proposal / đầu vào</th><th scope="col">Trạng thái</th><th scope="col">Account</th><th scope="col">Session</th><th scope="col">Kết quả</th></tr></thead><tbody>
      {visible.map(run=><tr key={run.id} data-selected={run.id===selectedId}><td><input type="checkbox" aria-label={`So sánh ${run.title||run.id}`}
        checked={compare.includes(run.id)} onChange={()=>toggle(run.id)}/></td>
        <td><button className="run-board-open" type="button" onClick={()=>onSelect(run.id)}>{run.title||run.id.slice(0,8)}</button>
          <small className="run-purpose-preview" title={run.purpose}>{run.purpose||'Chưa có purpose'} · {run.id.slice(0,8)}</small></td>
        <td><span title={run.proposal_id}>v{run.proposal_version||'—'} · {run.proposal_id.slice(0,8)}</span>
          <small>{run.source_refs?.map(source=>`${source.title} v${source.version}`).join(', ')||'Không chọn data'}</small>
          <small title={run.protocol?.context_sha256}>Snapshot {run.protocol?.context_sha256.slice(0,8)||'—'} · seed {typeof run.protocol?.split==='object' && run.protocol.split ? String(run.protocol.split.seed??'—'):'—'}</small></td>
        <td>{run.state}{run.error && <small className="run-board-error" title={run.error}>{run.error}</small>}</td>
        <td>{run.account||'chưa gán'}</td><td className="mono">{run.session_id||'—'}</td>
        <td>{run.result_metric?`${run.result_metric.name}: ${run.result_metric.final_value}`:run.report_available?'Report đã lưu':'—'}
          <small>{run.artifacts?.length||0} artifact</small></td></tr>)}
      </tbody></table>{!visible.length && <p className="empty">Không có run phù hợp bộ lọc.</p>}</div>
  </section>;
}
