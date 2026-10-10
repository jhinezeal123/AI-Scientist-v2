import {useState} from 'react';
import {Idea,ideaTitle,modeLabel} from './api';

const labels:Record<string,string>={
  DRAFT:'Bản nháp', PLANNING:'Đang lập proposal', NEEDS_CLARIFICATION:'Cần trả lời',
  AWAITING_APPROVAL:'Chờ duyệt', APPROVED:'Đã duyệt', FAILED:'Có lỗi', NEEDS_REVIEW:'Cần xem lại proposal',
};

function TitleEditor({idea,busy,onRename}:{idea:Idea;busy:boolean;onRename:(idea:Idea,title:string)=>Promise<void>}) {
  const [title,setTitle]=useState(idea.title);
  return <form className="stack" onSubmit={event=>{event.preventDefault();void onRename(idea,title);}}>
    <label>Đổi tiêu đề<input value={title} required maxLength={80} disabled={busy}
      placeholder="Đặt tiêu đề ngắn gọn" onChange={event=>setTitle(event.target.value)}/></label>
    <div className="actions"><button disabled={busy || !title.trim() || title.trim()===idea.title}>Lưu tiêu đề</button></div>
  </form>;
}

export default function IdeaCards({ideas,selectedId,busy,onSelect,onEdit,onRename,onDelete,onRestore}:{
  ideas:Idea[];selectedId:string;busy:boolean;onSelect:(id:string)=>void;onEdit:(idea:Idea)=>void;
  onRename:(idea:Idea,title:string)=>Promise<void>;
  onDelete:(id:string)=>Promise<void>;onRestore:(id:string)=>Promise<void>;
}) {
  const [showDeleted,setShowDeleted]=useState(false);
  const visible=ideas.filter(idea=>Boolean(idea.deleted_at)===showDeleted);
  const deletedCount=ideas.filter(idea=>idea.deleted_at).length;
  const selected=visible.find(idea=>idea.id===selectedId && !idea.deleted_at);
  return <div className="saved-ideas">
    <div className="panel-head section-heading"><h2>Idea đã lưu</h2>
      <button type="button" disabled={busy} onClick={()=>{setShowDeleted(!showDeleted);onSelect('');}}>
        {showDeleted ? 'Idea đã lưu' : `Đã xóa (${deletedCount})`}</button>
      {!!visible.length && <span className="muted">{visible.length} idea</span>}</div>
    {!visible.length && <p className="empty">{showDeleted ? 'Chưa có idea đã xóa.' : 'Chưa có idea.'}</p>}
    {!!visible.length && <div className="idea-cards" aria-label={showDeleted ? 'Idea đã xóa' : 'Danh sách idea'}>
      {visible.map(idea=><button type="button" key={idea.id} disabled={!!idea.deleted_at && busy}
        aria-label={idea.deleted_at ? `Khôi phục idea ${ideaTitle(idea)}` : undefined}
        className={`idea-card ${selectedId===idea.id ? 'selected' : ''}`}
        aria-expanded={selectedId===idea.id} aria-controls="idea-detail"
        onClick={()=>idea.deleted_at ? void onRestore(idea.id) : onSelect(selectedId===idea.id ? '' : idea.id)}>
        <span className="idea-alias" title={ideaTitle(idea)}>{ideaTitle(idea)}</span>
        <span className="mode-tag" data-mode={idea.mode}>{modeLabel(idea.mode,idea.mode_legacy)}</span>
        {!idea.title && <small className="idea-preview" title={idea.text.slice(0,160)}>{idea.text.slice(0,80)}</small>}
        <span className="idea-card-status" data-state={idea.state}>
          <span className="idea-status-dot" aria-hidden="true"/>{idea.deleted_at ? 'Đã xóa · bấm để khôi phục' : labels[idea.state] || idea.state}
        </span>
      </button>)}
    </div>}
    {!!visible.length && !selected && !showDeleted && <p className="muted">Chọn một idea để xem nội dung và proposal.</p>}
    {selected && <article className="resource idea-detail" id="idea-detail"
      aria-label={`Chi tiết idea: ${ideaTitle(selected)}`}>
      <div className="panel-head"><h3>{ideaTitle(selected)}</h3>
        <button type="button" onClick={()=>onSelect('')}>Đóng chi tiết</button></div>
      <TitleEditor key={`${selected.id}:${selected.title}`} idea={selected} busy={busy} onRename={onRename}/>
      <p className="source-meta">{labels[selected.state] || selected.state} · {new Date(selected.created_at).toLocaleString('vi-VN')}</p>
      <p className="mode-tag" data-mode={selected.mode}>{modeLabel(selected.mode,selected.mode_legacy)}</p>
      {selected.benchmark_id && <p className="muted">Benchmark: {selected.benchmark_id.slice(0,8)}</p>}
      {selected.benchmark_definition && <div className="context"><h3>Định nghĩa benchmark</h3><p>{selected.benchmark_definition.metric.name} · {selected.benchmark_definition.metric.direction}</p><pre>{selected.benchmark_definition.metric.definition}</pre><h4>Test</h4><pre>{selected.benchmark_definition.test_split}</pre><h4>Train (tùy chọn)</h4><pre>{selected.benchmark_definition.train_split||'Không có tập train'}</pre><p>Dataset sẽ được tạo public.</p></div>}
      {selected.mode==='etc' && <><h3>Đầu ra mong muốn</h3><pre>{selected.desired_output || 'Chưa nhập'}</pre></>}
      {selected.variant && <p className="muted">Biến thể từ Run {selected.variant.parent_run_id.slice(0,8)} · {selected.variant.purpose}</p>}
      <pre>{selected.text}</pre><code className="source-id">{selected.id}</code>
      <button type="button" disabled={busy || selected.state==='PLANNING' || selected.state==='APPROVED'}
        onClick={()=>onEdit(selected)}>{selected.variant ? 'Sửa mode / đầu ra' : 'Sửa idea'}</button>
      <button type="button" className="danger-button" disabled={busy || selected.state==='PLANNING'}
        onClick={()=>void onDelete(selected.id)}>Xóa idea</button>
    </article>}
  </div>;
}
